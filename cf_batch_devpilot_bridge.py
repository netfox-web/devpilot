from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv


TOOL_DIR = Path(__file__).resolve().parent
DEVPILOT_ROOT = Path(os.getenv("DEVPILOT_ROOT", "/volume1/docker/devpilot"))
DEVPILOT_ENV = DEVPILOT_ROOT / ".env"
DB_PATH = Path(os.getenv("DATABASE_PATH", DEVPILOT_ROOT / "data" / "project_manager.db"))
API_BASE = "https://api.cloudflare.com/client/v4"
PREFERRED_CLOUDFLARE_KEY_ID = 7
DEFAULT_SAMPLE_CSV = TOOL_DIR / "docs" / "templates" / "domains.sample.csv"
DEFAULT_RESULT_DIR = TOOL_DIR / "reports" / "generated" / "cloudflare"
REQUIRED_HEADER = [
    "domain",
    "type",
    "target",
    "main_target",
    "app_target",
    "api_target",
    "proxied",
    "ssl_mode",
    "category",
    "note",
]
VALID_TYPES = {"main", "redirect", "parking"}
MOJIBAKE_PATTERNS = ("銝", "蝟", "頧", "隡", "撠", "摰", "蝞", "", "", "???", "\ufffd")
REQUIRED_TARGETS = [
    "DEFAULT_MAIN_TARGET",
    "DEFAULT_APP_TARGET",
    "DEFAULT_API_TARGET",
]


class ConfigError(RuntimeError):
    pass


def load_runtime_environment() -> None:
    load_dotenv(DEVPILOT_ENV, override=False)
    load_dotenv(TOOL_DIR / ".env", override=False)
    os.environ.setdefault("DEFAULT_PARKING_TARGET", "aioffice.com.tw")
    os.environ.setdefault("DEFAULT_SSL_MODE", "full")
    os.environ.setdefault("DEFAULT_PROXIED", "true")


def encryption_material() -> bytes:
    configured = os.getenv("MASTER_KEY", "").strip() or os.getenv("API_KEY_ENCRYPTION_KEY", "").strip()
    if configured:
        return configured.encode("utf-8")
    api_token = os.getenv("API_TOKEN", "change-me-token")
    secret_key = os.getenv("SECRET_KEY", "devpilot-secret-key")
    return f"{secret_key}:{api_token}:devpilot-api-key-center".encode("utf-8")


def fernet_key_from_material(material: bytes) -> bytes:
    try:
        Fernet(material)
        return material
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def aes256_key() -> bytes:
    return hashlib.sha256(encryption_material()).digest()


def decrypt_secret_value(ciphertext_value: str) -> str:
    if not ciphertext_value:
        return ""
    if str(ciphertext_value).startswith("aes256:"):
        raw = base64.urlsafe_b64decode(str(ciphertext_value).split(":", 1)[1].encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        return AESGCM(aes256_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    try:
        return Fernet(fernet_key_from_material(encryption_material())).decrypt(
            str(ciphertext_value).encode("ascii")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("cloudflare credential decrypt failed") from exc


def mask_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "missing"
    if len(text) <= 8:
        return "present masked"
    return f"{text[:4]}...{text[-4:]}"


def fetch_cloudflare_key(decrypt: bool) -> dict[str, Any]:
    if not DB_PATH.exists():
        raise RuntimeError(f"DevPilot DB not found: {DB_PATH}")
    encrypted_column = "encrypted" + "_value"
    query = f"""
        SELECT id, name, provider, category, environment, status, {encrypted_column}, masked_value, key_mask
        FROM api_keys
        WHERE lower(COALESCE(provider, ''))='cloudflare'
          AND lower(COALESCE(status, ''))='active'
        ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, datetime(COALESCE(updated_at, created_at)) DESC, id DESC
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(query, (PREFERRED_CLOUDFLARE_KEY_ID,)))
    if not rows:
        raise RuntimeError("active cloudflare key not found in DevPilot API Key Center")
    if len(rows) > 1 and int(rows[0]["id"]) != PREFERRED_CLOUDFLARE_KEY_ID:
        raise RuntimeError("multiple active cloudflare keys found and preferred key id was not selected")
    row = rows[0]
    token = ""
    if decrypt:
        token = decrypt_secret_value(row[encrypted_column])
        if not str(token or "").strip():
            raise RuntimeError("active cloudflare key decrypted to empty value")
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "provider": row["provider"],
        "category": row["category"],
        "environment": row["environment"],
        "masked": row["masked_value"] or row["key_mask"] or "************",
        "token": str(token).strip(),
        "token_present": bool(str(row[encrypted_column] or "").strip()),
    }


def cloudflare_request(token: str, path: str) -> dict[str, Any]:
    response = requests.get(
        API_BASE + path,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        timeout=30,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"success": False, "errors": [{"message": response.text[:500]}]}
    if not response.ok or not payload.get("success", False):
        errors = payload.get("errors") or [{"message": f"HTTP {response.status_code}"}]
        message = "; ".join(str(item.get("message", item)) for item in errors)
        raise RuntimeError("cloudflare accounts lookup failed: " + message)
    return payload


def discover_account_id(token: str) -> tuple[str, str]:
    existing = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if existing:
        return existing, "existing config / env"
    payload = cloudflare_request(token, "/accounts")
    accounts = payload.get("result") or []
    if len(accounts) == 1:
        account_id = str(accounts[0].get("id") or "").strip()
        if account_id:
            return account_id, "Cloudflare accounts auto-discovery via read-only GET /accounts"
    if not accounts:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID missing and token returned no visible accounts")
    masked_accounts = [
        {"id": mask_value(str(item.get("id") or "")), "name": item.get("name") or ""}
        for item in accounts
    ]
    raise RuntimeError("multiple Cloudflare accounts visible; choose one account id: " + json.dumps(masked_accounts, ensure_ascii=False))


def print_preflight(key_info: dict[str, Any], account_source: str | None, dry_run: bool, csv_path: Path, result_dir: Path) -> None:
    print("Bridge preflight:")
    print("- command: add-zone (mutation-capable)")
    print(f"- mode: {'dry-run' if dry_run else 'real write'}")
    print("- default mode: dry-run")
    print("- Cloudflare token from API Key Center present: " + ("yes" if key_info.get("token_present") else "no"))
    print(f"- token id: {key_info['id']}")
    print(f"- provider: {key_info.get('provider') or 'cloudflare'}")
    print("- token raw output: no")
    print("- token written to disk: no")
    print("- token stored in process environment: no")
    print(f"- CLOUDFLARE_ACCOUNT_ID: {mask_value(os.getenv('CLOUDFLARE_ACCOUNT_ID', ''))} ({account_source or 'not queried in dry-run'})")
    print(f"- CSV path: {csv_path}")
    print(f"- result dir: {result_dir}")
    for name in REQUIRED_TARGETS:
        status = "present" if os.getenv(name, "").strip() else "missing but not required for add-zone"
        print(f"- {name}: {status}")
    for name in ["DEFAULT_PARKING_TARGET", "DEFAULT_SSL_MODE", "DEFAULT_PROXIED"]:
        print(f"- {name}: {'present' if os.getenv(name, '').strip() else 'missing'}")


def clean_domain(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("https://", "").replace("http://", "")
    return text.split("/", 1)[0].strip(".")


def sanitize_error(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(Authorization:\s*)[^\s]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(token|secret|api[_-]?key)(\s*[=:]\s*)[^\s,;]+", r"\1\2[redacted]", text)
    return text[:500]


def resolve_csv_path(value: str | None) -> tuple[Path, bool]:
    if value:
        return Path(value).expanduser().resolve(), False
    return DEFAULT_SAMPLE_CSV.resolve(), True


def is_sample_csv(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_SAMPLE_CSV.resolve()
    except OSError:
        return False


def validate_csv_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    matched = [pattern for pattern in MOJIBAKE_PATTERNS if pattern in text]
    if matched:
        raise ConfigError("CSV appears to contain mojibake or replacement text; rebuild from a clean source before use")
    physical_lines = [line for line in text.splitlines() if line.strip()]
    for line_no, line in enumerate(physical_lines, start=1):
        comma_count = line.count(",")
        if comma_count != 9:
            raise ConfigError(f"CSV line {line_no} has {comma_count} commas; expected 9")


def load_domain_entries(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ConfigError(f"CSV input not found: {path}")
    validate_csv_text(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUIRED_HEADER:
            raise ConfigError("CSV header must be: " + ",".join(REQUIRED_HEADER))
        rows = []
        for line_no, item in enumerate(reader, start=2):
            domain = clean_domain(item.get("domain", ""))
            if not domain:
                raise ConfigError(f"CSV line {line_no}: domain is required")
            domain_type = str(item.get("type", "") or "").strip().lower()
            if domain_type not in VALID_TYPES:
                raise ConfigError(f"CSV line {line_no}: type must be one of main, redirect, parking")
            rows.append({
                "domain": domain,
                "category": str(item.get("category", "") or "").strip(),
                "type": domain_type,
                "target": clean_domain(item.get("target", "")),
            })
    return rows


def ensure_result_dir(path: Path) -> Path:
    result_dir = path.expanduser().resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def run_add_zone_only(token: str, account_id: str, entries: list[dict[str, str]], result_dir: Path, dry_run: bool) -> int:
    import cf_batch

    client = None if dry_run else cf_batch.CloudflareClient(token)
    rows = []
    print(f"Domains to process ({len(entries)}):")
    for entry in entries:
        print(f"  - {entry['domain']} [{entry['type']}]")

    for entry in entries:
        row = cf_batch.ResultRow(
            domain=entry["domain"],
            category=entry["category"],
            type=entry["type"],
            target=entry["target"],
        )
        try:
            if dry_run:
                row.zone_id = "<zone_id>"
                row.zone_status = "dry_run_would_get_or_create_zone"
                cf_batch.set_dry_run_nameserver_placeholders(row)
                row.nameserver_status = "pending_nameserver_update"
            else:
                assert client is not None
                current_ns = cf_batch.current_nameservers(entry["domain"])
                row.current_nameservers = "|".join(current_ns)
                zone = client.list_zone(entry["domain"])
                if zone:
                    row.zone_status = "exists"
                else:
                    zone = client.create_zone(entry["domain"], account_id)
                    row.zone_status = "created"
                row.zone_id = str(zone.get("id") or "")
                zone_nameservers = zone.get("name_servers") or []
                cf_batch.set_cloudflare_nameservers(row, zone_nameservers)
                row.nameserver_status = cf_batch.ns_status(current_ns, zone_nameservers)
            row.dns_status = "not_started"
            row.redirect_status = "not_applicable"
            row.ssl_status = "not_started"
            row.proxied_status = "not_started"
        except Exception as exc:
            row.zone_status = "error"
            row.error_message = sanitize_error(exc)
        rows.append(row)

    cf_batch.write_report(rows, str(result_dir / "cloudflare-result.csv"))
    cf_batch.write_nameserver_update_list(rows, str(result_dir / "nameserver-update-list.csv"))
    print("")
    print("Add-zone bridge summary:")
    for row in rows:
        print(f"- {row.domain}: zone={row.zone_status}, ns={row.nameserver_status}")
        if row.nameserver_status == "pending_nameserver_update":
            print(f"  registrar NS should be: {row.cloudflare_nameserver_1}, {row.cloudflare_nameserver_2}")
        if row.error_message:
            print(f"  error: {row.error_message}")
    return 0


def effective_dry_run(apply: bool, dry_run: bool) -> bool:
    return dry_run or not apply


def require_apply_confirmation(apply: bool, confirm_real_write: bool, dry_run_arg: bool) -> None:
    if dry_run_arg and apply:
        raise ConfigError("Use either --dry-run or --apply, not both. Default mode is dry-run.")
    if apply and not confirm_real_write:
        raise ConfigError("add-zone is mutation-capable. Real write requires both --apply and --confirm-real-write.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DevPilot API Key Center bridge for cf_batch add-zone. Default is dry-run. "
            "The bridge reads encrypted DevPilot credentials into memory only."
        ),
        epilog=(
            "--apply enables real Cloudflare write access. --confirm-real-write is required with --apply. "
            "Dry-run does not decrypt the token, does not create a Cloudflare mutation client, and does not call Cloudflare."
        ),
    )
    parser.add_argument("command", choices=["add-zone"], help="Mutation-capable add-zone planner/executor")
    parser.add_argument("--csv", default="", help="Reviewed domain CSV input. Defaults to docs/templates/domains.sample.csv for dry-run only.")
    parser.add_argument("--result-dir", default=str(DEFAULT_RESULT_DIR), help="Directory for generated local reports.")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode. This is the default.")
    parser.add_argument("--apply", action="store_true", help="Enable real Cloudflare write access.")
    parser.add_argument("--confirm-real-write", action="store_true", help="Required with --apply for add-zone.")
    args = parser.parse_args()

    try:
        dry_run = effective_dry_run(args.apply, args.dry_run)
        require_apply_confirmation(args.apply, args.confirm_real_write, args.dry_run)
        csv_path, used_default_sample = resolve_csv_path(args.csv)
        if not dry_run and (used_default_sample or is_sample_csv(csv_path)):
            raise ConfigError("Real write cannot use docs/templates/domains.sample.csv")

        load_runtime_environment()
        entries = load_domain_entries(csv_path)
        result_dir = ensure_result_dir(Path(args.result_dir))
        key_info = fetch_cloudflare_key(decrypt=not dry_run)
        token = key_info["token"]
        account_source = None
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        if not dry_run:
            account_id, account_source = discover_account_id(token)

        print_preflight(key_info, account_source, dry_run, csv_path, result_dir)
        return run_add_zone_only(token, account_id, entries, result_dir, dry_run)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {sanitize_error(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"BRIDGE ERROR: {sanitize_error(exc)}", file=sys.stderr)
        raise SystemExit(2)
