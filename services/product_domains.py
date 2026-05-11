from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import io
import json


VALID_DOMAIN_ROLES = {"official", "redirect", "campaign", "infra", "reserved"}
BRAND_KEY = "ai_office"
BRAND_NAME = "AI Office"
BRAND_HUB_DOMAIN = "aioffice.com.tw"


def _domain(value: str) -> str:
    return str(value or "").strip().lower().strip(".")


def _token(value: str) -> str:
    return str(value or "").strip().lower()


def _matches(value: str, expected: str) -> bool:
    expected = _token(expected)
    if not expected:
        return True
    return _token(value) == expected


def _domain_entry(domain: str, role: str, target_domain: str = "", note: str = "") -> dict:
    entry = {"domain": _domain(domain), "role": role}
    if target_domain:
        entry["target_domain"] = _domain(target_domain)
    if note:
        entry["note"] = note
    return entry


def _product(
    name: str,
    key: str,
    official: str,
    *,
    redirects: list[str] | None = None,
    campaign: list[str] | None = None,
    infra: list[str] | None = None,
    reserved: list[str] | None = None,
    module_name: str = "Public Web",
    module_key: str = "public_web",
) -> dict:
    official_domain = _domain(official)
    domains = [_domain_entry(official_domain, "official")]
    for domain in redirects or []:
        domains.append(_domain_entry(domain, "redirect", official_domain))
    for domain in campaign or []:
        domains.append(_domain_entry(domain, "campaign", official_domain))
    for domain in infra or []:
        domains.append(_domain_entry(domain, "infra"))
    for domain in reserved or []:
        domains.append(_domain_entry(domain, "reserved"))
    return {
        "name": name,
        "key": key,
        "official_domain": official_domain,
        "modules": [
            {
                "name": module_name,
                "key": module_key,
                "domains": domains,
            }
        ],
    }


PRODUCT_DOMAIN_CATALOG = {
    "brand": {
        "name": BRAND_NAME,
        "key": BRAND_KEY,
        "hub_domain": BRAND_HUB_DOMAIN,
        "domains": [
            _domain_entry(BRAND_HUB_DOMAIN, "official", note="Brand Hub"),
            _domain_entry("aioffice.tw", "redirect", BRAND_HUB_DOMAIN, note="Brand Hub redirect"),
        ],
    },
    "suites": [
        {
            "name": "Business AI",
            "key": "business_ai",
            "products": [
                _product("AICRM", "aicrm", "aicrm.com.tw", redirects=["crmai.com.tw", "crmai.tw"]),
                _product("AIERP", "aierp", "aierp.com.tw", redirects=["aierp.tw"]),
                _product("AIHRM", "aihrm", "aihrm.com.tw", redirects=["aihrm.tw", "aihrm.net"]),
                _product("AISales", "aisales", "aisales.com.tw"),
            ],
        },
        {
            "name": "Marketing AI",
            "key": "marketing_ai",
            "products": [
                _product("WebAI", "webai", "webai.tw", redirects=["webai.net.tw"]),
                _product("AIAD", "aiad", "aiad.com.tw", redirects=["aiad.tw", "aiad.net.tw"], campaign=["aiad.fun"]),
                _product("AIKOL", "aikol", "aikol.com.tw", redirects=["aikol.tw", "kolai.tw"]),
                _product("AIImage", "aiimage", "aiimage.com.tw", redirects=["aiimage.tw", "imageai.com.tw", "imageai.tw"]),
            ],
        },
        {
            "name": "Commerce AI",
            "key": "commerce_ai",
            "products": [
                _product("AIShopping", "aishopping", "aishopping.com.tw", redirects=["aishopping.tw", "shopai.com.tw", "shopai.tw"]),
                _product("AIPOS", "aipos", "aipos.tw"),
            ],
        },
        {
            "name": "Service AI",
            "key": "service_ai",
            "products": [
                _product("AIBooking", "aibooking", "aibooking.tw", redirects=["bookingai.com.tw", "bookingai.tw"]),
                _product("LiveAI", "liveai", "liveai.com.tw", redirects=["liveai.tw", "ailive.tw"]),
                _product("AIChat", "aichat", "aichat.tw", redirects=["aichat.net.tw"]),
            ],
        },
        {
            "name": "Industry AI",
            "key": "industry_ai",
            "products": [
                _product("TruckAI", "truckai", "truckai.com.tw", redirects=["truckai.tw", "truckai.net"]),
                _product("CarAI", "carai", "carai.tw"),
                _product("CleanAI", "cleanai", "cleanai.com.tw", redirects=["cleanai.tw"]),
                _product("MoveAI", "moveai", "moveai.com.tw", redirects=["moveai.tw"]),
                _product("FixAI", "fixai", "fixai.com.tw", redirects=["fixai.tw"]),
            ],
        },
        {
            "name": "Creative AI",
            "key": "creative_ai",
            "products": [
                _product("PaintAI", "paintai", "paintai.com.tw", redirects=["paintai.tw", "paintai.net"]),
                _product("PrintAI", "printai", "printai.com.tw", redirects=["printai.tw"]),
            ],
        },
        {
            "name": "Infrastructure AI",
            "key": "infrastructure_ai",
            "products": [
                _product("AISystem", "aisystem", "aisystem.com.tw", redirects=["aisystem.tw"]),
                _product("AICenter", "aicenter", "aicenter.com.tw", module_name="Infrastructure Endpoint", module_key="infrastructure_endpoint"),
                _product("AIServer", "aiserver", "aiserver.com.tw", module_name="Infrastructure Endpoint", module_key="infrastructure_endpoint"),
                _product("AITV", "aitv", "aitv.com.tw"),
                _product("AIVideo", "aivideo", "aivideo.com.tw"),
                _product("OEMAI", "oemai", "oemai.com.tw", redirects=["oemai.tw"]),
            ],
        },
    ],
}


def product_domain_tree(filters: dict | None = None) -> dict:
    tree = filtered_product_domain_catalog(filters)
    tree["summary"] = product_domain_summary(tree)
    tree["validation"] = validate_product_domain_catalog(PRODUCT_DOMAIN_CATALOG)
    tree["filters"] = normalize_product_domain_filters(filters)
    return tree


def normalize_product_domain_filters(filters: dict | None = None) -> dict:
    filters = filters or {}
    role = _token(filters.get("role", ""))
    if role == "all":
        role = ""
    if role and role not in VALID_DOMAIN_ROLES:
        role = ""
    return {
        "role": role,
        "suite": _token(filters.get("suite", "")),
        "product": _token(filters.get("product", "")),
        "q": _token(filters.get("q", "")),
    }


def product_domain_options(catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    suites = [{"key": suite.get("key"), "name": suite.get("name")} for suite in catalog.get("suites", [])]
    products = []
    for suite in catalog.get("suites", []):
        for product in suite.get("products", []):
            products.append({
                "key": product.get("key"),
                "name": product.get("name"),
                "suite_key": suite.get("key"),
                "suite_name": suite.get("name"),
            })
    return {
        "roles": ["all", *sorted(VALID_DOMAIN_ROLES)],
        "suites": suites,
        "products": products,
    }


def product_domain_redirect_plan(filters: dict | None = None, catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    filters = normalize_product_domain_filters(filters)
    rows = []

    for item in iter_all_domains(catalog):
        domain = item["domain"]
        role = domain.get("role")
        if role not in {"redirect", "campaign"}:
            continue
        if not _item_matches_filters(item.get("suite"), item.get("product"), domain, filters):
            continue
        source_domain = _domain(domain.get("domain"))
        target_domain = _domain(domain.get("target_domain"))
        scope = item.get("scope")
        notes = domain.get("note") or ""
        if scope == "brand_hub":
            notes = notes or "Brand Hub redirect"
        elif role == "campaign":
            notes = notes or "Campaign domain redirect plan"
        else:
            notes = notes or "Product redirect plan"
        rows.append({
            "source_domain": source_domain,
            "target_domain": target_domain,
            "role": role,
            "product": "" if not item.get("product") else item["product"].get("name", ""),
            "product_key": "" if not item.get("product") else item["product"].get("key", ""),
            "suite": "" if not item.get("suite") else item["suite"].get("name", ""),
            "suite_key": "" if not item.get("suite") else item["suite"].get("key", ""),
            "brand": item["brand"].get("name", BRAND_NAME),
            "brand_key": item["brand"].get("key", BRAND_KEY),
            "redirect_type": "301",
            "status": "ready",
            "notes": notes,
            "scope": scope,
        })

    summary = product_domain_redirect_plan_summary(rows)
    validation = validate_product_domain_redirect_plan(rows, catalog)
    if not validation["ok"]:
        invalid_sources = {item.get("source_domain") for item in validation["items"]}
        for row in rows:
            if row["source_domain"] in invalid_sources:
                row["status"] = "invalid"
    return {
        "items": rows,
        "summary": summary,
        "validation": validation,
        "filters": filters,
    }


def product_domain_redirect_plan_summary(rows: list[dict]) -> dict:
    return {
        "total_redirect_rules": len(rows),
        "redirect_count": sum(1 for row in rows if row.get("role") == "redirect" and row.get("scope") != "brand_hub"),
        "campaign_count": sum(1 for row in rows if row.get("role") == "campaign"),
        "brand_hub_redirect_count": sum(1 for row in rows if row.get("scope") == "brand_hub"),
    }


def product_domain_redirect_plan_json_export(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)


def product_domain_redirect_plan_csv_export(plan: dict) -> str:
    output = io.StringIO()
    fieldnames = [
        "source_domain",
        "target_domain",
        "role",
        "product",
        "suite",
        "brand",
        "redirect_type",
        "status",
        "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for item in plan.get("items", []):
        writer.writerow(item)
    return output.getvalue()


def product_domain_redirect_plan_nginx_export(plan: dict) -> str:
    lines = [
        "# Generated from DevPilot Product Domain Redirect Plan.",
        "# Read-only template. Review manually before applying to Nginx.",
        "",
    ]
    for item in plan.get("items", []):
        lines.extend([
            "server {",
            f"    server_name {item.get('source_domain')};",
            f"    return {item.get('redirect_type') or '301'} https://{item.get('target_domain')}$request_uri;",
            "}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def product_domain_redirect_plan_cloudflare_bulk_export(plan: dict) -> str:
    rows = []
    for item in plan.get("items", []):
        rows.append({
            "source": item.get("source_domain"),
            "target": item.get("target_domain"),
            "status_code": int(item.get("redirect_type") or 301),
            "preserve_path": True,
            "role": item.get("role"),
            "product": item.get("product"),
            "suite": item.get("suite"),
        })
    return json.dumps(rows, ensure_ascii=False, indent=2)


def product_domain_redirect_plan_export(export_format: str, filters: dict | None = None, catalog: dict | None = None) -> dict:
    fmt = _token(export_format or "json")
    if fmt not in {"json", "csv", "nginx", "cloudflare-bulk"}:
        return {"ok": False, "error": "unknown_export_format", "status_code": 400}
    plan = product_domain_redirect_plan(filters, catalog)
    if not plan.get("validation", {}).get("ok"):
        return {
            "ok": False,
            "error": "redirect_plan_validation_failed",
            "validation": plan.get("validation"),
            "status_code": 400,
        }
    if fmt == "json":
        return {
            "ok": True,
            "body": product_domain_redirect_plan_json_export(plan),
            "mimetype": "application/json",
            "filename": "product_domain_redirect_plan.json",
        }
    if fmt == "csv":
        return {
            "ok": True,
            "body": product_domain_redirect_plan_csv_export(plan),
            "mimetype": "text/csv",
            "filename": "product_domain_redirect_plan.csv",
        }
    if fmt == "nginx":
        return {
            "ok": True,
            "body": product_domain_redirect_plan_nginx_export(plan),
            "mimetype": "text/plain",
            "filename": "product_domain_redirect_plan.nginx.conf",
        }
    return {
        "ok": True,
        "body": product_domain_redirect_plan_cloudflare_bulk_export(plan),
        "mimetype": "application/json",
        "filename": "product_domain_redirect_plan_cloudflare_bulk.json",
    }


def validate_product_domain_redirect_plan(rows: list[dict] | None = None, catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    rows = product_domain_redirect_plan({}, catalog)["items"] if rows is None else rows
    known_domains = {_domain(item["domain"].get("domain")) for item in iter_all_domains(catalog)}
    errors = []
    warnings = []
    invalid_items = []
    for row in rows:
        source = _domain(row.get("source_domain"))
        target = _domain(row.get("target_domain"))
        role = row.get("role")
        notes = str(row.get("notes") or "")
        item_errors = []
        if role not in {"redirect", "campaign"}:
            item_errors.append("redirect plan only supports redirect or campaign roles")
        if not target:
            item_errors.append("target_domain is required")
        if source and target and source == target:
            item_errors.append("source_domain cannot equal target_domain")
        if target and target not in known_domains and "external" not in notes.lower():
            item_errors.append("target_domain is not present in catalog")
        if role == "campaign":
            warnings.append(f"{source}: campaign domain is planned separately from normal redirects")
        for error in item_errors:
            errors.append(f"{source}: {error}")
        if item_errors:
            invalid_items.append({"source_domain": source, "errors": item_errors})
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "items": invalid_items,
    }


def _item_matches_filters(suite: dict | None, product: dict | None, domain: dict, filters: dict) -> bool:
    if filters["role"] and domain.get("role") != filters["role"]:
        return False
    if filters["suite"]:
        if not suite or not (_matches(suite.get("key"), filters["suite"]) or _matches(suite.get("name"), filters["suite"])):
            return False
    if filters["product"]:
        if not product or not (_matches(product.get("key"), filters["product"]) or _matches(product.get("name"), filters["product"])):
            return False
    query = filters["q"]
    if not query:
        return True
    haystack = [
        domain.get("domain", ""),
        domain.get("target_domain", ""),
        domain.get("role", ""),
        "" if not product else product.get("name", ""),
        "" if not product else product.get("key", ""),
        "" if not suite else suite.get("name", ""),
        "" if not suite else suite.get("key", ""),
        BRAND_NAME,
        BRAND_KEY,
    ]
    return any(query in _token(value) for value in haystack)


def filtered_product_domain_catalog(filters: dict | None = None, catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    filters = normalize_product_domain_filters(filters)
    filtered = {
        "brand": deepcopy(catalog.get("brand", {})),
        "suites": [],
    }
    brand_domains = []
    for domain in catalog.get("brand", {}).get("domains", []):
        if _item_matches_filters(None, None, domain, filters):
            brand_domains.append(deepcopy(domain))
    filtered["brand"]["domains"] = brand_domains

    for suite in catalog.get("suites", []):
        suite_copy = {key: deepcopy(value) for key, value in suite.items() if key != "products"}
        suite_copy["products"] = []
        for product in suite.get("products", []):
            product_copy = {key: deepcopy(value) for key, value in product.items() if key != "modules"}
            product_copy["modules"] = []
            for module in product.get("modules", []):
                module_copy = {key: deepcopy(value) for key, value in module.items() if key != "domains"}
                module_copy["domains"] = [
                    deepcopy(domain)
                    for domain in module.get("domains", [])
                    if _item_matches_filters(suite, product, domain, filters)
                ]
                if module_copy["domains"]:
                    product_copy["modules"].append(module_copy)
            if product_copy["modules"]:
                suite_copy["products"].append(product_copy)
        if suite_copy["products"]:
            filtered["suites"].append(suite_copy)
    return filtered


def iter_product_domains(catalog: dict | None = None):
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    for suite in catalog.get("suites", []):
        for product in suite.get("products", []):
            for module in product.get("modules", []):
                for domain in module.get("domains", []):
                    yield suite, product, module, domain


def iter_all_domains(catalog: dict | None = None):
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    brand = catalog.get("brand", {})
    for domain in brand.get("domains", []):
        yield {
            "brand": brand,
            "suite": None,
            "product": None,
            "module": None,
            "domain": domain,
            "scope": "brand_hub",
        }
    for suite, product, module, domain in iter_product_domains(catalog):
        yield {
            "brand": catalog.get("brand", {}),
            "suite": suite,
            "product": product,
            "module": module,
            "domain": domain,
            "scope": "product",
        }


def product_domain_lookup(domain_name: str, catalog: dict | None = None) -> dict | None:
    wanted = _domain(domain_name)
    if not wanted:
        return None
    for item in iter_all_domains(catalog):
        domain = item["domain"]
        if _domain(domain.get("domain")) == wanted:
            return {
                "brand": {
                    "name": item["brand"].get("name"),
                    "key": item["brand"].get("key"),
                    "hub_domain": item["brand"].get("hub_domain"),
                },
                "suite": None if not item.get("suite") else {
                    "name": item["suite"].get("name"),
                    "key": item["suite"].get("key"),
                },
                "product": None if not item.get("product") else {
                    "name": item["product"].get("name"),
                    "key": item["product"].get("key"),
                    "official_domain": item["product"].get("official_domain"),
                },
                "module": None if not item.get("module") else {
                    "name": item["module"].get("name"),
                    "key": item["module"].get("key"),
                },
                "domain": deepcopy(domain),
                "role": domain.get("role"),
                "target_domain": domain.get("target_domain", ""),
                "scope": item.get("scope"),
            }
    return None


def product_domain_summary(catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    suites = catalog.get("suites", [])
    products = [product for suite in suites for product in suite.get("products", [])]
    all_domains = [item["domain"] for item in iter_all_domains(catalog)]
    role_counts = Counter(domain.get("role") or "" for domain in all_domains)
    return {
        "brand": catalog.get("brand", {}).get("name"),
        "brand_key": catalog.get("brand", {}).get("key"),
        "brand_hub": catalog.get("brand", {}).get("hub_domain"),
        "suite_count": len(suites),
        "product_count": len(products),
        "domain_count": len(all_domains),
        "role_counts": dict(sorted(role_counts.items())),
    }


def validate_product_domain_catalog(catalog: dict | None = None) -> dict:
    catalog = catalog or PRODUCT_DOMAIN_CATALOG
    errors: list[str] = []
    warnings: list[str] = []
    seen_domains: dict[str, str] = {}
    official_domains: dict[str, str] = {}

    for item in iter_all_domains(catalog):
        domain = item["domain"]
        domain_name = _domain(domain.get("domain"))
        role = domain.get("role")
        owner = "brand_hub"
        if item.get("product"):
            owner = item["product"].get("key") or item["product"].get("name") or "unknown_product"
        if not domain_name:
            errors.append(f"{owner}: domain is required")
            continue
        if role not in VALID_DOMAIN_ROLES:
            errors.append(f"{domain_name}: invalid role {role!r}")
        if domain_name in seen_domains:
            errors.append(f"{domain_name}: duplicate domain in {owner} and {seen_domains[domain_name]}")
        seen_domains[domain_name] = owner
        if role == "official":
            if domain_name in official_domains:
                errors.append(f"{domain_name}: duplicate official domain")
            official_domains[domain_name] = owner
        if role == "redirect" and not _domain(domain.get("target_domain")):
            errors.append(f"{domain_name}: redirect domain must define target_domain")
        if role == "campaign" and not _domain(domain.get("target_domain")):
            warnings.append(f"{domain_name}: campaign domain has no target_domain")

    for suite in catalog.get("suites", []):
        for product in suite.get("products", []):
            official = []
            for module in product.get("modules", []):
                official.extend([domain for domain in module.get("domains", []) if domain.get("role") == "official"])
            product_key = product.get("key") or product.get("name")
            if len(official) != 1:
                errors.append(f"{product_key}: product must have exactly one official domain, found {len(official)}")
                continue
            official_domain = _domain(official[0].get("domain"))
            if _domain(product.get("official_domain")) != official_domain:
                errors.append(f"{product_key}: official_domain does not match official domain entry")
            for module in product.get("modules", []):
                for domain in module.get("domains", []):
                    if domain.get("role") == "redirect" and _domain(domain.get("target_domain")) != official_domain:
                        errors.append(f"{domain.get('domain')}: redirect target must point to product official domain {official_domain}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
