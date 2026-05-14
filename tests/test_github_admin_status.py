import json
import unittest
from unittest.mock import patch


class GithubAdminStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module
        cls.app = app_module.app
        cls.app.testing = True
        with cls.app.app_context():
            owner = app_module.query_one("SELECT id FROM users WHERE role IN ('owner', 'admin') AND is_active=1 ORDER BY id LIMIT 1")
        cls.user_id = owner["id"]

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def test_get_active_github_api_token_returns_not_configured_without_key(self):
        with patch.object(self.app_module, "query_one", return_value=None):
            result = self.app_module.get_active_github_api_token()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "github_token_not_configured")
        self.assertNotIn("token", result)

    def test_get_active_github_api_token_success_includes_api_key_id(self):
        raw_token = "ghp_" + "e" * 36
        row = {
            "id": 42,
            "name": "GitHub Production",
            "environment": "production",
            "status": "active",
            "encrypted_value": "encrypted-token",
            "masked_value": "ghp****safe",
            "key_mask": "",
        }

        with patch.object(self.app_module, "query_one", return_value=row):
            with patch.object(self.app_module, "decrypt_secret_value", return_value=raw_token):
                result = self.app_module.get_active_github_api_token()

        self.assertTrue(result["ok"])
        self.assertEqual(result["token"], raw_token)
        self.assertEqual(result["api_key_id"], 42)
        self.assertEqual(result["api_key"]["name"], "GitHub Production")
        self.assertEqual(result["api_key"]["environment"], "production")
        self.assertEqual(result["api_key"]["masked"], "ghp****safe")
        self.assertEqual(result["api_key"]["status"], "active")

    def test_github_request_rejects_path_without_leading_slash(self):
        result = self.app_module.github_request("GET", "user", "ghp_" + "a" * 36)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 400)
        self.assertEqual(result["error"], "github_path_must_start_with_slash")

    def test_redact_github_response_text_hides_bearer_and_github_tokens(self):
        bearer_token = "ghp_" + "a" * 36
        pat_token = "github_pat_" + "b" * 80
        raw = f"Authorization: Bearer {bearer_token}; secondary={pat_token}"

        redacted = self.app_module.redact_github_response_text(raw)

        self.assertNotIn(bearer_token, redacted)
        self.assertNotIn(pat_token, redacted)
        self.assertNotIn(f"Bearer {bearer_token}", redacted)
        self.assertIn("[redacted", redacted)

    def test_admin_github_status_returns_safe_metadata_without_raw_token(self):
        raw_token = "ghp_" + "c" * 36
        api_key_meta = {
            "name": "GitHub Production",
            "environment": "production",
            "masked": "ghp****safe",
            "status": "active",
        }
        calls = []

        def fake_github_request(method, path, token, payload=None, query=None, timeout=20):
            self.assertEqual(token, raw_token)
            calls.append((method, path))
            if path == "/user":
                return {"ok": True, "status_code": 200, "json": {"login": "netfox-web", "id": 12345}, "error": None}
            if path == "/rate_limit":
                return {
                    "ok": True,
                    "status_code": 200,
                    "json": {"resources": {"core": {"limit": 5000, "remaining": 4999, "reset": 1900000000}}},
                    "error": None,
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with patch.object(
            self.app_module,
            "get_active_github_api_token",
            return_value={"ok": True, "token": raw_token, "api_key": api_key_meta, "api_key_id": 42},
        ):
            with patch.object(self.app_module, "github_request", side_effect=fake_github_request):
                with patch.object(self.app_module, "record_github_status_check_usage") as usage_record:
                    response = self.client().get("/api/admin/github/status")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["api_key"], api_key_meta)
        self.assertEqual(payload["github"]["login"], "netfox-web")
        self.assertEqual(payload["rate_limit"]["remaining"], 4999)
        self.assertEqual(calls, [("GET", "/user"), ("GET", "/rate_limit")])
        usage_record.assert_called_once_with(42, "success", 200)
        body = response.get_data(as_text=True)
        self.assertNotIn(raw_token, body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("Bearer", body)

    def test_admin_github_status_redacts_github_failure(self):
        raw_token = "ghp_" + "d" * 36
        api_key_meta = {
            "name": "GitHub Production",
            "environment": "production",
            "masked": "ghp****safe",
            "status": "active",
        }

        def fake_github_request(method, path, token, payload=None, query=None, timeout=20):
            return {
                "ok": False,
                "status_code": 403,
                "json": None,
                "error": f"GitHub HTTP 403 Authorization: Bearer {raw_token}",
            }

        with patch.object(
            self.app_module,
            "get_active_github_api_token",
            return_value={"ok": True, "token": raw_token, "api_key": api_key_meta},
        ):
            with patch.object(self.app_module, "github_request", side_effect=fake_github_request):
                response = self.client().get("/api/admin/github/status")

        self.assertEqual(response.status_code, 502, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertNotIn(raw_token, body)
        self.assertNotIn(f"Bearer {raw_token}", body)
        payload = json.loads(body)
        self.assertEqual(payload["status_code"], 403)
        self.assertIn("[redacted]", payload["error"])


if __name__ == "__main__":
    unittest.main()
