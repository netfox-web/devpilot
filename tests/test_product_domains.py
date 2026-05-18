import unittest
from copy import deepcopy
from unittest.mock import patch

from services import product_domains


class ProductDomainCatalogTest(unittest.TestCase):
    def test_catalog_validation_passes(self):
        validation = product_domains.validate_product_domain_catalog()
        self.assertTrue(validation["ok"], validation)
        self.assertEqual(validation["errors"], [])

    def test_each_product_has_one_official_domain(self):
        for suite in product_domains.PRODUCT_DOMAIN_CATALOG["suites"]:
            for product in suite["products"]:
                official = []
                for module in product["modules"]:
                    official.extend([domain for domain in module["domains"] if domain["role"] == "official"])
                self.assertEqual(len(official), 1, product["key"])
                self.assertEqual(official[0]["domain"], product["official_domain"])

    def test_official_domains_are_unique(self):
        official_domains = []
        for _suite, _product, _module, domain in product_domains.iter_product_domains():
            if domain["role"] == "official":
                official_domains.append(domain["domain"])
        self.assertEqual(len(official_domains), len(set(official_domains)))

    def test_redirect_domains_have_target_domain(self):
        for _suite, product, _module, domain in product_domains.iter_product_domains():
            if domain["role"] == "redirect":
                self.assertEqual(domain.get("target_domain"), product["official_domain"], domain["domain"])

    def test_domain_lookup_redirect(self):
        result = product_domains.product_domain_lookup("crmai.tw")
        self.assertIsNotNone(result)
        self.assertEqual(result["product"]["key"], "aicrm")
        self.assertEqual(result["role"], "redirect")
        self.assertEqual(result["target_domain"], "aicrm.com.tw")

    def test_domain_lookup_campaign(self):
        result = product_domains.product_domain_lookup("aiad.fun")
        self.assertIsNotNone(result)
        self.assertEqual(result["product"]["key"], "aiad")
        self.assertEqual(result["role"], "campaign")
        self.assertEqual(result["target_domain"], "aiad.com.tw")

    def test_brand_hub_lookup(self):
        result = product_domains.product_domain_lookup("aioffice.com.tw")
        self.assertIsNotNone(result)
        self.assertEqual(result["scope"], "brand_hub")
        self.assertIsNone(result["product"])
        self.assertEqual(result["role"], "official")

    def test_brand_hub_redirect_lookup(self):
        result = product_domains.product_domain_lookup("aioffice.tw")
        self.assertIsNotNone(result)
        self.assertEqual(result["scope"], "brand_hub")
        self.assertEqual(result["role"], "redirect")
        self.assertEqual(result["target_domain"], "aioffice.com.tw")

    def test_summary_counts(self):
        summary = product_domains.product_domain_summary()
        self.assertEqual(summary["brand_key"], "ai_office")
        self.assertEqual(summary["suite_count"], 7)
        self.assertEqual(summary["product_count"], 26)
        self.assertEqual(summary["domain_count"], 60)

    def test_role_filter(self):
        tree = product_domains.product_domain_tree({"role": "campaign"})
        self.assertEqual(tree["summary"]["domain_count"], 1)
        self.assertEqual(tree["summary"]["role_counts"], {"campaign": 1})
        self.assertEqual(tree["suites"][0]["products"][0]["key"], "aiad")
        self.assertEqual(tree["suites"][0]["products"][0]["modules"][0]["domains"][0]["domain"], "aiad.fun")

    def test_q_search(self):
        tree = product_domains.product_domain_tree({"q": "crmai"})
        domains = [
            domain["domain"]
            for suite in tree["suites"]
            for product in suite["products"]
            for module in product["modules"]
            for domain in module["domains"]
        ]
        self.assertEqual(set(domains), {"crmai.com.tw", "crmai.tw"})

    def test_suite_filter(self):
        tree = product_domains.product_domain_tree({"suite": "commerce_ai"})
        self.assertEqual([suite["key"] for suite in tree["suites"]], ["commerce_ai"])
        self.assertEqual(tree["summary"]["product_count"], 2)

    def test_redirect_plan_excludes_official_domains(self):
        plan = product_domains.product_domain_redirect_plan()
        sources = {item["source_domain"] for item in plan["items"]}
        official_sources = {
            domain["domain"]
            for _suite, _product, _module, domain in product_domains.iter_product_domains()
            if domain["role"] == "official"
        }
        official_sources.add("aioffice.com.tw")
        self.assertFalse(sources.intersection(official_sources))

    def test_redirect_plan_contains_crmai_redirect(self):
        plan = product_domains.product_domain_redirect_plan()
        match = [item for item in plan["items"] if item["source_domain"] == "crmai.tw"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["target_domain"], "aicrm.com.tw")
        self.assertEqual(match[0]["role"], "redirect")
        self.assertEqual(match[0]["redirect_type"], "301")

    def test_redirect_plan_contains_brand_hub_redirect(self):
        plan = product_domains.product_domain_redirect_plan()
        match = [item for item in plan["items"] if item["source_domain"] == "aioffice.tw"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["target_domain"], "aioffice.com.tw")
        self.assertEqual(match[0]["scope"], "brand_hub")

    def test_redirect_plan_contains_campaign(self):
        plan = product_domains.product_domain_redirect_plan()
        match = [item for item in plan["items"] if item["source_domain"] == "aiad.fun"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["target_domain"], "aiad.com.tw")
        self.assertEqual(match[0]["role"], "campaign")

    def test_redirect_plan_role_filter(self):
        plan = product_domains.product_domain_redirect_plan({"role": "campaign"})
        self.assertEqual(plan["summary"]["total_redirect_rules"], 1)
        self.assertEqual(plan["summary"]["campaign_count"], 1)
        self.assertEqual(plan["items"][0]["source_domain"], "aiad.fun")

    def test_redirect_plan_q_search(self):
        plan = product_domains.product_domain_redirect_plan({"q": "crmai"})
        self.assertEqual({item["source_domain"] for item in plan["items"]}, {"crmai.com.tw", "crmai.tw"})

    def test_redirect_plan_validation_success(self):
        plan = product_domains.product_domain_redirect_plan()
        self.assertTrue(plan["validation"]["ok"], plan["validation"])
        self.assertEqual(plan["validation"]["errors"], [])

    def test_redirect_plan_summary_counts(self):
        plan = product_domains.product_domain_redirect_plan()
        self.assertEqual(plan["summary"]["total_redirect_rules"], 33)
        self.assertEqual(plan["summary"]["redirect_count"], 31)
        self.assertEqual(plan["summary"]["campaign_count"], 1)
        self.assertEqual(plan["summary"]["brand_hub_redirect_count"], 1)

    def test_redirect_plan_export_validation_failure(self):
        catalog = deepcopy(product_domains.PRODUCT_DOMAIN_CATALOG)
        catalog["suites"][0]["products"][0]["modules"][0]["domains"][1]["target_domain"] = ""
        result = product_domains.product_domain_redirect_plan_export("csv", catalog=catalog)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "redirect_plan_validation_failed")
        self.assertNotIn("body", result)


class ProductDomainApiTest(unittest.TestCase):
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

    def test_lookup_unknown_domain_endpoint(self):
        response = self.client().get("/api/product-domains/lookup?domain=unknown.example")
        self.assertEqual(response.status_code, 404)
        payload = response.get_json()
        self.assertEqual(payload["error"], "domain_not_found")

    def test_validate_endpoint_success(self):
        response = self.client().get("/api/product-domains/validate")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation"]["ok"])

    def test_catalog_endpoint_filters(self):
        response = self.client().get("/api/product-domains?role=campaign&q=aiad")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["catalog"]["summary"]["domain_count"], 1)
        self.assertEqual(payload["catalog"]["summary"]["role_counts"], {"campaign": 1})

    def test_redirect_plan_endpoint_filters(self):
        response = self.client().get("/api/product-domains/redirect-plan?role=campaign&q=aiad")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        plan = payload["redirect_plan"]
        self.assertTrue(plan["validation"]["ok"])
        self.assertEqual(plan["summary"]["total_redirect_rules"], 1)
        self.assertEqual(plan["items"][0]["source_domain"], "aiad.fun")

    def test_redirect_plan_json_export_success(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=json&q=crmai")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("items", payload)
        self.assertEqual(payload["summary"]["total_redirect_rules"], 2)

    def test_redirect_plan_csv_export_contains_crmai(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=csv&q=crmai")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("crmai.tw,aicrm.com.tw", text)

    def test_redirect_plan_nginx_export_contains_crmai(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=nginx&q=crmai.tw")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("server_name crmai.tw", text)
        self.assertIn("return 301 https://aicrm.com.tw$request_uri", text)

    def test_redirect_plan_cloudflare_bulk_export_contains_crmai(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=cloudflare-bulk&q=crmai.tw")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload[0]["source"], "crmai.tw")
        self.assertEqual(payload[0]["target"], "aicrm.com.tw")
        self.assertEqual(payload[0]["status_code"], 301)
        self.assertTrue(payload[0]["preserve_path"])

    def test_redirect_plan_export_role_filter(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=csv&role=campaign")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("aiad.fun,aiad.com.tw,campaign", text)
        self.assertNotIn("crmai.tw", text)

    def test_redirect_plan_export_unknown_format(self):
        response = self.client().get("/api/product-domains/redirect-plan/export?format=toml")
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["error"], "unknown_export_format")

    def test_controlled_deploy_routes_do_not_500(self):
        routes = [
            "/product-domains",
            "/admin/product-domain-launch-plan",
            "/api/product-domains",
            "/api/admin/product-domain-launch-plan",
            "/api/product-domains/validate",
            "/api/product-domains/redirect-plan",
            "/api/product-domains/redirect-plan/export?format=json",
            "/api/product-domains/redirect-plan/export?format=csv",
            "/api/product-domains/redirect-plan/export?format=nginx",
            "/api/product-domains/redirect-plan/export?format=cloudflare-bulk",
        ]
        client = self.client()
        for route in routes:
            with self.subTest(route=route):
                response = client.get(route)
                self.assertNotEqual(response.status_code, 500)
                self.assertEqual(response.status_code, 200)

    def test_product_domain_launch_plan_api_is_read_only(self):
        with patch.object(self.app_module, "cloudflare_request") as cloudflare_request:
            with patch.object(self.app_module, "call_gemini_generate") as gemini_call:
                with patch.object(self.app_module, "call_claude_external_ai_generate") as claude_call:
                    response = self.client().get("/api/admin/product-domain-launch-plan")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["dns_write_enabled"])
        self.assertFalse(payload["cloudflare_write_enabled"])
        self.assertFalse(payload["nginx_write_enabled"])
        self.assertFalse(payload["ssl_write_enabled"])
        self.assertFalse(payload["deploy_enabled"])
        self.assertEqual(payload["brand"]["name"], "AI Office")
        self.assertEqual(payload["brand"]["key"], "ai_office")
        self.assertEqual(payload["brand"]["official_domain"], "aioffice.com.tw")
        self.assertEqual(payload["brand"]["redirect_domain"], "aioffice.tw")
        self.assertEqual(payload["brand"]["canonical_action"], "brand_hub_canonical")
        self.assertEqual(payload["summary"]["suite_count"], 7)
        self.assertEqual(payload["summary"]["product_count"], 26)
        self.assertEqual(payload["summary"]["domain_count"], 60)
        self.assertEqual(payload["summary"]["official_count"], 27)
        self.assertEqual(payload["summary"]["redirect_count"], 32)
        self.assertEqual(payload["summary"]["campaign_count"], 1)
        self.assertEqual(payload["launch_defaults"]["launch_wave"], "pending_analysis")
        self.assertFalse(payload["launch_defaults"]["execution_allowed"])
        self.assertEqual(len(payload["products"]), 26)
        self.assertTrue(all(item["launch_wave"] == "pending_analysis" for item in payload["products"]))
        self.assertTrue(all(item["execution_allowed"] is False for item in payload["products"]))
        self.assertTrue(payload["analyst_questions"])
        self.assertTrue(payload["safety"]["no_dns_write"])
        self.assertTrue(payload["safety"]["no_cloudflare_write"])
        self.assertTrue(payload["safety"]["no_nginx_write"])
        self.assertTrue(payload["safety"]["no_ssl_write"])
        self.assertTrue(payload["safety"]["no_deploy"])
        self.assertTrue(payload["safety"]["no_provider_live_call"])
        product_keys = {item["product_key"] for item in payload["products"]}
        self.assertIn("aicrm", product_keys)
        self.assertIn("aiad", product_keys)
        aiad = next(item for item in payload["products"] if item["product_key"] == "aiad")
        self.assertEqual(aiad["official_domain"], "aiad.com.tw")
        self.assertEqual(aiad["campaign_domains"][0]["domain"], "aiad.fun")
        combined = str(payload)
        self.assertNotIn("Authorization", combined)
        self.assertNotIn("Bearer", combined)
        self.assertNotIn("key_hash", combined)
        cloudflare_request.assert_not_called()
        gemini_call.assert_not_called()
        claude_call.assert_not_called()

    def test_product_domain_launch_plan_page_owner_admin_and_anonymous_boundary(self):
        anonymous = self.app.test_client().get("/admin/product-domain-launch-plan")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.headers.get("Location", ""))

        response = self.client().get("/admin/product-domain-launch-plan")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn("Product Domain Launch Plan", body)
        self.assertIn("AI Office", body)
        self.assertIn("aioffice.com.tw", body)
        self.assertIn("pending_analysis", body)
        self.assertIn("execution_allowed=false", body)
        self.assertIn("AICRM", body)
        self.assertIn("AIAD", body)
        self.assertIn("aiad.fun", body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("Bearer", body)
        self.assertNotIn("key_hash", body)


if __name__ == "__main__":
    unittest.main()
