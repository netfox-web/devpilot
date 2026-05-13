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
        self.profile_store_path = Path(self.key_store_dir.name) / "external_ai_permission_profiles.json"
        self.external_project_registry_path = Path(self.key_store_dir.name) / "external_project_registry.json"
        self.external_project_events_path = Path(self.key_store_dir.name) / "external_project_events.json"
        self.key_store_patch = patch.object(self.app_module, "EXTERNAL_API_KEY_STORE_PATH", self.key_store_path)
        self.policy_store_patch = patch.object(self.app_module, "EXTERNAL_AI_POLICY_STORE_PATH", self.policy_store_path)
        self.profile_store_patch = patch.object(self.app_module, "EXTERNAL_AI_PERMISSION_PROFILE_STORE_PATH", self.profile_store_path)
        self.external_project_registry_patch = patch.object(self.app_module, "EXTERNAL_PROJECT_REGISTRY_STORE_PATH", self.external_project_registry_path)
        self.external_project_events_patch = patch.object(self.app_module, "EXTERNAL_PROJECT_EVENTS_STORE_PATH", self.external_project_events_path)
        self.key_store_env_patch = patch.dict(
            self.app_module.os.environ,
            {
                "DEVPILOT_EXTERNAL_API_KEY_STORE_PATH": str(self.key_store_path),
                "DEVPILOT_EXTERNAL_AI_POLICY_STORE_PATH": str(self.policy_store_path),
                "DEVPILOT_EXTERNAL_AI_PERMISSION_PROFILE_STORE_PATH": str(self.profile_store_path),
                "DEVPILOT_EXTERNAL_PROJECT_REGISTRY_PATH": str(self.external_project_registry_path),
                "DEVPILOT_EXTERNAL_PROJECT_EVENTS_PATH": str(self.external_project_events_path),
            },
            clear=False,
        )
        self.key_store_patch.start()
        self.policy_store_patch.start()
        self.profile_store_patch.start()
        self.external_project_registry_patch.start()
        self.external_project_events_patch.start()
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
        self.external_project_events_patch.stop()
        self.external_project_registry_patch.stop()
        self.profile_store_patch.stop()
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

    def test_external_ai_policy_source_dropdown_uses_managed_keys_safely(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        active_response = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "dropdown-source", "label": "Dropdown source label"},
        )
        self.assertEqual(active_response.status_code, 201, active_response.get_data(as_text=True))
        active_payload = active_response.get_json()
        active_raw_key = active_payload["api_key"]
        active_record = active_payload["record"]

        duplicate_one = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "duplicate-source", "label": "Duplicate source first"},
        ).get_json()
        duplicate_two = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "duplicate-source", "label": "Duplicate source second"},
        ).get_json()

        revoked_response = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "revoked-source", "label": "Revoked source label"},
        )
        revoked_payload = revoked_response.get_json()
        revoked_raw_key = revoked_payload["api_key"]
        revoke_response = self.client().post(f"/api/admin/external-api-keys/{revoked_payload['record']['id']}/revoke", json={})
        self.assertEqual(revoke_response.status_code, 200)

        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                    page = self.client().get("/admin/external-ai-policies")
                    dropdown_create = self.client().post(
                        "/admin/external-ai-policies",
                        data={
                            "source_system_select": "dropdown-source",
                            "source_system": "",
                            "label": "Dropdown policy",
                            "allowed_providers": "openai",
                            "allowed_models": "gpt-4.1-mini",
                            "allowed_capabilities": "summary",
                        },
                    )
                    grouped_model_create = self.client().post(
                        "/admin/external-ai-policies",
                        data={
                            "source_system_select": "",
                            "source_system": "grouped-model-source",
                            "label": "Grouped model policy",
                            "allowed_providers": ["openai", "gemini"],
                            "allowed_models": ["gpt-4.1-mini", "gemini-1.5-flash"],
                            "allowed_capabilities": "summary",
                        },
                    )
                    manual_create = self.client().post(
                        "/admin/external-ai-policies",
                        data={
                            "source_system_select": "",
                            "source_system": "manual-source",
                            "label": "Manual policy",
                            "allowed_providers": "gemini",
                            "allowed_models": "gemini-1.5-flash",
                            "allowed_capabilities": "extraction",
                        },
                    )

        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("sourcePickerSearch", page_body)
        self.assertIn('name="source_systems"', page_body)
        self.assertIn("Apply Permission Profile", page_body)
        self.assertIn("Basic Text", page_body)
        self.assertIn("Text Multi Provider", page_body)
        self.assertIn("Image Basic", page_body)
        self.assertIn("Image Pro", page_body)
        self.assertIn("Video Review Only", page_body)
        self.assertIn("/admin/external-ai-permission-profiles", page_body)
        self.assertIn("Select a managed source system", page_body)
        self.assertIn("dropdown-source", page_body)
        self.assertIn("Dropdown source label", page_body)
        self.assertIn(active_record["key_prefix"], page_body)
        self.assertNotIn(active_raw_key, page_body)
        self.assertNotIn("key_hash", page_body)
        self.assertNotIn("revoked-source", page_body)
        self.assertNotIn(revoked_raw_key, page_body)
        self.assertEqual(page_body.count('name="source_systems" value="duplicate-source"'), 1)
        self.assertNotIn(duplicate_one["api_key"], page_body)
        self.assertNotIn(duplicate_two["api_key"], page_body)

        self.assertEqual(dropdown_create.status_code, 302, dropdown_create.get_data(as_text=True))
        self.assertEqual(grouped_model_create.status_code, 302, grouped_model_create.get_data(as_text=True))
        self.assertEqual(manual_create.status_code, 302, manual_create.get_data(as_text=True))
        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        policies = {item["source_system"]: item for item in response.get_json()["policies"]}
        sources = set(policies)
        self.assertIn("dropdown-source", sources)
        self.assertIn("grouped-model-source", sources)
        self.assertIn("manual-source", sources)
        self.assertEqual(policies["grouped-model-source"]["allowed_providers"], ["openai", "gemini"])
        self.assertEqual(policies["grouped-model-source"]["allowed_models"], ["gpt-4.1-mini", "gemini-1.5-flash"])

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_permission_profiles_apply_batch_and_update_existing(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        profiles = {item["id"]: item for item in response.get_json()["permission_profiles"]}
        self.assertIn("basic-text", profiles)
        self.assertIn("text-multi-provider", profiles)
        self.assertIn("image-basic", profiles)
        self.assertIn("image-pro", profiles)
        self.assertIn("video-review-only", profiles)
        self.assertEqual(profiles["basic-text"]["daily_request_limit"], 1000)
        self.assertEqual(profiles["text-multi-provider"]["allowed_providers"], ["openai", "gemini", "claude"])
        self.assertEqual(profiles["text-multi-provider"]["allowed_models"], ["gpt-4.1-mini", "gemini-1.5-flash", "claude-3-5-haiku"])
        self.assertEqual(profiles["image-basic"]["daily_request_limit"], 300)
        self.assertEqual(profiles["image-pro"]["daily_request_limit"], 1000)
        self.assertEqual(profiles["video-review-only"]["daily_request_limit"], 20)
        self.assertEqual(profiles["video-review-only"]["allowed_providers"], ["fal"])
        self.assertEqual(profiles["video-review-only"]["allowed_models"], ["fal-flux-pro"])
        self.assertFalse(profiles["video-review-only"]["enabled"])
        self.assertFalse(profiles["video-review-only"]["enabled_by_default"])

        self.profile_store_path.write_text("{not-json", encoding="utf-8")
        response = self.client().get("/api/admin/external-ai-policies")
        self.assertEqual(response.status_code, 200)
        self.assertIn("basic-text", {item["id"] for item in response.get_json()["permission_profiles"]})

        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                    with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                        with patch.object(self.app_module, "save_handoff") as legacy_save:
                            response = self.client().post(
                                "/api/admin/external-ai-policies/apply-profile",
                                json={
                                    "profile_id": "basic-text",
                                    "source_systems": ["profile-a", "profile-b"],
                                },
                            )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        result = response.get_json()["result"]
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)

        response = self.client().get("/api/admin/external-ai-policies")
        policies = {item["source_system"]: item for item in response.get_json()["policies"]}
        self.assertEqual(len(policies), 2)
        self.assertEqual(policies["profile-a"]["profile_id"], "basic-text")
        self.assertTrue(policies["profile-a"]["enabled"])
        self.assertEqual(policies["profile-a"]["allowed_providers"], ["openai"])
        self.assertEqual(policies["profile-a"]["allowed_models"], ["gpt-4.1-mini"])
        self.assertEqual(policies["profile-a"]["allowed_capabilities"], ["summary", "classification", "rewrite"])
        self.assertEqual(policies["profile-a"]["daily_request_limit"], 1000)

        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={
                "profile_id": "text-multi-provider",
                "source_systems": ["profile-b"],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        response = self.client().get("/api/admin/external-ai-policies")
        policies = {item["source_system"]: item for item in response.get_json()["policies"]}
        self.assertEqual(policies["profile-b"]["profile_id"], "text-multi-provider")
        self.assertEqual(policies["profile-b"]["allowed_providers"], ["openai", "gemini", "claude"])
        self.assertEqual(policies["profile-b"]["allowed_models"], ["gpt-4.1-mini", "gemini-1.5-flash", "claude-3-5-haiku"])

        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={
                "profile_id": "image-basic",
                "source_systems": ["profile-a"],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["result"]["updated"], 1)
        response = self.client().get("/api/admin/external-ai-policies")
        policies = {item["source_system"]: item for item in response.get_json()["policies"]}
        self.assertEqual(len(policies), 2)
        self.assertEqual(policies["profile-a"]["profile_id"], "image-basic")
        self.assertEqual(policies["profile-a"]["allowed_providers"], ["openai", "replicate", "fal"])
        self.assertEqual(policies["profile-a"]["allowed_models"], ["gpt-image-1", "flux-schnell", "fal-flux-schnell"])
        self.assertEqual(policies["profile-a"]["allowed_capabilities"], ["image_generation", "prompt_rewrite"])
        self.assertEqual(policies["profile-a"]["daily_request_limit"], 300)

        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={
                "profile_id": "image-pro",
                "source_systems": ["profile-b"],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={
                "profile_id": "video-review-only",
                "source_systems": ["profile-c"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("permission profile is disabled", response.get_json()["error"])
        response = self.client().get("/api/admin/external-ai-policies")
        policies = {item["source_system"]: item for item in response.get_json()["policies"]}
        self.assertEqual(policies["profile-b"]["profile_id"], "image-pro")
        self.assertEqual(policies["profile-b"]["allowed_models"], ["gpt-image-1", "flux-pro", "fal-flux-pro"])
        self.assertNotIn("profile-c", policies)

        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={"profile_id": "unknown-profile", "source_systems": ["profile-z"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown permission profile", response.get_json()["error"])

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_permission_profile_manager_crud_validation_and_warnings(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        page = self.client().get("/admin/external-ai-permission-profiles")
        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("External AI Permission Profiles", page_body)
        self.assertIn("Basic Text", page_body)
        self.assertIn("Text Multi Provider", page_body)
        self.assertIn("Image Basic", page_body)
        self.assertIn("Image Pro", page_body)
        self.assertIn("Video Review Only", page_body)
        self.assertIn('name="allowed_providers"', page_body)
        self.assertIn('value="openai"', page_body)
        self.assertIn('value="runway"', page_body)
        self.assertIn("Models are selected per provider. Selecting a provider does not automatically allow all models.", page_body)
        self.assertIn('data-model-provider="openai"', page_body)
        self.assertIn('data-model-provider="gemini"', page_body)
        self.assertIn('data-provider-model="openai"', page_body)
        self.assertIn('data-provider-model="fal"', page_body)
        self.assertIn('value="gpt-4.1-mini" data-provider-model="openai" checked', page_body)
        self.assertIn('value="gemini-1.5-flash" data-provider-model="gemini" checked', page_body)
        self.assertIn('value="gpt-image-1"', page_body)
        self.assertIn('value="fal-flux-pro"', page_body)
        self.assertNotIn("key_hash", page_body)

        high_risk_payload = {
            "id": "custom-high-risk",
            "name": "Custom High Risk",
            "description": "Exercises warning behavior",
            "enabled": True,
            "enabled_by_default": True,
            "allowed_providers": ["openai", "gemini", "claude", "replicate", "fal"],
            "allowed_models": ["gpt-4.1-mini", "gemini-1.5-flash", "claude-3-5-haiku", "flux-schnell", "fal-flux-pro"],
            "allowed_capabilities": [
                "summary",
                "classification",
                "rewrite",
                "extraction",
                "planning",
                "chat",
                "generate",
                "image_generation",
                "prompt_rewrite",
                "video_generation",
                "image_to_video",
            ],
            "max_tokens_per_request": 5000,
            "daily_request_limit": 1500,
            "daily_token_limit": 600000,
            "monthly_budget_usd": 150,
            "allow_streaming": True,
            "allow_tool_calling": True,
            "store_prompt": True,
            "store_response": True,
            "note": "High risk test profile",
        }

        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                    with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                        with patch.object(self.app_module, "save_handoff") as legacy_save:
                            response = self.client().post("/api/admin/external-ai-permission-profiles", json=high_risk_payload)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        profile = response.get_json()["profile"]
        warning_text = "\n".join(profile["warnings"])
        self.assertIn("Tool calling is enabled", warning_text)
        self.assertIn("Streaming is enabled", warning_text)
        self.assertIn("Full prompt storage is enabled", warning_text)
        self.assertIn("Full response storage is enabled", warning_text)
        self.assertIn("Many capabilities selected", warning_text)
        self.assertIn("Video capability is enabled", warning_text)
        self.assertIn("Monthly budget is high", warning_text)
        self.assertIn("Daily request limit is high", warning_text)
        self.assertIn("Daily token limit is high", warning_text)

        page = self.client().get("/admin/external-ai-permission-profiles")
        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("Custom High Risk", page_body)
        self.assertIn("Policy", self.client().get("/admin/external-ai-policies").get_data(as_text=True))
        self.assertIn("Tool calling is enabled", page_body)

        update_payload = {
            "name": "Custom Safer",
            "description": "Updated safer profile",
            "enabled": True,
            "enabled_by_default": False,
            "allowed_providers": ["openai", "gemini"],
            "allowed_models": ["gpt-4.1-mini", "gemini-1.5-flash"],
            "allowed_capabilities": ["summary", "extraction"],
            "max_tokens_per_request": 2000,
            "daily_request_limit": 200,
            "daily_token_limit": 100000,
            "monthly_budget_usd": 20,
            "allow_streaming": False,
            "allow_tool_calling": False,
            "store_prompt": False,
            "store_response": False,
        }
        response = self.client().post("/api/admin/external-ai-permission-profiles/custom-high-risk/update", json=update_payload)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["profile"]["name"], "Custom Safer")
        self.assertEqual(response.get_json()["profile"]["allowed_providers"], ["openai", "gemini"])

        response = self.client().post("/api/admin/external-ai-permission-profiles/custom-high-risk/disable", json={})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["profile"]["enabled"])
        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={"profile_id": "custom-high-risk", "source_systems": ["custom-profile-source"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("permission profile is disabled", response.get_json()["error"])
        response = self.client().post("/api/admin/external-ai-permission-profiles/custom-high-risk/enable", json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["profile"]["enabled"])
        response = self.client().post(
            "/api/admin/external-ai-policies/apply-profile",
            json={"profile_id": "custom-high-risk", "source_systems": ["custom-profile-source"]},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        applied = response.get_json()["result"]["policies"][0]
        self.assertEqual(applied["source_system"], "custom-profile-source")
        self.assertEqual(applied["profile_id"], "custom-high-risk")
        self.assertEqual(applied["allowed_capabilities"], ["summary", "extraction"])

        cases = [
            ({"id": "bad-provider", "name": "Bad Provider", "allowed_providers": ["unknown-provider"]}, "unknown provider"),
            ({"id": "bad-model", "name": "Bad Model", "allowed_providers": ["openai"], "allowed_models": ["unknown-model"]}, "unknown model"),
            ({"id": "bad-capability", "name": "Bad Capability", "allowed_providers": ["openai"], "allowed_capabilities": ["unknown-capability"]}, "unknown capability"),
            ({"id": "bad-mismatch", "name": "Bad Mismatch", "allowed_providers": ["openai"], "allowed_models": ["gemini-1.5-flash"]}, "model/provider mismatch"),
        ]
        for payload, expected_error in cases:
            response = self.client().post("/api/admin/external-ai-permission-profiles", json=payload)
            self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
            self.assertIn(expected_error, response.get_json()["error"])

        warning_policy = self.client().post(
            "/api/admin/external-ai-policies",
            json=dict(high_risk_payload, source_system="warning-source", id=None, name=None, label="Warning source"),
        )
        self.assertEqual(warning_policy.status_code, 201, warning_policy.get_data(as_text=True))
        policy_warnings = "\n".join(warning_policy.get_json()["policy"]["warnings"])
        self.assertIn("Tool calling is enabled", policy_warnings)
        policy_page = self.client().get("/admin/external-ai-policies")
        self.assertEqual(policy_page.status_code, 200)
        self.assertIn("Policy warnings", policy_page.get_data(as_text=True))
        self.assertIn("Video capability is enabled", policy_page.get_data(as_text=True))

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_api_key_integration_doc_download_is_safe(self):
        before = self.state_snapshot()
        response = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "doc-source", "label": "Doc source label"},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        raw_key = payload["api_key"]
        record = payload["record"]
        store_text = self.key_store_path.read_text(encoding="utf-8")
        stored_key_hash = json.loads(store_text)["keys"][0]["key_hash"]

        unauthenticated = self.app.test_client().get(f"/admin/external-api-keys/{record['id']}/integration-doc")
        self.assertEqual(unauthenticated.status_code, 302)

        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "run_ai_task") as run_task:
                doc_response = self.client().get(f"/admin/external-api-keys/{record['id']}/integration-doc")

        self.assertEqual(doc_response.status_code, 200, doc_response.get_data(as_text=True))
        self.assertIn("text/markdown", doc_response.headers.get("Content-Type", ""))
        self.assertIn("attachment", doc_response.headers.get("Content-Disposition", ""))
        self.assertIn("devpilot-integration-doc-source.md", doc_response.headers.get("Content-Disposition", ""))
        body = doc_response.get_data(as_text=True)
        self.assertIn("doc-source", body)
        self.assertIn("Doc source label", body)
        self.assertIn(record["key_prefix"], body)
        self.assertIn('DEVPILOT_API_KEY="<paste-the-key-shown-once>"', body)
        self.assertIn("POST /api/external/tasks/<task_id>/handoffs", body)
        self.assertIn("GET /api/external/ai-handoffs", body)
        self.assertIn("GET /api/external/handoffs/<handoff_id>", body)
        self.assertIn("X-DevPilot-Idempotency-Key", body)
        self.assertIn("AbortController", body)
        self.assertIn("randomUUID", body)
        self.assertIn("requests.post", body)
        self.assertNotIn(raw_key, body)
        self.assertNotIn(stored_key_hash, body)
        self.assertNotIn("key_hash", body)
        provider_call.assert_not_called()
        run_task.assert_not_called()

        page = self.client().get("/admin/external-api-keys")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f"/admin/external-api-keys/{record['id']}/integration-doc", page.get_data(as_text=True))
        self.assertNotIn(raw_key, page.get_data(as_text=True))

        revoke_response = self.client().post(f"/api/admin/external-api-keys/{record['id']}/revoke", json={})
        self.assertEqual(revoke_response.status_code, 200)
        revoked_doc = self.client().get(f"/admin/external-api-keys/{record['id']}/integration-doc")
        self.assertEqual(revoked_doc.status_code, 200)
        self.assertIn("revoked", revoked_doc.get_data(as_text=True).lower())
        self.assertNotIn(raw_key, revoked_doc.get_data(as_text=True))
        self.assertEqual(self.state_snapshot(), before)

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
        self.assertIn('value="runway"', page_body)
        self.assertIn('value="kling"', page_body)
        self.assertIn("Models are selected per provider. Selecting a provider does not automatically allow all models.", page_body)
        self.assertIn('data-model-provider="openai"', page_body)
        self.assertIn('data-model-provider="gemini"', page_body)
        self.assertIn('data-model-provider="claude"', page_body)
        self.assertIn('data-provider-model="openai"', page_body)
        self.assertIn('data-provider-model="gemini"', page_body)
        self.assertIn('value="gpt-4.1-mini"', page_body)
        self.assertIn('value="gpt-image-1"', page_body)
        self.assertIn('value="gemini-1.5-flash"', page_body)
        self.assertIn('value="claude-3-5-sonnet"', page_body)
        self.assertIn('value="flux-schnell"', page_body)
        self.assertIn('value="fal-flux-pro"', page_body)
        self.assertIn("<span class=\"text-muted\">openai:</span> gpt-4.1-mini", page_body)
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
                "allowed_providers": ["openai", "gemini", "claude", "replicate", "fal", "runway", "kling"],
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
        self.assertEqual(policy["allowed_providers"], ["openai", "gemini", "claude", "replicate", "fal", "runway", "kling"])
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

    def test_external_project_registry_register_read_isolated_and_safe(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        body = {
            "external_project_id": "ai-image-site-prod",
            "name": "AI Image Site",
            "description": "AI image generation website",
            "project_type": "ai-saas",
            "environment": "production",
            "status": "active",
            "repo_url": "https://github.com/example/ai-image-site",
            "branch": "main",
            "commit_sha": "abc123",
            "local_path": r"E:\Ai-project\ai-image-site",
            "nas_worktree_path": "/volume1/worktrees/ai-image-site",
            "nas_compose_path": "/volume1/docker/ai-image-site/docker-compose.yml",
            "nas_data_path": "/volume1/docker/ai-image-site/data",
            "container_name": "ai-image-site",
            "compose_project": "ai-image-site",
            "service_name": "web",
            "host_port": "5080",
            "container_port": "3000",
            "app_url": "https://image.example.com",
            "requested_domains": ["image.example.com", "www.image.example.com"],
            "deployment_target": "nas-docker",
            "runtime": "node/python/docker",
            "healthcheck_url": "https://image.example.com/health",
            "owner": "client/team name",
            "notes": "Needs domain pointing later",
        }

        missing = self.client().post("/api/external/projects/register", json=body)
        self.assertEqual(missing.status_code, 403)
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            wrong = self.client().post(
                "/api/external/projects/register",
                json=body,
                headers=self.external_headers(source="external-a", key="wrong-key"),
            )
        self.assertEqual(wrong.status_code, 403)

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            with patch.object(self.app_module, "save_handoff") as legacy_save:
                                created = self.client().post(
                                    "/api/external/projects/register",
                                    json=body,
                                    headers=self.external_headers(source="external-a", key="key-a", request_id="project-req-1", idempotency_key="project-idem-1"),
                                )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        project = created.get_json()["project"]
        self.assertTrue(created.get_json()["created"])
        self.assertEqual(project["source_system"], "external-a")
        self.assertEqual(project["external_project_id"], "ai-image-site-prod")
        self.assertEqual(project["requested_domains"], ["image.example.com", "www.image.example.com"])
        self.assertEqual(project["primary_domain"], "image.example.com")
        self.assertEqual(project["domain_status"], "review_needed")
        self.assertTrue(project["dns_action_required"])
        self.assertEqual(project["local_path"], r"E:\Ai-project\ai-image-site")
        self.assertEqual(project["nas_worktree_path"], "/volume1/worktrees/ai-image-site")
        self.assertFalse(created.get_json()["infra_actions_executed"])
        self.assertFalse(created.get_json()["provider_calls_executed"])
        self.assertFalse(created.get_json()["worker_execution"])
        self.assertFalse(created.get_json()["approval_created"])

        update_body = dict(body, name="AI Image Site Updated", status="paused", domain_status="requested", commit_sha="def456")
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            with patch.object(self.app_module, "now_str", return_value="2099-01-01 00:00:00"):
                updated = self.client().post(
                    "/api/external/projects/register",
                    json=update_body,
                    headers=self.external_headers(source="external-a", key="key-a", request_id="project-req-2", idempotency_key="project-idem-1"),
                )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        updated_project = updated.get_json()["project"]
        self.assertFalse(updated.get_json()["created"])
        self.assertEqual(updated_project["name"], "AI Image Site Updated")
        self.assertEqual(updated_project["status"], "paused")
        self.assertEqual(updated_project["last_seen_at"], "2099-01-01 00:00:00")
        self.assertEqual(len(self.app_module.load_external_project_registry_records()), 1)

        other_body = dict(body, external_project_id="other-project", name="Other Source Project", requested_domains=["other.example.com"])
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            other = self.client().post(
                "/api/external/projects/register",
                json=other_body,
                headers=self.external_headers(source="external-b", key="key-b", request_id="project-req-b", idempotency_key="project-idem-b"),
            )
        self.assertEqual(other.status_code, 201, other.get_data(as_text=True))

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            own_list = self.client().get("/api/external/projects", headers=self.external_headers(source="external-a", key="key-a"))
            own_detail = self.client().get("/api/external/projects/ai-image-site-prod", headers=self.external_headers(source="external-a", key="key-a"))
            blocked_detail = self.client().get("/api/external/projects/other-project", headers=self.external_headers(source="external-a", key="key-a"))
            forced_other = self.client().get("/api/external/projects?source_system=external-b", headers=self.external_headers(source="external-a", key="key-a"))
        self.assertEqual(own_list.status_code, 200)
        self.assertEqual({item["external_project_id"] for item in own_list.get_json()["projects"]}, {"ai-image-site-prod"})
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(blocked_detail.status_code, 404)
        self.assertEqual(forced_other.status_code, 200)
        self.assertEqual({item["external_project_id"] for item in forced_other.get_json()["projects"]}, set())

        with patch.dict(self.app_module.os.environ, self.external_api_env(allow_all_sources=True), clear=False):
            allow_all = self.client().get(
                "/api/external/projects?include_all_sources=true",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
        self.assertEqual(allow_all.status_code, 200)
        self.assertIn("other-project", {item["external_project_id"] for item in allow_all.get_json()["projects"]})

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            invalid_domain = self.client().post(
                "/api/external/projects/register",
                json=dict(body, external_project_id="bad-domain", name="Bad Domain", requested_domains=["bad.example.com;rm -rf /"]),
                headers=self.external_headers(source="external-a", key="key-a"),
            )
        self.assertEqual(invalid_domain.status_code, 400)
        self.assertIn("requested_domains", invalid_domain.get_json()["error"])

        admin_page = self.client().get("/admin/external-projects?q=Updated&environment=production&status=paused&domain_status=requested")
        self.assertEqual(admin_page.status_code, 200)
        page_body = admin_page.get_data(as_text=True)
        self.assertIn("AI Image Site Updated", page_body)
        self.assertIn("external-a / ai-image-site-prod", page_body)
        self.assertIn("/volume1/worktrees/ai-image-site", page_body)
        self.assertIn("image.example.com", page_body)
        self.assertIn("Domain fields are review-only", page_body)
        self.assertNotIn("key-a", page_body)
        self.assertNotIn("key_hash", page_body)

        detail_page = self.client().get("/admin/external-projects/external-a/ai-image-site-prod")
        self.assertEqual(detail_page.status_code, 200)
        self.assertIn("External Project Detail", detail_page.get_data(as_text=True))
        self.assertIn("nas_compose_path", detail_page.get_data(as_text=True))

        store = json.loads(self.external_project_registry_path.read_text(encoding="utf-8"))
        self.assertEqual(len(store["projects"]), 2)
        self.assertNotIn("key-a", self.external_project_registry_path.read_text(encoding="utf-8"))
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_project_events_are_source_isolated_and_side_effect_free(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        project_body = {
            "external_project_id": "event-project",
            "name": "Event Project",
            "project_type": "ai-saas",
            "environment": "production",
            "status": "active",
            "requested_domains": ["event.example.com"],
        }
        other_project_body = {
            "external_project_id": "other-event-project",
            "name": "Other Event Project",
            "project_type": "website",
            "environment": "staging",
            "status": "active",
        }
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            register = self.client().post(
                "/api/external/projects/register",
                json=project_body,
                headers=self.external_headers(source="external-a", key="key-a", idempotency_key="event-project-register"),
            )
            other_register = self.client().post(
                "/api/external/projects/register",
                json=other_project_body,
                headers=self.external_headers(source="external-b", key="key-b", idempotency_key="other-event-project-register"),
            )
        self.assertEqual(register.status_code, 201, register.get_data(as_text=True))
        self.assertEqual(other_register.status_code, 201, other_register.get_data(as_text=True))

        event_body = {
            "event_type": "deploy_success",
            "status": "success",
            "message": "Production deployment finished.",
            "environment": "production",
            "commit_sha": "abc123",
            "app_url": "https://event.example.com",
            "metadata": {"duration_seconds": 42, "deployment_id": "deploy-1"},
        }
        missing_key = self.client().post("/api/external/projects/event-project/events", json=event_body)
        self.assertEqual(missing_key.status_code, 403)
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            wrong_key = self.client().post(
                "/api/external/projects/event-project/events",
                json=event_body,
                headers=self.external_headers(source="external-a", key="wrong-key"),
            )
        self.assertEqual(wrong_key.status_code, 403)

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            with patch.object(self.app_module, "now_str", return_value="2099-02-03 04:05:06"):
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                with patch.object(self.app_module, "save_handoff") as legacy_save:
                                    created = self.client().post(
                                        "/api/external/projects/event-project/events",
                                        json=event_body,
                                        headers=self.external_headers(source="external-a", key="key-a", request_id="event-req-1", idempotency_key="event-idem-1"),
                                    )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        event = created.get_json()["event"]
        self.assertEqual(event["source_system"], "external-a")
        self.assertEqual(event["external_project_id"], "event-project")
        self.assertEqual(event["event_type"], "deploy_success")
        self.assertEqual(event["status"], "success")
        self.assertEqual(event["metadata"]["deployment_id"], "deploy-1")
        self.assertEqual(event["created_at"], "2099-02-03 04:05:06")
        self.assertFalse(created.get_json()["infra_actions_executed"])
        self.assertFalse(created.get_json()["provider_calls_executed"])
        self.assertFalse(created.get_json()["worker_execution"])
        self.assertFalse(created.get_json()["approval_created"])
        self.assertFalse(created.get_json()["task_project_mutation"])

        records = self.app_module.load_external_project_registry_records()
        own_project = next(item for item in records if item["source_system"] == "external-a" and item["external_project_id"] == "event-project")
        self.assertEqual(own_project["last_seen_at"], "2099-02-03 04:05:06")

        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            own_events = self.client().get(
                "/api/external/projects/event-project/events",
                headers=self.external_headers(source="external-a", key="key-a"),
            )
            other_read_blocked = self.client().get(
                "/api/external/projects/event-project/events",
                headers=self.external_headers(source="external-b", key="key-b"),
            )
            other_write_blocked = self.client().post(
                "/api/external/projects/event-project/events",
                json=event_body,
                headers=self.external_headers(source="external-b", key="key-b"),
            )
        self.assertEqual(own_events.status_code, 200)
        self.assertEqual(own_events.get_json()["count"], 1)
        self.assertEqual(own_events.get_json()["events"][0]["event_type"], "deploy_success")
        self.assertEqual(other_read_blocked.status_code, 404)
        self.assertEqual(other_write_blocked.status_code, 404)

        invalid_cases = [
            ({"event_type": "bad-event", "status": "info"}, "invalid event_type"),
            ({"event_type": "custom", "status": "bad-status"}, "invalid status"),
            ({"event_type": "custom", "metadata": ["not", "object"]}, "metadata must be an object"),
            ({"event_type": "custom", "message": "hello; rm -rf /"}, "message contains unsafe characters"),
        ]
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            for payload, expected_error in invalid_cases:
                response = self.client().post(
                    "/api/external/projects/event-project/events",
                    json=payload,
                    headers=self.external_headers(source="external-a", key="key-a"),
                )
                self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
                self.assertIn(expected_error, response.get_json()["error"])

        detail_page = self.client().get("/admin/external-projects/external-a/event-project")
        self.assertEqual(detail_page.status_code, 200)
        page_body = detail_page.get_data(as_text=True)
        self.assertIn("Recent Events", page_body)
        self.assertIn("deploy_success", page_body)
        self.assertIn("Production deployment finished.", page_body)
        self.assertNotIn("key-a", page_body)
        self.assertNotIn("key_hash", page_body)

        store_text = self.external_project_events_path.read_text(encoding="utf-8")
        store = json.loads(store_text)
        self.assertEqual(len(store["events"]), 1)
        self.assertNotIn("key-a", store_text)
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
