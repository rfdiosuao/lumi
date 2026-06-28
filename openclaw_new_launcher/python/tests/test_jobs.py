from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from services.jobs import JobManager


def wait_for_terminal(manager: JobManager, job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = manager.get(job_id)
        if job and job.get("status") in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job_id}")


class JobManagerStateTests(unittest.TestCase):
    def test_finished_capability_job_remains_available_for_page_switch(self) -> None:
        logs: list[str] = []
        manager = JobManager(logs.append)

        def target(job_id: str) -> dict:
            manager.progress(job_id, "正在执行能力命令", "neutral", commandId="phone:agent")
            return {
                "success": True,
                "commandId": "phone:agent",
                "stdout": "{\"ok\":true}",
            }

        submitted = manager.submit_progress("cli", "手机 Agent", target)
        finished = wait_for_terminal(manager, submitted["id"])

        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["kind"], "cli")
        self.assertEqual(finished["result"]["commandId"], "phone:agent")
        self.assertEqual(finished["progress"]["commandId"], "phone:agent")
        self.assertEqual(finished["progress"]["history"][-1]["message"], "正在执行能力命令")

        listed = manager.list(10)
        listed_job = next(job for job in listed if job["id"] == submitted["id"])
        self.assertEqual(listed_job["status"], "succeeded")
        self.assertEqual(listed_job["result"]["stdout"], "{\"ok\":true}")

    def test_failed_media_job_keeps_public_error_for_recent_tasks(self) -> None:
        logs: list[str] = []
        manager = JobManager(logs.append)

        def target(job_id: str) -> dict:
            manager.progress(job_id, "正在生成视频", "neutral")
            return {
                "success": False,
                "error": "视频服务密钥不能为空",
            }

        submitted = manager.submit_progress("video", "视频生成", target)
        finished = wait_for_terminal(manager, submitted["id"])

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["kind"], "video")
        self.assertEqual(finished["error"], "视频服务密钥不能为空")
        self.assertEqual(finished["progress"]["history"][-1]["message"], "正在生成视频")
        self.assertTrue(finished["failure"]["label"])


    def test_job_snapshot_exposes_xinflo_style_type_and_phase_without_losing_progress_history(self) -> None:
        logs: list[str] = []
        manager = JobManager(logs.append)

        def target(job_id: str) -> dict:
            manager.progress(job_id, "下载 Codex", "neutral", phase="downloading", percent=25)
            return {"success": True}

        submitted = manager.submit_progress("component.install", "Install Codex", target)

        self.assertEqual(submitted["type"], "component.install")
        self.assertEqual(submitted["phase"], "queued")

        finished = wait_for_terminal(manager, submitted["id"])

        self.assertEqual(finished["type"], "component.install")
        self.assertEqual(finished["phase"], "downloading")
        self.assertEqual(finished["progress"]["phase"], "downloading")
        self.assertEqual(finished["progress"]["percent"], 25)
        self.assertEqual(finished["progress"]["history"][-1]["message"], "下载 Codex")

    def test_finished_component_job_persists_for_bridge_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "jobs-state.json")
            logs: list[str] = []
            manager = JobManager(logs.append, state_path=state_path)

            def target(job_id: str) -> dict:
                manager.progress(job_id, "校验 Codex", "neutral", phase="verifying", componentId="codex-desktop")
                return {"success": True, "state": {"status": "ready"}}

            submitted = manager.submit_progress("component.install", "Install Codex", target)
            finished = wait_for_terminal(manager, submitted["id"])

            self.assertEqual(finished["status"], "succeeded")

            restarted = JobManager(logs.append, state_path=state_path)
            restored = restarted.get(submitted["id"])
            listed = restarted.list(10)

            self.assertIsNotNone(restored)
            self.assertEqual(restored["status"], "succeeded")
            self.assertEqual(restored["result"]["state"]["status"], "ready")
            self.assertEqual(restored["progress"]["componentId"], "codex-desktop")
            self.assertEqual(restored["progress"]["history"][-1]["message"], "校验 Codex")
            self.assertIn(submitted["id"], [job["id"] for job in listed])

    def test_running_job_snapshot_is_marked_interrupted_after_bridge_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "jobs-state.json")
            logs: list[str] = []
            manager = JobManager(logs.append, state_path=state_path)
            event = []

            def target(job_id: str) -> dict:
                manager.progress(job_id, "下载 Hermes", "neutral", phase="downloading", componentId="hermes")
                event.append(job_id)
                time.sleep(0.3)
                return {"success": True}

            submitted = manager.submit_progress("component.install", "Install Hermes", target)
            deadline = time.time() + 1
            while not event and time.time() < deadline:
                time.sleep(0.02)

            restarted = JobManager(logs.append, state_path=state_path)
            restored = restarted.get(submitted["id"])

            self.assertIsNotNone(restored)
            self.assertEqual(restored["status"], "failed")
            self.assertEqual(restored["phase"], "interrupted")
            self.assertIn("已中断", restored["error"])
            self.assertTrue(restored["failure"]["retryable"])
            self.assertEqual(restored["progress"]["componentId"], "hermes")


if __name__ == "__main__":
    unittest.main()
