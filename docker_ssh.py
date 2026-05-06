"""
NAS Docker 唯讀掃描 — 透過 SSH 執行固定白名單指令（find / docker ps / docker inspect）。
禁止：rm、docker stop／restart／compose down／compose up 等寫入或服務操控。
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from typing import Any

# Docker 掃描根目錄僅允許 Synology Volume 底下的 docker（或子路徑）
SAFE_ROOT_RE = re.compile(r"^/volume\d+/docker(?:/.*)?$")
# compose 容器 ID：hex，長度 64；舊版可為 12
SAFE_CONTAINER_ID_RE = re.compile(r"^[a-f0-9]{12,64}$")

DOCKER_BIN_PROBE = r'''
DOCKER_BIN="$(command -v docker 2>/dev/null || true)"
if [ -z "$DOCKER_BIN" ] && [ -x /usr/local/bin/docker ]; then DOCKER_BIN=/usr/local/bin/docker; fi
if [ -z "$DOCKER_BIN" ] && [ -x /var/packages/ContainerManager/target/usr/bin/docker ]; then DOCKER_BIN=/var/packages/ContainerManager/target/usr/bin/docker; fi
if [ -z "$DOCKER_BIN" ] && [ -x /var/packages/Docker/target/usr/bin/docker ]; then DOCKER_BIN=/var/packages/Docker/target/usr/bin/docker; fi
if [ -z "$DOCKER_BIN" ]; then echo "docker command not found" >&2; exit 127; fi
'''


def normalize_docker_root(path: str | None, default: str = "/volume1/docker") -> str:
    p = (path or default or "").strip().rstrip("/")
    if not p:
        p = default.rstrip("/")
    if not SAFE_ROOT_RE.match(p):
        raise ValueError("docker_root 必須以 /volume{數字}/docker 開頭且不包含危險字元")
    return p


def _ssh_argv(ssh_host: str, ssh_port: str | int | None, ssh_user: str) -> list[str]:
    args: list[str] = [
        "ssh",
        "-oBatchMode=yes",
        "-oConnectTimeout=25",
        "-oStrictHostKeyChecking=accept-new",
        "-oUserKnownHostsFile=/tmp/devpilot_known_hosts",
        "-i",
        "/root/.ssh/devpilot_scan_ed25519",
    ]
    if ssh_port not in (None, "", "22"):
        args.extend(["-p", str(int(ssh_port))])
    user = (ssh_user or "").strip()
    host = (ssh_host or "").strip()
    args.append(f"{user}@{host}")
    return args


def ssh_bash_lc(ssh_host: str, ssh_port: str | int | None, ssh_user: str, script: str, timeout: int = 180) -> str:
    """在遠端執行 bash -lc SCRIPT，回傳 stdout。"""
    # OpenSSH concatenates remote command arguments before handing them to the
    # remote shell, so quote the whole bash script as one argument.
    argv = _ssh_argv(ssh_host, ssh_port, ssh_user) + [f"bash -lc {shlex.quote(script)}"]
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    err = (proc.stderr or "").strip()
    out = proc.stdout or ""
    if proc.returncode != 0:
        tail = err or out[-2000:] or "(no output)"
        raise RuntimeError(f"SSH 指令結束碼 {proc.returncode}: {tail}")
    return out


def find_compose_files(ssh_host: str, ssh_port: str | int | None, ssh_user: str, docker_root: str) -> list[str]:
    root = normalize_docker_root(docker_root)
    script = f"find {shlex.quote(root)} -maxdepth 3 -name docker-compose.yml -print 2>/dev/null || true"
    raw = ssh_bash_lc(ssh_host, ssh_port, ssh_user, script, timeout=120)
    paths = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return sorted(set(paths))


def docker_ps_json_lines(ssh_host: str, ssh_port: str | int | None, ssh_user: str) -> list[dict[str, Any]]:
    # 勿改為互動或可注入字串；格式固定為 json 模板
    script = DOCKER_BIN_PROBE + r'''"$DOCKER_BIN" ps -a --format "{{json .}}" 2>/dev/null'''
    raw = ssh_bash_lc(ssh_host, ssh_port, ssh_user, script, timeout=600)
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def docker_inspect_full(ssh_host: str, ssh_port: str | int | None, ssh_user: str, container_id: str) -> dict[str, Any] | None:
    """唯讀：完整 docker inspect JSON（第一筆物件）。"""
    cid = (container_id or "").strip().lower()
    if not SAFE_CONTAINER_ID_RE.match(cid):
        return None
    script = DOCKER_BIN_PROBE + '"$DOCKER_BIN" inspect {} 2>/dev/null'.format(cid)
    try:
        raw = ssh_bash_lc(ssh_host, ssh_port, ssh_user, script, timeout=90)
    except RuntimeError:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        arr = json.loads(raw)
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            return arr[0]
    except json.JSONDecodeError:
        return None
    return None


def summarize_scan(compose_paths: list, containers: list) -> dict[str, Any]:
    return {
        "compose_file_count": len(compose_paths),
        "container_count": len(containers),
    }
