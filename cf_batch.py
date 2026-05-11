from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

try:
    import dns.resolver
except Exception:  # pragma: no cover - dependency is documented in requirements.txt
    dns = None


API_BASE = "https://api.cloudflare.com/client/v4"
VALID_TYPES = {"main", "redirect", "parking"}
VALID_SSL_MODES = {"off", "flexible", "full", "strict"}
REAL_WRITE_COMMANDS = {"add-zone", "setup-dns", "setup-redirects", "setup-ssl", "all"}
HIGHEST_RISK_COMMANDS = {"all"}
ENV_LABELS = [
    ("CLOUDFLARE_API_TOKEN", "token", "secret"),
    ("CLOUDFLARE_ACCOUNT_ID", "account_id", "masked"),
    ("DEFAULT_MAIN_TARGET", "default_main", "presence"),
    ("DEFAULT_APP_TARGET", "default_app", "presence"),
    ("DEFAULT_API_TARGET", "default_api", "presence"),
    ("DEFAULT_PARKING_TARGET", "default_parking", "presence"),
    ("DEFAULT_SSL_MODE", "default_ssl", "presence"),
    ("DEFAULT_PROXIED", "default_proxied", "presence"),
]
RESULT_COLUMNS = [
    "domain",
    "category",
    "type",
    "target",
    "zone_id",
    "zone_status",
    "cloudflare_nameserver_1",
    "cloudflare_nameserver_2",
    "cloudflare_nameservers",
    "current_nameservers",
    "nameserver_status",
    "dns_status",
    "redirect_status",
    "ssl_status",
    "proxied_status",
    "error_message",
]


class ConfigError(RuntimeError):
    pass


@dataclass
class DomainPlan:
    domain: str
    type: str
    category: str = ""
    target: str = ""
    main_target: str = ""
    app_target: str = ""
    api_target: str = ""
    proxied: bool = True
    ssl_mode: str = "full"
    note: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ResultRow:
    domain: str
    type: str
    category: str = ""
    target: str = ""
    zone_id: str = ""
    zone_status: str = "not_started"
    cloudflare_nameserver_1: str = ""
    cloudflare_nameserver_2: str = ""
    cloudflare_nameservers: str = ""
    current_nameservers: str = ""
    nameserver_status: str = "not_checked"
    dns_status: str = "not_started"
    redirect_status: str = "not_applicable"
    ssl_status: str = "not_started"
    proxied_status: str = "not_started"
    error_message: str = ""

    def as_dict(self) -> dict[str, str]:
        return {name: str(getattr(self, name, "")) for name in RESULT_COLUMNS}


class CloudflareClient:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        try:
            payload = response.json()
        except Exception:
            payload = {"success": False, "errors": [{"message": response.text[:500]}]}
        if not response.ok or not payload.get("success", False):
            errors = payload.get("errors") or [{"message": f"HTTP {response.status_code}"}]
            message = "; ".join(str(item.get("message", item)) for item in errors)
            raise RuntimeError(message)
        return payload

    def list_zone(self, domain: str) -> dict[str, Any] | None:
        payload = self.request("GET", "/zones", params={"name": domain, "per_page": 1})
        zones = payload.get("result") or []
        return zones[0] if zones else None

    def create_zone(self, domain: str, account_id: str) -> dict[str, Any]:
        payload = self.request("POST", "/zones", json={
            "name": domain,
            "account": {"id": account_id},
            "type": "full",
            "jump_start": False,
        })
        return payload.get("result") or {}

    def list_dns_record(self, zone_id: str, name: str, record_type: str) -> dict[str, Any] | None:
        payload = self.request(
            "GET",
            f"/zones/{zone_id}/dns_records",
            params={"name": name, "type": record_type, "per_page": 100},
        )
        records = payload.get("result") or []
        return records[0] if records else None

    def upsert_dns_record(self, zone_id: str, record: dict[str, Any]) -> str:
        existing = self.list_dns_record(zone_id, record["name"], record["type"])
        if existing:
            self.request("PATCH", f"/zones/{zone_id}/dns_records/{existing['id']}", json=record)
            return "updated"
        self.request("POST", f"/zones/{zone_id}/dns_records", json=record)
        return "created"

    def get_ssl_mode(self, zone_id: str) -> str:
        payload = self.request("GET", f"/zones/{zone_id}/settings/ssl")
        return str((payload.get("result") or {}).get("value") or "")

    def set_ssl_mode(self, zone_id: str, mode: str) -> str:
        current = self.get_ssl_mode(zone_id)
        if current == mode:
            return "already_set"
        self.request("PATCH", f"/zones/{zone_id}/settings/ssl", json={"value": mode})
        return "updated"

    def get_redirect_ruleset(self, zone_id: str) -> dict[str, Any] | None:
        try:
            payload = self.request("GET", f"/zones/{zone_id}/rulesets/phases/http_request_dynamic_redirect/entrypoint")
            return payload.get("result") or None
        except RuntimeError as exc:
            if "not found" in str(exc).lower() or "could not route" in str(exc).lower():
                return None
            raise

    def upsert_redirect_rule(self, zone_id: str, domain: str, target: str) -> str:
        description = f"cf_batch redirect {domain} to {target}"
        expression = f'(http.host eq "{domain}" or http.host eq "www.{domain}")'
        rule = {
            "description": description,
            "expression": expression,
            "action": "redirect",
            "action_parameters": {
                "from_value": {
                    "status_code": 301,
                    "preserve_query_string": True,
                    "target_url": {"expression": f'concat("https://{target}", http.request.uri.path)'},
                }
            },
            "enabled": True,
        }
        ruleset = self.get_redirect_ruleset(zone_id)
        if not ruleset:
            self.request("POST", f"/zones/{zone_id}/rulesets", json={
                "name": "cf_batch redirect rules",
                "kind": "zone",
                "phase": "http_request_dynamic_redirect",
                "rules": [rule],
            })
            return "created"

        rules = list(ruleset.get("rules") or [])
        action = "created"
        for idx, item in enumerate(rules):
            if item.get("description") == description or item.get("expression") == expression:
                rule["id"] = item.get("id")
                rules[idx] = rule
                action = "updated"
                break
        else:
            rules.append(rule)
        self.request("PUT", f"/zones/{zone_id}/rulesets/{ruleset['id']}", json={
            "name": ruleset.get("name") or "cf_batch redirect rules",
            "kind": ruleset.get("kind") or "zone",
            "phase": ruleset.get("phase") or "http_request_dynamic_redirect",
            "rules": rules,
        })
        return action


def bool_from_text(value: str, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def clean_domain(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("https://", "").replace("http://", "")
    text = text.split("/", 1)[0].strip(".")
    return text


def cname_target(value: str) -> str:
    return clean_domain(value)


def dns_name(domain: str, label: str) -> str:
    return domain if label == "@" else f"{label}.{domain}"


def current_nameservers(domain: str) -> list[str]:
    if dns is None:
        return []
    try:
        answers = dns.resolver.resolve(domain, "NS", lifetime=6)
        return sorted(str(item.target).strip(".").lower() for item in answers)
    except Exception:
        return []


def load_env() -> dict[str, str]:
    # System environment variables take precedence; .env is only a local fallback.
    load_dotenv(override=False)
    return {
        "token": os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
        "account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
        "default_main": os.getenv("DEFAULT_MAIN_TARGET", "").strip(),
        "default_app": os.getenv("DEFAULT_APP_TARGET", "").strip(),
        "default_api": os.getenv("DEFAULT_API_TARGET", "").strip(),
        "default_parking": os.getenv("DEFAULT_PARKING_TARGET", "aioffice.com.tw").strip(),
        "default_ssl": os.getenv("DEFAULT_SSL_MODE", "full").strip().lower(),
        "default_proxied": os.getenv("DEFAULT_PROXIED", "true").strip(),
    }


def mask_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "missing"
    if len(text) <= 8:
        return "present masked"
    return f"{text[:4]}...{text[-4:]}"


def env_preflight_lines(env: dict[str, str]) -> list[str]:
    lines = ["Environment preflight:"]
    for env_name, key, display in ENV_LABELS:
        value = env.get(key, "")
        if display == "masked":
            status = mask_value(value)
        else:
            status = "present" if value else "missing"
        lines.append(f"- {env_name}: {status}")
    return lines


def print_env_preflight(env: dict[str, str]) -> None:
    print("")
    for line in env_preflight_lines(env):
        print(line)
    print("")


def require_env(env: dict[str, str], command: str, dry_run: bool) -> None:
    if dry_run:
        return
    missing = []
    if not env["token"]:
        missing.append("CLOUDFLARE_API_TOKEN")
    if command in {"add-zone", "all"} and not env["account_id"]:
        missing.append("CLOUDFLARE_ACCOUNT_ID")
    if missing:
        raise ConfigError(
            "Missing required environment values: "
            + ", ".join(missing)
            + ". Set them as system environment variables or provide them in .env."
        )


def effective_dry_run(apply: bool, dry_run: bool) -> bool:
    return dry_run or not apply


def require_real_write_confirmation(command: str, apply: bool, confirm_real_write: bool, dry_run: bool) -> None:
    if dry_run and apply:
        raise ConfigError("Use either --dry-run or --apply, not both. Default mode is dry-run.")
    if command not in REAL_WRITE_COMMANDS:
        return
    if not apply:
        return
    if not confirm_real_write:
        risk = " highest-risk" if command in HIGHEST_RISK_COMMANDS else ""
        raise ConfigError(
            f"{command} is a{risk} real-write command. "
            "To modify Cloudflare, rerun with both --apply and --confirm-real-write after separate approval."
        )


def print_safety_mode(command: str, dry_run: bool) -> None:
    print("")
    if dry_run:
        print("Safety mode: dry-run (default). No Cloudflare write API calls will be made.")
    elif command in HIGHEST_RISK_COMMANDS:
        print("Safety mode: REAL WRITE ENABLED for highest-risk command 'all'.")
    elif command in REAL_WRITE_COMMANDS:
        print(f"Safety mode: REAL WRITE ENABLED for command '{command}'.")
    else:
        print("Safety mode: apply mode for read-only Cloudflare verification/reporting.")
    if command == "verify":
        print("Note: verify is read-only against Cloudflare but uses a token and writes local reports.")
    if command == "report":
        print("Note: report uses the verify planner and writes local reports.")
    print("")


def load_domains(path: str, env: dict[str, str], dry_run: bool) -> list[DomainPlan]:
    df = pd.read_csv(path, keep_default_na=False, dtype=str).fillna("")
    required = ["domain", "type", "target", "main_target", "app_target", "api_target", "proxied", "ssl_mode", "note"]
    missing = [name for name in required if name not in df.columns]
    if missing:
        raise ConfigError("domains.csv missing columns: " + ", ".join(missing))
    plans: list[DomainPlan] = []
    for _, row in df.iterrows():
        domain = clean_domain(row["domain"])
        if not domain:
            continue
        domain_type = str(row["type"]).strip().lower()
        if domain_type not in VALID_TYPES:
            raise ConfigError(f"{domain}: invalid type {domain_type!r}")
        ssl_mode = (row["ssl_mode"] or env["default_ssl"] or "full").strip().lower()
        if ssl_mode not in VALID_SSL_MODES:
            raise ConfigError(f"{domain}: invalid ssl_mode {ssl_mode!r}")
        plan = DomainPlan(
            domain=domain,
            type=domain_type,
            category=str(row["category"] or "").strip() if "category" in df.columns else "",
            target=cname_target(row["target"]),
            main_target=cname_target(row["main_target"]),
            app_target=cname_target(row["app_target"]),
            api_target=cname_target(row["api_target"]),
            proxied=bool_from_text(row["proxied"], bool_from_text(env["default_proxied"], True)),
            ssl_mode=ssl_mode,
            note=str(row["note"] or "").strip(),
        )
        fill_default_targets(plan, env, dry_run)
        plans.append(plan)
    return plans


def missing_placeholder(name: str) -> str:
    return f"<{name}>"


def default_or_placeholder(env: dict[str, str], key: str, dry_run: bool, warnings: list[str]) -> str:
    value = env[key]
    if value:
        return cname_target(value)
    env_name = {
        "default_main": "DEFAULT_MAIN_TARGET",
        "default_app": "DEFAULT_APP_TARGET",
        "default_api": "DEFAULT_API_TARGET",
        "default_parking": "DEFAULT_PARKING_TARGET",
    }[key]
    if dry_run:
        warnings.append(f"missing {env_name}; dry-run used placeholder")
        return missing_placeholder(env_name)
    raise ConfigError(f"Missing required environment value: {env_name}. Set it as a system environment variable or provide it in .env.")


def fill_default_targets(plan: DomainPlan, env: dict[str, str], dry_run: bool) -> None:
    if plan.type == "main":
        if not plan.main_target:
            plan.main_target = default_or_placeholder(env, "default_main", dry_run, plan.warnings)
        if not plan.app_target:
            plan.app_target = default_or_placeholder(env, "default_app", dry_run, plan.warnings)
        if not plan.api_target:
            plan.api_target = default_or_placeholder(env, "default_api", dry_run, plan.warnings)
    else:
        if not plan.target:
            plan.target = default_or_placeholder(env, "default_parking", dry_run, plan.warnings)


def planned_dns_records(plan: DomainPlan) -> list[dict[str, Any]]:
    if plan.type == "main":
        specs = [
            ("@", plan.main_target),
            ("www", plan.domain),
            ("app", plan.app_target),
            ("api", plan.api_target),
        ]
    else:
        fallback = plan.target or plan.main_target
        specs = [
            ("@", fallback),
            ("www", plan.domain),
        ]
    records = []
    for label, target in specs:
        records.append({
            "type": "CNAME",
            "name": dns_name(plan.domain, label),
            "content": target,
            "proxied": plan.proxied,
            "ttl": 1,
        })
    return records


def validate_records(plan: DomainPlan, records: list[dict[str, Any]], dry_run: bool) -> list[str]:
    errors = []
    for record in records:
        content = str(record["content"] or "")
        if content.startswith("<") and dry_run:
            continue
        if not content:
            errors.append(f"{record['name']}: missing CNAME target")
        if "://" in content or "/" in content:
            errors.append(f"{record['name']}: invalid CNAME target {content}")
        if clean_domain(content) == clean_domain(record["name"]):
            errors.append(f"{record['name']}: CNAME cannot point to itself")
    return errors


def ns_status(current: list[str], cf_ns: list[str]) -> str:
    if not cf_ns:
        return "not_available"
    if not current:
        return "pending_nameserver_update"
    return "active" if set(current) == set(ns.lower().strip(".") for ns in cf_ns) else "pending_nameserver_update"


def set_cloudflare_nameservers(row: ResultRow, nameservers: list[str]) -> None:
    clean = [str(ns or "").strip().lower().strip(".") for ns in nameservers if str(ns or "").strip()]
    row.cloudflare_nameserver_1 = clean[0] if len(clean) >= 1 else ""
    row.cloudflare_nameserver_2 = clean[1] if len(clean) >= 2 else ""
    row.cloudflare_nameservers = "|".join(clean)


def set_dry_run_nameserver_placeholders(row: ResultRow) -> None:
    row.cloudflare_nameserver_1 = "<cloudflare_nameserver_1_after_add_zone>"
    row.cloudflare_nameserver_2 = "<cloudflare_nameserver_2_after_add_zone>"
    row.cloudflare_nameservers = "|".join([row.cloudflare_nameserver_1, row.cloudflare_nameserver_2])


def print_domain_list(plans: list[DomainPlan]) -> None:
    print(f"Domains to process ({len(plans)}):")
    for plan in plans:
        print(f"  - {plan.domain} [{plan.type}]")


def run_command(command: str, plans: list[DomainPlan], env: dict[str, str], dry_run: bool, force: bool) -> list[ResultRow]:
    require_env(env, command, dry_run)
    client = CloudflareClient(env["token"]) if env["token"] and not dry_run else None
    rows = [ResultRow(domain=plan.domain, category=plan.category, type=plan.type, target=plan.target) for plan in plans]

    for plan, row in zip(plans, rows):
        try:
            records = planned_dns_records(plan)
            record_errors = validate_records(plan, records, dry_run)
            current_ns = current_nameservers(plan.domain)
            row.current_nameservers = "|".join(current_ns)
            if record_errors:
                row.error_message = "; ".join(record_errors + plan.warnings)
            elif plan.warnings:
                row.error_message = "; ".join(plan.warnings)

            zone = None
            if dry_run:
                row.zone_status = "dry_run_would_get_or_create_zone" if command in {"add-zone", "all"} else "dry_run_would_get_zone"
                row.zone_id = "<zone_id>"
                set_dry_run_nameserver_placeholders(row)
                row.nameserver_status = "pending_nameserver_update"
            else:
                assert client is not None
                zone = client.list_zone(plan.domain)
                if not zone and command in {"add-zone", "all"}:
                    zone = client.create_zone(plan.domain, env["account_id"])
                    row.zone_status = "created"
                elif zone:
                    row.zone_status = "exists"
                else:
                    row.zone_status = "missing"
                    raise RuntimeError("zone missing; run add-zone first")
                row.zone_id = zone.get("id", "")
                zone_nameservers = zone.get("name_servers") or []
                set_cloudflare_nameservers(row, zone_nameservers)
                row.nameserver_status = ns_status(current_ns, zone_nameservers)

            if command in {"setup-dns", "all"}:
                if dry_run:
                    row.dns_status = "dry_run_plan:" + ";".join(f"{r['name']} CNAME {r['content']}" for r in records)
                else:
                    assert client is not None and zone is not None
                    actions = [client.upsert_dns_record(zone["id"], record) for record in records]
                    row.dns_status = "|".join(actions)
                row.proxied_status = f"proxied={str(plan.proxied).lower()}"

            if command in {"setup-redirects", "all"}:
                if plan.type in {"redirect", "parking"}:
                    if dry_run:
                        row.redirect_status = f"dry_run_plan:https://{plan.domain}/* -> https://{plan.target}/*;https://www.{plan.domain}/* -> https://{plan.target}/*"
                    else:
                        assert client is not None and zone is not None
                        row.redirect_status = client.upsert_redirect_rule(zone["id"], plan.domain, plan.target)
                else:
                    row.redirect_status = "not_applicable"

            if command in {"setup-ssl", "all"}:
                if dry_run:
                    row.ssl_status = f"dry_run_plan:{plan.ssl_mode}"
                else:
                    assert client is not None and zone is not None
                    row.ssl_status = client.set_ssl_mode(zone["id"], plan.ssl_mode)

            if command == "verify":
                if dry_run:
                    row.dns_status = "dry_run_verify_planned"
                    row.redirect_status = "dry_run_verify_planned" if plan.type in {"redirect", "parking"} else "not_applicable"
                    row.ssl_status = "dry_run_verify_planned"
                    row.proxied_status = f"proxied={str(plan.proxied).lower()}"
                else:
                    assert client is not None and zone is not None
                    dns_checks = []
                    for record in records:
                        dns_checks.append("ok" if client.list_dns_record(zone["id"], record["name"], record["type"]) else f"missing:{record['name']}")
                    row.dns_status = "|".join(dns_checks)
                    row.ssl_status = "ok" if client.get_ssl_mode(zone["id"]) == plan.ssl_mode else "mismatch"
                    row.proxied_status = f"expected={str(plan.proxied).lower()}"
                    row.redirect_status = "manual_check_ruleset" if plan.type in {"redirect", "parking"} else "not_applicable"

        except Exception as exc:
            row.error_message = "; ".join(part for part in [row.error_message, str(exc)] if part)
            if row.zone_status == "not_started":
                row.zone_status = "error"
    return rows


def write_report(rows: list[ResultRow], path: str) -> None:
    pd.DataFrame([row.as_dict() for row in rows], columns=RESULT_COLUMNS).to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {path}")


def nameserver_update_rows(rows: list[ResultRow]) -> list[dict[str, str]]:
    output = []
    for row in rows:
        status = row.nameserver_status
        note = ""
        if row.cloudflare_nameserver_1.startswith("<"):
            note = "Run real add-zone to fill Cloudflare assigned nameservers before changing registrar settings."
        elif status == "pending_nameserver_update":
            note = "Update nameservers at the domain registrar to the two Cloudflare nameservers shown here."
        output.append({
            "domain": row.domain,
            "cloudflare_nameserver_1": row.cloudflare_nameserver_1,
            "cloudflare_nameserver_2": row.cloudflare_nameserver_2,
            "status": status,
            "note": note,
        })
    return output


def write_nameserver_update_list(rows: list[ResultRow], path: str) -> None:
    columns = ["domain", "cloudflare_nameserver_1", "cloudflare_nameserver_2", "status", "note"]
    pd.DataFrame(nameserver_update_rows(rows), columns=columns).to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {path}")


def load_old_nameservers(path: str) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    try:
        frame = pd.read_csv(path, keep_default_na=False, dtype=str).fillna("")
    except Exception:
        return {}
    if "domain" not in frame.columns:
        return {}
    source_column = "current_ns" if "current_ns" in frame.columns else "current_nameservers" if "current_nameservers" in frame.columns else ""
    if not source_column:
        return {}
    return {
        clean_domain(row["domain"]): str(row[source_column] or "")
        for _, row in frame.iterrows()
        if clean_domain(row["domain"])
    }


def nameserver_verify_status(row: ResultRow) -> str:
    if row.zone_status == "error":
        return "failed"
    if row.nameserver_status == "active":
        return "nameserver_ok"
    if row.nameserver_status == "pending_nameserver_update":
        return "pending_dns_propagation"
    return "manual_check_required"


def write_nameserver_update_result(rows: list[ResultRow], path: str, dry_run_report_path: str) -> None:
    old_nameservers = load_old_nameservers(dry_run_report_path)
    verified_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    columns = [
        "domain",
        "old_nameservers",
        "new_nameservers",
        "cloudflare_nameserver_1",
        "cloudflare_nameserver_2",
        "status",
        "verified_at",
        "error_message",
    ]
    data = []
    for row in rows:
        data.append({
            "domain": row.domain,
            "old_nameservers": old_nameservers.get(row.domain, ""),
            "new_nameservers": row.current_nameservers,
            "cloudflare_nameserver_1": row.cloudflare_nameserver_1,
            "cloudflare_nameserver_2": row.cloudflare_nameserver_2,
            "status": nameserver_verify_status(row),
            "verified_at": verified_at,
            "error_message": row.error_message,
        })
    pd.DataFrame(data, columns=columns).to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {path}")


def summarize(rows: list[ResultRow], dry_run: bool) -> None:
    print("")
    print("Plan summary:" if dry_run else "Execution summary:")
    for row in rows:
        print(f"- {row.domain}: zone={row.zone_status}, dns={row.dns_status}, redirect={row.redirect_status}, ssl={row.ssl_status}, ns={row.nameserver_status}")
        if row.nameserver_status == "pending_nameserver_update":
            print(f"  registrar NS should be: {row.cloudflare_nameserver_1}, {row.cloudflare_nameserver_2}")
        if row.error_message:
            print(f"  warning/error: {row.error_message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare batch domain setup tool. Default mode is dry-run.",
        epilog=(
            "Default is dry-run. --apply enables real Cloudflare access, and write commands also require "
            "--confirm-real-write. The 'all' command is highest-risk because it can create zones, DNS records, "
            "redirect rules, and SSL setting changes."
        ),
    )
    parser.add_argument("command", choices=["add-zone", "setup-dns", "setup-redirects", "setup-ssl", "verify", "report", "all"])
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode. This is the default and never writes to Cloudflare.")
    parser.add_argument("--apply", action="store_true", help="Enable real Cloudflare access. Real-write commands still require --confirm-real-write.")
    parser.add_argument("--confirm-real-write", action="store_true", help="Required together with --apply for add-zone, setup-dns, setup-redirects, setup-ssl, and all.")
    parser.add_argument("--csv", default="domains.csv", help="Domain matrix CSV path")
    parser.add_argument("--result", default="cloudflare-result.csv", help="Result CSV path")
    parser.add_argument("--nameserver-result", default="nameserver-update-list.csv", help="Registrar nameserver update CSV path")
    parser.add_argument("--nameserver-update-result", default="nameserver-update-result.csv", help="Post-registrar nameserver verification CSV path")
    parser.add_argument("--registrar-dry-run-report", default="nameserver-registrar-dry-run.csv", help="Optional registrar dry-run report used for old nameservers")
    parser.add_argument("--force", action="store_true", help="Reserved for future destructive operations; current version still does not delete records")
    args = parser.parse_args()

    try:
        dry_run = effective_dry_run(args.apply, args.dry_run)
        require_real_write_confirmation(args.command, args.apply, args.confirm_real_write, args.dry_run)
        print_safety_mode(args.command, dry_run)
        env = load_env()
        print_env_preflight(env)
        plans = load_domains(args.csv, env, dry_run)
        print_domain_list(plans)
        if args.command == "report":
            rows = run_command("verify", plans, env, dry_run, args.force)
        else:
            rows = run_command(args.command, plans, env, dry_run, args.force)
        write_report(rows, args.result)
        write_nameserver_update_list(rows, args.nameserver_result)
        if args.command == "verify":
            write_nameserver_update_result(rows, args.nameserver_update_result, args.registrar_dry_run_report)
        summarize(rows, dry_run)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
