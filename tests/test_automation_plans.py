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
        self.assertFalse(result["suggested_commands"][0]["execution_allowed"])
        self.assertTrue(any(item["name"] == "Display-only commands" and item["status"] == "pass" for item in result["safety_checks"]))

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


if __name__ == "__main__":
    unittest.main()
