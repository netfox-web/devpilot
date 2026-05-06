import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import app as devpilot


POLL_INTERVAL_SECONDS = int(os.getenv("DEVPILOT_WORKER_POLL_SECONDS", "10"))
CODEX_MOCK = os.getenv("DEVPILOT_CODEX_MOCK", "").lower() in ("1", "true", "yes", "on")
CODEX_RUNNER_MODE = os.getenv("DEVPILOT_CODEX_RUNNER_MODE", "direct").strip().lower()
CODEX_RUNNER_COMMAND = os.getenv("DEVPILOT_CODEX_RUNNER_COMMAND", "").strip()


def queued_jobs(limit=3):
    return devpilot.query_all(
        """SELECT * FROM dispatch_jobs
           WHERE status='queued' AND COALESCE(agent, 'codex')='codex'
           ORDER BY created_at ASC, id ASC LIMIT ?""",
        (limit,),
    )


def claim_job(job_id):
    row = devpilot.query_one("SELECT status FROM dispatch_jobs WHERE id=?", (job_id,))
    if not row or row["status"] != "queued":
        return False
    devpilot.update_dispatch_job(job_id, status="running", started_at=devpilot.now_str(), error_message="")
    return True


def run_command(job_id, args, cwd, timeout=600):
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    devpilot.record_agent_run(
        job_id,
        " ".join(str(part) for part in args),
        result.stdout or "",
        result.stderr or "",
        result.returncode,
    )
    return result


def record_subprocess(job_id, command_text, result):
    devpilot.record_agent_run(
        job_id,
        command_text,
        result.stdout or "",
        result.stderr or "",
        result.returncode,
    )


def safe_worktree(job):
    repo = devpilot.project_repo_row(job["project_id"])
    expected_text = (repo or {}).get("worktree_path") or ""
    if not expected_text:
        raise RuntimeError("project_repos.worktree_path is required")
    expected = Path(expected_text).expanduser().resolve(strict=False)
    worktree = Path(job["worktree_path"] or expected).expanduser().resolve(strict=False)
    if not expected or worktree != expected:
        raise RuntimeError("dispatch job worktree_path does not match project_repos.worktree_path")
    if not worktree.exists() or not worktree.is_dir():
        raise RuntimeError(f"worktree_path does not exist: {worktree}")
    if devpilot.is_same_or_parent(worktree, devpilot.DEPLOY_ROOT):
        raise RuntimeError("worker refused to run inside deploy root")
    return worktree


def codex_help_text():
    codex_path = shutil.which("codex")
    if not codex_path:
        return "", None
    result = subprocess.run(
        [codex_path, "--help"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return (result.stdout or "") + (result.stderr or ""), codex_path


def codex_command(prompt):
    if CODEX_MOCK:
        return None
    help_text, codex_path = codex_help_text()
    if not codex_path:
        raise RuntimeError("codex CLI not found; set DEVPILOT_CODEX_MOCK=1 for mock worker tests")

    args = [codex_path]
    if "--approval-mode" in help_text:
        args.extend(["--approval-mode", "never"])
    if "--ask-for-approval" in help_text:
        args.extend(["--ask-for-approval", "never"])
    if "--sandbox" in help_text:
        args.extend(["--sandbox", "workspace-write"])
    elif "--sandbox-mode" in help_text:
        args.extend(["--sandbox-mode", "workspace-write"])

    if "exec" in help_text.lower():
        args.extend(["exec", prompt])
    else:
        args.append(prompt)
    return args


def external_runner_args(job, worktree, prompt):
    if not CODEX_RUNNER_COMMAND:
        raise RuntimeError("DEVPILOT_CODEX_RUNNER_COMMAND is required when runner mode is external")
    return [
        *shlex.split(CODEX_RUNNER_COMMAND),
        str(job["id"]),
        str(job["project_id"]),
        str(worktree),
        prompt,
    ]


def build_prompt(job):
    return "\n".join(
        [
            "You are running as the DevPilot Codex dispatch worker.",
            "Only modify files inside the assigned worktree.",
            "Do not modify /volume1/docker directly; it is the deploy/runtime path.",
            "Do not edit, overwrite, or delete .env.",
            "Do not delete data, uploads, backups, backup, or output directories.",
            "Do not run docker compose down, docker rm, docker rmi, or rm -rf /.",
            "When finished, include a concise change summary and test result.",
            "",
            "Task:",
            job["task_prompt"] or job["task"] or "",
        ]
    )


def run_codex(job, worktree):
    prompt = build_prompt(job)
    if CODEX_MOCK:
        marker = worktree / ".devpilot_worker_mock.txt"
        marker.write_text(
            f"mock codex run\njob_id={job['id']}\ntask={job['task_prompt'] or job['task']}\n",
            encoding="utf-8",
        )
        devpilot.record_agent_run(job["id"], "mock codex", f"wrote {marker}", "", 0)
        return

    if CODEX_RUNNER_MODE == "external":
        args = external_runner_args(job, worktree, prompt)
        result = subprocess.run(
            args,
            cwd=str(worktree),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )
        command_text = " ".join(str(part) for part in args[:-1]) + " <task_prompt>"
        record_subprocess(job["id"], command_text, result)
        if result.returncode != 0:
            raise RuntimeError(f"external codex runner exited {result.returncode}")
        return

    args = codex_command(prompt)
    if args is None:
        marker = worktree / ".devpilot_worker_mock.txt"
        marker.write_text(
            f"mock codex run\njob_id={job['id']}\ntask={job['task_prompt'] or job['task']}\n",
            encoding="utf-8",
        )
        devpilot.record_agent_run(job["id"], "mock codex", f"wrote {marker}", "", 0)
        return

    result = run_command(job["id"], args, worktree, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"codex exited {result.returncode}")


def run_project_tests(job_id, worktree):
    package_json = worktree / "package.json"
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            package = {}
        scripts = package.get("scripts") or {}
        if "test" in scripts:
            result = run_command(job_id, ["npm", "test"], worktree, timeout=900)
            if result.returncode != 0:
                raise RuntimeError("npm test failed")
        elif "build" in scripts:
            result = run_command(job_id, ["npm", "run", "build"], worktree, timeout=900)
            if result.returncode != 0:
                raise RuntimeError("npm run build failed")

    if (worktree / "requirements.txt").exists() or (worktree / "app.py").exists():
        app_py = worktree / "app.py"
        if app_py.exists():
            result = run_command(job_id, [sys.executable, "-m", "py_compile", "app.py"], worktree, timeout=120)
            if result.returncode != 0:
                raise RuntimeError("python -m py_compile app.py failed")


def process_job(job):
    job_id = job["id"]
    if not claim_job(job_id):
        return

    try:
        current = devpilot.dispatch_job_row(job_id)
        worktree = safe_worktree(current)
        run_codex(current, worktree)
        run_project_tests(job_id, worktree)
        devpilot.update_dispatch_job(
            job_id,
            status="waiting_approval",
            finished_at=devpilot.now_str(),
            error_message="",
            result=json.dumps({"worker": "codex", "tests": "passed"}, ensure_ascii=False),
        )
    except Exception as exc:
        devpilot.update_dispatch_job(
            job_id,
            status="failed",
            finished_at=devpilot.now_str(),
            error_message=str(exc),
        )


def run_once():
    with devpilot.app.app_context():
        for job in queued_jobs():
            process_job(job)


def run_forever():
    while True:
        run_once()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
