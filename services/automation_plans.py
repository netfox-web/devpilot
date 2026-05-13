from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid


STORE_VERSION = 1
ALLOWED_PLAN_STATUSES = {"draft", "reviewed", "approved", "rejected", "executed_later"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "blocked"}
ALLOWED_SAFETY_STATUSES = {"pass", "warn", "fail", "not_available"}
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DEFAULT_STORE_PATH = DATA_DIR / "automation_plans.json"

SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|password|private[_-]?key|key[_-]?hash|token|secret)",
    re.IGNORECASE,
)
SENSITIVE_VALUE_RE = re.compile(
    r"(Authorization\s*:|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"OPENAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|CLAUDE_API_KEY|"
    r"DEVPILOT_API_KEY|REPLICATE_API_TOKEN|FAL_KEY|SECRET|PASSWORD|TOKEN|PRIVATE_KEY|key_hash)",
    re.IGNORECASE,
)


def automation_plan_store_path() -> Path:
    raw_path = os.getenv("DEVPILOT_AUTOMATION_PLAN_STORE_PATH", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_STORE_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value, limit: int = 1000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def _string_list(value, *, limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, limit) for item in value if _text(item, limit)]


def _has_sensitive_content(value) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if SENSITIVE_KEY_RE.search(str(key or "")):
                return True
            if _has_sensitive_content(item):
                return True
        return False
    if isinstance(value, list):
        return any(_has_sensitive_content(item) for item in value)
    return bool(SENSITIVE_VALUE_RE.search(str(value or "")))


def _normalize_choice(value, allowed: set[str], default: str) -> str:
    text = _text(value, 80).lower()
    return text if text in allowed else default


def _normalize_action(item) -> dict:
    if not isinstance(item, dict):
        item = {"description": item}
    return {
        "label": _text(item.get("label"), 160),
        "description": _text(item.get("description"), 1000),
        "risk_level": _normalize_choice(item.get("risk_level"), ALLOWED_RISK_LEVELS, "low"),
        "requires_approval": bool(item.get("requires_approval")),
        "approval_type": _text(item.get("approval_type") or "none", 80),
        "status": _text(item.get("status") or "suggested", 80),
    }


def _normalize_safety_check(item) -> dict:
    if not isinstance(item, dict):
        item = {"name": item}
    return {
        "name": _text(item.get("name"), 160),
        "status": _normalize_choice(item.get("status"), ALLOWED_SAFETY_STATUSES, "not_available"),
        "details": _text(item.get("details"), 1000),
    }


def _normalize_command(item) -> dict:
    if not isinstance(item, dict):
        item = {"command": item}
    return {
        "label": _text(item.get("label"), 160),
        "command": _text(item.get("command"), 2000),
        "execution_allowed": False,
    }


def _normalize_affected_system(item) -> dict:
    if not isinstance(item, dict):
        item = {"name": item}
    return {
        "type": _text(item.get("type"), 80),
        "name": _text(item.get("name"), 160),
        "impact": _text(item.get("impact"), 1000),
    }


def normalize_automation_plan(plan_input: dict) -> dict:
    if not isinstance(plan_input, dict):
        raise ValueError("automation plan must be an object")
    if _has_sensitive_content(plan_input):
        raise ValueError("automation plan contains sensitive content")

    risk_level = _text(plan_input.get("risk_level"), 80).lower()
    if risk_level not in ALLOWED_RISK_LEVELS:
        raise ValueError("invalid risk_level")

    plan = {
        "id": _text(plan_input.get("id"), 120) or f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:12]}",
        "source_system": _text(plan_input.get("source_system"), 160),
        "external_project_id": _text(plan_input.get("external_project_id"), 160),
        "title": _text(plan_input.get("title"), 240),
        "objective": _text(plan_input.get("objective"), 1000),
        "risk_level": risk_level,
        "recommended_actions": [_normalize_action(item) for item in plan_input.get("recommended_actions") or []],
        "required_approvals": _string_list(plan_input.get("required_approvals") or [], limit=80),
        "blocked_by": _string_list(plan_input.get("blocked_by") or [], limit=240),
        "safety_checks": [_normalize_safety_check(item) for item in plan_input.get("safety_checks") or []],
        "suggested_commands": [_normalize_command(item) for item in plan_input.get("suggested_commands") or []],
        "affected_systems": [_normalize_affected_system(item) for item in plan_input.get("affected_systems") or []],
        "created_at": _text(plan_input.get("created_at"), 80) or _now_iso(),
        "status": "draft",
    }
    validate_automation_plan(plan)
    return plan


def validate_automation_plan(plan: dict) -> bool:
    if not isinstance(plan, dict):
        raise ValueError("automation plan must be an object")
    if _has_sensitive_content(plan):
        raise ValueError("automation plan contains sensitive content")
    if plan.get("status") not in ALLOWED_PLAN_STATUSES:
        raise ValueError("invalid status")
    if plan.get("risk_level") not in ALLOWED_RISK_LEVELS:
        raise ValueError("invalid risk_level")
    for field in ("id", "title", "objective", "created_at"):
        if not _text(plan.get(field)):
            raise ValueError(f"{field} is required")
    if not isinstance(plan.get("suggested_commands"), list):
        raise ValueError("suggested_commands must be a list")
    for command in plan.get("suggested_commands") or []:
        if not isinstance(command, dict):
            raise ValueError("suggested command must be an object")
        if command.get("execution_allowed") is not False:
            raise ValueError("suggested command execution is not allowed")
        if not _text(command.get("command")):
            raise ValueError("suggested command text is required")
    return True


def redact_automation_plan(plan: dict) -> dict:
    safe = deepcopy(plan or {})
    for key in list(safe.keys()):
        if SENSITIVE_KEY_RE.search(str(key or "")):
            safe.pop(key, None)
    for command in safe.get("suggested_commands") or []:
        if isinstance(command, dict):
            command["execution_allowed"] = False
    if _has_sensitive_content(safe):
        raise ValueError("automation plan contains sensitive content")
    return safe


def _empty_store(error: str = "") -> dict:
    store = {"version": STORE_VERSION, "plans": []}
    if error:
        store["error"] = error
    return store


def load_automation_plan_store() -> dict:
    path = automation_plan_store_path()
    if not path.exists():
        return _empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError):
        return _empty_store("malformed_store")
    if not isinstance(raw, dict):
        return _empty_store("malformed_store")
    plans = []
    for item in raw.get("plans") or []:
        try:
            plan = normalize_automation_plan(item)
            plan["id"] = _text(item.get("id"), 120) or plan["id"]
            plan["created_at"] = _text(item.get("created_at"), 80) or plan["created_at"]
            plan["status"] = _normalize_choice(item.get("status"), ALLOWED_PLAN_STATUSES, "draft")
            validate_automation_plan(plan)
            plans.append(plan)
        except (AttributeError, TypeError, ValueError):
            continue
    return {"version": STORE_VERSION, "plans": plans}


def save_automation_plan_store(store: dict) -> dict:
    if not isinstance(store, dict):
        raise ValueError("automation plan store must be an object")
    plans = []
    for item in store.get("plans") or []:
        plan = normalize_automation_plan(item)
        if item.get("status") in ALLOWED_PLAN_STATUSES:
            plan["status"] = item.get("status")
        validate_automation_plan(plan)
        plans.append(redact_automation_plan(plan))
    payload = {"version": STORE_VERSION, "plans": plans}
    path = automation_plan_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def list_automation_plans() -> list[dict]:
    return [redact_automation_plan(plan) for plan in load_automation_plan_store().get("plans", [])]


def create_automation_plan(plan_input: dict) -> dict:
    plan = normalize_automation_plan(plan_input)
    store = load_automation_plan_store()
    plans = store.get("plans") or []
    plans.append(plan)
    save_automation_plan_store({"version": STORE_VERSION, "plans": plans})
    return redact_automation_plan(plan)
