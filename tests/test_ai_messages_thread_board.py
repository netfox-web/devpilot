import json
import unittest
from unittest.mock import patch


class AiMessagesThreadBoardTest(unittest.TestCase):
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
        self.marker = "ai_thread_board_test"
        with self.app.app_context():
            self.task = self.app_module.create_ai_task({
                "title": "AI Thread Board Test Task",
                "prompt": "Read-only thread board fixture.",
                "provider": "openai",
                "task_type": "review",
                "priority": "medium",
            })
            self.executor_message_id = self.app_module.insert_ai_message(
                None,
                "openai",
                "test-model",
                "executor",
                "executor fixture",
            )
            self.app_module.update_ai_message(
                self.executor_message_id,
                status="done",
                response_text="executor completed fixture",
                raw_response=json.dumps({"task_id": self.task["id"], "marker": self.marker}),
            )
            self.reviewer_message_id = self.app_module.insert_ai_message(
                None,
                "gemini",
                "test-reviewer",
                "reviewer",
                "reviewer fixture",
            )
            self.app_module.update_ai_message(
                self.reviewer_message_id,
                status="done",
                response_text="reviewer pass fixture",
                raw_response=json.dumps({"task_id": self.task["id"], "marker": self.marker, "review": "pass"}),
            )

    def tearDown(self):
        with self.app.app_context():
            self.app_module.execute("DELETE FROM ai_messages WHERE raw_response LIKE ?", (f"%{self.marker}%",))
            self.app_module.execute("DELETE FROM tasks WHERE title=?", ("AI Thread Board Test Task",))

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def test_ai_messages_page_returns_200(self):
        response = self.client().get("/ai-messages")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI Messages", response.get_data(as_text=True))
        self.assertIn("AI Thread Board Test Task", response.get_data(as_text=True))

    def test_api_ai_messages_returns_thread_list(self):
        response = self.client().get("/api/ai-messages")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIsInstance(payload["items"], list)
        self.assertTrue(any(item.get("task_id") == self.task["id"] for item in payload["items"]))

    def test_task_thread_page_returns_200(self):
        response = self.client().get(f"/tasks/{self.task['id']}/thread")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("AI Task Thread", text)
        self.assertIn("reviewer pass fixture", text)

    def test_task_timeline_api_returns_timeline(self):
        response = self.client().get(f"/api/tasks/{self.task['id']}/timeline")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["task"]["id"], self.task["id"])
        self.assertIsInstance(payload["timeline"], list)
        self.assertTrue(any(item.get("type") == "ai_message" for item in payload["timeline"]))

    def test_timeline_contains_expected_sections(self):
        response = self.client().get(f"/api/tasks/{self.task['id']}/timeline")
        payload = response.get_json()
        for key in ("messages", "handoffs", "heartbeats", "approvals", "dispatch_jobs"):
            self.assertIn(key, payload)
            self.assertIsInstance(payload[key], list)
        self.assertEqual(len(payload["reviewer_messages"]), 1)
        self.assertTrue(payload["safety"]["read_only"])
        self.assertFalse(payload["safety"]["execution_allowed"])

    def test_thread_board_does_not_trigger_external_side_effects(self):
        with patch.object(self.app_module, "call_task_provider") as provider_call:
            with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                    response = self.client().get(f"/api/tasks/{self.task['id']}/timeline")
        self.assertEqual(response.status_code, 200)
        provider_call.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
