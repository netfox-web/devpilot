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

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

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

        response = self.client().get("/api/ai-handoffs?q=searchable&status=accepted&risk_level=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        ids = {item["id"] for item in payload["items"]}
        self.assertIn(match["id"], ids)
        self.assertNotIn(other["id"], ids)

        response = self.client().get("/ai-handoffs?q=searchable&status=accepted&risk_level=medium&from_agent=planner-search&to_agent=executor-search")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Searchable follow-up step", body)
        self.assertIn("planner-search", body)
        self.assertIn('name="q"', body)
        self.assertIn('name="from_agent"', body)
        self.assertIn('name="to_agent"', body)
        self.assertIn('value="medium" selected', body)

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


if __name__ == "__main__":
    unittest.main()
