import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services import automation_plans


class AutomationPlanStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "automation_plans.json"
        self.store_env = patch.dict(
            os.environ,
            {"DEVPILOT_AUTOMATION_PLAN_STORE_PATH": str(self.store_path)},
            clear=False,
        )
        self.store_env.start()

    def tearDown(self):
        self.store_env.stop()
        self.temp_dir.cleanup()

    def base_plan(self, **overrides):
        plan = {
            "source_system": "gpcarai",
            "external_project_id": "gpcarai-prod",
            "title": "Review gpcarai live loop",
            "objective": "Summarize current external project state.",
            "risk_level": "low",
            "recommended_actions": [
                {
                    "label": "Review diagnostics",
                    "description": "Open source detail and confirm latest external event.",
                    "risk_level": "low",
                    "requires_approval": False,
                    "approval_type": "none",
                }
            ],
            "required_approvals": [],
            "blocked_by": [],
            "safety_checks": [
                {
                    "name": "No execution",
                    "status": "pass",
                    "details": "Planning only.",
                }
            ],
            "suggested_commands": [
                {
                    "label": "Inspect recent logs",
                    "command": "docker compose logs --tail=100 devpilot",
                    "execution_allowed": True,
                }
            ],
            "affected_systems": [
                {
                    "type": "external_project",
                    "name": "gpcarai-prod",
                    "impact": "Read-only planning context.",
                }
            ],
        }
        plan.update(overrides)
        return plan

    def test_missing_store_loads_empty_store(self):
        store = automation_plans.load_automation_plan_store()

        self.assertEqual(store["version"], 1)
        self.assertEqual(store["plans"], [])
        self.assertNotIn("error", store)

    def test_malformed_store_fails_closed_without_overwriting_file(self):
        self.store_path.write_text("{not-valid-json", encoding="utf-8")

        store = automation_plans.load_automation_plan_store()

        self.assertEqual(store["version"], 1)
        self.assertEqual(store["plans"], [])
        self.assertEqual(store["error"], "malformed_store")
        self.assertEqual(self.store_path.read_text(encoding="utf-8"), "{not-valid-json")

    def test_create_draft_plan_writes_one_plan(self):
        created = automation_plans.create_automation_plan(self.base_plan())

        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["plans"]), 1)
        self.assertEqual(payload["plans"][0]["id"], created["id"])
        self.assertEqual(payload["plans"][0]["status"], "draft")
        self.assertEqual(payload["plans"][0]["approval_status"], "not_requested")
        self.assertIsNone(payload["plans"][0]["approval_request_id"])

    def test_list_automation_plans_returns_saved_plan(self):
        created = automation_plans.create_automation_plan(self.base_plan())

        plans = automation_plans.list_automation_plans()

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["id"], created["id"])
        self.assertEqual(plans[0]["source_system"], "gpcarai")

    def test_created_plan_gets_id_created_at_and_default_status(self):
        created = automation_plans.create_automation_plan(self.base_plan(status="approved"))

        self.assertTrue(created["id"].startswith("plan_"))
        self.assertTrue(created["created_at"].endswith("Z"))
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["approval_status"], "not_requested")
        self.assertIsNone(created["approval_request_id"])

    def test_allowed_risk_levels_are_accepted(self):
        for risk_level in ("low", "medium", "high", "blocked"):
            with self.subTest(risk_level=risk_level):
                created = automation_plans.create_automation_plan(
                    self.base_plan(
                        title=f"Risk {risk_level}",
                        risk_level=risk_level,
                    )
                )
                self.assertEqual(created["risk_level"], risk_level)

    def test_invalid_risk_level_is_rejected(self):
        with self.assertRaises(ValueError):
            automation_plans.create_automation_plan(self.base_plan(risk_level="execute"))

        self.assertFalse(self.store_path.exists())

    def test_suggested_commands_are_text_only_and_never_execution_allowed(self):
        created = automation_plans.create_automation_plan(
            self.base_plan(
                suggested_commands=[
                    {
                        "label": "Display command",
                        "command": 12345,
                        "execution_allowed": True,
                    }
                ]
            )
        )

        command = created["suggested_commands"][0]
        self.assertIsInstance(command["command"], str)
        self.assertEqual(command["command"], "12345")
        self.assertFalse(command["execution_allowed"])

        saved = json.loads(self.store_path.read_text(encoding="utf-8"))["plans"][0]
        self.assertFalse(saved["suggested_commands"][0]["execution_allowed"])

    def test_sensitive_markers_are_rejected_and_not_saved(self):
        cases = [
            {"api_key": "dp_ext_example_value"},
            {"objective": "Use Authorization: Bearer abcdefghijk"},
            {"objective": "Read OPENAI_API_KEY from environment"},
            {"safety_checks": [{"name": "hash", "status": "warn", "details": "key_hash=abc123"}]},
        ]

        for override in cases:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    automation_plans.create_automation_plan(self.base_plan(**override))

        self.assertFalse(self.store_path.exists())

    def test_approval_metadata_defaults_for_low_risk_plan(self):
        created = automation_plans.create_automation_plan(
            self.base_plan(
                suggested_commands=[
                    {
                        "label": "Open planner",
                        "command": "Open DevPilot page /admin/automation-planner",
                        "execution_allowed": False,
                    }
                ],
            )
        )

        self.assertFalse(created["approval_required"])
        self.assertEqual(created["approval_types"], [])
        self.assertEqual(created["approval_status"], "not_requested")
        self.assertIsNone(created["approval_request_id"])
        self.assertIn("disabled", created["approval_disabled_reason"])

    def test_high_risk_plan_persists_disabled_approval_metadata(self):
        created = automation_plans.create_automation_plan(
            self.base_plan(
                risk_level="high",
                required_approvals=["dns"],
                recommended_actions=[
                    {
                        "label": "Review domain request",
                        "description": "Change DNS after separate review.",
                        "risk_level": "high",
                        "requires_approval": False,
                        "approval_type": "none",
                    }
                ],
                suggested_commands=[
                    {
                        "label": "Open source detail",
                        "command": "Open DevPilot page /admin/external-sources/gpcarai",
                        "execution_allowed": False,
                    }
                ],
                approval_status="approved",
                approval_request_id=123,
            )
        )

        saved = json.loads(self.store_path.read_text(encoding="utf-8"))["plans"][0]
        self.assertTrue(created["approval_required"])
        self.assertIn("dns", created["approval_types"])
        self.assertEqual(created["approval_status"], "not_requested")
        self.assertIsNone(created["approval_request_id"])
        self.assertTrue(saved["approval_required"])
        self.assertEqual(saved["approval_status"], "not_requested")
        self.assertIsNone(saved["approval_request_id"])

    def test_store_layer_does_not_add_admin_api_or_draft_endpoint(self):
        import app as app_module

        routes = {rule.rule for rule in app_module.app.url_map.iter_rules()}

        self.assertNotIn("/api/admin/automation-plans", routes)
        self.assertNotIn("/api/admin/automation-plans/draft", routes)
        self.assertNotIn("/api/admin/automation-plans/safety", routes)
        self.assertNotIn("/admin/automation-planner/safety", routes)

    def test_store_actions_do_not_call_providers_workers_or_mutate_core_tables(self):
        import app as app_module

        def table_counts():
            with app_module.app.app_context():
                return {
                    "projects": app_module.query_one("SELECT COUNT(*) AS count FROM projects")["count"],
                    "tasks": app_module.query_one("SELECT COUNT(*) AS count FROM tasks")["count"],
                    "project_phases": app_module.query_one("SELECT COUNT(*) AS count FROM project_phases")["count"],
                    "approval_requests": app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"],
                }

        before = table_counts()
        with patch.object(app_module, "call_gemini_generate") as gemini_call, \
                patch.object(app_module, "call_task_provider") as provider_call, \
                patch.object(app_module, "run_ai_task") as run_task, \
                patch.object(app_module, "dispatch_ai_console_task") as dispatch_task, \
                patch.object(app_module, "cloudflare_request") as cloudflare_call:
            automation_plans.create_automation_plan(self.base_plan())
            automation_plans.list_automation_plans()

        self.assertEqual(before, table_counts())
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        dispatch_task.assert_not_called()
        cloudflare_call.assert_not_called()

    def test_safety_evaluator_classifies_high_risk_actions(self):
        cases = [
            ("deploy", "Deploy production release", "deploy"),
            ("restart", "Restart and rebuild service", "infra"),
            ("migration", "Run migration alter table", "migration"),
            ("dns", "Change DNS SSL Nginx reverse proxy", "dns"),
            ("cloudflare", "Prepare Cloudflare R2 change", "infra"),
            ("provider", "Run Gemini live ping provider call", "provider"),
            ("worker", "Run worker task execution", "worker"),
            ("mutation", "Update task status and project mutation", "mutation"),
            ("approval", "Create approval request row", "approval"),
        ]

        for label, description, approval_type in cases:
            with self.subTest(label=label):
                result = automation_plans.evaluate_automation_plan_safety(
                    self.base_plan(
                        recommended_actions=[
                            {
                                "label": label,
                                "description": description,
                                "risk_level": "low",
                                "requires_approval": False,
                                "approval_type": "none",
                            }
                        ],
                        suggested_commands=[
                            {
                                "label": "Open source detail",
                                "command": "Open DevPilot page /admin/external-sources/gpcarai",
                                "execution_allowed": False,
                            }
                        ],
                    )
                )

                self.assertEqual(result["overall_risk_level"], "high")
                self.assertIn(approval_type, result["required_approvals"])
                self.assertTrue(result["recommended_actions"][0]["requires_approval"])
                self.assertNotEqual(result["recommended_actions"][0]["approval_type"], "none")
                self.assertFalse(result["execution_allowed"])
                self.assertFalse(result["safe_to_execute"])

    def test_safety_evaluator_blocks_sensitive_markers_without_echoing_values(self):
        cases = [
            self.base_plan(objective="Use Authorization: Bearer abcdefghijk"),
            self.base_plan(recommended_actions=[{"label": "Provider", "description": "Read OPENAI_API_KEY from runtime."}]),
            self.base_plan(api_key="dp_ext_example_value"),
        ]

        for plan in cases:
            with self.subTest(plan=plan):
                result = automation_plans.evaluate_automation_plan_safety(plan)
                combined = json.dumps(result, ensure_ascii=False)

                self.assertEqual(result["overall_risk_level"], "blocked")
                self.assertIn("automation plan contains blocked sensitive content", result["blocked_by"])
                self.assertFalse(result["execution_allowed"])
                self.assertFalse(result["safe_to_execute"])
                self.assertNotIn("Authorization:", combined)
                self.assertNotIn("Bearer abcdefghijk", combined)
                self.assertNotIn("OPENAI_API_KEY", combined)
                self.assertNotIn("dp_ext_example_value", combined)
                self.assertNotIn("api_key", combined)

    def test_safety_evaluator_forces_commands_display_only(self):
        result = automation_plans.evaluate_automation_plan_safety(
            self.base_plan(
                suggested_commands=[
                    {
                        "label": "Operational command",
                        "command": "docker compose up -d devpilot",
                        "execution_allowed": True,
                    }
                ]
            )
        )

        self.assertEqual(result["overall_risk_level"], "blocked")
        self.assertIn("infra", result["required_approvals"])
        self.assertIn("execution", result["required_approvals"])
        self.assertIn("suggested command execution is not allowed in the MVP", result["blocked_by"])
        self.assertFalse(result["suggested_commands"][0]["execution_allowed"])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["safe_to_execute"])

    def test_safety_evaluator_keeps_safe_diagnostics_low_risk(self):
        result = automation_plans.evaluate_automation_plan_safety(
            self.base_plan(
                recommended_actions=[
                    {
                        "label": "Review diagnostics",
                        "description": "Open status page and read diagnostic notes.",
                        "risk_level": "low",
                        "requires_approval": False,
                        "approval_type": "none",
                    }
                ],
                suggested_commands=[
                    {
                        "label": "Open source detail",
                        "command": "Open DevPilot page /admin/external-sources/gpcarai",
                        "execution_allowed": False,
                    }
                ],
            )
        )

        self.assertEqual(result["overall_risk_level"], "low")
        self.assertEqual(result["required_approvals"], [])
        self.assertEqual(result["blocked_by"], [])
        self.assertFalse(result["approval_required"])
        self.assertEqual(result["approval_types"], [])
        self.assertEqual(result["approval_status"], "not_requested")
        self.assertIsNone(result["approval_request_id"])
        self.assertFalse(result["suggested_commands"][0]["execution_allowed"])
        self.assertTrue(any(item["name"] == "Display-only commands" and item["status"] == "pass" for item in result["safety_checks"]))

    def test_safety_evaluator_sets_disabled_approval_metadata_for_high_risk_plan(self):
        result = automation_plans.evaluate_automation_plan_safety(
            self.base_plan(
                recommended_actions=[
                    {
                        "label": "Review deployment",
                        "description": "Deploy production release after approval.",
                        "risk_level": "low",
                        "requires_approval": False,
                        "approval_type": "none",
                    }
                ],
                suggested_commands=[
                    {
                        "label": "Open source detail",
                        "command": "Open DevPilot page /admin/external-sources/gpcarai",
                        "execution_allowed": False,
                    }
                ],
            )
        )

        self.assertEqual(result["overall_risk_level"], "high")
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["approval_types"], result["required_approvals"])
        self.assertIn("deploy", result["approval_types"])
        self.assertEqual(result["approval_status"], "not_requested")
        self.assertIsNone(result["approval_request_id"])
        self.assertFalse(result["safe_to_execute"])

    def test_safety_evaluator_helpers_are_deterministic_and_side_effect_free(self):
        import app as app_module

        def table_counts():
            with app_module.app.app_context():
                return {
                    "projects": app_module.query_one("SELECT COUNT(*) AS count FROM projects")["count"],
                    "tasks": app_module.query_one("SELECT COUNT(*) AS count FROM tasks")["count"],
                    "project_phases": app_module.query_one("SELECT COUNT(*) AS count FROM project_phases")["count"],
                    "approval_requests": app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"],
                }

        plan = self.base_plan(
            recommended_actions=[
                {
                    "label": "Review status",
                    "description": "Open status page and read diagnostic notes.",
                    "risk_level": "low",
                    "requires_approval": False,
                    "approval_type": "none",
                }
            ],
            suggested_commands=[
                {
                    "label": "Open planner",
                    "command": "Open DevPilot page /admin/automation-planner",
                    "execution_allowed": False,
                }
            ],
        )

        before = table_counts()
        with patch.object(app_module, "call_gemini_generate") as gemini_call, \
                patch.object(app_module, "call_task_provider") as provider_call, \
                patch.object(app_module, "run_ai_task") as run_task, \
                patch.object(app_module, "dispatch_ai_console_task") as dispatch_task, \
                patch.object(app_module, "cloudflare_request") as cloudflare_call:
            first = automation_plans.evaluate_automation_plan_safety(plan)
            second = automation_plans.evaluate_automation_plan_safety(plan)
            approvals = automation_plans.classify_required_approvals(plan)
            blockers = automation_plans.detect_blockers(plan)
            commands = automation_plans.validate_display_only_commands(plan)

        self.assertEqual(first, second)
        self.assertEqual(approvals, [])
        self.assertEqual(blockers, [])
        self.assertFalse(commands["commands"][0]["execution_allowed"])
        self.assertEqual(before, table_counts())
        gemini_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        dispatch_task.assert_not_called()
        cloudflare_call.assert_not_called()


class AutomationPlannerExternalProjectHealthTest(unittest.TestCase):
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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.key_store_path = Path(self.temp_dir.name) / "external_api_keys.json"
        self.registry_path = Path(self.temp_dir.name) / "external_project_registry.json"
        self.events_path = Path(self.temp_dir.name) / "external_project_events.json"
        self.usage_path = Path(self.temp_dir.name) / "external_ai_usage_log.json"
        self.env_patch = patch.dict(
            os.environ,
            {
                "DEVPILOT_EXTERNAL_API_KEY_STORE_PATH": str(self.key_store_path),
                "DEVPILOT_EXTERNAL_PROJECT_REGISTRY_PATH": str(self.registry_path),
                "DEVPILOT_EXTERNAL_PROJECT_EVENTS_PATH": str(self.events_path),
                "DEVPILOT_EXTERNAL_AI_USAGE_LOG_PATH": str(self.usage_path),
                "DEVPILOT_EXTERNAL_API_KEYS": "",
            },
            clear=False,
        )
        self.env_patch.start()
        self.write_health_fixture()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def client(self):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        return client

    def write_json(self, path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_health_fixture(self):
        self.write_json(self.key_store_path, {
            "keys": [
                {
                    "id": "extkey_health",
                    "source_system": "health-source",
                    "key_prefix": "dp_ext_health",
                    "key_hash": "hash-health-source",
                    "label": "Health source",
                    "created_at": "2026-05-18 09:00:00",
                    "last_used_at": "2026-05-18 09:10:00",
                }
            ]
        })
        self.write_json(self.registry_path, {
            "projects": [
                {
                    "source_system": "health-source",
                    "external_project_id": "health-prod",
                    "name": "Health Production",
                    "project_type": "ai-saas",
                    "environment": "production",
                    "status": "active",
                    "repo_url": "https://github.com/example/health-prod",
                    "app_url": "https://health.example.test",
                    "healthcheck_url": "https://health.example.test/health",
                    "primary_domain": "health.example.test",
                    "domain_status": "approved",
                    "created_at": "2026-05-18 09:00:00",
                    "updated_at": "2026-05-18 09:15:00",
                    "last_seen_at": "2026-05-18 09:15:00",
                }
            ]
        })
        self.write_json(self.events_path, {
            "events": [
                {
                    "source_system": "health-source",
                    "external_project_id": "health-prod",
                    "event_type": "healthcheck_ok",
                    "status": "success",
                    "message": "Project is healthy",
                    "environment": "production",
                    "created_at": "2026-05-18 09:20:00",
                }
            ]
        })
        self.write_json(self.usage_path, {
            "usage": [
                {
                    "id": "usage_health",
                    "source_system": "health-source",
                    "request_id": "req-health",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "capability": "summary",
                    "status": "completed",
                    "input_chars": 10,
                    "output_chars": 2,
                    "input_token_estimate": 3,
                    "output_token_estimate": 1,
                    "created_at": "2026-05-18 09:25:00",
                }
            ]
        })

    def table_counts(self):
        with self.app.app_context():
            return {
                "projects": self.app_module.query_one("SELECT COUNT(*) AS count FROM projects")["count"],
                "tasks": self.app_module.query_one("SELECT COUNT(*) AS count FROM tasks")["count"],
                "project_phases": self.app_module.query_one("SELECT COUNT(*) AS count FROM project_phases")["count"],
                "approval_requests": self.app_module.query_one("SELECT COUNT(*) AS count FROM approval_requests")["count"],
                "handoff_logs": self.app_module.query_one("SELECT COUNT(*) AS count FROM handoff_logs")["count"],
            }

    def test_external_project_health_empty_state_requires_no_source(self):
        with patch.object(self.app_module, "ai_handoff_rows", return_value=[]):
            response = self.client().get("/api/admin/automation-planner/external-project-health")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_allowed"])
        self.assertEqual(payload["health_status"], "not_available")
        self.assertEqual(payload["risk_score"], 0)
        self.assertEqual(payload["source_system"], "")
        self.assertTrue(payload["context"]["sources"])
        self.assertTrue(payload["safety_checks"]["provider_calls_executed"] is False)

    def test_external_project_health_api_is_read_only_and_low_risk_for_healthy_fixture(self):
        before = self.table_counts()
        with patch.object(self.app_module, "ai_handoff_rows", return_value=[]) as handoff_rows:
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    with patch.object(self.app_module, "call_task_provider") as provider_call:
                        with patch.object(self.app_module, "run_ai_task") as run_task:
                            with patch.object(self.app_module, "dispatch_ai_console_task") as dispatch_task:
                                with patch.object(self.app_module, "cloudflare_request") as cloudflare_call:
                                    response = self.client().get(
                                        "/api/admin/automation-planner/external-project-health?source_system=health-source&external_project_id=health-prod"
                                    )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_allowed"])
        self.assertEqual(payload["source_system"], "health-source")
        self.assertEqual(payload["external_project_id"], "health-prod")
        self.assertEqual(payload["health_status"], "healthy")
        self.assertEqual(payload["risk_level"], "low")
        self.assertEqual(payload["risk_score"], 0)
        self.assertEqual(payload["context"]["project"]["external_project_id"], "health-prod")
        self.assertEqual(payload["context"]["usage_summary"]["success_count"], 1)
        self.assertTrue(any(item["id"] == "recent_events" and item["status"] == "pass" for item in payload["signals"]))
        self.assertTrue(all(item["execution_allowed"] is False for item in payload["recommended_actions"]))
        self.assertFalse(payload["safety_checks"]["provider_calls_executed"])
        self.assertFalse(payload["safety_checks"]["deployment_executed"])
        self.assertFalse(payload["safety_checks"]["dns_changes_executed"])
        self.assertFalse(payload["safety_checks"]["cloudflare_changes_executed"])
        self.assertFalse(payload["safety_checks"]["project_mutation_executed"])
        combined = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("key_hash", combined)
        self.assertNotIn("hash-health-source", combined)
        self.assertNotIn("Authorization", combined)
        self.assertNotIn("Bearer", combined)
        self.assertEqual(before, self.table_counts())
        handoff_rows.assert_called()
        gemini_call.assert_not_called()
        claude_call.assert_not_called()
        provider_call.assert_not_called()
        run_task.assert_not_called()
        dispatch_task.assert_not_called()
        cloudflare_call.assert_not_called()

    def test_external_project_health_missing_project_returns_blocked_without_500(self):
        with patch.object(self.app_module, "ai_handoff_rows", return_value=[]):
            response = self.client().get(
                "/api/admin/automation-planner/external-project-health?source_system=health-source&external_project_id=missing-prod"
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["health_status"], "blocked")
        self.assertEqual(payload["risk_level"], "blocked")
        self.assertIn("external_project_id was not found for this source", payload["blockers"])
        self.assertTrue(any(item["id"] == "project_selected" and item["status"] == "fail" for item in payload["signals"]))

    def test_external_project_health_page_owner_admin_and_anonymous_boundary(self):
        anonymous_page = self.app.test_client().get("/admin/automation-planner/external-project-health")
        self.assertEqual(anonymous_page.status_code, 302)
        self.assertIn("/login", anonymous_page.headers.get("Location", ""))

        anonymous_api = self.app.test_client().get("/api/admin/automation-planner/external-project-health")
        self.assertEqual(anonymous_api.status_code, 403)

        with patch.object(self.app_module, "ai_handoff_rows", return_value=[]):
            response = self.client().get(
                "/admin/automation-planner/external-project-health?source_system=health-source&external_project_id=health-prod"
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn("External Project Health", body)
        self.assertIn("health-source", body)
        self.assertIn("health-prod", body)
        self.assertIn("healthy", body)
        self.assertIn("Planning-only MVP", body)
        self.assertNotIn("key_hash", body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("Bearer", body)

    def test_approval_object_preview_page_owner_admin_and_anonymous_boundary(self):
        anonymous_page = self.app.test_client().get("/admin/approval-object-preview")
        self.assertEqual(anonymous_page.status_code, 302)
        self.assertIn("/login", anonymous_page.headers.get("Location", ""))

        response = self.client().get("/admin/approval-object-preview")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn("Approval Object Preview", body)
        self.assertIn("DRAFT PREVIEW ONLY", body)
        self.assertIn("NO APPROVAL CREATED", body)
        self.assertIn("NO EXECUTION", body)
        self.assertNotIn("key_hash", body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("Bearer", body)

    def test_approval_object_preview_api_is_draft_only_and_has_no_side_effects(self):
        before = self.table_counts()
        with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
            with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                with patch.object(self.app_module, "cloudflare_request") as cloudflare_call:
                    with patch.object(self.app_module, "create_approval_request") as approval_create:
                        external_ai_response = self.client().post("/api/admin/approval-object-preview", json={
                            "type": "external_ai_live_verification",
                            "title": "Preview Gemini live verification",
                            "source_surface": "/admin/external-ai-live-verification-gate",
                            "risk_level": "high",
                            "target": {"provider": "gemini", "model": "gemini-2.5-flash"},
                            "dry_run_snapshot": {"preview_only": True},
                        })
                        domain_response = self.client().post("/api/admin/approval-object-preview", json={
                            "type": "domain_execution",
                            "title": "Preview domain execution",
                            "source_surface": "/admin/domain-execution-dry-run",
                            "risk_level": "critical",
                            "target": {"domain": "aioffice.com.tw"},
                            "dry_run_snapshot": {"planned_dns_records": 27},
                        })

        for response in (external_ai_response, domain_response):
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertTrue(payload["draft_only"])
            self.assertFalse(payload["approval_object_created"])
            self.assertFalse(payload["execution_allowed"])
            self.assertFalse(payload["provider_calls_executed"])
            self.assertFalse(payload["approval_requests_created"])
            self.assertFalse(payload["usage_logs_written"])
            self.assertFalse(payload["generation_results_written"])
            self.assertEqual(payload["approval_preview"]["id"], "preview_only")
            self.assertEqual(payload["approval_preview"]["status"], "draft_preview")
            self.assertEqual(payload["approval_preview"]["execution_mode"], "none")
            self.assertEqual(payload["approval_preview"]["audit_events"], [])
            self.assertFalse(payload["approval_preview"]["safety_checks"]["approval_request_created"])
            self.assertFalse(payload["approval_preview"]["safety_checks"]["usage_log_written"])
            self.assertFalse(payload["approval_preview"]["safety_checks"]["generation_result_written"])
            combined = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            self.assertNotIn("key_hash", combined)
            self.assertNotIn("Authorization", combined)
            self.assertNotIn("Bearer", combined)

        external_roles = {item["role"] for item in external_ai_response.get_json()["approval_preview"]["required_approvals"]}
        self.assertEqual(external_roles, {"product_owner", "engineering_owner", "operations_owner", "security_reviewer"})
        domain_roles = {item["role"] for item in domain_response.get_json()["approval_preview"]["required_approvals"]}
        self.assertEqual(domain_roles, {"domain_owner", "product_owner", "operations_owner", "dns_cloudflare_owner", "security_reviewer"})
        self.assertEqual(before, self.table_counts())
        gemini_call.assert_not_called()
        claude_call.assert_not_called()
        cloudflare_call.assert_not_called()
        approval_create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
