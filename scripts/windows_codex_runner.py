#!/usr/bin/env python
"""Windows-side DevPilot Codex runner.

Polls a DevPilot API for queued Codex dispatch jobs, runs them from a mapped
worktree path or SSH-assisted mock mode, and reports stdout/stderr back.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import posixpath
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib import error, parse, request


RUNNER_NAME = "windows codex runner"
DEFAULT_API_URL = "http://211.75.219.184:5010"
DEFAULT_SSH_HOST = "chaokun@211.75.219.184"
DEFAULT_REMOTE_WORKTREE_ROOT = "/volume1/worktrees"
DEFAULT_LOCAL_WORKTREE_ROOT = Path(r"C:\devpilot\worktrees")
DEFAULT_STAGING_ROOT = "/volume1/docker-staging"
FORBIDDEN_REMOTE_PREFIXES = (
    "/volume1/docker",
    "/volume1/backups",
)
FORBIDDEN_NAMES = {".env", "data", "uploads", "backups", "backup", "output"}
SYNC_EXCLUDE_NAMES = {".git", ".env", "data", "uploads", "backups", "backup", "output", "node_modules", ".venv"}
SYNC_EXCLUDE_PATTERNS = ("*.db", "*.sqlite", "*.sqlite3")
VERIFY_SKIP_DIRS = {".git"}
PROTECTED_CHANGE_NAMES = {".env", "data", "uploads", "backups", "backup", "output"}
PROTECTED_CHANGE_PATTERNS = ("*.db", "*.sqlite", "*.sqlite3")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_request(api_url: str, token: str, method: str, path: str, payload=None):
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = request.Request(api_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return json.loads(data) if data else {}
    except error.HTTPError as exc:
        data = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {data}") from exc


def assert_safe_remote_worktree(remote_path: str) -> None:
    normalized = remote_path.replace("\\", "/").rstrip("/")
    if not normalized.startswith("/volume1/worktrees/"):
        raise RuntimeError(f"refused worktree outside /volume1/worktrees: {remote_path}")
    for prefix in FORBIDDEN_REMOTE_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            raise RuntimeError(f"refused forbidden path: {remote_path}")
    parts = set(Path(normalized).parts)
    if parts & FORBIDDEN_NAMES:
        raise RuntimeError(f"refused protected path segment in worktree: {remote_path}")


def remote_worktree_slug(remote_path: str, remote_root: str = DEFAULT_REMOTE_WORKTREE_ROOT) -> str:
    normalized = posixpath.normpath(remote_path.replace("\\", "/"))
    root = posixpath.normpath(remote_root)
    if normalized == root or not normalized.startswith(root + "/"):
        raise RuntimeError(f"refused worktree outside {root}: {remote_path}")
    slug = normalized[len(root):].lstrip("/")
    if not slug or slug.startswith("../") or "/../" in f"/{slug}/":
        raise RuntimeError(f"invalid worktree slug from path: {remote_path}")
    return slug


def parse_worktree_maps(raw_maps: list[str]) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    for raw in raw_maps:
        for item in raw.split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" not in item:
                raise RuntimeError(f"invalid worktree map, expected remote=local: {item}")
            remote, local = item.split("=", 1)
            mappings.append((remote.rstrip("/\\"), local.rstrip("/\\")))
    return mappings


def mapped_worktree_path(remote_path: str, mappings: list[tuple[str, str]], local_root: Path) -> Path | None:
    remote_norm = remote_path.replace("\\", "/").rstrip("/")
    for remote_prefix, local_prefix in mappings:
        prefix_norm = remote_prefix.replace("\\", "/").rstrip("/")
        if remote_norm == prefix_norm or remote_norm.startswith(prefix_norm + "/"):
            suffix = remote_norm[len(prefix_norm):].lstrip("/")
            local = Path(local_prefix)
            for part in suffix.split("/"):
                if part:
                    local = local / part
            return local
    if remote_norm == DEFAULT_REMOTE_WORKTREE_ROOT or remote_norm.startswith(DEFAULT_REMOTE_WORKTREE_ROOT + "/"):
        slug = remote_worktree_slug(remote_norm)
        local = local_root
        for part in slug.split("/"):
            if part:
                local = local / part
        return local
    direct = Path(remote_path)
    return direct if direct.exists() else None


def assert_safe_local_worktree(local_worktree: Path, local_root: Path) -> None:
    root = local_root.resolve(strict=False)
    target = local_worktree.resolve(strict=False)
    if target != root and root not in target.parents:
        raise RuntimeError(f"refused local worktree outside {root}: {target}")


def ensure_local_worktree(local_worktree: Path, local_root: Path) -> Path:
    assert_safe_local_worktree(local_worktree, local_root)
    local_worktree.mkdir(parents=True, exist_ok=True)
    return local_worktree


def run_text_command(command: list[str], cwd: Path, timeout: int = 60) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return result.stdout or "", result.stderr or "", result.returncode
    except FileNotFoundError as exc:
        return "", str(exc), 127
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return stdout, f"{stderr}\ncommand timed out after {timeout}s", 124


def git_text(local_worktree: Path, *git_args: str) -> str:
    stdout, _stderr, exit_code = run_text_command(["git", *git_args], local_worktree)
    return stdout.strip() if exit_code == 0 else ""


def changed_files_from_git_status(status_text: str) -> list[str]:
    files: list[str] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        path_text = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        files.append(path_text.strip('"'))
    return files


def snapshot_worktree_files(local_worktree: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    if not local_worktree.exists():
        return snapshot
    for path in local_worktree.rglob("*"):
        rel = path.relative_to(local_worktree).as_posix()
        if any(part in VERIFY_SKIP_DIRS for part in Path(rel).parts):
            continue
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[rel] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def capture_worktree_state(local_worktree: Path) -> dict:
    diff_parts = [
        git_text(local_worktree, "diff", "--stat"),
        git_text(local_worktree, "diff", "--cached", "--stat"),
    ]
    return {
        "git_status": git_text(local_worktree, "status", "--short"),
        "diff_stat": "\n".join(part for part in diff_parts if part).strip(),
        "files": snapshot_worktree_files(local_worktree),
    }


def compare_worktree_states(before: dict | None, after: dict | None) -> dict:
    before = before or {"git_status": "", "diff_stat": "", "files": {}}
    after = after or {"git_status": "", "diff_stat": "", "files": {}}
    changed = set(changed_files_from_git_status(after.get("git_status", "")))
    changed.difference_update(changed_files_from_git_status(before.get("git_status", "")))

    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    for rel, stamp in after_files.items():
        if before_files.get(rel) != stamp:
            changed.add(rel)
    for rel in before_files:
        if rel not in after_files:
            changed.add(f"{rel} (deleted)")

    changed_files = sorted(changed)
    diff_stat = after.get("diff_stat") or ""
    if changed_files and not diff_stat:
        diff_stat = "\n".join(f"{path} | changed" for path in changed_files[:80])
    return {"changed_files": changed_files, "diff_stat": diff_stat}


def is_protected_changed_path(rel: str) -> bool:
    clean_rel = rel.replace("\\", "/").replace(" (deleted)", "")
    parts = set(Path(clean_rel).parts)
    if parts & PROTECTED_CHANGE_NAMES:
        return True
    return any(fnmatch.fnmatch(Path(clean_rel).name, pattern) for pattern in PROTECTED_CHANGE_PATTERNS)


def format_change_report(before: dict | None, after: dict | None, report: dict) -> str:
    changed_files = report.get("changed_files") or []
    lines = [
        "before git status --short:",
        before.get("git_status", "") if before else "",
        "",
        "after git status --short:",
        after.get("git_status", "") if after else "",
        "",
        "changed files:",
        "\n".join(f"- {path}" for path in changed_files) if changed_files else "(none)",
        "",
        "git diff --stat:",
        report.get("diff_stat") or "(none)",
    ]
    return "\n".join(lines).rstrip()


def build_prompt(job: dict) -> str:
    return "\n".join(
        [
            "You are running as a Windows DevPilot Codex runner.",
            "Only modify files inside the assigned Windows local worktree.",
            "Do not modify /volume1/docker or production deploy paths.",
            "If files are synced back, only sync to /volume1/docker-staging.",
            "Do not edit, overwrite, or delete .env.",
            "Do not delete data, uploads, backups, output, or *.db files.",
            "Do not deploy production.",
            "Do not run docker compose down, docker stop, docker restart, docker rm, docker rmi, or rm -rf.",
            "When finished, include a concise change summary and test result.",
            "",
            "Task:",
            job.get("task_prompt") or job.get("task") or "",
        ]
    )


def write_mock_marker_local(local_worktree: Path, job: dict, prompt: str) -> tuple[str, str, int]:
    local_worktree.mkdir(parents=True, exist_ok=True)
    marker = local_worktree / ".devpilot_windows_runner_mock.txt"
    marker.write_text(
        "\n".join(
            [
                "windows codex runner mock",
                f"job_id={job['id']}",
                f"project_id={job['project_id']}",
                f"remote_worktree={job.get('worktree_path')}",
                "",
                prompt,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return f"mock wrote {marker}", "", 0


def write_mock_marker_ssh(ssh_host: str, remote_worktree: str, job: dict, prompt: str) -> tuple[str, str, int]:
    q_worktree = shlex.quote(remote_worktree)
    command = f"mkdir -p {q_worktree} && cat > {q_worktree}/.devpilot_windows_runner_mock.txt"
    content = "\n".join(
        [
            "windows codex runner mock via ssh",
            f"job_id={job['id']}",
            f"project_id={job['project_id']}",
            f"remote_worktree={remote_worktree}",
            "",
            prompt,
            "",
        ]
    )
    result = subprocess.run(
        ["ssh", ssh_host, command],
        input=content,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    stdout = (result.stdout or "") + f"mock wrote {remote_worktree}/.devpilot_windows_runner_mock.txt via ssh\n"
    return stdout, result.stderr or "", result.returncode


def codex_args(codex_command: str, prompt: str) -> list[str]:
    base = shlex.split(codex_command, posix=False)
    if not base:
        raise RuntimeError("codex command is empty")
    exe = shutil.which(base[0]) or base[0]
    try:
        help_result = subprocess.run(
            [exe, "--help"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        help_text = (help_result.stdout or "") + (help_result.stderr or "")
    except Exception:
        help_text = ""
    args = [exe, *base[1:]]
    if "--approval-mode" in help_text:
        args.extend(["--approval-mode", "never"])
    if "--ask-for-approval" in help_text:
        args.extend(["--ask-for-approval", "never"])
    if "--sandbox" in help_text:
        args.extend(["--sandbox", "workspace-write"])
    elif "--sandbox-mode" in help_text:
        args.extend(["--sandbox-mode", "workspace-write"])
    if "exec" in help_text.lower():
        try:
            exec_help_result = subprocess.run(
                [exe, "exec", "--help"],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            exec_help_text = (exec_help_result.stdout or "") + (exec_help_result.stderr or "")
        except Exception:
            exec_help_text = ""
        args.append("exec")
        if "--skip-git-repo-check" in exec_help_text:
            args.append("--skip-git-repo-check")
        args.append(prompt)
    else:
        args.append(prompt)
    return args


def run_codex_local(local_worktree: Path, codex_command: str, prompt: str) -> tuple[str, str, int]:
    args = codex_args(codex_command, prompt)
    result = subprocess.run(
        args,
        cwd=str(local_worktree),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )
    return result.stdout or "", result.stderr or "", result.returncode


def should_exclude_from_sync(path: Path, rel: str) -> bool:
    parts = set(Path(rel).parts)
    if parts & SYNC_EXCLUDE_NAMES:
        return True
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in SYNC_EXCLUDE_PATTERNS)


def build_worktree_tar(local_worktree: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in local_worktree.rglob("*"):
            rel = path.relative_to(local_worktree).as_posix()
            if should_exclude_from_sync(path, rel):
                continue
            archive.add(path, arcname=rel, recursive=False)
    return buffer.getvalue()


def sync_local_worktree_to_staging(args, local_worktree: Path, remote_worktree: str) -> tuple[str, str, int]:
    if not args.ssh_host:
        raise RuntimeError("--sync-staging requires --ssh-host")
    slug = remote_worktree_slug(remote_worktree)
    staging_root = posixpath.normpath(args.staging_root)
    if staging_root != DEFAULT_STAGING_ROOT and not staging_root.startswith(DEFAULT_STAGING_ROOT + "/"):
        raise RuntimeError(f"refused staging root outside {DEFAULT_STAGING_ROOT}: {args.staging_root}")
    staging_path = posixpath.join(staging_root, slug)
    if not staging_path.startswith(DEFAULT_STAGING_ROOT + "/"):
        raise RuntimeError(f"refused unsafe staging path: {staging_path}")
    archive = build_worktree_tar(local_worktree)
    command = f"mkdir -p {shlex.quote(staging_path)} && tar -xf - -C {shlex.quote(staging_path)}"
    result = subprocess.run(
        ["ssh", args.ssh_host, command],
        input=archive,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    if result.returncode == 0:
        stdout += f"synced local worktree {local_worktree} to {args.ssh_host}:{staging_path}\n"
    return stdout, stderr, result.returncode


def repo_for_project(args, project_id: int) -> dict:
    data = api_request(args.api_url, args.token, "GET", f"/api/projects/{project_id}/repo-status")
    repo = data.get("repo") or {}
    if not repo.get("worktree_path"):
        raise RuntimeError(f"project {project_id} has no project_repos.worktree_path")
    return repo


def sync_project_staging_only(args, mappings: list[tuple[str, str]]) -> int:
    if not args.project_id:
        raise RuntimeError("--sync-only requires --project-id")
    repo = repo_for_project(args, args.project_id)
    remote_worktree = repo.get("worktree_path") or ""
    assert_safe_remote_worktree(remote_worktree)
    local_worktree = mapped_worktree_path(remote_worktree, mappings, args.local_worktree_root)
    if not local_worktree:
        raise RuntimeError(f"could not map remote worktree to local path: {remote_worktree}")
    local_worktree = ensure_local_worktree(local_worktree, args.local_worktree_root)
    if not local_worktree.exists():
        raise RuntimeError(f"local worktree does not exist: {local_worktree}")
    stdout, stderr, exit_code = sync_local_worktree_to_staging(args, local_worktree, remote_worktree)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
    if exit_code == 0:
        slug = remote_worktree_slug(remote_worktree)
        print(f"sync-only complete: project_id={args.project_id} local={local_worktree} staging={posixpath.join(args.staging_root, slug)}")
    else:
        print(f"sync-only failed: project_id={args.project_id} exit_code={exit_code}", file=sys.stderr)
    return exit_code


def claim_and_run_job(args, job: dict, mappings: list[tuple[str, str]]) -> None:
    job_id = job["id"]
    remote_worktree = job.get("worktree_path") or ""
    assert_safe_remote_worktree(remote_worktree)
    api_request(args.api_url, args.token, "PATCH", f"/api/dispatch-jobs/{job_id}/status", {"status": "running"})
    prompt = build_prompt(job)
    command_label = "windows codex runner mock" if args.mock else args.codex_command
    stdout = ""
    stderr = ""
    exit_code = 1
    changed_files: list[str] = []
    diff_stat = ""
    try:
        local_worktree = mapped_worktree_path(remote_worktree, mappings, args.local_worktree_root)
        if local_worktree:
            local_worktree = ensure_local_worktree(local_worktree, args.local_worktree_root)
        before_state = capture_worktree_state(local_worktree) if local_worktree else None
        if args.mock:
            if args.mock_no_change and local_worktree:
                stdout, stderr, exit_code = "mock completed without changing files", "", 0
            elif local_worktree:
                stdout, stderr, exit_code = write_mock_marker_local(local_worktree, job, prompt)
            elif args.ssh_host:
                stdout, stderr, exit_code = write_mock_marker_ssh(args.ssh_host, remote_worktree, job, prompt)
            else:
                raise RuntimeError("mock mode needs a mapped worktree or --ssh-host")
        else:
            if not local_worktree:
                raise RuntimeError("real Codex mode requires a mapped local worktree path")
            stdout, stderr, exit_code = run_codex_local(local_worktree, args.codex_command, prompt)

        if local_worktree:
            after_state = capture_worktree_state(local_worktree)
            change_report = compare_worktree_states(before_state, after_state)
            changed_files = change_report["changed_files"]
            diff_stat = change_report["diff_stat"]
            verification_report = format_change_report(before_state, after_state, change_report)
            stdout = (stdout + "\n\n" if stdout else "") + "[DevPilot worktree change verification]\n" + verification_report

            protected_changes = [path for path in changed_files if is_protected_changed_path(path)]
            if exit_code == 0 and not changed_files:
                stderr = (stderr + "\n" if stderr else "") + "Codex 執行成功但未產生任何檔案變更"
                exit_code = 1
            elif exit_code == 0 and protected_changes:
                stderr = (stderr + "\n" if stderr else "") + "Codex 修改了受保護檔案，已拒絕通過：" + ", ".join(protected_changes)
                exit_code = 1
        else:
            stdout = (stdout + "\n\n" if stdout else "") + "[DevPilot worktree change verification]\nskipped: no mapped local worktree"

        if exit_code == 0 and args.sync_staging and local_worktree:
            sync_stdout, sync_stderr, sync_code = sync_local_worktree_to_staging(args, local_worktree, remote_worktree)
            stdout = (stdout + "\n" if stdout else "") + sync_stdout
            stderr = (stderr + "\n" if stderr else "") + sync_stderr
            exit_code = sync_code
    except Exception as exc:
        stderr = (stderr + "\n" if stderr else "") + str(exc)
        exit_code = 1
    api_request(
        args.api_url,
        args.token,
        "POST",
        f"/api/dispatch-jobs/{job_id}/agent-runs",
        {"command": command_label, "stdout": stdout, "stderr": stderr, "exit_code": exit_code},
    )
    next_status = "waiting_approval" if exit_code == 0 else "failed"
    api_request(
        args.api_url,
        args.token,
        "PATCH",
        f"/api/dispatch-jobs/{job_id}/status",
        {
            "status": next_status,
            "error_message": stderr if exit_code else "",
            "changed_files": changed_files,
            "diff_stat": diff_stat,
            "result": {"runner": RUNNER_NAME, "mock": args.mock, "exit_code": exit_code},
        },
    )
    print(f"job {job_id}: {next_status}")


def poll_once(args, mappings: list[tuple[str, str]]) -> int:
    query_params = {"status": "queued", "agent": args.agent, "limit": args.limit}
    if args.project_id:
        query_params["project_id"] = args.project_id
    query = parse.urlencode(query_params)
    data = api_request(args.api_url, args.token, "GET", f"/api/dispatch-jobs?{query}")
    jobs = data.get("jobs") or []
    if not jobs:
        print("no queued jobs")
        return 0
    for job in jobs:
        claim_and_run_job(args, job, mappings)
    return len(jobs)


def parse_args(argv=None):
    env = load_env_file(Path(".env"))
    parser = argparse.ArgumentParser(description="Poll DevPilot and run Codex jobs from Windows.")
    parser.add_argument("--api-url", default=os.getenv("DEV_PILOT_API_URL") or env.get("DEV_PILOT_API_URL") or DEFAULT_API_URL)
    parser.add_argument("--token", default=os.getenv("DEV_PILOT_API_TOKEN") or os.getenv("API_TOKEN") or env.get("DEV_PILOT_API_TOKEN") or env.get("API_TOKEN"))
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock-no-change", action="store_true", help="mock runner exits 0 without modifying files; useful for verification tests")
    parser.add_argument("--agent", default="codex")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--project-id", type=int)
    parser.add_argument("--local-worktree-root", type=Path, default=Path(os.getenv("DEVPILOT_LOCAL_WORKTREE_ROOT", str(DEFAULT_LOCAL_WORKTREE_ROOT))))
    parser.add_argument("--worktree-map", action="append", default=[os.getenv("DEVPILOT_WORKTREE_MAP", "")])
    parser.add_argument("--ssh-host", default=os.getenv("DEVPILOT_RUNNER_SSH_HOST", DEFAULT_SSH_HOST))
    parser.add_argument("--sync-only", action="store_true", help="sync a project's local worktree to staging without polling queued jobs")
    parser.add_argument("--sync-staging", action="store_true", default=os.getenv("DEVPILOT_SYNC_STAGING", "").lower() in ("1", "true", "yes", "on"))
    parser.add_argument("--staging-root", default=os.getenv("DEVPILOT_STAGING_ROOT", DEFAULT_STAGING_ROOT))
    parser.add_argument("--codex-command", default=os.getenv("DEVPILOT_CODEX_COMMAND", "codex"))
    args = parser.parse_args(argv)
    if not args.token:
        raise SystemExit("API token is required via --token, API_TOKEN, or DEV_PILOT_API_TOKEN")
    if args.mock_no_change:
        args.mock = True
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    mappings = parse_worktree_maps([item for item in args.worktree_map if item])
    if args.sync_only:
        return sync_project_staging_only(args, mappings)
    while True:
        poll_once(args, mappings)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
