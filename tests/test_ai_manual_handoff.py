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
        self.generation_results_path = Path(self.key_store_dir.name) / "external_ai_generation_results.json"
        self.usage_log_path = Path(self.key_store_dir.name) / "external_ai_usage_log.json"
        self.external_project_registry_path = Path(self.key_store_dir.name) / "external_project_registry.json"
        self.external_project_events_path = Path(self.key_store_dir.name) / "external_project_events.json"
        self.approval_objects_path = Path(self.key_store_dir.name) / "approval_objects.json"
        self.key_store_patch = patch.object(self.app_module, "EXTERNAL_API_KEY_STORE_PATH", self.key_store_path)
        self.policy_store_patch = patch.object(self.app_module, "EXTERNAL_AI_POLICY_STORE_PATH", self.policy_store_path)
        self.profile_store_patch = patch.object(self.app_module, "EXTERNAL_AI_PERMISSION_PROFILE_STORE_PATH", self.profile_store_path)
        self.generation_results_patch = patch.object(self.app_module, "EXTERNAL_AI_GENERATION_RESULTS_STORE_PATH", self.generation_results_path)
        self.usage_log_patch = patch.object(self.app_module, "EXTERNAL_AI_USAGE_LOG_STORE_PATH", self.usage_log_path)
        self.external_project_registry_patch = patch.object(self.app_module, "EXTERNAL_PROJECT_REGISTRY_STORE_PATH", self.external_project_registry_path)
        self.external_project_events_patch = patch.object(self.app_module, "EXTERNAL_PROJECT_EVENTS_STORE_PATH", self.external_project_events_path)
        self.approval_objects_patch = patch.object(self.app_module, "APPROVAL_OBJECTS_PATH", self.approval_objects_path)
        self.key_store_env_patch = patch.dict(
            self.app_module.os.environ,
            {
                "DEVPILOT_EXTERNAL_API_KEY_STORE_PATH": str(self.key_store_path),
                "DEVPILOT_EXTERNAL_AI_POLICY_STORE_PATH": str(self.policy_store_path),
                "DEVPILOT_EXTERNAL_AI_PERMISSION_PROFILE_STORE_PATH": str(self.profile_store_path),
                "DEVPILOT_EXTERNAL_AI_GENERATION_RESULTS_PATH": str(self.generation_results_path),
                "DEVPILOT_EXTERNAL_AI_USAGE_LOG_PATH": str(self.usage_log_path),
                "DEVPILOT_EXTERNAL_PROJECT_REGISTRY_PATH": str(self.external_project_registry_path),
                "DEVPILOT_EXTERNAL_PROJECT_EVENTS_PATH": str(self.external_project_events_path),
                "DEVPILOT_APPROVAL_OBJECTS_PATH": str(self.approval_objects_path),
            },
            clear=False,
        )
        self.key_store_patch.start()
        self.policy_store_patch.start()
        self.profile_store_patch.start()
        self.generation_results_patch.start()
        self.usage_log_patch.start()
        self.external_project_registry_patch.start()
        self.external_project_events_patch.start()
        self.approval_objects_patch.start()
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
            self.cleanup_managed_ai_provider_keys()
            self.app_module.execute("DELETE FROM handoff_logs WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM tasks WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM project_phases WHERE project_id=?", (self.project_id,))
            self.app_module.execute("DELETE FROM projects WHERE id=?", (self.project_id,))
        self.key_store_env_patch.stop()
        self.external_project_events_patch.stop()
        self.external_project_registry_patch.stop()
        self.approval_objects_patch.stop()
        self.usage_log_patch.stop()
        self.generation_results_patch.stop()
        self.profile_store_patch.stop()
        self.policy_store_patch.stop()
        self.key_store_patch.stop()
        self.key_store_dir.cleanup()

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def test_ai_provider_readiness_api_is_read_only_and_does_not_call_providers(self):
        env = {
            "GEMINI_API_KEY": "gemini-test-raw-secret-1234",
            "GOOGLE_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": "",
            "ANTHROPIC_API_KEY": "claude-test-raw-secret-5678",
            "CLAUDE_API_KEY": "",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/api/admin/ai-provider-readiness")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["provider_calls_executed"])
        self.assertFalse(payload["live_calls_enabled"])
        self.assertTrue(payload["safety"]["no_live_provider_call"])
        providers = {item["id"]: item for item in payload["providers"]}
        self.assertEqual(set(providers), {"gemini", "claude"})
        self.assertTrue(providers["gemini"]["configured"])
        self.assertTrue(providers["claude"]["configured"])
        self.assertEqual(providers["gemini"]["readiness"], "verified_with_mock")
        self.assertEqual(providers["claude"]["readiness"], "verified_with_mock")
        self.assertTrue(providers["gemini"]["mock_verified"])
        self.assertTrue(providers["claude"]["mock_verified"])
        self.assertFalse(providers["gemini"]["live_verified"])
        self.assertFalse(providers["claude"]["live_verified"])
        self.assertFalse(providers["gemini"]["live_call_enabled"])
        self.assertFalse(providers["claude"]["live_call_enabled"])
        self.assertEqual(providers["gemini"]["allowed_models"], ["gemini-2.5-flash"])
        self.assertEqual(providers["claude"]["allowed_models"], ["claude-haiku-4-5-20251001"])
        combined = json.dumps(payload, sort_keys=True)
        self.assertNotIn("gemini-test-raw-secret-1234", combined)
        self.assertNotIn("claude-test-raw-secret-5678", combined)
        self.assertNotIn("Authorization", combined)
        self.assertNotIn("Bearer", combined)
        self.assertNotIn("key_hash", combined)
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_ai_provider_readiness_page_masks_secrets_and_requires_login(self):
        anonymous = self.app.test_client().get("/admin/ai-provider-readiness")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.headers.get("Location", ""))

        env = {
            "GEMINI_API_KEY": "gemini-page-raw-secret-1234",
            "GOOGLE_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": "",
            "ANTHROPIC_API_KEY": "claude-page-raw-secret-5678",
            "CLAUDE_API_KEY": "",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/admin/ai-provider-readiness")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("AI Provider Readiness", page)
        self.assertIn("Gemini", page)
        self.assertIn("Claude", page)
        self.assertIn("verified_with_mock", page)
        self.assertIn("gemini-2.5-flash", page)
        self.assertIn("claude-haiku-4-5-20251001", page)
        self.assertNotIn("gemini-page-raw-secret-1234", page)
        self.assertNotIn("claude-page-raw-secret-5678", page)
        self.assertNotIn("Authorization", page)
        self.assertNotIn("Bearer", page)
        self.assertNotIn("key_hash", page)
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_ai_provider_readiness_reports_missing_credentials_without_provider_calls(self):
        env = {
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/api/admin/ai-provider-readiness")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        providers = {item["id"]: item for item in response.get_json()["providers"]}
        self.assertFalse(providers["gemini"]["configured"])
        self.assertFalse(providers["claude"]["configured"])
        self.assertEqual(providers["gemini"]["gateway_route_status"], "mock_route_available")
        self.assertEqual(providers["claude"]["gateway_route_status"], "mock_route_available")
        self.assertEqual(providers["gemini"]["masked_preview"], "")
        self.assertEqual(providers["claude"]["masked_preview"], "")
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_external_ai_live_verification_gate_api_is_read_only_and_does_not_call_providers(self):
        env = {
            "GEMINI_API_KEY": "gemini-live-gate-raw-secret-1234",
            "ANTHROPIC_API_KEY": "claude-live-gate-raw-secret-5678",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/api/admin/external-ai-live-verification-gate")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["live_verification_allowed"])
        self.assertFalse(payload["provider_calls_executed"])
        self.assertFalse(payload["approval_objects_created"])
        self.assertFalse(payload["usage_logs_written"])
        self.assertFalse(payload["generation_results_written"])
        self.assertTrue(payload["safety"]["no_live_provider_call"])
        self.assertTrue(payload["safety"]["no_secret_output"])
        providers = {item["id"]: item for item in payload["providers"]}
        self.assertEqual(set(providers), {"gemini", "claude"})
        self.assertEqual(providers["gemini"]["default_model"], "gemini-2.5-flash")
        self.assertEqual(providers["claude"]["default_model"], "claude-haiku-4-5-20251001")
        self.assertTrue(providers["gemini"]["mock_verified"])
        self.assertTrue(providers["claude"]["mock_verified"])
        self.assertFalse(providers["gemini"]["live_verified"])
        self.assertFalse(providers["claude"]["live_verified"])
        self.assertFalse(providers["gemini"]["live_call_enabled"])
        self.assertFalse(providers["claude"]["live_call_enabled"])
        self.assertTrue(providers["gemini"]["one_call_plan_ready"])
        self.assertFalse(providers["claude"]["one_call_plan_ready"])
        self.assertEqual(providers["gemini"]["approval_status"], "not_requested")
        self.assertEqual(providers["gemini"]["constraints"]["max_provider_calls"], 1)
        self.assertFalse(providers["gemini"]["constraints"]["streaming_allowed"])
        self.assertFalse(providers["gemini"]["constraints"]["tool_calling_allowed"])
        self.assertFalse(providers["gemini"]["constraints"]["fallback_allowed"])
        self.assertFalse(providers["gemini"]["constraints"]["retry_allowed"])
        self.assertEqual(providers["gemini"]["fixed_prompt"], "Return exactly OK.")
        approval_ids = {item["id"] for item in payload["global_required_approvals"]}
        self.assertEqual(approval_ids, {"product_owner", "engineering_owner", "operations_owner", "security_reviewer"})
        self.assertTrue(all(item["status"] == "missing" for item in payload["global_required_approvals"]))
        combined = json.dumps(payload, sort_keys=True)
        self.assertNotIn("gemini-live-gate-raw-secret-1234", combined)
        self.assertNotIn("claude-live-gate-raw-secret-5678", combined)
        self.assertNotIn("Authorization:", combined)
        self.assertNotIn("Bearer ", combined)
        self.assertNotIn("key_hash", combined)
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_external_ai_live_verification_gate_page_masks_secrets_and_requires_login(self):
        anonymous = self.app.test_client().get("/admin/external-ai-live-verification-gate")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.headers.get("Location", ""))

        env = {
            "GEMINI_API_KEY": "gemini-live-page-raw-secret-1234",
            "ANTHROPIC_API_KEY": "claude-live-page-raw-secret-5678",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/admin/external-ai-live-verification-gate")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("External AI Live Verification Gate", page)
        self.assertIn("Live verification is not allowed", page)
        self.assertIn("Gemini", page)
        self.assertIn("Claude", page)
        self.assertIn("gemini-2.5-flash", page)
        self.assertIn("claude-haiku-4-5-20251001", page)
        self.assertIn("Product owner approval", page)
        self.assertIn("Return exactly OK.", page)
        self.assertNotIn("gemini-live-page-raw-secret-1234", page)
        self.assertNotIn("claude-live-page-raw-secret-5678", page)
        self.assertNotIn("Authorization:", page)
        self.assertNotIn("Bearer ", page)
        self.assertNotIn("key_hash", page)
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_task_queue_generator_page_requires_login_and_owner_admin_can_preview(self):
        anonymous = self.app.test_client().get("/admin/ai-coding-agent-task-generator")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.headers.get("Location", ""))

        response = self.client().get("/admin/ai-coding-agent-task-generator")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("AI Coding Agent Task Generator", page)
        self.assertIn("PREVIEW ONLY", page)
        self.assertIn("NO EXECUTION", page)
        self.assertIn("NO CODEX CALL", page)
        self.assertNotIn("Authorization", page)
        self.assertNotIn("Bearer", page)
        self.assertNotIn("key_hash", page)

    def test_task_queue_generator_preview_classifies_safe_and_high_risk_requests_without_side_effects(self):
        task_queue_path = self.app_module.BASE_DIR / "docs" / "ai_coding_agent_task_queue.md"
        before_text = task_queue_path.read_text(encoding="utf-8")
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        client = self.client()
        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                with patch.object(self.app_module, "cloudflare_request") as cloudflare_call:
                    with patch.object(self.app_module, "save_ai_task_handoff") as handoff_save:
                        with patch.object(self.app_module, "create_approval_request") as approval_create:
                            with patch.object(self.app_module.subprocess, "run") as subprocess_run:
                                docs_response = client.post("/api/admin/ai-coding-agent-task-generator/preview", json={
                                    "source": "chatgpt",
                                    "title": "Update analyst docs",
                                    "request": "Add a docs-only planning summary.",
                                    "requested_files": ["docs/level_7_safe_ai_automation_scaffold.md"],
                                    "requested_actions": ["docs"],
                                })
                                ui_response = client.post("/api/admin/ai-coding-agent-task-generator/preview", json={
                                    "source": "admin_note",
                                    "title": "Add read-only dashboard preview",
                                    "request": "Design a read-only UI/API preview with tests.",
                                    "requested_files": ["app.py", "templates/example.html", "tests/test_ai_manual_handoff.py"],
                                    "requested_actions": ["read-only dashboard"],
                                })
                                live_response = client.post("/api/admin/ai-coding-agent-task-generator/preview", json={
                                    "source": "approval_object",
                                    "title": "Run live Gemini check",
                                    "request": "Request a live provider Gemini verification call.",
                                    "requested_files": ["docs/external_ai_live_verification_gate.md"],
                                    "requested_actions": ["live provider"],
                                })
                                dns_response = client.post("/api/admin/ai-coding-agent-task-generator/preview", json={
                                    "source": "domain_dry_run",
                                    "title": "DNS deploy request",
                                    "request": "Write DNS records and deploy domain changes.",
                                    "requested_files": ["docs/product_domain_launch_planning_matrix.md"],
                                    "requested_actions": ["dns write", "deploy"],
                                })
                                secret_response = client.post("/api/admin/ai-coding-agent-task-generator/preview", json={
                                    "source": "admin_note",
                                    "title": "Use Authorization Bearer value",
                                    "request": "Use Authorization: Bearer super-secret-token and key_hash=abc",
                                    "requested_files": [".env"],
                                    "requested_actions": ["secret"],
                                })

        for response in (docs_response, ui_response, live_response, dns_response, secret_response):
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["execution_allowed"])
            self.assertFalse(payload["commit_allowed"])
            self.assertFalse(payload["push_allowed"])
            self.assertFalse(payload["task_queue_written"])
            self.assertFalse(payload["codex_called"])
            self.assertFalse(payload["approval_object_created"])
            self.assertTrue(payload["safety"]["no_deploy"])
            self.assertTrue(payload["safety"]["no_provider_live_call"])
            self.assertTrue(payload["safety"]["no_dns_cloudflare_nginx_ssl_r2_mutation"])
            combined = json.dumps(payload, sort_keys=True)
            self.assertNotIn("Authorization", combined)
            self.assertNotIn("Bearer", combined)
            self.assertNotIn("key_hash", combined)
            self.assertNotIn("super-secret-token", combined)

        docs_payload = docs_response.get_json()
        self.assertEqual(docs_payload["classification"], "docs_only")
        self.assertEqual(docs_payload["risk_level"], "low")
        self.assertFalse(docs_payload["requires_approval"])
        self.assertIn("- [ ]", docs_payload["task_queue_patch"])
        self.assertIn("Execution mode: docs_only", docs_payload["task_queue_patch"])

        ui_payload = ui_response.get_json()
        self.assertEqual(ui_payload["classification"], "read_only_ui")
        self.assertEqual(ui_payload["risk_level"], "medium")

        live_payload = live_response.get_json()
        self.assertEqual(live_payload["classification"], "approval_draft_only")
        self.assertEqual(live_payload["risk_level"], "high")
        self.assertTrue(live_payload["requires_approval"])
        self.assertIn("Execution mode: approval_draft_only", live_payload["task_queue_patch"])

        dns_payload = dns_response.get_json()
        self.assertEqual(dns_payload["classification"], "approval_draft_only")
        self.assertEqual(dns_payload["risk_level"], "high")
        self.assertTrue(dns_payload["requires_approval"])

        secret_payload = secret_response.get_json()
        self.assertEqual(secret_payload["classification"], "blocked")
        self.assertEqual(secret_payload["risk_level"], "critical")
        self.assertTrue(secret_payload["requires_approval"])

        self.assertEqual(before_text, task_queue_path.read_text(encoding="utf-8"))
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_before, approval_count_after)
        gemini_call.assert_not_called()
        claude_call.assert_not_called()
        cloudflare_call.assert_not_called()
        handoff_save.assert_not_called()
        approval_create.assert_not_called()
        subprocess_run.assert_not_called()

    def test_approval_object_draft_persistence_is_draft_only_and_isolated(self):
        self.assertFalse(self.approval_objects_path.exists())
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                with patch.object(self.app_module, "cloudflare_request") as cloudflare_call:
                    with patch.object(self.app_module, "create_approval_request") as approval_create:
                        response = self.client().post("/api/admin/approval-objects/draft", json={
                            "type": "external_ai_live_verification",
                            "title": "Persist Gemini live verification draft",
                            "source_surface": "/admin/external-ai-live-verification-gate",
                            "risk_level": "high",
                            "target": {"provider": "gemini", "model": "gemini-2.5-flash"},
                            "dry_run_snapshot": {"preview_only": True},
                        })

        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["approval_object_created"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["provider_calls_executed"])
        self.assertFalse(payload["approval_request_created"])
        self.assertFalse(payload["usage_logs_written"])
        self.assertFalse(payload["generation_results_written"])
        record = payload["approval_object"]
        self.assertTrue(record["id"].startswith("approval_"))
        self.assertEqual(record["type"], "external_ai_live_verification")
        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["risk_level"], "high")
        self.assertFalse(record["execution_allowed"])
        self.assertEqual(record["execution_mode"], "none")
        self.assertTrue(record["approval_object_created"])
        self.assertIsNone(record["execution_result"])
        roles = {item["role"] for item in record["required_approvals"]}
        self.assertEqual(roles, {"product_owner", "engineering_owner", "operations_owner", "security_reviewer"})
        self.assertTrue(all(item["status"] == "missing" for item in record["required_approvals"]))
        self.assertEqual(record["audit_events"][0]["event"], "draft_created")
        self.assertIn("No execution", record["audit_events"][0]["summary"])
        combined = json.dumps(payload, sort_keys=True)
        self.assertNotIn("Authorization", combined)
        self.assertNotIn("Bearer", combined)
        self.assertNotIn("key_hash", combined)
        self.assertTrue(self.approval_objects_path.exists())

        list_response = self.client().get("/api/admin/approval-objects")
        self.assertEqual(list_response.status_code, 200, list_response.get_data(as_text=True))
        list_payload = list_response.get_json()
        self.assertTrue(list_payload["read_only"])
        self.assertFalse(list_payload["execution_allowed"])
        self.assertEqual(list_payload["count"], 1)
        self.assertEqual(list_payload["approval_objects"][0]["id"], record["id"])

        detail_response = self.client().get(f"/api/admin/approval-objects/{record['id']}")
        self.assertEqual(detail_response.status_code, 200, detail_response.get_data(as_text=True))
        self.assertEqual(detail_response.get_json()["approval_object"]["id"], record["id"])

        missing_response = self.client().get("/api/admin/approval-objects/missing")
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.get_json()["error"], "approval_object_not_found")

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_before, approval_count_after)
        self.assertFalse(self.generation_results_path.exists())
        self.assertFalse(self.usage_log_path.exists())
        gemini_call.assert_not_called()
        claude_call.assert_not_called()
        cloudflare_call.assert_not_called()
        approval_create.assert_not_called()

    def test_approval_object_draft_rejects_sensitive_payload_without_persisting(self):
        response = self.client().post("/api/admin/approval-objects/draft", json={
            "type": "external_ai_live_verification",
            "title": "Authorization Bearer fake-secret",
            "source_surface": "/admin/external-ai-live-verification-gate",
            "risk_level": "critical",
            "target": {"provider": "gemini", "api_key": "fake-secret"},
            "dry_run_snapshot": {"key_hash": "abc123"},
        })

        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "approval_payload_contains_sensitive_marker")
        self.assertFalse(payload["approval_object_created"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(self.approval_objects_path.exists())
        combined = json.dumps(payload, sort_keys=True)
        self.assertNotIn("fake-secret", combined)
        self.assertNotIn("Bearer", combined)
        self.assertNotIn("key_hash", combined)

    def test_approval_objects_pages_require_login_and_render_drafts(self):
        anonymous = self.app.test_client().get("/admin/approval-objects")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.headers.get("Location", ""))

        create_response = self.client().post("/api/admin/approval-objects/draft", json={
            "type": "domain_execution",
            "title": "Persist domain execution draft",
            "source_surface": "/admin/domain-execution-dry-run",
            "risk_level": "critical",
            "target": {"domain": "aioffice.com.tw"},
            "dry_run_snapshot": {"planned_dns_records": 27},
        })
        record = create_response.get_json()["approval_object"]

        list_page = self.client().get("/admin/approval-objects")
        self.assertEqual(list_page.status_code, 200, list_page.get_data(as_text=True))
        list_body = list_page.get_data(as_text=True)
        self.assertIn("Approval Objects", list_body)
        self.assertIn(record["id"], list_body)
        self.assertIn("DRAFTS ONLY", list_body)
        self.assertIn("execution_allowed=false", list_body)

        detail_page = self.client().get(f"/admin/approval-objects/{record['id']}")
        self.assertEqual(detail_page.status_code, 200, detail_page.get_data(as_text=True))
        detail_body = detail_page.get_data(as_text=True)
        self.assertIn("Approval Object Detail", detail_body)
        self.assertIn("DRAFT ONLY", detail_body)
        self.assertIn("dns_cloudflare_owner", detail_body)
        self.assertNotIn("Authorization", detail_body)
        self.assertNotIn("Bearer", detail_body)
        self.assertNotIn("key_hash", detail_body)

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

    def create_managed_ai_provider_key(self, provider, key_value):
        with self.app.app_context():
            return self.app_module.create_api_key_record({
                "name": f"{self.marker}-{provider}",
                "category": "ai",
                "provider": provider,
                "environment": "staging",
                "status": "active",
                "key_value": key_value,
                "source": "test",
                "notes": self.marker,
                "ai_allowed": True,
            })

    def cleanup_managed_ai_provider_keys(self):
        with self.app.app_context():
            rows = self.app_module.query_all("SELECT id FROM api_keys WHERE notes=?", (self.marker,))
            for row in rows:
                key_id = row["id"]
                self.app_module.execute("DELETE FROM api_key_audit_logs WHERE api_key_id=?", (key_id,))
                self.app_module.execute("DELETE FROM api_key_versions WHERE api_key_id=?", (key_id,))
                self.app_module.execute("DELETE FROM api_keys WHERE id=?", (key_id,))

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
                            "allowed_models": ["gpt-4.1-mini", "gemini-2.5-flash"],
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
                            "allowed_models": "gemini-2.5-flash",
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
        self.assertEqual(policies["grouped-model-source"]["allowed_models"], ["gpt-4.1-mini", "gemini-2.5-flash"])

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
        self.assertEqual(profiles["text-multi-provider"]["allowed_models"], ["gpt-4.1-mini", "gemini-2.5-flash", "claude-haiku-4-5-20251001"])
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
        self.assertEqual(policies["profile-b"]["allowed_models"], ["gpt-4.1-mini", "gemini-2.5-flash", "claude-haiku-4-5-20251001"])

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
        self.assertIn("Models are selected per provider. Check a provider first to enable its model boxes.", page_body)
        self.assertIn('data-model-provider="openai"', page_body)
        self.assertIn('data-model-provider="gemini"', page_body)
        self.assertIn('data-provider-model="openai"', page_body)
        self.assertIn('data-provider-model="fal"', page_body)
        self.assertIn('value="gpt-4.1-mini" data-provider-model="openai" checked', page_body)
        self.assertIn('value="gemini-2.5-flash" data-provider-model="gemini" checked', page_body)
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
            "allowed_models": ["gpt-4.1-mini", "gemini-2.5-flash", "claude-haiku-4-5-20251001", "flux-schnell", "fal-flux-pro"],
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
            "allowed_models": ["gpt-4.1-mini", "gemini-2.5-flash"],
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
            ({"id": "bad-mismatch", "name": "Bad Mismatch", "allowed_providers": ["openai"], "allowed_models": ["gemini-2.5-flash"]}, "model/provider mismatch"),
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

    def test_integration_toolbox_page_and_downloads_are_safe(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        key_response = self.client().post(
            "/api/admin/external-api-keys",
            json={"source_system": "toolbox-source", "label": "Toolbox source label"},
        )
        self.assertEqual(key_response.status_code, 201, key_response.get_data(as_text=True))
        raw_key = key_response.get_json()["api_key"]
        key_hash = json.loads(self.key_store_path.read_text(encoding="utf-8"))["keys"][0]["key_hash"]

        unauthenticated = self.app.test_client().get("/admin/integration-toolbox")
        unauthenticated_download = self.app.test_client().get("/admin/integration-toolbox/download/devpilot-env-template")
        self.assertEqual(unauthenticated.status_code, 302)
        self.assertEqual(unauthenticated_download.status_code, 302)

        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            page = self.client().get("/admin/integration-toolbox")
                            doc_download = self.client().get("/admin/integration-toolbox/download/devpilot-integration-settings-spec")
                            admin_instructions_download = self.client().get(
                                "/admin/integration-toolbox/download/external-project-admin-integration-instructions"
                            )
                            registry_download = self.client().get("/admin/integration-toolbox/download/external-project-registry-api")
                            js_download = self.client().get("/admin/integration-toolbox/download/devpilot-js-client-example")
                            py_download = self.client().get("/admin/integration-toolbox/download/devpilot-python-client-example")
                            env_download = self.client().get("/admin/integration-toolbox/download/devpilot-env-template")
                            unknown = self.client().get("/admin/integration-toolbox/download/not-real")
                            traversal = self.client().get("/admin/integration-toolbox/download/..%2Fapp.py")

        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))
        page_body = page.get_data(as_text=True)
        for expected in (
            "Integration Toolbox",
            "DevPilot Integration Settings Spec",
            "External Project Admin Integration Instructions",
            "External Project Registry API",
            "External API Onboarding Admin Guide",
            "External AI Gateway Plan",
            "External AI Gateway Admin Guide",
            "External Project Communication Plan",
            "JS client example",
            "Python client example",
            ".env template",
        ):
            self.assertIn(expected, page_body)
        self.assertNotIn(raw_key, page_body)
        self.assertNotIn(key_hash, page_body)
        self.assertNotIn("key_hash", page_body)

        for response in (doc_download, admin_instructions_download, registry_download, js_download, py_download, env_download):
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            self.assertIn("attachment", response.headers.get("Content-Disposition", ""))

        self.assertIn("DevPilot Integration", doc_download.get_data(as_text=True))
        admin_instructions_body = admin_instructions_download.get_data(as_text=True)
        self.assertIn("/admin/integrations/devpilot", admin_instructions_body)
        self.assertIn("DEVPILOT_API_KEY", admin_instructions_body)
        self.assertIn("<paste-the-key-shown-once>", admin_instructions_body)
        self.assertIn("Never show the full key again", admin_instructions_body)
        self.assertIn("GET /api/external/projects", admin_instructions_body)
        self.assertIn("POST /api/external/projects/register", admin_instructions_body)
        self.assertIn("POST /api/external/projects/<external_project_id>/events", admin_instructions_body)
        self.assertIn("register project metadata", registry_download.get_data(as_text=True))

        js_body = js_download.get_data(as_text=True)
        self.assertIn("DEVPILOT_API_KEY", js_body)
        self.assertIn("<paste-the-key-shown-once>", js_body)
        self.assertIn("AbortController", js_body)
        self.assertIn("crypto.randomUUID", js_body)
        self.assertIn("generateAiText", js_body)
        self.assertIn("/api/external/ai/generate", js_body)
        self.assertIn("Never expose DEVPILOT_API_KEY", js_body)

        py_body = py_download.get_data(as_text=True)
        self.assertIn("DEVPILOT_API_KEY", py_body)
        self.assertIn("<paste-the-key-shown-once>", py_body)
        self.assertIn("requests.request", py_body)
        self.assertIn("timeout=TIMEOUT_SECONDS", py_body)
        self.assertIn("generate_ai_text", py_body)
        self.assertIn("/api/external/ai/generate", py_body)
        self.assertIn("Never print or log DEVPILOT_API_KEY", py_body)

        env_body = env_download.get_data(as_text=True)
        self.assertIn("DEVPILOT_API_BASE_URL=", env_body)
        self.assertIn("DEVPILOT_SOURCE_SYSTEM=", env_body)
        self.assertIn("DEVPILOT_API_KEY=", env_body)
        self.assertIn("EXTERNAL_PROJECT_ID=", env_body)

        combined_generated = "\n".join((admin_instructions_body, js_body, py_body, env_body))
        self.assertNotIn(raw_key, combined_generated)
        self.assertNotIn(key_hash, combined_generated)
        self.assertNotIn("key_hash", combined_generated)
        self.assertNotIn("sk-test", combined_generated)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(traversal.status_code, 404)

        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_integration_diagnostics_is_read_only_and_secret_safe(self):
        active_record, raw_key = self.app_module.generate_external_api_key("diagnostic-source", "Diagnostic source")
        revoked_record, revoked_key = self.app_module.generate_external_api_key("diagnostic-source", "Old diagnostic source")
        self.app_module.revoke_external_api_key(revoked_record["id"])
        store_text = self.key_store_path.read_text(encoding="utf-8")
        stored_hashes = [item["key_hash"] for item in json.loads(store_text)["keys"]]
        self.app_module.save_external_project_registry_records([
            {
                "source_system": "diagnostic-source",
                "external_project_id": "diagnostic-project",
                "name": "Diagnostic Project",
                "project_type": "ai-saas",
                "environment": "production",
                "status": "active",
                "app_url": "https://diagnostic.example.com",
                "primary_domain": "diagnostic.example.com",
                "created_at": "2026-05-13 10:00:00",
                "updated_at": "2026-05-13 10:00:00",
                "last_seen_at": "2026-05-13 10:00:00",
            }
        ])
        self.app_module.save_external_project_event_records([
            {
                "source_system": "diagnostic-source",
                "external_project_id": "diagnostic-project",
                "event_type": "healthcheck_ok",
                "status": "success",
                "message": "Diagnostic event",
                "environment": "production",
                "created_at": "2026-05-13 10:05:00",
            }
        ])
        self.app_module.save_external_ai_usage_log_records([
            {
                "id": "diagnostic-usage",
                "source_system": "diagnostic-source",
                "request_id": "diag-req",
                "idempotency_key": "diag-usage",
                "external_ref": "diag-ref",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "input_chars": 11,
                "output_chars": 22,
                "prompt_hash": "diag-prompt-hash",
                "prompt_summary": "Diagnostic safe prompt summary",
                "response_hash": "diag-response-hash",
                "response_summary": "Diagnostic safe response summary",
                "created_at": "2026-05-13 10:10:00",
            }
        ])
        with self.app.app_context():
            now = self.app_module.now_str()
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
            self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "external-api",
                    "diagnostic-source",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "medium",
                    "Diagnostic handoff reason",
                    "Diagnostic handoff next step",
                    "",
                    json.dumps({
                        "record_type": "ai_task_handoff",
                        "source_system": "diagnostic-source",
                        "external_ref": "diagnostic-handoff",
                        "from_agent": "diagnostic-source",
                        "to_agent": "devpilot-reviewer",
                        "reason": "Diagnostic handoff reason",
                        "next_step": "Diagnostic handoff next step",
                        "status": "pending",
                        "risk_level": "medium",
                        "api_key": raw_key,
                    }),
                    now,
                ),
            )
        before = self.state_snapshot()

        unauthenticated = self.app.test_client().get("/admin/external-integration-diagnostics")
        self.assertEqual(unauthenticated.status_code, 302)
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": "diagnostic-env:env-secret-value"}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                overview = self.client().get("/admin/external-integration-diagnostics")
                                response = self.client().get("/admin/external-integration-diagnostics?source_system=diagnostic-source")
                                unknown = self.client().get("/admin/external-integration-diagnostics?source_system=missing-source")

        self.assertEqual(overview.status_code, 200, overview.get_data(as_text=True))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(unknown.status_code, 200, unknown.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("External Integration Diagnostics", page)
        self.assertIn("/admin/external-integration-diagnostics", page)
        self.assertIn("diagnostic-source", page)
        self.assertIn(active_record["key_prefix"], page)
        self.assertIn(revoked_record["key_prefix"], page)
        self.assertIn("active", page)
        self.assertIn("revoked", page)
        self.assertIn("Diagnostic Project", page)
        self.assertIn("healthcheck_ok", page)
        self.assertIn("Diagnostic handoff reason", page)
        self.assertIn("Diagnostic safe prompt summary", page)
        self.assertIn("external source system is not allowed", page)
        self.assertIn("external API credential is invalid", page)
        self.assertIn("provider_not_configured", page)
        self.assertIn("external_ai_gateway_not_enabled", page)
        self.assertIn("DEVPILOT_API_BASE_URL", page)
        self.assertIn("DEVPILOT_SOURCE_SYSTEM", page)
        self.assertIn("DEVPILOT_API_KEY", page)
        self.assertIn("EXTERNAL_PROJECT_ID", page)
        self.assertIn("&lt;paste-devpilot-external-api-key&gt;", page)
        self.assertNotIn(raw_key, page)
        self.assertNotIn(revoked_key, page)
        self.assertNotIn("env-secret-value", overview.get_data(as_text=True))
        self.assertNotIn("env-secret-value", page)
        for stored_hash in stored_hashes:
            self.assertNotIn(stored_hash, page)
        self.assertNotIn("key_hash", page)
        self.assertIn("Source system", unknown.get_data(as_text=True))
        self.assertIn("was not found", unknown.get_data(as_text=True))
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_source_detail_page_is_read_only_and_secret_safe(self):
        active_record, raw_key = self.app_module.generate_external_api_key("source-detail", "Source detail key")
        revoked_record, revoked_key = self.app_module.generate_external_api_key("source-detail", "Old source detail key")
        self.app_module.revoke_external_api_key(revoked_record["id"])
        store_text = self.key_store_path.read_text(encoding="utf-8")
        stored_hashes = [item["key_hash"] for item in json.loads(store_text)["keys"]]
        self.app_module.create_external_ai_policy({
            "source_system": "source-detail",
            "profile_id": "text-multi-provider",
            "label": "Source Detail Policy",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary", "rewrite"],
            "daily_request_limit": 100,
            "daily_token_limit": 1000,
            "monthly_budget_usd": 10,
        })
        self.app_module.save_external_project_registry_records([
            {
                "source_system": "source-detail",
                "external_project_id": "source-detail-project",
                "name": "Source Detail Project",
                "project_type": "ai-saas",
                "environment": "production",
                "status": "active",
                "app_url": "https://source-detail.example.com",
                "primary_domain": "source-detail.example.com",
                "created_at": "2026-05-13 11:00:00",
                "updated_at": "2026-05-13 11:00:00",
                "last_seen_at": "2026-05-13 11:00:00",
            }
        ])
        self.app_module.save_external_project_event_records([
            {
                "source_system": "source-detail",
                "external_project_id": "source-detail-project",
                "event_type": "deploy_success",
                "status": "success",
                "message": "Source detail deploy event",
                "environment": "production",
                "created_at": "2026-05-13 11:05:00",
            }
        ])
        self.app_module.save_external_ai_usage_log_records([
            {
                "id": "source-detail-usage",
                "source_system": "source-detail",
                "request_id": "source-detail-req",
                "idempotency_key": "source-detail-usage",
                "external_ref": "source-detail-ref",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "input_chars": 33,
                "output_chars": 44,
                "latency_ms": 55,
                "prompt_hash": "source-detail-prompt-hash",
                "prompt_summary": "Source detail safe prompt summary",
                "response_hash": "source-detail-response-hash",
                "response_summary": "Source detail safe response summary",
                "created_at": "2026-05-13 11:10:00",
            }
        ])
        with self.app.app_context():
            now = self.app_module.now_str()
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
            self.app_module.execute(
                """INSERT INTO handoff_logs
                   (project_id, source, agent_name, work_mode, conversation_ref, risk_level, summary, next_steps, warnings, api_payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.project_id,
                    "external-api",
                    "source-detail",
                    "ai-task-handoff",
                    f"ai-task:{self.task['id']}",
                    "medium",
                    "Source detail handoff reason",
                    "Source detail handoff next step",
                    "",
                    json.dumps({
                        "record_type": "ai_task_handoff",
                        "source_system": "source-detail",
                        "external_ref": "source-detail-handoff",
                        "reason": "Source detail handoff reason",
                        "next_step": "Source detail handoff next step",
                        "status": "pending",
                        "api_key": raw_key,
                    }),
                    now,
                ),
            )
        before = self.state_snapshot()

        unauthenticated = self.app.test_client().get("/admin/external-sources/source-detail")
        self.assertEqual(unauthenticated.status_code, 302)
        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            index = self.client().get("/admin/external-sources")
                            detail = self.client().get("/admin/external-sources/source-detail")
                            unknown = self.client().get("/admin/external-sources/missing-source")
                            diagnostics = self.client().get("/admin/external-integration-diagnostics?source_system=source-detail")

        self.assertEqual(index.status_code, 200, index.get_data(as_text=True))
        self.assertEqual(detail.status_code, 200, detail.get_data(as_text=True))
        self.assertEqual(unknown.status_code, 200, unknown.get_data(as_text=True))
        self.assertEqual(diagnostics.status_code, 200, diagnostics.get_data(as_text=True))
        page = detail.get_data(as_text=True)
        self.assertIn("External Source Detail", page)
        self.assertIn("source-detail", page)
        self.assertIn(active_record["key_prefix"], page)
        self.assertIn(revoked_record["key_prefix"], page)
        self.assertIn("Source Detail Policy", page)
        self.assertIn("gemini-2.5-flash", page)
        self.assertIn("summary, rewrite", page)
        self.assertIn("Source Detail Project", page)
        self.assertIn("deploy_success", page)
        self.assertIn("Source detail handoff reason", page)
        self.assertIn("Source detail safe prompt summary", page)
        self.assertIn("Diagnostics Summary", page)
        self.assertIn("Safe Env Snippet", page)
        self.assertIn("Safe Curl Snippets", page)
        self.assertIn("&lt;paste-devpilot-external-api-key&gt;", page)
        self.assertIn("/admin/external-integration-diagnostics?source_system=source-detail", page)
        self.assertIn("/admin/external-projects?source_system=source-detail", page)
        self.assertIn("/admin/external-ai-usage?source_system=source-detail", page)
        self.assertIn("/admin/external-sources/source-detail", diagnostics.get_data(as_text=True))
        self.assertIn("Source system", unknown.get_data(as_text=True))
        self.assertIn("was not found", unknown.get_data(as_text=True))
        self.assertNotIn(raw_key, page)
        self.assertNotIn(revoked_key, page)
        for stored_hash in stored_hashes:
            self.assertNotIn(stored_hash, page)
        self.assertNotIn("key_hash", page)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
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

    def test_ai_provider_secrets_page_is_env_only_masked_and_read_only(self):
        before = self.state_snapshot()
        raw_openai = "sk-test-openai-secret-value"
        raw_gemini = "gemini-test-secret-value"
        raw_claude = "anthropic-test-secret-value"
        env = {
            "OPENAI_API_KEY": raw_openai,
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": raw_gemini,
            "ANTHROPIC_API_KEY": raw_claude,
            "CLAUDE_API_KEY": "",
        }
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        with patch.dict(self.app_module.os.environ, env, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                response = self.client().get("/admin/ai-provider-secrets")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("AI Provider Secrets", page)
        self.assertIn("OPENAI_API_KEY", page)
        self.assertIn("GOOGLE_GENERATIVE_AI_API_KEY", page)
        self.assertIn("ANTHROPIC_API_KEY", page)
        self.assertIn("sk-tes...alue", page)
        self.assertIn("gemini...alue", page)
        self.assertIn("anthro...alue", page)
        self.assertIn("DevPilot External API Keys authenticate external projects", page)
        self.assertIn("This page only inspects runtime env and does not store secrets", page)
        self.assertIn("/admin/ai-provider-secrets", page)
        self.assertNotIn(raw_openai, page)
        self.assertNotIn(raw_gemini, page)
        self.assertNotIn(raw_claude, page)
        self.assertNotIn("Authorization:", page)
        self.assertNotIn("key_hash", page)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_ai_provider_secrets_page_shows_missing_state_and_requires_auth(self):
        env = {
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
        }
        with patch.dict(self.app_module.os.environ, env, clear=False):
            page = self.client().get("/admin/ai-provider-secrets")
            anonymous = self.app.test_client().get("/admin/ai-provider-secrets")

        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))
        body = page.get_data(as_text=True)
        self.assertIn("not configured", body)
        self.assertIn("OpenAI provider key is not configured in runtime env.", body)
        self.assertIn("Gemini provider key is not configured in runtime env.", body)
        self.assertIn("Claude provider key is not configured in runtime env.", body)
        self.assertEqual(anonymous.status_code, 302)

    def test_automation_planner_admin_page_is_read_only_and_lists_context(self):
        from services import automation_plans

        before = self.state_snapshot()
        plan_store_path = Path(self.key_store_dir.name) / "automation_plans.json"
        self.app_module.upsert_external_project_registry_record(
            "planner-source",
            {
                "external_project_id": "planner-project",
                "name": "Planner Project",
                "project_type": "ai-saas",
                "environment": "production",
                "status": "active",
                "app_url": "https://planner.example.test",
                "primary_domain": "planner.example.test",
            },
        )
        self.app_module.create_external_project_event(
            "planner-source",
            "planner-project",
            {
                "event_type": "healthcheck_ok",
                "status": "success",
                "message": "Planner source healthcheck passed.",
                "environment": "production",
            },
        )
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(plan_store_path)}, clear=False):
            created_plan = automation_plans.create_automation_plan({
                "source_system": "planner-source",
                "external_project_id": "planner-project",
                "title": "Review planner source",
                "objective": "Inspect current external source context.",
                "risk_level": "low",
                "recommended_actions": [],
                "required_approvals": [],
                "blocked_by": [],
                "safety_checks": [{"name": "No execution", "status": "pass", "details": "Planning only."}],
                "suggested_commands": [
                    {
                        "label": "Display healthcheck",
                        "command": "curl -I https://planner.example.test",
                        "execution_allowed": True,
                    }
                ],
                "affected_systems": [{"type": "external_project", "name": "planner-project", "impact": "Read-only planning view."}],
            })

            with self.app.app_context():
                approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                response = self.client().get("/admin/automation-planner?source_system=planner-source&external_project_id=planner-project")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("Automation Planner", page)
        self.assertIn("MVP planning only / no execution", page)
        self.assertIn("Suggested commands are display-only", page)
        self.assertIn("Source system", page)
        self.assertIn("External project", page)
        self.assertIn("planner-source", page)
        self.assertIn("planner-project", page)
        self.assertIn("Planner Project", page)
        self.assertIn("healthcheck_ok", page)
        self.assertIn("Existing Draft Plans", page)
        self.assertIn(created_plan["title"], page)
        self.assertIn("Approval integration is planned but disabled in this MVP.", page)
        self.assertIn("request: not created", page)
        self.assertIn("execution_allowed=false", page)
        self.assertIn("/admin/automation-planner", page)
        self.assertNotIn(">Execute<", page)
        self.assertNotIn("name=\"execute\"", page)
        self.assertNotIn("Request Approval", page)
        self.assertNotIn("name=\"approve\"", page)
        self.assertNotIn("Authorization:", page)
        self.assertNotIn("key_hash", page)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_automation_planner_handles_missing_and_malformed_plan_store(self):
        missing_store_path = Path(self.key_store_dir.name) / "missing_automation_plans.json"
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(missing_store_path)}, clear=False):
            missing = self.client().get("/admin/automation-planner")

        self.assertEqual(missing.status_code, 200, missing.get_data(as_text=True))
        self.assertIn("No draft automation plans found.", missing.get_data(as_text=True))

        malformed_store_path = Path(self.key_store_dir.name) / "malformed_automation_plans.json"
        malformed_store_path.write_text("{not-json", encoding="utf-8")
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(malformed_store_path)}, clear=False):
            malformed = self.client().get("/admin/automation-planner")

        self.assertEqual(malformed.status_code, 200, malformed.get_data(as_text=True))
        body = malformed.get_data(as_text=True)
        self.assertIn("Plan store could not be read safely", body)
        self.assertIn("No draft automation plans found.", body)

    def test_automation_planner_requires_auth_and_has_no_post_or_api_endpoint(self):
        anonymous = self.app.test_client().get("/admin/automation-planner")
        self.assertEqual(anonymous.status_code, 302)

        routes = {rule.rule: rule.methods for rule in self.app.url_map.iter_rules()}
        self.assertIn("/admin/automation-planner", routes)
        self.assertNotIn("POST", routes["/admin/automation-planner"])
        self.assertNotIn("/api/admin/automation-plans", routes)
        self.assertNotIn("/api/admin/automation-plans/draft", routes)
        self.assertNotIn("/api/admin/automation-plans/approval", routes)
        self.assertNotIn("/admin/automation-planner/approval", routes)

    def test_automation_planner_draft_generator_creates_low_risk_plan_from_context(self):
        from services import automation_plans

        active_record, raw_key = self.app_module.generate_external_api_key("gpcarai", "GPCarai live loop")
        project, created = self.app_module.upsert_external_project_registry_record(
            "gpcarai",
            {
                "external_project_id": "gpcarai-prod",
                "name": "GPCarai Dispatch",
                "project_type": "ai-saas",
                "environment": "production",
                "status": "active",
                "app_url": "https://go.carai.tw",
                "primary_domain": "go.carai.tw",
                "runtime": "python/docker",
                "container_name": "gkh-dispatch",
                "compose_project": "gkh-dispatch",
                "service_name": "gkh-dispatch",
                "host_port": "5011",
            },
        )
        self.assertTrue(created)
        self.app_module.create_external_project_event(
            "gpcarai",
            "gpcarai-prod",
            {
                "event_type": "healthcheck_ok",
                "status": "success",
                "message": "External project can reach DevPilot integration endpoint.",
                "environment": "production",
                "app_url": "https://go.carai.tw",
            },
        )
        plan_store_path = Path(self.key_store_dir.name) / "automation_plans.json"
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(plan_store_path)}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                with self.app.app_context():
                                    plan = self.app_module.generate_automation_plan_from_context("gpcarai", "gpcarai-prod")
                                    stored_plans = automation_plans.list_automation_plans()

        self.assertEqual(plan["source_system"], "gpcarai")
        self.assertEqual(plan["external_project_id"], "gpcarai-prod")
        self.assertEqual(plan["risk_level"], "low")
        self.assertEqual(plan["status"], "draft")
        self.assertFalse(plan["blocked_by"])
        self.assertEqual(plan["required_approvals"], [])
        self.assertTrue(plan["id"])
        self.assertTrue(plan["created_at"])
        self.assertEqual(len(stored_plans), 1)
        self.assertEqual(stored_plans[0]["id"], plan["id"])
        self.assertIn("GPCarai Dispatch", plan["title"])
        self.assertTrue(any(item["name"] == "Recent events" and item["status"] == "pass" for item in plan["safety_checks"]))
        self.assertTrue(any("healthcheck" in item["description"] for item in plan["recommended_actions"]))
        self.assertTrue(plan["suggested_commands"])
        self.assertTrue(all(command["execution_allowed"] is False for command in plan["suggested_commands"]))

        combined = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn(raw_key, combined)
        self.assertNotIn(active_record["key_hash"], combined)
        self.assertNotIn("key_hash", combined)
        self.assertNotIn("Authorization:", combined)
        self.assertNotIn("Bearer ", combined)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_automation_planner_draft_generator_blocks_unknown_source_and_missing_project(self):
        from services import automation_plans

        self.app_module.generate_external_api_key("known-generator-source", "Known generator source")
        plan_store_path = Path(self.key_store_dir.name) / "automation_plans_blocked.json"
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(plan_store_path)}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                with self.app.app_context():
                                    unknown = self.app_module.generate_automation_plan_from_context("missing-generator-source", "missing-project")
                                    missing_project = self.app_module.generate_automation_plan_from_context("known-generator-source", "missing-project")
                                    stored_plans = automation_plans.list_automation_plans()

        self.assertEqual(unknown["risk_level"], "blocked")
        self.assertIn("source_system was not found in external integration context", unknown["blocked_by"])
        self.assertIn("external project was not found", unknown["blocked_by"])
        self.assertEqual(missing_project["risk_level"], "blocked")
        self.assertIn("external project was not found", missing_project["blocked_by"])
        self.assertTrue(all(command["execution_allowed"] is False for command in unknown["suggested_commands"]))
        self.assertTrue(all(command["execution_allowed"] is False for command in missing_project["suggested_commands"]))
        self.assertEqual(len(stored_plans), 2)

        combined = json.dumps(stored_plans, ensure_ascii=False)
        self.assertNotIn("key_hash", combined)
        self.assertNotIn("Authorization:", combined)
        self.assertNotIn("Bearer ", combined)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_automation_planner_draft_generator_handles_missing_and_malformed_store(self):
        missing_store_path = Path(self.key_store_dir.name) / "missing_generator_plans.json"
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(missing_store_path)}, clear=False):
            with self.app.app_context():
                missing_store_plan = self.app_module.generate_automation_plan_from_context("missing-store-source")

        self.assertEqual(missing_store_plan["risk_level"], "blocked")
        self.assertTrue(missing_store_path.exists())

        malformed_store_path = Path(self.key_store_dir.name) / "malformed_generator_plans.json"
        malformed_store_path.write_text("{not-json", encoding="utf-8")
        with patch.dict(self.app_module.os.environ, {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(malformed_store_path)}, clear=False):
            with self.app.app_context():
                malformed_store_plan = self.app_module.generate_automation_plan_from_context("malformed-store-source")

        self.assertEqual(malformed_store_plan["risk_level"], "blocked")
        body = malformed_store_path.read_text(encoding="utf-8")
        self.assertIn("\"plans\"", body)
        self.assertNotIn("key_hash", body)

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
        self.assertIn("Control which provider/model pairs external projects may call through DevPilot.", page_body)
        self.assertIn('name="allowed_providers"', page_body)
        self.assertIn('value="openai"', page_body)
        self.assertIn('value="gemini"', page_body)
        self.assertIn('value="claude"', page_body)
        self.assertIn('value="replicate"', page_body)
        self.assertIn('value="fal"', page_body)
        self.assertIn('value="runway"', page_body)
        self.assertIn('value="kling"', page_body)
        self.assertIn("Pick a preset or select provider cards below.", page_body)
        self.assertIn("External AI Gateway MVP allowlist", page_body)
        self.assertIn("not a full provider model catalog", page_body)
        self.assertIn("Step 1. Choose a gateway setup", page_body)
        self.assertIn("Presets select Active Gateway Models only.", page_body)
        self.assertIn("Default MVP gateway set.", page_body)
        self.assertIn("Active Gateway Models", page_body)
        self.assertIn("Active / Available", page_body)
        self.assertIn("Candidate / Future Models, not enabled", page_body)
        self.assertIn("Gateway model onboarding", page_body)
        self.assertIn("Request enable", page_body)
        self.assertIn("Requires Gateway model onboarding.", page_body)
        self.assertIn("Backend allowlist update.", page_body)
        self.assertIn("Provider adapter compatibility check.", page_body)
        self.assertIn("Single-provider live smoke approval.", page_body)
        self.assertIn("Candidate models cannot be used by external projects until they complete onboarding.", page_body)
        self.assertIn("Selected summary", page_body)
        self.assertIn("External projects can call only the selected allowlist models through DevPilot.", page_body)
        self.assertIn("Candidate models shown below are not included in the submitted policy.", page_body)
        self.assertIn("Gemini 2.5 Flash", page_body)
        self.assertIn('data-model-provider="openai"', page_body)
        self.assertIn('data-model-provider="gemini"', page_body)
        self.assertIn('data-model-provider="claude"', page_body)
        self.assertIn('data-provider-model="openai"', page_body)
        self.assertIn('data-provider-model="gemini"', page_body)
        self.assertIn('name="allowed_models" value="gpt-4.1-mini"', page_body)
        self.assertIn('name="allowed_models" value="gpt-4o-mini"', page_body)
        self.assertIn('name="allowed_models" value="gemini-2.5-flash"', page_body)
        self.assertIn('name="allowed_models" value="claude-haiku-4-5-20251001"', page_body)
        self.assertIn('data-candidate-model="gpt-5.2"', page_body)
        self.assertIn('data-candidate-model="gpt-image-1"', page_body)
        self.assertIn('data-candidate-model="claude-sonnet-4-6"', page_body)
        self.assertIn('type="button" data-candidate-enable', page_body)
        self.assertNotIn('name="allowed_models" value="gpt-5.2"', page_body)
        self.assertNotIn('name="allowed_models" value="gpt-5.1"', page_body)
        self.assertNotIn('name="allowed_models" value="gpt-5"', page_body)
        self.assertNotIn('name="allowed_models" value="o4-mini"', page_body)
        self.assertNotIn('name="allowed_models" value="gpt-image-1"', page_body)
        self.assertNotIn('name="allowed_models" value="claude-sonnet-4-6"', page_body)
        self.assertNotIn('data-policy-preset data-providers="openai,gemini,claude" data-models="gpt-5', page_body)
        self.assertNotIn('data-policy-preset data-providers="openai,gemini,claude" data-models="gpt-image-1', page_body)
        self.assertIn('value="flux-schnell"', page_body)
        self.assertIn('value="fal-flux-pro"', page_body)
        self.assertIn("<span class=\"text-muted\">openai:</span> gpt-4.1-mini", page_body)
        self.assertIn('value="summary"', page_body)
        self.assertIn('data-capability-chip', page_body)
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
                "allowed_models": ["gpt-4.1-mini", "gpt-image-1", "gemini-2.5-flash", "claude-haiku-4-5-20251001", "flux-schnell", "fal-flux-pro"],
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
        self.assertEqual(policy["allowed_models"], ["gpt-4.1-mini", "gpt-image-1", "gemini-2.5-flash", "claude-haiku-4-5-20251001", "flux-schnell", "fal-flux-pro"])
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
            ({"allowed_providers": ["openai"], "allowed_models": ["gemini-2.5-flash"]}, "model/provider mismatch"),
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

    def test_external_ai_generate_rejects_auth_policy_and_mvp_violations(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        body = {
            "capability": "summary",
            "model": "gemini-2.5-flash",
            "prompt": "Summarize this safely.",
            "external_ref": "gateway-ticket-1",
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

        disabled_policy = self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": False,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary"],
        })
        self.assertFalse(disabled_policy["enabled"])
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], "external_ai_policy_not_enabled")

        policy_cases = [
            (
                "provider_not_allowed",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["openai"],
                    "allowed_models": ["gpt-4.1-mini"],
                    "allowed_capabilities": ["summary"],
                },
                body,
                403,
                "external_ai_provider_not_allowed",
            ),
            (
                "model_not_allowed",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-1.5-pro"],
                    "allowed_capabilities": ["summary"],
                },
                body,
                403,
                "external_ai_model_not_allowed",
            ),
            (
                "capability_not_allowed",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["rewrite"],
                },
                body,
                403,
                "external_ai_capability_not_allowed",
            ),
            (
                "tools_not_supported",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["summary"],
                    "allow_tool_calling": True,
                },
                body,
                403,
                "external_ai_policy_not_supported_for_mvp",
            ),
            (
                "streaming_not_supported",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["summary"],
                    "allow_streaming": True,
                },
                body,
                403,
                "external_ai_policy_not_supported_for_mvp",
            ),
            (
                "unsupported_image_capability",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["image_generation"],
                },
                {**body, "capability": "image_generation"},
                403,
                "external_ai_capability_not_supported_for_mvp",
            ),
            (
                "oversized_prompt",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["summary"],
                    "max_tokens_per_request": 1,
                },
                {**body, "prompt": "This prompt is intentionally too long."},
                413,
                "external_ai_prompt_too_large",
            ),
        ]

        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            for name, policy_payload, request_body, expected_status, expected_error in policy_cases:
                self.policy_store_path.write_text('{"policies": []}', encoding="utf-8")
                self.app_module.create_external_ai_policy(policy_payload)
                with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
                    response = self.client().post(
                        "/api/external/ai/generate",
                        json=request_body,
                        headers=self.external_headers(request_id=f"gateway-{name}", idempotency_key=f"gateway-{name}"),
                    )
                self.assertEqual(response.status_code, expected_status, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertEqual(payload["error"], expected_error)
                self.assertNotIn("test-provider-key", response.get_data(as_text=True))
        gemini_call.assert_not_called()

        self.policy_store_path.write_text('{"policies": []}', encoding="utf-8")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary"],
        })
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(response.status_code, 503, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], "provider_not_configured")
        self.assertNotIn("GEMINI_API_KEY", response.get_data(as_text=True))
        gemini_call.assert_not_called()

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_calls_mocked_gemini_logs_usage_and_replays_idempotency(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        long_prompt = "Summarize this external project update. " * 12
        long_response = "This is a concise Gemini summary. " * 8
        body = {
            "capability": "generate",
            "model": "gemini-2.5-flash",
            "prompt": long_prompt,
            "external_ref": "gateway-ticket-2",
            "metadata": {"project": "AD-Studio_AI"},
        }
        headers = self.external_headers(source="external-a", key="key-a", request_id="gateway-req-ok", idempotency_key="gateway-idem-ok")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["generate", "summary", "rewrite", "classification", "extraction", "planning", "chat"],
            "max_tokens_per_request": 1000,
        })
        provider_result = {
            "ok": True,
            "text": long_response,
            "usage": {"input_tokens": 12, "output_tokens": 9, "total_tokens": 21},
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate", return_value=provider_result) as gemini_call:
                with patch.object(self.app_module, "call_task_provider") as provider_call:
                    with patch.object(self.app_module, "run_ai_task") as run_task:
                        with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                            with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                with patch.object(self.app_module, "save_handoff") as legacy_save:
                                    response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
                                    replay = self.client().post("/api/external/ai/generate", json=body, headers=headers)

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["idempotent_replay"])
        self.assertEqual(payload["provider"], "gemini")
        self.assertEqual(payload["model"], "gemini-2.5-flash")
        self.assertEqual(payload["capability"], "generate")
        self.assertEqual(payload["text"], long_response)
        self.assertEqual(payload["usage"]["total_tokens"], 21)
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["side_effects"])
        self.assertTrue(payload["provider_calls_executed"])
        self.assertNotIn("test-provider-key", response.get_data(as_text=True))

        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        replay_payload = replay.get_json()
        self.assertTrue(replay_payload["idempotent_replay"])
        self.assertFalse(replay_payload["provider_calls_executed"])
        self.assertEqual(replay_payload["text"], long_response)
        gemini_call.assert_called_once_with(long_prompt, "gemini-2.5-flash", "test-provider-key")
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        usage_records = self.app_module.load_external_ai_usage_log_records()
        result_records = self.app_module.load_external_ai_generation_results()
        self.assertEqual(len(usage_records), 1)
        self.assertEqual(len(result_records), 1)
        usage = usage_records[0]
        self.assertEqual(usage["status"], "completed")
        self.assertEqual(usage["source_system"], "external-a")
        self.assertEqual(usage["provider"], "gemini")
        self.assertEqual(usage["model"], "gemini-2.5-flash")
        self.assertEqual(usage["capability"], "generate")
        self.assertTrue(usage["prompt_hash"])
        self.assertTrue(usage["response_hash"])
        self.assertNotIn(long_prompt, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_response, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-provider-key", self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_prompt, self.generation_results_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-provider-key", self.generation_results_path.read_text(encoding="utf-8"))
        self.assertEqual(result_records[0]["status"], "completed")

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_resolves_legacy_gateway_model_aliases(self):
        before = self.state_snapshot()
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini", "claude"],
            "allowed_models": ["gemini-1.5-flash", "claude-3-5-haiku"],
            "allowed_capabilities": ["generate"],
            "max_tokens_per_request": 1000,
        })

        gemini_body = {
            "provider": "gemini",
            "capability": "generate",
            "model": "gemini-1.5-flash",
            "prompt": "Confirm legacy Gemini alias.",
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate", return_value={
                "ok": True,
                "text": "Gemini alias resolved.",
                "usage": {"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
            }) as gemini_call:
                gemini_response = self.client().post(
                    "/api/external/ai/generate",
                    json=gemini_body,
                    headers=self.external_headers(request_id="gateway-gemini-alias", idempotency_key="gateway-gemini-alias"),
                )
        self.assertEqual(gemini_response.status_code, 200, gemini_response.get_data(as_text=True))
        gemini_payload = gemini_response.get_json()
        self.assertEqual(gemini_payload["model"], "gemini-2.5-flash")
        self.assertEqual(gemini_payload["requested_model"], "gemini-1.5-flash")
        gemini_call.assert_called_once_with("Confirm legacy Gemini alias.", "gemini-2.5-flash", "test-provider-key")

        claude_body = {
            "provider": "claude",
            "capability": "generate",
            "model": "claude-3-5-haiku",
            "prompt": "Confirm legacy Claude alias.",
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "ANTHROPIC_API_KEY": "test-claude-provider-key", "CLAUDE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_claude_external_ai_generate", return_value={
                "ok": True,
                "text": "Claude alias resolved.",
                "usage": {"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
            }) as claude_call:
                claude_response = self.client().post(
                    "/api/external/ai/generate",
                    json=claude_body,
                    headers=self.external_headers(request_id="gateway-claude-alias", idempotency_key="gateway-claude-alias"),
                )
        self.assertEqual(claude_response.status_code, 200, claude_response.get_data(as_text=True))
        claude_payload = claude_response.get_json()
        self.assertEqual(claude_payload["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(claude_payload["requested_model"], "claude-3-5-haiku")
        claude_call.assert_called_once_with("Confirm legacy Claude alias.", "claude-haiku-4-5-20251001", "test-claude-provider-key")

        self.assertNotIn("test-provider-key", gemini_response.get_data(as_text=True))
        self.assertNotIn("test-claude-provider-key", claude_response.get_data(as_text=True))
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_provider_failure_reports_sanitized_upstream_status(self):
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["generate"],
            "max_tokens_per_request": 1000,
        })
        body = {
            "provider": "gemini",
            "capability": "generate",
            "model": "gemini-2.5-flash",
            "prompt": "Summarize this safely.",
        }
        provider_result = {
            "ok": False,
            "error": "gemini_http_error",
            "status_code": 404,
            "upstream_error": "NOT_FOUND model missing api_key=secret-token Bearer secret-bearer-token",
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate", return_value=provider_result):
                response = self.client().post(
                    "/api/external/ai/generate",
                    json=body,
                    headers=self.external_headers(request_id="gateway-upstream-status", idempotency_key="gateway-upstream-status"),
                )
        self.assertEqual(response.status_code, 502, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["error"], "external_ai_provider_call_failed")
        self.assertEqual(payload["provider_error"], "gemini_http_error")
        self.assertEqual(payload["provider_status_code"], 404)
        self.assertEqual(payload["upstream_status_code"], 404)
        self.assertIn("NOT_FOUND", payload["provider_error_summary"])
        response_text = response.get_data(as_text=True)
        self.assertIn("REDACTED", response_text)
        self.assertNotIn("secret-token", response_text)
        self.assertNotIn("secret-bearer-token", response_text)
        self.assertNotIn("test-provider-key", response_text)

    def test_external_ai_generate_claude_rejects_policy_and_missing_config_without_live_call(self):
        before = self.state_snapshot()
        body = {
            "provider": "claude",
            "capability": "summary",
            "model": "claude-haiku-4-5-20251001",
            "prompt": "Summarize this safely.",
            "external_ref": "claude-policy-ticket",
        }
        headers = self.external_headers(source="external-a", key="key-a", request_id="claude-policy", idempotency_key="claude-policy")

        policy_cases = [
            (
                "provider_not_allowed",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["gemini"],
                    "allowed_models": ["gemini-2.5-flash"],
                    "allowed_capabilities": ["summary"],
                },
                403,
                "external_ai_provider_not_allowed",
            ),
            (
                "model_not_allowed",
                {
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": ["claude"],
                    "allowed_models": ["claude-sonnet-4-6"],
                    "allowed_capabilities": ["summary"],
                },
                403,
                "external_ai_model_not_allowed",
            ),
        ]

        with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                for name, policy_payload, expected_status, expected_error in policy_cases:
                    self.policy_store_path.write_text('{"policies": []}', encoding="utf-8")
                    self.app_module.create_external_ai_policy(policy_payload)
                    with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "ANTHROPIC_API_KEY": "test-claude-key", "CLAUDE_API_KEY": ""}, clear=False):
                        response = self.client().post(
                            "/api/external/ai/generate",
                            json=body,
                            headers=self.external_headers(request_id=f"claude-{name}", idempotency_key=f"claude-{name}"),
                        )
                    self.assertEqual(response.status_code, expected_status, response.get_data(as_text=True))
                    payload = response.get_json()
                    self.assertEqual(payload["provider"], "claude")
                    self.assertEqual(payload["model"], "claude-haiku-4-5-20251001")
                    self.assertEqual(payload["error"], expected_error)
                    self.assertFalse(payload["provider_calls_executed"])
                    self.assertNotIn("test-claude-key", response.get_data(as_text=True))
        claude_call.assert_not_called()
        gemini_call.assert_not_called()

        self.policy_store_path.write_text('{"policies": []}', encoding="utf-8")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["claude"],
            "allowed_models": ["claude-haiku-4-5-20251001"],
            "allowed_capabilities": ["summary"],
        })
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "ANTHROPIC_API_KEY": "", "CLAUDE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(response.status_code, 503, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["error"], "provider_not_configured")
        self.assertEqual(response.get_json()["provider"], "claude")
        self.assertNotIn("ANTHROPIC_API_KEY", response.get_data(as_text=True))
        self.assertNotIn("CLAUDE_API_KEY", response.get_data(as_text=True))
        claude_call.assert_not_called()
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_calls_mocked_claude_logs_usage_and_replays_idempotency(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        long_prompt = "Summarize this external Claude gateway update. " * 12
        long_response = "This is a concise mocked Claude summary. " * 8
        body = {
            "provider": "claude",
            "capability": "generate",
            "model": "claude-haiku-4-5-20251001",
            "prompt": long_prompt,
            "external_ref": "claude-gateway-ticket",
            "metadata": {"project": "AD-Studio_AI"},
        }
        headers = self.external_headers(source="external-a", key="key-a", request_id="claude-req-ok", idempotency_key="claude-idem-ok")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["claude"],
            "allowed_models": ["claude-haiku-4-5-20251001"],
            "allowed_capabilities": ["generate", "summary", "rewrite", "classification", "extraction", "planning", "chat"],
            "max_tokens_per_request": 1000,
        })
        provider_result = {
            "ok": True,
            "text": long_response,
            "usage": {"input_tokens": 14, "output_tokens": 11, "total_tokens": 25},
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "ANTHROPIC_API_KEY": "test-claude-provider-key", "CLAUDE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_claude_external_ai_generate", return_value=provider_result) as claude_call:
                with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                    with patch.object(self.app_module, "call_task_provider") as provider_call:
                        with patch.object(self.app_module, "run_ai_task") as run_task:
                            with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                                with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                    with patch.object(self.app_module, "save_handoff") as legacy_save:
                                        response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
                                        replay = self.client().post("/api/external/ai/generate", json=body, headers=headers)

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["idempotent_replay"])
        self.assertEqual(payload["provider"], "claude")
        self.assertEqual(payload["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(payload["capability"], "generate")
        self.assertEqual(payload["text"], long_response)
        self.assertEqual(payload["usage"]["total_tokens"], 25)
        self.assertTrue(payload["provider_calls_executed"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["side_effects"])
        self.assertNotIn("test-claude-provider-key", response.get_data(as_text=True))

        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        replay_payload = replay.get_json()
        self.assertTrue(replay_payload["idempotent_replay"])
        self.assertFalse(replay_payload["provider_calls_executed"])
        self.assertEqual(replay_payload["provider"], "claude")
        self.assertEqual(replay_payload["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(replay_payload["text"], long_response)
        claude_call.assert_called_once_with(long_prompt, "claude-haiku-4-5-20251001", "test-claude-provider-key")
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        usage_records = self.app_module.load_external_ai_usage_log_records()
        result_records = self.app_module.load_external_ai_generation_results()
        self.assertEqual(len(usage_records), 1)
        self.assertEqual(len(result_records), 1)
        usage = usage_records[0]
        self.assertEqual(usage["status"], "completed")
        self.assertEqual(usage["source_system"], "external-a")
        self.assertEqual(usage["provider"], "claude")
        self.assertEqual(usage["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(usage["capability"], "generate")
        self.assertTrue(usage["prompt_hash"])
        self.assertTrue(usage["response_hash"])
        self.assertNotIn(long_prompt, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_response, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-claude-provider-key", self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_prompt, self.generation_results_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-claude-provider-key", self.generation_results_path.read_text(encoding="utf-8"))
        self.assertEqual(result_records[0]["status"], "completed")
        self.assertEqual(result_records[0]["provider"], "claude")

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_invalid_stores_do_not_crash(self):
        self.generation_results_path.write_text("{not json", encoding="utf-8")
        self.usage_log_path.write_text("{not json", encoding="utf-8")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary"],
        })
        body = {
            "capability": "summary",
            "model": "gemini-2.5-flash",
            "prompt": "Summarize this safely.",
            "external_ref": "gateway-ticket-invalid-store",
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate", return_value={
                "ok": True,
                "text": "Safe summary.",
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            }) as gemini_call:
                response = self.client().post(
                    "/api/external/ai/generate",
                    json=body,
                    headers=self.external_headers(request_id="gateway-invalid-store", idempotency_key="gateway-invalid-store"),
                )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        gemini_call.assert_called_once()
        self.assertEqual(len(self.app_module.load_external_ai_generation_results()), 1)
        self.assertEqual(len(self.app_module.load_external_ai_usage_log_records()), 1)

    def test_external_ai_generate_failed_result_can_retry(self):
        body = {
            "capability": "summary",
            "model": "gemini-2.5-flash",
            "prompt": "Summarize this safely.",
            "external_ref": "gateway-ticket-retry",
        }
        headers = self.external_headers(request_id="gateway-retry", idempotency_key="gateway-retry")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary"],
        })
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            first = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(first.status_code, 503, first.get_data(as_text=True))
        self.assertEqual(first.get_json()["error"], "provider_not_configured")
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "GEMINI_API_KEY": "test-provider-key", "GOOGLE_API_KEY": ""}, clear=False):
            with patch.object(self.app_module, "call_gemini_generate", return_value={
                "ok": True,
                "text": "Retry worked.",
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            }) as gemini_call:
                second = self.client().post("/api/external/ai/generate", json=body, headers=headers)
        self.assertEqual(second.status_code, 200, second.get_data(as_text=True))
        self.assertFalse(second.get_json()["idempotent_replay"])
        gemini_call.assert_called_once()
        result_records = self.app_module.load_external_ai_generation_results()
        self.assertEqual([record["status"] for record in result_records], ["failed", "completed"])

    def test_external_ai_generate_calls_mocked_openai_logs_usage_and_replays_idempotency(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        long_prompt = "Summarize this external OpenAI gateway update. " * 12
        long_response = "This is a concise mocked OpenAI summary. " * 8
        body = {
            "provider": "openai",
            "capability": "generate",
            "model": "gpt-4.1-mini",
            "prompt": long_prompt,
            "external_ref": "openai-gateway-ticket",
            "metadata": {"project": "AD-Studio_AI"},
        }
        headers = self.external_headers(source="external-a", key="key-a", request_id="openai-req-ok", idempotency_key="openai-idem-ok")
        self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["openai"],
            "allowed_models": ["gpt-4.1-mini"],
            "allowed_capabilities": ["generate", "summary", "rewrite", "classification", "extraction", "planning", "chat"],
            "max_tokens_per_request": 1000,
        })
        provider_result = {
            "ok": True,
            "text": long_response,
            "usage": {"input_tokens": 16, "output_tokens": 12, "total_tokens": 28},
        }
        with patch.dict(self.app_module.os.environ, {**self.external_api_env(), "OPENAI_API_KEY": "test-openai-provider-key"}, clear=False):
            with patch.object(self.app_module, "call_openai_external_ai_generate", return_value=provider_result) as openai_call:
                with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                    with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                        with patch.object(self.app_module, "call_task_provider") as provider_call:
                            with patch.object(self.app_module, "run_ai_task") as run_task:
                                with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                                    with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                                        with patch.object(self.app_module, "save_handoff") as legacy_save:
                                            response = self.client().post("/api/external/ai/generate", json=body, headers=headers)
                                            replay = self.client().post("/api/external/ai/generate", json=body, headers=headers)

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["idempotent_replay"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["model"], "gpt-4.1-mini")
        self.assertEqual(payload["capability"], "generate")
        self.assertEqual(payload["text"], long_response)
        self.assertEqual(payload["usage"]["total_tokens"], 28)
        self.assertTrue(payload["provider_calls_executed"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["side_effects"])
        self.assertNotIn("test-openai-provider-key", response.get_data(as_text=True))

        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        replay_payload = replay.get_json()
        self.assertTrue(replay_payload["idempotent_replay"])
        self.assertFalse(replay_payload["provider_calls_executed"])
        self.assertEqual(replay_payload["provider"], "openai")
        self.assertEqual(replay_payload["model"], "gpt-4.1-mini")
        self.assertEqual(replay_payload["text"], long_response)
        openai_call.assert_called_once_with(long_prompt, "gpt-4.1-mini", "test-openai-provider-key")
        gemini_call.assert_not_called()
        claude_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()
        legacy_save.assert_not_called()

        usage_records = self.app_module.load_external_ai_usage_log_records()
        result_records = self.app_module.load_external_ai_generation_results()
        self.assertEqual(len(usage_records), 1)
        self.assertEqual(len(result_records), 1)
        usage = usage_records[0]
        self.assertEqual(usage["status"], "completed")
        self.assertEqual(usage["source_system"], "external-a")
        self.assertEqual(usage["provider"], "openai")
        self.assertEqual(usage["model"], "gpt-4.1-mini")
        self.assertEqual(usage["capability"], "generate")
        self.assertTrue(usage["prompt_hash"])
        self.assertTrue(usage["response_hash"])
        self.assertNotIn(long_prompt, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_response, self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-openai-provider-key", self.usage_log_path.read_text(encoding="utf-8"))
        self.assertNotIn(long_prompt, self.generation_results_path.read_text(encoding="utf-8"))
        self.assertNotIn("test-openai-provider-key", self.generation_results_path.read_text(encoding="utf-8"))
        self.assertEqual(result_records[0]["status"], "completed")
        self.assertEqual(result_records[0]["provider"], "openai")

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_generate_uses_managed_provider_keys_without_runtime_env(self):
        before = self.state_snapshot()
        cases = [
            {
                "provider": "openai",
                "db_provider": "openai",
                "model": "gpt-4.1-mini",
                "key": "managed-openai-provider-key",
                "call_name": "call_openai_external_ai_generate",
            },
            {
                "provider": "gemini",
                "db_provider": "google",
                "model": "gemini-2.5-flash",
                "key": "managed-gemini-provider-key",
                "call_name": "call_gemini_generate",
            },
            {
                "provider": "claude",
                "db_provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "key": "managed-claude-provider-key",
                "call_name": "call_claude_external_ai_generate",
            },
        ]
        empty_provider_env = {
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_API_KEY": "",
        }

        try:
            for item in cases:
                self.cleanup_managed_ai_provider_keys()
                self.policy_store_path.write_text('{"policies": []}', encoding="utf-8")
                self.generation_results_path.write_text('{"results": []}', encoding="utf-8")
                self.usage_log_path.write_text('{"records": []}', encoding="utf-8")
                self.create_managed_ai_provider_key(item["db_provider"], item["key"])
                self.app_module.create_external_ai_policy({
                    "source_system": "external-a",
                    "enabled": True,
                    "allowed_providers": [item["provider"]],
                    "allowed_models": [item["model"]],
                    "allowed_capabilities": ["generate"],
                    "max_tokens_per_request": 1000,
                })
                prompt = f"Managed key gateway smoke for {item['provider']}."
                body = {
                    "provider": item["provider"],
                    "capability": "generate",
                    "model": item["model"],
                    "prompt": prompt,
                }
                provider_result = {
                    "ok": True,
                    "text": f"{item['provider']} managed key response",
                    "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                }
                with patch.dict(self.app_module.os.environ, {**self.external_api_env(), **empty_provider_env}, clear=False):
                    with patch.object(self.app_module, item["call_name"], return_value=provider_result) as provider_call:
                        response = self.client().post(
                            "/api/external/ai/generate",
                            json=body,
                            headers=self.external_headers(
                                request_id=f"managed-{item['provider']}",
                                idempotency_key=f"managed-{item['provider']}",
                            ),
                        )

                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["provider"], item["provider"])
                self.assertEqual(payload["model"], item["model"])
                provider_call.assert_called_once_with(prompt, item["model"], item["key"])
                combined = response.get_data(as_text=True)
                self.assertNotIn(item["key"], combined)
                self.assertNotIn("OPENAI_API_KEY", combined)
                self.assertNotIn("GEMINI_API_KEY", combined)
                self.assertNotIn("ANTHROPIC_API_KEY", combined)
        finally:
            self.cleanup_managed_ai_provider_keys()

        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_usage_api_is_source_isolated_filtered_and_summarized(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        records = [
            {
                "id": "usage-a-1",
                "source_system": "external-a",
                "request_id": "req-a-1",
                "idempotency_key": "idem-a-1",
                "external_ref": "ticket-a",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "error_code": "",
                "input_token_estimate": 10,
                "output_token_estimate": 5,
                "input_chars": 100,
                "output_chars": 50,
                "latency_ms": 100,
                "prompt_hash": "prompt-hash-a",
                "prompt_summary": "Safe prompt summary",
                "response_hash": "response-hash-a",
                "response_summary": "Safe response summary",
                "prompt": "FULL_PROMPT_SECRET_SHOULD_NOT_LEAK",
                "response": "FULL_RESPONSE_SECRET_SHOULD_NOT_LEAK",
                "created_at": "2026-05-13 10:00:00",
            },
            {
                "id": "usage-a-2",
                "source_system": "external-a",
                "request_id": "req-a-2",
                "idempotency_key": "idem-a-2",
                "external_ref": "ticket-b",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "rewrite",
                "status": "failed",
                "error_code": "provider_not_configured",
                "input_token_estimate": 6,
                "output_token_estimate": 0,
                "input_chars": 60,
                "output_chars": 0,
                "latency_ms": 200,
                "prompt_hash": "prompt-hash-b",
                "prompt_summary": "Safe failure prompt summary",
                "response_hash": "response-hash-b",
                "response_summary": "",
                "created_at": "2026-05-13 11:00:00",
            },
            {
                "id": "usage-b-1",
                "source_system": "external-b",
                "request_id": "req-b-1",
                "idempotency_key": "idem-b-1",
                "external_ref": "ticket-other",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "input_chars": 999,
                "output_chars": 999,
                "latency_ms": 999,
                "prompt_hash": "prompt-hash-other",
                "prompt_summary": "Other source summary",
                "response_hash": "response-hash-other",
                "response_summary": "Other source response",
                "created_at": "2026-05-13 12:00:00",
            },
        ]
        self.app_module.save_external_ai_usage_log_records(records)

        with patch.dict(self.app_module.os.environ, {"DEVPILOT_EXTERNAL_API_KEYS": ""}, clear=False):
            missing = self.client().get("/api/external/ai/usage")
        self.assertEqual(missing.status_code, 403)
        with patch.dict(self.app_module.os.environ, self.external_api_env(), clear=False):
            wrong = self.client().get("/api/external/ai/usage", headers=self.external_headers(key="wrong"))
            response = self.client().get("/api/external/ai/usage", headers=self.external_headers())
            filtered = self.client().get(
                "/api/external/ai/usage?provider=gemini&model=gemini-2.5-flash&capability=summary&status=completed&external_ref=ticket-a&from=2026-05-13&to=2026-05-13",
                headers=self.external_headers(),
            )
            forced_other = self.client().get("/api/external/ai/usage?source_system=external-b", headers=self.external_headers())

        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual({item["source_system"] for item in payload["items"]}, {"external-a"})
        self.assertEqual(payload["summary"]["total_requests"], 2)
        self.assertEqual(payload["summary"]["success_count"], 1)
        self.assertEqual(payload["summary"]["failed_count"], 1)
        self.assertEqual(payload["summary"]["total_input_chars"], 160)
        self.assertEqual(payload["summary"]["total_output_chars"], 50)
        self.assertEqual(payload["summary"]["average_latency_ms"], 150)
        self.assertIn("gemini-2.5-flash", payload["summary"]["grouped_by_model"])
        self.assertIn("summary", payload["summary"]["grouped_by_capability"])
        response_text = response.get_data(as_text=True)
        self.assertNotIn("FULL_PROMPT_SECRET_SHOULD_NOT_LEAK", response_text)
        self.assertNotIn("FULL_RESPONSE_SECRET_SHOULD_NOT_LEAK", response_text)
        self.assertNotIn("ticket-other", response_text)

        self.assertEqual(filtered.status_code, 200, filtered.get_data(as_text=True))
        self.assertEqual(filtered.get_json()["count"], 1)
        self.assertEqual(filtered.get_json()["items"][0]["id"], "usage-a-1")
        self.assertEqual(forced_other.status_code, 200)
        self.assertEqual(forced_other.get_json()["count"], 0)

        with self.app.app_context():
            approval_count_after = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.assertEqual(approval_count_after, approval_count_before)
        self.assertEqual(self.state_snapshot(), before)

    def test_external_ai_usage_admin_dashboard_invalid_store_and_budget_warnings(self):
        before = self.state_snapshot()
        with self.app.app_context():
            approval_count_before = self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"]
        self.usage_log_path.write_text("{not json", encoding="utf-8")
        invalid_response = self.client().get("/admin/external-ai-usage")
        self.assertEqual(invalid_response.status_code, 200, invalid_response.get_data(as_text=True))
        self.assertIn("External AI Usage", invalid_response.get_data(as_text=True))

        records = [
            {
                "id": "usage-budget-1",
                "source_system": "external-a",
                "request_id": "req-budget-1",
                "idempotency_key": "idem-budget-1",
                "external_ref": "budget-ticket",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "input_token_estimate": 9,
                "output_token_estimate": 6,
                "input_chars": 90,
                "output_chars": 60,
                "latency_ms": 100,
                "prompt_hash": "budget-prompt-hash",
                "prompt_summary": "Budget safe prompt summary",
                "response_hash": "budget-response-hash",
                "response_summary": "Budget safe response summary",
                "created_at": "2026-05-13 10:00:00",
            },
            {
                "id": "usage-budget-2",
                "source_system": "external-a",
                "request_id": "req-budget-2",
                "idempotency_key": "idem-budget-2",
                "external_ref": "budget-ticket",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "capability": "summary",
                "status": "completed",
                "input_token_estimate": 9,
                "output_token_estimate": 6,
                "input_chars": 90,
                "output_chars": 60,
                "latency_ms": 300,
                "prompt_hash": "budget-prompt-hash-2",
                "prompt_summary": "Second budget safe prompt summary",
                "response_hash": "budget-response-hash-2",
                "response_summary": "Second budget safe response summary",
                "created_at": "2026-05-13 10:05:00",
            },
        ]
        self.app_module.save_external_ai_usage_log_records(records)
        policy = self.app_module.create_external_ai_policy({
            "source_system": "external-a",
            "enabled": True,
            "allowed_providers": ["gemini"],
            "allowed_models": ["gemini-2.5-flash"],
            "allowed_capabilities": ["summary"],
            "daily_request_limit": 2,
            "daily_token_limit": 20,
            "monthly_budget_usd": 50,
        })
        response = self.client().get("/admin/external-ai-usage?source_system=external-a&q=budget-ticket&provider=gemini&model=gemini-2.5-flash&capability=summary&status=completed")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        page = response.get_data(as_text=True)
        self.assertIn("budget-ticket", page)
        self.assertIn("daily_request_limit_exceeded", page)
        self.assertIn("daily_token_limit_exceeded", page)
        self.assertIn("monthly_budget_not_enforced_yet", page)
        self.assertIn("Budget safe prompt summary", page)

        summary = self.app_module.summarize_external_ai_usage(self.app_module.external_ai_usage_rows({"source_system": "external-a"}))
        budget = self.app_module.external_ai_usage_within_policy(policy, summary)
        self.assertFalse(budget["ok"])
        self.assertIn("daily_request_limit_exceeded", budget["warnings"])
        self.assertIn("daily_token_limit_exceeded", budget["warnings"])

        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_task_provider") as provider_call:
                with patch.object(self.app_module, "run_ai_task") as run_task:
                    with patch.object(self.app_module, "dispatch_ai_console_task") as console_dispatch:
                        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
                            followup = self.client().get("/admin/external-ai-usage?source_system=external-a")
        self.assertEqual(followup.status_code, 200)
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        console_dispatch.assert_not_called()
        cloudflare_request.assert_not_called()

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
