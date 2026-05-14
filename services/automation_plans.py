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
RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "blocked": 4}
APPROVAL_ORDER = [
    "deploy",
    "infra",
    "migration",
    "dns",
    "provider",
    "worker",
    "mutation",
    "approval",
    "execution",
    "manual_review",
]
HIGH_RISK_PATTERNS = [
    ("deploy", "deploy", re.compile(r"\b(deploy|deployment|release)\b", re.IGNORECASE)),
    ("restart_rebuild", "infra", re.compile(r"\b(restart|rebuild|recreate|docker\s+build|docker\s+compose\s+up)\b", re.IGNORECASE)),
    ("migration", "migration", re.compile(r"\b(migration|migrate|schema\s+change|alter\s+table)\b", re.IGNORECASE)),
    ("dns_ssl_nginx", "dns", re.compile(r"\b(dns|ssl|nginx|certbot|certificate|redirect|reverse\s+proxy)\b", re.IGNORECASE)),
    ("cloudflare_r2", "infra", re.compile(r"\b(cloudflare|r2)\b", re.IGNORECASE)),
    ("provider", "provider", re.compile(r"\b(provider\s+call|openai|gemini|claude|anthropic|live\s+ping|ai\s+ping|spend|budget)\b", re.IGNORECASE)),
    ("worker", "worker", re.compile(r"\b(worker|task\s+execution|run_ai_task|dispatch_ai_console_task|queue\s+job)\b", re.IGNORECASE)),
    ("mutation", "mutation", re.compile(r"\b(project\s+mutation|task\s+mutation|phase\s+mutation|mutate|write\s+project|update\s+task|approval\s+mutation)\b", re.IGNORECASE)),
    ("approval", "approval", re.compile(r"\b(create\s+approval|approval\s+request|approval\s+row)\b", re.IGNORECASE)),
    ("shell", "execution", re.compile(r"\b(shell\s+command|bash|powershell|cmd\s+/c|sh\s+-lc|ssh|kubectl|docker)\b", re.IGNORECASE)),
]
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


def _risk_max(*values: str) -> str:
    winner = "low"
    for value in values:
        risk = _normalize_choice(value, ALLOWED_RISK_LEVELS, "low")
        if RISK_ORDER[risk] > RISK_ORDER[winner]:
            winner = risk
    return winner


def _append_unique(items: list[str], value: str) -> None:
    value = _text(value, 120)
    if value and value not in items:
        items.append(value)


def _ordered_approvals(items) -> list[str]:
    seen = set(_string_list(list(items or []), limit=80))
    ordered = [item for item in APPROVAL_ORDER if item in seen]
    ordered.extend(sorted(item for item in seen if item not in APPROVAL_ORDER))
    return ordered


def _safety_text_from_value(value) -> str:
    if isinstance(value, dict):
        return " ".join(_safety_text_from_value(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_safety_text_from_value(item) for item in value)
    return _text(value, 500)


def _classify_high_risk_categories(text: str) -> list[dict]:
    text = _text(text, 4000)
    matches = []
    for category, approval_type, pattern in HIGH_RISK_PATTERNS:
        if pattern.search(text):
            matches.append({"category": category, "approval_type": approval_type})
    return matches


def validate_display_only_commands(plan: dict) -> dict:
    warnings = []
    required_approvals = []
    commands = []
    raw_commands = plan.get("suggested_commands") if isinstance(plan, dict) else []
    if not isinstance(raw_commands, list):
        raw_commands = []
        warnings.append("suggested_commands was not a list and was treated as empty")
    for item in raw_commands:
        raw = item if isinstance(item, dict) else {"command": item}
        if raw.get("execution_allowed") is True:
            warnings.append("suggested command requested execution and was forced display-only")
        command = _normalize_command(raw)
        categories = _classify_high_risk_categories(command.get("command") or "")
        if categories:
            warnings.append("suggested command text references high-risk operational action")
            for category in categories:
                _append_unique(required_approvals, category["approval_type"])
        commands.append(command)
    return {
        "commands": commands,
        "required_approvals": _ordered_approvals(required_approvals),
        "warnings": warnings,
        "execution_allowed": False,
    }


def _evaluate_recommended_actions(plan: dict) -> tuple[list[dict], list[str], list[str], str]:
    evaluated = []
    required_approvals = []
    warnings = []
    overall_risk = "low"
    raw_actions = plan.get("recommended_actions") if isinstance(plan, dict) else []
    if not isinstance(raw_actions, list):
        raw_actions = []
        warnings.append("recommended_actions was not a list and was treated as empty")
    for item in raw_actions:
        action = _normalize_action(item)
        text = _safety_text_from_value(action)
        categories = _classify_high_risk_categories(text)
        if action.get("risk_level") == "high" and not categories:
            categories = [{"category": "manual_review", "approval_type": "manual_review"}]
        if categories:
            action["risk_level"] = "high"
            action["requires_approval"] = True
            if action.get("approval_type") in ("", "none"):
                action["approval_type"] = categories[0]["approval_type"]
            for category in categories:
                _append_unique(required_approvals, category["approval_type"])
            warnings.append(f"high-risk action requires approval: {action.get('label') or 'unnamed action'}")
        elif action.get("requires_approval"):
            approval_type = action.get("approval_type") or "manual_review"
            if approval_type == "none":
                approval_type = "manual_review"
            action["approval_type"] = approval_type
            _append_unique(required_approvals, approval_type)
        overall_risk = _risk_max(overall_risk, action.get("risk_level"))
        evaluated.append(action)
    return evaluated, _ordered_approvals(required_approvals), warnings, overall_risk


def classify_required_approvals(plan: dict) -> list[str]:
    if not isinstance(plan, dict) or _has_sensitive_content(plan):
        return []
    approvals = []
    for item in _string_list(plan.get("required_approvals") or [], limit=80):
        _append_unique(approvals, item)
    for action in plan.get("recommended_actions") or []:
        normalized = _normalize_action(action)
        if normalized.get("requires_approval") and normalized.get("approval_type") not in ("", "none"):
            _append_unique(approvals, normalized["approval_type"])
        for category in _classify_high_risk_categories(_safety_text_from_value(normalized)):
            _append_unique(approvals, category["approval_type"])
        if normalized.get("risk_level") == "high" and not approvals:
            _append_unique(approvals, "manual_review")
    command_result = validate_display_only_commands(plan)
    for item in command_result.get("required_approvals") or []:
        _append_unique(approvals, item)
    if _text(plan.get("risk_level")).lower() == "high" and not approvals:
        _append_unique(approvals, "manual_review")
    return _ordered_approvals(approvals)


def detect_blockers(plan: dict) -> list[str]:
    blockers = []
    if not isinstance(plan, dict):
        return ["automation plan is not an object"]
    if _has_sensitive_content(plan):
        blockers.append("automation plan contains blocked sensitive content")
        return blockers
    for item in _string_list(plan.get("blocked_by") or [], limit=240):
        _append_unique(blockers, item)
    if plan.get("execution_allowed") is True:
        _append_unique(blockers, "plan-level execution is not allowed in the MVP")
    if plan.get("safe_to_execute") is True:
        _append_unique(blockers, "plan cannot be marked safe to execute in the MVP")
    for command in plan.get("suggested_commands") or []:
        if isinstance(command, dict) and command.get("execution_allowed") is True:
            _append_unique(blockers, "suggested command execution is not allowed in the MVP")
            break
    return blockers


def evaluate_automation_plan_safety(plan: dict) -> dict:
    if not isinstance(plan, dict):
        return {
            "overall_risk_level": "blocked",
            "required_approvals": [],
            "blocked_by": ["automation plan is not an object"],
            "safety_checks": [{"name": "Plan shape", "status": "fail", "details": "Automation plan must be an object."}],
            "execution_allowed": False,
            "safe_to_execute": False,
            "warnings": [],
            "recommended_actions": [],
            "suggested_commands": [],
        }
    if _has_sensitive_content(plan):
        return {
            "overall_risk_level": "blocked",
            "required_approvals": [],
            "blocked_by": ["automation plan contains blocked sensitive content"],
            "safety_checks": [{"name": "Sensitive content", "status": "fail", "details": "Blocked sensitive content was detected and was not echoed."}],
            "execution_allowed": False,
            "safe_to_execute": False,
            "warnings": ["blocked sensitive content detected"],
            "recommended_actions": [],
            "suggested_commands": [],
        }

    actions, action_approvals, action_warnings, action_risk = _evaluate_recommended_actions(plan)
    command_result = validate_display_only_commands(plan)
    required_approvals = []
    for item in _string_list(plan.get("required_approvals") or [], limit=80):
        _append_unique(required_approvals, item)
    for item in action_approvals + command_result.get("required_approvals", []):
        _append_unique(required_approvals, item)
    required_approvals = _ordered_approvals(required_approvals)
    blockers = detect_blockers(plan)

    declared_risk = _normalize_choice(plan.get("risk_level"), ALLOWED_RISK_LEVELS, "low")
    overall_risk = _risk_max(declared_risk, action_risk)
    if required_approvals:
        overall_risk = _risk_max(overall_risk, "high")
    if blockers:
        overall_risk = "blocked"

    safety_checks = [_normalize_safety_check(item) for item in plan.get("safety_checks") or []]
    safety_checks.extend([
        {
            "name": "Display-only commands",
            "status": "pass" if not command_result.get("warnings") else "warn",
            "details": "Suggested commands are display-only and execution_allowed=false.",
        },
        {
            "name": "Required approvals",
            "status": "warn" if required_approvals else "pass",
            "details": ", ".join(required_approvals) if required_approvals else "No high-risk approval categories detected.",
        },
        {
            "name": "Execution bridge",
            "status": "pass",
            "details": "No execution bridge is enabled by this safety evaluator.",
        },
    ])
    if blockers:
        safety_checks.append({
            "name": "Blockers",
            "status": "fail",
            "details": f"{len(blockers)} blocker(s) detected.",
        })

    warnings = action_warnings + command_result.get("warnings", [])
    return {
        "overall_risk_level": overall_risk,
        "required_approvals": required_approvals,
        "blocked_by": blockers,
        "safety_checks": safety_checks,
        "execution_allowed": False,
        "safe_to_execute": False,
        "warnings": warnings,
        "recommended_actions": actions,
        "suggested_commands": command_result.get("commands", []),
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
