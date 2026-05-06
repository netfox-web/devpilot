import json


def normalize_task_provider(value):
    text = str(value or "openai").strip().lower()
    aliases = {
        "gpt": "openai",
        "openai_gpt": "openai",
        "google": "gemini",
        "anthropic": "claude",
    }
    provider = aliases.get(text, text)
    if provider not in ("openai", "gemini", "claude"):
        raise ValueError("unsupported task provider")
    return provider


def normalize_ai_task_status(value, allowed_statuses, default="queued"):
    text = str(value or "").strip().lower()
    return text if text in allowed_statuses else default


def normalize_ai_task_priority(value, allowed_priorities):
    text = str(value or "").strip().lower()
    return text if text in allowed_priorities else "medium"


def normalize_ai_task_type(value):
    text = str(value or "").strip().lower()
    return text or "general"


def normalize_ai_task_approval_status(value, allowed_statuses):
    text = str(value or "").strip().lower()
    return text if text in allowed_statuses else "none"


def ai_message_task_id(message):
    raw = message.get("raw_response") if isinstance(message, dict) else message["raw_response"]
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return int(data["task_id"]) if data.get("task_id") not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_task_detail(task, parent_task, child_tasks, ai_messages, flow_runs):
    if not task:
        return None
    return {
        "task": task,
        "parent_task": parent_task,
        "child_tasks": child_tasks,
        "ai_messages": ai_messages,
        "flow_runs": flow_runs,
    }
