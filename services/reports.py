import html as html_lib
import json
import re


def report_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(report_text(item) for item in value)
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def report_cell(value):
    text = report_text(value).replace("\n", "<br>")
    return text.replace("|", "\\|") or "-"


def report_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    if rows:
        for row in rows:
            lines.append("| " + " | ".join(report_cell(cell) for cell in row) + " |")
    else:
        lines.append("| " + " | ".join(["-"] * len(headers)) + " |")
    return "\n".join(lines)


def report_bullets(items):
    values = [report_text(item) for item in items if report_text(item)]
    return "\n".join(f"- {item}" for item in values) if values else "- none"


def parse_report_list(value, parse_json_list_func=None):
    if parse_json_list_func:
        items = parse_json_list_func(value)
    else:
        try:
            items = json.loads(value or "[]")
        except (TypeError, ValueError):
            items = []
    if items:
        return items
    return [line.strip() for line in report_text(value).splitlines() if line.strip()]


def build_engineering_report_markdown(data, parse_json_list_func=None, machine_display_name_func=None):
    project = data["project"]
    project_id = project.get("id")
    repo = data.get("project_repo") or {}
    machine_display_name_func = machine_display_name_func or (lambda value: value)
    lines = [
        f"# DevPilot 工程報告 - {project.get('name') or f'Project {project_id}'}",
        "",
        f"- 產生時間：{data['generated_at']}",
        f"- Project ID：{project.get('id')}",
        f"- 客戶：{project.get('client_name') or '-'}",
        f"- 類型：{project.get('project_type') or '-'}",
        f"- 狀態：{project.get('status') or '-'}",
        f"- 優先級：{project.get('priority') or '-'}",
        f"- 進度：{project.get('progress') or 0}%",
        f"- 下一步：{project.get('next_steps') or '-'}",
        "",
        "## 基本資料",
        "",
        report_table(
            ["項目", "內容"],
            [
                ["GitHub / Repo", project.get("github_repo") or repo.get("repo_url") or "-"],
                ["Local Path", project.get("local_path") or "-"],
                ["Deploy URL", project.get("deploy_url") or "-"],
                ["Deploy Location", project.get("deploy_location") or "-"],
                ["Owner Machine", machine_display_name_func(project.get("owner_machine")) or "-"],
                ["Description", project.get("description") or "-"],
            ],
        ),
        "",
        "## Repo / Worktree / Deploy",
        "",
        report_table(
            ["Repo URL", "Repo Path", "Worktree Path", "Deploy Path", "Status", "Branch", "Last Commit"],
            [[
                repo.get("repo_url") or "-",
                repo.get("repo_path") or "-",
                repo.get("worktree_path") or "-",
                repo.get("deploy_path") or "-",
                repo.get("repo_status") or "-",
                repo.get("branch") or "-",
                (repo.get("last_commit") or "-")[:12],
            ]] if repo else [],
        ),
        "",
        "## 階段",
        "",
        report_table(
            ["#", "Phase", "Status", "Due", "Completed", "Test Result", "Notes"],
            [[p.get("phase_order"), p.get("phase_name"), p.get("status"), p.get("due_date"), p.get("completed_at"), p.get("test_result"), p.get("notes")] for p in data.get("phases", [])],
        ),
        "",
        "## 專案任務",
        "",
        report_table(
            ["Task", "Status", "Priority", "Assignee", "Due", "Completed"],
            [[t.get("title"), t.get("status"), t.get("priority"), t.get("assignee"), t.get("due_date"), t.get("completed_at")] for t in data.get("project_tasks", [])],
        ),
        "",
        "## AI Tasks",
        "",
        report_table(
            ["ID", "Title", "Provider", "Type", "Status", "Priority", "Retry", "Approval", "Updated"],
            [[t.get("id"), t.get("title"), t.get("provider"), t.get("task_type"), t.get("status"), t.get("priority"), f"{t.get('retry_count') or 0}/{t.get('max_retries') if t.get('max_retries') is not None else 3}", t.get("approval_status"), t.get("updated_at")] for t in data.get("ai_tasks", [])],
        ),
        "",
        "## AI Flow Runs",
        "",
        report_table(
            ["ID", "Mode", "Status", "Done", "Failed", "Stopped Reason", "Started", "Finished"],
            [[r.get("id"), r.get("mode"), r.get("status"), r.get("done_tasks"), r.get("failed_tasks"), r.get("stopped_reason"), r.get("started_at"), r.get("finished_at")] for r in data.get("flow_runs", [])],
        ),
        "",
        "## AI Dispatch Jobs",
        "",
        report_table(
            ["ID", "Agent", "Status", "Risk", "Worktree", "Deploy", "Updated", "Error"],
            [[j.get("id"), j.get("agent"), j.get("status"), j.get("risk_level"), j.get("worktree_path"), j.get("deploy_path"), j.get("updated_at"), j.get("error_message")] for j in data.get("dispatch_jobs", [])],
        ),
        "",
        "## 部署位置",
        "",
        report_table(
            ["Environment", "Target", "Type", "Service", "Port", "Deploy Path", "Compose Path", "Status"],
            [[d.get("environment"), d.get("target_name"), d.get("deploy_type"), d.get("service_name"), d.get("port"), d.get("deploy_path"), d.get("compose_path"), d.get("status")] for d in data.get("deployments", [])],
        ),
        "",
        "## 部署 Jobs / 驗收",
        "",
        report_table(
            ["Job", "Env", "Status", "Validation", "Target Path", "Updated", "Notes"],
            [[j.get("id"), j.get("environment"), j.get("status"), j.get("validation_status"), j.get("target_path"), j.get("updated_at"), j.get("notes")] for j in data.get("deployment_jobs", [])],
        ),
        "",
        report_table(
            ["Validation", "Provider", "Status", "Score", "Summary", "Created"],
            [[r.get("id"), r.get("provider"), r.get("status"), r.get("score"), r.get("summary"), r.get("created_at")] for r in data.get("validation_reports", [])],
        ),
        "",
        "## Docker 服務與端點",
        "",
        report_table(
            ["Container", "Image", "Status", "Ports", "Deploy Path", "Compose Path", "Last Seen"],
            [[s.get("container_name"), s.get("image"), s.get("status"), s.get("ports"), s.get("deploy_path"), s.get("compose_path"), s.get("last_seen_at")] for s in data.get("docker_services", [])],
        ),
        "",
        report_table(
            ["Type", "URL", "Status Code", "Title", "Container", "Checked"],
            [[e.get("endpoint_type"), e.get("url"), e.get("status_code"), e.get("title"), e.get("container_name"), e.get("last_checked_at")] for e in data.get("service_endpoints", [])],
        ),
        "",
        "## 交接紀錄",
        "",
    ]
    if data.get("handoffs"):
        for handoff in data["handoffs"]:
            lines.extend([
                f"### Handoff #{handoff.get('id')} - {handoff.get('source') or '-'} / {handoff.get('work_mode') or '-'}",
                "",
                f"- 建立時間：{handoff.get('created_at') or '-'}",
                f"- Agent：{handoff.get('agent_name') or '-'}",
                f"- Branch：{handoff.get('repo_branch') or '-'}",
                f"- Commit：{handoff.get('commit_sha') or '-'}",
                f"- Summary：{handoff.get('summary') or '-'}",
                "",
                "**Completed Phases**",
                report_bullets(parse_report_list(handoff.get("completed_phases"), parse_json_list_func)),
                "",
                "**Changed Files**",
                report_bullets(parse_report_list(handoff.get("changed_files"), parse_json_list_func)),
                "",
                f"**Test Result**\n\n{handoff.get('test_result') or '-'}",
                "",
                f"**Next Steps**\n\n{handoff.get('next_steps') or '-'}",
                "",
                f"**Warnings**\n\n{handoff.get('warnings') or '-'}",
                "",
            ])
    else:
        lines.extend(["- none", ""])

    lines.extend([
        "## 驗收項目",
        "",
        report_table(
            ["Title", "Status", "Tested", "Accepted", "Notes", "Updated"],
            [[a.get("title"), a.get("status"), "yes" if a.get("tested") else "no", "yes" if a.get("accepted") else "no", a.get("notes"), a.get("updated_at")] for a in data.get("acceptance", [])],
        ),
        "",
        "## 建議下一步",
        "",
        report_bullets([
            project.get("next_steps"),
            "Review failed or blocked AI tasks before the next flow run." if any((t.get("status") in ("failed", "blocked")) for t in data.get("ai_tasks", [])) else "",
            "Confirm staging validation before any production deployment." if data.get("deployment_jobs") else "",
            "Keep handoff updated after each AI or deployment run.",
        ]),
        "",
    ])
    return "\n".join(lines)


def markdown_to_html(markdown_text):
    html_lines = [
        "<!doctype html>",
        "<html lang=\"zh-Hant\">",
        "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>DevPilot 工程報告</title>",
        "<style>body{font-family:Arial,'Microsoft JhengHei',sans-serif;line-height:1.6;color:#1f2937;margin:32px;}table{border-collapse:collapse;width:100%;margin:12px 0 24px;}th,td{border:1px solid #d1d5db;padding:6px 8px;vertical-align:top;}th{background:#f3f4f6;}pre{white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;padding:12px;border-radius:6px;}code{background:#f3f4f6;padding:1px 4px;border-radius:4px;}h1,h2,h3{line-height:1.25;}a{color:#0d6efd;}</style>",
        "</head><body>",
    ]
    in_table = False
    in_list = False
    in_pre = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            html_lines.append("</pre>" if in_pre else "<pre>")
            in_pre = not in_pre
            continue
        if in_pre:
            html_lines.append(html_lib.escape(line))
            continue
        if line.startswith("| ") and line.endswith(" |"):
            cells = [html_lib.escape(cell.strip()).replace("&lt;br&gt;", "<br>") for cell in line.strip("|").split("|")]
            if all(set(cell.replace(" ", "")) <= {"-"} for cell in cells):
                continue
            if not in_table:
                html_lines.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            html_lines.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if in_table:
            html_lines.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html_lib.escape(line[2:])}</li>")
            continue
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        if line.startswith("# "):
            html_lines.append(f"<h1>{html_lib.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html_lib.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{html_lib.escape(line[4:])}</h3>")
        elif line.strip():
            html_lines.append(f"<p>{html_lib.escape(line)}</p>")
        else:
            html_lines.append("")
    if in_table:
        html_lines.append("</table>")
    if in_list:
        html_lines.append("</ul>")
    if in_pre:
        html_lines.append("</pre>")
    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def engineering_report_filename(project, extension, project_slug_func, today_str_func):
    slug = project_slug_func(project.get("name"), f"project-{project.get('id')}")
    return f"devpilot-engineering-report-{slug}-{today_str_func()}.{extension}"
