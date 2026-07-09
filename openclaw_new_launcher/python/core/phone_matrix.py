"""Matrix control plane for LOOM phone devices.

The control plane owns registry, orchestration metadata, events, and
experience summaries. Single-device execution remains delegated to the phone
Bridge/APKClaw layer.
"""

from __future__ import annotations

import hashlib
import csv
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from core.paths import AppPaths
from core.feishu_integration import FeishuAcquisitionIntegration


Json = Dict[str, Any]
DEFAULT_PHONE_MODEL = "qwen3.7-plus"

SENSITIVE_KEYS = {
    "token",
    "secret",
    "password",
    "apiKey",
    "api_key",
    "accessToken",
    "launcherSecret",
    "lumiLauncherSecret",
    "lumiLauncherId",
}

OUTREACH_MARKERS = (
    "批量私信",
    "私信所有",
    "自动私信",
    "批量评论",
    "自动评论",
    "自动回复",
    "批量触达",
    "群发",
    "骚扰",
)


class MatrixSafetyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MatrixControlPlane:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    @property
    def devices_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-devices.json")

    @property
    def phone_devices_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "phone-agents.json")

    @property
    def tasks_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-tasks.json")

    @property
    def events_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-events.jsonl")

    @property
    def experience_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-experience.jsonl")

    @property
    def leads_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-leads.jsonl")

    @property
    def acquisition_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "matrix-acquisition.json")

    def register_device(self, raw: Json) -> Json:
        devices = self._load_registered_devices()
        device_id = _device_id(raw.get("deviceId") or raw.get("id") or raw.get("name") or "phone-1")
        groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
        group = str(raw.get("group") or (groups[0] if groups else "default") or "default").strip() or "default"
        existing = next((item for item in devices if item.get("deviceId") == device_id), {})
        device = {
            **existing,
            "deviceId": device_id,
            "name": _clip(raw.get("name") or existing.get("name") or device_id, 80),
            "group": group,
            "groups": sorted({group, *[_clip(item, 80) for item in groups if str(item or "").strip()]}),
            "online": bool(raw.get("online", existing.get("online", False))),
            "heartbeatAt": _clip(raw.get("heartbeatAt") or existing.get("heartbeatAt") or _now_iso(), 64),
            "currentTaskId": _clip(raw.get("currentTaskId") or existing.get("currentTaskId") or "", 80),
            "busy": bool(raw.get("busy", existing.get("busy", False))),
            "currentScreenSummary": _clip(
                raw.get("currentScreenSummary") or raw.get("screenSummary") or existing.get("currentScreenSummary") or "",
                300,
            ),
            "failureCount": _int(raw.get("failureCount"), _int(existing.get("failureCount"), 0)),
            "model": _clip(raw.get("model") or existing.get("model") or DEFAULT_PHONE_MODEL, 120),
            "lastResult": _clip(raw.get("lastResult") or existing.get("lastResult") or "", 300),
            "lastEventAt": _clip(raw.get("lastEventAt") or existing.get("lastEventAt") or "", 64),
            "streamStatus": _clip(raw.get("streamStatus") or existing.get("streamStatus") or "", 40),
            "streamLatencyMs": _int(raw.get("streamLatencyMs"), _int(existing.get("streamLatencyMs"), 0)),
            "currentPackage": _clip(raw.get("currentPackage") or existing.get("currentPackage") or "", 160),
            "foregroundApp": _clip(raw.get("foregroundApp") or existing.get("foregroundApp") or "", 120),
            "accessibilityRunning": _optional_bool(raw.get("accessibilityRunning"), existing.get("accessibilityRunning")),
            "screenOn": _optional_bool(raw.get("screenOn"), existing.get("screenOn")),
            "deviceLocked": _optional_bool(raw.get("deviceLocked"), existing.get("deviceLocked")),
            "runningTaskCount": _int(raw.get("runningTaskCount"), _int(existing.get("runningTaskCount"), 0)),
            "updatedAt": _now_iso(),
        }
        next_devices = [item for item in devices if item.get("deviceId") != device_id]
        next_devices.append(device)
        self._write_json(self.devices_path, {"schema": "loom.matrix.devices.v1", "devices": next_devices})
        return _public_device(device)

    def status(self) -> Json:
        devices = [_public_device(item) for item in self._load_devices()]
        tasks = self._load_tasks().get("campaigns", [])
        return {
            "schema": "loom.matrix.v1",
            "updatedAt": _now_iso(),
            "devices": devices,
            "summary": {
                "total": len(devices),
                "online": sum(1 for item in devices if item.get("online")),
                "busy": sum(1 for item in devices if item.get("busy")),
                "failed": sum(1 for item in devices if int(item.get("failureCount") or 0) > 0),
            },
            "campaigns": _redact_json(tasks[-20:]),
        }

    def dispatch(self, raw: Json) -> Json:
        prompt = _clip(raw.get("prompt"), 2000)
        title = _clip(raw.get("title") or prompt[:40] or "Matrix task", 120)
        confirmed = _truthy(raw.get("confirmed"))
        self._check_safety(prompt, confirmed=confirmed)
        profile = _profile(raw.get("profile"))
        mode = _mode(raw.get("mode"))
        template = _template(raw.get("template") or raw.get("templateId") or _template_from_prompt(prompt))
        action = _direct_action(raw.get("action") or raw.get("directAction"), prompt)
        layer = _execution_layer(mode=mode, action=action, template=template, prompt=prompt)
        devices = self._target_devices(raw.get("target") if isinstance(raw.get("target"), dict) else raw)
        now = _now_iso()
        campaign_id = f"campaign_{uuid.uuid4().hex[:12]}"
        mission_id = f"mission_{uuid.uuid4().hex[:12]}"
        device_tasks = []
        retry_of = _clip(raw.get("retryOf") or raw.get("retry_of"), 80)
        self._append_event("queued", campaign_id, mission_id, "", "", "任务已进入 Matrix 队列")
        for device in devices:
            device_task_id = f"deviceTask_{uuid.uuid4().hex[:12]}"
            device_tasks.append(
                {
                    "deviceTaskId": device_task_id,
                    "deviceId": device["deviceId"],
                    "status": "running",
                    "executionLayer": layer,
                    "mode": mode,
                    "profile": profile,
                    "template": template,
                    "directAction": action,
                    "currentStep": _steps_for_layer(layer)[0]["stepId"],
                    "steps": _steps_for_layer(layer),
                    "createdAt": now,
                    "updatedAt": now,
                    "promptHash": _hash_prompt(prompt),
                }
            )
            self._update_device(device["deviceId"], {"currentTaskId": device_task_id, "online": True})
            self._append_event("assigned", campaign_id, mission_id, device_task_id, device["deviceId"], f"已分配到 {device['deviceId']}")
            self._append_event("running", campaign_id, mission_id, device_task_id, device["deviceId"], "任务进入执行中")
            self._append_event("step", campaign_id, mission_id, device_task_id, device["deviceId"], _steps_for_layer(layer)[0]["label"])
        campaign = {
            "campaignId": campaign_id,
            "title": title,
            "status": "running" if device_tasks else "queued",
            "safety": {"confirmationRequired": _needs_confirmation(prompt), "confirmed": confirmed},
            "retryOf": retry_of,
            "retryCount": _int(raw.get("retryCount"), 0),
            "retryBody": _retry_body_snapshot(
                prompt=prompt,
                mode=mode,
                profile=profile,
                template=template,
                action=action,
                devices=devices,
            ),
            "createdAt": now,
            "updatedAt": now,
            "missions": [
                {
                    "missionId": mission_id,
                    "status": "running" if device_tasks else "queued",
                    "createdAt": now,
                    "updatedAt": now,
                    "deviceTasks": device_tasks,
                }
            ],
        }
        tasks = self._load_tasks()
        campaigns = tasks.get("campaigns") if isinstance(tasks.get("campaigns"), list) else []
        campaigns.append(campaign)
        self._write_json(self.tasks_path, {"schema": "loom.matrix.tasks.v1", "campaigns": campaigns[-500:]})
        return _redact_json(campaign)

    def retry_failed(self, campaign_id: str, raw: Json | None = None) -> Json:
        body = raw if isinstance(raw, dict) else {}
        tasks = self._load_tasks()
        campaign = next((item for item in tasks.get("campaigns", []) if item.get("campaignId") == campaign_id), None)
        if not isinstance(campaign, dict):
            return {"retried": False, "campaignId": campaign_id, "reason": "campaign not found"}
        failed = []
        for mission in campaign.get("missions", []):
            for device_task in mission.get("deviceTasks", []):
                if isinstance(device_task, dict) and device_task.get("status") == "failed":
                    failed.append(device_task)
        if not failed:
            return {"retried": False, "campaignId": campaign_id, "reason": "没有失败设备任务"}
        retry_body = campaign.get("retryBody") if isinstance(campaign.get("retryBody"), dict) else {}
        prompt = _clip(body.get("prompt") or retry_body.get("promptPreview") or campaign.get("title") or "重试手机任务", 2000)
        retry_payload: Json = {
            "title": _clip(body.get("title") or f"重试 {campaign.get('title') or campaign_id}", 120),
            "prompt": prompt,
            "mode": _mode(body.get("mode") or retry_body.get("mode")),
            "profile": _profile(body.get("profile") or retry_body.get("profile")),
            "target": {"deviceIds": [str(item.get("deviceId") or "") for item in failed if str(item.get("deviceId") or "")][:100]},
            "retryOf": campaign_id,
            "retryCount": _int(campaign.get("retryCount"), 0) + 1,
            "confirmed": _truthy(body.get("confirmed")),
        }
        template = _template(body.get("template") or retry_body.get("template"))
        action = _direct_action(body.get("action") or retry_body.get("directAction"), prompt)
        if template:
            retry_payload["template"] = template
        if action:
            retry_payload["action"] = action
        task = self.dispatch(retry_payload)
        self._append_event(
            "retry",
            campaign_id,
            "",
            "",
            "",
            f"已生成重试任务 {task.get('campaignId')}",
        )
        return {"retried": True, "retryOf": campaign_id, "task": task, "dispatchBody": _redact_json(retry_payload)}

    def record_lead(self, raw: Json) -> Json:
        lead = {
            "schema": "loom.matrix.lead.v1",
            "leadId": f"lead_{uuid.uuid4().hex[:12]}",
            "createdAt": _now_iso(),
            "updatedAt": _now_iso(),
            "source": _lead_source(raw.get("source")),
            "status": _lead_status(raw.get("status")),
            "deviceId": _clip(raw.get("deviceId"), 80),
            "campaignId": _clip(raw.get("campaignId"), 80),
            "deviceTaskId": _clip(raw.get("deviceTaskId"), 80),
            "title": _clip(raw.get("title") or "手机线索", 120),
            "summary": _safe_lead_summary(raw.get("summary") or raw.get("note") or raw.get("description")),
            "tags": _safe_tags(raw.get("tags")),
        }
        self._append_jsonl(self.leads_path, lead)
        return _redact_json(lead)

    def list_leads(self, *, limit: int = 100) -> Json:
        rows = self._read_jsonl(self.leads_path)
        bounded = max(1, min(int(limit or 100), 500))
        return {"schema": "loom.matrix.leads.v1", "leads": _redact_json(rows[-bounded:])}

    def acquisition_snapshot(self) -> Json:
        state = self._load_acquisition_state()
        drafts = [item for item in state["drafts"] if isinstance(item, dict)]
        feishu = FeishuAcquisitionIntegration(self.paths).status()
        return _redact_json(
            {
                "schema": "loom.customer_acquisition.v1",
                "updatedAt": state.get("updatedAt") or _now_iso(),
                "contentTasks": state["contentTasks"][-50:],
                "leads": state["leads"][-100:],
                "customers": state["customers"][-100:],
                "drafts": drafts[-100:],
                "agentRuns": state.get("agentRuns", [])[-50:],
                "sop": state["sop"],
                "logs": state["logs"][-100:],
                "stats": {
                    "contentTasks": len(state["contentTasks"]),
                    "leads": len(state["leads"]),
                    "customers": len(state["customers"]),
                    "agentRuns": len(state.get("agentRuns", [])),
                    "draftsPending": sum(1 for item in drafts if item.get("status") == "pending_manual_review"),
                    "approvedDrafts": sum(1 for item in drafts if item.get("status") == "approved_pending_manual_send"),
                    "pendingSync": sum(1 for item in state["leads"] if item.get("syncStatus") in {"pending_sync", "sync_failed"}),
                },
                "outboundPolicy": _acquisition_policy(),
                "integrations": {
                    "feishu": feishu,
                },
            }
        )

    def create_acquisition_demo_flow(self, raw: Json) -> Json:
        state = self._load_acquisition_state()
        now = _now_iso()
        topic = _clip(raw.get("topic") or "AI 矩阵获客内容", 120)
        platform = _acquisition_platform(raw.get("platform"))
        channel = _acquisition_channel(raw.get("channel"))
        knowledge = _safe_lead_summary(raw.get("knowledge") or "先判断客户意图，再给出案例和人工跟进入口。", limit=320)
        lead_summary = _safe_lead_summary(
            raw.get("leadSummary") or raw.get("summary") or "评论区出现潜在线索，适合进入人工跟进。",
            limit=320,
        )
        content_task = {
            "taskId": f"content_{uuid.uuid4().hex[:10]}",
            "createdAt": now,
            "title": topic,
            "platform": platform,
            "status": "draft_ready",
            "assetPlan": [
                "短视频脚本",
                "评论区线索观察",
                "人工确认后跟进",
            ],
        }
        lead = {
            "leadId": f"lead_{uuid.uuid4().hex[:12]}",
            "createdAt": now,
            "updatedAt": now,
            "source": "demo_flow",
            "platform": platform,
            "channel": channel,
            "status": "qualified",
            "title": f"{topic} 线索",
            "summary": lead_summary,
            "tags": ["mvp-demo", channel, platform],
        }
        customer = {
            "customerId": f"customer_{uuid.uuid4().hex[:12]}",
            "createdAt": now,
            "updatedAt": now,
            "leadId": lead["leadId"],
            "name": f"{platform.upper()} 潜在客户",
            "stage": "needs_follow_up",
            "summary": lead_summary,
            "allowedChannels": [channel],
        }
        draft = {
            "draftId": f"draft_{uuid.uuid4().hex[:12]}",
            "createdAt": now,
            "updatedAt": now,
            "leadId": lead["leadId"],
            "customerId": customer["customerId"],
            "channel": channel,
            "status": "pending_manual_review",
            "requiresHumanReview": True,
            "sendEnabled": False,
            "policy": _acquisition_policy(),
            "body": _safe_lead_summary(
                f"您好，看到您关注「{topic}」。{knowledge} 如果方便，我可以先整理一份方案草稿，您确认后再继续沟通。",
                limit=500,
            ),
        }
        sync = FeishuAcquisitionIntegration(self.paths).sync_lead(
            {
                **lead,
                "sourceTask": content_task["title"],
                "draft": draft["body"],
                "recommendedAction": "人工确认后跟进",
                "logId": lead["leadId"],
            }
        )
        lead["syncStatus"] = sync.get("syncStatus") or "pending_sync"
        lead["syncError"] = sync.get("syncError") or ""
        lead["feishuRecordId"] = sync.get("recordId") or ""
        state["contentTasks"].append(content_task)
        state["leads"].append(lead)
        state["customers"].append(customer)
        state["drafts"].append(draft)
        state["logs"].extend(
            [
                _acquisition_log("content_task.created", f"内容任务已生成：{topic}", now),
                _acquisition_log("lead.qualified", f"线索进入线索池：{lead['title']}", now),
                _acquisition_log("customer.created", "线索已沉淀到客户池", now),
                _acquisition_log("draft.created", "跟进草稿已生成，等待人工确认，不会自动发送", now),
            ]
        )
        state["updatedAt"] = now
        self._write_acquisition_state(state)
        return _redact_json({"contentTask": content_task, "lead": lead, "customer": customer, "draft": draft})

    def import_acquisition_leads(self, raw: Json) -> Json:
        state = self._load_acquisition_state()
        now = _now_iso()
        topic = _clip(raw.get("topic") or "真实线索导入", 120)
        platform = _acquisition_platform(raw.get("platform"))
        channel = _acquisition_channel(raw.get("channel"))
        knowledge = _safe_lead_summary(raw.get("knowledge") or "先确认客户需求，再给人工跟进方案。", limit=360)
        owner = _clip(raw.get("owner") or "", 80)
        source = _acquisition_source(raw.get("source"))
        agent_task_id = _clip(raw.get("agentTaskId") or raw.get("taskId"), 80)
        device_id = _clip(raw.get("deviceId"), 80)
        action_status = _clip(raw.get("actionStatus") or raw.get("status"), 80)
        rows = _parse_acquisition_import_rows(raw)
        existing_keys = {
            str(item.get("dedupeKey") or "")
            for item in state["leads"]
            if isinstance(item, dict) and str(item.get("dedupeKey") or "")
        }
        seen: set[str] = set()
        content_task = {
            "taskId": f"content_{uuid.uuid4().hex[:10]}",
            "createdAt": now,
            "title": topic,
            "platform": platform,
            "status": "imported",
            "assetPlan": ["真实线索导入", "规则意向评分", "飞书线索表写入", "人工确认跟进草稿"],
        }
        imported_leads: list[Json] = []
        imported_customers: list[Json] = []
        imported_drafts: list[Json] = []
        duplicate_count = 0
        sync_ok = 0
        sync_pending = 0
        sync_failed = 0
        feishu = FeishuAcquisitionIntegration(self.paths)

        for row in rows:
            safe_platform = _acquisition_platform(row.get("platform") or platform)
            safe_channel = _acquisition_channel(row.get("channel") or channel)
            title = _clip(row.get("title") or row.get("nickname") or row.get("account") or "潜在线索", 120)
            summary = _safe_lead_summary(
                row.get("summary") or row.get("rawContent") or row.get("content") or row.get("description") or title,
                limit=360,
            )
            profile_url = _safe_lead_url(row.get("profileUrl") or row.get("主页链接") or row.get("url"))
            content_url = _safe_lead_url(row.get("contentUrl") or row.get("内容链接") or "")
            dedupe_key = _acquisition_dedupe_key(safe_platform, profile_url or content_url, title, summary)
            if not summary or dedupe_key in existing_keys or dedupe_key in seen:
                duplicate_count += 1
                continue
            seen.add(dedupe_key)
            qualification = _qualify_acquisition_lead(summary, topic=topic, target=raw.get("target") or raw.get("targetCustomer"))
            lead = {
                "leadId": f"lead_{uuid.uuid4().hex[:12]}",
                "createdAt": now,
                "updatedAt": now,
                "source": source,
                "sourceTask": content_task["title"],
                "agentTaskId": agent_task_id,
                "deviceId": device_id,
                "actionStatus": action_status,
                "platform": safe_platform,
                "channel": safe_channel,
                "status": "qualified" if qualification["score"] >= 50 else "new",
                "title": title,
                "nickname": _clip(row.get("nickname") or title, 120),
                "summary": summary,
                "rawContent": summary,
                "profileUrl": profile_url,
                "contentUrl": content_url,
                "need": qualification["need"],
                "intentLevel": qualification["intentLevel"],
                "intentScore": qualification["score"],
                "qualificationSource": "rules",
                "qualificationReasons": qualification["reasons"],
                "recommendedAction": qualification["recommendedAction"],
                "owner": owner,
                "dedupeKey": dedupe_key,
                "tags": ["real-import", safe_channel, safe_platform, qualification["intentLevel"]],
            }
            customer = {
                "customerId": f"customer_{uuid.uuid4().hex[:12]}",
                "createdAt": now,
                "updatedAt": now,
                "leadId": lead["leadId"],
                "name": title,
                "stage": "needs_follow_up" if qualification["score"] >= 50 else "needs_qualification",
                "summary": summary,
                "intentLevel": qualification["intentLevel"],
                "owner": owner,
                "allowedChannels": [safe_channel],
            }
            draft_body = _safe_lead_summary(row.get("draftBody"), limit=500) or _build_acquisition_followup_draft(lead, knowledge)
            draft = {
                "draftId": f"draft_{uuid.uuid4().hex[:12]}",
                "createdAt": now,
                "updatedAt": now,
                "leadId": lead["leadId"],
                "customerId": customer["customerId"],
                "agentTaskId": agent_task_id,
                "deviceId": device_id,
                "channel": safe_channel,
                "status": "pending_manual_review",
                "requiresHumanReview": True,
                "sendEnabled": False,
                "policy": _acquisition_policy(),
                "body": draft_body,
            }
            sync = feishu.sync_lead({**lead, "draft": draft_body, "logId": lead["leadId"]})
            lead["syncStatus"] = sync.get("syncStatus") or "pending_sync"
            lead["syncError"] = sync.get("syncError") or ""
            lead["feishuRecordId"] = sync.get("recordId") or ""
            if lead["syncStatus"] == "synced":
                sync_ok += 1
            elif lead["syncStatus"] == "sync_failed":
                sync_failed += 1
            else:
                sync_pending += 1
            imported_leads.append(lead)
            imported_customers.append(customer)
            imported_drafts.append(draft)

        if imported_leads:
            state["contentTasks"].append(content_task)
            state["leads"].extend(imported_leads)
            state["customers"].extend(imported_customers)
            state["drafts"].extend(imported_drafts)
        state["logs"].extend(
            [
                _acquisition_log("lead.imported", f"真实线索导入 {len(imported_leads)} 条，去重 {duplicate_count} 条", now),
                _acquisition_log("lead.qualified", f"规则评分完成 {len(imported_leads)} 条，等待人工确认草稿", now),
                _acquisition_log("feishu.sync", f"飞书已同步 {sync_ok} 条，待同步 {sync_pending} 条，失败 {sync_failed} 条", now),
            ]
        )
        state["updatedAt"] = now
        self._write_acquisition_state(state)
        return _redact_json(
            {
                "imported": len(imported_leads),
                "duplicates": duplicate_count,
                "leads": imported_leads,
                "customers": imported_customers,
                "drafts": imported_drafts,
                "contentTask": content_task if imported_leads else None,
                "summary": f"导入 {len(imported_leads)} 条，去重 {duplicate_count} 条，飞书已同步 {sync_ok} 条，待同步 {sync_pending} 条，失败 {sync_failed} 条",
            }
        )

    def run_acquisition_agent_task(self, raw: Json) -> Json:
        dry_run = _truthy(raw.get("dryRun", True))
        if not dry_run and not _truthy(raw.get("confirmed")):
            return _redact_json(
                {
                    "error": "acquisition_agent_confirmation_required",
                    "executed": False,
                    "message": "Real phone Agent runs require confirmed=true and must still stop at human confirmation.",
                    "policy": _acquisition_policy(),
                }
            )
        agent_result = raw.get("agentResult") if isinstance(raw.get("agentResult"), dict) else {}
        if agent_result:
            ingest = self.ingest_acquisition_agent_result(agent_result, raw)
        else:
            ingest = {
                "imported": 0,
                "duplicates": 0,
                "leads": [],
                "customers": [],
                "drafts": [],
                "contentTask": None,
                "summary": "手机 Agent 任务已生成，等待真实回传入库",
            }
        agent_run = {
            "schema": "loom.acquisition.agent_run.v1",
            "dryRun": dry_run,
            "taskId": _clip(agent_result.get("taskId") or raw.get("taskId") or f"agent_task_{uuid.uuid4().hex[:10]}", 80),
            "deviceId": _clip(agent_result.get("deviceId") or raw.get("deviceId") or raw.get("device") or "phone-1", 80),
            "platform": _acquisition_platform(agent_result.get("platform") or raw.get("platform")),
            "action": _clip(agent_result.get("action") or raw.get("action") or "discover_leads", 80),
            "status": _clip(agent_result.get("status") or "pending_human_confirm", 80),
            "requiresHumanReview": True,
            "sendEnabled": False,
        }
        agent_run["phoneTask"] = _acquisition_phone_task_payload(raw, agent_run)
        state = self._load_acquisition_state()
        state["agentRuns"].append(agent_run)
        state["logs"].append(
            _acquisition_log(
                "agent.task_prepared",
                f"手机 Agent 获客任务已准备：{agent_run['taskId']} / {agent_run['platform']} / {agent_run['deviceId']}",
                _now_iso(),
            )
        )
        state["updatedAt"] = _now_iso()
        self._write_acquisition_state(state)
        return _redact_json({"agentRun": agent_run, "ingest": ingest, "snapshot": self.acquisition_snapshot()})

    def ingest_acquisition_agent_result(self, agent_result: Json, raw: Json | None = None) -> Json:
        body = raw if isinstance(raw, dict) else {}
        task_id = _clip(agent_result.get("taskId") or body.get("taskId") or f"agent_task_{uuid.uuid4().hex[:10]}", 80)
        device_id = _clip(agent_result.get("deviceId") or body.get("deviceId") or "", 80)
        platform = _acquisition_platform(agent_result.get("platform") or body.get("platform"))
        action = _clip(agent_result.get("action") or body.get("action") or "discover_leads", 80)
        status = _clip(agent_result.get("status") or "pending_human_confirm", 80)
        drafts = agent_result.get("drafts") if isinstance(agent_result.get("drafts"), list) else []
        draft = next((item for item in drafts if isinstance(item, dict)), {})
        policy_clamped = _agent_result_has_unsafe_outbound(agent_result)
        leads = []
        for item in agent_result.get("leads") if isinstance(agent_result.get("leads"), list) else []:
            if not isinstance(item, dict):
                continue
            leads.append(
                {
                    **item,
                    "platform": item.get("platform") or platform,
                    "channel": item.get("channel") or draft.get("channel") or "comment",
                    "draftBody": item.get("draftBody") or draft.get("body") or "",
                }
            )
        ingest = self.import_acquisition_leads(
            {
                "topic": body.get("topic") or f"{platform} 手机 Agent 获客任务",
                "platform": platform,
                "channel": draft.get("channel") or body.get("channel") or "comment",
                "knowledge": body.get("knowledge") or "手机 Agent 已返回线索，后续只生成草稿并等待人工确认。",
                "target": body.get("target") or "",
                "owner": body.get("owner") or "phone-agent",
                "leads": leads,
                "source": "phone_agent",
                "agentTaskId": task_id,
                "deviceId": device_id,
                "actionStatus": status,
                "status": status,
            }
        )
        state = self._load_acquisition_state()
        if policy_clamped:
            state["logs"].append(
                _acquisition_log(
                    "agent.result_policy_clamped",
                    f"手机 Agent 回传包含外发意图，已强制钳制为草稿/人工确认：{task_id}",
                    _now_iso(),
                )
            )
        state["logs"].append(_acquisition_log("agent.result_ingested", f"手机 Agent 结果已入库：{task_id} / {action} / {status}", _now_iso()))
        state["updatedAt"] = _now_iso()
        self._write_acquisition_state(state)
        return ingest

    def confirm_acquisition_draft(self, draft_id: str, raw: Json | None = None) -> Json:
        state = self._load_acquisition_state()
        body = raw if isinstance(raw, dict) else {}
        safe_id = _clip(draft_id, 80)
        now = _now_iso()
        for draft in state["drafts"]:
            if not isinstance(draft, dict) or draft.get("draftId") != safe_id:
                continue
            draft["status"] = "approved_pending_manual_send"
            draft["updatedAt"] = now
            draft["approvedBy"] = _clip(body.get("operator") or "human", 80)
            draft["sendEnabled"] = False
            draft["requiresHumanReview"] = True
            state["logs"].append(_acquisition_log("draft.approved", "草稿已人工确认，仍需在白名单和频控下手动发送", now))
            state["updatedAt"] = now
            self._write_acquisition_state(state)
            return _redact_json({"draft": draft, "snapshot": self.acquisition_snapshot()})
        return {"error": "draft not found", "draftId": safe_id}

    def record_acquisition_manual_send(self, draft_id: str, raw: Json | None = None) -> Json:
        state = self._load_acquisition_state()
        body = raw if isinstance(raw, dict) else {}
        safe_id = _clip(draft_id, 80)
        now = _now_iso()
        outcome = _manual_send_outcome(body.get("outcome"))
        for draft in state["drafts"]:
            if not isinstance(draft, dict) or draft.get("draftId") != safe_id:
                continue
            draft["status"] = "manual_sent" if outcome != "failed" else "manual_send_failed"
            draft["updatedAt"] = now
            draft["sendEnabled"] = False
            draft["requiresHumanReview"] = True
            draft["manualSend"] = {
                "outcome": outcome,
                "operator": _clip(body.get("operator") or "human", 80),
                "recordedAt": now,
                "reply": _safe_lead_summary(body.get("reply"), limit=320),
                "note": _safe_lead_summary(body.get("note"), limit=320),
                "nextFollowUpAt": _clip(body.get("nextFollowUpAt"), 80),
            }
            for customer in state["customers"]:
                if isinstance(customer, dict) and customer.get("customerId") == draft.get("customerId"):
                    customer["stage"] = "replied" if draft["manualSend"]["reply"] else ("contact_failed" if outcome == "failed" else "contacted")
                    customer["lastReply"] = draft["manualSend"]["reply"]
                    customer["nextFollowUpAt"] = draft["manualSend"]["nextFollowUpAt"]
                    customer["updatedAt"] = now
            for lead in state["leads"]:
                if isinstance(lead, dict) and lead.get("leadId") == draft.get("leadId"):
                    lead["status"] = "contact_failed" if outcome == "failed" else "contacted"
                    lead["updatedAt"] = now
            state["logs"].append(
                _acquisition_log(
                    "draft.manual_sent",
                    f"已记录人工触达：{safe_id} / {outcome}；系统未自动发送评论、私信或加好友。",
                    now,
                )
            )
            state["updatedAt"] = now
            self._write_acquisition_state(state)
            return _redact_json({"draft": draft, "snapshot": self.acquisition_snapshot()})
        return {"error": "draft not found", "draftId": safe_id}

    def watch(self, campaign_id: str | None = None, *, limit: int = 100) -> Json:
        events = self._load_events()
        if campaign_id:
            events = [event for event in events if event.get("campaignId") == campaign_id]
        return {"schema": "loom.matrix.events.v1", "events": _redact_json(events[-max(1, min(limit, 500)):])}

    def append_runtime_event(
        self,
        event_type: str,
        device_id: str,
        message: str,
        *,
        source: str = "runtime",
        details: Json | None = None,
    ) -> Json:
        safe_type = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(event_type or "runtime").strip()).strip(".-_")[:80] or "runtime"
        event = {
            "schema": "loom.matrix.event.v1",
            "eventId": f"evt_{uuid.uuid4().hex[:12]}",
            "timestamp": _now_iso(),
            "type": safe_type,
            "campaignId": "",
            "missionId": "",
            "deviceTaskId": "",
            "deviceId": _device_id(device_id) if str(device_id or "").strip() else "",
            "source": _clip(source, 80) or "runtime",
            "message": _clip(message, 320),
        }
        if isinstance(details, dict) and details:
            event["details"] = _redact_json(details)
        self._append_jsonl(self.events_path, event)
        return _redact_json(event)

    def append_task_event(self, event_type: str, device_task_id: str, message: str) -> Json:
        found = self._find_device_task(device_task_id)
        if not found:
            return {"ok": False, "error": "deviceTask not found"}
        self._append_event(
            event_type,
            str(found["campaign"].get("campaignId") or ""),
            str(found["mission"].get("missionId") or ""),
            device_task_id,
            str(found["deviceTask"].get("deviceId") or ""),
            _clip(message, 240),
        )
        return {"ok": True}

    def mark_step(self, device_task_id: str, step_id: str, *, status: str, message: str = "") -> Json:
        tasks = self._load_tasks()
        found = self._find_device_task(device_task_id, tasks=tasks)
        if not found:
            return {"ok": False, "error": "deviceTask not found"}
        now = _now_iso()
        device_task = found["deviceTask"]
        device_task["currentStep"] = step_id
        device_task["updatedAt"] = now
        for step in device_task.get("steps", []):
            if step.get("stepId") == step_id:
                step["status"] = status
                step["updatedAt"] = now
        found["campaign"]["updatedAt"] = now
        found["mission"]["updatedAt"] = now
        self._write_json(self.tasks_path, tasks)
        self._append_event(
            "step",
            str(found["campaign"].get("campaignId") or ""),
            str(found["mission"].get("missionId") or ""),
            device_task_id,
            str(device_task.get("deviceId") or ""),
            message or step_id,
        )
        return {"ok": True}

    def cancel(self, campaign_id: str) -> Json:
        tasks = self._load_tasks()
        changed = False
        for campaign in tasks.get("campaigns", []):
            if campaign.get("campaignId") != campaign_id:
                continue
            campaign["status"] = "cancelled"
            campaign["updatedAt"] = _now_iso()
            for mission in campaign.get("missions", []):
                mission["status"] = "cancelled"
                for device_task in mission.get("deviceTasks", []):
                    device_task["status"] = "cancelled"
                    self._append_event(
                        "cancelled",
                        campaign_id,
                        str(mission.get("missionId") or ""),
                        str(device_task.get("deviceTaskId") or ""),
                        str(device_task.get("deviceId") or ""),
                        "任务已取消",
                    )
                    self._update_device(str(device_task.get("deviceId") or ""), {"currentTaskId": ""})
            changed = True
        self._write_json(self.tasks_path, tasks)
        return {"cancelled": changed, "campaignId": campaign_id}

    def record_result(self, device_task_id: str, *, ok: bool, duration_ms: int, failure_reason: str = "") -> Json:
        tasks = self._load_tasks()
        found: Json | None = None
        campaign_id = ""
        mission_id = ""
        for campaign in tasks.get("campaigns", []):
            for mission in campaign.get("missions", []):
                for device_task in mission.get("deviceTasks", []):
                    if device_task.get("deviceTaskId") == device_task_id:
                        found = device_task
                        campaign_id = str(campaign.get("campaignId") or "")
                        mission_id = str(mission.get("missionId") or "")
                        break
        if found is None:
            return {"ok": False, "error": "deviceTask not found"}
        found["status"] = "succeeded" if ok else "failed"
        found["durationMs"] = int(duration_ms)
        found["failureReason"] = _clip(failure_reason, 200)
        found["updatedAt"] = _now_iso()
        for step in found.get("steps", []):
            if step.get("status") == "running":
                step["status"] = "succeeded" if ok else "failed"
                step["updatedAt"] = found["updatedAt"]
        self._refresh_campaign_status(tasks, campaign_id)
        self._write_json(self.tasks_path, tasks)
        event_type = "result" if ok else "error"
        self._append_event(event_type, campaign_id, mission_id, device_task_id, str(found.get("deviceId") or ""), "任务完成" if ok else "任务失败")
        self._update_device(
            str(found.get("deviceId") or ""),
            {
                "currentTaskId": "",
                "lastResult": "成功" if ok else (failure_reason or "失败"),
                "failureCount": 0 if ok else None,
            },
            increment_failure=not ok,
        )
        record = {
            "schema": "loom.matrix.experience_record.v1",
            "timestamp": _now_iso(),
            "deviceTaskId": device_task_id,
            "deviceId": found.get("deviceId"),
            "executionLayer": found.get("executionLayer"),
            "profile": found.get("profile"),
            "mode": found.get("mode"),
            "ok": bool(ok),
            "durationMs": int(duration_ms),
            "failureReason": _clip(failure_reason, 200),
            "promptHash": found.get("promptHash"),
        }
        self._append_jsonl(self.experience_path, record)
        return {"ok": True, "record": _redact_json(record)}

    def _find_device_task(self, device_task_id: str, *, tasks: Json | None = None) -> Json | None:
        tasks = tasks if isinstance(tasks, dict) else self._load_tasks()
        for campaign in tasks.get("campaigns", []):
            for mission in campaign.get("missions", []):
                for device_task in mission.get("deviceTasks", []):
                    if device_task.get("deviceTaskId") == device_task_id:
                        return {"campaign": campaign, "mission": mission, "deviceTask": device_task}
        return None

    def _refresh_campaign_status(self, tasks: Json, campaign_id: str) -> None:
        now = _now_iso()
        for campaign in tasks.get("campaigns", []):
            if campaign.get("campaignId") != campaign_id:
                continue
            mission_statuses = []
            for mission in campaign.get("missions", []):
                device_tasks = [item for item in mission.get("deviceTasks", []) if isinstance(item, dict)]
                statuses = {str(item.get("status") or "") for item in device_tasks}
                if not device_tasks:
                    mission["status"] = "queued"
                elif statuses.issubset({"succeeded"}):
                    mission["status"] = "succeeded"
                elif statuses and statuses.issubset({"failed", "succeeded", "cancelled"}):
                    mission["status"] = "failed" if "failed" in statuses else "cancelled"
                else:
                    mission["status"] = "running"
                mission["updatedAt"] = now
                mission_statuses.append(mission["status"])
            if mission_statuses and all(status == "succeeded" for status in mission_statuses):
                campaign["status"] = "succeeded"
            elif any(status == "failed" for status in mission_statuses):
                campaign["status"] = "failed"
            elif any(status == "running" for status in mission_statuses):
                campaign["status"] = "running"
            elif any(status == "cancelled" for status in mission_statuses):
                campaign["status"] = "cancelled"
            campaign["updatedAt"] = now
            return

    def experience_report(self) -> Json:
        rows = self._read_jsonl(self.experience_path)
        total = len(rows)
        success = sum(1 for item in rows if item.get("ok") is True)
        durations = [int(item.get("durationMs") or 0) for item in rows if int(item.get("durationMs") or 0) > 0]
        by_layer: dict[str, Json] = {}
        for item in rows:
            layer = str(item.get("executionLayer") or "unknown")
            bucket = by_layer.setdefault(layer, {"total": 0, "success": 0, "failures": 0})
            bucket["total"] += 1
            if item.get("ok") is True:
                bucket["success"] += 1
            else:
                bucket["failures"] += 1
        suggestions = []
        for layer, bucket in by_layer.items():
            if bucket["success"] >= 1:
                suggestions.append(
                    {
                        "id": f"matrix_tpl_{layer}",
                        "executionLayer": layer,
                        "reason": "该路径已有成功记录，可在人工确认后固化为模板。",
                        "requiresConfirmation": True,
                    }
                )
        return {
            "schema": "loom.matrix.experience.v1",
            "summary": {
                "total": total,
                "success": success,
                "failure": total - success,
                "successRate": round(success / total, 4) if total else 0,
                "avgDurationMs": round(sum(durations) / len(durations), 2) if durations else 0,
            },
            "byLayer": by_layer,
            "templateSuggestions": suggestions,
        }

    def _target_devices(self, target: Json) -> list[Json]:
        devices = [_public_device(item) for item in self._load_devices()]
        raw_ids = target.get("deviceIds") or target.get("devices") or target.get("deviceId")
        if isinstance(raw_ids, str):
            wanted_ids = {_device_id(raw_ids)}
        elif isinstance(raw_ids, list):
            wanted_ids = {_device_id(item) for item in raw_ids}
        else:
            wanted_ids = set()
        raw_groups = target.get("groups") or target.get("group")
        if isinstance(raw_groups, str):
            wanted_groups = {raw_groups}
        elif isinstance(raw_groups, list):
            wanted_groups = {str(item) for item in raw_groups}
        else:
            wanted_groups = set()
        if wanted_ids:
            return [item for item in devices if item.get("deviceId") in wanted_ids]
        if wanted_groups:
            return [item for item in devices if item.get("group") in wanted_groups or wanted_groups.intersection(set(item.get("groups") or []))]
        return devices[:5]

    def _check_safety(self, prompt: str, *, confirmed: bool) -> None:
        if _needs_confirmation(prompt) and not confirmed:
            raise MatrixSafetyError("safety_confirmation_required", "批量触达、私信、评论或自动回复任务需要用户明确确认。")

    def _update_device(self, device_id: str, patch: Json, *, increment_failure: bool = False) -> None:
        if not device_id:
            return
        devices = self._load_registered_devices()
        found = False
        for device in devices:
            if device.get("deviceId") != device_id:
                continue
            for key, value in patch.items():
                if value is not None:
                    device[key] = value
            if increment_failure:
                device["failureCount"] = int(device.get("failureCount") or 0) + 1
            device["updatedAt"] = _now_iso()
            found = True
            break
        if not found:
            device = {
                "deviceId": device_id,
                "name": device_id,
                "group": "default",
                "groups": ["default"],
                "online": False,
                "heartbeatAt": "",
                "currentTaskId": "",
                "currentScreenSummary": "",
                "failureCount": 0,
                "model": DEFAULT_PHONE_MODEL,
                "lastResult": "",
                "updatedAt": _now_iso(),
            }
            for key, value in patch.items():
                if value is not None:
                    device[key] = value
            if increment_failure:
                device["failureCount"] = int(device.get("failureCount") or 0) + 1
            devices.append(device)
        self._write_json(self.devices_path, {"schema": "loom.matrix.devices.v1", "devices": devices})

    def _append_event(self, event_type: str, campaign_id: str, mission_id: str, device_task_id: str, device_id: str, message: str) -> None:
        self._append_jsonl(
            self.events_path,
            {
                "schema": "loom.matrix.event.v1",
                "eventId": f"evt_{uuid.uuid4().hex[:12]}",
                "timestamp": _now_iso(),
                "type": event_type,
                "campaignId": campaign_id,
                "missionId": mission_id,
                "deviceTaskId": device_task_id,
                "deviceId": device_id,
                "message": message,
            },
        )

    def _load_devices(self) -> list[Json]:
        phone_devices = self._load_phone_config_devices()
        registered_devices = self._load_registered_devices()
        merged: dict[str, Json] = {}
        order: list[str] = []
        for device in phone_devices:
            device_id = str(device.get("deviceId") or "")
            if not device_id:
                continue
            merged[device_id] = device
            order.append(device_id)
        for device in registered_devices:
            device_id = str(device.get("deviceId") or "")
            if not device_id:
                continue
            base = merged.get(device_id, {})
            merged[device_id] = {
                **base,
                **device,
                "source": "matrix-registry" if not base else base.get("source", "phone-config"),
                "selected": bool(base.get("selected")),
            }
            if device_id not in order:
                order.append(device_id)
        return [merged[device_id] for device_id in order if device_id in merged]

    def _load_registered_devices(self) -> list[Json]:
        data = self._read_json(self.devices_path, {"devices": []})
        devices = data.get("devices") if isinstance(data, dict) else []
        return [item for item in devices if isinstance(item, dict)] if isinstance(devices, list) else []

    def _load_phone_config_devices(self) -> list[Json]:
        data = self._read_json(self.phone_devices_path, {"selectedDeviceId": "", "devices": []})
        devices = data.get("devices") if isinstance(data, dict) else []
        if not isinstance(devices, list):
            return []
        selected_id = _device_id(data.get("selectedDeviceId") or "")
        model = self._phone_model()
        rows: list[Json] = []
        for index, item in enumerate(devices, start=1):
            if not isinstance(item, dict):
                continue
            device_id = _device_id(item.get("id") or item.get("deviceId") or item.get("name") or f"phone-{index}")
            name = _clip(item.get("name") or item.get("id") or device_id, 80)
            last_seen = _clip(item.get("lastSeenAt") or item.get("lastCheckedAt") or "", 64)
            rows.append(
                {
                    "deviceId": device_id,
                    "name": name,
                    "group": _clip(item.get("group") or "本机手机", 80),
                    "groups": ["本机手机"],
                    "online": False,
                    "heartbeatAt": last_seen,
                    "currentTaskId": "",
                    "currentScreenSummary": "已保存手机连接配置",
                    "failureCount": 0,
                    "model": model,
                    "lastResult": "",
                    "updatedAt": last_seen,
                    "source": "phone-config",
                    "configSource": self.phone_devices_path,
                    "selected": device_id == selected_id or (not selected_id and index == 1),
                }
            )
        return rows

    def _phone_model(self) -> str:
        wire_path = getattr(self.paths, "wire_current", "")
        data = self._read_json(wire_path, {}) if wire_path else {}
        models = data.get("models") if isinstance(data, dict) else {}
        if isinstance(models, dict):
            model = _clip(models.get("phone"), 120)
            if model:
                return model
        return DEFAULT_PHONE_MODEL

    def _load_tasks(self) -> Json:
        data = self._read_json(self.tasks_path, {"schema": "loom.matrix.tasks.v1", "campaigns": []})
        if not isinstance(data, dict):
            return {"schema": "loom.matrix.tasks.v1", "campaigns": []}
        if not isinstance(data.get("campaigns"), list):
            data["campaigns"] = []
        return data

    def _load_acquisition_state(self) -> Json:
        data = self._read_json(
            self.acquisition_path,
            {
                "schema": "loom.customer_acquisition.v1",
                "updatedAt": "",
                "contentTasks": [],
                "leads": [],
                "customers": [],
                "drafts": [],
                "agentRuns": [],
                "logs": [],
                "sop": _default_acquisition_sop(),
            },
        )
        for key in ("contentTasks", "leads", "customers", "drafts", "agentRuns", "logs"):
            if not isinstance(data.get(key), list):
                data[key] = []
        if not isinstance(data.get("sop"), list):
            data["sop"] = _default_acquisition_sop()
        data["schema"] = "loom.customer_acquisition.v1"
        return data

    def _write_acquisition_state(self, state: Json) -> None:
        state["schema"] = "loom.customer_acquisition.v1"
        state["contentTasks"] = state.get("contentTasks", [])[-200:]
        state["leads"] = state.get("leads", [])[-500:]
        state["customers"] = state.get("customers", [])[-500:]
        state["drafts"] = state.get("drafts", [])[-500:]
        state["agentRuns"] = state.get("agentRuns", [])[-200:]
        state["logs"] = state.get("logs", [])[-500:]
        self._write_json(self.acquisition_path, state)

    def _load_events(self) -> list[Json]:
        return self._read_jsonl(self.events_path)

    def _read_json(self, path: str, default: Json) -> Json:
        if not os.path.exists(path):
            return dict(default)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else dict(default)
        except (OSError, json.JSONDecodeError):
            return dict(default)

    def _write_json(self, path: str, data: Json) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(_redact_json(data), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)

    def _append_jsonl(self, path: str, data: Json) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(_redact_json(data), ensure_ascii=False, separators=(",", ":")) + "\n")

    def _read_jsonl(self, path: str) -> list[Json]:
        if not os.path.exists(path):
            return []
        rows: list[Json] = []
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows[-1000:]


def _public_device(device: Json) -> Json:
    current_task_id = str(device.get("currentTaskId") or "")
    failure_count = int(device.get("failureCount") or 0)
    online = bool(device.get("online"))
    stream_status = str(device.get("streamStatus") or ("connected" if online else "offline"))
    stream_latency_ms = _int(device.get("streamLatencyMs"), 0)
    presence_age_ms = _timestamp_age_ms(device.get("lastEventAt") or "")
    if online and presence_age_ms >= 0:
        stream_latency_ms = max(stream_latency_ms, presence_age_ms)
        if presence_age_ms > 30000:
            online = False
            stream_status = "offline"
        elif presence_age_ms > 10000 and stream_status == "connected":
            stream_status = "unstable"
    return {
        "deviceId": str(device.get("deviceId") or ""),
        "name": str(device.get("name") or device.get("deviceId") or ""),
        "group": str(device.get("group") or "default"),
        "groups": [str(item) for item in (device.get("groups") or []) if str(item or "").strip()][:20],
        "online": online,
        "busy": bool(device.get("busy") or current_task_id),
        "heartbeatAt": str(device.get("heartbeatAt") or ""),
        "lastEventAt": str(device.get("lastEventAt") or ""),
        "streamStatus": stream_status,
        "streamLatencyMs": stream_latency_ms,
        "currentPackage": str(device.get("currentPackage") or ""),
        "foregroundApp": str(device.get("foregroundApp") or ""),
        "accessibilityRunning": device.get("accessibilityRunning") if isinstance(device.get("accessibilityRunning"), bool) else None,
        "screenOn": device.get("screenOn") if isinstance(device.get("screenOn"), bool) else None,
        "deviceLocked": device.get("deviceLocked") if isinstance(device.get("deviceLocked"), bool) else None,
        "runningTaskCount": _int(device.get("runningTaskCount"), 0),
        "currentTaskId": current_task_id,
        "currentScreenSummary": str(device.get("currentScreenSummary") or ""),
        "failureCount": failure_count,
        "model": str(device.get("model") or DEFAULT_PHONE_MODEL),
        "lastResult": str(device.get("lastResult") or ""),
        "updatedAt": str(device.get("updatedAt") or ""),
        "source": str(device.get("source") or "matrix-registry"),
        "configSource": str(device.get("configSource") or ""),
        "selected": bool(device.get("selected")),
        "platform": str(device.get("platform") or device.get("group") or "手机"),
        "account": str(device.get("account") or ""),
        "progress": _int(device.get("progress"), 10 if current_task_id else 0),
        "queue": _int(device.get("queue"), 0),
        "elapsedMs": _int(device.get("elapsedMs"), 0),
    }


def _steps_for_layer(layer: str) -> list[Json]:
    if layer == "direct":
        return [
            {"stepId": "step_direct", "kind": "direct", "label": "Direct 快路径", "status": "running", "timeoutSec": 8},
            {"stepId": "step_result", "kind": "result", "label": "收集结果", "status": "queued", "timeoutSec": 8},
        ]
    if layer == "template":
        return [
            {"stepId": "step_template", "kind": "template", "label": "Template 固化流程", "status": "running", "timeoutSec": 12},
            {"stepId": "step_result", "kind": "result", "label": "收集结果", "status": "queued", "timeoutSec": 12},
        ]
    return [
        {"stepId": "step_agent", "kind": "agent", "label": "Agent 推理执行", "status": "running", "timeoutSec": 20},
        {"stepId": "step_result", "kind": "result", "label": "收集结果", "status": "queued", "timeoutSec": 15},
    ]


def _execution_layer(*, mode: str, action: str, template: str, prompt: str) -> str:
    if mode == "observe" or action:
        return "direct"
    if template:
        return "template"
    if _template_from_prompt(prompt):
        return "template"
    return "agent"


def _direct_action(value: Any, prompt: str) -> str:
    text = re.sub(r"\s+", "", str(value or prompt or "").strip().lower())
    if text in {"back", "pressback", "返回", "返回上一页", "上一页", "后退"}:
        return "back"
    if text in {"home", "presshome", "回到桌面", "返回桌面", "桌面", "主页", "回主页"}:
        return "home"
    return ""


def _template_from_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", "", str(prompt or "").strip().lower())
    if any(token in text for token in {"打开系统设置", "打开设置", "系统设置", "opensettings"}):
        return "open-settings"
    if any(token in text for token in {"读取当前屏幕", "读屏", "screen-summary"}):
        return "read-screen"
    return ""


def _needs_confirmation(prompt: str) -> bool:
    return any(marker in str(prompt or "") for marker in OUTREACH_MARKERS)


def _parse_acquisition_import_rows(raw: Json) -> list[Json]:
    rows = raw.get("leads") or raw.get("rows") or raw.get("items")
    if isinstance(rows, list):
        return [_normalize_acquisition_row(item) for item in rows if isinstance(item, dict)][:200]
    summary = _safe_lead_summary(raw.get("leadSummary") or raw.get("summary"), limit=360)
    if summary:
        return [_normalize_acquisition_row({"summary": summary, "title": raw.get("title") or raw.get("topic")})]
    text = str(raw.get("sourceText") or raw.get("text") or "").strip()
    if not text:
        return []
    parsed = _try_parse_acquisition_json_rows(text)
    if parsed:
        return parsed[:200]
    csv_rows = _try_parse_acquisition_csv_rows(text)
    if csv_rows:
        return csv_rows[:200]
    return [
        _normalize_acquisition_row({"summary": line.strip(), "title": line.strip()[:40]})
        for line in text.splitlines()
        if line.strip()
    ][:200]


def _try_parse_acquisition_json_rows(text: str) -> list[Json]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        rows = data.get("comments") or data.get("leads") or data.get("items") or data.get("rows")
        if isinstance(rows, list):
            return [_normalize_acquisition_row(item) for item in rows if isinstance(item, dict)]
        return [_normalize_acquisition_row(data)]
    if isinstance(data, list):
        return [_normalize_acquisition_row(item) for item in data if isinstance(item, dict)]
    return []


def _try_parse_acquisition_csv_rows(text: str) -> list[Json]:
    sample = text.lstrip("\ufeff")
    try:
        reader = csv.DictReader(io.StringIO(sample))
        if reader.fieldnames and len(reader.fieldnames) > 1:
            rows = [_normalize_acquisition_row(dict(row)) for row in reader if any(str(value or "").strip() for value in row.values())]
            if rows:
                return rows
        plain_reader = csv.reader(io.StringIO(sample))
        return [
            _normalize_acquisition_row({"title": row[0] if row else "", "summary": " ".join(cell for cell in row if cell)})
            for row in plain_reader
            if row and any(cell.strip() for cell in row)
        ]
    except csv.Error:
        return []


def _normalize_acquisition_row(row: Json) -> Json:
    def pick(*keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    return {
        "platform": pick("platform", "平台", "来源平台", "sourcePlatform"),
        "channel": pick("channel", "渠道", "来源渠道"),
        "title": pick("title", "客户昵称/账号", "客户昵称", "昵称", "账号", "nickname", "account", "author"),
        "nickname": pick("nickname", "客户昵称/账号", "客户昵称", "昵称", "账号", "author"),
        "summary": pick("summary", "线索内容", "原始线索内容", "评论内容", "内容", "comment", "rawContent", "description"),
        "draftBody": pick("draftBody", "跟进话术草稿", "草稿", "draft", "reply", "body"),
        "profileUrl": pick("profileUrl", "主页链接", "主页或内容链接", "主页", "profile", "url"),
        "contentUrl": pick("contentUrl", "内容链接", "作品链接", "noteUrl"),
    }


def _qualify_acquisition_lead(summary: str, *, topic: Any = "", target: Any = "") -> Json:
    text = f"{summary} {topic or ''} {target or ''}".lower()
    high_tokens = ["报价", "价格", "预算", "合作", "预约", "方案", "案例", "获客", "加微信", "私域", "线索", "客户"]
    medium_tokens = ["了解", "咨询", "怎么", "如何", "需要", "想看", "有没有", "可以吗"]
    score = 30
    reasons: list[str] = []
    for token in high_tokens:
        if token.lower() in text:
            score += 15
            reasons.append(f"命中高意向词：{token}")
    for token in medium_tokens:
        if token.lower() in text:
            score += 8
            reasons.append(f"命中咨询词：{token}")
    score = max(0, min(score, 100))
    if score >= 70:
        level = "high"
        action = "优先人工确认跟进草稿，并记录行业、城市、预算和时间窗口。"
    elif score >= 50:
        level = "medium"
        action = "进入客户池，先用低压开场白确认场景和需求。"
    else:
        level = "low"
        action = "先保留为线索，等待更多互动信号后再跟进。"
    return {
        "score": score,
        "intentLevel": level,
        "need": _safe_lead_summary(summary, limit=220),
        "recommendedAction": action,
        "reasons": reasons[:6] or ["未命中强意向词，按普通线索保留"],
    }


def _build_acquisition_followup_draft(lead: Json, knowledge: str) -> str:
    title = _safe_lead_summary(lead.get("nickname") or lead.get("title") or "您好", limit=60)
    need = _safe_lead_summary(lead.get("need") or lead.get("summary") or "", limit=180)
    action = _safe_lead_summary(lead.get("recommendedAction") or "先确认需求，再人工跟进。", limit=140)
    return _safe_lead_summary(
        f"{title}，看到您提到“{need}”。我先不打扰您做决定，可以根据您的行业和城市整理一版试跑思路：{knowledge} 下一步建议：{action}",
        limit=500,
    )


def _acquisition_dedupe_key(platform: str, url: str, title: str, summary: str) -> str:
    source = "|".join([platform, url, title, summary[:160]]).lower()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]


def _safe_lead_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.match(r"^https?://", text, flags=re.I):
        return ""
    return _safe_lead_summary(text, limit=260)


def _acquisition_source(value: Any) -> str:
    text = str(value or "manual_import").strip().lower()
    if text in {"manual_import", "phone_agent", "demo_flow", "agent_result", "csv_import"}:
        return text
    return "manual_import"


def _acquisition_phone_task_payload(raw: Json, agent_run: Json) -> Json:
    device_id = _clip(agent_run.get("deviceId") or raw.get("deviceId") or raw.get("device") or "phone-1", 80) or "phone-1"
    platform = _acquisition_platform(agent_run.get("platform") or raw.get("platform"))
    topic = _clip(raw.get("topic") or f"{platform} 手机 Agent 获客任务", 120)
    action = _clip(agent_run.get("action") or raw.get("action") or "discover_leads", 80)
    target = _safe_lead_summary(raw.get("target") or raw.get("targetCustomer") or "", limit=180)
    knowledge = _safe_lead_summary(raw.get("knowledge") or "", limit=240)
    prompt = _safe_lead_summary(
        f"在{platform}执行{topic}。只读取可见公开内容，识别潜在线索，生成跟进草稿；如需触达，只能填草稿并停在人工确认页。目标客户：{target}。SOP：{knowledge}。返回 JSON 必须符合 loom.acquisition.agent_result.v1，字段包含 taskId、deviceId、platform、action、status、leads、drafts、logs；禁止自动私信、评论、加好友、加微信或发布。",
        limit=900,
    )
    payload = {
        "schema": "loom.acquisition.phone_task.v1",
        "taskId": agent_run.get("taskId"),
        "platform": platform,
        "action": action,
        "topic": topic,
        "mode": "safe",
        "profile": "fast",
        "target": {"deviceIds": [device_id]},
        "resultSchema": "loom.acquisition.agent_result.v1",
        "stopAt": "human_confirmation",
        "requiresHumanReview": True,
        "sendEnabled": False,
        "allowedActions": ["open_app", "read_public_content", "summarize_leads", "fill_draft", "capture_screenshot"],
        "forbiddenActions": ["send_dm", "post_comment", "add_friend", "add_wechat", "bulk_outreach", "publish_without_confirmation"],
        "outboundPolicy": _acquisition_policy(),
        "prompt": prompt,
    }
    payload["bridgeDispatch"] = _acquisition_phone_bridge_dispatch(payload, device_id)
    return payload


def _acquisition_phone_bridge_dispatch(phone_task: Json, device_id: str) -> Json:
    return {
        "method": "POST",
        "endpoint": "/api/phone/task",
        "body": {
            "taskId": phone_task.get("taskId") or "",
            "prompt": phone_task.get("prompt") or "",
            "mode": "safe",
            "profile": phone_task.get("profile") or "fast",
            "executionLayer": "agent",
            "target": {"deviceIds": [device_id]},
            "template": "",
            "requiresHumanReview": True,
            "sendEnabled": False,
            "resultSchema": "loom.acquisition.agent_result.v1",
            "outboundPolicy": _acquisition_policy(),
            "resultCallback": {
                "method": "POST",
                "endpoint": "/api/matrix/acquisition/agent/result",
                "payloadField": "agentResult",
            },
        },
    }

def _mode(value: Any) -> str:
    text = str(value or "safe").strip().lower()
    if text in {"observe", "safe", "full"}:
        return text
    return "safe"


def _profile(value: Any) -> str:
    text = str(value or "fast").strip().lower()
    if text in {"fast", "standard", "deep"}:
        return text
    return "fast"


def _template(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_.-]+", "-", text).strip(".-_")[:80]


def _retry_body_snapshot(*, prompt: str, mode: str, profile: str, template: str, action: str, devices: list[Json]) -> Json:
    return {
        "promptPreview": _safe_lead_summary(prompt, limit=240),
        "promptHash": _hash_prompt(prompt),
        "mode": mode,
        "profile": profile,
        "template": template,
        "directAction": action,
        "target": {"deviceIds": [str(device.get("deviceId") or "") for device in devices if str(device.get("deviceId") or "")][:100]},
    }


def _lead_source(value: Any) -> str:
    text = str(value or "manual").strip().lower()
    if text in {"manual", "task", "template", "agent", "import"}:
        return text
    return "manual"


def _lead_status(value: Any) -> str:
    text = str(value or "new").strip().lower()
    if text in {"new", "qualified", "follow-up", "ignored", "closed"}:
        return text
    return "new"


def _acquisition_platform(value: Any) -> str:
    text = str(value or "douyin").strip().lower()
    aliases = {
        "抖音": "douyin",
        "小红书": "xiaohongshu",
        "微信": "wechat",
        "视频号": "wechat",
        "快手": "kuaishou",
        "海外小红书": "rednote",
        "小红书海外版": "rednote",
        "red note": "rednote",
        "海外版小红书": "rednote",
    }
    text = aliases.get(text, text)
    if text in {"douyin", "xiaohongshu", "wechat", "bilibili", "kuaishou", "tiktok", "rednote", "lemon8", "manual"}:
        return text
    return "manual"


def _acquisition_channel(value: Any) -> str:
    text = str(value or "comment").strip().lower()
    aliases = {
        "评论": "comment",
        "评论区": "comment",
        "私信": "dm",
        "微信": "wechat",
        "电话": "phone",
        "手动": "manual",
    }
    text = aliases.get(text, text)
    if text in {"comment", "dm", "wechat", "phone", "manual"}:
        return text
    return "manual"


def _manual_send_outcome(value: Any) -> str:
    text = str(value or "sent").strip().lower()
    if text in {"sent", "replied", "no_reply", "failed"}:
        return text
    aliases = {
        "已发送": "sent",
        "已回复": "replied",
        "无回复": "no_reply",
        "失败": "failed",
    }
    return aliases.get(text, "sent")


def _acquisition_policy() -> list[str]:
    return ["draft_only", "manual_confirm", "whitelist", "frequency_cap", "audit_log"]


def _agent_result_has_unsafe_outbound(agent_result: Json) -> bool:
    forbidden = {"send_dm", "post_comment", "add_friend", "add_wechat", "bulk_outreach", "publish_without_confirmation"}
    if _truthy(agent_result.get("sendEnabled")):
        return True
    if str(agent_result.get("status") or "").strip().lower() in {"ready_to_send", "sent", "published", "auto_sent"}:
        return True
    actions = agent_result.get("requestedActions")
    if isinstance(actions, list):
        for item in actions:
            if str(item or "").strip().lower() in forbidden:
                return True
    drafts = agent_result.get("drafts")
    if isinstance(drafts, list):
        for item in drafts:
            if not isinstance(item, dict):
                continue
            if _truthy(item.get("sendEnabled")):
                return True
            if item.get("requiresHumanReview") is False:
                return True
    return False


def _default_acquisition_sop() -> list[Json]:
    return [
        {
            "id": "qualify",
            "title": "识别意图",
            "text": "先确认客户场景、预算和时间窗口，不承诺效果。",
        },
        {
            "id": "reply",
            "title": "回复草稿",
            "text": "所有评论、私信和微信跟进先生成草稿，人工确认后再处理。",
        },
        {
            "id": "risk",
            "title": "频控留痕",
            "text": "真实触达必须走白名单、频控和日志留痕。",
        },
    ]


def _acquisition_log(event_type: str, message: str, timestamp: str | None = None) -> Json:
    return {
        "logId": f"log_{uuid.uuid4().hex[:12]}",
        "timestamp": timestamp or _now_iso(),
        "type": event_type,
        "message": _safe_lead_summary(message, limit=260),
    }


def _safe_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "").strip())[:40]
        if text:
            tags.append(text)
    return tags[:20]


def _safe_lead_summary(value: Any, *, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"sk-[A-Za-z0-9_\-]{4,}", "sk-***", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", text, flags=re.I)
    text = re.sub(r"\b1[3-9]\d{9}\b", "[手机号已隐藏]", text)
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", text)
    return text[:limit]


def _device_id(value: Any) -> str:
    text = str(value or "phone-1").strip()
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", text).strip(".-_")
    return text[:80] or "phone-1"


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest()[:16]


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        safe: Json = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if str(key) in SENSITIVE_KEYS or any(mark in lowered for mark in ("token", "secret", "password", "apikey", "api_key")):
                continue
            safe[key] = _redact_json(item)
        return safe
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"sk-[A-Za-z0-9_\-]{4,}", "sk-***", value)
        value = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", value, flags=re.I)
        return value
    return value


def _clip(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_bool(value: Any, fallback: Any = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(fallback, bool):
        return fallback
    return None


def _timestamp_age_ms(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return -1
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if re.search(r"[+-]\d{4}$", text):
        text = f"{text[:-5]}{text[-5:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return -1
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0, int((now - parsed.astimezone(timezone.utc)).total_seconds() * 1000))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "confirmed"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
