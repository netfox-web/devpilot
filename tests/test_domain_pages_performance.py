import unittest
from unittest.mock import patch


class DomainPagesPerformanceTest(unittest.TestCase):
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
        self.app_module.clear_domain_page_caches()

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def sample_readiness(self, generated_at="2026-05-11 10:00:00"):
        return {
            "rendered_at": generated_at,
            "generated_at": generated_at,
            "cloudflare_snapshot": {
                "ok": True,
                "source": "cloudflare_read_only",
                "error": "",
            },
            "items": [
                {
                    "group": "DevPilot",
                    "hostname": "devpilot.aicenter.com.tw",
                    "expected_upstream": "devpilot-project-manager :5010",
                    "notes": "test fixture",
                    "dns": {
                        "exists": True,
                        "type": "A",
                        "content": "211.75.219.184",
                        "proxied": False,
                        "ttl": 1,
                        "record_id_masked": "abc****1234",
                        "note": "fixture DNS",
                    },
                    "http": {
                        "ok": True,
                        "status_code": 200,
                        "detail": "responded",
                        "classification": "devpilot",
                        "final_url": "",
                        "url": "http://devpilot.aicenter.com.tw/",
                    },
                    "https": {
                        "ok": True,
                        "status_code": 200,
                        "detail": "responded",
                        "classification": "devpilot",
                        "final_url": "",
                        "url": "https://devpilot.aicenter.com.tw/",
                    },
                    "tls": {
                        "valid": True,
                        "error": "",
                        "common_name": "devpilot.aicenter.com.tw",
                        "san": ["devpilot.aicenter.com.tw"],
                        "not_after": "Jun 1 00:00:00 2026 GMT",
                    },
                    "backend": {
                        "url": "",
                        "ok": False,
                        "status_code": None,
                        "detail": "health url not configured",
                        "latency_ms": None,
                    },
                    "readiness": "ready",
                    "next_step": "no action",
                }
            ],
            "summary": {"ready": 1},
        }

    def fake_cloudflare(self, calls):
        def _fake(method, path, token, payload=None, query=None, timeout=30):
            calls.append(path)
            if path == "/zones":
                return {
                    "ok": True,
                    "data": {
                        "result": [
                            {
                                "id": "zone123",
                                "name": "aicenter.com.tw",
                                "status": "active",
                                "paused": False,
                                "type": "full",
                                "account": {"name": "fixture account"},
                            }
                        ],
                        "result_info": {"count": 1},
                    },
                }
            if path == "/zones/zone123":
                return {
                    "ok": True,
                    "data": {
                        "result": {
                            "id": "zone123",
                            "name": "aicenter.com.tw",
                            "status": "active",
                            "paused": False,
                            "type": "full",
                            "account": {"name": "fixture account"},
                        }
                    },
                }
            if path == "/zones/zone123/dns_records":
                return {
                    "ok": True,
                    "data": {
                        "result": [
                            {
                                "id": "record123",
                                "type": "A",
                                "name": "aicenter.com.tw",
                                "content": "211.75.219.184",
                                "ttl": 1,
                                "proxied": False,
                                "created_on": "2026-05-11T00:00:00Z",
                                "modified_on": "2026-05-11T00:00:00Z",
                            }
                        ],
                        "result_info": {"count": 1},
                    },
                }
            raise AssertionError(f"unexpected Cloudflare path: {path}")

        return _fake

    def test_domain_readiness_route_uses_cache_metadata(self):
        with patch.object(self.app_module, "domain_readiness_context_live", return_value=self.sample_readiness()) as live:
            response = self.client().get("/domain-readiness")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Generated 2026-05-11 10:00:00", text)
        self.assertIn("TTL 60s", text)
        self.assertIn("live", text)
        self.assertEqual(live.call_count, 1)

    def test_domain_action_plan_reuses_readiness_cache(self):
        with patch.object(self.app_module, "domain_readiness_context_live", return_value=self.sample_readiness()) as live:
            readiness_response = self.client().get("/domain-readiness")
            action_response = self.client().get("/domain-action-plan")
        self.assertEqual(readiness_response.status_code, 200)
        self.assertEqual(action_response.status_code, 200)
        self.assertEqual(live.call_count, 1)
        self.assertIn("cached", action_response.get_data(as_text=True))

    def test_refresh_bypasses_readiness_cache(self):
        with patch.object(
            self.app_module,
            "domain_readiness_context_live",
            side_effect=[
                self.sample_readiness("2026-05-11 10:00:00"),
                self.sample_readiness("2026-05-11 10:01:00"),
            ],
        ) as live:
            first = self.client().get("/domain-readiness")
            second = self.client().get("/domain-readiness")
            refreshed = self.client().get("/domain-readiness?refresh=1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(live.call_count, 2)
        self.assertIn("2026-05-11 10:01:00", refreshed.get_data(as_text=True))

    def test_domains_route_does_not_fetch_all_zone_records(self):
        calls = []
        with patch.object(self.app_module, "get_active_cloudflare_api_key", return_value={"ok": True, "token": "fixture"}):
            with patch.object(self.app_module, "cloudflare_request", side_effect=self.fake_cloudflare(calls)):
                response = self.client().get("/domains")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/zones", calls)
        self.assertFalse(any("dns_records" in path for path in calls), calls)
        text = response.get_data(as_text=True)
        self.assertIn("DNS records are loaded only after clicking this button.", text)

    def test_domain_records_endpoint_returns_mocked_records_and_cache_metadata(self):
        calls = []
        with patch.object(self.app_module, "get_active_cloudflare_api_key", return_value={"ok": True, "token": "fixture"}):
            with patch.object(self.app_module, "cloudflare_request", side_effect=self.fake_cloudflare(calls)):
                response = self.client().get("/api/domains/zone123/records")
                cached_response = self.client().get("/api/domains/zone123/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cached_response.status_code, 200)
        payload = response.get_json()
        cached_payload = cached_response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["name"], "aicenter.com.tw")
        self.assertFalse(payload["cache"]["cached"])
        self.assertTrue(cached_payload["cache"]["cached"])
        self.assertEqual(calls.count("/zones/zone123/dns_records"), 1)

    def test_domain_records_refresh_bypasses_cache(self):
        calls = []
        with patch.object(self.app_module, "get_active_cloudflare_api_key", return_value={"ok": True, "token": "fixture"}):
            with patch.object(self.app_module, "cloudflare_request", side_effect=self.fake_cloudflare(calls)):
                first = self.client().get("/api/domains/zone123/records")
                refreshed = self.client().get("/api/domains/zone123/records?refresh=1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(calls.count("/zones/zone123/dns_records"), 2)
        self.assertFalse(refreshed.get_json()["cache"]["cached"])


if __name__ == "__main__":
    unittest.main()
