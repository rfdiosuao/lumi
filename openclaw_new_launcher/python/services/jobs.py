"""Persistent job runner for long launcher tasks."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import traceback
import uuid
from collections.abc import Callable

from core.reliability import classify_failure


class JobManager:
    def __init__(self, append_log: Callable[[str], None], max_jobs: int = 100, state_path: str | None = None):
        self.append_log = append_log
        self.max_jobs = max_jobs
        self.state_path = state_path
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._load_persisted_jobs()

    def submit(self, kind: str, label: str, target: Callable[[], dict]) -> dict:
        return self.submit_progress(kind, label, lambda _job_id: target())

    def submit_progress(self, kind: str, label: str, target: Callable[[str], dict], initial_progress: dict | None = None) -> dict:
        job_id = f"job_{uuid.uuid4().hex}"
        now = time.time()
        initial_progress = dict(initial_progress or {})
        initial_message = str(initial_progress.pop("message", "queued") or "queued")
        initial_tone = str(initial_progress.pop("tone", "neutral") or "neutral")
        initial_phase = str(initial_progress.get("phase") or "queued")
        initial_entry = {"message": initial_message, "tone": initial_tone, "updatedAt": now}
        job = {
            "id": job_id,
            "kind": kind,
            "type": kind,
            "label": label,
            "status": "queued",
            "phase": initial_phase,
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "finishedAt": None,
            "result": None,
            "error": None,
            "failure": None,
            "attempt": 1,
            "message": initial_message,
            "progress": {
                **initial_progress,
                **initial_entry,
                "history": [initial_entry] if initial_progress else [],
                "updatedAt": now,
            },
        }
        with self._lock:
            self._jobs[job_id] = job
            self._prune_locked()
            self._persist_locked()

        queued_snapshot = dict(job)
        thread = threading.Thread(target=self._run, args=(job_id, target), daemon=True)
        thread.start()
        return queued_snapshot

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self, limit: int = 30) -> list[dict]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: float(item.get("createdAt") or 0), reverse=True)
            return [dict(item) for item in jobs[: max(1, min(limit, self.max_jobs))]]

    def progress(self, job_id: str, message: str, tone: str = "neutral", **extra) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            current = job.get("progress") if isinstance(job.get("progress"), dict) else {}
            history = current.get("history") if isinstance(current.get("history"), list) else []
            entry = {"message": str(message or ""), "tone": str(tone or "neutral"), "updatedAt": now}
            history = [*history, entry][-30:]
            job["message"] = entry["message"]
            if "phase" in extra:
                job["phase"] = str(extra.get("phase") or "")
            job["progress"] = {
                **current,
                **extra,
                **entry,
                "history": history,
            }
            job["updatedAt"] = now
            self._persist_locked()

    def _run(self, job_id: str, target: Callable[[str], dict]) -> None:
        self._patch(job_id, status="running", phase="running", startedAt=time.time(), updatedAt=time.time(), message="running")
        self.append_log(f"[Job] {job_id} started\n")
        try:
            result = target(job_id)
            if isinstance(result, dict) and result.get("success") is False:
                failure = _public_failure(classify_failure(result))
                error_text = str(result.get("error") or result.get("message") or failure.get("evidence") or "job_result_failed")
                self._patch(
                    job_id,
                    status="failed",
                    result=result,
                    error=error_text,
                    failure=failure,
                    finishedAt=time.time(),
                    updatedAt=time.time(),
                )
                self.append_log(f"[Job] {job_id} failed: {error_text}\n")
                return
            self._patch(
                job_id,
                status="succeeded",
                result=result,
                error=None,
                failure=None,
                finishedAt=time.time(),
                updatedAt=time.time(),
            )
            self.append_log(f"[Job] {job_id} succeeded\n")
        except Exception as error:
            technical = f"{type(error).__name__}: {error}"
            self.append_log(f"[Job] {job_id} failed: {technical}\n{traceback.format_exc()}\n")
            self._patch(
                job_id,
                status="failed",
                result=None,
                error="任务执行失败，详情已写入运行日志",
                failure=_public_failure(classify_failure({"error": technical})),
                traceback=None,
                finishedAt=time.time(),
                updatedAt=time.time(),
            )

    def _patch(self, job_id: str, **updates) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(updates)
            self._persist_locked()

    def _prune_locked(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        jobs = sorted(self._jobs.values(), key=lambda item: float(item.get("createdAt") or 0))
        for job in jobs[: len(self._jobs) - self.max_jobs]:
            self._jobs.pop(str(job.get("id")), None)

    def _load_persisted_jobs(self) -> None:
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if isinstance(raw_jobs, dict):
            jobs = [item for item in raw_jobs.values() if isinstance(item, dict)]
        elif isinstance(raw_jobs, list):
            jobs = [item for item in raw_jobs if isinstance(item, dict)]
        else:
            return

        now = time.time()
        changed = False
        with self._lock:
            for raw_job in jobs:
                job_id = str(raw_job.get("id") or "").strip()
                if not job_id:
                    continue
                job = dict(raw_job)
                status = str(job.get("status") or "")
                if status in {"queued", "running"}:
                    progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
                    history = progress.get("history") if isinstance(progress.get("history"), list) else []
                    entry = {
                        "message": "任务已中断，请重试",
                        "tone": "warning",
                        "updatedAt": now,
                    }
                    job.update({
                        "status": "failed",
                        "phase": "interrupted",
                        "message": entry["message"],
                        "error": entry["message"],
                        "finishedAt": now,
                        "updatedAt": now,
                        "failure": {
                            "class": "interrupted",
                            "label": "任务已中断",
                            "retryable": True,
                            "severity": "warn",
                            "suggestion": "请重新执行该操作",
                        },
                        "progress": {
                            **progress,
                            **entry,
                            "phase": "interrupted",
                            "history": [*history, entry][-30:],
                        },
                    })
                    changed = True
                self._jobs[job_id] = job
            self._prune_locked()
            if changed:
                self._persist_locked()

    def _persist_locked(self) -> None:
        if not self.state_path:
            return
        payload = {
            "schemaVersion": 1,
            "updatedAt": time.time(),
            "jobs": {job_id: job for job_id, job in sorted(self._jobs.items())},
        }
        directory = os.path.dirname(self.state_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".jobs-state-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
                handle.write("\n")
            try:
                os.replace(temp_path, self.state_path)
            except PermissionError:
                with open(self.state_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
                    handle.write("\n")
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


def _public_failure(failure: dict) -> dict:
    return {
        "class": failure.get("class") or "",
        "label": failure.get("label") or "",
        "retryable": bool(failure.get("retryable")),
        "severity": failure.get("severity") or "warn",
        "suggestion": failure.get("suggestion") or "",
    }
