"""DevPilot AI 交接回寫工具

用法：
python scripts/report_handoff.py --base-url http://127.0.0.1:5000 --token YOUR_TOKEN --project-id 1 --source claude --summary "完成第三階段 API" --phase "第三階段" --test-result "測試通過"
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.request


def load_env_file():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"取得失敗：{exc}"


def main():
    load_env_file()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--token", default=os.getenv("DEV_PILOT_API_TOKEN") or os.getenv("API_TOKEN"))
    parser.add_argument("--project-id", required=True, type=int)
    parser.add_argument("--source", default="claude", choices=["codex", "claude", "cursor", "antigravity", "manual", "github", "deploy"])
    parser.add_argument("--agent-name", default="Claude Code")
    parser.add_argument(
        "--work-mode",
        default="code-change",
        choices=["planning", "review", "code-change", "debug", "test", "deploy", "manual", "agent-run"],
    )
    parser.add_argument("--summary", required=True)
    parser.add_argument("--phase", action="append", default=[])
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--test-result", default="")
    parser.add_argument("--next-steps", default="")
    parser.add_argument("--warnings", default="")
    args = parser.parse_args()
    if not args.token:
        parser.error("API token is required. Pass --token or set DEV_PILOT_API_TOKEN / API_TOKEN in .env.")

    git_status = run("git status --short") or "clean"
    repo_branch = run("git branch --show-current")
    commit_sha = run("git rev-parse --short HEAD")

    payload = {
        "source": args.source,
        "agent_name": args.agent_name,
        "work_mode": args.work_mode,
        "summary": args.summary,
        "completed_phases": args.phase,
        "changed_files": args.changed_file,
        "test_result": args.test_result,
        "git_status": git_status,
        "repo_branch": repo_branch,
        "commit_sha": commit_sha,
        "next_steps": args.next_steps,
        "warnings": args.warnings,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/api/projects/{args.project_id}/handoff",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {args.token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
