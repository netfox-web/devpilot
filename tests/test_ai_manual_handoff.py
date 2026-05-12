import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class AiManualHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.testing = True
        with cls.app.app_context():
            owner = app_module.query_one("SELECT id FROM users WHERE role IN ('owner', 'admin') AND is_active=1 ORDER BY id LIMIT 1")
        cls.user_id = owner["id"]

    def setUp(self):
        self.marker = "ai_manual_handoff_test"
        self.key_store_dir = tempfile.TemporaryDirectory()
        self.key_store_path = Path(self.key_store_dir.name) / "external_api_keys.json"
        self.policy_store_path = Path(self.key_store_dir.name) / "external_ai_policies.json"
        self.key_store_patch = patch.object(self.app_module, "EXTERNAL_API_KEY_STORE_PATH", self.key_store_path)
        self.policy_store_patch = patch.object(self.app_module, "EXTERNAL_AI_POLICY_STORE_PATH", self.policy_store_path)
        self.key_store_env_patch = patch.dict(
            self.app_module.os.environ,
            {
                "DEVPILOT_EXTERNAL_API_KEY_STORE_PATH": str(self.key_store_path),
                "DEVPILOT_EXTERNAL_AI_POLICY_STORE_PATH": str(self.policy_store_path),
            },
            clear=False,
        )
        self.key_store_patch.start()
        self.policy_store_patch.start()
        self.key_store_env_patch.start()
        with self.app.app_context():
            now = self.app_module.now_str()
            self.project_id = self.app_module.execute(
                """INSERT INTO projects
                   (name, client_name, project_type, status, priority, description, next_steps, progress, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"AI Manual Handoff Test Project {self.marker}",
                    "test",
                    "ai",
                    "active",
                    "medium",
                    self.marker,
                    "original project next step",
                    7,
                    now,
                    now,
                ),
            ).lastrowid
            self.phase_id = self.app_module.execute(
                """INSERT INTO project_phases
                   (project_id, phase_name, phase_order, status, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.project_id, f"AI Manual Handoff Phase {self.marker}", 1, "phase-original", self.marker, now, now),
            ).lastrowid
            self.task = self.app_module.create_ai_task({
                "project_id": self.project_id,
                "title": f"AI Manual Handoff Test Task {self.marker}",
                "prompt": "Keep this task side-effect free.",
                "provider": "openai",
                "task_type": "handoff",
                "priority": "medium",
            })

    def tearDown(self):
        with self.app.app_context():
            self.app_module.execute("DELETE FROM handoff_logs WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM tasks WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM project_phases WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM projects WHERE id=?", (self.project_id,))
        self.key_store_env_patch.stop()
        self.policy_store_patch.stop()
        self.key_store_patch.stop()
        self.key_store_dir.cleanup()

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def external_api_env(self, allow_all_sources=False):
        return {
            "DEVPILOT_EXTERNAL_API_KEYS": "external-a:key-a,external-b:key-b",
            "DEVPILOT_EXTERNAL_API_ALLOW_ALL_SOURCES": "1" if allow_all_sources else "0",
        }

    def external_headers(self, source="external-a", key="key-a", request_id="req-a", idempotency_key="idem-a"):
        headers = {
            "X-DevPilot-Source-System": source,
            "X-DevPilot-Api-Key": key,
            "X-DevPilot-Request-Id": request_id,
        }
        if idempotency_key:
            headers["X-DevPilot-Idempotency-Key"] = idempotency_key
        return headers

    def handoff_payload(self, risk_level="low", **overrides):
        payload = {
            "from_agent": "planner-ai",
            "to_agent": "executor-ai",
            "reason": f"Manual handoff fixture {self.marker}",
            "next_step": "Review the handoff and respond manually.",
            "risk_level": risk_level,
        }
        payload.update(overrides)
        return payload

    def create_handoff(self, risk_level="low", **overrides):
        response = self.client().post(f"/api/tasks/{self.task['id']}/handoff", json=self.handoff_payload(risk_level, **overrides))
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["handoff"]

    def state_snapshot(self):
        with self.app.app_context():
            project = self.app_module.row_to_dict(self.app_module.query_one("SELECT * FROM projects WHERE id=?", (self.project_id,)))
            phase = self.app_module.row_to_dict(self.app_module.query_one("SELECT * FROM project_phases WHERE id=?", (self.phase_id,)))
            task = self.app_module.task_row(self.task["id"])
        return {
            "project_status": project["status"],
            "project_next_steps": project["next_steps"],
            "project_progress": project["progress"],
            "phase_status": phase["status"],
            "task_status": task["status"],
            "task_updated_at": task["updated_at"],
        }

    def test_ai_handoffs_page_returns_200(self):
        response = self.client().get("/ai-handoffs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI Handoffs", response.get_data(as_text=True))

    def test_create_handoff_is_side_effect_free(self):
        before = self.state_snapshot()
        with patch.object(self.app_module, "save_handoff") as legacy_save:
            response = self.client().post(f"/api/tasks/{self.task['id']}/handoff", json=self.handoff_payload())
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        legacy_save.assert_not_called()
        payload = response.get_json()
        handoff = payload["handoff"]
        self.assertEqual(handoff["task_id"], self.task["id"])
        self.assertEqual(handoff["from_agent"], "planner-ai")
        self.assertEqual(handoff["to_agent"], "executor-ai")
        self.assertEqual(handoff["handoff_status"], "pending")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(self.state_snapshot(), before)

    def test_handoff_appears_in_task_timeline(self):
        created = self.create_handoff()
        response = self.client().get(f"/api/tasks/{self.task['id']}/timeline")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(any(item.get("id") == created["id"] and item.get("handoff_status") == "pending" for item in payload["handoffs"]))
        self.assertTrue(any(item.get("type") == "handoff" and "pending" in item.get("title", "") for item in payload["timeline"]))

    def test_task_handoff_page_returns_200(self):
        response = self.client().get(f"/tasks/{self.task['id']}/handoff")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Manual AI Handoff", response.get_data(as_text=True))

    def test_accept_complete_reject_handoff(self):
        completed = self.create_handoff()
        response = self.client().post(f"/api/handoffs/{completed['id']}/accept", json={})
        self.assertEqual(response.status_code, 200)
        handoff = response.get_json()["handoff"]
        self.assertEqual(handoff["handoff_status"], "accepted")
        self.assertTrue(handoff["accepted_at"])

        response = self.client().post(f"/api/handoffs/{completed['id']}/complete", json={})
        self.assertEqual(response.status_code, 200)
        handoff = response.get_json()["handoff"]
        self.assertEqual(handoff["handoff_status"], "completed")
        self.assertTrue(handoff["completed_at"])

        rejected = self.create_handoff()
        response = self.client().post(f"/api/handoffs/{rejected['id']}/reject", json={"reason": "Not the right agent."})
        self.assertEqual(response.status_code, 200)
        handoff = response.get_json()["handoff"]
        self.assertEqual(handoff["handoff_status"], "rejected")
        self.assertTrue(handoff["rejected_at"])

    def test_handoff_lifecycle_blocks_invalid_transitions_and_requires_reject_reason(self):
        before = self.state_snapshot()
        pending = self.create_handoff()

        response = self.client().post(f"/api/handoffs/{pending['id']}/complete", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid handoff transition", response.get_json()["error"])

        response = self.client().post(f"/api/handoffs/{pending['id']}/reject", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("reject reason is required", response.get_json()["error"])

        response = self.client().post(f"/api/handoffs/{pending['id']}/accept", json={})
        self.assertEqual(response.status_code, 200)

        response = self.client().post(f"/api/handoffs/{pending['id']}/accept", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid handoff transition", response.get_json()["error"])

        response = self.client().post(f"/api/handoffs/{pending['id']}/complete", json={})
        self.assertEqual(response.status_code, 200)

        for action in ("accept", "complete", "reject"):
            body = {"reason": "Already completed."} if action == "reject" else {}
            response = self.client().post(f"/api/handoffs/{pending['id']}/{action}", json=body)
            self.assertEqual(response.status_code, 400)
            self.assertIn("invalid handoff transition", response.get_json()["error"])

        rejected = self.create_handoff()
        response = self.client().post(f"/api/handoffs/{rejected['id']}/reject", json={"reason": "Not needed."})
        self.assertEqual(response.status_code, 200)
        for action in ("accept", "complete", "reject"):
            body = {"reason": "Already rejected."} if action == "reject" else {}
            response = self.client().post(f"/api/handoffs/{rejected['id']}/{action}", json=body)
            self.assertEqual(response.status_code, 400)
            self.assertIn("invalid handoff transition", response.get_json()["error"])

        self.assertEqual(self.state_snapshot(), before)

    def test_high_risk_handoff_has_no_external_or_approval_side_effects(self):
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        before = self.state_snapshot()
        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                    with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                        with patch.object(self.app_module, "save_handoff") as legacy_save:
                            response = self.client().post(f"/api/tasks/{self.task['id']}/handoff", json=self.handoff_payload("high"))
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        handoff = response.get_json()["handoff"]
        self.assertEqual(handoff["risk_level"], "high")
        self.assertTrue(handoff["approval_required"])
        self.assertTrue(handoff["pending_approval"])
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_ai_handoffs_api_lists_created_handoff(self):
        created = self.create_handoff()
        response = self.client().get(f"/api/ai-handoffs?task_id={self.task['id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["execution_allowed"])
        self.assertTrue(any(item.get("id") == created["id"] for item in payload["items"]))

    def test_ai_handoffs_filters_and_search(self):
        match = self.create_handoff(
            from_agent="planner-search",
            to_agent="executor-search",
            reason="Need focused verification for searchable handoff",
            next_step="Searchable follow-up step",
            risk_level="medium",
        )
        other = self.create_handoff(
            from_agent="other-planner",
            to_agent="other-executor",
            reason="Different handoff fixture",
            next_step="Different next step",
            risk_level="low",
        )
        self.client().post(f"/api/handoffs/{match['id']}/accept", json={})

        response = self.client().get("/api/ai-handoffs?q=searchable")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?status=accepted")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?risk=medium")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?risk_level=medium")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?risk=low&risk_level=medium")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?q=searchable&status=accepted&risk_level=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        ids = {item["id"] for item in payload["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs?q=searchable&status=accepted&risk=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        ids = {item["id"] for item in payload["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/ai-handoffs?risk=medium")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Searchable follow-up step", body)
        self.assertNotIn("Different next step", body)
        self.assertIn('value="medium" selected', body)

        response = self.client().get("/ai-handoffs?q=searchable&status=accepted&risk=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Searchable follow-up step", body)
        self.assertNotIn("Different next step", body)
        self.assertIn("planner-search", body)

        response = self.client().get("/ai-handoffs?q=searchable&status=accepted&risk_level=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Searchable follow-up step", body)
        self.assertIn("planner-search", body)
        self.assertIn('name="q"', body)
        self.assertIn('name="from_agent"', body)
        self.assertIn('name="to_agent"', body)
        self.assertIn('value="medium" selected', body)

    def test_ai_handoffs_review_queue_counts_and_active_filters(self):
        pending = self.create_handoff(
            from_agent="queue-planner",
            to_agent="queue-reviewer",
            reason="Review queue counts marker",
            next_step="Pending queue item",
            risk_level="medium",
        )
        accepted = self.create_handoff(
            from_agent="queue-planner",
            to_agent="queue-reviewer",
            reason="Review queue counts marker",
            next_step="Accepted queue item",
            risk_level="medium",
        )
        completed = self.create_handoff(
            from_agent="queue-planner",
            to_agent="queue-reviewer",
            reason="Review queue counts marker",
            next_step="Completed queue item",
            risk_level="medium",
        )
        rejected = self.create_handoff(
            from_agent="queue-planner",
            to_agent="queue-reviewer",
            reason="Review queue counts marker",
            next_step="Rejected queue item",
            risk_level="medium",
        )
        self.client().post(f"/api/handoffs/{accepted['id']}/accept", json={})
        self.client().post(f"/api/handoffs/{completed['id']}/accept", json={})
        self.client().post(f"/api/handoffs/{completed['id']}/complete", json={})
        self.client().post(f"/api/handoffs/{rejected['id']}/reject", json={"reason": "Queue rejected"})

        response = self.client().get(
            "/ai-handoffs?q=Review+queue+counts&from_agent=queue-planner&to_agent=queue-reviewer&risk=medium"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("pending: 1", body)
        self.assertIn("accepted: 1", body)
        self.assertIn("completed: 1", body)
        self.assertIn("rejected: 1", body)
        self.assertIn("Active filters", body)
        self.assertIn("search: Review queue counts", body)
        self.assertIn("from: queue-planner", body)
        self.assertIn("to: queue-reviewer", body)
        self.assertIn("risk: medium", body)
        self.assertIn("Clear filters", body)
        self.assertIn(f"Details for handoff #{pending['id']}", body)

    def test_ai_handoff_detail_endpoint_and_board_detail_are_read_only(self):
        before = self.state_snapshot()
        created = self.create_handoff(
            from_agent="detail-planner",
            to_agent="detail-reviewer",
            reason="Detailed handoff reason",
            next_step="Detailed handoff next step",
            risk_level="medium",
        )
        response = self.client().post(f"/api/handoffs/{created['id']}/reject", json={"reason": "Detailed rejection reason"})
        self.assertEqual(response.status_code, 200)

        response = self.client().get(f"/api/handoffs/{created['id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["read_only"] is False)
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["api_payload_parse_error"])
        handoff = payload["handoff"]
        self.assertEqual(handoff["id"], created["id"])
        self.assertEqual(handoff["task_id"], self.task["id"])
        self.assertEqual(handoff["task_title"], self.task["title"])
        self.assertEqual(handoff["project_id"], self.project_id)
        self.assertEqual(handoff["from_agent"], "detail-planner")
        self.assertEqual(handoff["to_agent"], "detail-reviewer")
        self.assertEqual(handoff["handoff_status"], "rejected")
        self.assertEqual(handoff["rejection_reason"], "Detailed rejection reason")
        self.assertEqual(payload["api_payload"]["reason"], "Detailed handoff reason")
        self.assertEqual(payload["api_payload"]["next_step"], "Detailed handoff next step")
        self.assertTrue(payload["api_payload"]["rejected_at"])

        response = self.client().get("/ai-handoffs?q=Detailed")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn(f"Details for handoff #{created['id']}", body)
        self.assertIn("Conversation ref", body)
        self.assertIn(f"ai-task:{self.task['id']}", body)
        self.assertIn("API payload summary", body)
        self.assertIn("Detailed rejection reason", body)

        response = self.client().get(f"/api/tasks/{self.task['id']}/timeline")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Reject reason: Detailed rejection reason", response.get_data(as_text=True))
        self.assertEqual(self.state_snapshot(), before)

    def test_ai_handoff_detail_handles_invalid_or_missing_api_payload(self):
        with self.app.app_context():
            now = self.app_module.now_str()
            invalid_id = self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "legacy-invalid",
                    "legacy-invalid",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "low",
                    "Invalid payload fallback reason",
                    "Invalid payload fallback next step",
                    "",
                    "{not-json",
                    now,
                ),
            ).lastrowid
            missing_id = self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "legacy-missing",
                    "legacy-missing",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "low",
                    "Missing payload fallback reason",
                    "Missing payload fallback next step",
                    "",
                    "",
                    now,
                ),
            ).lastrowid

        response = self.client().get(f"/api/handoffs/{invalid_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["api_payload_parse_error"])
        self.assertEqual(payload["handoff"]["task_id"], self.task["id"])
        self.assertEqual(payload["handoff"]["handoff_status"], "pending")
        self.assertEqual(payload["handoff"]["reason"], "Invalid payload fallback reason")

        response = self.client().get(f"/api/handoffs/{missing_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["api_payload_parse_error"])
        self.assertEqual(payload["handoff"]["task_id"], self.task["id"])
        self.assertEqual(payload["handoff"]["handoff_status"], "pending")
        self.assertEqual(payload["handoff"]["reason"], "Missing payload fallback reason")

    def test_ai_handoffs_export_is_filtered_safe_and_read_only(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        match = self.create_handoff(
            from_agent="export-planner",
            to_agent="export-reviewer",
            reason="Export searchable handoff",
            next_step="Export next step",
            risk_level="medium",
        )
        other = self.create_handoff(
            from_agent="other-export-planner",
            to_agent="other-export-reviewer",
            reason="Other export handoff",
            next_step="Other export next step",
            risk_level="low",
        )
        with self.app.app_context():
            invalid_id = self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "export-invalid",
                    "export-invalid",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "low",
                    "Export invalid payload fallback",
                    "Export invalid payload next step",
                    "",
                    "{not-json",
                    self.app_module.now_str(),
                ),
            ).lastrowid

        response = self.client().get("/api/ai-handoffs/export?q=Export+searchable&risk=medium")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_allowed"])
        ids = {item["handoff_id"] for item in payload["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)
        item = next(item for item in payload["items"] if item["handoff_id"] == match["id"])
        self.assertEqual(item["task_id"], self.task["id"])
        self.assertEqual(item["task_title"], self.task["title"])
        self.assertEqual(item["project_id"], self.project_id)
        self.assertEqual(item["project_name"], f"AI Manual Handoff Test Project {self.marker}")
        self.assertEqual(item["project_status"], "active")
        self.assertEqual(item["from_agent"], "export-planner")
        self.assertEqual(item["to_agent"], "export-reviewer")
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["risk"], "medium")
        self.assertEqual(item["reason"], "Export searchable handoff")
        self.assertEqual(item["next_step"], "Export next step")
        self.assertEqual(item["conversation_ref"], f"ai-task:{self.task['id']}")
        self.assertTrue(item["created_at"])
        self.assertIn("api_payload_summary", item)
        self.assertNotIn("api_payload", item)
        self.assertEqual(item["api_payload_summary"]["reason"], "Export searchable handoff")

        response = self.client().get("/api/ai-handoffs/export?q=Export+searchable&risk_level=medium")
        self.assertEqual(response.status_code, 200)
        ids = {item["handoff_id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs/export?q=Export+searchable&risk=low&risk_level=medium")
        self.assertEqual(response.status_code, 200)
        ids = {item["handoff_id"] for item in response.get_json()["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/api/ai-handoffs/export?q=Export+invalid+payload")
        self.assertEqual(response.status_code, 200)
        item = next(item for item in response.get_json()["items"] if item["handoff_id"] == invalid_id)
        self.assertTrue(item["api_payload_parse_error"])
        self.assertEqual(item["api_payload_summary"], {})

        response = self.client().get("/api/ai-handoffs/export?q=Export+searchable&risk=medium&format=csv")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        row = next(row for row in rows if row["handoff_id"] == str(match["id"]))
        self.assertEqual(row["risk"], "medium")
        self.assertIn("api_payload_summary", row)
        self.assertNotIn("api_payload", row)

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_handoff_api_rejects_missing_or_wrong_key(self):
        payload = self.handoff_payload(risk="medium")
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().post(f"/api/external/tasks/{self.task['id']}/handoffs", json=payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["ok"])

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response = self.client().post(f"/api/external/tasks/{self.task['id']}/handoffs", json=payload)
            self.assertEqual(response.status_code, 403)

            response = self.client().post(
                f"/api/external/tasks/{self.task['id']}/handoffs",
                json=payload,
                headers=self.external_headers(key="wrong-key"),
            )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["ok"])

    def test_external_handoff_create_stores_metadata_is_idempotent_and_side_effect_free(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
            self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "external-invalid",
                    "external-invalid",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "medium",
                    "Invalid idempotency lookup payload",
                    "Invalid idempotency next step",
                    "",
                    "{not-json",
                    self.app_module.now_str(),
                ),
            )

        body = {
            "from_agent": "external-system-a",
            "to_agent": "devpilot-reviewer",
            "reason": "External handoff reason",
            "next_step": "External handoff next step",
            "risk": "medium",
            "external_ref": "external-ticket-123",
            "actor_type": "system",
            "actor_id": "external-system-a",
        }
        headers = self.external_headers(
            source="external-a",
            key="key-a",
            request_id="request-123",
            idempotency_key="external-ticket-123:create",
        )
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            with patch.object(self.app_module, "save_handoff") as legacy_save:
                                response = self.client().post(
                                    f"/api/external/tasks/{self.task['id']}/handoffs",
                                    json=body,
                                    headers=headers,
                                )
                                replay = self.client().post(
                                    f"/api/external/tasks/{self.task['id']}/handoffs",
                                    json={**body, "reason": "Retry body should not create duplicate"},
                                    headers=headers,
                                )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["idempotent_replay"])
        self.assertFalse(payload["execution_allowed"])
        self.assertEqual(payload["task_id"], self.task["id"])
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["conversation_ref"], f"ai-task:{self.task['id']}")
        self.assertEqual(payload["source_system"], "external-a")
        self.assertEqual(payload["external_ref"], "external-ticket-123")
        self.assertEqual(payload["idempotency_key"], "external-ticket-123:create")
        handoff_id = payload["handoff_id"]

        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        replay_payload = replay.get_json()
        self.assertTrue(replay_payload["idempotent_replay"])
        self.assertEqual(replay_payload["handoff_id"], handoff_id)

        with self.app.app_context():
            row = self.app_module.query_one("SELECT * FROM handoff_logs WHERE id=?", (handoff_id,))
            api_payload, parse_error = self.app_module.parse_ai_handoff_payload(row["api_payload"])
            handoff_count = self.app_module.query_one("SELECT COUNT(*) AS count FROM handoff_logs WHERE project_id=?", (self.project_id,))["count"]
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertFalse(parse_error)
        self.assertEqual(api_payload["source_system"], "external-a")
        self.assertEqual(api_payload["external_ref"], "external-ticket-123")
        self.assertEqual(api_payload["request_id"], "request-123")
        self.assertEqual(api_payload["idempotency_key"], "external-ticket-123:create")
        self.assertEqual(api_payload["actor_type"], "system")
        self.assertEqual(api_payload["actor_id"], "external-system-a")
        self.assertEqual(api_payload["risk_level"], "medium")
        self.assertEqual(handoff_count, 2)
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

    def test_external_handoff_read_endpoints_are_source_isolated(self):
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response_a = self.client().post(
                f"/api/external/tasks/{self.task['id']}/handoffs",
                json={
                    "from_agent": "external-a-agent",
                    "to_agent": "devpilot-reviewer",
                    "reason": "External A handoff",
                    "next_step": "Review external A",
                    "risk": "medium",
                    "external_ref": "ticket-a",
                    "actor_type": "system",
                    "actor_id": "external-a",
                },
                headers=self.external_headers(source="external-a", key="key-a", request_id="req-a", idempotency_key="idem-a"),
            )
            response_b = self.client().post(
                f"/api/external/tasks/{self.task['id']}/handoffs",
                json={
                    "from_agent": "external-b-agent",
                    "to_agent": "devpilot-reviewer",
                    "reason": "External B handoff",
                    "next_step": "Review external B",
                    "risk": "high",
                    "external_ref": "ticket-b",
                    "actor_type": "system",
                    "actor_id": "external-b",
                },
                headers=self.external_headers(source="external-b", key="key-b", request_id="req-b", idempotency_key="idem-b"),
            )
            self.assertEqual(response_a.status_code, 201)
            self.assertEqual(response_b.status_code, 201)
            handoff_a = response_a.get_json()["handoff_id"]
            handoff_b = response_b.get_json()["handoff_id"]

            response = self.client().get("/api/external/ai-handoffs", headers=self.external_headers(source="external-a", key="key-a"))
            self.assertEqual(response.status_code, 200)
            items = response.get_json()["items"]
            ids = {item["handoff_id"] for item in items}
            self.assertIn(handoff_a, ids)
            self.assertNotIn(handoff_b, ids)
            self.assertTrue(all(item["source_system"] == "external-a" for item in items))

            response = self.client().get(
                "/api/external/ai-handoffs?source_system=external-b",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
            self.assertEqual(response.status_code, 200)
            ids = {item["handoff_id"] for item in response.get_json()["items"]}
            self.assertIn(handoff_a, ids)
            self.assertNotIn(handoff_b, ids)

            response = self.client().get(
                "/api/external/ai-handoffs?external_ref=ticket-a&risk=medium",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
            self.assertEqual(response.status_code, 200)
            ids = {item["handoff_id"] for item in response.get_json()["items"]}
            self.assertIn(handoff_a, ids)
            self.assertNotIn(handoff_b, ids)

            response = self.client().get(
                f"/api/external/handoffs/{handoff_a}",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["execution_allowed"])
            self.assertEqual(payload["handoff"]["source_system"], "external-a")
            self.assertEqual(payload["handoff"]["external_ref"], "ticket-a")
            self.assertNotIn("api_payload", payload["handoff"])

            response = self.client().get(
                f"/api/external/handoffs/{handoff_b}",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
            self.assertEqual(response.status_code, 404)

        with patch.dict(self.app_module.os.environ, self.external_api_env(allow_all_sources=True), clear=False):
            response = self.client().get(
                "/api/external/ai-handoffs?include_all_sources=true",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
        self.assertEqual(response.status_code, 200)
        ids = {item["handoff_id"] for item in response.get_json()["items"]}
        self.assertIn(handoff_a, ids)
        self.assertIn(handoff_b, ids)

    def test_managed_external_api_key_generate_auth_revoke_and_env_compatibility(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        response = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "managed-a", "label": "Managed source A"},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        raw_key = payload["api_key"]
        record = payload["record"]
        self.assertTrue(raw_key.startswith("dp_ext_"))
        self.assertEqual(record["source_system"], "managed-a")
        self.assertEqual(record["status"], "active")
        self.assertIn("key_prefix", record)
        self.assertNotIn("key_hash", record)

        store_text = self.key_store_path.read_text(encoding="utf-8")
        store = json.loads(store_text)
        stored_record = store["keys"][0]
        self.assertNotIn(raw_key, store_text)
        self.assertEqual(stored_record["source_system"], "managed-a")
        self.assertEqual(stored_record["key_prefix"], record["key_prefix"])
        self.assertEqual(stored_record["key_hash"], self.app_module.external_api_key_hash(raw_key))

        response = self.client().get("/api/admin/external-api-keys")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(raw_key, response.get_data(as_text=True))

        headers = self.external_headers(
            source="managed-a",
            key=raw_key,
            request_id="managed-request",
            idempotency_key="managed-idempotency",
        )
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().get("/api/external/ai-handoffs", headers=headers)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="managed-a", key="wrong-key"),
            )
            self.assertEqual(response.status_code, 403)

            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="managed-b", key=raw_key),
            )
            self.assertEqual(response.status_code, 403)

            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            with patch.object(self.app_module, "save_handoff") as legacy_save:
                                create_response = self.client().post(
                                    f"/api/external/tasks/{self.task['id']}/handoffs",
                                    json={
                                        "from_agent": "managed-a",
                                        "to_agent": "devpilot-reviewer",
                                        "reason": "Managed key handoff",
                                        "next_step": "Review managed key handoff",
                                        "risk": "medium",
                                        "external_ref": "managed-ticket-1",
                                        "actor_type": "system",
                                        "actor_id": "managed-a",
                                    },
                                    headers=headers,
                                )
        self.assertEqual(create_response.status_code, 201, create_response.get_data(as_text=True))
        handoff_id = create_response.get_json()["handoff_id"]
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        with self.app.app_context():
            row = self.app_module.query_one("SELECT * FROM handoff_logs WHERE id=?", (handoff_id,))
            api_payload, parse_error = self.app_module.parse_ai_handoff_payload(row["api_payload"])
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertFalse(parse_error)
        self.assertEqual(api_payload["source_system"], "managed-a")
        self.assertEqual(api_payload["request_id"], "managed-request")
        self.assertEqual(api_payload["idempotency_key"], "managed-idempotency")
        self.assertEqual(api_payload["external_ref"], "managed-ticket-1")
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

        response = self.client().post(f"/api/admin/external-api-keys/{record['id']}/revoke", json={})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["api_key"])
        self.assertEqual(response.get_json()["record"]["status"], "revoked")
        self.assertNotIn(raw_key, response.get_data(as_text=True))

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().get("/api/external/ai-handoffs", headers=headers)
        self.assertEqual(response.status_code, 403)

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_managed_external_api_key_admin_page_and_store_fallbacks_are_safe(self):
        response = self.client().get("/admin/external-api-keys")
        self.assertEqual(response.status_code, 200)
        self.assertIn("External API Keys", response.get_data(as_text=True))

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="managed-a", key="missing-key"),
            )
        self.assertEqual(response.status_code, 403)

        self.key_store_path.write_text("{not-json", encoding="utf-8")
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="managed-a", key="missing-key"),
            )
        self.assertEqual(response.status_code, 403)

        self.key_store_path.write_text(
            json.dumps({"keys": [{"id": "bad-record"}, {"id": "bad-hash", "source_system": "managed-a", "key_prefix": "dp_ext_bad"}]}),
            encoding="utf-8",
        )
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().get(
                "/api/external/ai-handoffs",
                headers=self.external_headers(source="managed-a", key="missing-key"),
            )
        self.assertEqual(response.status_code, 403)

    def test_ai_provider_config_inspection_is_masked_and_read_only(self):
        before = self.state_snapshot()
        env = {
            "OPENAI_API_KEY": "sk-test-openai-secret-value",
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "gemini-test-secret-value",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    response = self.client().get("/api/admin/ai-providers")
                    page = self.client().get("/admin/ai-providers")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        providers = {item["id"]: item for item in payload["providers"]}
        self.assertTrue(providers["openai"]["configured"])
        self.assertTrue(providers["gemini"]["configured"])
        self.assertFalse(providers["claude"]["configured"])
        self.assertEqual(providers["openai"]["key_prefix"], "sk-tes...")
        self.assertNotIn("sk-test-openai-secret-value", response.get_data(as_text=True))
        self.assertNotIn("gemini-test-secret-value", response.get_data(as_text=True))
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["provider_calls_executed"])

        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("AI Providers", page_body)
        self.assertNotIn("sk-test-openai-secret-value", page_body)
        self.assertNotIn("gemini-test-secret-value", page_body)
        provider_call.assert_not_called()
        run_task.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_policy_manager_create_list_toggle_and_safe_defaults(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        response = self.client().post(
            "/api/admin/external-ai-policies",
            json={
                "source_system": "policy-source",
                "label": "Policy source summary",
                "allowed_providers": "openai, gemini",
                "allowed_models": "gpt-4.1-mini",
                "allowed_capabilities": "summary, classification",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        policy = response.get_json()["policy"]
        self.assertEqual(policy["source_system"], "policy-source")
        self.assertFalse(policy["enabled"])
        self.assertEqual(policy["allowed_providers"], ["openai", "gemini"])
        self.assertEqual(policy["allowed_models"], ["gpt-4.1-mini"])
        self.assertEqual(policy["allowed_capabilities"], ["summary", "classification"])
        self.assertFalse(policy["allow_streaming"])
        self.assertFalse(policy["allow_tool_calling"])
        self.assertFalse(policy["store_prompt"])
        self.assertFalse(policy["store_response"])
        self.assertEqual(policy["max_tokens_per_request"], self.app_module.EXTERNAL_AI_POLICY_DEFAULT_MAX_TOKENS)
        self.assertTrue(policy["disabled_at"])

        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        self.assertIn(policy["id"], {item["id"] for item in response.get_json()["policies"]})

        response = self.client().post(f"/api/admin/external-ai-policies/{policy['id']}/enable", json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["policy"]["enabled"])
        self.assertEqual(response.get_json()["policy"]["disabled_at"], "")

        response = self.client().post(f"/api/admin/external-ai-policies/{policy['id']}/disable", json={})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["policy"]["enabled"])
        self.assertTrue(response.get_json()["policy"]["disabled_at"])

        page = self.client().get("/admin/external-ai-policies")
        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("External AI Policies", page_body)
        self.assertIn('name="allowed_providers"', page_body)
        self.assertIn('value="openai"', page_body)
        self.assertIn('value="gemini"', page_body)
        self.assertIn('value="claude"', page_body)
        self.assertIn('value="replicate"', page_body)
        self.assertIn('value="fal"', page_body)
        self.assertIn('name="allowed_models" multiple', page_body)
        self.assertIn('value="gpt-4.1-mini"', page_body)
        self.assertIn('value="gpt-image-1"', page_body)
        self.assertIn('value="gemini-1.5-flash"', page_body)
        self.assertIn('value="claude-3-5-sonnet"', page_body)
        self.assertIn('value="flux-schnell"', page_body)
        self.assertIn('value="fal-flux-pro"', page_body)
        self.assertIn('value="summary"', page_body)
        self.assertIn('value="image_generation"', page_body)
        self.assertIn('value="video_generation"', page_body)
        self.assertIn('value="product_image"', page_body)
        self.assertIn("Providers are AI platforms", page_body)

        self.policy_store_path.write_text("{not-json", encoding="utf-8")
        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["policies"], [])

        self.policy_store_path.write_text(json.dumps({"policies": [{"id": "missing-source"}]}), encoding="utf-8")
        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["policies"], [])

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_policy_validation_rejects_unknown_or_mismatched_allowlists(self):
        before = self.state_snapshot()
        valid = self.client().post(
            "/api/admin/external-ai-policies",
            json={
                "source_system": "multi-policy-source",
                "allowed_providers": ["openai", "gemini", "claude", "replicate", "fal"],
                "allowed_models": ["gpt-4.1-mini", "gpt-image-1", "gemini-1.5-flash", "claude-3-5-haiku", "flux-schnell", "fal-flux-pro"],
                "allowed_capabilities": [
                    "summary",
                    "classification",
                    "rewrite",
                    "extraction",
                    "planning",
                    "chat",
                    "generate",
                    "image_generation",
                    "image_editing",
                    "image_variation",
                    "prompt_rewrite",
                    "video_generation",
                    "image_to_video",
                    "video_editing",
                    "ad_creative",
                    "product_image",
                    "avatar_generation",
                ],
            },
        )
        self.assertEqual(valid.status_code, 201, valid.get_data(as_text=True))
        policy = valid.get_json()["policy"]
        self.assertEqual(policy["allowed_providers"], ["openai", "gemini", "claude", "replicate", "fal"])
        self.assertEqual(policy["allowed_models"], ["gpt-4.1-mini", "gpt-image-1", "gemini-1.5-flash", "claude-3-5-haiku", "flux-schnell", "fal-flux-pro"])
        self.assertIn("image_generation", policy["allowed_capabilities"])
        self.assertIn("video_generation", policy["allowed_capabilities"])
        self.assertIn("product_image", policy["allowed_capabilities"])
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["allow_streaming"])
        self.assertFalse(policy["allow_tool_calling"])
        self.assertFalse(policy["store_prompt"])
        self.assertFalse(policy["store_response"])

        cases = [
            ({"allowed_providers": ["unknown-provider"]}, "unknown provider"),
            ({"allowed_providers": ["openai"], "allowed_models": ["unknown-model"]}, "unknown model"),
            ({"allowed_providers": ["openai"], "allowed_capabilities": ["unknown-capability"]}, "unknown capability"),
            ({"allowed_providers": ["openai"], "allowed_models": ["gemini-1.5-flash"]}, "model/provider mismatch"),
            ({"allowed_providers": ["replicate"], "allowed_models": ["fal-flux-schnell"]}, "model/provider mismatch"),
            ({"allowed_models": ["gpt-4.1-mini"]}, "model/provider mismatch"),
        ]
        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                    for index, (overrides, expected_error) in enumerate(cases):
                        body = {
                            "source_system": f"invalid-policy-{index}",
                            "allowed_providers": [],
                            "allowed_models": [],
                            "allowed_capabilities": [],
                        }
                        body.update(overrides)
                        response = self.client().post("/api/admin/external-ai-policies", json=body)
                        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
                        self.assertIn(expected_error, response.get_json()["error"])
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_stub_is_auth_gated_policy_gated_and_side_effect_free(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        body = {
            "capability": "summary",
            "model": "gpt-4.1-mini",
            "prompt": "Summarize this safely.",
            "external_ref": "stub-ticket-1",
        }

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            response = self.client().post("/api/external/ai/generate", json=body)
        self.assertEqual(response.status_code, 403)

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response = self.client().post(
                "/api/external/ai/generate",
                json=body,
                headers=self.external_headers(source="external-a", key="wrong-key"),
            )
        self.assertEqual(response.status_code, 403)

        headers = self.external_headers(source="external-a", key="key-a", request_id="gateway-req", idempotency_key="gateway-idem")
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], "external_ai_policy_not_enabled")

        policy = self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["openai"],
            "allowed_models": ["gpt-4.1-mini"],
            "allowed_capabilities": ["summary"],
        })
        self.assertTrue(policy["enabled"])
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            with patch.object(self.app_module, "save_handoff") as legacy_save:
                                response = self.client().post("/api/external/ai/generate", json=body, headers=headers)

        self.assertEqual(response.status_code, 501, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "external_ai_gateway_not_enabled")
        self.assertEqual(payload["source_system"], "external-a")
        self.assertEqual(payload["request_id"], "gateway-req")
        self.assertEqual(payload["policy_id"], policy["id"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["side_effects"])
        self.assertFalse(payload["provider_calls_executed"])
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
