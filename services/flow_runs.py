import re


def compact_text(value, limit=160):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def build_summary(project_id, mode, status, stopped_reason, executed_tasks, counts, messages=None, error_message=None):
    lines = [
        f"Flow mode: {mode}",
        f"Status: {status}",
        f"Stopped reason: {stopped_reason}",
        (
            "Task counts: "
            f"total={counts['total']}, done={counts['done']}, failed={counts['failed']}, "
            f"queued={counts['queued']}, blocked={counts['blocked']}"
        ),
    ]
    lines.append("Executed tasks:")
    if executed_tasks:
        for item in executed_tasks:
            title = item.get("title") or "-"
            task_type = item.get("task_type") or "-"
            task_status = item.get("status") or "-"
            approval = item.get("approval_status") or "none"
            error = item.get("error") or ""
            suffix = f" error={error}" if error else ""
            lines.append(f"- #{item.get('task_id')} {title} ({task_type}) -> {task_status}, approval={approval}{suffix}")
    else:
        lines.append("- No task executed.")

    if messages:
        lines.append("AI messages:")
        for message in messages:
            text = message.get("response_text") or message.get("error_message") or message.get("prompt_summary") or ""
            lines.append(f"- {message.get('provider')}/{message.get('status')}: {compact_text(text)}")

    next_steps = {
        "completed": "Review the summary and decide whether to create the next task batch.",
        "approval_required": "Review the pending task output, then approve or reject before continuing.",
        "failed": "Inspect failed task error_message and retry after fixing provider or prompt issues.",
        "no_queued_task": "Create or queue AI tasks before running the flow again.",
        "blocked_by_safety": "Review task_type and remove deploy/shell/ssh/docker style work from full auto mode.",
        "error": "Inspect server logs and retry after the exception is fixed.",
    }
    lines.append(f"Suggested next step: {next_steps.get(stopped_reason, 'Review flow result manually.')}")
    if error_message:
        lines.append(f"Error: {error_message}")
    return "\n".join(lines)
