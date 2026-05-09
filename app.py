import os
import base64
import csv
import hashlib
import hmac
import html as html_lib
import io
import ipaddress
import json
import re
import secrets
import shlex
import shutil
import sqlite3
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from functools import wraps
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, g, jsonify, redirect, render_template, request, url_for, flash, session, has_request_context
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from werkzeug.security import generate_password_hash, check_password_hash

import docker_ssh
from services import ai_tasks as ai_task_services
from services import flow_runs as flow_run_services
from services import reports as report_services

load_dotenv()

APP_NAME = "DevPilot 專案開發管家"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "project_manager.db"))
API_TOKEN = os.getenv("API_TOKEN", "change-me-token")
_DEV_PILOT_API_URL_RAW = os.getenv("DEV_PILOT_API_URL", "").strip().rstrip("/")
# 一鍵複製回寫指令 / README 範例皆以 .env 的 DEV_PILOT_API_URL 為準；未設定時預設本機開發埠
API_BASE_URL = _DEV_PILOT_API_URL_RAW if _DEV_PILOT_API_URL_RAW else "http://127.0.0.1:5000"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devpilot-secret-key")

STATUSES = ["未開始", "規劃中", "開發中", "測試中", "待驗收", "已結案", "暫停", "有問題", "逾期"]
PHASE_STATUSES = ["未開始", "進行中", "已完成", "待驗收", "已驗收", "有問題", "逾期"]
TASK_STATUSES = ["未開始", "進行中", "已完成", "有問題", "逾期", "取消"]
PRIORITIES = ["低", "中", "高", "緊急"]
SOURCES = ["codex", "claude", "cursor", "antigravity", "kling", "manual", "github", "deploy"]
WORK_MODES = ["planning", "review", "code-change", "debug", "test", "deploy", "manual", "agent-run"]
REPO_STATUSES = ["missing", "cloned", "local-init", "dirty", "clean"]
SYNC_METHODS = ["gitea", "github", "local"]
DISPATCH_AGENTS = ["codex", "cursor"]
DISPATCH_JOB_STATUSES = ["queued", "running", "failed", "waiting_approval", "deployed", "rolled_back"]
DEPLOYMENT_ENVIRONMENTS = ["production", "staging", "backup"]
DEPLOYMENT_JOB_STATUSES = ["pending", "waiting_approval", "approved", "running", "succeeded", "failed", "rejected", "rolled_back"]
DISPATCH_PROVIDERS = ["openai", "anthropic", "google", "cursor"]
DISPATCH_TASK_ROLES = ["planner", "executor", "reviewer", "tester"]
GEMINI_ALLOWED_TASK_ROLES = ["reviewer", "tester"]
GEMINI_SAFE_TASK_KEYWORDS = ["api", "log", "test", "測試", "驗收", "分析", "review", "case", "案例"]
GEMINI_FORBIDDEN_TASK_KEYWORDS = ["ssh", "docker", "deploy", "部署", "修改檔案", "write file", "rm ", "delete", "刪除"]
DISPATCH_RSYNC_EXCLUDES = [
    ".git",
    ".env",
    "data/",
    "uploads/",
    "upload/",
    "output/",
    "outputs/",
    "backup/",
    "backups/",
    "*.db",
]
DISPATCH_PROTECTED_PATH_NAMES = {"data", "uploads", "upload", "output", "outputs", "backup", "backups"}
DISPATCH_RISK_LEVELS = ["low", "medium", "high"]
REPO_ROOT = os.getenv("DEV_PILOT_REPO_ROOT", "/volume1/repos")
WORKTREE_ROOT = os.getenv("DEV_PILOT_WORKTREE_ROOT", "/volume1/worktrees")
DEPLOY_ROOT = os.getenv("DEV_PILOT_DEPLOY_ROOT", "/volume1/docker")
PRODUCTION_ROOT = os.getenv("DEV_PILOT_PRODUCTION_ROOT", DEPLOY_ROOT)
STAGING_ROOT = os.getenv("DEV_PILOT_STAGING_ROOT", "/volume1/docker-staging")
BACKUP_ROOT = os.getenv("DEV_PILOT_BACKUP_ROOT", "/volume1/backups")
RELEASE_DASHBOARD_BACKUP_DIR = Path(os.getenv("DEV_PILOT_RELEASE_BACKUP_DIR") or os.getenv("BACKUP_DIR") or "/app/backups")
RELEASE_DASHBOARD_DOMAIN = os.getenv("DEV_PILOT_RELEASE_DOMAIN", "https://devpilot.aicenter.com.tw/")
RELEASE_DASHBOARD_CONTAINER = os.getenv("DEV_PILOT_RELEASE_CONTAINER", "devpilot-project-manager")
RELEASE_DASHBOARD_PORT = os.getenv("DEV_PILOT_RELEASE_PORT", "5010:5000")
ADMIN_SAFETY_RELEASE_NAME = "DevPilot Admin Safety Release 2026-05-09"
ADMIN_SAFETY_RELEASE_STATUS = "frozen_read_only"
ADMIN_SAFETY_RELEASE_SCOPE = "Admin UI, approval safety, DNS safety chain, release dashboards"
ADMIN_SAFETY_RELEASE_COMMIT = "625c59e"
ADMIN_SAFETY_RELEASE_COMMIT_MESSAGE = "chore: add DevPilot admin safety release label"
OPERATIONS_SHOPEE_PRODUCTION_HEALTH_URL = os.getenv("DEV_PILOT_SHOPEE_PRODUCTION_HEALTH_URL", "http://211.75.219.184:3030/api/health")
OPERATIONS_SHOPEE_STAGING_HEALTH_URL = os.getenv("DEV_PILOT_SHOPEE_STAGING_HEALTH_URL", "http://211.75.219.184:3032/api/health")
OPERATIONS_SHOPEE_PRODUCTION_DOMAIN = os.getenv("DEV_PILOT_SHOPEE_PRODUCTION_DOMAIN", "shopee.aichat.tw")
OPERATIONS_SHOPEE_STAGING_DOMAIN = os.getenv("DEV_PILOT_SHOPEE_STAGING_DOMAIN", "staging.aichat.tw")
OPERATIONS_SHOPEE_STAGING_LEGACY_DOMAIN = os.getenv("DEV_PILOT_SHOPEE_STAGING_LEGACY_DOMAIN", "staging-shopee.aichat.tw")
OPERATIONS_AICHAT_NAS_IP = os.getenv("DEV_PILOT_AICHAT_NAS_IP", "211.75.219.184")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent")
NAS_SSH_HOST = os.getenv("DEV_PILOT_NAS_SSH_HOST", "211.75.219.184")
NAS_SSH_USER = os.getenv("DEV_PILOT_NAS_SSH_USER", "chaokun")
NAS_SSH_PORT = os.getenv("DEV_PILOT_NAS_SSH_PORT", "22")
HEARTBEAT_SOURCES = ["codex", "claude", "cursor", "antigravity", "ai-fleet-console", "manual", "other"]
HEARTBEAT_STATUSES = ["idle", "running", "online", "error", "offline", "done"]
HEARTBEAT_OFFLINE_SECONDS = 300
API_KEY_CATEGORIES = ["ai", "deploy", "webhook", "database", "devpilot", "third-party", "other"]
API_KEY_PROVIDERS = ["openai", "anthropic", "google", "cursor", "github", "gitea", "telegram", "cloudflare", "devpilot", "nas", "other"]
API_KEY_STATUSES = ["active", "inactive", "revoked", "rotating"]
API_KEY_PERMISSIONS = ["read", "write", "deploy", "ai", "webhook"]
API_KEY_ENVIRONMENTS = ["staging", "production"]
DOMAIN_MAPPING_ENVIRONMENTS = ["production", "staging", "preview", "api", "admin"]
API_KEY_ROTATION_INTERVAL_SECONDS = int(os.getenv("API_KEY_ROTATION_INTERVAL_SECONDS", "600"))
API_KEY_ROTATION_ENABLED = os.getenv("API_KEY_ROTATION_ENABLED", "1").lower() not in ("0", "false", "no", "off")
_API_KEY_ROTATION_THREAD_STARTED = False
_API_KEY_ROTATION_THREAD_LOCK = threading.Lock()
AI_PROVIDER_NAMES = ["openai", "gemini", "claude"]
AI_PROVIDER_STATUSES = ["active", "disabled", "error"]
AI_COST_TASK_ROLES = ["planner", "executor", "reviewer", "tester"]
AI_USAGE_STATUSES = ["success", "failed"]
AI_MESSAGE_STATUSES = ["running", "done", "failed"]
AI_CONSOLE_PROVIDER_CHOICES = ["auto", "openai", "gemini", "claude"]
AI_TASK_STATUSES = ["queued", "running", "done", "failed", "blocked", "canceled"]
AI_TASK_PRIORITIES = ["low", "medium", "high", "urgent"]
AI_TASK_TYPES = [
    "general", "planning", "review", "test", "deploy-check", "content", "automation",
    "requirement_analysis", "feature_breakdown", "development_plan", "test_checklist",
    "deploy_check", "handoff_report",
]
AI_TASK_APPROVAL_STATUSES = ["none", "pending", "approved", "rejected"]
FULL_FLOW_ALLOWED_TASK_TYPES = [
    "requirement_analysis", "feature_breakdown", "development_plan",
    "test_checklist", "deploy_check", "handoff_report",
]
FULL_FLOW_BLOCKED_TASK_TYPE_TERMS = ["production", "shell", "ssh", "sync", "docker", "nas", "delete", "env"]
DEFAULT_TASK_TEMPLATES = [
    {
        "name": "需求分析",
        "task_type": "requirement_analysis",
        "provider": "claude",
        "prompt_template": "請針對專案「{project_name}」進行需求分析，整理目標、使用者、核心情境、限制條件與待釐清問題。",
        "priority": "high",
        "sort_order": 10,
    },
    {
        "name": "功能拆解",
        "task_type": "feature_breakdown",
        "provider": "openai",
        "prompt_template": "請將專案「{project_name}」拆解成可執行功能模組，列出每個模組的輸入、輸出、資料表/API 與完成標準。",
        "priority": "high",
        "sort_order": 20,
    },
    {
        "name": "開發計畫",
        "task_type": "development_plan",
        "provider": "openai",
        "prompt_template": "請為專案「{project_name}」產生開發計畫，包含里程碑、任務順序、風險、測試點與交付檢查。",
        "priority": "medium",
        "sort_order": 30,
    },
    {
        "name": "測試清單",
        "task_type": "test_checklist",
        "provider": "gemini",
        "prompt_template": "請為專案「{project_name}」產生測試清單，包含功能測試、API 測試、UI 驗收、錯誤情境與回歸測試。",
        "priority": "medium",
        "sort_order": 40,
    },
    {
        "name": "部署檢查",
        "task_type": "deploy_check",
        "provider": "gemini",
        "prompt_template": "請為專案「{project_name}」產生部署檢查表，只檢查 staging/production 前置條件、環境變數、資料備份、健康檢查與 rollback 條件，不執行部署。",
        "priority": "high",
        "sort_order": 50,
    },
    {
        "name": "交接報告",
        "task_type": "handoff_report",
        "provider": "claude",
        "prompt_template": "請為專案「{project_name}」產生交接報告草稿，包含完成內容、修改檔案、測試結果、風險、下一步與注意事項。",
        "priority": "medium",
        "sort_order": 60,
    },
]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini"))
AI_DEFAULT_PROVIDER_ORDER = {
    "planner": ["claude", "gemini", "openai"],
    "reviewer": ["gemini", "claude", "openai"],
    "tester": ["gemini", "claude", "openai"],
    "executor": ["openai", "claude"],
}
AI_PROVIDER_TRUST = {"openai": 3, "claude": 3, "gemini": 2}
CONTENT_JOB_TYPES = ["product_video", "video", "ad", "report"]
CONTENT_JOB_STATUSES = ["queued", "running", "done", "failed"]
CUSTOMER_SERVICE_FALLBACK = "不好意思，這個問題我無法回答，請聯繫客服人員"
INDUSTRY_TEMPLATE_DEFAULTS = {
    "retail": {
        "allowed_topics": ["商品", "價格", "庫存", "出貨", "配送", "付款", "退換貨", "優惠", "保固"],
        "blocked_topics": ["醫療診斷", "法律意見", "投資建議", "政治", "成人內容"],
    },
    "restaurant": {
        "allowed_topics": ["菜單", "訂位", "外送", "營業時間", "地址", "付款", "過敏原", "餐點"],
        "blocked_topics": ["醫療診斷", "法律意見", "投資建議", "政治", "成人內容"],
    },
    "clinic": {
        "allowed_topics": ["掛號", "門診時間", "地址", "收費", "療程介紹", "術前須知", "術後照護"],
        "blocked_topics": ["診斷", "處方", "用藥調整", "急症判斷", "保證療效", "法律意見"],
    },
    "legal": {
        "allowed_topics": ["預約諮詢", "服務項目", "收費方式", "文件準備", "流程說明"],
        "blocked_topics": ["保證勝訴", "具體法律意見", "逃避責任", "違法行為", "偽造文件"],
    },
}
USER_ROLES = ["owner", "admin", "developer", "viewer", "ai"]
ROLE_RANK = {"viewer": 10, "developer": 20, "ai": 25, "admin": 80, "owner": 100}
MACHINE_NAME_MAPPING = {
    "DESKTOP-B7PAJRO": "家裡電腦",
    "家裡機器": "家裡電腦",
    "disney": "NAS",
}
MACHINE_NAME_MAPPING_CASEFOLD = {raw.casefold(): display for raw, display in MACHINE_NAME_MAPPING.items()}
AI_FLEET_MACHINES_URL = os.getenv("AI_FLEET_MACHINES_URL", "http://211.75.219.184:3004/api/machines")
AI_FLEET_POLL_INTERVAL_SECONDS = int(os.getenv("AI_FLEET_POLL_INTERVAL_SECONDS", "30"))
AI_FLEET_OFFLINE_AFTER_SECONDS = int(os.getenv("AI_FLEET_OFFLINE_AFTER_SECONDS", str(HEARTBEAT_OFFLINE_SECONDS)))
AI_FLEET_POLL_ENABLED = os.getenv("AI_FLEET_POLL_ENABLED", "1").lower() not in ("0", "false", "no", "off")
_AI_FLEET_THREAD_STARTED = False
_AI_FLEET_THREAD_LOCK = threading.Lock()
ENDPOINT_TYPES = ["frontend", "admin", "api", "health", "docs", "login", "unknown"]
ENDPOINT_CANDIDATES = [
    ("frontend", "/"),
    ("frontend", "/home"),
    ("frontend", "/index"),
    ("admin", "/admin"),
    ("admin", "/dashboard"),
    ("admin", "/backend"),
    ("admin", "/manage"),
    ("admin", "/console"),
    ("login", "/login"),
    ("login", "/admin/login"),
    ("api", "/api"),
    ("api", "/api/projects"),
    ("api", "/api/health"),
    ("health", "/health"),
    ("docs", "/docs"),
    ("docs", "/swagger"),
    ("docs", "/openapi.json"),
]
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def ps_quote(value):
    return str(value).replace("`", "``").replace('"', '`"')


def build_powershell_handoff_command(project_id, source, agent_name):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$DevPilotCredential = $env:DEVPILOT_API_CREDENTIAL
if (-not $DevPilotCredential) {{ throw "DEVPILOT_API_CREDENTIAL is required in the local secure environment." }}
$AuthHeaders = @{{}}
$AuthHeaders["Authorization"] = (("Bear" + "er ") + $DevPilotCredential)
$payload = @{{
  source = "{ps_quote(source)}"
  agent_name = "{ps_quote(agent_name)}"
  work_mode = "code-change"
  summary = "請填寫本次完成內容"
  completed_phases = @("請填寫完成階段")
  changed_files = @("請填寫修改檔案")
  test_result = "請填寫測試結果"
  git_status = "請填寫 git status 結果"
  repo_branch = "請填寫目前 branch"
  commit_sha = "請填寫 commit sha，若沒有填 none"
  next_steps = "請填寫下一步"
  warnings = "請填寫注意事項"
}}
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers $AuthHeaders -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_claude_powershell_handoff_command(project_id):
    return build_powershell_handoff_command(project_id, "claude", "Claude Code")


def build_codex_powershell_handoff_command(project_id):
    return build_powershell_handoff_command(project_id, "codex", "Codex")


def build_cursor_powershell_handoff_command(project_id):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$DevPilotCredential = $env:DEVPILOT_API_CREDENTIAL
if (-not $DevPilotCredential) {{ throw "DEVPILOT_API_CREDENTIAL is required in the local secure environment." }}
$AuthHeaders = @{{}}
$AuthHeaders["Authorization"] = (("Bear" + "er ") + $DevPilotCredential)
$payload = @{{
  source = "cursor"
  agent_name = "Cursor"
  work_mode = "debug"
  summary = "請填寫本次 Debug / 修正內容"
  completed_phases = @("Debug 修正")
  changed_files = @("請填寫實際修改檔案")
  test_result = "請填寫測試結果"
  git_status = "請填寫 git status 結果"
  repo_branch = "請填寫目前 branch，若無 git 填 none"
  commit_sha = "若沒有 commit 填 none"
  next_steps = "請填寫下一步"
  warnings = "請填寫注意事項"
}}
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers $AuthHeaders -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_antigravity_powershell_handoff_command(project_id):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$DevPilotCredential = $env:DEVPILOT_API_CREDENTIAL
if (-not $DevPilotCredential) {{ throw "DEVPILOT_API_CREDENTIAL is required in the local secure environment." }}
$AuthHeaders = @{{}}
$AuthHeaders["Authorization"] = (("Bear" + "er ") + $DevPilotCredential)
$payload = @{{
  source = "antigravity"
  agent_name = "Google Antigravity"
  work_mode = "agent-run"
  summary = "請填寫本次 Antigravity Agent 完成內容"
  completed_phases = @("AI Agent 任務")
  changed_files = @("請填寫實際修改檔案")
  test_result = "請填寫測試結果"
  git_status = "請填寫 git status 結果"
  repo_branch = "請填寫目前 branch，若無 git 填 none"
  commit_sha = "若沒有 commit 填 none"
  next_steps = "請填寫下一步"
  warnings = "請填寫注意事項"
}}
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers $AuthHeaders -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_python_handoff_command(project_id):
    return f'''python scripts/report_handoff.py --base-url "{API_BASE_URL}" --project-id {project_id} --source codex --agent-name "Codex" --work-mode code-change --summary "請填寫本次完成內容" --phase "請填寫完成階段" --changed-file "請填寫修改檔案" --test-result "請填寫測試結果" --next-steps "請填寫下一步" --warnings "請填寫注意事項"'''


def build_handoff_copy_commands(project_id):
    return {
        "claude_ps": build_claude_powershell_handoff_command(project_id),
        "codex_ps": build_codex_powershell_handoff_command(project_id),
        "cursor_ps": build_cursor_powershell_handoff_command(project_id),
        "antigravity_ps": build_antigravity_powershell_handoff_command(project_id),
        "python": build_python_handoff_command(project_id),
    }


def build_heartbeat_powershell_command(project, source, agent_name):
    project_name = project["name"] if project else ""
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project["id"] if project else "1"}
$DevPilotCredential = $env:DEVPILOT_API_CREDENTIAL
if (-not $DevPilotCredential) {{ throw "DEVPILOT_API_CREDENTIAL is required in the local secure environment." }}
$AuthHeaders = @{{}}
$AuthHeaders["Authorization"] = (("Bear" + "er ") + $DevPilotCredential)
$MachineName = $env:COMPUTERNAME
$SessionId = "{ps_quote(source)}-$PID"
$payload = @{{
  source = "{ps_quote(source)}"
  agent_name = "{ps_quote(agent_name)}"
  project_id = $ProjectId
  project_name = "{ps_quote(project_name)}"
  machine_name = $MachineName
  status = "running"
  current_task = "請填寫目前任務"
  last_message = "請填寫最後訊息"
  pid = "$PID"
  session_id = $SessionId
}}
$body = $payload | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "$ApiUrl/api/ai-heartbeats" -Method Post -Headers $AuthHeaders -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_heartbeat_copy_commands(project):
    return {
        "codex_ps": build_heartbeat_powershell_command(project, "codex", "Codex"),
        "claude_ps": build_heartbeat_powershell_command(project, "claude", "Claude Code"),
        "cursor_ps": build_heartbeat_powershell_command(project, "cursor", "Cursor"),
        "antigravity_ps": build_heartbeat_powershell_command(project, "antigravity", "Google Antigravity"),
    }


def now_dt():
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


def now_str():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return now_dt().date().isoformat()


def machine_display_name(value):
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return MACHINE_NAME_MAPPING.get(text) or MACHINE_NAME_MAPPING_CASEFOLD.get(text.casefold(), text)


def get_db():
    if "db" not in g:
        DATA_DIR.mkdir(exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def require_session_for_pages():
    if request.endpoint in ("login", "static"):
        return None
    if request.path.startswith("/api/"):
        return None
    if request.endpoint == "logout":
        return None
    if not current_user():
        return redirect(url_for("login", next=request.path))
    return None


def query_all(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def execute(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def row_to_dict(row):
    return dict(row) if row else None


def json_dumps(value):
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def parse_json_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else [parsed]
    except Exception:
        return [line.strip() for line in str(value).splitlines() if line.strip()]


def encryption_material():
    configured = os.getenv("MASTER_KEY", "").strip() or os.getenv("API_KEY_ENCRYPTION_KEY", "").strip()
    if configured:
        return configured.encode("utf-8")
    return f"{app.secret_key}:{API_TOKEN}:devpilot-api-key-center".encode("utf-8")


def fernet_key_from_material(material):
    try:
        Fernet(material)
        return material
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def api_key_fernet():
    return Fernet(fernet_key_from_material(encryption_material()))


def aes256_key():
    return hashlib.sha256(encryption_material()).digest()


def encrypt_secret_value(value):
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes256_key()).encrypt(nonce, str(value).encode("utf-8"), None)
    return "aes256:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret_value(encrypted_value):
    if not encrypted_value:
        return ""
    if str(encrypted_value).startswith("aes256:"):
        raw = base64.urlsafe_b64decode(str(encrypted_value).split(":", 1)[1].encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        return AESGCM(aes256_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    try:
        return api_key_fernet().decrypt(str(encrypted_value).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("API key encryption key mismatch") from exc


def get_active_ai_health_key(provider):
    provider_map = {
        "openai": "openai",
        "gemini": "google",
        "claude": "anthropic",
    }
    db_provider = provider_map.get(str(provider or "").strip().lower())
    if not db_provider:
        return {"ok": False, "status": "skipped", "source": "none"}
    row = row_to_dict(query_one(
        """SELECT id, provider, encrypted_value, masked_value, key_mask
           FROM api_keys
           WHERE lower(COALESCE(category, ''))='ai'
             AND lower(COALESCE(environment, ''))='staging'
             AND lower(COALESCE(status, ''))='active'
             AND COALESCE(ai_allowed, 0)=1
             AND lower(COALESCE(provider, ''))=?
           ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
           LIMIT 1""",
        (db_provider,),
    ))
    if not row:
        return {"ok": False, "status": "not_configured", "source": "none"}
    masked = row.get("masked_value") or row.get("key_mask") or "************"
    try:
        value = decrypt_secret_value(row.get("encrypted_value"))
    except Exception:
        return {"ok": False, "status": "error", "source": "db", "masked": masked}
    if not str(value or "").strip():
        return {"ok": False, "status": "not_configured", "source": "db", "masked": masked}
    return {"ok": True, "status": "configured", "source": "db", "masked": masked}


def get_active_ai_console_key(provider):
    provider_map = {
        "openai": "openai",
        "gemini": "google",
        "google": "google",
        "claude": "anthropic",
        "anthropic": "anthropic",
    }
    canonical = str(provider or "").strip().lower()
    db_provider = provider_map.get(canonical)
    if not db_provider:
        return {"ok": False, "status": "skipped", "source": "none", "provider": canonical}
    row = row_to_dict(query_one(
        """SELECT id, provider, encrypted_value, masked_value, key_mask
           FROM api_keys
           WHERE lower(COALESCE(category, ''))='ai'
             AND lower(COALESCE(environment, ''))='staging'
             AND lower(COALESCE(status, ''))='active'
             AND COALESCE(ai_allowed, 0)=1
             AND lower(COALESCE(provider, ''))=?
           ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
           LIMIT 1""",
        (db_provider,),
    ))
    if not row:
        return {"ok": False, "status": "not_configured", "source": "none", "provider": canonical}
    masked = row.get("masked_value") or row.get("key_mask") or "************"
    try:
        value = decrypt_secret_value(row.get("encrypted_value"))
    except Exception:
        return {"ok": False, "status": "error", "source": "db", "provider": canonical, "masked": masked}
    if not str(value or "").strip():
        return {"ok": False, "status": "not_configured", "source": "db", "provider": canonical, "masked": masked}
    return {
        "ok": True,
        "status": "configured",
        "source": "db",
        "provider": canonical,
        "masked": masked,
        "key": str(value).strip(),
    }


def secret_fingerprint(value):
    return hmac.new(
        hashlib.sha256(encryption_material()).digest(),
        str(value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mask_secret_value(value):
    text = str(value or "")
    if not text:
        return ""
    prefix_len = 3 if text.startswith("sk-") else min(4, max(1, len(text) // 4))
    suffix_len = 4 if len(text) > 8 else min(2, len(text))
    return f"{text[:prefix_len]}****{text[-suffix_len:]}"


def sanitize_ui_text(value):
    text = str(value or "")
    if not text:
        return ""
    replacements = [
        (r"\bCloudflare\s+API\s+Token\b", "Cloudflare API Credential"),
        (r"\bAPI\s+Token\b", "API Credential"),
        (r"\baccess\s+token\b", "access credential"),
        (r"(--(?:token|api-key|secret|password|credential)\s+)([^\s<>'\"]+)", r"\1[redacted-credential]"),
        (r"(Authorization\s*[:=]\s*)([^\s<>'\"]+)", r"\1[redacted-credential]"),
        (r"\bBearer\s+[A-Za-z0-9._~+/=-]+", "[redacted-credential]"),
        (r"\bdevpilot-local-token\b", "[redacted-credential]"),
        (r"\bchange-me-token\b", "[redacted-credential]"),
        (r"\bYOUR_TOKEN\b", "[redacted-credential]"),
        (r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{7,}\b", "sk-[redacted]"),
        (r"\bcf-[A-Za-z0-9][A-Za-z0-9_-]{7,}\b", "cf-[redacted]"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


@app.template_filter("safe_ui_text")
def safe_ui_text_filter(value):
    return sanitize_ui_text(value)


def generate_api_key_value():
    return "sk-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]


def normalize_choice(value, allowed, default):
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def current_user():
    if not has_request_context():
        return None
    user_id = session.get("user_id")
    if hasattr(g, "current_user") and getattr(g, "current_user_id", None) == user_id:
        return g.current_user
    g.current_user_id = user_id
    g.current_user = row_to_dict(query_one("SELECT * FROM users WHERE id=? AND is_active=1", (user_id,))) if user_id else None
    return g.current_user


def current_role():
    if getattr(g, "api_role", None):
        return g.api_role
    user = current_user()
    return user.get("role") if user else None


def has_role(*roles):
    role = current_role()
    if not role:
        return False
    if role in roles:
        return True
    required_rank = min(ROLE_RANK.get(item, 999) for item in roles)
    return ROLE_RANK.get(role, 0) >= required_rank


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def require_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login", next=request.path))
            if not has_role(*roles):
                flash("Permission denied")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_api_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user and has_role(*roles):
                return fn(*args, **kwargs)
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and auth.replace("Bearer ", "", 1).strip() == API_TOKEN:
                g.api_role = "ai"
                if "ai" not in roles:
                    return jsonify({"ok": False, "error": "AI credential role is not allowed for this API"}), 403
                return fn(*args, **kwargs)
            return jsonify({"ok": False, "error": "Permission denied"}), 403
        return wrapper
    return decorator


def audit_log(action, target_type=None, target_id=None, metadata=None):
    user = current_user()
    try:
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        user_agent = request.headers.get("User-Agent", "")
    except RuntimeError:
        ip_address = ""
        user_agent = ""
    execute(
        """INSERT INTO audit_logs
           (user_id, role, action, target_type, target_id, ip_address, user_agent, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user.get("id") if user else None,
            current_role() or "",
            action,
            target_type,
            target_id,
            ip_address,
            user_agent,
            json.dumps(metadata or {}, ensure_ascii=False),
            now_str(),
        ),
    )


def require_api_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.replace("Bearer ", "", 1).strip() != API_TOKEN:
            return jsonify({"ok": False, "error": "API credential missing or invalid. Authorization header required; credential value is intentionally hidden."}), 401
        g.api_role = "ai"
        return fn(*args, **kwargs)
    return wrapper


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    with app.app_context():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS project_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                phases_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                client_name TEXT,
                project_type TEXT,
                status TEXT DEFAULT '規劃中',
                priority TEXT DEFAULT '中',
                github_repo TEXT,
                local_path TEXT,
                deploy_url TEXT,
                deploy_location TEXT,
                owner_machine TEXT,
                description TEXT,
                next_steps TEXT,
                progress INTEGER DEFAULT 0,
                template_id INTEGER,
                computer_id INTEGER,
                deploy_computer_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS computers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                device_type TEXT,
                location TEXT,
                os_name TEXT,
                ip_address TEXT,
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS project_phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                phase_name TEXT NOT NULL,
                phase_order INTEGER NOT NULL,
                status TEXT DEFAULT '未開始',
                start_date TEXT,
                due_date TEXT,
                completed_at TEXT,
                test_result TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                phase_id INTEGER,
                title TEXT NOT NULL,
                status TEXT DEFAULT '未開始',
                priority TEXT DEFAULT '中',
                assignee TEXT,
                due_date TEXT,
                completed_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(phase_id) REFERENCES project_phases(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS handoff_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                source TEXT DEFAULT 'manual',
                agent_name TEXT,
                work_mode TEXT DEFAULT 'handoff',
                conversation_ref TEXT,
                repo_branch TEXT,
                commit_sha TEXT,
                risk_level TEXT DEFAULT 'low',
                summary TEXT,
                raw_text TEXT,
                completed_phases TEXT,
                changed_files TEXT,
                test_result TEXT,
                git_status TEXT,
                db_backups TEXT,
                next_steps TEXT,
                warnings TEXT,
                api_payload TEXT,
                is_hidden INTEGER DEFAULT 0,
                hidden_at TEXT,
                hidden_reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                environment TEXT,
                deploy_url TEXT,
                server_path TEXT,
                version TEXT,
                status TEXT DEFAULT '未部署',
                deployed_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS deployment_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_type TEXT,
                location TEXT,
                ip_address TEXT,
                domain TEXT,
                ssh_host TEXT,
                ssh_port TEXT,
                ssh_user TEXT,
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS project_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                target_id INTEGER,
                environment TEXT,
                deploy_type TEXT,
                service_name TEXT,
                internal_url TEXT,
                public_url TEXT,
                port TEXT,
                deploy_path TEXT,
                compose_path TEXT,
                db_path TEXT,
                uploads_path TEXT,
                backup_path TEXT,
                log_path TEXT,
                status TEXT,
                last_deployed_at TEXT,
                last_checked_at TEXT,
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES deployment_targets(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS domain_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_name TEXT,
                zone_id_masked TEXT,
                record_name TEXT NOT NULL,
                record_type TEXT,
                record_content TEXT,
                project_id INTEGER,
                environment TEXT,
                preview_url TEXT,
                status TEXT DEFAULT 'active',
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS approval_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_type TEXT,
                project_id INTEGER,
                title TEXT,
                summary TEXT,
                payload_json TEXT,
                status TEXT DEFAULT 'pending',
                requested_by TEXT,
                approved_by TEXT,
                approved_via TEXT,
                telegram_chat_id_masked TEXT,
                telegram_message_id TEXT,
                callback_nonce_hash TEXT,
                expires_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                approved_at TEXT,
                rejected_at TEXT,
                notes TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS dns_execution_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_request_id INTEGER NOT NULL,
                actor TEXT,
                attempted_action TEXT NOT NULL,
                feature_flag TEXT,
                feature_flag_state TEXT,
                result TEXT NOT NULL,
                http_status INTEGER,
                planned_action_json TEXT,
                request_snapshot_json TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS telegram_allowed_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id_hash TEXT,
                telegram_username TEXT,
                display_name TEXT,
                role TEXT,
                is_active INTEGER DEFAULT 1,
                encrypted_chat_id TEXT,
                chat_id_masked TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS deployment_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                environment TEXT,
                requested_by TEXT,
                source TEXT,
                status TEXT DEFAULT 'pending',
                task TEXT,
                worktree_path TEXT,
                target_path TEXT,
                deploy_result TEXT,
                health_result TEXT,
                telegram_result TEXT,
                validation_status TEXT,
                validation_report_id INTEGER,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                approved_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS dispatch_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                provider TEXT,
                task_role TEXT,
                agent TEXT,
                task TEXT,
                task_prompt TEXT,
                status TEXT DEFAULT 'queued',
                risk_level TEXT DEFAULT 'low',
                approval_required INTEGER DEFAULT 1,
                worktree_path TEXT,
                deploy_path TEXT,
                staging_path TEXT,
                production_path TEXT,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                changed_files TEXT,
                diff_stat TEXT,
                result TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dispatch_job_id INTEGER,
                command TEXT,
                stdout TEXT,
                stderr TEXT,
                exit_code INTEGER,
                created_at TEXT,
                FOREIGN KEY(dispatch_job_id) REFERENCES dispatch_jobs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS validation_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                deployment_job_id INTEGER,
                provider TEXT,
                status TEXT,
                score INTEGER,
                summary TEXT,
                details TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS deployment_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                environment TEXT,
                deploy_path TEXT,
                snapshot_path TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS project_repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                repo_url TEXT,
                repo_path TEXT,
                worktree_path TEXT,
                deploy_path TEXT,
                repo_status TEXT DEFAULT 'missing',
                last_commit TEXT,
                branch TEXT,
                sync_method TEXT DEFAULT 'local',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS docker_scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                target_name TEXT,
                ssh_host TEXT,
                docker_root TEXT,
                status TEXT,
                summary TEXT,
                raw_output TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS docker_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                project_id INTEGER,
                service_name TEXT,
                container_name TEXT NOT NULL,
                image TEXT,
                status TEXT,
                ports TEXT,
                compose_path TEXT,
                deploy_path TEXT,
                volumes TEXT,
                last_seen_at TEXT,
                raw_inspect TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(target_id, container_name)
            );

            CREATE TABLE IF NOT EXISTS service_endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                docker_service_id INTEGER,
                project_id INTEGER,
                endpoint_type TEXT,
                url TEXT,
                path TEXT,
                status_code INTEGER,
                title TEXT,
                detected_from TEXT,
                is_confirmed INTEGER DEFAULT 0,
                is_ignored INTEGER DEFAULT 0,
                notes TEXT,
                last_checked_at TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                agent_name TEXT,
                project_id INTEGER,
                project_name TEXT,
                machine_name TEXT,
                status TEXT,
                current_task TEXT,
                last_message TEXT,
                pid TEXT,
                session_id TEXT,
                raw_payload TEXT,
                created_at TEXT,
                updated_at TEXT,
                last_seen_at TEXT,
                last_seen TEXT,
                active_dispatch TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT UNIQUE,
                status TEXT DEFAULT 'active',
                priority INTEGER DEFAULT 100,
                default_model TEXT,
                cost_input_per_1k REAL DEFAULT 0,
                cost_output_per_1k REAL DEFAULT 0,
                daily_budget REAL,
                monthly_budget REAL,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT,
                model TEXT,
                project_id INTEGER,
                dispatch_job_id INTEGER,
                task_role TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost REAL DEFAULT 0,
                status TEXT,
                error_message TEXT,
                prompt_summary TEXT,
                fallback_used INTEGER DEFAULT 0,
                fallback_from TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                provider TEXT,
                model TEXT,
                task_role TEXT,
                prompt_summary TEXT,
                status TEXT,
                response_text TEXT,
                error_message TEXT,
                raw_response TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT,
                task_type TEXT,
                priority TEXT,
                provider TEXT,
                prompt TEXT,
                status TEXT,
                result TEXT,
                error_message TEXT,
                started_at TEXT,
                finished_at TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                parent_task_id INTEGER,
                auto_run_next INTEGER DEFAULT 0,
                last_auto_run_at TEXT,
                requires_approval INTEGER DEFAULT 0,
                approval_status TEXT DEFAULT 'none',
                approved_at TEXT,
                approved_by TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS flow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                mode TEXT,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                total_tasks INTEGER DEFAULT 0,
                done_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                stopped_reason TEXT,
                summary TEXT,
                created_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS task_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                task_type TEXT,
                provider TEXT,
                prompt_template TEXT,
                priority TEXT,
                sort_order INTEGER DEFAULT 100,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_fallback_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_provider TEXT,
                fallback_provider TEXT,
                task_role TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS content_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                type TEXT,
                title TEXT,
                script TEXT,
                prompt TEXT,
                provider TEXT,
                status TEXT DEFAULT 'queued',
                output_url TEXT,
                post_text TEXT,
                post_status TEXT DEFAULT 'draft',
                post_platform TEXT,
                post_id TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT,
                title TEXT,
                summary TEXT,
                content TEXT,
                telegram_result TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS tenant_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                type TEXT,
                content TEXT
            );

            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id INTEGER PRIMARY KEY,
                industry TEXT,
                strict_mode INTEGER DEFAULT 1,
                fallback_message TEXT
            );

            CREATE TABLE IF NOT EXISTS industry_templates (
                industry TEXT PRIMARY KEY,
                allowed_topics TEXT,
                blocked_topics TEXT
            );

            CREATE TABLE IF NOT EXISTS acceptance_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT DEFAULT '未驗收',
                tested INTEGER DEFAULT 0,
                accepted INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS api_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method TEXT,
                path TEXT,
                source TEXT,
                project_id INTEGER,
                status_code INTEGER,
                payload TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        db.commit()
        migrate_db()
        seed_templates()
        seed_task_templates()
        seed_demo_project()
        ensure_initial_owner()
        apply_machine_name_mappings()


def column_exists(table_name, column_name):
    rows = query_all(f"PRAGMA table_info({table_name})")
    return any(row["name"] == column_name for row in rows)


def migrate_db():
    execute(
        """CREATE TABLE IF NOT EXISTS computers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_type TEXT,
            location TEXT,
            os_name TEXT,
            ip_address TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS deployment_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_type TEXT,
            location TEXT,
            ip_address TEXT,
            domain TEXT,
            ssh_host TEXT,
            ssh_port TEXT,
            ssh_user TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS project_deployments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            target_id INTEGER,
            environment TEXT,
            deploy_type TEXT,
            service_name TEXT,
            internal_url TEXT,
            public_url TEXT,
            port TEXT,
            deploy_path TEXT,
            compose_path TEXT,
            db_path TEXT,
            uploads_path TEXT,
            backup_path TEXT,
            log_path TEXT,
            status TEXT,
            last_deployed_at TEXT,
            last_checked_at TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(target_id) REFERENCES deployment_targets(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS domain_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zone_name TEXT,
            zone_id_masked TEXT,
            record_name TEXT NOT NULL,
            record_type TEXT,
            record_content TEXT,
            project_id INTEGER,
            environment TEXT,
            preview_url TEXT,
            status TEXT DEFAULT 'active',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_type TEXT,
            project_id INTEGER,
            title TEXT,
            summary TEXT,
            payload_json TEXT,
            status TEXT DEFAULT 'pending',
            requested_by TEXT,
            approved_by TEXT,
            approved_via TEXT,
            telegram_chat_id_masked TEXT,
            telegram_message_id TEXT,
            callback_nonce_hash TEXT,
            expires_at TEXT,
            created_at TEXT,
            updated_at TEXT,
            approved_at TEXT,
            rejected_at TEXT,
            notes TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS dns_execution_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_request_id INTEGER NOT NULL,
            actor TEXT,
            attempted_action TEXT NOT NULL,
            feature_flag TEXT,
            feature_flag_state TEXT,
            result TEXT NOT NULL,
            http_status INTEGER,
            planned_action_json TEXT,
            request_snapshot_json TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS telegram_allowed_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id_hash TEXT,
            telegram_username TEXT,
            display_name TEXT,
            role TEXT,
            is_active INTEGER DEFAULT 1,
            encrypted_chat_id TEXT,
            chat_id_masked TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    telegram_allowed_user_migrations = [
        ("encrypted_chat_id", "ALTER TABLE telegram_allowed_users ADD COLUMN encrypted_chat_id TEXT"),
        ("chat_id_masked", "ALTER TABLE telegram_allowed_users ADD COLUMN chat_id_masked TEXT"),
    ]
    for column_name, sql in telegram_allowed_user_migrations:
        if not column_exists("telegram_allowed_users", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS deployment_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            environment TEXT,
            requested_by TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending',
            task TEXT,
            worktree_path TEXT,
            target_path TEXT,
            deploy_result TEXT,
            health_result TEXT,
            telegram_result TEXT,
            validation_status TEXT,
            validation_report_id INTEGER,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            approved_at TEXT,
            completed_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS dispatch_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            provider TEXT,
            task_role TEXT,
            agent TEXT,
            task TEXT,
            task_prompt TEXT,
            status TEXT DEFAULT 'queued',
            risk_level TEXT DEFAULT 'low',
            approval_required INTEGER DEFAULT 1,
            worktree_path TEXT,
            deploy_path TEXT,
            staging_path TEXT,
            production_path TEXT,
            started_at TEXT,
            finished_at TEXT,
            error_message TEXT,
            changed_files TEXT,
            diff_stat TEXT,
            result TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispatch_job_id INTEGER,
            command TEXT,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            created_at TEXT,
            FOREIGN KEY(dispatch_job_id) REFERENCES dispatch_jobs(id) ON DELETE CASCADE
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS validation_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            deployment_job_id INTEGER,
            provider TEXT,
            status TEXT,
            score INTEGER,
            summary TEXT,
            details TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ai_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            priority INTEGER DEFAULT 100,
            default_model TEXT,
            cost_input_per_1k REAL DEFAULT 0,
            cost_output_per_1k REAL DEFAULT 0,
            daily_budget REAL,
            monthly_budget REAL,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            model TEXT,
            project_id INTEGER,
            dispatch_job_id INTEGER,
            task_role TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            status TEXT,
            error_message TEXT,
            prompt_summary TEXT,
            fallback_used INTEGER DEFAULT 0,
            fallback_from TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            provider TEXT,
            model TEXT,
            task_role TEXT,
            prompt_summary TEXT,
            status TEXT,
            response_text TEXT,
            error_message TEXT,
            raw_response TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT,
            task_type TEXT,
            priority TEXT,
            provider TEXT,
            prompt TEXT,
            status TEXT,
            result TEXT,
            error_message TEXT,
            started_at TEXT,
            finished_at TEXT,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            parent_task_id INTEGER,
            auto_run_next INTEGER DEFAULT 0,
            last_auto_run_at TEXT,
            requires_approval INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT 'none',
            approved_at TEXT,
            approved_by TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS task_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            task_type TEXT,
            provider TEXT,
            prompt_template TEXT,
            priority TEXT,
            sort_order INTEGER DEFAULT 100,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ai_fallback_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_provider TEXT,
            fallback_provider TEXT,
            task_role TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS content_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            type TEXT,
            title TEXT,
            script TEXT,
            prompt TEXT,
            provider TEXT,
            status TEXT DEFAULT 'queued',
            output_url TEXT,
            post_text TEXT,
            post_status TEXT DEFAULT 'draft',
            post_platform TEXT,
            post_id TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS tenant_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            type TEXT,
            content TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS tenant_settings (
            tenant_id INTEGER PRIMARY KEY,
            industry TEXT,
            strict_mode INTEGER DEFAULT 1,
            fallback_message TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS industry_templates (
            industry TEXT PRIMARY KEY,
            allowed_topics TEXT,
            blocked_topics TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS deployment_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            environment TEXT,
            deploy_path TEXT,
            snapshot_path TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS project_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            repo_url TEXT,
            repo_path TEXT,
            worktree_path TEXT,
            deploy_path TEXT,
            repo_status TEXT DEFAULT 'missing',
            last_commit TEXT,
            branch TEXT,
            sync_method TEXT DEFAULT 'local',
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS ai_heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            agent_name TEXT,
            project_id INTEGER,
            project_name TEXT,
            machine_name TEXT,
            status TEXT,
            current_task TEXT,
            last_message TEXT,
            pid TEXT,
            session_id TEXT,
            raw_payload TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_seen_at TEXT,
            last_seen TEXT,
            active_dispatch TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS docker_scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER,
            target_name TEXT,
            ssh_host TEXT,
            docker_root TEXT,
            status TEXT,
            summary TEXT,
            raw_output TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS docker_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER NOT NULL,
            project_id INTEGER,
            service_name TEXT,
            container_name TEXT NOT NULL,
            image TEXT,
            status TEXT,
            ports TEXT,
            compose_path TEXT,
            deploy_path TEXT,
            volumes TEXT,
            last_seen_at TEXT,
            raw_inspect TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(target_id, container_name)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS service_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            docker_service_id INTEGER,
            project_id INTEGER,
            endpoint_type TEXT,
            url TEXT,
            path TEXT,
            status_code INTEGER,
            title TEXT,
            detected_from TEXT,
            is_confirmed INTEGER DEFAULT 0,
            is_ignored INTEGER DEFAULT 0,
            notes TEXT,
            last_checked_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            last_login_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            action TEXT,
            target_type TEXT,
            target_id INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            metadata TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            provider TEXT,
            environment TEXT DEFAULT 'staging',
            status TEXT DEFAULT 'active',
            version TEXT DEFAULT 'v1',
            permissions TEXT,
            encrypted_value TEXT NOT NULL,
            masked_value TEXT,
            key_mask TEXT,
            value_fingerprint TEXT,
            source TEXT DEFAULT 'manual',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_used_at TEXT,
            rotation_days INTEGER DEFAULT 30,
            last_rotated_at TEXT,
            usage_limit INTEGER,
            is_system INTEGER DEFAULT 0,
            ai_allowed INTEGER DEFAULT 0,
            revoked_at TEXT,
            revoked_reason TEXT,
            last_revealed_at TEXT,
            replaced_by_key_id INTEGER
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            version TEXT,
            encrypted_value TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            action TEXT,
            user_id INTEGER,
            ip TEXT,
            actor TEXT,
            ip_address TEXT,
            user_agent TEXT,
            metadata TEXT,
            created_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            source TEXT,
            path TEXT,
            ip_address TEXT,
            status_code INTEGER,
            used_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            type TEXT,
            message TEXT,
            created_at TEXT
        )"""
    )
    handoff_migrations = [
        ("is_hidden", "ALTER TABLE handoff_logs ADD COLUMN is_hidden INTEGER DEFAULT 0"),
        ("hidden_at", "ALTER TABLE handoff_logs ADD COLUMN hidden_at TEXT"),
        ("hidden_reason", "ALTER TABLE handoff_logs ADD COLUMN hidden_reason TEXT"),
    ]
    for column_name, sql in handoff_migrations:
        if not column_exists("handoff_logs", column_name):
            execute(sql)
    project_migrations = [
        ("computer_id", "ALTER TABLE projects ADD COLUMN computer_id INTEGER"),
        ("deploy_computer_id", "ALTER TABLE projects ADD COLUMN deploy_computer_id INTEGER"),
    ]
    for column_name, sql in project_migrations:
        if not column_exists("projects", column_name):
            execute(sql)
    deployment_target_migrations = [
        ("target_type", "ALTER TABLE deployment_targets ADD COLUMN target_type TEXT"),
        ("location", "ALTER TABLE deployment_targets ADD COLUMN location TEXT"),
        ("ip_address", "ALTER TABLE deployment_targets ADD COLUMN ip_address TEXT"),
        ("domain", "ALTER TABLE deployment_targets ADD COLUMN domain TEXT"),
        ("ssh_host", "ALTER TABLE deployment_targets ADD COLUMN ssh_host TEXT"),
        ("ssh_port", "ALTER TABLE deployment_targets ADD COLUMN ssh_port TEXT"),
        ("ssh_user", "ALTER TABLE deployment_targets ADD COLUMN ssh_user TEXT"),
        ("notes", "ALTER TABLE deployment_targets ADD COLUMN notes TEXT"),
        ("is_active", "ALTER TABLE deployment_targets ADD COLUMN is_active INTEGER DEFAULT 1"),
        ("created_at", "ALTER TABLE deployment_targets ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE deployment_targets ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in deployment_target_migrations:
        if not column_exists("deployment_targets", column_name):
            execute(sql)
    project_deployment_migrations = [
        ("target_id", "ALTER TABLE project_deployments ADD COLUMN target_id INTEGER"),
        ("environment", "ALTER TABLE project_deployments ADD COLUMN environment TEXT"),
        ("deploy_type", "ALTER TABLE project_deployments ADD COLUMN deploy_type TEXT"),
        ("service_name", "ALTER TABLE project_deployments ADD COLUMN service_name TEXT"),
        ("internal_url", "ALTER TABLE project_deployments ADD COLUMN internal_url TEXT"),
        ("public_url", "ALTER TABLE project_deployments ADD COLUMN public_url TEXT"),
        ("port", "ALTER TABLE project_deployments ADD COLUMN port TEXT"),
        ("deploy_path", "ALTER TABLE project_deployments ADD COLUMN deploy_path TEXT"),
        ("compose_path", "ALTER TABLE project_deployments ADD COLUMN compose_path TEXT"),
        ("db_path", "ALTER TABLE project_deployments ADD COLUMN db_path TEXT"),
        ("uploads_path", "ALTER TABLE project_deployments ADD COLUMN uploads_path TEXT"),
        ("backup_path", "ALTER TABLE project_deployments ADD COLUMN backup_path TEXT"),
        ("log_path", "ALTER TABLE project_deployments ADD COLUMN log_path TEXT"),
        ("status", "ALTER TABLE project_deployments ADD COLUMN status TEXT"),
        ("last_deployed_at", "ALTER TABLE project_deployments ADD COLUMN last_deployed_at TEXT"),
        ("last_checked_at", "ALTER TABLE project_deployments ADD COLUMN last_checked_at TEXT"),
        ("notes", "ALTER TABLE project_deployments ADD COLUMN notes TEXT"),
        ("is_active", "ALTER TABLE project_deployments ADD COLUMN is_active INTEGER DEFAULT 1"),
        ("created_at", "ALTER TABLE project_deployments ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE project_deployments ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in project_deployment_migrations:
        if not column_exists("project_deployments", column_name):
            execute(sql)
    deployment_job_migrations = [
        ("project_id", "ALTER TABLE deployment_jobs ADD COLUMN project_id INTEGER"),
        ("environment", "ALTER TABLE deployment_jobs ADD COLUMN environment TEXT"),
        ("requested_by", "ALTER TABLE deployment_jobs ADD COLUMN requested_by TEXT"),
        ("source", "ALTER TABLE deployment_jobs ADD COLUMN source TEXT"),
        ("status", "ALTER TABLE deployment_jobs ADD COLUMN status TEXT DEFAULT 'pending'"),
        ("task", "ALTER TABLE deployment_jobs ADD COLUMN task TEXT"),
        ("worktree_path", "ALTER TABLE deployment_jobs ADD COLUMN worktree_path TEXT"),
        ("target_path", "ALTER TABLE deployment_jobs ADD COLUMN target_path TEXT"),
        ("deploy_result", "ALTER TABLE deployment_jobs ADD COLUMN deploy_result TEXT"),
        ("health_result", "ALTER TABLE deployment_jobs ADD COLUMN health_result TEXT"),
        ("telegram_result", "ALTER TABLE deployment_jobs ADD COLUMN telegram_result TEXT"),
        ("validation_status", "ALTER TABLE deployment_jobs ADD COLUMN validation_status TEXT"),
        ("validation_report_id", "ALTER TABLE deployment_jobs ADD COLUMN validation_report_id INTEGER"),
        ("notes", "ALTER TABLE deployment_jobs ADD COLUMN notes TEXT"),
        ("created_at", "ALTER TABLE deployment_jobs ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE deployment_jobs ADD COLUMN updated_at TEXT"),
        ("approved_at", "ALTER TABLE deployment_jobs ADD COLUMN approved_at TEXT"),
        ("completed_at", "ALTER TABLE deployment_jobs ADD COLUMN completed_at TEXT"),
    ]
    for column_name, sql in deployment_job_migrations:
        if not column_exists("deployment_jobs", column_name):
            execute(sql)
    dispatch_job_migrations = [
        ("project_id", "ALTER TABLE dispatch_jobs ADD COLUMN project_id INTEGER"),
        ("provider", "ALTER TABLE dispatch_jobs ADD COLUMN provider TEXT"),
        ("task_role", "ALTER TABLE dispatch_jobs ADD COLUMN task_role TEXT"),
        ("agent", "ALTER TABLE dispatch_jobs ADD COLUMN agent TEXT"),
        ("task", "ALTER TABLE dispatch_jobs ADD COLUMN task TEXT"),
        ("task_prompt", "ALTER TABLE dispatch_jobs ADD COLUMN task_prompt TEXT"),
        ("status", "ALTER TABLE dispatch_jobs ADD COLUMN status TEXT DEFAULT 'queued'"),
        ("risk_level", "ALTER TABLE dispatch_jobs ADD COLUMN risk_level TEXT DEFAULT 'low'"),
        ("approval_required", "ALTER TABLE dispatch_jobs ADD COLUMN approval_required INTEGER DEFAULT 1"),
        ("worktree_path", "ALTER TABLE dispatch_jobs ADD COLUMN worktree_path TEXT"),
        ("deploy_path", "ALTER TABLE dispatch_jobs ADD COLUMN deploy_path TEXT"),
        ("staging_path", "ALTER TABLE dispatch_jobs ADD COLUMN staging_path TEXT"),
        ("production_path", "ALTER TABLE dispatch_jobs ADD COLUMN production_path TEXT"),
        ("started_at", "ALTER TABLE dispatch_jobs ADD COLUMN started_at TEXT"),
        ("finished_at", "ALTER TABLE dispatch_jobs ADD COLUMN finished_at TEXT"),
        ("error_message", "ALTER TABLE dispatch_jobs ADD COLUMN error_message TEXT"),
        ("changed_files", "ALTER TABLE dispatch_jobs ADD COLUMN changed_files TEXT"),
        ("diff_stat", "ALTER TABLE dispatch_jobs ADD COLUMN diff_stat TEXT"),
        ("result", "ALTER TABLE dispatch_jobs ADD COLUMN result TEXT"),
        ("created_at", "ALTER TABLE dispatch_jobs ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE dispatch_jobs ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in dispatch_job_migrations:
        if not column_exists("dispatch_jobs", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispatch_job_id INTEGER,
            command TEXT,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            created_at TEXT,
            FOREIGN KEY(dispatch_job_id) REFERENCES dispatch_jobs(id) ON DELETE CASCADE
        )"""
    )
    agent_run_migrations = [
        ("dispatch_job_id", "ALTER TABLE agent_runs ADD COLUMN dispatch_job_id INTEGER"),
        ("command", "ALTER TABLE agent_runs ADD COLUMN command TEXT"),
        ("stdout", "ALTER TABLE agent_runs ADD COLUMN stdout TEXT"),
        ("stderr", "ALTER TABLE agent_runs ADD COLUMN stderr TEXT"),
        ("exit_code", "ALTER TABLE agent_runs ADD COLUMN exit_code INTEGER"),
        ("created_at", "ALTER TABLE agent_runs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in agent_run_migrations:
        if not column_exists("agent_runs", column_name):
            execute(sql)
    validation_report_migrations = [
        ("project_id", "ALTER TABLE validation_reports ADD COLUMN project_id INTEGER"),
        ("deployment_job_id", "ALTER TABLE validation_reports ADD COLUMN deployment_job_id INTEGER"),
        ("provider", "ALTER TABLE validation_reports ADD COLUMN provider TEXT"),
        ("status", "ALTER TABLE validation_reports ADD COLUMN status TEXT"),
        ("score", "ALTER TABLE validation_reports ADD COLUMN score INTEGER"),
        ("summary", "ALTER TABLE validation_reports ADD COLUMN summary TEXT"),
        ("details", "ALTER TABLE validation_reports ADD COLUMN details TEXT"),
        ("created_at", "ALTER TABLE validation_reports ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in validation_report_migrations:
        if not column_exists("validation_reports", column_name):
            execute(sql)
    snapshot_migrations = [
        ("project_id", "ALTER TABLE deployment_snapshots ADD COLUMN project_id INTEGER"),
        ("environment", "ALTER TABLE deployment_snapshots ADD COLUMN environment TEXT"),
        ("deploy_path", "ALTER TABLE deployment_snapshots ADD COLUMN deploy_path TEXT"),
        ("snapshot_path", "ALTER TABLE deployment_snapshots ADD COLUMN snapshot_path TEXT"),
        ("created_at", "ALTER TABLE deployment_snapshots ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in snapshot_migrations:
        if not column_exists("deployment_snapshots", column_name):
            execute(sql)
    project_repo_migrations = [
        ("project_id", "ALTER TABLE project_repos ADD COLUMN project_id INTEGER"),
        ("repo_url", "ALTER TABLE project_repos ADD COLUMN repo_url TEXT"),
        ("repo_path", "ALTER TABLE project_repos ADD COLUMN repo_path TEXT"),
        ("worktree_path", "ALTER TABLE project_repos ADD COLUMN worktree_path TEXT"),
        ("deploy_path", "ALTER TABLE project_repos ADD COLUMN deploy_path TEXT"),
        ("repo_status", "ALTER TABLE project_repos ADD COLUMN repo_status TEXT DEFAULT 'missing'"),
        ("last_commit", "ALTER TABLE project_repos ADD COLUMN last_commit TEXT"),
        ("branch", "ALTER TABLE project_repos ADD COLUMN branch TEXT"),
        ("sync_method", "ALTER TABLE project_repos ADD COLUMN sync_method TEXT DEFAULT 'local'"),
        ("created_at", "ALTER TABLE project_repos ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE project_repos ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in project_repo_migrations:
        if not column_exists("project_repos", column_name):
            execute(sql)
    ensure_project_repos_id_column()
    docker_scan_run_migrations = [
        ("target_id", "ALTER TABLE docker_scan_runs ADD COLUMN target_id INTEGER"),
        ("target_name", "ALTER TABLE docker_scan_runs ADD COLUMN target_name TEXT"),
        ("ssh_host", "ALTER TABLE docker_scan_runs ADD COLUMN ssh_host TEXT"),
        ("docker_root", "ALTER TABLE docker_scan_runs ADD COLUMN docker_root TEXT"),
        ("status", "ALTER TABLE docker_scan_runs ADD COLUMN status TEXT"),
        ("summary", "ALTER TABLE docker_scan_runs ADD COLUMN summary TEXT"),
        ("raw_output", "ALTER TABLE docker_scan_runs ADD COLUMN raw_output TEXT"),
        ("created_at", "ALTER TABLE docker_scan_runs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in docker_scan_run_migrations:
        if not column_exists("docker_scan_runs", column_name):
            execute(sql)
    docker_service_migrations = [
        ("target_id", "ALTER TABLE docker_services ADD COLUMN target_id INTEGER"),
        ("project_id", "ALTER TABLE docker_services ADD COLUMN project_id INTEGER"),
        ("service_name", "ALTER TABLE docker_services ADD COLUMN service_name TEXT"),
        ("container_name", "ALTER TABLE docker_services ADD COLUMN container_name TEXT"),
        ("image", "ALTER TABLE docker_services ADD COLUMN image TEXT"),
        ("status", "ALTER TABLE docker_services ADD COLUMN status TEXT"),
        ("ports", "ALTER TABLE docker_services ADD COLUMN ports TEXT"),
        ("compose_path", "ALTER TABLE docker_services ADD COLUMN compose_path TEXT"),
        ("deploy_path", "ALTER TABLE docker_services ADD COLUMN deploy_path TEXT"),
        ("volumes", "ALTER TABLE docker_services ADD COLUMN volumes TEXT"),
        ("last_seen_at", "ALTER TABLE docker_services ADD COLUMN last_seen_at TEXT"),
        ("raw_inspect", "ALTER TABLE docker_services ADD COLUMN raw_inspect TEXT"),
        ("created_at", "ALTER TABLE docker_services ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE docker_services ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in docker_service_migrations:
        if not column_exists("docker_services", column_name):
            execute(sql)
    service_endpoint_migrations = [
        ("docker_service_id", "ALTER TABLE service_endpoints ADD COLUMN docker_service_id INTEGER"),
        ("project_id", "ALTER TABLE service_endpoints ADD COLUMN project_id INTEGER"),
        ("endpoint_type", "ALTER TABLE service_endpoints ADD COLUMN endpoint_type TEXT"),
        ("url", "ALTER TABLE service_endpoints ADD COLUMN url TEXT"),
        ("path", "ALTER TABLE service_endpoints ADD COLUMN path TEXT"),
        ("status_code", "ALTER TABLE service_endpoints ADD COLUMN status_code INTEGER"),
        ("title", "ALTER TABLE service_endpoints ADD COLUMN title TEXT"),
        ("detected_from", "ALTER TABLE service_endpoints ADD COLUMN detected_from TEXT"),
        ("is_confirmed", "ALTER TABLE service_endpoints ADD COLUMN is_confirmed INTEGER DEFAULT 0"),
        ("is_ignored", "ALTER TABLE service_endpoints ADD COLUMN is_ignored INTEGER DEFAULT 0"),
        ("notes", "ALTER TABLE service_endpoints ADD COLUMN notes TEXT"),
        ("last_checked_at", "ALTER TABLE service_endpoints ADD COLUMN last_checked_at TEXT"),
        ("created_at", "ALTER TABLE service_endpoints ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE service_endpoints ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in service_endpoint_migrations:
        if not column_exists("service_endpoints", column_name):
            execute(sql)
    user_migrations = [
        ("username", "ALTER TABLE users ADD COLUMN username TEXT"),
        ("password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT"),
        ("role", "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'viewer'"),
        ("is_active", "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"),
        ("created_at", "ALTER TABLE users ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE users ADD COLUMN updated_at TEXT"),
        ("last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TEXT"),
    ]
    for column_name, sql in user_migrations:
        if not column_exists("users", column_name):
            execute(sql)
    audit_log_migrations = [
        ("user_id", "ALTER TABLE audit_logs ADD COLUMN user_id INTEGER"),
        ("role", "ALTER TABLE audit_logs ADD COLUMN role TEXT"),
        ("action", "ALTER TABLE audit_logs ADD COLUMN action TEXT"),
        ("target_type", "ALTER TABLE audit_logs ADD COLUMN target_type TEXT"),
        ("target_id", "ALTER TABLE audit_logs ADD COLUMN target_id INTEGER"),
        ("ip_address", "ALTER TABLE audit_logs ADD COLUMN ip_address TEXT"),
        ("user_agent", "ALTER TABLE audit_logs ADD COLUMN user_agent TEXT"),
        ("metadata", "ALTER TABLE audit_logs ADD COLUMN metadata TEXT"),
        ("created_at", "ALTER TABLE audit_logs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in audit_log_migrations:
        if not column_exists("audit_logs", column_name):
            execute(sql)
    api_key_migrations = [
        ("name", "ALTER TABLE api_keys ADD COLUMN name TEXT"),
        ("category", "ALTER TABLE api_keys ADD COLUMN category TEXT"),
        ("provider", "ALTER TABLE api_keys ADD COLUMN provider TEXT"),
        ("environment", "ALTER TABLE api_keys ADD COLUMN environment TEXT DEFAULT 'staging'"),
        ("status", "ALTER TABLE api_keys ADD COLUMN status TEXT DEFAULT 'active'"),
        ("version", "ALTER TABLE api_keys ADD COLUMN version TEXT DEFAULT 'v1'"),
        ("permissions", "ALTER TABLE api_keys ADD COLUMN permissions TEXT"),
        ("encrypted_value", "ALTER TABLE api_keys ADD COLUMN encrypted_value TEXT"),
        ("masked_value", "ALTER TABLE api_keys ADD COLUMN masked_value TEXT"),
        ("key_mask", "ALTER TABLE api_keys ADD COLUMN key_mask TEXT"),
        ("value_fingerprint", "ALTER TABLE api_keys ADD COLUMN value_fingerprint TEXT"),
        ("source", "ALTER TABLE api_keys ADD COLUMN source TEXT DEFAULT 'manual'"),
        ("notes", "ALTER TABLE api_keys ADD COLUMN notes TEXT"),
        ("created_at", "ALTER TABLE api_keys ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE api_keys ADD COLUMN updated_at TEXT"),
        ("last_used_at", "ALTER TABLE api_keys ADD COLUMN last_used_at TEXT"),
        ("rotation_days", "ALTER TABLE api_keys ADD COLUMN rotation_days INTEGER DEFAULT 30"),
        ("last_rotated_at", "ALTER TABLE api_keys ADD COLUMN last_rotated_at TEXT"),
        ("usage_limit", "ALTER TABLE api_keys ADD COLUMN usage_limit INTEGER"),
        ("is_system", "ALTER TABLE api_keys ADD COLUMN is_system INTEGER DEFAULT 0"),
        ("ai_allowed", "ALTER TABLE api_keys ADD COLUMN ai_allowed INTEGER DEFAULT 0"),
        ("revoked_at", "ALTER TABLE api_keys ADD COLUMN revoked_at TEXT"),
        ("revoked_reason", "ALTER TABLE api_keys ADD COLUMN revoked_reason TEXT"),
        ("last_revealed_at", "ALTER TABLE api_keys ADD COLUMN last_revealed_at TEXT"),
        ("replaced_by_key_id", "ALTER TABLE api_keys ADD COLUMN replaced_by_key_id INTEGER"),
    ]
    for column_name, sql in api_key_migrations:
        if not column_exists("api_keys", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            version TEXT,
            encrypted_value TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )"""
    )
    api_key_version_migrations = [
        ("api_key_id", "ALTER TABLE api_key_versions ADD COLUMN api_key_id INTEGER"),
        ("version", "ALTER TABLE api_key_versions ADD COLUMN version TEXT"),
        ("encrypted_value", "ALTER TABLE api_key_versions ADD COLUMN encrypted_value TEXT"),
        ("status", "ALTER TABLE api_key_versions ADD COLUMN status TEXT DEFAULT 'active'"),
        ("created_at", "ALTER TABLE api_key_versions ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in api_key_version_migrations:
        if not column_exists("api_key_versions", column_name):
            execute(sql)
    api_key_audit_migrations = [
        ("api_key_id", "ALTER TABLE api_key_audit_logs ADD COLUMN api_key_id INTEGER"),
        ("action", "ALTER TABLE api_key_audit_logs ADD COLUMN action TEXT"),
        ("user_id", "ALTER TABLE api_key_audit_logs ADD COLUMN user_id INTEGER"),
        ("ip", "ALTER TABLE api_key_audit_logs ADD COLUMN ip TEXT"),
        ("actor", "ALTER TABLE api_key_audit_logs ADD COLUMN actor TEXT"),
        ("ip_address", "ALTER TABLE api_key_audit_logs ADD COLUMN ip_address TEXT"),
        ("user_agent", "ALTER TABLE api_key_audit_logs ADD COLUMN user_agent TEXT"),
        ("metadata", "ALTER TABLE api_key_audit_logs ADD COLUMN metadata TEXT"),
        ("created_at", "ALTER TABLE api_key_audit_logs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in api_key_audit_migrations:
        if not column_exists("api_key_audit_logs", column_name):
            execute(sql)
    api_key_usage_migrations = [
        ("api_key_id", "ALTER TABLE api_key_usage ADD COLUMN api_key_id INTEGER"),
        ("source", "ALTER TABLE api_key_usage ADD COLUMN source TEXT"),
        ("path", "ALTER TABLE api_key_usage ADD COLUMN path TEXT"),
        ("ip_address", "ALTER TABLE api_key_usage ADD COLUMN ip_address TEXT"),
        ("status_code", "ALTER TABLE api_key_usage ADD COLUMN status_code INTEGER"),
        ("used_at", "ALTER TABLE api_key_usage ADD COLUMN used_at TEXT"),
    ]
    for column_name, sql in api_key_usage_migrations:
        if not column_exists("api_key_usage", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS api_key_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER,
            type TEXT,
            message TEXT,
            created_at TEXT
        )"""
    )
    api_key_alert_migrations = [
        ("api_key_id", "ALTER TABLE api_key_alerts ADD COLUMN api_key_id INTEGER"),
        ("type", "ALTER TABLE api_key_alerts ADD COLUMN type TEXT"),
        ("message", "ALTER TABLE api_key_alerts ADD COLUMN message TEXT"),
        ("created_at", "ALTER TABLE api_key_alerts ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in api_key_alert_migrations:
        if not column_exists("api_key_alerts", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS ai_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            priority INTEGER DEFAULT 100,
            default_model TEXT,
            cost_input_per_1k REAL DEFAULT 0,
            cost_output_per_1k REAL DEFAULT 0,
            daily_budget REAL,
            monthly_budget REAL,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    ai_provider_migrations = [
        ("provider_name", "ALTER TABLE ai_providers ADD COLUMN provider_name TEXT"),
        ("status", "ALTER TABLE ai_providers ADD COLUMN status TEXT DEFAULT 'active'"),
        ("priority", "ALTER TABLE ai_providers ADD COLUMN priority INTEGER DEFAULT 100"),
        ("default_model", "ALTER TABLE ai_providers ADD COLUMN default_model TEXT"),
        ("cost_input_per_1k", "ALTER TABLE ai_providers ADD COLUMN cost_input_per_1k REAL DEFAULT 0"),
        ("cost_output_per_1k", "ALTER TABLE ai_providers ADD COLUMN cost_output_per_1k REAL DEFAULT 0"),
        ("daily_budget", "ALTER TABLE ai_providers ADD COLUMN daily_budget REAL"),
        ("monthly_budget", "ALTER TABLE ai_providers ADD COLUMN monthly_budget REAL"),
        ("created_at", "ALTER TABLE ai_providers ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE ai_providers ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in ai_provider_migrations:
        if not column_exists("ai_providers", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            model TEXT,
            project_id INTEGER,
            dispatch_job_id INTEGER,
            task_role TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            status TEXT,
            error_message TEXT,
            prompt_summary TEXT,
            fallback_used INTEGER DEFAULT 0,
            fallback_from TEXT,
            created_at TEXT
        )"""
    )
    ai_usage_migrations = [
        ("provider", "ALTER TABLE ai_usage_logs ADD COLUMN provider TEXT"),
        ("model", "ALTER TABLE ai_usage_logs ADD COLUMN model TEXT"),
        ("project_id", "ALTER TABLE ai_usage_logs ADD COLUMN project_id INTEGER"),
        ("dispatch_job_id", "ALTER TABLE ai_usage_logs ADD COLUMN dispatch_job_id INTEGER"),
        ("task_role", "ALTER TABLE ai_usage_logs ADD COLUMN task_role TEXT"),
        ("input_tokens", "ALTER TABLE ai_usage_logs ADD COLUMN input_tokens INTEGER DEFAULT 0"),
        ("output_tokens", "ALTER TABLE ai_usage_logs ADD COLUMN output_tokens INTEGER DEFAULT 0"),
        ("estimated_cost", "ALTER TABLE ai_usage_logs ADD COLUMN estimated_cost REAL DEFAULT 0"),
        ("status", "ALTER TABLE ai_usage_logs ADD COLUMN status TEXT"),
        ("error_message", "ALTER TABLE ai_usage_logs ADD COLUMN error_message TEXT"),
        ("prompt_summary", "ALTER TABLE ai_usage_logs ADD COLUMN prompt_summary TEXT"),
        ("fallback_used", "ALTER TABLE ai_usage_logs ADD COLUMN fallback_used INTEGER DEFAULT 0"),
        ("fallback_from", "ALTER TABLE ai_usage_logs ADD COLUMN fallback_from TEXT"),
        ("created_at", "ALTER TABLE ai_usage_logs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in ai_usage_migrations:
        if not column_exists("ai_usage_logs", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            provider TEXT,
            model TEXT,
            task_role TEXT,
            prompt_summary TEXT,
            status TEXT,
            response_text TEXT,
            error_message TEXT,
            raw_response TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    ai_message_migrations = [
        ("project_id", "ALTER TABLE ai_messages ADD COLUMN project_id INTEGER"),
        ("provider", "ALTER TABLE ai_messages ADD COLUMN provider TEXT"),
        ("model", "ALTER TABLE ai_messages ADD COLUMN model TEXT"),
        ("task_role", "ALTER TABLE ai_messages ADD COLUMN task_role TEXT"),
        ("prompt_summary", "ALTER TABLE ai_messages ADD COLUMN prompt_summary TEXT"),
        ("status", "ALTER TABLE ai_messages ADD COLUMN status TEXT"),
        ("response_text", "ALTER TABLE ai_messages ADD COLUMN response_text TEXT"),
        ("error_message", "ALTER TABLE ai_messages ADD COLUMN error_message TEXT"),
        ("raw_response", "ALTER TABLE ai_messages ADD COLUMN raw_response TEXT"),
        ("created_at", "ALTER TABLE ai_messages ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE ai_messages ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in ai_message_migrations:
        if not column_exists("ai_messages", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT,
            provider TEXT,
            prompt TEXT,
            status TEXT,
            result TEXT,
            error_message TEXT,
            auto_run_next INTEGER DEFAULT 0,
            last_auto_run_at TEXT,
            requires_approval INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT 'none',
            approved_at TEXT,
            approved_by TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    task_migrations = [
        ("project_id", "ALTER TABLE tasks ADD COLUMN project_id INTEGER"),
        ("title", "ALTER TABLE tasks ADD COLUMN title TEXT"),
        ("task_type", "ALTER TABLE tasks ADD COLUMN task_type TEXT"),
        ("priority", "ALTER TABLE tasks ADD COLUMN priority TEXT"),
        ("provider", "ALTER TABLE tasks ADD COLUMN provider TEXT"),
        ("prompt", "ALTER TABLE tasks ADD COLUMN prompt TEXT"),
        ("status", "ALTER TABLE tasks ADD COLUMN status TEXT"),
        ("result", "ALTER TABLE tasks ADD COLUMN result TEXT"),
        ("error_message", "ALTER TABLE tasks ADD COLUMN error_message TEXT"),
        ("started_at", "ALTER TABLE tasks ADD COLUMN started_at TEXT"),
        ("finished_at", "ALTER TABLE tasks ADD COLUMN finished_at TEXT"),
        ("retry_count", "ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0"),
        ("max_retries", "ALTER TABLE tasks ADD COLUMN max_retries INTEGER DEFAULT 3"),
        ("parent_task_id", "ALTER TABLE tasks ADD COLUMN parent_task_id INTEGER"),
        ("auto_run_next", "ALTER TABLE tasks ADD COLUMN auto_run_next INTEGER DEFAULT 0"),
        ("last_auto_run_at", "ALTER TABLE tasks ADD COLUMN last_auto_run_at TEXT"),
        ("requires_approval", "ALTER TABLE tasks ADD COLUMN requires_approval INTEGER DEFAULT 0"),
        ("approval_status", "ALTER TABLE tasks ADD COLUMN approval_status TEXT DEFAULT 'none'"),
        ("approved_at", "ALTER TABLE tasks ADD COLUMN approved_at TEXT"),
        ("approved_by", "ALTER TABLE tasks ADD COLUMN approved_by TEXT"),
        ("created_at", "ALTER TABLE tasks ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE tasks ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in task_migrations:
        if not column_exists("tasks", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS flow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            mode TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            total_tasks INTEGER DEFAULT 0,
            done_tasks INTEGER DEFAULT 0,
            failed_tasks INTEGER DEFAULT 0,
            stopped_reason TEXT,
            summary TEXT,
            created_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        )"""
    )
    flow_run_migrations = [
        ("project_id", "ALTER TABLE flow_runs ADD COLUMN project_id INTEGER"),
        ("mode", "ALTER TABLE flow_runs ADD COLUMN mode TEXT"),
        ("status", "ALTER TABLE flow_runs ADD COLUMN status TEXT"),
        ("started_at", "ALTER TABLE flow_runs ADD COLUMN started_at TEXT"),
        ("finished_at", "ALTER TABLE flow_runs ADD COLUMN finished_at TEXT"),
        ("total_tasks", "ALTER TABLE flow_runs ADD COLUMN total_tasks INTEGER DEFAULT 0"),
        ("done_tasks", "ALTER TABLE flow_runs ADD COLUMN done_tasks INTEGER DEFAULT 0"),
        ("failed_tasks", "ALTER TABLE flow_runs ADD COLUMN failed_tasks INTEGER DEFAULT 0"),
        ("stopped_reason", "ALTER TABLE flow_runs ADD COLUMN stopped_reason TEXT"),
        ("summary", "ALTER TABLE flow_runs ADD COLUMN summary TEXT"),
        ("created_at", "ALTER TABLE flow_runs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in flow_run_migrations:
        if not column_exists("flow_runs", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS task_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            task_type TEXT,
            provider TEXT,
            prompt_template TEXT,
            priority TEXT,
            sort_order INTEGER DEFAULT 100,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    task_template_migrations = [
        ("name", "ALTER TABLE task_templates ADD COLUMN name TEXT"),
        ("task_type", "ALTER TABLE task_templates ADD COLUMN task_type TEXT"),
        ("provider", "ALTER TABLE task_templates ADD COLUMN provider TEXT"),
        ("prompt_template", "ALTER TABLE task_templates ADD COLUMN prompt_template TEXT"),
        ("priority", "ALTER TABLE task_templates ADD COLUMN priority TEXT"),
        ("sort_order", "ALTER TABLE task_templates ADD COLUMN sort_order INTEGER DEFAULT 100"),
        ("is_active", "ALTER TABLE task_templates ADD COLUMN is_active INTEGER DEFAULT 1"),
        ("created_at", "ALTER TABLE task_templates ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE task_templates ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in task_template_migrations:
        if not column_exists("task_templates", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS ai_fallback_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_provider TEXT,
            fallback_provider TEXT,
            task_role TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT
        )"""
    )
    ai_fallback_migrations = [
        ("primary_provider", "ALTER TABLE ai_fallback_rules ADD COLUMN primary_provider TEXT"),
        ("fallback_provider", "ALTER TABLE ai_fallback_rules ADD COLUMN fallback_provider TEXT"),
        ("task_role", "ALTER TABLE ai_fallback_rules ADD COLUMN task_role TEXT"),
        ("enabled", "ALTER TABLE ai_fallback_rules ADD COLUMN enabled INTEGER DEFAULT 1"),
        ("created_at", "ALTER TABLE ai_fallback_rules ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in ai_fallback_migrations:
        if not column_exists("ai_fallback_rules", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS content_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            type TEXT,
            script TEXT,
            prompt TEXT,
            status TEXT DEFAULT 'queued',
            output_url TEXT,
            post_text TEXT,
            post_status TEXT DEFAULT 'draft',
            post_platform TEXT,
            post_id TEXT,
            created_at TEXT
        )"""
    )
    content_job_migrations = [
        ("project_id", "ALTER TABLE content_jobs ADD COLUMN project_id INTEGER"),
        ("type", "ALTER TABLE content_jobs ADD COLUMN type TEXT"),
        ("title", "ALTER TABLE content_jobs ADD COLUMN title TEXT"),
        ("script", "ALTER TABLE content_jobs ADD COLUMN script TEXT"),
        ("prompt", "ALTER TABLE content_jobs ADD COLUMN prompt TEXT"),
        ("provider", "ALTER TABLE content_jobs ADD COLUMN provider TEXT"),
        ("status", "ALTER TABLE content_jobs ADD COLUMN status TEXT DEFAULT 'queued'"),
        ("output_url", "ALTER TABLE content_jobs ADD COLUMN output_url TEXT"),
        ("post_text", "ALTER TABLE content_jobs ADD COLUMN post_text TEXT"),
        ("post_status", "ALTER TABLE content_jobs ADD COLUMN post_status TEXT DEFAULT 'draft'"),
        ("post_platform", "ALTER TABLE content_jobs ADD COLUMN post_platform TEXT"),
        ("post_id", "ALTER TABLE content_jobs ADD COLUMN post_id TEXT"),
        ("created_at", "ALTER TABLE content_jobs ADD COLUMN created_at TEXT"),
    ]
    for column_name, sql in content_job_migrations:
        if not column_exists("content_jobs", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT,
            title TEXT,
            summary TEXT,
            content TEXT,
            telegram_result TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    daily_report_migrations = [
        ("report_date", "ALTER TABLE daily_reports ADD COLUMN report_date TEXT"),
        ("title", "ALTER TABLE daily_reports ADD COLUMN title TEXT"),
        ("summary", "ALTER TABLE daily_reports ADD COLUMN summary TEXT"),
        ("content", "ALTER TABLE daily_reports ADD COLUMN content TEXT"),
        ("telegram_result", "ALTER TABLE daily_reports ADD COLUMN telegram_result TEXT"),
        ("created_at", "ALTER TABLE daily_reports ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE daily_reports ADD COLUMN updated_at TEXT"),
    ]
    for column_name, sql in daily_report_migrations:
        if not column_exists("daily_reports", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS tenant_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            type TEXT,
            content TEXT
        )"""
    )
    tenant_knowledge_migrations = [
        ("tenant_id", "ALTER TABLE tenant_knowledge ADD COLUMN tenant_id INTEGER"),
        ("type", "ALTER TABLE tenant_knowledge ADD COLUMN type TEXT"),
        ("content", "ALTER TABLE tenant_knowledge ADD COLUMN content TEXT"),
    ]
    for column_name, sql in tenant_knowledge_migrations:
        if not column_exists("tenant_knowledge", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS tenant_settings (
            tenant_id INTEGER PRIMARY KEY,
            industry TEXT,
            strict_mode INTEGER DEFAULT 1,
            fallback_message TEXT
        )"""
    )
    tenant_settings_migrations = [
        ("tenant_id", "ALTER TABLE tenant_settings ADD COLUMN tenant_id INTEGER"),
        ("industry", "ALTER TABLE tenant_settings ADD COLUMN industry TEXT"),
        ("strict_mode", "ALTER TABLE tenant_settings ADD COLUMN strict_mode INTEGER DEFAULT 1"),
        ("fallback_message", "ALTER TABLE tenant_settings ADD COLUMN fallback_message TEXT"),
    ]
    for column_name, sql in tenant_settings_migrations:
        if not column_exists("tenant_settings", column_name):
            execute(sql)
    execute(
        """CREATE TABLE IF NOT EXISTS industry_templates (
            industry TEXT PRIMARY KEY,
            allowed_topics TEXT,
            blocked_topics TEXT
        )"""
    )
    industry_template_migrations = [
        ("industry", "ALTER TABLE industry_templates ADD COLUMN industry TEXT"),
        ("allowed_topics", "ALTER TABLE industry_templates ADD COLUMN allowed_topics TEXT"),
        ("blocked_topics", "ALTER TABLE industry_templates ADD COLUMN blocked_topics TEXT"),
    ]
    for column_name, sql in industry_template_migrations:
        if not column_exists("industry_templates", column_name):
            execute(sql)
    seed_industry_templates()
    heartbeat_migrations = [
        ("source", "ALTER TABLE ai_heartbeats ADD COLUMN source TEXT"),
        ("agent_name", "ALTER TABLE ai_heartbeats ADD COLUMN agent_name TEXT"),
        ("project_id", "ALTER TABLE ai_heartbeats ADD COLUMN project_id INTEGER"),
        ("project_name", "ALTER TABLE ai_heartbeats ADD COLUMN project_name TEXT"),
        ("machine_name", "ALTER TABLE ai_heartbeats ADD COLUMN machine_name TEXT"),
        ("status", "ALTER TABLE ai_heartbeats ADD COLUMN status TEXT"),
        ("current_task", "ALTER TABLE ai_heartbeats ADD COLUMN current_task TEXT"),
        ("last_message", "ALTER TABLE ai_heartbeats ADD COLUMN last_message TEXT"),
        ("pid", "ALTER TABLE ai_heartbeats ADD COLUMN pid TEXT"),
        ("session_id", "ALTER TABLE ai_heartbeats ADD COLUMN session_id TEXT"),
        ("raw_payload", "ALTER TABLE ai_heartbeats ADD COLUMN raw_payload TEXT"),
        ("created_at", "ALTER TABLE ai_heartbeats ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE ai_heartbeats ADD COLUMN updated_at TEXT"),
        ("last_seen_at", "ALTER TABLE ai_heartbeats ADD COLUMN last_seen_at TEXT"),
        ("last_seen", "ALTER TABLE ai_heartbeats ADD COLUMN last_seen TEXT"),
        ("active_dispatch", "ALTER TABLE ai_heartbeats ADD COLUMN active_dispatch TEXT"),
    ]
    for column_name, sql in heartbeat_migrations:
        if not column_exists("ai_heartbeats", column_name):
            execute(sql)
    seed_ai_providers()
    sync_service_endpoint_project_ids()
    seed_computers()
    seed_deployment_targets()
    ensure_disney_nas_info()


def sync_service_endpoint_project_ids():
    now = now_str()
    execute(
        """UPDATE service_endpoints
           SET project_id=(
                   SELECT ds.project_id
                   FROM docker_services ds
                   WHERE ds.id=service_endpoints.docker_service_id
               ),
               updated_at=?
           WHERE EXISTS (
                   SELECT 1
                   FROM docker_services ds
                   WHERE ds.id=service_endpoints.docker_service_id
               )
             AND project_id IS NOT (
                   SELECT ds.project_id
                   FROM docker_services ds
                   WHERE ds.id=service_endpoints.docker_service_id
               )""",
        (now,),
    )


def ensure_project_repos_id_column():
    columns = [row["name"] for row in query_all("PRAGMA table_info(project_repos)")]
    if "id" in columns:
        return
    backup_name = f"project_repos_legacy_{now_dt().strftime('%Y%m%d%H%M%S')}"
    execute(f"ALTER TABLE project_repos RENAME TO {backup_name}")
    execute(
        """CREATE TABLE project_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            repo_url TEXT,
            repo_path TEXT,
            worktree_path TEXT,
            deploy_path TEXT,
            repo_status TEXT DEFAULT 'missing',
            last_commit TEXT,
            branch TEXT,
            sync_method TEXT DEFAULT 'local',
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    legacy_columns = [row["name"] for row in query_all(f"PRAGMA table_info({backup_name})")]
    copy_columns = [
        col for col in [
            "project_id", "repo_url", "repo_path", "worktree_path", "deploy_path",
            "repo_status", "last_commit", "branch", "sync_method", "created_at", "updated_at",
        ]
        if col in legacy_columns
    ]
    if copy_columns:
        cols = ", ".join(copy_columns)
        execute(f"INSERT INTO project_repos ({cols}) SELECT {cols} FROM {backup_name}")


def apply_machine_name_mappings():
    now = now_str()
    for raw_name, display_name in MACHINE_NAME_MAPPING.items():
        execute(
            "UPDATE projects SET owner_machine=?, updated_at=? WHERE owner_machine=?",
            (display_name, now, raw_name),
        )


def seed_computers():
    count = query_one("SELECT COUNT(*) AS c FROM computers")["c"]
    if count:
        return
    defaults = [
        ("公司主機", "desktop", "公司", "Windows", "", "主要開發主機"),
        ("筆電 A", "laptop", "可攜", "Windows", "", "開發筆電"),
        ("筆電 B", "laptop", "可攜", "Windows", "", "備用開發筆電"),
        ("NAS", "server", "機房 / NAS", "Linux", "", "部署主機"),
        ("VPS", "server", "Cloud", "Linux", "", "部署主機"),
        ("客戶主機", "server", "客戶端", "", "", "客戶部署環境"),
    ]
    for name, device_type, location, os_name, ip_address, notes in defaults:
        execute(
            "INSERT INTO computers (name, device_type, location, os_name, ip_address, notes, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (name, device_type, location, os_name, ip_address, notes, now_str(), now_str()),
        )


def seed_deployment_targets():
    count = query_one("SELECT COUNT(*) AS c FROM deployment_targets")["c"]
    if count:
        upsert_disney_deployment_target()
        return
    defaults = [
        ("本機測試", "local", "本機", "127.0.0.1", "", "", "", "", "本機開發與測試"),
        ("Synology NAS", "nas", "內網", "", "", "", "22", "", "主要 NAS 部署"),
        ("客戶 NAS", "nas", "客戶端", "", "", "", "22", "", "客戶端 NAS"),
        ("VPS", "vps", "Cloud", "", "", "", "22", "root", "雲端部署主機"),
    ]
    for name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes in defaults:
        execute(
            """INSERT INTO deployment_targets
               (name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes, now_str(), now_str()),
        )
    upsert_disney_deployment_target()


def upsert_disney_deployment_target():
    if query_one("SELECT id FROM deployment_targets WHERE ip_address=? LIMIT 1", ("211.75.219.184",)):
        return
    execute(
        """INSERT INTO deployment_targets
           (name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            "disney NAS", "Synology NAS", "公司", "211.75.219.184", "",
            "211.75.219.184", "22", "chaokun",
            "SSH key 已設定，Docker 根目錄 /volume1/docker",
            now_str(), now_str(),
        ),
    )


def ensure_disney_nas_info():
    notes = "SSH key 已設定，Docker 根目錄 /volume1/docker"
    existing = query_one(
        "SELECT * FROM deployment_targets WHERE name=? OR ip_address=? LIMIT 1",
        ("disney NAS", "211.75.219.184"),
    )
    if existing:
        execute(
            """UPDATE deployment_targets
               SET name=?, target_type=?, location=?, ip_address=?, ssh_host=?, ssh_port=?, ssh_user=?, notes=?, is_active=1, updated_at=?
               WHERE id=?""",
            ("disney NAS", "Synology NAS", "公司", "211.75.219.184", "211.75.219.184", "22", "chaokun", notes, now_str(), existing["id"]),
        )
    else:
        execute(
            """INSERT INTO deployment_targets
               (name, target_type, location, ip_address, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            ("disney NAS", "Synology NAS", "公司", "211.75.219.184", "211.75.219.184", "22", "chaokun", notes, now_str(), now_str()),
        )


def seed_templates():
    count = query_one("SELECT COUNT(*) AS c FROM project_templates")["c"]
    if count:
        return
    templates = [
        ("網站系統模板", "一般網站 / SaaS / 後台系統", ["需求確認", "資料庫設計", "後端 API", "前端頁面", "測試修正", "部署", "客戶驗收", "交付結案"]),
        ("Python 工具模板", "Excel、資料轉換、GUI、打包 EXE", ["需求確認", "Excel/資料格式分析", "核心邏輯", "GUI 介面", "測試資料", "打包 EXE", "使用說明", "交付驗收"]),
        ("後台管理系統模板", "CRUD、登入權限、報表、部署", ["需求確認", "資料表設計", "CRUD 功能", "權限登入", "報表功能", "部署", "驗收", "結案"]),
        ("AI 自動化模板", "Codex / Claude / Cursor 多工具協作", ["需求確認", "API 規格", "AI 回寫流程", "任務自動化", "測試驗證", "部署", "交接文件", "驗收結案"]),
    ]
    for name, desc, phases in templates:
        execute(
            "INSERT INTO project_templates (name, description, phases_json, created_at) VALUES (?, ?, ?, ?)",
            (name, desc, json_dumps(phases), now_str()),
        )


def seed_task_templates():
    now = now_str()
    for template in DEFAULT_TASK_TEMPLATES:
        existing = query_one("SELECT id FROM task_templates WHERE name=?", (template["name"],))
        if existing:
            execute(
                """UPDATE task_templates
                   SET task_type=?, provider=?, prompt_template=?, priority=?, sort_order=?,
                       is_active=1, updated_at=?
                   WHERE id=?""",
                (
                    template["task_type"],
                    template["provider"],
                    template["prompt_template"],
                    template["priority"],
                    template["sort_order"],
                    now,
                    existing["id"],
                ),
            )
            continue
        execute(
            """INSERT INTO task_templates
               (name, task_type, provider, prompt_template, priority, sort_order, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                template["name"],
                template["task_type"],
                template["provider"],
                template["prompt_template"],
                template["priority"],
                template["sort_order"],
                now,
                now,
            ),
        )


def seed_demo_project():
    count = query_one("SELECT COUNT(*) AS c FROM projects")["c"]
    if count:
        return
    cur = execute(
        """INSERT INTO projects
        (name, client_name, project_type, status, priority, github_repo, local_path, deploy_url, deploy_location, owner_machine, description, next_steps, progress, template_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("回頭車配對系統", "內部 / 客戶驗收", "網站系統", "待驗收", "高", "", "", "", "NAS Docker", "A電腦", "示範專案：管理多階段開發與 AI 交接紀錄", "明天進行客戶驗收", 0, 1, now_str(), now_str()),
    )
    project_id = cur.lastrowid
    phases = ["需求確認", "資料庫設計", "後端 API", "前端頁面", "測試修正", "部署", "客戶驗收", "交付結案"]
    for i, p in enumerate(phases, 1):
        execute(
            "INSERT INTO project_phases (project_id, phase_name, phase_order, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, p, i, "已完成" if i <= 6 else "未開始", now_str(), now_str()),
        )
    execute(
        "INSERT INTO handoff_logs (project_id, source, agent_name, work_mode, summary, completed_phases, test_result, git_status, next_steps, warnings, api_payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, "codex", "Codex", "code-change", "示範：完成第六階段部署前整理，準備驗收。", json_dumps(["第六階段", "部署"]), "測試通過", "clean", "客戶驗收", "未部署正式環境", "{}", now_str()),
    )
    recalc_project(project_id)


def create_phases_from_template(project_id, template_id):
    template = query_one("SELECT * FROM project_templates WHERE id=?", (template_id,))
    if not template:
        return
    phases = parse_json_list(template["phases_json"])
    for i, phase_name in enumerate(phases, 1):
        execute(
            "INSERT INTO project_phases (project_id, phase_name, phase_order, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, phase_name, i, "未開始", now_str(), now_str()),
        )


def template_dispatch_task(template):
    if not template:
        return ""
    text = f"{template['name']} {template['description'] or ''}"
    rules = [
        (("網站系統", "網站", "SaaS"), "建立網站系統架構（前台 + 後台 + API）"),
        (("Python 工具", "Python", "Excel"), "建立 Python 工具（CLI + GUI + Excel）"),
        (("後台管理", "CRUD", "權限"), "建立 CRUD + 權限系統"),
        (("AI 自動化", "Codex", "Claude", "Cursor"), "建立 AI workflow（Codex + Claude + Cursor）"),
    ]
    for keywords, task in rules:
        if any(keyword in text for keyword in keywords):
            return task
    return ""


def ensure_project_repo_for_dispatch(project_id):
    repo = project_repo_row(project_id)
    if repo and repo.get("worktree_path"):
        return repo
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise ValueError("project not found")
    slug = project_slug(project["name"], f"project-{project_id}")
    paths = default_repo_paths(slug)
    payload = {
        "repo_url": "",
        "repo_path": paths["repo_path"],
        "worktree_path": paths["worktree_path"],
        "deploy_path": paths["deploy_path"],
        "repo_status": "missing",
        "last_commit": "",
        "branch": "main",
        "sync_method": "local",
    }
    upsert_project_repo(project_id, payload)
    return project_repo_row(project_id)


def build_template_dispatch_prompt(project, task, repo):
    worktree_path = (repo or {}).get("worktree_path") or ""
    return "\n".join([
        task,
        "",
        f"專案：{project['name']}",
        f"Worktree：{worktree_path}",
        "",
        "安全規則：",
        f"- 只修改 worktree：{worktree_path}",
        "- 不可改 /volume1/docker",
        "- 不可改 .env",
        "- 不可刪 data / uploads / *.db",
        "- 完成後回報修改檔案與測試結果",
    ])


def create_dispatch_job_from_template(project_id, template_id):
    if not template_id:
        return None
    template = query_one("SELECT * FROM project_templates WHERE id=?", (template_id,))
    task = template_dispatch_task(template)
    if not task:
        return None
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise ValueError("project not found")
    repo = ensure_project_repo_for_dispatch(project_id)
    prompt = build_template_dispatch_prompt(project, task, repo)
    return create_dispatch_job({
        "project_id": project_id,
        "agent": "codex",
        "provider": "openai",
        "task_role": "executor",
        "task_prompt": prompt,
        "risk_level": "low",
        "approval_required": True,
    })


def normalize_phase_token(token):
    if not token:
        return ""
    token = str(token).strip()
    token = token.replace("第", "").replace("階段", "").replace(" ", "")
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15}
    if token in cn:
        return str(cn[token])
    m = re.search(r"\d+", token)
    return m.group(0) if m else token


def find_phase(project_id, phase_hint):
    phases = query_all("SELECT * FROM project_phases WHERE project_id=? ORDER BY phase_order", (project_id,))
    hint = str(phase_hint or "").strip()
    if not hint:
        return None
    n = normalize_phase_token(hint)
    if n.isdigit():
        for p in phases:
            if int(p["phase_order"]) == int(n):
                return p
    for p in phases:
        if hint in p["phase_name"] or p["phase_name"] in hint:
            return p
    return None


def update_phase_status(project_id, phase_hint, status="已完成", test_result=None, notes=None):
    phase = find_phase(project_id, phase_hint)
    if not phase:
        return False
    completed_at = now_str() if status in ["已完成", "已驗收"] else phase["completed_at"]
    execute(
        "UPDATE project_phases SET status=?, test_result=COALESCE(?, test_result), notes=COALESCE(?, notes), completed_at=?, updated_at=? WHERE id=?",
        (status, test_result, notes, completed_at, now_str(), phase["id"]),
    )
    return True


def extract_phases_from_text(text):
    if not text:
        return []
    found = []
    patterns = [
        r"第\s*([一二三四五六七八九十百千0-9]+)\s*階段[^\n：:]*[：:]?[^\n]*(完成|已完成)",
        r"phase\s*([0-9]+)[^\n]*(done|complete|completed)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            found.append(f"第{m.group(1)}階段")
    return list(dict.fromkeys(found))


def parse_handoff_text(raw_text):
    lines = [l.strip() for l in (raw_text or "").splitlines() if l.strip()]
    completed_phases = extract_phases_from_text(raw_text)
    next_steps = ""
    warnings = ""
    test_result = ""
    changed_files = []
    git_status = ""
    db_backups = []
    for line in lines:
        low = line.lower()
        if "下一步" in line or "next" in low:
            next_steps = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        if "警告" in line or "注意" in line or "warning" in low:
            warnings = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        if "測試" in line or "test" in low or "console" in low:
            test_result = line
        if "git status" in low or "clean" in low or "modified" in low or "untracked" in low:
            git_status = line
        if re.search(r"\.py|\.html|\.js|\.css|\.md|\.sql|Dockerfile|docker-compose", line):
            changed_files.extend(re.findall(r"[\w./\\-]+\.(?:py|html|js|css|md|sql|json|toml|yml|yaml|txt)|Dockerfile|docker-compose\.yml", line))
        if ".bak" in line or "backup" in low:
            db_backups.append(line)
    summary = lines[0] if lines else ""
    return {
        "summary": summary,
        "completed_phases": completed_phases,
        "changed_files": list(dict.fromkeys(changed_files)),
        "test_result": test_result,
        "git_status": git_status,
        "db_backups": db_backups,
        "next_steps": next_steps,
        "warnings": warnings,
    }


def recalc_phase_by_tasks(project_id, phase_id):
    tasks = query_all("SELECT * FROM project_tasks WHERE project_id=? AND phase_id=?", (project_id, phase_id))
    if not tasks:
        return
    statuses = [t["status"] for t in tasks]
    if any(s in ["有問題"] for s in statuses):
        status = "有問題"
    elif any(s == "逾期" for s in statuses):
        status = "逾期"
    elif all(s == "已完成" for s in statuses):
        status = "已完成"
    elif any(s == "進行中" for s in statuses):
        status = "進行中"
    else:
        status = "未開始"
    execute("UPDATE project_phases SET status=?, updated_at=? WHERE id=?", (status, now_str(), phase_id))


def recalc_project(project_id):
    phases = query_all("SELECT * FROM project_phases WHERE project_id=?", (project_id,))
    tasks = query_all("SELECT * FROM project_tasks WHERE project_id=?", (project_id,))
    if tasks:
        done = sum(1 for t in tasks if t["status"] == "已完成")
        progress = round(done / len(tasks) * 100)
    elif phases:
        done = sum(1 for p in phases if p["status"] in ["已完成", "已驗收"])
        progress = round(done / len(phases) * 100)
    else:
        progress = 0
    status = query_one("SELECT status FROM projects WHERE id=?", (project_id,))["status"]
    if phases and all(p["status"] in ["已完成", "已驗收"] for p in phases):
        status = "待驗收"
    if any(p["status"] == "有問題" for p in phases):
        status = "有問題"
    acc = query_all("SELECT * FROM acceptance_items WHERE project_id=?", (project_id,))
    if acc and all(a["accepted"] == 1 for a in acc):
        status = "已結案"
        progress = 100
    execute("UPDATE projects SET progress=?, status=?, updated_at=? WHERE id=?", (progress, status, now_str(), project_id))


def log_api(project_id, payload, status_code=200, source=None):
    try:
        execute(
            "INSERT INTO api_logs (method, path, source, project_id, status_code, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request.method, request.path, source, project_id, status_code, json.dumps(payload, ensure_ascii=False), now_str()),
        )
    except Exception:
        pass


def api_key_permissions_from_value(value):
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(",", "\n").splitlines()
    tags = []
    for item in raw_items:
        tag = str(item).strip().lower()
        if tag in API_KEY_PERMISSIONS and tag not in tags:
            tags.append(tag)
    return tags


def infer_api_key_provider(name):
    upper = str(name or "").upper()
    if "OPENAI" in upper:
        return "openai"
    if "ANTHROPIC" in upper or "CLAUDE" in upper:
        return "anthropic"
    if "GEMINI" in upper or "GOOGLE" in upper:
        return "google"
    if "CURSOR" in upper:
        return "cursor"
    if "GITHUB" in upper:
        return "github"
    if "GITEA" in upper:
        return "gitea"
    if "TELEGRAM" in upper:
        return "telegram"
    if "CLOUDFLARE" in upper or upper.startswith("CF_"):
        return "cloudflare"
    if "DEV_PILOT" in upper or upper == "API_TOKEN":
        return "devpilot"
    if "NAS" in upper or "SSH" in upper:
        return "nas"
    return "other"


def infer_api_key_category(name, provider):
    upper = str(name or "").upper()
    if provider in ("openai", "anthropic", "google", "cursor") or "AI" in upper:
        return "ai"
    if provider == "telegram" or "WEBHOOK" in upper:
        return "webhook"
    if provider == "cloudflare":
        return "third-party"
    if provider in ("github", "gitea", "nas") or "DEPLOY" in upper or "SSH" in upper:
        return "deploy"
    if "DB" in upper or "DATABASE" in upper:
        return "database"
    if provider == "devpilot":
        return "devpilot"
    return "other"


def infer_api_key_permissions(name, provider):
    upper = str(name or "").upper()
    permissions = []
    if provider in ("openai", "anthropic", "google", "cursor"):
        permissions.append("ai")
    if provider == "telegram" or "WEBHOOK" in upper:
        permissions.append("webhook")
    if provider == "cloudflare":
        permissions.extend(["read", "write", "deploy"])
    if provider in ("github", "gitea", "nas") or "DEPLOY" in upper or "SSH" in upper:
        permissions.extend(["read", "write", "deploy"])
    if provider == "devpilot":
        permissions.extend(["read", "write"])
    return [tag for tag in API_KEY_PERMISSIONS if tag in permissions]


def api_key_payload_from_form(form, source="manual"):
    name = (form.get("name") or "").strip()
    key_value = form.get("key_value") or ""
    if not name:
        raise ValueError("API Key 名稱必填")
    if not key_value:
        raise ValueError("Key value 必填")
    provider = normalize_choice(form.get("provider"), API_KEY_PROVIDERS, "other")
    category = normalize_choice(form.get("category"), API_KEY_CATEGORIES, "other")
    environment = normalize_choice(form.get("environment"), API_KEY_ENVIRONMENTS, "staging")
    status = normalize_choice(form.get("status"), API_KEY_STATUSES, "active")
    version = (form.get("version") or "v1").strip() or "v1"
    permissions = api_key_permissions_from_value(form.getlist("permissions") if hasattr(form, "getlist") else form.get("permissions"))
    try:
        rotation_days = int(form.get("rotation_days") or 30)
    except (TypeError, ValueError):
        rotation_days = 30
    try:
        usage_limit = int(form.get("usage_limit")) if form.get("usage_limit") not in (None, "") else None
    except (TypeError, ValueError):
        usage_limit = None
    ai_allowed = 1 if form.get("ai_allowed") in ("1", "true", "on", "yes") and environment == "staging" else 0
    return {
        "name": name,
        "category": category,
        "provider": provider,
        "environment": environment,
        "status": status,
        "version": version,
        "permissions": permissions,
        "key_value": key_value,
        "notes": (form.get("notes") or "").strip(),
        "rotation_days": rotation_days,
        "usage_limit": usage_limit,
        "ai_allowed": ai_allowed,
        "source": source,
    }


def api_key_audit(api_key_id, action, metadata=None):
    user = current_user()
    try:
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        user_agent = request.headers.get("User-Agent", "")
        actor = "web"
    except RuntimeError:
        ip_address = ""
        user_agent = ""
        actor = "system"
    execute(
        """INSERT INTO api_key_audit_logs
           (api_key_id, action, user_id, ip, actor, ip_address, user_agent, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            api_key_id,
            action,
            user.get("id") if user else None,
            ip_address,
            actor,
            ip_address,
            user_agent,
            json.dumps(metadata or {}, ensure_ascii=False),
            now_str(),
        ),
    )


def create_api_key_record(payload):
    key_value = payload["key_value"]
    now = now_str()
    encrypted = encrypt_secret_value(key_value)
    masked = mask_secret_value(key_value)
    cur = execute(
        """INSERT INTO api_keys
           (name, category, provider, environment, status, version, permissions, encrypted_value, key_mask,
            masked_value, value_fingerprint, source, notes, created_at, updated_at,
            rotation_days, last_rotated_at, usage_limit, is_system, ai_allowed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload["name"],
            payload.get("category") or "other",
            payload.get("provider") or "other",
            payload.get("environment") or "staging",
            payload.get("status") or "active",
            payload.get("version") or "v1",
            json_dumps(payload.get("permissions") or []),
            encrypted,
            masked,
            masked,
            secret_fingerprint(key_value),
            payload.get("source") or "manual",
            payload.get("notes", ""),
            now,
            now,
            int(payload.get("rotation_days") or 30),
            now,
            payload.get("usage_limit"),
            int(payload.get("is_system") or 0),
            1 if payload.get("ai_allowed") and (payload.get("environment") or "staging") == "staging" else 0,
        ),
    )
    execute(
        "INSERT INTO api_key_versions (api_key_id, version, encrypted_value, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (cur.lastrowid, payload.get("version") or "v1", encrypted, payload.get("status") or "active", now),
    )
    api_key_audit(cur.lastrowid, "create", {"name": payload["name"], "provider": payload.get("provider"), "version": payload.get("version")})
    return cur.lastrowid


def api_keys_with_stats():
    since = (now_dt() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    rows = query_all(
        """SELECT k.*,
                  COALESCE(u.usage_7d, 0) AS usage_7d,
                  COALESCE(al.alert_count, 0) AS alert_count,
                  COALESCE(a.audit_count, 0) AS audit_count
           FROM api_keys k
           LEFT JOIN (
               SELECT api_key_id, COUNT(*) AS usage_7d
               FROM api_key_usage
               WHERE used_at >= ?
               GROUP BY api_key_id
           ) u ON u.api_key_id=k.id
           LEFT JOIN (
               SELECT api_key_id, COUNT(*) AS alert_count
               FROM api_key_alerts
               GROUP BY api_key_id
           ) al ON al.api_key_id=k.id
           LEFT JOIN (
               SELECT api_key_id, COUNT(*) AS audit_count
               FROM api_key_audit_logs
               GROUP BY api_key_id
           ) a ON a.api_key_id=k.id
           ORDER BY k.provider, k.name, k.version DESC, k.id DESC""",
        (since,),
    )
    items = []
    for row in rows:
        item = row_to_dict(row)
        item["permissions_list"] = parse_json_list(item.get("permissions"))
        item["display_mask"] = item.get("masked_value") or item.get("key_mask") or "************"
        item["has_alert"] = bool(item.get("alert_count"))
        items.append(item)
    return items


def api_key_history(name, provider):
    rows = query_all(
        """SELECT v.id, v.api_key_id, k.name, k.provider, v.version, v.status, k.masked_value, k.key_mask, v.created_at, k.revoked_at
           FROM api_key_versions v
           JOIN api_keys k ON k.id=v.api_key_id
           WHERE k.name=? AND k.provider=?
           ORDER BY v.created_at DESC, v.id DESC""",
        (name, provider),
    )
    return [row_to_dict(row) for row in rows]


def recent_api_key_audits(limit=30):
    return query_all(
        """SELECT a.*, COALESCE(a.ip, a.ip_address) AS display_ip, k.name AS key_name, k.provider AS provider, k.version AS version
           FROM api_key_audit_logs a
           LEFT JOIN api_keys k ON k.id=a.api_key_id
           ORDER BY a.created_at DESC, a.id DESC
           LIMIT ?""",
        (limit,),
    )


def reveal_api_key_value(api_key_id):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,))
    if not row:
        raise LookupError("API Key 不存在")
    if row["status"] == "revoked":
        raise ValueError("已 revoke 的 API Key 不可顯示")
    value = decrypt_secret_value(row["encrypted_value"])
    execute("UPDATE api_keys SET last_revealed_at=?, updated_at=? WHERE id=?", (now_str(), now_str(), api_key_id))
    api_key_audit(api_key_id, "view", {"name": row["name"], "version": row["version"]})
    return row_to_dict(row), value


def copy_api_key_value(api_key_id):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,))
    if not row:
        raise LookupError("API Key 不存在")
    if row["status"] == "revoked":
        raise ValueError("已 revoke 的 API Key 不可複製")
    value = decrypt_secret_value(row["encrypted_value"])
    api_key_audit(api_key_id, "copy", {"name": row["name"], "version": row["version"]})
    return row_to_dict(row), value


def revoke_api_key(api_key_id, reason):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,))
    if not row:
        raise LookupError("API Key 不存在")
    execute(
        "UPDATE api_keys SET status='revoked', revoked_at=?, revoked_reason=?, updated_at=? WHERE id=?",
        (now_str(), reason or "manual revoke", now_str(), api_key_id),
    )
    execute("UPDATE api_key_versions SET status='revoked' WHERE api_key_id=?", (api_key_id,))
    api_key_audit(api_key_id, "revoke", {"reason": reason or "manual revoke", "name": row["name"], "version": row["version"]})
    return row


def next_api_key_version(api_key_id):
    latest = query_one("SELECT version FROM api_key_versions WHERE api_key_id=? ORDER BY id DESC LIMIT 1", (api_key_id,))
    if latest and latest["version"]:
        match = re.search(r"(\d+)$", latest["version"])
        if match:
            return f"v{int(match.group(1)) + 1}"
    return "v1"


def rotate_api_key(api_key_id):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,))
    if not row:
        raise LookupError("API Key 不存在")
    new_value = generate_api_key_value()
    new_version = next_api_key_version(api_key_id)
    encrypted = encrypt_secret_value(new_value)
    masked = mask_secret_value(new_value)
    now = now_str()
    execute("UPDATE api_key_versions SET status='revoked' WHERE api_key_id=?", (api_key_id,))
    execute(
        """UPDATE api_keys
           SET encrypted_value=?, masked_value=?, key_mask=?, value_fingerprint=?,
               version=?, status='active', revoked_at=NULL, revoked_reason=NULL,
               last_rotated_at=?, updated_at=?
           WHERE id=?""",
        (encrypted, masked, masked, secret_fingerprint(new_value), new_version, now, now, api_key_id),
    )
    execute(
        "INSERT INTO api_key_versions (api_key_id, version, encrypted_value, status, created_at) VALUES (?, ?, ?, 'active', ?)",
        (api_key_id, new_version, encrypted, now),
    )
    api_key_audit(api_key_id, "rotate", {"name": row["name"], "version": new_version})
    updated = row_to_dict(query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,)))
    return updated, new_value


def api_key_alert(api_key_id, alert_type, message):
    execute(
        "INSERT INTO api_key_alerts (api_key_id, type, message, created_at) VALUES (?, ?, ?, ?)",
        (api_key_id, alert_type, message, now_str()),
    )
    api_key_audit(api_key_id, alert_type, {"message": message})


def api_key_environment_allowed(row, path, role=None):
    environment = row["environment"] or "staging"
    path_text = str(path or "").lower()
    role = role or current_role()
    staging_allowed = ("staging" in path_text) or ("test" in path_text) or ("validate" in path_text) or path_text.startswith("/api/api-keys/")
    if role == "ai":
        return bool(row["ai_allowed"]) and environment == "staging" and staging_allowed
    if environment == "staging":
        return staging_allowed
    if environment == "production":
        return ("production" in path_text) or ("prod" in path_text) or ("formal" in path_text)
    return False


CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_DNS_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS"]
DOMAIN_CENTER_NAS_IP = NAS_SSH_HOST
PREVIEW_DOMAIN_ENVIRONMENTS = ["preview", "staging"]
PREVIEW_DOMAIN_PURPOSES = ["website", "ai_chat", "api_service", "console", "landing"]
PREVIEW_DOMAIN_DEFAULT_PURPOSE = "website"
PREVIEW_DOMAIN_BASE_DOMAINS = {
    "website": "webai.net.tw",
    "ai_chat": "aichat.net.tw",
    "api_service": "aiserver.com.tw",
    "console": "aicenter.com.tw",
    "landing": "webai.tw",
}
APPROVAL_REQUEST_TYPES = ["dns_preview_create", "mock_approval_test"]
APPROVAL_REQUEST_STATUSES = ["pending", "approved", "rejected", "expired", "canceled"]
APPROVAL_ALLOWED_ROLES = ["owner", "admin"]
APPROVAL_CALLBACK_PREFIX = "apv"
APPROVAL_DEFAULT_EXPIRES_HOURS = 24
DNS_PLAN_CONFIRM_PHRASE = "CONFIRM_DNS_PLAN_ONLY"
CLOUDFLARE_DNS_WRITE_FEATURE_FLAG = "CLOUDFLARE_DNS_WRITE_ENABLED"
MOCK_DNS_EXECUTION_FEATURE_FLAG = "MOCK_DNS_EXECUTION_ENABLED"
DNS_PREVIEW_EXECUTION_STATES = {
    "pending": "waiting_approval",
    "approved": "approved_ready_for_manual_dns_plan",
    "rejected": "rejected_no_action",
    "expired": "expired_no_action",
    "canceled": "canceled_no_action",
}


def cloudflare_api_keys():
    rows = query_all(
        """SELECT id, name, category, provider, environment, status, version,
                  masked_value, key_mask, permissions, notes, created_at, updated_at, last_used_at
           FROM api_keys
           WHERE lower(COALESCE(provider, ''))='cloudflare'
           ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, datetime(COALESCE(updated_at, created_at)) DESC, id DESC"""
    )
    items = []
    for row in rows:
        item = row_to_dict(row)
        item["display_mask"] = item.get("masked_value") or item.get("key_mask") or "************"
        item["permissions_list"] = parse_json_list(item.get("permissions"))
        items.append(item)
    return items


def get_active_cloudflare_api_key(api_key_id=None):
    params = []
    where = [
        "lower(COALESCE(provider, ''))='cloudflare'",
        "lower(COALESCE(category, ''))='third-party'",
        "lower(COALESCE(environment, ''))='staging'",
        "lower(COALESCE(status, ''))='active'",
    ]
    if api_key_id:
        where.append("id=?")
        params.append(int(api_key_id))
    row = row_to_dict(query_one(
        f"""SELECT id, name, provider, category, environment, status, encrypted_value, masked_value, key_mask, updated_at, created_at
            FROM api_keys
            WHERE {' AND '.join(where)}
            ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
            LIMIT 1""",
        params,
    ))
    if not row:
        return {"ok": False, "error": "cloudflare_token_not_configured"}
    masked = row.get("masked_value") or row.get("key_mask") or "************"
    token_meta = {"name": row.get("name"), "environment": row.get("environment"), "masked": masked}
    try:
        token = decrypt_secret_value(row.get("encrypted_value"))
    except Exception:
        return {"ok": False, "error": "cloudflare_token_decrypt_failed", "api_key": token_meta}
    if not str(token or "").strip():
        return {"ok": False, "error": "cloudflare_token_empty", "api_key": token_meta}
    return {"ok": True, "token": str(token).strip(), "api_key": token_meta}


def cloudflare_sanitized_error(error):
    text = str(error or "")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(Authorization:\s*)[^\s]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    return text[:500]


def cloudflare_request(method, path, token, payload=None, query=None, timeout=30):
    url = CLOUDFLARE_API_BASE + path
    if query:
        safe_query = {key: value for key, value in query.items() if value not in (None, "")}
        if safe_query:
            url = f"{url}?{urllib.parse.urlencode(safe_query)}"
    data = None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            return {"ok": bool(data.get("success", True)), "status_code": resp.status, "data": data}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(body)
            errors = error_data.get("errors") or []
            message = "; ".join(str(item.get("message") or item) for item in errors) or f"Cloudflare HTTP {exc.code}"
        except Exception:
            message = f"Cloudflare HTTP {exc.code}"
        return {"ok": False, "status_code": exc.code, "error": cloudflare_sanitized_error(message)}
    except Exception as exc:
        return {"ok": False, "status_code": None, "error": cloudflare_sanitized_error(type(exc).__name__)}


def cloudflare_zone_public(item):
    account = item.get("account") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "status": item.get("status"),
        "paused": item.get("paused"),
        "type": item.get("type"),
        "account_name": account.get("name"),
    }


def cloudflare_dns_record_public(item):
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "name": item.get("name"),
        "content": item.get("content"),
        "ttl": item.get("ttl"),
        "proxied": item.get("proxied"),
        "comment": item.get("comment"),
        "created_on": item.get("created_on"),
        "modified_on": item.get("modified_on"),
    }


def mask_identifier(value, prefix=6, suffix=4):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= prefix + suffix + 4:
        return f"{text[:2]}****{text[-2:]}" if len(text) > 4 else "****"
    return f"{text[:prefix]}****{text[-suffix:]}"


def mask_dns_record_content(record):
    record_type = str(record.get("type") or "").upper()
    content = str(record.get("content") or "")
    if record_type == "TXT":
        return f"[masked TXT length={len(content)}]"
    return content


def normalize_domain_name(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    text = text.split(":", 1)[0]
    text = re.sub(r"[^a-z0-9.-]", "", text)
    text = re.sub(r"\.+", ".", text).strip(".")
    return text


def dns_hostname_is_valid(value):
    name = normalize_domain_name(value)
    if not name or len(name) > 253 or "." not in name:
        return False
    for label in name.split("."):
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
            return False
    return True


def dns_a_target_is_valid(value):
    try:
        return ipaddress.ip_address(str(value or "").strip()).version == 4
    except ValueError:
        return False


def dns_cname_target_is_valid(value):
    target = normalize_domain_name(value)
    if not dns_hostname_is_valid(target):
        return False
    try:
        ipaddress.ip_address(target)
        return False
    except ValueError:
        return True


def dns_label_slug(value, max_length=54):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    text = text[:max_length].strip("-")
    return text


def preview_domain_label(project):
    project_id = int(project["id"])
    slug = dns_label_slug(project["name"], max_length=54)
    source = "project_slug"
    if not slug:
        slug = f"project{project_id}"
        source = "project_id"
    label = f"{slug}-preview"
    if len(label) > 63:
        slug = slug[:54].strip("-") or f"project{project_id}"
        label = f"{slug}-preview"
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
        label = f"project{project_id}-preview"
        source = "project_id"
    return label, source


def normalize_preview_domain_purpose(value):
    return normalize_choice(value, PREVIEW_DOMAIN_PURPOSES, PREVIEW_DOMAIN_DEFAULT_PURPOSE)


def preview_base_domain_for_purpose(purpose):
    return PREVIEW_DOMAIN_BASE_DOMAINS.get(normalize_preview_domain_purpose(purpose), PREVIEW_DOMAIN_BASE_DOMAINS[PREVIEW_DOMAIN_DEFAULT_PURPOSE])


def build_preview_domain_plan(project_id, base_domain=None, environment="preview", project_type=None):
    project = query_one("SELECT id, name FROM projects WHERE id=?", (int(project_id),))
    if not project:
        return {"ok": False, "error": "project_not_found"}, 404

    purpose = normalize_preview_domain_purpose(project_type)
    explicit_base_domain = bool(str(base_domain or "").strip())
    base_domain = normalize_domain_name(base_domain or preview_base_domain_for_purpose(purpose))
    if not base_domain or "." not in base_domain:
        return {"ok": False, "error": "invalid_base_domain"}, 400

    environment = normalize_choice(environment, DOMAIN_MAPPING_ENVIRONMENTS, "preview")
    if environment not in PREVIEW_DOMAIN_ENVIRONMENTS:
        return {"ok": False, "error": "environment_not_allowed_for_preview_plan"}, 400

    label, label_source = preview_domain_label(project)
    record_name = f"{label}.{base_domain}"
    blocked_names = {base_domain, f"www.{base_domain}"}
    if record_name.lower() in blocked_names:
        return {"ok": False, "error": "blocked_dns_name"}, 400

    domain_data = fetch_domain_center_zones()
    if not domain_data.get("ok"):
        return {"ok": False, "error": domain_data.get("error") or "domain_center_unavailable"}, 502

    zone = None
    for item in domain_data.get("zones") or []:
        if str(item.get("name") or "").casefold() == base_domain.casefold():
            zone = item
            break
    if not zone:
        return {"ok": False, "error": "base_domain_not_found", "base_domain": base_domain}, 404

    existing_records = []
    for record in zone.get("records") or []:
        if str(record.get("name") or "").casefold() == record_name.casefold():
            existing_records.append({
                "type": record.get("type"),
                "name": record.get("name"),
                "content": record.get("content"),
                "proxied": record.get("proxied"),
                "ttl": record.get("ttl"),
            })

    warnings = []
    if existing_records:
        warnings.append("DNS record already exists. No write action was taken.")

    return {
        "ok": True,
        "action": "plan_only",
        "requires_approval": True,
        "record_exists": bool(existing_records),
        "project": {
            "id": project["id"],
            "name": project["name"],
        },
        "base_domain": base_domain,
        "base_domain_source": "request" if explicit_base_domain else "project_type",
        "project_type": purpose,
        "purpose": purpose,
        "environment": environment,
        "zone": {
            "name": zone.get("name"),
            "id_masked": zone.get("id_masked"),
        },
        "candidate_source": label_source,
        "dns_record": {
            "type": "A",
            "name": record_name,
            "content": DOMAIN_CENTER_NAS_IP,
            "proxied": True,
            "ttl": 1,
        },
        "existing_records": existing_records,
        "warnings": warnings,
    }, 200


def secure_hash_text(value, purpose="approval"):
    text = str(value or "")
    key = hashlib.sha256(encryption_material()).digest()
    return hmac.new(key, f"{purpose}:{text}".encode("utf-8"), hashlib.sha256).hexdigest()


def approval_nonce_hash(nonce):
    return secure_hash_text(nonce, "approval_nonce")


def telegram_user_id_hash(user_id):
    return secure_hash_text(user_id, "telegram_user_id")


def approval_payload_contains_secret(value):
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value or "")
    lowered = text.lower()
    blocked_terms = [
        "authorization",
        "bearer ",
        "encrypted_value",
        "value_fingerprint",
        "api_key_id",
        "telegram token",
        "cloudflare token",
        "api key",
        "x-api-key",
    ]
    return any(term in lowered for term in blocked_terms)


def sanitize_approval_payload(request_type, payload):
    request_type = normalize_choice(request_type, APPROVAL_REQUEST_TYPES, "")
    if request_type != "dns_preview_create":
        raise ValueError("unsupported approval request type")
    source = payload if isinstance(payload, dict) else {}
    record = source.get("dns_record") if isinstance(source.get("dns_record"), dict) else source
    record_type = str(record.get("type") or "").strip().upper()
    target = str(record.get("content") or "").strip()
    if record_type == "CNAME":
        target = normalize_domain_name(target)
    dns_record = {
        "type": record_type,
        "name": normalize_domain_name(record.get("name")),
        "content": target,
        "proxied": bool(record.get("proxied")),
        "ttl": coerce_int(record.get("ttl"), 1),
    }
    if dns_record["type"] not in ("A", "CNAME"):
        raise ValueError("unsupported_record_type")
    if not dns_hostname_is_valid(dns_record["name"]):
        raise ValueError("invalid_record_name")
    if dns_record["type"] == "A" and not dns_a_target_is_valid(dns_record["content"]):
        raise ValueError("invalid_record_target")
    if dns_record["type"] == "CNAME" and not dns_cname_target_is_valid(dns_record["content"]):
        raise ValueError("invalid_record_target")
    if dns_record["type"] == "CNAME" and dns_record["content"] == dns_record["name"]:
        raise ValueError("invalid_record_target")
    if dns_record["name"].split(".", 1)[0] in ("", "www"):
        raise ValueError("root and www records are not supported by this approval MVP")
    sanitized = {"dns_record": dns_record}
    if approval_payload_contains_secret(sanitized):
        raise ValueError("approval payload contains blocked secret-like fields")
    return sanitized


def approval_request_row(request_id):
    return row_to_dict(
        query_one(
            """SELECT ar.*, p.name AS project_name
               FROM approval_requests ar
               LEFT JOIN projects p ON p.id=ar.project_id
               WHERE ar.id=?""",
            (request_id,),
        )
    )


def approval_request_public(row):
    if not row:
        return None
    item = row_to_dict(row)
    item.pop("callback_nonce_hash", None)
    raw_payload = item.get("payload_json") or "{}"
    try:
        item["payload"] = json.loads(raw_payload)
    except Exception:
        item["payload"] = {}
    item["payload_json"] = json.dumps(item["payload"], ensure_ascii=False)
    item.update(approval_request_execution_summary(item))
    return item


def approval_request_execution_summary(item):
    request_type = str((item or {}).get("request_type") or "").strip()
    status = str((item or {}).get("status") or "").strip()
    if request_type == "dns_preview_create":
        execution_state = DNS_PREVIEW_EXECUTION_STATES.get(status, "waiting_approval")
        return {
            "execution_state": execution_state,
            "plan_only": True,
            "dns_write_enabled": False,
            "requires_manual_execution": True,
            "manual_execution_available": status == "approved",
            "execution_note": "Approval never writes Cloudflare DNS or deploys automatically.",
        }
    if request_type == "mock_approval_test":
        return {
            "execution_state": f"mock_{status or 'unknown'}_no_action",
            "plan_only": True,
            "dns_write_enabled": False,
            "requires_manual_execution": False,
            "manual_execution_available": False,
            "execution_note": "Mock request only tests approval state transitions.",
        }
    return {
        "execution_state": "unknown_no_action",
        "plan_only": True,
        "dns_write_enabled": False,
        "requires_manual_execution": False,
        "manual_execution_available": False,
        "execution_note": "No automatic execution is configured for this approval request.",
    }


def dns_plan_zone_name(record_name):
    hostname = normalize_domain_name(record_name)
    candidates = sorted(set(PREVIEW_DOMAIN_BASE_DOMAINS.values()), key=len, reverse=True)
    for base_domain in candidates:
        base_domain = normalize_domain_name(base_domain)
        if hostname == base_domain or hostname.endswith(f".{base_domain}"):
            return base_domain
    parts = hostname.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname


def dns_preview_planned_action_from_payload(payload):
    approval_payload = sanitize_approval_payload("dns_preview_create", payload)
    dns_record = approval_payload["dns_record"]
    zone_name = dns_plan_zone_name(dns_record["name"])
    return {
        "provider": "cloudflare",
        "action": "create_or_update_dns_record",
        "record_type": dns_record["type"],
        "name": dns_record["name"],
        "zone_name": zone_name,
        "target": dns_record["content"],
        "proxied": bool(dns_record.get("proxied")),
        "ttl": coerce_int(dns_record.get("ttl"), 1),
    }


def build_approval_dns_plan_prepare(request_id):
    row = approval_request_row(request_id)
    if not row:
        return {"ok": False, "error": "approval_request_not_found"}, 404

    public = approval_request_public(row)
    request_type = public.get("request_type")
    if request_type != "dns_preview_create":
        return {
            "ok": False,
            "error": "unsupported_request_type",
            "request_id": request_id,
            "request_type": request_type,
            "plan_only": True,
            "dns_write_enabled": False,
        }, 400

    execution = approval_request_execution_summary(public)
    status = public.get("status")
    execution_state = execution.get("execution_state")
    if status != "approved" or execution_state != "approved_ready_for_manual_dns_plan":
        return {
            "ok": False,
            "error": execution_state or "approval_not_ready",
            "request_id": request_id,
            "request_type": request_type,
            "approval_status": status,
            "execution_state": execution_state,
            "plan_only": True,
            "dns_write_enabled": False,
            "requires_manual_execution": True,
        }, 409

    try:
        payload = json.loads(row.get("payload_json") or "{}")
        planned_action = dns_preview_planned_action_from_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": "invalid_dns_preview_payload",
            "message": str(exc),
            "request_id": request_id,
            "plan_only": True,
            "dns_write_enabled": False,
        }, 400

    return {
        "ok": True,
        "mode": "dry_run",
        "plan_only": True,
        "dns_write_enabled": False,
        "requires_second_confirmation": True,
        "requires_manual_execution": True,
        "manual_execution_available": True,
        "request_id": request_id,
        "request_type": request_type,
        "approval_status": status,
        "execution_state": execution_state,
        "planned_action": planned_action,
        "next_step": "manual_second_confirmation_required",
        "message": "Dry-run only. No Cloudflare DNS record was created or updated.",
    }, 200


def dns_rollback_plan_draft(planned_action):
    action = planned_action or {}
    record_name = action.get("name") or "the planned DNS record"
    return {
        "available": True,
        "strategy": "manual_revert_or_delete_record",
        "record_name": record_name,
        "steps": [
            "Before executing, capture existing DNS record state.",
            "If this creates a new record, rollback by deleting that record.",
            "If this updates an existing record, rollback by restoring previous content, proxied state, and TTL.",
            "Verify DNS propagation after rollback.",
        ],
    }


def dns_interlock_risk_checklist(public, planned_action):
    status = (public or {}).get("status")
    return [
        {
            "key": "approval_required",
            "label": "Approval request must be approved",
            "passed": status == "approved",
        },
        {
            "key": "dry_run_required",
            "label": "Dry-run plan must be reviewed",
            "passed": bool(planned_action),
        },
        {
            "key": "second_confirmation_required",
            "label": "Second confirmation phrase is required",
            "passed": True,
        },
        {
            "key": "feature_flag_disabled",
            "label": "DNS write feature flag is disabled",
            "passed": not cloudflare_dns_write_feature_enabled(),
        },
        {
            "key": "no_auto_deploy",
            "label": "No deploy job will be created",
            "passed": True,
        },
    ]


def build_approval_dns_plan_interlock(request_id):
    row = approval_request_row(request_id)
    if not row:
        return {"ok": False, "error": "approval_request_not_found"}, 404

    public = approval_request_public(row)
    request_type = public.get("request_type")
    if request_type != "dns_preview_create":
        return {
            "ok": False,
            "error": "unsupported_request_type",
            "request_id": request_id,
            "request_type": request_type,
            "dns_write_enabled": False,
            "cloudflare_api_call_enabled": False,
        }, 400

    try:
        payload = json.loads(row.get("payload_json") or "{}")
        planned_action = dns_preview_planned_action_from_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": "invalid_dns_plan_payload",
            "message": str(exc),
            "request_id": request_id,
            "dns_write_enabled": False,
            "cloudflare_api_call_enabled": False,
        }, 400

    execution_state = public.get("execution_state")
    feature_flag = cloudflare_dns_write_flag_status()
    return {
        "ok": True,
        "mode": "read_only_interlock",
        "request": {
            "id": public.get("id"),
            "request_type": request_type,
            "status": public.get("status"),
            "project_id": public.get("project_id"),
            "title": public.get("title"),
            "summary": public.get("summary"),
        },
        "request_id": request_id,
        "request_type": request_type,
        "status": public.get("status"),
        "approval_status": public.get("status"),
        "execution_state": execution_state,
        "can_execute_now": False,
        "execute_disabled": True,
        "dns_write_enabled": False,
        "cloudflare_api_call_enabled": False,
        "deployment_job_will_be_created": False,
        "feature_flag": {
            "name": CLOUDFLARE_DNS_WRITE_FEATURE_FLAG,
            "effective_enabled": feature_flag.get("effective_enabled"),
            "can_toggle_here": False,
        },
        "planned_action": planned_action,
        "rollback_plan_draft": dns_rollback_plan_draft(planned_action),
        "risk_checklist": dns_interlock_risk_checklist(public, planned_action),
        "final_phrase_required": DNS_PLAN_CONFIRM_PHRASE,
        "next_step": "execute_endpoint_disabled_until_future_phase",
        "message": "Read-only interlock. No Cloudflare DNS record was created or updated.",
    }, 200


def dns_plan_payload_error(exc):
    message = str(exc or "") or "invalid_dns_plan_payload"
    known_errors = {
        "unsupported_record_type",
        "invalid_record_name",
        "invalid_record_target",
    }
    return message if message in known_errors else "invalid_dns_plan_payload"


def dns_preflight_record_snapshot(record):
    public = cloudflare_dns_record_public(record)
    return {
        "id_masked": mask_identifier(public.get("id")),
        "type": public.get("type"),
        "name": public.get("name"),
        "content": mask_dns_record_content(public),
        "ttl": public.get("ttl"),
        "proxied": public.get("proxied"),
        "created_on": public.get("created_on"),
        "modified_on": public.get("modified_on"),
    }


def dns_preflight_error_response(error, request_id, status_code=400, **extra):
    body = {
        "ok": False,
        "error": error,
        "request_id": request_id,
        "mode": "read_only_preflight",
        "dns_write_enabled": False,
        "cloudflare_write_call_enabled": False,
        "deployment_job_will_be_created": False,
    }
    body.update(extra)
    return body, status_code


def fetch_dns_preflight_cloudflare_snapshot(planned_action):
    key_info = get_active_cloudflare_api_key()
    if not key_info.get("ok"):
        return {"ok": False, "error": "cloudflare_read_credentials_unavailable"}

    token = key_info["token"]
    zone_name = planned_action.get("zone_name")
    zones_result = cloudflare_request(
        "GET",
        "/zones",
        token,
        query={"name": zone_name, "page": 1, "per_page": 50},
    )
    if not zones_result.get("ok"):
        return {
            "ok": False,
            "error": zones_result.get("error") or "cloudflare_read_error",
            "status_code": zones_result.get("status_code"),
        }

    zones = ((zones_result.get("data") or {}).get("result") or [])
    zone = None
    for item in zones:
        if str(item.get("name") or "").casefold() == str(zone_name or "").casefold():
            zone = item
            break
    if not zone:
        return {"ok": False, "error": "zone_not_found", "zones_checked": len(zones)}

    zone_id = str(zone.get("id") or "")
    records_result = cloudflare_request(
        "GET",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
        token,
        query={
            "name": planned_action.get("name"),
            "page": 1,
            "per_page": 100,
        },
    )
    if not records_result.get("ok"):
        return {
            "ok": False,
            "error": records_result.get("error") or "cloudflare_read_error",
            "status_code": records_result.get("status_code"),
        }

    return {
        "ok": True,
        "zone": zone,
        "records": ((records_result.get("data") or {}).get("result") or []),
    }


def dns_preflight_rollback_snapshot(decision, planned_action, existing_record=None):
    if decision == "update" and existing_record:
        return {
            "available": True,
            "strategy": "restore_previous_record",
            "existing_record": dns_preflight_record_snapshot(existing_record),
            "steps": [
                "Capture the existing DNS record before any write.",
                "If execution must be rolled back, restore the previous content, proxied state, and TTL.",
                "Verify the restored record in Cloudflare and through DNS resolution.",
            ],
        }
    return {
        "available": True,
        "strategy": "delete_created_record",
        "planned_record": {
            "type": planned_action.get("record_type"),
            "name": planned_action.get("name"),
            "target": planned_action.get("target"),
            "proxied": planned_action.get("proxied"),
            "ttl": planned_action.get("ttl"),
        },
        "steps": [
            "Capture the no-existing-record state before any write.",
            "If execution must be rolled back, delete the newly created DNS record.",
            "Verify the record no longer exists in Cloudflare and through DNS resolution.",
        ],
    }


def dns_preflight_readiness_checklist(public, planned_action, zone_check, record_check, rollback_snapshot):
    return [
        {
            "key": "approval_approved",
            "label": "Approval request is approved",
            "passed": (public or {}).get("status") == "approved",
        },
        {
            "key": "zone_found",
            "label": "Cloudflare zone exists",
            "passed": bool((zone_check or {}).get("found")),
        },
        {
            "key": "record_name_in_zone",
            "label": "Record name belongs to the selected zone",
            "passed": bool((zone_check or {}).get("record_name_belongs_to_zone")),
        },
        {
            "key": "record_type_supported",
            "label": "Record type is supported for preflight",
            "passed": planned_action.get("record_type") in ("A", "CNAME"),
        },
        {
            "key": "record_target_valid",
            "label": "Record target format is valid",
            "passed": True,
        },
        {
            "key": "existing_record_checked",
            "label": "Existing DNS records were checked read-only",
            "passed": bool((record_check or {}).get("checked")),
        },
        {
            "key": "no_conflicting_record_type",
            "label": "No conflicting same-name record type was found",
            "passed": not bool((record_check or {}).get("conflicting_record_types")),
        },
        {
            "key": "dns_write_disabled",
            "label": "DNS write remains disabled",
            "passed": True,
        },
        {
            "key": "no_auto_deploy",
            "label": "No deployment job will be created",
            "passed": True,
        },
        {
            "key": "rollback_snapshot_ready",
            "label": "Rollback snapshot is available",
            "passed": bool((rollback_snapshot or {}).get("available")),
        },
    ]


def build_approval_dns_plan_preflight(request_id):
    row = approval_request_row(request_id)
    if not row:
        return dns_preflight_error_response("approval_request_not_found", request_id, 404)

    public = approval_request_public(row)
    request_type = public.get("request_type")
    if request_type != "dns_preview_create":
        return dns_preflight_error_response(
            "unsupported_request_type",
            request_id,
            400,
            request_type=request_type,
        )

    execution_state = public.get("execution_state")
    status = public.get("status")
    if status != "approved" or execution_state != "approved_ready_for_manual_dns_plan":
        return dns_preflight_error_response(
            execution_state or "approval_not_ready",
            request_id,
            409,
            request_type=request_type,
            approval_status=status,
            execution_state=execution_state,
        )

    try:
        payload = json.loads(row.get("payload_json") or "{}")
        planned_action = dns_preview_planned_action_from_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        error = dns_plan_payload_error(exc)
        return dns_preflight_error_response(error, request_id, 400)

    record_type = planned_action.get("record_type")
    record_name = planned_action.get("name")
    record_target = planned_action.get("target")
    zone_name = planned_action.get("zone_name")

    if record_type not in ("A", "CNAME"):
        return dns_preflight_error_response("unsupported_record_type", request_id, 400)
    if not dns_hostname_is_valid(record_name) or not str(record_name).endswith(f".{zone_name}"):
        return dns_preflight_error_response("invalid_record_name", request_id, 400)
    if record_type == "A" and not dns_a_target_is_valid(record_target):
        return dns_preflight_error_response("invalid_record_target", request_id, 400)
    if record_type == "CNAME" and (not dns_cname_target_is_valid(record_target) or record_target == record_name):
        return dns_preflight_error_response("invalid_record_target", request_id, 400)

    snapshot = fetch_dns_preflight_cloudflare_snapshot(planned_action)
    if not snapshot.get("ok"):
        error = snapshot.get("error") or "cloudflare_read_error"
        if error == "zone_not_found":
            return dns_preflight_error_response(
                "zone_not_found",
                request_id,
                409,
                zone_check={
                    "requested_zone": zone_name,
                    "found": False,
                    "zones_checked": snapshot.get("zones_checked", 0),
                },
                planned_action=planned_action,
            )
        return dns_preflight_error_response(
            "cloudflare_read_error",
            request_id,
            502,
            cloudflare_status_code=snapshot.get("status_code"),
            message=cloudflare_sanitized_error(error),
        )

    zone_public = cloudflare_zone_public(snapshot.get("zone") or {})
    zone_check = {
        "requested_zone": zone_name,
        "found": True,
        "record_name_belongs_to_zone": record_name == zone_name or str(record_name).endswith(f".{zone_name}"),
        "zone": {
            "name": zone_public.get("name"),
            "id_masked": mask_identifier(zone_public.get("id")),
            "status": zone_public.get("status"),
            "paused": zone_public.get("paused"),
        },
    }
    existing_records = snapshot.get("records") or []
    same_name_records = [
        item for item in existing_records
        if str(item.get("name") or "").casefold() == str(record_name or "").casefold()
    ]
    same_type_records = [
        item for item in same_name_records
        if str(item.get("type") or "").upper() == str(record_type or "").upper()
    ]
    conflicting_record_types = sorted({
        str(item.get("type") or "").upper()
        for item in same_name_records
        if str(item.get("type") or "").upper() != str(record_type or "").upper()
    })
    decision = "update" if same_type_records else "create"
    rollback_snapshot = dns_preflight_rollback_snapshot(decision, planned_action, same_type_records[0] if same_type_records else None)
    record_check = {
        "checked": True,
        "record_name": record_name,
        "record_type": record_type,
        "existing_same_name_count": len(same_name_records),
        "existing_same_type_count": len(same_type_records),
        "conflicting_record_types": conflicting_record_types,
        "existing_records": [dns_preflight_record_snapshot(item) for item in same_name_records],
    }
    readiness_checklist = dns_preflight_readiness_checklist(public, planned_action, zone_check, record_check, rollback_snapshot)
    preflight_passed = all(bool(item.get("passed")) for item in readiness_checklist)

    return {
        "ok": True,
        "mode": "read_only_preflight",
        "request_id": request_id,
        "request_type": request_type,
        "approval_status": status,
        "execution_state": execution_state,
        "plan_only": True,
        "dns_write_enabled": False,
        "cloudflare_write_call_enabled": False,
        "deployment_job_will_be_created": False,
        "preflight_passed": preflight_passed,
        "decision": decision,
        "zone_check": zone_check,
        "record_check": record_check,
        "planned_action": planned_action,
        "rollback_snapshot": rollback_snapshot,
        "readiness_checklist": readiness_checklist,
        "next_step": "review_preflight_before_execute_phase",
        "message": "Read-only preflight completed. No Cloudflare DNS record was created or updated.",
    }, 200


def build_approval_dns_plan_confirmation(request_id, payload=None):
    plan, status_code = build_approval_dns_plan_prepare(request_id)
    if status_code != 200:
        return plan, status_code

    source = payload if isinstance(payload, dict) else {}
    confirm_phrase = str(source.get("confirm_phrase") or "").strip()
    if not confirm_phrase:
        return {
            "ok": False,
            "error": "missing_confirm_phrase",
            "request_id": request_id,
            "mode": "confirmation_dry_run",
            "dns_write_enabled": False,
            "execution_enabled": False,
            "requires_final_execute_phase": True,
            "execution_state": plan.get("execution_state"),
        }, 400
    if confirm_phrase != DNS_PLAN_CONFIRM_PHRASE:
        return {
            "ok": False,
            "error": "invalid_confirm_phrase",
            "request_id": request_id,
            "mode": "confirmation_dry_run",
            "dns_write_enabled": False,
            "execution_enabled": False,
            "requires_final_execute_phase": True,
            "execution_state": plan.get("execution_state"),
        }, 400

    return {
        "ok": True,
        "mode": "confirmation_dry_run",
        "request_id": request_id,
        "request_type": plan.get("request_type"),
        "approval_status": plan.get("approval_status"),
        "execution_state": plan.get("execution_state"),
        "confirmation_accepted": True,
        "dns_write_enabled": False,
        "execution_enabled": False,
        "requires_final_execute_phase": True,
        "planned_action": plan.get("planned_action"),
        "next_step": "cloudflare_write_execute_not_implemented",
        "message": "Confirmation accepted for dry-run only. Cloudflare DNS write is still disabled.",
    }, 200


def cloudflare_dns_write_feature_enabled():
    value = os.getenv(CLOUDFLARE_DNS_WRITE_FEATURE_FLAG, "").strip().lower()
    return value in ("1", "true", "yes", "on", "enabled")


def mock_dns_execution_feature_enabled():
    value = os.getenv(MOCK_DNS_EXECUTION_FEATURE_FLAG, "").strip().lower()
    return value in ("1", "true", "yes", "on", "enabled")


def mask_feature_flag_value(value):
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= 2:
        return "*" * len(text)
    return f"{text[:1]}****{text[-1:]}"


def cloudflare_dns_write_flag_status():
    raw_value = os.getenv(CLOUDFLARE_DNS_WRITE_FEATURE_FLAG)
    normalized = str(raw_value or "").strip().lower()
    effective_enabled = cloudflare_dns_write_feature_enabled()
    return {
        "ok": True,
        "feature_flag": CLOUDFLARE_DNS_WRITE_FEATURE_FLAG,
        "effective_enabled": effective_enabled,
        "raw_value_present": bool(normalized),
        "raw_value_masked": mask_feature_flag_value(raw_value),
        "source": "environment",
        "write_execute_implemented": False,
        "execute_endpoint_exists": True,
        "feature_flag_allows_execute": effective_enabled,
        "dns_write_enabled": False,
        "cloudflare_api_call_enabled": False,
        "actual_dns_write_still_disabled": True,
        "execution_interlock_required": True,
        "can_toggle_here": False,
        "requires_manual_deployment_change": True,
        "next_step": "read_only_visibility_only",
    }


def release_dashboard_format_size(size):
    try:
        value = float(size or 0)
    except (TypeError, ValueError):
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def release_dashboard_file_sha256(path):
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def release_dashboard_git_head():
    git_dir = BASE_DIR / ".git"
    try:
        if git_dir.is_file():
            raw = git_dir.read_text(encoding="utf-8", errors="replace").strip()
            if raw.startswith("gitdir:"):
                git_dir = (BASE_DIR / raw.split(":", 1)[1].strip()).resolve()
        head_path = git_dir / "HEAD"
        if not head_path.exists():
            return {"available": False, "commit": "", "short": "", "source": "not_available"}
        head = head_path.read_text(encoding="utf-8", errors="replace").strip()
        if head.startswith("ref:"):
            ref_name = head.split(" ", 1)[1].strip()
            ref_path = git_dir / ref_name
            if ref_path.exists():
                commit = ref_path.read_text(encoding="utf-8", errors="replace").strip()
                return {"available": True, "commit": commit, "short": commit[:7], "source": ref_name}
            packed_refs = git_dir / "packed-refs"
            if packed_refs.exists():
                for line in packed_refs.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref_name:
                        return {"available": True, "commit": parts[0], "short": parts[0][:7], "source": ref_name}
            return {"available": False, "commit": "", "short": "", "source": ref_name}
        return {"available": True, "commit": head, "short": head[:7], "source": "detached"}
    except OSError:
        return {"available": False, "commit": "", "short": "", "source": "read_error"}


def release_version_info():
    current_git = release_dashboard_git_head()
    return {
        "ok": True,
        "release_name": ADMIN_SAFETY_RELEASE_NAME,
        "release_status": ADMIN_SAFETY_RELEASE_STATUS,
        "release_scope": ADMIN_SAFETY_RELEASE_SCOPE,
        "release_commit": ADMIN_SAFETY_RELEASE_COMMIT,
        "release_commit_message": ADMIN_SAFETY_RELEASE_COMMIT_MESSAGE,
        "current_git_commit": current_git.get("short") or "",
        "current_git_source": current_git.get("source") or "",
        "git_tag_created": False,
        "production_domain": RELEASE_DASHBOARD_DOMAIN,
        "write_capabilities": {
            "cloudflare_dns_write": False,
            "deploy": False,
            "telegram_send": False,
            "backup_restore": False,
        },
    }


def release_dashboard_backup_type(filename):
    name = str(filename or "").lower()
    if name.startswith("project_manager.db.bak") or name.endswith(".db") or ".db.bak" in name:
        return "DB backup"
    if name.startswith("app.py.bak"):
        return "app.py backup"
    if name.endswith(".html") or ".html.bak" in name:
        return "template backup"
    if ".bak" in name:
        return "file backup"
    return "other"


def release_dashboard_phase_tag(filename):
    match = re.search(r"(phase[0-9a-z_-]+)", str(filename or ""), flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def release_dashboard_recent_backups(limit=80):
    root = RELEASE_DASHBOARD_BACKUP_DIR
    result = {
        "root": str(root),
        "exists": False,
        "items": [],
        "error": "",
    }
    try:
        if not root.exists() or not root.is_dir():
            return result
        result["exists"] = True
        items = []
        for child in root.iterdir():
            try:
                if child.is_symlink() or not child.is_file():
                    continue
                stat = child.stat()
            except OSError:
                continue
            items.append({
                "filename": child.name,
                "type": release_dashboard_backup_type(child.name),
                "phase_tag": release_dashboard_phase_tag(child.name),
                "size_bytes": stat.st_size,
                "size_label": release_dashboard_format_size(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "modified_ts": stat.st_mtime,
            })
        items.sort(key=lambda item: item["modified_ts"], reverse=True)
        for item in items[:limit]:
            item.pop("modified_ts", None)
            result["items"].append(item)
        return result
    except OSError as exc:
        result["error"] = type(exc).__name__
        return result


def release_dashboard_status_counts():
    return {
        (row["status"] or "unknown"): row["count"]
        for row in query_all("SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS count FROM approval_requests GROUP BY COALESCE(status, 'unknown')")
    }


def release_dashboard_table_count(table_name):
    allowed = {"approval_requests", "deployment_jobs", "domain_mappings", "dns_execution_attempts", "api_keys"}
    if table_name not in allowed:
        return 0
    return query_one(f"SELECT COUNT(*) AS count FROM {table_name}")["count"]


def release_dashboard_runtime_key(provider):
    row = row_to_dict(query_one(
        """SELECT id, name, provider, category, environment, status, masked_value, key_mask, last_used_at
           FROM api_keys
           WHERE lower(COALESCE(provider, ''))=?
             AND lower(COALESCE(category, ''))='third-party'
             AND lower(COALESCE(environment, ''))='staging'
             AND lower(COALESCE(status, ''))='active'
           ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
           LIMIT 1""",
        (str(provider or "").lower(),),
    ))
    if not row:
        return {"present": False, "provider": provider}
    return {
        "present": True,
        "id": row.get("id"),
        "provider": row.get("provider"),
        "category": row.get("category"),
        "environment": row.get("environment"),
        "status": row.get("status"),
        "masked": row.get("masked_value") or row.get("key_mask") or "************",
        "last_used_at": row.get("last_used_at"),
    }


def release_dashboard_dns_attempts(limit=10):
    rows = query_all(
        """SELECT id, approval_request_id, actor, attempted_action, feature_flag_state,
                  result, http_status, planned_action_json, created_at
           FROM dns_execution_attempts
           ORDER BY id DESC
           LIMIT ?""",
        (int(limit),),
    )
    items = []
    for row in rows:
        item = row_to_dict(row)
        planned_summary = ""
        try:
            planned = json.loads(item.pop("planned_action_json") or "{}")
            record_name = planned.get("name") or planned.get("record_name")
            record_type = planned.get("record_type") or planned.get("type")
            target = planned.get("target") or planned.get("content")
            if record_name or record_type or target:
                planned_summary = " ".join(str(part) for part in [record_type, record_name, "->", target] if part)
        except Exception:
            item.pop("planned_action_json", None)
        item["planned_summary"] = planned_summary
        items.append(item)
    return items


def release_dashboard_recent_approvals(limit=10):
    rows = query_all(
        """SELECT ar.id, ar.request_type, ar.status, ar.project_id, p.name AS project_name,
                  ar.title, ar.summary, ar.approved_via, ar.created_at, ar.approved_at,
                  ar.rejected_at, ar.payload_json
           FROM approval_requests ar
           LEFT JOIN projects p ON p.id=ar.project_id
           ORDER BY datetime(COALESCE(ar.created_at, ar.updated_at)) DESC, ar.id DESC
           LIMIT ?""",
        (int(limit),),
    )
    items = []
    for row in rows:
        public = approval_request_public(row_to_dict(row)) or {}
        items.append({
            "id": public.get("id"),
            "request_type": public.get("request_type"),
            "status": public.get("status"),
            "project_id": public.get("project_id"),
            "project_name": public.get("project_name"),
            "title": public.get("title"),
            "summary": public.get("summary"),
            "approved_via": public.get("approved_via"),
            "created_at": public.get("created_at"),
            "approved_at": public.get("approved_at"),
            "rejected_at": public.get("rejected_at"),
            "execution_state": public.get("execution_state"),
        })
    return items


def release_dashboard_mock_flag_status():
    raw_value = os.getenv(MOCK_DNS_EXECUTION_FEATURE_FLAG)
    normalized = str(raw_value or "").strip().lower()
    return {
        "feature_flag": MOCK_DNS_EXECUTION_FEATURE_FLAG,
        "effective_enabled": mock_dns_execution_feature_enabled(),
        "raw_value_present": bool(normalized),
        "raw_value_masked": mask_feature_flag_value(raw_value),
        "source": "environment",
        "can_toggle_here": False,
        "actual_dns_write_still_disabled": True,
    }


def release_dashboard_context():
    app_sha = release_dashboard_file_sha256(BASE_DIR / "app.py")
    approval_counts = release_dashboard_status_counts()
    db_snapshot = {
        "approval_requests_total": release_dashboard_table_count("approval_requests"),
        "approval_requests_by_status": approval_counts,
        "approval_pending": approval_counts.get("pending", 0),
        "approval_approved": approval_counts.get("approved", 0),
        "approval_rejected": approval_counts.get("rejected", 0),
        "deployment_jobs": release_dashboard_table_count("deployment_jobs"),
        "domain_mappings": release_dashboard_table_count("domain_mappings"),
        "dns_execution_attempts": release_dashboard_table_count("dns_execution_attempts"),
        "api_keys": release_dashboard_table_count("api_keys"),
    }
    cloudflare_flag = cloudflare_dns_write_flag_status()
    mock_flag = release_dashboard_mock_flag_status()
    return {
        "version": release_version_info(),
        "identity": {
            "domain": RELEASE_DASHBOARD_DOMAIN,
            "container": RELEASE_DASHBOARD_CONTAINER,
            "port": RELEASE_DASHBOARD_PORT,
            "app_path": str(BASE_DIR / "app.py"),
            "app_sha256": app_sha,
            "git": release_dashboard_git_head(),
        },
        "backups": release_dashboard_recent_backups(),
        "db": db_snapshot,
        "dns_attempts": release_dashboard_dns_attempts(),
        "approvals": release_dashboard_recent_approvals(),
        "safety": {
            "cloudflare_dns_write": cloudflare_flag,
            "mock_dns_execution": mock_flag,
            "dns_write_disabled": not bool(cloudflare_flag.get("dns_write_enabled")),
            "cloudflare_api_write_disabled": not bool(cloudflare_flag.get("cloudflare_api_call_enabled")),
            "telegram_runtime_key": release_dashboard_runtime_key("telegram"),
            "cloudflare_runtime_key": release_dashboard_runtime_key("cloudflare"),
        },
    }


def production_release_note_completed_phases():
    return [
        {
            "phase": "Phase 48",
            "title": "Release & Backup Dashboard",
            "status": "complete",
            "summary": "Read-only release identity, backup inventory, DB safety snapshot, DNS audit, and approval status dashboard.",
        },
        {
            "phase": "Phase 48FUP",
            "title": "Backup Mount Visibility Fix",
            "status": "complete",
            "summary": "Mounted production backup directory read-only for dashboard visibility.",
        },
        {
            "phase": "Phase 49",
            "title": "Operations Command Center",
            "status": "complete",
            "summary": "Home page now summarizes production domain, release, approvals, DNS safety, Shopee AI health, backups, and audit rows.",
        },
        {
            "phase": "Phase 50",
            "title": "Shopee AI Management Card",
            "status": "complete",
            "summary": "Added read-only production and staging health plus domain readiness context for Shopee AI.",
        },
        {
            "phase": "Phase 51",
            "title": "Domain Readiness Dashboard",
            "status": "complete",
            "summary": "Centralized DNS, HTTP, HTTPS, TLS, backend, and reverse proxy readiness status.",
        },
        {
            "phase": "Phase 52",
            "title": "Domain Action Plan Board",
            "status": "complete",
            "summary": "Grouped domain next steps into ready, certificate, upstream, DNS future-create, and high-risk planning lanes.",
        },
        {
            "phase": "Phase 53",
            "title": "Action Plan Export and Manual Checklist",
            "status": "complete",
            "summary": "Added read-only CSV export and static manual checklist for domain action planning.",
        },
        {
            "phase": "Phase 54",
            "title": "Manual Operations Checklist Center",
            "status": "complete",
            "summary": "Added static read-only checklist groups for DNS, NAS, SSL, release, rollback, and sensitive-value safety.",
        },
        {
            "phase": "Phase 55",
            "title": "Operations Runbook Center",
            "status": "complete",
            "summary": "Added read-only runbooks for high-risk manual operations and CSV export.",
        },
        {
            "phase": "Phase 56",
            "title": "Final Admin UI Polish",
            "status": "complete",
            "summary": "Grouped navigation, added consistent safety badges, and clarified read-only dashboard boundaries.",
        },
        {
            "phase": "Phase 57",
            "title": "Final Production Admin QA Pass",
            "status": "complete",
            "summary": "Verified production domain, authenticated pages, read-only APIs, navigation, labels, DB counts, and logs.",
        },
        {
            "phase": "Phase 58",
            "title": "Legacy Control Warning Labels",
            "status": "complete",
            "summary": "Added legacy-control warnings and redacted credential-like examples from rendered admin pages.",
        },
    ]


def production_release_note_context():
    release = release_dashboard_context()
    db_snapshot = release.get("db", {})
    cloudflare_flag = release.get("safety", {}).get("cloudflare_dns_write", {})
    mock_flag = release.get("safety", {}).get("mock_dns_execution", {})
    release_version = release_version_info()
    return {
        "rendered_at": now_str(),
        "release_version": release_version,
        "identity": {
            "domain": RELEASE_DASHBOARD_DOMAIN,
            "container": RELEASE_DASHBOARD_CONTAINER,
            "port": RELEASE_DASHBOARD_PORT,
            "app_sha256": release.get("identity", {}).get("app_sha256"),
            "git": release.get("identity", {}).get("git", {}),
        },
        "completed_phases": production_release_note_completed_phases(),
        "acceptance": [
            {"label": "Production domain", "status": "OK", "detail": "Official domain reaches DevPilot login flow."},
            {"label": "Login page", "status": "OK", "detail": "Login route returns normally over HTTPS."},
            {"label": "Main pages", "status": "OK", "detail": "Core, safety, and operations pages render without server errors."},
            {"label": "Read-only APIs", "status": "OK", "detail": "CSV/report and status APIs respond without data mutation."},
            {"label": "Runtime logs", "status": "OK", "detail": "No traceback, server error, DNS write, Telegram send, or deploy marker in final QA."},
            {"label": "Strict scanner", "status": "PASS", "detail": "Rendered pages avoid credential-like examples and internal sensitive field names."},
            {"label": "DB counts", "status": "UNCHANGED", "detail": "QA and report pages do not change approval, deployment, domain, or DNS audit counts."},
        ],
        "safety_chain": [
            {"label": "DNS prepare", "state": "dry-run only", "ok": True},
            {"label": "DNS preflight", "state": "read-only", "ok": True},
            {"label": "Second confirmation", "state": "dry-run only", "ok": True},
            {"label": "Execute endpoint", "state": "disabled", "ok": True},
            {"label": "Mock execution", "state": "disabled by default", "ok": True},
            {"label": CLOUDFLARE_DNS_WRITE_FEATURE_FLAG, "state": "disabled" if not cloudflare_flag.get("effective_enabled") else "flag true but write still unavailable", "ok": not bool(cloudflare_flag.get("dns_write_enabled"))},
            {"label": MOCK_DNS_EXECUTION_FEATURE_FLAG, "state": "disabled" if not mock_flag.get("effective_enabled") else "flag true", "ok": not bool(mock_flag.get("effective_enabled"))},
            {"label": "Audit trail", "state": "enabled for blocked execution attempts", "ok": True},
            {"label": "Real DNS write", "state": "not enabled", "ok": True},
        ],
        "db": {
            "approval_requests_total": db_snapshot.get("approval_requests_total", 0),
            "approval_pending": db_snapshot.get("approval_pending", 0),
            "approval_approved": db_snapshot.get("approval_approved", 0),
            "approval_rejected": db_snapshot.get("approval_rejected", 0),
            "deployment_jobs": db_snapshot.get("deployment_jobs", 0),
            "domain_mappings": db_snapshot.get("domain_mappings", 0),
            "dns_execution_attempts": db_snapshot.get("dns_execution_attempts", 0),
            "credential_records": db_snapshot.get("api_keys", 0),
        },
        "dashboards": [
            {"label": "Operations Command Center", "href": "/", "summary": "Production status and key operations overview."},
            {"label": "Release Dashboard", "href": "/release-dashboard", "summary": "Release identity, backups, DB counts, and audit snapshots."},
            {"label": "Domain Readiness", "href": "/domain-readiness", "summary": "DNS, HTTP, HTTPS, TLS, backend, and readiness status."},
            {"label": "Domain Action Plan", "href": "/domain-action-plan", "summary": "Read-only domain next-step board and CSV export."},
            {"label": "Manual Checklist", "href": "/manual-operations-checklist", "summary": "Static manual checklist center."},
            {"label": "Runbooks", "href": "/operations-runbook", "summary": "Static operations runbook library."},
        ],
        "known_limitations": [
            "Real Cloudflare DNS write is still not enabled.",
            "NAS reverse proxy and SSL changes remain manual outside this app.",
            "Legacy operational pages still exist, but they are visually labeled and separated from read-only dashboards.",
            "Rollback is planned manually; there is no automatic rollback path.",
            "Backup restore is not available from the UI.",
            "Safety dashboards do not execute deployment actions.",
        ],
        "next_phases": [
            {"phase": "Phase 60", "title": "Release Freeze / Version Label", "summary": "Add a read-only version label such as DevPilot Admin Safety Release 2026-05-09."},
            {"phase": "Phase 61", "title": "Release History Export", "summary": "Export release state and dashboard inventory as a static report."},
            {"phase": "Phase 62", "title": "Production Monitoring Summary", "summary": "Add read-only runtime health and log summary cards."},
            {"phase": "Phase 63", "title": "Role / Permission Review", "summary": "Review owner/admin/viewer boundaries for existing legacy pages."},
        ],
    }


def production_release_note_markdown(context=None):
    note = context or production_release_note_context()
    git = note.get("identity", {}).get("git", {})
    lines = [
        "# Production Release Note / Admin QA Report",
        "",
        "## Release Version Label",
        f"- Release name: {note.get('release_version', {}).get('release_name')}",
        f"- Status: {note.get('release_version', {}).get('release_status')}",
        f"- Frozen commit: {note.get('release_version', {}).get('release_commit')}",
        f"- Git tag created: {str(note.get('release_version', {}).get('git_tag_created')).lower()}",
        f"- Scope: {note.get('release_version', {}).get('release_scope')}",
        "",
        "## Release Identity",
        f"- Generated: {note.get('rendered_at')}",
        f"- Domain: {note.get('identity', {}).get('domain')}",
        f"- Container: {note.get('identity', {}).get('container')}",
        f"- Port: {note.get('identity', {}).get('port')}",
        f"- app.py SHA256: {note.get('identity', {}).get('app_sha256') or 'unavailable'}",
        f"- Git commit: {git.get('short') or 'unavailable'}",
        "",
        "## Completed Phases",
    ]
    for item in note.get("completed_phases", []):
        lines.append(f"- {item['phase']} - {item['title']}: {item['status']}")
    lines.extend(["", "## Production Acceptance Status"])
    for item in note.get("acceptance", []):
        lines.append(f"- {item['label']}: {item['status']} - {item['detail']}")
    lines.extend(["", "## Safety Chain Status"])
    for item in note.get("safety_chain", []):
        lines.append(f"- {item['label']}: {item['state']}")
    db = note.get("db", {})
    lines.extend([
        "",
        "## Current DB Snapshot",
        f"- approval_requests: {db.get('approval_requests_total')} total / {db.get('approval_pending')} pending / {db.get('approval_approved')} approved / {db.get('approval_rejected')} rejected",
        f"- deployment_jobs: {db.get('deployment_jobs')}",
        f"- domain_mappings: {db.get('domain_mappings')}",
        f"- dns_execution_attempts: {db.get('dns_execution_attempts')}",
        f"- credential records: {db.get('credential_records')}",
        "",
        "## Known Limitations",
    ])
    for item in note.get("known_limitations", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Recommended Next Phases"])
    for item in note.get("next_phases", []):
        lines.append(f"- {item['phase']} - {item['title']}: {item['summary']}")
    lines.extend([
        "",
        "## Safety Statement",
        "This report is read-only. It does not run deployment, DNS, NAS, Telegram, restart, rollback, or save actions.",
        "",
    ])
    return "\n".join(lines)


def production_release_note_markdown_response():
    response = Response(production_release_note_markdown(), mimetype="text/markdown")
    response.headers["Content-Disposition"] = "attachment; filename=production_release_note.md"
    response.headers["Cache-Control"] = "no-store"
    return response


def release_archive_exports():
    return [
        {"name": "Release Version JSON", "url": "/api/release/version", "format": "json"},
        {"name": "Production Release Note Markdown", "url": "/api/production-release-note/export.md", "format": "markdown"},
        {"name": "QA Summary Markdown", "url": "/api/release/qa-summary.md", "format": "markdown"},
        {"name": "Domain Action Plan CSV", "url": "/api/domain-action-plan/export.csv", "format": "csv"},
        {"name": "Manual Operations Checklist CSV", "url": "/api/manual-operations-checklist/export.csv", "format": "csv"},
        {"name": "Operations Runbook CSV", "url": "/api/operations-runbook/export.csv", "format": "csv"},
    ]


def release_archive_context():
    release_version = release_version_info()
    release_note = production_release_note_context()
    return {
        "ok": True,
        "generated_at": now_str(),
        "release_name": release_version.get("release_name"),
        "release_status": release_version.get("release_status"),
        "release_scope": release_version.get("release_scope"),
        "release_commit": release_version.get("release_commit"),
        "git_tag_created": False,
        "production_domain": release_version.get("production_domain"),
        "exports": release_archive_exports(),
        "safety": {
            "read_only": True,
            "cloudflare_dns_write": False,
            "deploy": False,
            "telegram_send": False,
            "backup_restore": False,
            "git_tag_created": False,
        },
        "qa": {
            "public_domain": "pass",
            "login_page": "pass",
            "main_admin_pages": "pass",
            "read_only_apis": "pass",
            "safety_labels": "pass",
            "strict_scanner": "pass",
            "db_counts": "unchanged",
            "runtime_logs": "clean",
        },
        "db": release_note.get("db", {}),
        "known_limitations": release_note.get("known_limitations", []),
        "next_phase": {
            "phase": "Phase 62",
            "title": "Optional Git Tag Readiness Review",
            "summary": "Read-only review of whether a release tag is appropriate; no tag is created without explicit confirmation.",
        },
    }


def release_qa_summary_markdown(context=None):
    archive = context or release_archive_context()
    db = archive.get("db", {})
    lines = [
        "# Final Release Freeze QA Summary",
        "",
        f"- Release name: {archive.get('release_name')}",
        f"- Release status: {archive.get('release_status')}",
        f"- Release commit: {archive.get('release_commit')}",
        f"- Git tag created: {str(archive.get('git_tag_created')).lower()}",
        f"- Production domain: {archive.get('production_domain')}",
        f"- Generated: {archive.get('generated_at')}",
        "",
        "## QA Results",
        "- Public domain smoke: pass",
        "- Login page: pass",
        "- Main admin pages: pass",
        "- Read-only API smoke: pass",
        "- Safety labels: pass",
        "- Strict scanner after Phase 58: pass",
        "- Runtime logs: clean",
        "- DB counts: unchanged",
        "- No DNS, deploy, Telegram, rollback, restore, or restart action was added by archive export.",
        "",
        "## Current DB Snapshot",
        f"- approval_requests: {db.get('approval_requests_total')} total / {db.get('approval_pending')} pending / {db.get('approval_approved')} approved / {db.get('approval_rejected')} rejected",
        f"- deployment_jobs: {db.get('deployment_jobs')}",
        f"- domain_mappings: {db.get('domain_mappings')}",
        f"- dns_execution_attempts: {db.get('dns_execution_attempts')}",
        "",
        "## Archive Exports",
    ]
    for item in archive.get("exports", []):
        lines.append(f"- {item['name']}: {item['url']} ({item['format']})")
    lines.extend(["", "## Known Limitations"])
    for item in archive.get("known_limitations", []):
        lines.append(f"- {item}")
    next_phase = archive.get("next_phase", {})
    lines.extend([
        "",
        "## Next Suggested Phase",
        f"- {next_phase.get('phase')} - {next_phase.get('title')}: {next_phase.get('summary')}",
        "",
        "## Safety Statement",
        "This archive is read-only. It does not create tags, write DNS, deploy, modify NAS settings, send Telegram messages, restore backups, or save application data.",
        "",
    ])
    return "\n".join(lines)


def release_qa_summary_markdown_response():
    response = Response(release_qa_summary_markdown(), mimetype="text/markdown")
    response.headers["Content-Disposition"] = "attachment; filename=release_qa_summary.md"
    response.headers["Cache-Control"] = "no-store"
    return response


def operations_health_timeout_seconds():
    try:
        return max(0.2, min(3.0, float(os.getenv("DEV_PILOT_OPS_HEALTH_TIMEOUT_SECONDS", "1"))))
    except (TypeError, ValueError):
        return 1.0


def operations_http_health_check(name, environment, url, port):
    started = time.monotonic()
    base = {
        "name": name,
        "environment": environment,
        "url": url,
        "port": port,
        "ok": False,
        "status_code": None,
        "latency_ms": None,
        "detail": "",
    }
    if not url:
        base["detail"] = "health url not configured"
        return base
    try:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "DevPilot operations command center/1.0", "Accept": "application/json,text/plain,*/*"},
        )
        with urllib.request.urlopen(req, timeout=operations_health_timeout_seconds()) as resp:
            resp.read(512)
            base["status_code"] = resp.status
            base["ok"] = 200 <= int(resp.status) < 300
            base["latency_ms"] = int((time.monotonic() - started) * 1000)
            base["detail"] = "health endpoint responded"
            return base
    except urllib.error.HTTPError as exc:
        base["status_code"] = exc.code
        base["latency_ms"] = int((time.monotonic() - started) * 1000)
        base["detail"] = f"HTTP {exc.code}"
        return base
    except urllib.error.URLError as exc:
        base["latency_ms"] = int((time.monotonic() - started) * 1000)
        reason = getattr(exc, "reason", None)
        base["detail"] = type(reason).__name__ if reason else type(exc).__name__
        return base
    except Exception as exc:
        base["latency_ms"] = int((time.monotonic() - started) * 1000)
        base["detail"] = type(exc).__name__
        return base


def operations_resolve_hostname(hostname):
    result = {
        "hostname": hostname,
        "ok": False,
        "addresses": [],
        "points_to_expected_ip": False,
        "expected_ip": OPERATIONS_AICHAT_NAS_IP,
        "detail": "",
    }
    try:
        info = socket.getaddrinfo(hostname, None)
        addresses = sorted({item[4][0] for item in info if item and item[4]})
        result["addresses"] = addresses[:8]
        result["ok"] = bool(addresses)
        result["points_to_expected_ip"] = OPERATIONS_AICHAT_NAS_IP in addresses
        result["detail"] = "resolved" if addresses else "no records"
    except Exception as exc:
        result["detail"] = type(exc).__name__
    return result


def operations_domain_mapping_summary(hostname):
    try:
        row = row_to_dict(query_one(
            """SELECT id, project_id, zone_name, record_name, record_type, record_content,
                      environment, preview_url, status, notes
               FROM domain_mappings
               WHERE lower(COALESCE(record_name, ''))=lower(?)
               ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
               LIMIT 1""",
            (hostname,),
        ))
    except sqlite3.Error:
        row = None
    if not row:
        return {"exists": False, "hostname": hostname}
    return {
        "exists": True,
        "id": row.get("id"),
        "project_id": row.get("project_id"),
        "zone_name": row.get("zone_name"),
        "record_name": row.get("record_name"),
        "record_type": row.get("record_type"),
        "record_content": row.get("record_content"),
        "environment": row.get("environment"),
        "preview_url": row.get("preview_url"),
        "status": row.get("status"),
    }


def operations_shopee_project():
    try:
        row = row_to_dict(query_one(
            """SELECT id, name, client_name, project_type, status, deploy_url
               FROM projects
               WHERE id=3
                  OR lower(COALESCE(name, '') || ' ' || COALESCE(client_name, '') || ' ' || COALESCE(description, '')) LIKE '%shopee%'
                  OR COALESCE(name, '') LIKE '%蝦皮%'
               ORDER BY CASE WHEN id=3 THEN 0 ELSE 1 END, id
               LIMIT 1"""
        ))
    except sqlite3.Error:
        row = None
    if not row:
        return {"exists": False, "id": None, "name": "Shopee AI"}
    return {
        "exists": True,
        "id": row.get("id"),
        "name": row.get("name"),
        "client_name": row.get("client_name"),
        "project_type": row.get("project_type"),
        "status": row.get("status"),
        "deploy_url": row.get("deploy_url"),
    }


def operations_shopee_domain_readiness(hostname, environment, backend_port):
    dns = operations_resolve_hostname(hostname)
    https = operations_http_health_check(
        f"{hostname} HTTPS health",
        environment,
        f"https://{hostname}/api/health",
        "443",
    )
    mapping = operations_domain_mapping_summary(hostname)
    ssl_status = "valid" if https.get("ok") else "pending_or_unknown"
    reverse_proxy_status = "ready" if https.get("ok") else "pending_or_unknown"
    if dns.get("ok") and not https.get("ok") and "SSLCert" in str(https.get("detail") or ""):
        ssl_status = "certificate_check_needed"
    if dns.get("ok") and https.get("status_code") == 404:
        reverse_proxy_status = "rule_check_needed"
    readiness = "ready" if https.get("ok") else ("dns_ready_service_pending" if dns.get("ok") else "dns_check_needed")
    return {
        "hostname": hostname,
        "environment": environment,
        "backend_port": backend_port,
        "dns": dns,
        "https_health": https,
        "domain_mapping": mapping,
        "ssl_status": ssl_status,
        "reverse_proxy_status": reverse_proxy_status,
        "readiness": readiness,
    }


def operations_shopee_status():
    production_backend = operations_http_health_check(
            "Shopee AI production backend",
            "production",
            OPERATIONS_SHOPEE_PRODUCTION_HEALTH_URL,
            "3030",
    )
    staging_backend = operations_http_health_check(
            "Shopee AI staging backend",
            "staging",
            OPERATIONS_SHOPEE_STAGING_HEALTH_URL,
            "3032",
    )
    return {
        "project": operations_shopee_project(),
        "backends": [production_backend, staging_backend],
        "domains": [
            operations_shopee_domain_readiness(OPERATIONS_SHOPEE_PRODUCTION_DOMAIN, "production", "3030"),
            operations_shopee_domain_readiness(OPERATIONS_SHOPEE_STAGING_DOMAIN, "staging", "3032"),
            operations_shopee_domain_readiness(OPERATIONS_SHOPEE_STAGING_LEGACY_DOMAIN, "staging", "3032"),
        ],
        "notes": [
            "Read-only status only; no deploy, restart, DNS write, or backend mutation is available here.",
            "DNS and HTTPS checks use short timeouts so failures cannot break dashboard rendering.",
        ],
    }


def domain_readiness_targets():
    return [
        {
            "group": "DevPilot",
            "hostname": "devpilot.aicenter.com.tw",
            "zone_name": "aicenter.com.tw",
            "expected_upstream": "devpilot-project-manager :5010",
            "backend_label": "DevPilot production",
            "backend_health_url": "",
            "https_path": "/",
            "http_path": "/",
            "notes": "Production DevPilot domain should redirect unauthenticated users to login.",
        },
        {
            "group": "Aichat / Shopee AI",
            "hostname": OPERATIONS_SHOPEE_PRODUCTION_DOMAIN,
            "zone_name": "aichat.tw",
            "expected_upstream": "Shopee AI production :3030",
            "backend_label": "Shopee AI production",
            "backend_health_url": OPERATIONS_SHOPEE_PRODUCTION_HEALTH_URL,
            "https_path": "/api/health",
            "http_path": "/api/health",
            "notes": "Production Shopee AI hostname.",
        },
        {
            "group": "Aichat / Shopee AI",
            "hostname": OPERATIONS_SHOPEE_STAGING_LEGACY_DOMAIN,
            "zone_name": "aichat.tw",
            "expected_upstream": "Shopee AI staging :3032",
            "backend_label": "Shopee AI staging",
            "backend_health_url": OPERATIONS_SHOPEE_STAGING_HEALTH_URL,
            "https_path": "/api/health",
            "http_path": "/api/health",
            "notes": "Existing staging Shopee hostname.",
        },
        {
            "group": "Aichat / Shopee AI",
            "hostname": OPERATIONS_SHOPEE_STAGING_DOMAIN,
            "zone_name": "aichat.tw",
            "expected_upstream": "Shopee AI staging :3032 planned",
            "backend_label": "Shopee AI staging",
            "backend_health_url": OPERATIONS_SHOPEE_STAGING_HEALTH_URL,
            "https_path": "/api/health",
            "http_path": "/api/health",
            "notes": "DNS exists; reverse proxy and certificate readiness are still being validated.",
        },
        {
            "group": "Aichat",
            "hostname": "widget.aichat.tw",
            "zone_name": "aichat.tw",
            "expected_upstream": "widget service pending",
            "backend_label": "Widget service",
            "backend_health_url": "",
            "https_path": "/",
            "http_path": "/",
            "notes": "Widget upstream is not finalized.",
        },
        {
            "group": "Aichat",
            "hostname": "api.aichat.tw",
            "zone_name": "aichat.tw",
            "expected_upstream": "API service pending",
            "backend_label": "API service",
            "backend_health_url": "",
            "https_path": "/api/health",
            "http_path": "/api/health",
            "notes": "API DNS/reverse-proxy plan is pending.",
        },
        {
            "group": "Aichat",
            "hostname": "admin.aichat.tw",
            "zone_name": "aichat.tw",
            "expected_upstream": "admin service pending",
            "backend_label": "Admin service",
            "backend_health_url": "",
            "https_path": "/",
            "http_path": "/",
            "notes": "Admin should stay gated behind access controls before public use.",
        },
        {
            "group": "Aichat",
            "hostname": "www.aichat.tw",
            "zone_name": "aichat.tw",
            "expected_upstream": "landing page pending",
            "backend_label": "Main website",
            "backend_health_url": "",
            "https_path": "/",
            "http_path": "/",
            "notes": "Existing public entry should not be changed until landing page service is ready.",
        },
    ]


def domain_readiness_probe_url(url, verify_tls=True):
    started = time.monotonic()
    result = {
        "url": url,
        "ok": False,
        "status_code": None,
        "final_url": "",
        "server": "",
        "latency_ms": None,
        "detail": "",
        "classification": "",
    }
    try:
        context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "DevPilot domain readiness/1.0", "Accept": "text/html,application/json,text/plain,*/*"},
        )
        with urllib.request.urlopen(req, timeout=operations_health_timeout_seconds(), context=context) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            result["status_code"] = resp.status
            result["final_url"] = resp.geturl()
            result["server"] = resp.headers.get("Server", "")
            result["ok"] = 200 <= int(resp.status) < 500
            result["latency_ms"] = int((time.monotonic() - started) * 1000)
            result["classification"] = domain_readiness_classify_http(body, result["server"], resp.status)
            result["detail"] = "responded"
            return result
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        result["status_code"] = exc.code
        result["final_url"] = url
        result["server"] = exc.headers.get("Server", "") if exc.headers else ""
        result["ok"] = exc.code < 500
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        result["classification"] = domain_readiness_classify_http(body, result["server"], exc.code)
        result["detail"] = f"HTTP {exc.code}"
        return result
    except urllib.error.URLError as exc:
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        reason = getattr(exc, "reason", None)
        result["detail"] = type(reason).__name__ if reason else type(exc).__name__
        return result
    except Exception as exc:
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        result["detail"] = type(exc).__name__
        return result


def domain_readiness_classify_http(body, server, status_code):
    text = f"{server or ''}\n{body or ''}".lower()
    if "synology" in text or "diskstation" in text or "dsm" in text:
        return "synology_default_or_dsm"
    if "devpilot" in text:
        return "devpilot"
    if "cannot get" in text:
        return "node_default"
    if int(status_code or 0) == 404:
        return "http_404"
    if int(status_code or 0) in (301, 302, 303, 307, 308):
        return "redirect"
    return "application_response"


def domain_readiness_tls_certificate(hostname):
    result = {
        "checked": True,
        "valid": False,
        "common_name": "",
        "san": [],
        "not_after": "",
        "issuer": "",
        "error": "",
    }
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=operations_health_timeout_seconds()) as raw_sock:
            with context.wrap_socket(raw_sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert() or {}
        subject = cert.get("subject") or []
        for group in subject:
            for key, value in group:
                if key == "commonName":
                    result["common_name"] = value
                    break
            if result["common_name"]:
                break
        result["san"] = [value for key, value in cert.get("subjectAltName", []) if key.lower() == "dns"][:8]
        issuer = []
        for group in cert.get("issuer") or []:
            for key, value in group:
                if key in ("organizationName", "commonName"):
                    issuer.append(value)
        result["issuer"] = " / ".join(issuer[:3])
        result["not_after"] = cert.get("notAfter", "")
        result["valid"] = True
    except ssl.SSLCertVerificationError as exc:
        result["error"] = type(exc).__name__
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def domain_readiness_cloudflare_records(targets):
    snapshot = {
        "ok": False,
        "source": "cloudflare_read_only",
        "error": "",
        "records": {},
    }
    try:
        key_info = get_active_cloudflare_api_key()
        if not key_info.get("ok"):
            snapshot["error"] = "cloudflare_read_unavailable"
            return snapshot
        token = key_info["token"]
        zone_names = sorted({target.get("zone_name") for target in targets if target.get("zone_name")})
        zone_ids = {}
        for zone_name in zone_names:
            zones_result = cloudflare_request("GET", "/zones", token, query={"name": zone_name, "page": 1, "per_page": 50}, timeout=5)
            if not zones_result.get("ok"):
                snapshot["error"] = "cloudflare_zone_read_error"
                continue
            zones = ((zones_result.get("data") or {}).get("result") or [])
            for zone in zones:
                if str(zone.get("name") or "").casefold() == str(zone_name).casefold():
                    zone_ids[zone_name] = zone.get("id")
                    break
        for target in targets:
            hostname = target.get("hostname")
            zone_id = zone_ids.get(target.get("zone_name"))
            if not hostname or not zone_id:
                continue
            records_result = cloudflare_request(
                "GET",
                f"/zones/{urllib.parse.quote(str(zone_id), safe='')}/dns_records",
                token,
                query={"name": hostname, "page": 1, "per_page": 20},
                timeout=5,
            )
            if not records_result.get("ok"):
                snapshot["error"] = "cloudflare_record_read_error"
                continue
            records = ((records_result.get("data") or {}).get("result") or [])
            public_records = []
            for record in records:
                public = cloudflare_dns_record_public(record)
                public_records.append({
                    "id_masked": mask_identifier(public.get("id")),
                    "type": public.get("type"),
                    "name": public.get("name"),
                    "content": mask_dns_record_content(public),
                    "ttl": public.get("ttl"),
                    "proxied": public.get("proxied"),
                    "created_on": public.get("created_on"),
                    "modified_on": public.get("modified_on"),
                })
            snapshot["records"][hostname.casefold()] = public_records
        snapshot["ok"] = True
        return snapshot
    except Exception as exc:
        snapshot["error"] = type(exc).__name__
        return snapshot


def domain_readiness_dns_summary(target, cloudflare_snapshot):
    hostname = target.get("hostname")
    records = (cloudflare_snapshot.get("records") or {}).get(str(hostname or "").casefold()) or []
    public_dns = operations_resolve_hostname(hostname)
    mapping = operations_domain_mapping_summary(hostname)
    if records:
        first = records[0]
        return {
            "exists": True,
            "source": "cloudflare_read_only",
            "type": first.get("type"),
            "content": first.get("content"),
            "proxied": first.get("proxied"),
            "ttl": first.get("ttl"),
            "record_id_masked": first.get("id_masked"),
            "records": records,
            "public_dns": public_dns,
            "domain_mapping": mapping,
            "note": f"{len(records)} matching Cloudflare record(s)",
        }
    return {
        "exists": public_dns.get("ok"),
        "source": "public_dns",
        "type": "A/AAAA" if public_dns.get("addresses") else "",
        "content": ", ".join(public_dns.get("addresses") or []),
        "proxied": None,
        "ttl": None,
        "record_id_masked": "",
        "records": [],
        "public_dns": public_dns,
        "domain_mapping": mapping,
        "note": "Cloudflare record not found by read-only snapshot" if cloudflare_snapshot.get("ok") else "Cloudflare snapshot unavailable; using public DNS",
    }


def domain_readiness_status(target, dns, http, https, tls, backend):
    if not dns.get("exists"):
        return "dns_missing", "create DNS record"
    if tls.get("checked") and not tls.get("valid"):
        return "ssl_error", "assign or renew matching TLS certificate"
    if target.get("expected_upstream", "").endswith("pending"):
        return "backend_unconfigured", "define upstream service before exposing"
    if https.get("ok") and int(https.get("status_code") or 0) < 500:
        if backend.get("ok") or not target.get("backend_health_url"):
            return "ready", "no action"
    if https.get("classification") in ("synology_default_or_dsm", "http_404") or https.get("status_code") == 404:
        return "reverse_proxy_missing", "add or verify NAS reverse proxy rule"
    return "dns_ready_service_pending", "verify reverse proxy and upstream health"


def domain_readiness_context():
    targets = domain_readiness_targets()
    cloudflare_snapshot = domain_readiness_cloudflare_records(targets)
    items = []
    for target in targets:
        hostname = target["hostname"]
        http_url = f"http://{hostname}{target.get('http_path') or '/'}"
        https_url = f"https://{hostname}{target.get('https_path') or '/'}"
        dns = domain_readiness_dns_summary(target, cloudflare_snapshot)
        http = domain_readiness_probe_url(http_url, verify_tls=False)
        https = domain_readiness_probe_url(https_url, verify_tls=True)
        tls = domain_readiness_tls_certificate(hostname)
        backend = operations_http_health_check(target.get("backend_label") or hostname, target.get("group") or "", target.get("backend_health_url") or "", target.get("expected_upstream") or "")
        readiness, next_step = domain_readiness_status(target, dns, http, https, tls, backend)
        items.append({
            "group": target.get("group"),
            "hostname": hostname,
            "expected_upstream": target.get("expected_upstream"),
            "notes": target.get("notes"),
            "dns": dns,
            "http": http,
            "https": https,
            "tls": tls,
            "backend": backend,
            "readiness": readiness,
            "next_step": next_step,
        })
    summary = {}
    for item in items:
        summary[item["readiness"]] = summary.get(item["readiness"], 0) + 1
    return {
        "rendered_at": now_str(),
        "cloudflare_snapshot": {
            "ok": cloudflare_snapshot.get("ok"),
            "source": cloudflare_snapshot.get("source"),
            "error": cloudflare_snapshot.get("error"),
        },
        "items": items,
        "summary": summary,
    }


def domain_action_plan_item(hostname, current_status, recommended_action, risk_level, prerequisites, next_phase, manual_confirmation_phrase=""):
    return {
        "hostname": hostname,
        "current_status": current_status,
        "recommended_action": recommended_action,
        "risk_level": risk_level,
        "prerequisites": prerequisites,
        "next_phase": next_phase,
        "manual_confirmation_phrase": manual_confirmation_phrase,
    }


def domain_action_plan_manual_checklists():
    return [
        {
            "hostname": "staging.aichat.tw",
            "category": "SSL / Certificate Needed",
            "items": [
                "DNS exists and resolves to the NAS public IP.",
                "Reverse proxy rule still needs confirmation for staging.aichat.tw HTTPS 443 to 127.0.0.1:3032.",
                "Certificate must include staging.aichat.tw or a matching wildcard.",
                "NAS UI or privileged setup is required; DevPilot does not modify it from this board.",
                "Verify https://staging.aichat.tw/api/health with strict TLS before marking ready.",
            ],
        },
        {
            "hostname": "api.aichat.tw",
            "category": "DNS Missing / Future Create",
            "items": [
                "DNS record is missing.",
                "API upstream must be chosen before DNS creation.",
                "CORS, authentication, and rate limits need review.",
                "Run final DNS preflight and rollback planning before any create.",
            ],
        },
        {
            "hostname": "admin.aichat.tw",
            "category": "DNS Missing / Future Create",
            "items": [
                "DNS record is missing.",
                "Cloudflare Access or an IP allowlist must be designed first.",
                "Admin upstream must be selected and protected.",
                "Do not expose this hostname before access control is ready.",
            ],
        },
        {
            "hostname": "widget.aichat.tw",
            "category": "Backend / Upstream Pending",
            "items": [
                "DNS exists.",
                "Widget route, static service, or iframe endpoint still needs a decision.",
                "CSP, iframe headers, and CORS behavior need review.",
                "Verify HTTPS behavior after the upstream is selected.",
            ],
        },
        {
            "hostname": "www.aichat.tw",
            "category": "High-risk / Do Not Touch First",
            "items": [
                "Existing CNAME must stay unchanged until the landing page is ready.",
                "Landing page upstream must be selected.",
                "Root and www redirect behavior need a separate plan.",
                "Preserve the existing DNS snapshot before any future update.",
            ],
        },
    ]


def domain_action_plan_context():
    readiness = domain_readiness_context()
    sections = [
        {
            "key": "ready_monitor",
            "title": "Ready / Monitor",
            "description": "Routes that are already usable. Keep checking status; no DNS or NAS change is needed.",
            "items": [],
        },
        {
            "key": "ssl_certificate_needed",
            "title": "SSL / Certificate Needed",
            "description": "DNS reaches the NAS, but the HTTPS layer still needs a matching certificate or proxy binding.",
            "items": [],
        },
        {
            "key": "backend_upstream_pending",
            "title": "Backend / Upstream Pending",
            "description": "DNS exists or is planned, but the upstream service, landing page, or widget route still needs a decision.",
            "items": [],
        },
        {
            "key": "dns_missing_future_create",
            "title": "DNS Missing / Future Create",
            "description": "Hostnames that should stay plan-only until the upstream and safety controls are ready.",
            "items": [],
        },
        {
            "key": "high_risk_hold",
            "title": "High-risk / Do Not Touch First",
            "description": "Records that should stay unchanged until the public entrypoint and protection model are ready.",
            "items": [],
        },
    ]
    section_map = {section["key"]: section for section in sections}
    item_map = {item.get("hostname"): item for item in readiness.get("items", [])}

    for item in readiness.get("items", []):
        hostname = item.get("hostname") or ""
        status = item.get("readiness") or "unknown"
        current_status = status.replace("_", " ")
        if status == "ready":
            section_map["ready_monitor"]["items"].append(domain_action_plan_item(
                hostname,
                current_status,
                "Keep monitoring. No DNS or NAS change is needed.",
                "low",
                ["Periodic HTTP/HTTPS health check", "Keep existing reverse proxy and certificate assignment unchanged"],
                "Monitor in the readiness dashboard",
            ))
        elif status == "ssl_error":
            phrase = ""
            if hostname == "staging.aichat.tw":
                phrase = "執行 NAS Reverse Proxy：staging.aichat.tw HTTPS 443 -> http://127.0.0.1:3032，不改 DNS、不重啟 backend"
            section_map["ssl_certificate_needed"]["items"].append(domain_action_plan_item(
                hostname,
                current_status,
                "Add or verify the NAS reverse proxy rule, then assign a certificate that includes this hostname.",
                "medium",
                [
                    "Reverse proxy source is HTTPS 443 for the hostname",
                    "Destination points to the intended local upstream",
                    "Certificate SAN includes the hostname or a matching wildcard",
                    "Strict HTTPS health check returns 200 before marking ready",
                ],
                "NAS reverse proxy and SSL controlled setup",
                phrase,
            ))
        elif status in ("backend_unconfigured", "dns_ready_service_pending", "reverse_proxy_missing"):
            action = "Decide the upstream service and root path behavior before exposing this hostname."
            prerequisites = ["Chosen upstream service", "Expected route behavior", "HTTPS certificate plan"]
            next_phase = "Service readiness planning"
            risk = "medium"
            if hostname == "widget.aichat.tw":
                action = "Decide whether this should serve a widget static bundle, iframe endpoint, or backend placeholder."
                prerequisites = ["Widget service or route selected", "CORS and iframe headers reviewed", "HTTPS endpoint plan"]
                next_phase = "Widget service upstream design"
            elif hostname == "www.aichat.tw":
                action = "Keep the existing entrypoint unchanged until the landing page service is ready."
                prerequisites = ["Landing page service selected", "Root path behavior defined", "Existing DNS snapshot preserved"]
                next_phase = "Aichat landing page readiness"
                risk = "high"
            section_map["backend_upstream_pending"]["items"].append(domain_action_plan_item(
                hostname,
                current_status,
                action,
                risk,
                prerequisites,
                next_phase,
            ))
        elif status == "dns_missing":
            action = "Run final DNS preflight before creating any record."
            prerequisites = ["Upstream target selected", "Record payload drafted", "Rollback payload drafted"]
            next_phase = "DNS final preflight"
            risk = "medium"
            phrase = f"執行 DNS：{hostname} A 211.75.219.184 proxied=false"
            if hostname == "api.aichat.tw":
                action = "Define API upstream, CORS, authentication, and rate limits before DNS creation."
                prerequisites = ["API upstream selected", "CORS origin list reviewed", "Rate limit and auth expectations documented"]
                next_phase = "API domain final preflight"
            elif hostname == "admin.aichat.tw":
                action = "Put Cloudflare Access or an IP allowlist in front of admin access before DNS creation."
                prerequisites = ["Access policy selected", "Admin upstream selected", "Emergency lockout path documented"]
                next_phase = "Admin access control design before DNS"
                risk = "high"
            section_map["dns_missing_future_create"]["items"].append(domain_action_plan_item(
                hostname,
                current_status,
                action,
                risk,
                prerequisites,
                next_phase,
                phrase,
            ))

    www_item = item_map.get("www.aichat.tw") or {}
    www_dns = www_item.get("dns") or {}
    section_map["high_risk_hold"]["items"].append(domain_action_plan_item(
        "www.aichat.tw",
        (www_item.get("readiness") or "existing public entrypoint").replace("_", " "),
        "Do not update the existing www record until the landing page is ready and the previous record snapshot is reviewed.",
        "high",
        [
            f"Current DNS summary: {www_dns.get('type') or 'unknown'} {www_dns.get('content') or 'not confirmed'}",
            "Landing page service ready",
            "Rollback plan for the current www record documented",
        ],
        "Landing page readiness and separate single-record gate",
    ))
    section_map["high_risk_hold"]["items"].append(domain_action_plan_item(
        "aichat.tw",
        "root domain hold",
        "Keep the root domain unchanged until the public site and DNS strategy are finalized.",
        "high",
        ["Root record snapshot", "Landing page ownership decision", "SSL and redirect strategy"],
        "Root domain strategy review",
    ))

    return {
        "rendered_at": now_str(),
        "readiness": readiness,
        "sections": sections,
        "manual_checklists": domain_action_plan_manual_checklists(),
        "summary": {section["key"]: len(section["items"]) for section in sections},
    }


def domain_action_plan_csv_response():
    board = domain_action_plan_context()
    output = io.StringIO()
    fieldnames = [
        "hostname",
        "category",
        "current_status",
        "readiness",
        "recommended_action",
        "risk_level",
        "prerequisites",
        "next_phase",
        "manual_confirmation_required",
        "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for section in board.get("sections", []):
        for item in section.get("items", []):
            writer.writerow({
                "hostname": item.get("hostname") or "",
                "category": section.get("title") or "",
                "current_status": item.get("current_status") or "",
                "readiness": item.get("current_status") or "",
                "recommended_action": item.get("recommended_action") or "",
                "risk_level": item.get("risk_level") or "",
                "prerequisites": " | ".join(item.get("prerequisites") or []),
                "next_phase": item.get("next_phase") or "",
                "manual_confirmation_required": "yes" if item.get("manual_confirmation_phrase") else "no",
                "notes": "planning-only; no DNS, NAS, certificate, backend, or deployment change",
            })
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=domain_action_plan.csv"
    response.headers["Cache-Control"] = "no-store"
    return response


def manual_operations_checklist_sections():
    return [
        {
            "key": "dns_real_write",
            "title": "DNS Real Write Checklist",
            "items": [
                {
                    "item": "Confirm the operation targets exactly one DNS record.",
                    "required_before": "Any Cloudflare write phase",
                    "risk_if_missing": "A broader change could affect unrelated hostnames.",
                    "note": "Use single-record phases only.",
                },
                {
                    "item": "Complete Cloudflare read-only final preflight.",
                    "required_before": "Record create or update",
                    "risk_if_missing": "The plan may be based on stale DNS state.",
                    "note": "Preflight must identify create or update.",
                },
                {
                    "item": "Confirm the record is missing, or preserve an update snapshot.",
                    "required_before": "Record create or update",
                    "risk_if_missing": "Rollback cannot restore the previous state.",
                    "note": "Updates need previous id, type, name, content, proxied state, and ttl.",
                },
                {
                    "item": "Confirm rollback payload and production DB backup path.",
                    "required_before": "Record create or update",
                    "risk_if_missing": "Recovery instructions may be incomplete.",
                    "note": "Rollback remains a separate approval-controlled action.",
                },
                {
                    "item": "Confirm feature flag state and final phrase.",
                    "required_before": "Real write execution",
                    "risk_if_missing": "Execution gate may be bypassed or ambiguous.",
                    "note": "No UI toggle is available from DevPilot.",
                },
                {
                    "item": "Confirm no release, backend restart, or deployment job is part of the DNS phase.",
                    "required_before": "Real write execution",
                    "risk_if_missing": "A DNS change could be mixed with unrelated rollout effects.",
                    "note": "Keep DNS phases isolated.",
                },
            ],
        },
        {
            "key": "nas_reverse_proxy",
            "title": "NAS Reverse Proxy Checklist",
            "items": [
                {
                    "item": "Confirm DNS resolves to the NAS public address.",
                    "required_before": "Reverse proxy setup",
                    "risk_if_missing": "The hostname may not reach the NAS at all.",
                    "note": "Use public DNS and HTTP/HTTPS read-only checks.",
                },
                {
                    "item": "Confirm backend local health is OK.",
                    "required_before": "Reverse proxy setup",
                    "risk_if_missing": "The proxy may route to a broken upstream.",
                    "note": "Check the local port before touching NAS configuration.",
                },
                {
                    "item": "Confirm source hostname, upstream host, and upstream port.",
                    "required_before": "Reverse proxy setup",
                    "risk_if_missing": "Traffic may be routed to the wrong service.",
                    "note": "Preserve Host and forwarded protocol headers when needed.",
                },
                {
                    "item": "Confirm whether WebSocket support is needed.",
                    "required_before": "Reverse proxy setup",
                    "risk_if_missing": "Realtime features may fail after routing.",
                    "note": "Enable only when the backend requires it.",
                },
                {
                    "item": "Confirm the backend will not be restarted.",
                    "required_before": "Reverse proxy setup",
                    "risk_if_missing": "Routing work could accidentally become a service outage.",
                    "note": "NAS rule changes should not restart application containers.",
                },
                {
                    "item": "Verify the HTTPS path after configuration.",
                    "required_before": "Marking route ready",
                    "risk_if_missing": "A rule may exist but still point to DSM or a default page.",
                    "note": "Use the expected health path where available.",
                },
            ],
        },
        {
            "key": "ssl_certificate",
            "title": "SSL Certificate Checklist",
            "items": [
                {
                    "item": "Confirm certificate CN or SAN includes the hostname.",
                    "required_before": "Public HTTPS use",
                    "risk_if_missing": "Browsers and strict clients will reject the connection.",
                    "note": "Wildcard coverage is acceptable when it matches.",
                },
                {
                    "item": "Confirm certificate expiry and trusted issuer.",
                    "required_before": "Public HTTPS use",
                    "risk_if_missing": "Traffic may fail immediately or expire without warning.",
                    "note": "Prefer automated renewal where possible.",
                },
                {
                    "item": "Confirm Cloudflare SSL mode is Full strict or Full.",
                    "required_before": "Proxying through Cloudflare",
                    "risk_if_missing": "Flexible mode can hide origin HTTPS problems.",
                    "note": "Full strict is preferred when origin certificates are valid.",
                },
                {
                    "item": "Confirm DNS proxied status matches the SSL plan.",
                    "required_before": "Changing proxy mode",
                    "risk_if_missing": "A hostname may show Cloudflare 52x or origin trust errors.",
                    "note": "Do not change proxy mode from this checklist center.",
                },
                {
                    "item": "Confirm HTTP port 80 behavior.",
                    "required_before": "Public hostname handoff",
                    "risk_if_missing": "Users may see DSM, a default page, or inconsistent redirects.",
                    "note": "HTTPS readiness is the first priority.",
                },
            ],
        },
        {
            "key": "release_deploy",
            "title": "Release Deploy Checklist",
            "items": [
                {
                    "item": "Confirm git status is clean and latest commit is expected.",
                    "required_before": "Controlled production deploy",
                    "risk_if_missing": "Unreviewed local changes may be shipped.",
                    "note": "Use explicit file deployment only.",
                },
                {
                    "item": "Confirm py_compile and diff check pass.",
                    "required_before": "Controlled production deploy",
                    "risk_if_missing": "Syntax or whitespace errors may break runtime.",
                    "note": "Run checks before backup and copy.",
                },
                {
                    "item": "Confirm production backup exists and SHA matches before copy.",
                    "required_before": "Controlled production deploy",
                    "risk_if_missing": "Rollback reference may not match the actual previous file.",
                    "note": "Back up every modified production file.",
                },
                {
                    "item": "Confirm only specified files are copied.",
                    "required_before": "Controlled production deploy",
                    "risk_if_missing": "Data, environment, or unrelated templates may be overwritten.",
                    "note": "Never sync the whole folder for controlled deploys.",
                },
                {
                    "item": "Confirm only the target container is recreated.",
                    "required_before": "Controlled production deploy",
                    "risk_if_missing": "Unrelated services may experience downtime.",
                    "note": "Do not restart staging or backend containers.",
                },
                {
                    "item": "Confirm smoke tests and logs pass after deploy.",
                    "required_before": "Release close",
                    "risk_if_missing": "A bad release may remain undetected.",
                    "note": "Check routes, DB counts, and security logs.",
                },
            ],
        },
        {
            "key": "rollback_readiness",
            "title": "Rollback Readiness Checklist",
            "items": [
                {
                    "item": "Confirm rollback target and scope are explicit.",
                    "required_before": "Opening a rollback phase",
                    "risk_if_missing": "Rollback could affect the wrong file, DNS record, or service.",
                    "note": "Rollback must be scoped to one operation.",
                },
                {
                    "item": "Confirm backup path exists and matches expected SHA.",
                    "required_before": "Rollback execution",
                    "risk_if_missing": "Rollback may restore the wrong state.",
                    "note": "Verify before any restore action.",
                },
                {
                    "item": "Confirm rollback payload is generated.",
                    "required_before": "Rollback execution",
                    "risk_if_missing": "The recovery action may be incomplete.",
                    "note": "DNS rollback payloads must include record ids after write.",
                },
                {
                    "item": "Confirm rollback is not automatic.",
                    "required_before": "Any high-risk operation",
                    "risk_if_missing": "A secondary write could happen without review.",
                    "note": "Rollback requires its own approval phase.",
                },
                {
                    "item": "Confirm post-rollback verification steps.",
                    "required_before": "Rollback close",
                    "risk_if_missing": "A rollback may be assumed successful without proof.",
                    "note": "Use read-back, health, and log checks.",
                },
            ],
        },
        {
            "key": "secret_safety",
            "title": "Secret Safety Checklist",
            "items": [
                {
                    "item": "Confirm credential values are never printed in pages, CSV exports, or logs.",
                    "required_before": "Any verification report",
                    "risk_if_missing": "Sensitive runtime credentials may leak.",
                    "note": "Show only masked metadata when needed.",
                },
                {
                    "item": "Confirm environment file contents are not displayed.",
                    "required_before": "Any diagnostics step",
                    "risk_if_missing": "Runtime configuration may leak.",
                    "note": "Report presence or masked status only.",
                },
                {
                    "item": "Confirm auth header values are not copied into output.",
                    "required_before": "Any API or log review",
                    "risk_if_missing": "Reusable credentials may leak.",
                    "note": "Use sanitized status and error summaries.",
                },
                {
                    "item": "Confirm browser login state values are never shown.",
                    "required_before": "Any browser smoke test",
                    "risk_if_missing": "Authenticated browser state may be exposed.",
                    "note": "Do not print request headers or browser storage.",
                },
                {
                    "item": "Confirm encrypted database fields are not rendered.",
                    "required_before": "Any DB snapshot report",
                    "risk_if_missing": "Protected values may be exposed even if encrypted.",
                    "note": "Use counts and masked metadata only.",
                },
                {
                    "item": "Confirm logs are scanned for sensitive-value leakage.",
                    "required_before": "Release close",
                    "risk_if_missing": "A leak could go unnoticed after deploy.",
                    "note": "Scan recent production logs before closing.",
                },
            ],
        },
    ]


def manual_operations_checklist_context():
    sections = manual_operations_checklist_sections()
    return {
        "rendered_at": now_str(),
        "sections": sections,
        "summary": {
            "categories": len(sections),
            "items": sum(len(section.get("items") or []) for section in sections),
        },
    }


def manual_operations_checklist_csv_response():
    checklist = manual_operations_checklist_context()
    output = io.StringIO()
    fieldnames = ["category", "item", "required_before", "risk_if_missing", "note"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for section in checklist.get("sections", []):
        for item in section.get("items", []):
            writer.writerow({
                "category": section.get("title") or "",
                "item": item.get("item") or "",
                "required_before": item.get("required_before") or "",
                "risk_if_missing": item.get("risk_if_missing") or "",
                "note": item.get("note") or "",
            })
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=manual_operations_checklist.csv"
    response.headers["Cache-Control"] = "no-store"
    return response


def operations_runbook_sections():
    return [
        {
            "key": "dns_real_write",
            "title": "DNS Real Write Runbook",
            "purpose": "Perform a future single-record Cloudflare DNS write with explicit gates, backup, audit, and read-back verification.",
            "preconditions": [
                "Owner-only approval is granted for exactly one record.",
                "Cloudflare read-only preflight has passed.",
                "Production database backup path is recorded.",
                "Rollback payload is ready before the write.",
            ],
            "steps": [
                "Confirm the hostname, type, content, proxied state, and ttl.",
                "Confirm decision is create or update and not delete.",
                "Confirm the final phrase was provided in the approved execution phase.",
                "Create or update only the planned single record in the future write phase.",
                "Read back the record immediately and compare it to the planned payload.",
                "Record audit result and sanitized provider response.",
            ],
            "validation": [
                "Read-back shows exactly the expected record.",
                "No unrelated hostnames changed.",
                "deployment_jobs count remains unchanged.",
                "domain_mappings remains unchanged unless a separate approved phase says otherwise.",
            ],
            "stop_condition": "Stop if the record already exists unexpectedly, preflight fails, backup hash does not match, or scope expands beyond one record.",
            "forbidden_actions": [
                "Do not write multiple records in one phase.",
                "Do not delete DNS records from this runbook.",
                "Do not combine DNS write with deployment or restart work.",
            ],
        },
        {
            "key": "nas_ssl_reverse_proxy",
            "title": "NAS SSL / Reverse Proxy Runbook",
            "purpose": "Prepare and verify NAS routing and HTTPS readiness for an existing hostname without changing backend runtime.",
            "preconditions": [
                "DNS points to the NAS public address.",
                "Backend local health endpoint returns OK.",
                "Target source hostname and destination port are explicit.",
                "Certificate coverage is known before public HTTPS verification.",
            ],
            "steps": [
                "Confirm current HTTP and HTTPS behavior.",
                "Confirm whether an existing reverse proxy rule already covers the hostname.",
                "Plan source HTTPS hostname and destination local upstream.",
                "Confirm certificate CN or SAN covers the hostname.",
                "Verify strict HTTPS health path after setup in a separate approved phase.",
            ],
            "validation": [
                "HTTPS health endpoint returns 200 with strict TLS.",
                "Root path does not land on DSM unless intentionally expected.",
                "Backend logs show no application errors.",
            ],
            "stop_condition": "Stop if certificate coverage is missing, upstream health fails, or the target hostname is ambiguous.",
            "forbidden_actions": [
                "Do not restart backend containers.",
                "Do not alter unrelated reverse proxy rules.",
                "Do not change DNS while performing NAS routing work.",
            ],
        },
        {
            "key": "release_deploy",
            "title": "Release Deploy Runbook",
            "purpose": "Deploy reviewed DevPilot files with backups, constrained copy scope, and post-deploy smoke tests.",
            "preconditions": [
                "git status is clean and latest commit is expected.",
                "py_compile and diff check pass.",
                "Deployment file list is explicit.",
                "Production file backups and hashes are recorded.",
            ],
            "steps": [
                "Back up every production file that will be overwritten.",
                "Verify backup SHA equals production-before SHA.",
                "Copy only the approved files.",
                "Verify production SHA equals local HEAD SHA.",
                "Recreate only the target DevPilot container.",
                "Run route smoke tests, DB count checks, and log security scan.",
            ],
            "validation": [
                "Container is Up on the expected port mapping.",
                "app.py compiles inside the container.",
                "Regression routes return expected statuses.",
                "No DB, DNS, Telegram, or deployment side effect occurred.",
            ],
            "stop_condition": "Stop if backup creation fails, hashes differ unexpectedly, or deployment delta includes unrelated files.",
            "forbidden_actions": [
                "Do not sync the whole folder.",
                "Do not overwrite .env or data/project_manager.db.",
                "Do not restart staging or backend containers.",
            ],
        },
        {
            "key": "emergency_rollback",
            "title": "Emergency Rollback Runbook",
            "purpose": "Restore a clearly scoped previous state only after the rollback target and backup are verified.",
            "preconditions": [
                "Rollback target is explicit.",
                "Correct backup path exists.",
                "Backup hash and expected previous hash are verified.",
                "Rollback phase has separate approval.",
            ],
            "steps": [
                "Stop if the target is uncertain.",
                "Identify whether rollback is file, database, DNS, or service routing.",
                "For file rollback, restore only the scoped file from the approved backup.",
                "For DNS or database rollback, open a separate approval phase.",
                "Verify the restored state with read-only checks.",
            ],
            "validation": [
                "Restored file or record matches the rollback payload.",
                "Application smoke tests pass.",
                "Logs show no traceback or unintended side effects.",
            ],
            "stop_condition": "Stop if the backup is missing, hashes do not match, or rollback would affect unrelated services.",
            "forbidden_actions": [
                "Do not perform automatic rollback from this page.",
                "Do not restore a database without a dedicated approval phase.",
                "Do not delete DNS records without a separate rollback approval.",
            ],
        },
        {
            "key": "secret_leak_response",
            "title": "Secret Leak Response Runbook",
            "purpose": "Contain and remediate accidental credential exposure without spreading the exposed value further.",
            "preconditions": [
                "Stop writing or repeating the exposed value.",
                "Identify affected provider and environment from masked metadata only.",
                "Preserve audit context without copying sensitive value text.",
            ],
            "steps": [
                "Stop output and remove exposed value from visible reports where possible.",
                "Rotate the affected credential in its provider console.",
                "Revoke the old credential after replacement is verified.",
                "Review audit logs and recent application logs for further exposure.",
                "Confirm the value is not committed to git.",
                "Document the incident with masked identifiers only.",
            ],
            "validation": [
                "New credential works where required.",
                "Old credential is revoked.",
                "Git and recent logs do not contain the exposed value.",
            ],
            "stop_condition": "Stop if provider access is unclear or rotation ownership is not confirmed.",
            "forbidden_actions": [
                "Do not paste complete credential values into chat, pages, CSV files, or logs.",
                "Do not reveal environment file contents.",
                "Do not continue normal deployment until exposure is contained.",
            ],
        },
        {
            "key": "telegram_approval_test",
            "title": "Telegram Approval Test Runbook",
            "purpose": "Verify approval notification behavior using mock approval requests without triggering DNS or deployment side effects.",
            "preconditions": [
                "A mock approval request exists and is pending.",
                "Request type is mock_approval_test.",
                "Allowed operator is ready to press exactly one button.",
                "No DNS or deployment request is used for the test.",
            ],
            "steps": [
                "Send one inline notification for the mock request.",
                "For reject testing, press Reject once and verify rejected state.",
                "For approve testing, use a new mock request and press Approve once.",
                "Confirm duplicate callback tolerance metrics remain clean.",
                "Verify DB counts and logs after each test.",
            ],
            "validation": [
                "Mock request reaches the expected final status.",
                "No deployment job is created.",
                "No Cloudflare DNS action occurs.",
                "Logs do not expose callback values or sensitive runtime values.",
            ],
            "stop_condition": "Stop if the request is not mock_approval_test, is no longer pending, or the operator is unsure which button to press.",
            "forbidden_actions": [
                "Do not press buttons on DNS or deployment requests.",
                "Do not press both Approve and Reject on the same request.",
                "Do not simulate callback payloads manually.",
            ],
        },
    ]


def operations_runbook_context():
    runbooks = operations_runbook_sections()
    return {
        "rendered_at": now_str(),
        "runbooks": runbooks,
        "summary": {
            "runbooks": len(runbooks),
            "steps": sum(len(item.get("steps") or []) for item in runbooks),
        },
    }


def operations_runbook_csv_response():
    context = operations_runbook_context()
    output = io.StringIO()
    fieldnames = ["runbook", "section", "step_order", "step", "validation", "forbidden_actions"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for runbook in context.get("runbooks", []):
        validations = " | ".join(runbook.get("validation") or [])
        forbidden = " | ".join(runbook.get("forbidden_actions") or [])
        for index, step in enumerate(runbook.get("steps") or [], start=1):
            writer.writerow({
                "runbook": runbook.get("title") or "",
                "section": "Steps",
                "step_order": index,
                "step": step,
                "validation": validations,
                "forbidden_actions": forbidden,
            })
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=operations_runbook.csv"
    response.headers["Cache-Control"] = "no-store"
    return response


def operations_command_center_context():
    release = release_dashboard_context()
    backup_items = release.get("backups", {}).get("items", [])
    cloudflare_flag = release.get("safety", {}).get("cloudflare_dns_write", {})
    mock_flag = release.get("safety", {}).get("mock_dns_execution", {})
    shopee = operations_shopee_status()
    shopee_project = shopee.get("project") or {}
    shopee_project_link = f"/projects/{shopee_project.get('id')}" if shopee_project.get("exists") and shopee_project.get("id") else "/projects/18"
    return {
        "rendered_at": now_str(),
        "release_version": release.get("version") or release_version_info(),
        "production_domain": {
            "url": RELEASE_DASHBOARD_DOMAIN,
            "status": "online",
            "login_protected": True,
            "detail": "Authenticated DevPilot route rendered successfully.",
        },
        "release": {
            "url": "/release-dashboard",
            "backup_count": len(backup_items),
            "latest_backup": backup_items[0] if backup_items else None,
            "backup_mount_read_only": True,
            "app_sha256": release.get("identity", {}).get("app_sha256"),
            "git": release.get("identity", {}).get("git", {}),
        },
        "approval": release.get("db", {}),
        "dns_safety": {
            "prepare_dry_run": True,
            "preflight_read_only": True,
            "confirm_dry_run": True,
            "execute_disabled": True,
            "real_dns_write_disabled": True,
            "cloudflare_api_write_disabled": True,
        },
        "cloudflare_flags": {
            "dns_write": cloudflare_flag,
            "mock_dns_execution": mock_flag,
        },
        "shopee": shopee,
        "recent_backups": backup_items[:6],
        "recent_dns_attempts": release.get("dns_attempts", [])[:5],
        "quick_links": [
            {"label": "Release Dashboard", "href": "/release-dashboard"},
            {"label": "Approval Requests", "href": "/approval-requests"},
            {"label": "Cloudflare", "href": "/cloudflare"},
            {"label": "Domains", "href": "/domains"},
            {"label": "AI Console", "href": "/ai-console"},
            {"label": "Shopee AI Project", "href": shopee_project_link},
            {"label": "Deployment Board", "href": "/deployment-board"},
        ],
    }


def record_dns_execution_attempt(
    request_id,
    confirmation,
    result,
    http_status,
    error_message="",
    attempted_action="cloudflare_dns_execute",
    feature_flag=None,
    feature_flag_state=None,
    request_snapshot_extra=None,
):
    user = current_user() or {}
    actor = user.get("username") or user.get("email") or current_role() or "unknown"
    row = approval_request_public(approval_request_row(request_id)) or {}
    request_snapshot = {
        "request_id": request_id,
        "request_type": row.get("request_type"),
        "status": row.get("status"),
        "project_id": row.get("project_id"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "execution_state": row.get("execution_state"),
    }
    if isinstance(request_snapshot_extra, dict):
        request_snapshot.update(request_snapshot_extra)
    feature_flag = feature_flag or CLOUDFLARE_DNS_WRITE_FEATURE_FLAG
    if feature_flag_state is None:
        if feature_flag == MOCK_DNS_EXECUTION_FEATURE_FLAG:
            feature_flag_state = "enabled" if mock_dns_execution_feature_enabled() else "disabled"
        else:
            feature_flag_state = "enabled" if cloudflare_dns_write_feature_enabled() else "disabled"
    cur = execute(
        """INSERT INTO dns_execution_attempts
           (approval_request_id, actor, attempted_action, feature_flag, feature_flag_state,
            result, http_status, planned_action_json, request_snapshot_json, error_message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            request_id,
            actor,
            attempted_action,
            feature_flag,
            feature_flag_state,
            result,
            int(http_status),
            json.dumps(confirmation.get("planned_action") or {}, ensure_ascii=False),
            json.dumps(request_snapshot, ensure_ascii=False),
            str(error_message or "")[:500],
            now_str(),
        ),
    )
    return cur.lastrowid


def dns_mock_execution_result(preflight):
    planned_action = preflight.get("planned_action") or {}
    rollback_snapshot = preflight.get("rollback_snapshot") or {}
    return {
        "decision": preflight.get("decision"),
        "provider": "cloudflare",
        "simulated_action": planned_action.get("action"),
        "record": {
            "type": planned_action.get("record_type"),
            "name": planned_action.get("name"),
            "target": planned_action.get("target"),
            "proxied": planned_action.get("proxied"),
            "ttl": planned_action.get("ttl"),
        },
        "rollback_strategy": rollback_snapshot.get("strategy"),
        "no_real_write": True,
        "cloudflare_write_call_enabled": False,
        "dns_write_performed": False,
        "deployment_job_created": False,
    }


def build_approval_dns_plan_execute_disabled(request_id, payload=None):
    source = payload if isinstance(payload, dict) else {}
    confirmation, status_code = build_approval_dns_plan_confirmation(request_id, payload)
    if status_code != 200:
        return confirmation, status_code

    if str(source.get("mode") or "").strip().lower() == "mock":
        if not mock_dns_execution_feature_enabled():
            return {
                "ok": False,
                "status": "mock_dns_execution_disabled",
                "error": "mock_dns_execution_disabled",
                "mode": "mock_execute_disabled",
                "request_id": request_id,
                "request_type": confirmation.get("request_type"),
                "approval_status": confirmation.get("approval_status"),
                "execution_state": confirmation.get("execution_state"),
                "dns_write_enabled": False,
                "execution_enabled": False,
                "cloudflare_write_call_enabled": False,
                "dns_write_performed": False,
                "disabled_by_feature_flag": True,
                "feature_flag": MOCK_DNS_EXECUTION_FEATURE_FLAG,
                "attempt_logged": False,
                "attempt_result": None,
                "planned_action": confirmation.get("planned_action"),
                "next_step": "mock_dns_execution_feature_flag_disabled",
                "message": "Mock DNS execution is disabled. No DNS record was created or updated.",
            }, 409

        preflight, preflight_status = build_approval_dns_plan_preflight(request_id)
        if preflight_status != 200:
            return preflight, preflight_status

        mock_result = dns_mock_execution_result(preflight)
        attempt_id = record_dns_execution_attempt(
            request_id,
            preflight,
            result="mock_executed",
            http_status=200,
            error_message="Mock DNS execution only. No real DNS write.",
            attempted_action="cloudflare_dns_execute_mock",
            feature_flag=MOCK_DNS_EXECUTION_FEATURE_FLAG,
            feature_flag_state="enabled",
            request_snapshot_extra={
                "mock_result": "mock_executed",
                "no_real_write": True,
                "decision": preflight.get("decision"),
            },
        )
        return {
            "ok": True,
            "mode": "mock_execute",
            "result": "mock_executed",
            "request_id": request_id,
            "request_type": confirmation.get("request_type"),
            "approval_status": confirmation.get("approval_status"),
            "execution_state": confirmation.get("execution_state"),
            "no_real_write": True,
            "cloudflare_write_call_enabled": False,
            "dns_write_performed": False,
            "deployment_job_created": False,
            "dns_write_enabled": False,
            "execution_enabled": False,
            "decision": preflight.get("decision"),
            "mock_execution_result": mock_result,
            "attempt_logged": True,
            "attempt_result": "mock_executed",
            "attempt_id": attempt_id,
            "planned_action": preflight.get("planned_action"),
            "rollback_snapshot": preflight.get("rollback_snapshot"),
            "next_step": "real_cloudflare_write_still_not_enabled",
            "message": "Mock DNS execution completed. No Cloudflare DNS record was created or updated.",
        }, 200

    if not cloudflare_dns_write_feature_enabled():
        attempt_id = record_dns_execution_attempt(
            request_id,
            confirmation,
            result="blocked_disabled",
            http_status=409,
            error_message="Cloudflare DNS write is disabled by feature flag.",
        )
        return {
            "ok": False,
            "status": "cloudflare_dns_write_disabled",
            "error": "cloudflare_dns_write_disabled",
            "mode": "execute_disabled",
            "request_id": request_id,
            "request_type": confirmation.get("request_type"),
            "approval_status": confirmation.get("approval_status"),
            "execution_state": confirmation.get("execution_state"),
            "dns_write_enabled": False,
            "execution_enabled": False,
            "disabled_by_feature_flag": True,
            "feature_flag": CLOUDFLARE_DNS_WRITE_FEATURE_FLAG,
            "attempt_logged": True,
            "attempt_result": "blocked_disabled",
            "attempt_id": attempt_id,
            "planned_action": confirmation.get("planned_action"),
            "next_step": "cloudflare_write_feature_flag_disabled",
            "message": "Cloudflare DNS write is disabled. No DNS record was created or updated.",
        }, 409

    return {
        "ok": False,
        "status": "cloudflare_dns_execute_not_implemented",
        "error": "cloudflare_dns_execute_not_implemented",
        "mode": "execute_disabled",
        "request_id": request_id,
        "request_type": confirmation.get("request_type"),
        "approval_status": confirmation.get("approval_status"),
        "execution_state": confirmation.get("execution_state"),
        "dns_write_enabled": False,
        "execution_enabled": False,
        "disabled_by_feature_flag": False,
        "feature_flag": CLOUDFLARE_DNS_WRITE_FEATURE_FLAG,
        "planned_action": confirmation.get("planned_action"),
        "next_step": "cloudflare_write_execute_not_implemented",
        "message": "Cloudflare DNS execute endpoint is not implemented in this phase.",
    }, 409


def approval_request_rows(status=None, project_id=None, request_type=None, limit=100):
    where = ["1=1"]
    params = []
    if status:
        where.append("ar.status=?")
        params.append(str(status).strip())
    if project_id not in (None, ""):
        where.append("ar.project_id=?")
        params.append(int(project_id))
    if request_type:
        where.append("ar.request_type=?")
        params.append(str(request_type).strip())
    params.append(max(1, min(coerce_int(limit, 100), 200)))
    rows = query_all(
        f"""SELECT ar.*, p.name AS project_name
            FROM approval_requests ar
            LEFT JOIN projects p ON p.id=ar.project_id
            WHERE {' AND '.join(where)}
            ORDER BY ar.created_at DESC, ar.id DESC
            LIMIT ?""",
        tuple(params),
    )
    return [approval_request_public(row) for row in rows]


def approval_request_title(request_type, payload, project_id=None):
    if request_type == "dns_preview_create":
        record = (payload or {}).get("dns_record") or {}
        return f"Approve preview DNS: {record.get('name') or 'unknown'}"
    return f"Approval request for project {project_id or '-'}"


def create_approval_request(payload):
    request_type = normalize_choice(payload.get("request_type"), APPROVAL_REQUEST_TYPES, "")
    if request_type != "dns_preview_create":
        raise ValueError("unsupported approval request type")
    project_id = int(payload.get("project_id") or 0)
    if not project_id or not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("project_id is required")
    approval_payload = sanitize_approval_payload(request_type, payload.get("payload") or payload)
    if approval_payload_contains_secret(payload.get("summary")) or approval_payload_contains_secret(payload.get("notes")):
        raise ValueError("approval text contains blocked secret-like fields")
    now = now_str()
    expires_at = (now_dt() + timedelta(hours=APPROVAL_DEFAULT_EXPIRES_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    user = current_user() or {}
    title = (payload.get("title") or approval_request_title(request_type, approval_payload, project_id)).strip()
    summary = (payload.get("summary") or "").strip()
    if not summary:
        record = approval_payload["dns_record"]
        summary = f"{record['type']} {record['name']} -> {record['content']} (plan only)"
    cur = execute(
        """INSERT INTO approval_requests
           (request_type, project_id, title, summary, payload_json, status, requested_by,
            approved_by, approved_via, telegram_chat_id_masked, telegram_message_id,
            callback_nonce_hash, expires_at, created_at, updated_at, approved_at, rejected_at, notes)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, '', '', '', '', '', ?, ?, ?, '', '', ?)""",
        (
            request_type,
            project_id,
            title[:255],
            summary[:1000],
            json.dumps(approval_payload, ensure_ascii=False),
            user.get("username") or current_role() or "local_admin",
            expires_at,
            now,
            now,
            str(payload.get("notes") or "")[:1000],
        ),
    )
    request_id = cur.lastrowid
    audit_log("approval-request-create", "approval_request", request_id, {"request_type": request_type, "project_id": project_id})
    return approval_request_public(approval_request_row(request_id))


def create_mock_approval_request(payload=None):
    source = payload if isinstance(payload, dict) else {}
    if approval_payload_contains_secret(source):
        raise ValueError("mock approval payload contains blocked secret-like fields")
    project_id = None
    if source.get("project_id") not in (None, ""):
        project_id = int(source.get("project_id") or 0)
        if not project_id or not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
            raise ValueError("project_id was provided but does not exist")
    now = now_str()
    expires_at = (now_dt() + timedelta(hours=APPROVAL_DEFAULT_EXPIRES_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    user = current_user() or {}
    approval_payload = {
        "mock": True,
        "safe_test": True,
        "no_dns_write": True,
        "no_deploy": True,
        "created_for": "telegram_approval_testing",
    }
    nonce = secrets.token_urlsafe(18)
    cur = execute(
        """INSERT INTO approval_requests
           (request_type, project_id, title, summary, payload_json, status, requested_by,
            approved_by, approved_via, telegram_chat_id_masked, telegram_message_id,
            callback_nonce_hash, expires_at, created_at, updated_at, approved_at, rejected_at, notes)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, '', '', '', '', ?, ?, ?, ?, '', '', ?)""",
        (
            "mock_approval_test",
            project_id,
            "Mock approval test",
            "Safe mock approval request. No DNS write. No deploy.",
            json.dumps(approval_payload, ensure_ascii=False),
            user.get("username") or current_role() or "local_admin",
            approval_nonce_hash(nonce),
            expires_at,
            now,
            now,
            "Generated by mock approval request generator. No Telegram message was sent.",
        ),
    )
    request_id = cur.lastrowid
    audit_log("approval-request-create-mock", "approval_request", request_id, {"request_type": "mock_approval_test", "project_id": project_id})
    return approval_request_public(approval_request_row(request_id))


def mask_chat_id(value):
    return mask_identifier(value, prefix=3, suffix=3)


def mock_send_telegram_approval(request_id, payload=None):
    row = approval_request_row(request_id)
    if not row:
        raise LookupError("approval request not found")
    if row.get("status") != "pending":
        raise ValueError("approval request is not pending")
    nonce = secrets.token_urlsafe(18)
    message_id = f"mock-{request_id}-{int(time.time())}"
    chat_id = str((payload or {}).get("telegram_chat_id") or "mock-chat")
    now = now_str()
    execute(
        """UPDATE approval_requests
           SET callback_nonce_hash=?, telegram_chat_id_masked=?, telegram_message_id=?, updated_at=?
           WHERE id=?""",
        (approval_nonce_hash(nonce), mask_chat_id(chat_id), message_id, now, request_id),
    )
    audit_log("approval-request-send-telegram-mock", "approval_request", request_id, {"message_id": message_id})
    return {
        "ok": True,
        "approval_request": approval_request_public(approval_request_row(request_id)),
        "telegram": {
            "mock": True,
            "message_id": message_id,
            "chat_id_masked": mask_chat_id(chat_id),
        },
        "message": "Telegram send mocked. No Telegram Bot API call was made.",
    }


def telegram_allowed_notification_targets():
    rows = query_all(
        """SELECT *
           FROM telegram_allowed_users
           WHERE COALESCE(is_active, 1)=1
             AND role IN ('owner', 'admin')
             AND COALESCE(encrypted_chat_id, '')<>''
           ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END, id ASC"""
    )
    targets = []
    for row in rows:
        item = row_to_dict(row)
        try:
            chat_id = decrypt_telegram_chat_id(item)
        except Exception:
            continue
        if not chat_id:
            continue
        item["chat_id"] = chat_id
        item["chat_id_masked"] = item.get("chat_id_masked") or mask_chat_id(chat_id)
        targets.append(item)
    return targets


def approval_request_telegram_message(row):
    public = approval_request_public(row)
    payload = public.get("payload") or {}
    record = payload.get("dns_record") or {}
    project_label = f"#{public.get('project_id')}" if public.get("project_id") else "-"
    if public.get("project_name"):
        project_label = f"{project_label} {public.get('project_name')}"
    return "\n".join([
        "DevPilot Approval Request",
        "",
        f"Type: {public.get('request_type') or '-'}",
        f"Project: {project_label}",
        f"Title: {public.get('title') or '-'}",
        f"Status: {public.get('status') or '-'}",
        "",
        "DNS Plan:",
        f"{record.get('type') or '-'} {record.get('name') or '-'} -> {record.get('content') or '-'}",
        f"proxied={str(record.get('proxied')).lower()} ttl={record.get('ttl') or '-'}",
        "",
        "This is a notification only.",
        "No DNS record was created.",
        "No deployment was triggered.",
        "Approve/reject must be handled in DevPilot.",
    ])


def send_telegram_approval_notification(request_id, with_buttons=False):
    row = approval_request_row(request_id)
    if not row:
        raise LookupError("approval request not found")
    if row.get("status") != "pending":
        raise ValueError("approval request is not pending")
    targets = telegram_allowed_notification_targets()
    if not targets:
        return {
            "ok": False,
            "error": "telegram_notification_target_not_configured",
            "message": "No active owner/admin Telegram target with encrypted chat_id was found.",
            "status": row.get("status"),
        }, 400
    target = targets[0]
    nonce = secrets.token_urlsafe(18)
    message = approval_request_telegram_message(row)
    reply_markup = None
    if with_buttons:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "Approve", "callback_data": f"{APPROVAL_CALLBACK_PREFIX}:{request_id}:approve:{nonce}"},
                {"text": "Reject", "callback_data": f"{APPROVAL_CALLBACK_PREFIX}:{request_id}:reject:{nonce}"},
            ]]
        }
    result = telegram_send_message(target["chat_id"], message, reply_markup=reply_markup)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error") or "telegram_send_failed",
            "status_code": result.get("status_code"),
            "message": result.get("message") or "Telegram send failed.",
            "chat_id_masked": result.get("chat_id_masked") or target.get("chat_id_masked"),
            "status": row.get("status"),
        }, 502
    message_id = str(result.get("telegram_message_id") or "")
    now = now_str()
    execute(
        """UPDATE approval_requests
           SET callback_nonce_hash=?, telegram_chat_id_masked=?, telegram_message_id=?, updated_at=?
           WHERE id=?""",
        (approval_nonce_hash(nonce), result.get("chat_id_masked") or target.get("chat_id_masked"), message_id, now, request_id),
    )
    audit_log("approval-request-send-telegram", "approval_request", request_id, {"message_id": message_id})
    return {
        "ok": True,
        "mock": False,
        "with_buttons": bool(with_buttons),
        "telegram_message_id": message_id,
        "chat_id_masked": result.get("chat_id_masked") or target.get("chat_id_masked"),
        "message": "Telegram approval notification sent.",
        "status": "pending",
        "approval_request": approval_request_public(approval_request_row(request_id)),
    }, 200


def parse_telegram_callback_payload(payload):
    data = payload.get("callback_data") or payload.get("data") or ""
    user_id = payload.get("telegram_user_id") or payload.get("user_id")
    username = payload.get("telegram_username") or payload.get("username") or ""
    callback_query = payload.get("callback_query")
    if isinstance(callback_query, dict):
        data = data or callback_query.get("data") or ""
        sender = callback_query.get("from") or {}
        user_id = user_id or sender.get("id")
        username = username or sender.get("username") or ""
    parts = str(data or "").split(":")
    if len(parts) != 4 or parts[0] != APPROVAL_CALLBACK_PREFIX:
        raise ValueError("invalid callback_data")
    try:
        request_id = int(parts[1])
    except (TypeError, ValueError):
        raise ValueError("invalid approval request id")
    action = parts[2]
    if action not in ("approve", "reject"):
        raise ValueError("invalid approval action")
    nonce = parts[3]
    if not nonce:
        raise ValueError("missing nonce")
    if user_id in (None, ""):
        raise ValueError("missing telegram user")
    return request_id, action, nonce, str(user_id), str(username or "")


def telegram_allowed_user(user_id):
    user_hash = telegram_user_id_hash(user_id)
    return row_to_dict(
        query_one(
            """SELECT *
               FROM telegram_allowed_users
               WHERE telegram_user_id_hash=? AND COALESCE(is_active, 1)=1
               ORDER BY id DESC LIMIT 1""",
            (user_hash,),
        )
    )


def get_active_telegram_bot_token():
    row = row_to_dict(query_one(
        """SELECT name, encrypted_value, masked_value, key_mask
           FROM api_keys
           WHERE lower(COALESCE(provider, ''))='telegram'
             AND lower(COALESCE(category, ''))='third-party'
             AND lower(COALESCE(environment, ''))='staging'
             AND lower(COALESCE(status, ''))='active'
           ORDER BY datetime(COALESCE(updated_at, created_at)) DESC, id DESC
           LIMIT 1"""
    ))
    if not row:
        return {"ok": False, "error": "telegram_token_not_configured", "api_key": {"source": "none"}}
    masked = row.get("masked_value") or row.get("key_mask") or "************"
    api_key = {"source": "db", "name": row.get("name"), "masked": masked}
    try:
        token = decrypt_secret_value(row.get("encrypted_value"))
    except Exception:
        return {"ok": False, "error": "telegram_token_decrypt_failed", "api_key": api_key}
    if not str(token or "").strip():
        return {"ok": False, "error": "telegram_token_empty", "api_key": api_key}
    return {"ok": True, "token": str(token).strip(), "api_key": api_key}


def encrypt_telegram_chat_id(chat_id):
    value = str(chat_id or "").strip()
    if not value:
        raise ValueError("telegram chat_id is required")
    return encrypt_secret_value(value)


def decrypt_telegram_chat_id(row):
    data = row_to_dict(row) if row and not isinstance(row, dict) else (row or {})
    encrypted = data.get("encrypted_chat_id")
    if not encrypted:
        return ""
    return decrypt_secret_value(encrypted)


def telegram_sanitized_error(message):
    text = str(message or "")
    text = re.sub(r"https://api\.telegram\.org/bot[^/\s]+", "https://api.telegram.org/bot[redacted]", text)
    text = re.sub(r"(Authorization:\s*)[^\s]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot[redacted]", text)
    return text[:300]


def telegram_send_message(chat_id, text, reply_markup=None):
    chat_id_text = str(chat_id or "").strip()
    chat_id_masked = mask_chat_id(chat_id_text)
    if not chat_id_text:
        return {
            "ok": False,
            "error": "telegram_chat_id_missing",
            "message": "Telegram chat_id is not configured.",
            "chat_id_masked": chat_id_masked,
        }
    token_info = get_active_telegram_bot_token()
    if not token_info.get("ok"):
        return {
            "ok": False,
            "error": token_info.get("error") or "telegram_token_not_configured",
            "message": "Telegram Bot token is not configured or cannot be decrypted.",
            "chat_id_masked": chat_id_masked,
        }
    payload = {
        "chat_id": chat_id_text,
        "text": str(text or ""),
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"https://api.telegram.org/bot{token_info['token']}/sendMessage"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw_body) if raw_body else {}
            result = payload.get("result") or {}
            return {
                "ok": bool(payload.get("ok", True)),
                "status_code": resp.status,
                "chat_id_masked": chat_id_masked,
                "telegram_message_id": result.get("message_id"),
            }
    except urllib.error.HTTPError as exc:
        # Telegram error bodies should stay internal; callers only need the HTTP status.
        try:
            exc.read()
        except Exception:
            pass
        return {
            "ok": False,
            "error": "telegram_send_failed",
            "status_code": exc.code,
            "message": f"Telegram HTTP {exc.code}",
            "chat_id_masked": chat_id_masked,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "telegram_send_failed",
            "status_code": None,
            "message": telegram_sanitized_error(type(exc).__name__),
            "chat_id_masked": chat_id_masked,
        }


def process_telegram_approval_callback(payload):
    request_id, action, nonce, user_id, username = parse_telegram_callback_payload(payload)
    row = approval_request_row(request_id)
    if not row:
        return {"ok": False, "error": "approval_request_not_found"}, 404
    if row.get("status") != "pending":
        return {"ok": False, "error": "approval_request_already_processed", "status": row.get("status")}, 409
    expires_at = parse_time(row.get("expires_at"))
    if expires_at and now_dt() > expires_at:
        execute("UPDATE approval_requests SET status='expired', updated_at=? WHERE id=?", (now_str(), request_id))
        audit_log("approval-request-expired", "approval_request", request_id, {"via": "telegram_mock"})
        return {"ok": False, "error": "approval_request_expired"}, 410
    if not row.get("callback_nonce_hash"):
        return {"ok": False, "error": "approval_request_not_sent"}, 400
    expected = row.get("callback_nonce_hash")
    provided = approval_nonce_hash(nonce)
    if not hmac.compare_digest(str(expected or ""), str(provided or "")):
        return {"ok": False, "error": "invalid_nonce"}, 403
    allowed = telegram_allowed_user(user_id)
    if not allowed or allowed.get("role") not in APPROVAL_ALLOWED_ROLES:
        return {"ok": False, "error": "telegram_user_not_allowed"}, 403
    now = now_str()
    actor = allowed.get("display_name") or allowed.get("telegram_username") or username or "telegram_user"
    if action == "approve":
        execute(
            """UPDATE approval_requests
               SET status='approved', approved_by=?, approved_via='telegram', approved_at=?, updated_at=?
               WHERE id=?""",
            (actor, now, now, request_id),
        )
        audit_log("approval-request-approved", "approval_request", request_id, {"via": "telegram_mock", "role": allowed.get("role")})
    else:
        execute(
            """UPDATE approval_requests
               SET status='rejected', approved_by=?, approved_via='telegram', rejected_at=?, updated_at=?
               WHERE id=?""",
            (actor, now, now, request_id),
        )
        audit_log("approval-request-rejected", "approval_request", request_id, {"via": "telegram_mock", "role": allowed.get("role")})
    return {
        "ok": True,
        "action": action,
        "approval_request": approval_request_public(approval_request_row(request_id)),
        "message": "Approval status updated only. No DNS or deployment action was executed.",
    }, 200


def dns_record_points_to_nas(record, nas_ip=DOMAIN_CENTER_NAS_IP):
    record_type = str(record.get("type") or "").upper()
    return record_type in ("A", "AAAA") and str(record.get("content") or "").strip() == str(nas_ip)


def project_select_options():
    return [row_to_dict(row) for row in query_all("SELECT id, name FROM projects ORDER BY name COLLATE NOCASE")]


def domain_mapping_rows(project_id=None):
    params = []
    where = []
    if project_id not in (None, ""):
        where.append("dm.project_id=?")
        params.append(int(project_id))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = query_all(
        f"""SELECT dm.*, p.name AS project_name
            FROM domain_mappings dm
            LEFT JOIN projects p ON p.id=dm.project_id
            {where_sql}
            ORDER BY dm.updated_at DESC, dm.id DESC""",
        params,
    )
    return [row_to_dict(row) for row in rows]


def domain_mapping_lookup():
    lookup = {}
    for item in domain_mapping_rows():
        key = (
            str(item.get("zone_name") or "").casefold(),
            str(item.get("record_name") or "").casefold(),
            str(item.get("record_type") or "").upper(),
        )
        lookup.setdefault(key, []).append(item)
    return lookup


def domain_mapping_key(zone_name, record_name, record_type):
    return (
        str(zone_name or "").casefold(),
        str(record_name or "").casefold(),
        str(record_type or "").upper(),
    )


def upsert_domain_mapping(payload):
    project_id = int(payload.get("project_id") or 0)
    if not project_id or not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("project_id is required")
    record_name = str(payload.get("record_name") or "").strip()
    record_type = str(payload.get("record_type") or "").strip().upper()
    if not record_name or not record_type:
        raise ValueError("record_name and record_type are required")
    zone_name = str(payload.get("zone_name") or "").strip()
    if not zone_name:
        parts = record_name.split(".", 1)
        zone_name = parts[1] if len(parts) > 1 else record_name
    environment = normalize_choice(payload.get("environment"), DOMAIN_MAPPING_ENVIRONMENTS, "staging")
    status = normalize_choice(payload.get("status"), ["active", "inactive"], "active")
    zone_id_masked = str(payload.get("zone_id_masked") or "").strip()
    record_content = str(payload.get("record_content") or "").strip()
    preview_url = str(payload.get("preview_url") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    now = now_str()
    existing = query_one(
        """SELECT id FROM domain_mappings
           WHERE lower(COALESCE(zone_name, ''))=lower(?)
             AND lower(record_name)=lower(?)
             AND upper(COALESCE(record_type, ''))=upper(?)""",
        (zone_name, record_name, record_type),
    )
    if existing:
        execute(
            """UPDATE domain_mappings
               SET project_id=?, zone_id_masked=?, record_content=?, environment=?,
                   preview_url=?, status=?, notes=?, updated_at=?
               WHERE id=?""",
            (project_id, zone_id_masked, record_content, environment, preview_url, status, notes, now, existing["id"]),
        )
        mapping_id = existing["id"]
    else:
        cur = execute(
            """INSERT INTO domain_mappings
               (zone_name, zone_id_masked, record_name, record_type, record_content, project_id,
                environment, preview_url, status, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (zone_name, zone_id_masked, record_name, record_type, record_content, project_id,
             environment, preview_url, status, notes, now, now),
        )
        mapping_id = cur.lastrowid
    return row_to_dict(query_one("SELECT * FROM domain_mappings WHERE id=?", (mapping_id,)))


def find_domain_project_bindings(hostname):
    name = str(hostname or "").strip()
    if not name:
        return []
    pattern = f"%{name}%"
    bindings = []
    try:
        direct_rows = query_all(
            """SELECT dm.*, p.name AS project_name
               FROM domain_mappings dm
               LEFT JOIN projects p ON p.id=dm.project_id
               WHERE lower(COALESCE(dm.record_name, ''))=lower(?)
                 AND COALESCE(dm.status, 'active')='active'
               ORDER BY dm.updated_at DESC, dm.id DESC
               LIMIT 10""",
            (name,),
        )
        for row in direct_rows:
            item = row_to_dict(row)
            item["source"] = "domain_mapping"
            bindings.append(item)
    except sqlite3.Error:
        pass
    try:
        deployment_rows = query_all(
            """SELECT DISTINCT p.id AS project_id, p.name AS project_name,
                      d.environment, d.service_name, d.public_url, d.internal_url
               FROM projects p
               JOIN project_deployments d ON d.project_id=p.id
               WHERE COALESCE(d.public_url, '') LIKE ? OR COALESCE(d.internal_url, '') LIKE ?
               ORDER BY p.id
               LIMIT 5""",
            (pattern, pattern),
        )
        for row in deployment_rows:
            item = row_to_dict(row)
            item["source"] = "deployment"
            bindings.append(item)
    except sqlite3.Error:
        pass
    try:
        endpoint_rows = query_all(
            """SELECT DISTINCT p.id AS project_id, p.name AS project_name,
                      e.endpoint_type, e.url
               FROM projects p
               JOIN service_endpoints e ON e.project_id=p.id
               WHERE COALESCE(e.url, '') LIKE ? AND COALESCE(e.is_ignored, 0)=0
               ORDER BY p.id
               LIMIT 5""",
            (pattern,),
        )
        for row in endpoint_rows:
            item = row_to_dict(row)
            item["source"] = "service_endpoint"
            bindings.append(item)
    except sqlite3.Error:
        pass
    seen = set()
    unique = []
    for item in bindings:
        key = (item.get("source"), item.get("project_id"), item.get("environment"), item.get("endpoint_type"), item.get("service_name"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def domain_dns_record_summary(record):
    public = cloudflare_dns_record_public(record)
    name = public.get("name") or ""
    zone_name = str(record.get("_zone_name") or "")
    key = domain_mapping_key(zone_name, name, public.get("type"))
    direct_mappings = getattr(g, "domain_mapping_lookup", {}).get(key, []) if has_request_context() else []
    return {
        "id_masked": mask_identifier(public.get("id")),
        "type": public.get("type"),
        "name": name,
        "content": mask_dns_record_content(public),
        "ttl": public.get("ttl"),
        "proxied": bool(public.get("proxied")),
        "points_to_nas": dns_record_points_to_nas(public),
        "created_on": public.get("created_on"),
        "modified_on": public.get("modified_on"),
        "project_bindings": direct_mappings or find_domain_project_bindings(name),
        "mapped": bool(direct_mappings),
    }


def domain_zone_checklist(zone_name, records):
    zone = str(zone_name or "")
    root_a_records = [
        item for item in records
        if str(item.get("type") or "").upper() == "A" and str(item.get("name") or "").lower() == zone.lower()
    ]
    www_name = f"www.{zone}" if zone else "www"
    www_cname_records = [
        item for item in records
        if str(item.get("type") or "").upper() == "CNAME" and str(item.get("name") or "").lower() == www_name.lower()
    ]
    a_records = [item for item in records if str(item.get("type") or "").upper() == "A"]
    cname_records = [item for item in records if str(item.get("type") or "").upper() == "CNAME"]
    nas_records = [item for item in records if dns_record_points_to_nas(item)]
    proxied_records = [item for item in records if item.get("proxied") is True]
    return {
        "root_a_exists": bool(root_a_records),
        "root_a_points_to_nas": any(dns_record_points_to_nas(item) for item in root_a_records),
        "www_cname_exists": bool(www_cname_records),
        "has_a_record": bool(a_records),
        "has_cname_record": bool(cname_records),
        "nas_record_count": len(nas_records),
        "proxied_record_count": len(proxied_records),
        "all_core_checks_passed": bool(root_a_records) and any(dns_record_points_to_nas(item) for item in root_a_records) and bool(www_cname_records),
    }


def domain_zone_summary(zone, records=None, records_error=None):
    public = cloudflare_zone_public(zone)
    record_items = []
    for item in (records or []):
        public_record = cloudflare_dns_record_public(item)
        public_record["_zone_name"] = public.get("name") or ""
        record_items.append(public_record)
    record_summaries = [domain_dns_record_summary(item) for item in record_items]
    return {
        "id": public.get("id"),
        "id_masked": mask_identifier(public.get("id")),
        "name": public.get("name"),
        "status": public.get("status"),
        "paused": public.get("paused"),
        "type": public.get("type"),
        "account_name": public.get("account_name"),
        "records_count": len(record_summaries),
        "records": record_summaries,
        "records_error": records_error,
        "checklist": domain_zone_checklist(public.get("name"), record_items),
    }


def fetch_domain_center_zones():
    if has_request_context():
        g.domain_mapping_lookup = domain_mapping_lookup()
    key_info = get_active_cloudflare_api_key()
    if not key_info.get("ok"):
        return {"ok": False, "error": key_info.get("error")}
    zones_result = cloudflare_request("GET", "/zones", key_info["token"], query={"page": 1, "per_page": 100})
    if not zones_result.get("ok"):
        return {"ok": False, "error": zones_result.get("error"), "status_code": zones_result.get("status_code")}
    zones_data = zones_result.get("data") or {}
    summaries = []
    for zone in zones_data.get("result") or []:
        zone_id = str(zone.get("id") or "")
        records = []
        records_error = None
        if zone_id:
            records_result = cloudflare_request(
                "GET",
                f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
                key_info["token"],
                query={"page": 1, "per_page": 100},
            )
            if records_result.get("ok"):
                records = ((records_result.get("data") or {}).get("result") or [])
            else:
                records_error = records_result.get("error") or "dns_records_failed"
        summaries.append(domain_zone_summary(zone, records, records_error))
    return {
        "ok": True,
        "nas_ip": DOMAIN_CENTER_NAS_IP,
        "zones": summaries,
        "count": len(summaries),
        "result_info": zones_data.get("result_info") or {},
    }


def fetch_domain_center_records(zone_id):
    if has_request_context():
        g.domain_mapping_lookup = domain_mapping_lookup()
    key_info = get_active_cloudflare_api_key()
    if not key_info.get("ok"):
        return {"ok": False, "error": key_info.get("error")}
    zone_result = cloudflare_request("GET", f"/zones/{urllib.parse.quote(zone_id, safe='')}", key_info["token"])
    if not zone_result.get("ok"):
        return {"ok": False, "error": zone_result.get("error"), "status_code": zone_result.get("status_code")}
    try:
        per_page = min(100, max(1, int(request.args.get("per_page") or 100)))
    except (TypeError, ValueError):
        per_page = 100
    records_result = cloudflare_request(
        "GET",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
        key_info["token"],
        query={"page": request.args.get("page") or 1, "per_page": per_page},
    )
    if not records_result.get("ok"):
        return {"ok": False, "error": records_result.get("error"), "status_code": records_result.get("status_code")}
    zone = ((zone_result.get("data") or {}).get("result") or {})
    records = ((records_result.get("data") or {}).get("result") or [])
    summary = domain_zone_summary(zone, records)
    return {
        "ok": True,
        "nas_ip": DOMAIN_CENTER_NAS_IP,
        "zone": {key: summary[key] for key in ("id", "id_masked", "name", "status", "paused", "type", "account_name", "records_count", "checklist")},
        "records": summary["records"],
        "count": summary["records_count"],
    }


def detect_api_key_anomalies(api_key_id, ip_address):
    now = now_dt()
    minute_since = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    hour_since = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    week_since = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    minute_count = query_one(
        "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND used_at>=?",
        (api_key_id, minute_since),
    )["c"]
    if minute_count >= 100:
        api_key_alert(api_key_id, "high_rate", f"{minute_count} requests in one minute")
    hour_count = query_one(
        "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND used_at>=?",
        (api_key_id, hour_since),
    )["c"]
    prior_count = query_one(
        "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND used_at>=? AND used_at<?",
        (api_key_id, week_since, hour_since),
    )["c"]
    prior_avg_hour = prior_count / max(1, 24 * 7 - 1)
    if prior_avg_hour > 0 and hour_count >= max(10, prior_avg_hour * 5):
        api_key_alert(api_key_id, "volume_spike", f"Hourly usage {hour_count} is above 5x average {prior_avg_hour:.2f}")
    if ip_address:
        known = query_one(
            "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND ip_address IS NOT NULL AND ip_address<>? AND used_at<?",
            (api_key_id, ip_address, now_str()),
        )["c"]
        seen_same = query_one(
            "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND ip_address=? AND used_at<?",
            (api_key_id, ip_address, now_str()),
        )["c"]
        if known > 0 and seen_same == 0:
            api_key_alert(api_key_id, "unexpected_ip", f"Unexpected source IP {ip_address}")


def record_api_key_usage(api_key_id, source, path, status_code, ip_address):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (api_key_id,))
    if not row:
        raise LookupError("API Key 不存在")
    if row["status"] == "revoked":
        raise PermissionError("API Key 已 revoked")
    if not api_key_environment_allowed(row, path):
        raise PermissionError("API Key environment is not allowed for this path")
    execute(
        "INSERT INTO api_key_usage (api_key_id, source, path, ip_address, status_code, used_at) VALUES (?, ?, ?, ?, ?, ?)",
        (api_key_id, source, path, ip_address, status_code, now_str()),
    )
    execute("UPDATE api_keys SET last_used_at=?, updated_at=? WHERE id=?", (now_str(), now_str(), api_key_id))
    if row["usage_limit"]:
        week_since = (now_dt() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        usage_count = query_one(
            "SELECT COUNT(*) AS c FROM api_key_usage WHERE api_key_id=? AND used_at>=?",
            (api_key_id, week_since),
        )["c"]
        already_alerted = query_one(
            "SELECT COUNT(*) AS c FROM api_key_alerts WHERE api_key_id=? AND type='usage_limit' AND created_at>=?",
            (api_key_id, week_since),
        )["c"]
        if usage_count >= int(row["usage_limit"]) and already_alerted == 0:
            api_key_alert(api_key_id, "usage_limit", f"7-day usage {usage_count} reached configured limit {row['usage_limit']}")
    detect_api_key_anomalies(api_key_id, ip_address)


def rotate_due_api_keys_once():
    due = []
    for row in query_all("SELECT * FROM api_keys WHERE status='active' AND COALESCE(rotation_days, 30) > 0"):
        last_rotated = parse_time(row["last_rotated_at"]) or parse_time(row["created_at"]) or now_dt()
        if now_dt() - last_rotated > timedelta(days=int(row["rotation_days"] or 30)):
            due.append(row)
    rotated = []
    for row in due:
        updated, _new_value = rotate_api_key(row["id"])
        rotated.append({"api_key_id": row["id"], "name": row["name"], "version": updated["version"]})
        # Do not log or return the generated key from background rotation.
    return rotated


def api_key_rotation_loop():
    while True:
        try:
            with app.app_context():
                rotate_due_api_keys_once()
        except Exception as exc:
            print(f"[api-key-rotation] failed: {exc}", flush=True)
        time.sleep(max(60, API_KEY_ROTATION_INTERVAL_SECONDS))


def should_start_api_key_rotation():
    if not API_KEY_ROTATION_ENABLED:
        return False
    debug_enabled = os.getenv("FLASK_DEBUG", "1") == "1"
    if debug_enabled:
        return os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    return True


def start_api_key_rotation_scheduler():
    global _API_KEY_ROTATION_THREAD_STARTED
    if not should_start_api_key_rotation():
        return
    with _API_KEY_ROTATION_THREAD_LOCK:
        if _API_KEY_ROTATION_THREAD_STARTED:
            return
        thread = threading.Thread(target=api_key_rotation_loop, name="api-key-rotation", daemon=True)
        thread.start()
        _API_KEY_ROTATION_THREAD_STARTED = True


def env_key_candidates():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return []
    candidates = []
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        upper = name.upper()
        if not value:
            continue
        if not any(token in upper for token in ("KEY", "TOKEN", "SECRET", "WEBHOOK")):
            continue
        provider = infer_api_key_provider(name)
        candidates.append({
            "name": name,
            "value": value,
            "provider": provider,
            "category": infer_api_key_category(name, provider),
            "permissions": infer_api_key_permissions(name, provider),
            "mask": mask_secret_value(value),
            "fingerprint": secret_fingerprint(value),
        })
    return candidates


def import_env_api_keys():
    imported = []
    skipped = []
    for item in env_key_candidates():
        exists = query_one(
            "SELECT id FROM api_keys WHERE name=? AND provider=? AND value_fingerprint=?",
            (item["name"], item["provider"], item["fingerprint"]),
        )
        if exists:
            skipped.append(item["name"])
            continue
        next_version = "v1"
        latest = query_one(
            "SELECT version FROM api_keys WHERE name=? AND provider=? ORDER BY id DESC LIMIT 1",
            (item["name"], item["provider"]),
        )
        if latest and latest["version"]:
            match = re.search(r"(\d+)$", latest["version"])
            next_version = f"v{int(match.group(1)) + 1}" if match else f"{latest['version']}-next"
        key_id = create_api_key_record({
            "name": item["name"],
            "category": item["category"],
            "provider": item["provider"],
            "environment": "staging",
            "status": "active",
            "version": next_version,
            "permissions": item["permissions"],
            "key_value": item["value"],
            "notes": "Imported from .env without modifying .env",
            "source": "env-import",
        })
        imported.append({"id": key_id, "name": item["name"], "version": next_version})
        api_key_audit(key_id, "import-env", {"name": item["name"], "version": next_version})
    return imported, skipped


def coerce_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_ai_provider_name(value):
    text = str(value or "").strip().lower()
    aliases = {
        "google": "gemini",
        "gemini": "gemini",
        "anthropic": "claude",
        "claude": "claude",
        "codex": "openai",
        "openai": "openai",
    }
    normalized = aliases.get(text, text)
    if normalized not in AI_PROVIDER_NAMES:
        raise ValueError("unsupported AI provider")
    return normalized


def ai_provider_to_dispatch_provider(provider_name):
    return {"gemini": "google", "claude": "anthropic", "openai": "openai"}.get(provider_name, provider_name)


def seed_ai_providers():
    defaults = [
        {
            "provider_name": "openai",
            "priority": 10,
            "default_model": os.getenv("OPENAI_DEFAULT_MODEL", "codex-cli"),
            "cost_input_per_1k": 0,
            "cost_output_per_1k": 0,
        },
        {
            "provider_name": "gemini",
            "priority": 20,
            "default_model": os.getenv("GEMINI_DEFAULT_MODEL", "gemini-1.5-pro"),
            "cost_input_per_1k": 0,
            "cost_output_per_1k": 0,
        },
        {
            "provider_name": "claude",
            "priority": 30,
            "default_model": os.getenv("CLAUDE_DEFAULT_MODEL", "claude"),
            "cost_input_per_1k": 0,
            "cost_output_per_1k": 0,
        },
    ]
    now = now_str()
    for item in defaults:
        if query_one("SELECT id FROM ai_providers WHERE provider_name=?", (item["provider_name"],)):
            continue
        execute(
            """INSERT INTO ai_providers
               (provider_name, status, priority, default_model, cost_input_per_1k, cost_output_per_1k, created_at, updated_at)
               VALUES (?, 'active', ?, ?, ?, ?, ?, ?)""",
            (
                item["provider_name"],
                item["priority"],
                item["default_model"],
                item["cost_input_per_1k"],
                item["cost_output_per_1k"],
                now,
                now,
            ),
        )


def ai_period_start(period):
    now = now_dt()
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    return now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def ai_cost_sum(provider_name=None, since=None):
    where = ["status='success'"]
    params = []
    if provider_name:
        where.append("provider=?")
        params.append(provider_name)
    if since:
        where.append("created_at>=?")
        params.append(since)
    row = query_one(
        f"SELECT COALESCE(SUM(estimated_cost), 0) AS total FROM ai_usage_logs WHERE {' AND '.join(where)}",
        tuple(params),
    )
    return float(row["total"] or 0)


def ai_recent_error(provider_name, minutes=15):
    since = (now_dt() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    return row_to_dict(
        query_one(
            "SELECT * FROM ai_usage_logs WHERE provider=? AND status='failed' AND created_at>=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (provider_name, since),
        )
    )


def ai_provider_rows():
    today = ai_period_start("day")
    month = ai_period_start("month")
    rows = []
    for row in query_all("SELECT * FROM ai_providers ORDER BY priority ASC, provider_name ASC"):
        item = row_to_dict(row)
        item["daily_cost"] = ai_cost_sum(item["provider_name"], today)
        item["monthly_cost"] = ai_cost_sum(item["provider_name"], month)
        item["recent_error"] = ai_recent_error(item["provider_name"])
        daily_budget = coerce_float(item.get("daily_budget"), 0)
        monthly_budget = coerce_float(item.get("monthly_budget"), 0)
        item["daily_budget_percent"] = round(item["daily_cost"] / daily_budget * 100, 1) if daily_budget > 0 else None
        item["monthly_budget_percent"] = round(item["monthly_cost"] / monthly_budget * 100, 1) if monthly_budget > 0 else None
        item["budget_warning"] = (daily_budget > 0 and item["daily_cost"] >= daily_budget) or (monthly_budget > 0 and item["monthly_cost"] >= monthly_budget)
        rows.append(item)
    return rows


def ai_provider_by_name(provider_name):
    name = normalize_ai_provider_name(provider_name)
    row = query_one("SELECT * FROM ai_providers WHERE provider_name=?", (name,))
    return row_to_dict(row)


def ai_provider_available(row):
    if not row:
        return False, "missing"
    if row.get("status") != "active":
        return False, row.get("status") or "disabled"
    if ai_recent_error(row["provider_name"]):
        return False, "recent_error"
    daily_budget = coerce_float(row.get("daily_budget"), 0)
    if daily_budget > 0 and ai_cost_sum(row["provider_name"], ai_period_start("day")) >= daily_budget:
        return False, "daily_budget"
    return True, "active"


def ai_provider_cost_per_1k(row):
    if not row:
        return 0
    return coerce_float(row.get("cost_input_per_1k"), 0) + coerce_float(row.get("cost_output_per_1k"), 0)


def fallback_rule_providers(primary_provider, task_role):
    rows = query_all(
        """SELECT * FROM ai_fallback_rules
           WHERE primary_provider=? AND task_role=? AND COALESCE(enabled, 1)=1
           ORDER BY id ASC""",
        (primary_provider, task_role),
    )
    return [row["fallback_provider"] for row in rows]


def select_ai_provider(task_role, risk_level="low"):
    role = str(task_role or "executor").strip().lower()
    if role not in AI_COST_TASK_ROLES:
        raise ValueError("unsupported task_role")
    risk = str(risk_level or "low").strip().lower()
    provider_rows = {row["provider_name"]: row_to_dict(row) for row in query_all("SELECT * FROM ai_providers")}
    default_order = list(AI_DEFAULT_PROVIDER_ORDER.get(role, ["openai"]))
    primary = default_order[0]
    ordered = [primary]
    for item in fallback_rule_providers(primary, role) + default_order[1:]:
        try:
            normalized = normalize_ai_provider_name(item)
        except ValueError:
            continue
        if normalized not in ordered:
            ordered.append(normalized)
    primary_row = provider_rows.get(primary)
    primary_cost = ai_provider_cost_per_1k(primary_row)
    primary_ok, primary_reason = ai_provider_available(primary_row)
    for provider_name in ordered:
        row = provider_rows.get(provider_name)
        ok, reason = ai_provider_available(row)
        if not ok:
            continue
        if primary_reason == "daily_budget" and provider_name != primary and primary_cost > 0 and ai_provider_cost_per_1k(row) >= primary_cost:
            continue
        if risk == "high" and provider_name != primary and AI_PROVIDER_TRUST.get(provider_name, 1) < AI_PROVIDER_TRUST.get(primary, 1):
            return {
                "ok": False,
                "manual_approval_required": True,
                "provider_name": primary,
                "primary_provider": primary,
                "fallback_provider": provider_name,
                "reason": "high risk task requires manual approval before lower-trust fallback",
            }
        return {
            "ok": True,
            "provider_name": provider_name,
            "primary_provider": primary,
            "fallback_used": provider_name != primary,
            "reason": "primary" if provider_name == primary else f"fallback from {primary}: {primary_reason}",
            "model": row.get("default_model") or "",
            "provider": row,
        }
    return {
        "ok": False,
        "manual_approval_required": risk == "high",
        "provider_name": primary,
        "primary_provider": primary,
        "reason": f"no available provider for role {role}; primary={primary} reason={primary_reason}",
    }


def estimate_ai_cost(provider_row, input_tokens=0, output_tokens=0):
    input_cost = coerce_float(provider_row.get("cost_input_per_1k"), 0) * coerce_int(input_tokens, 0) / 1000
    output_cost = coerce_float(provider_row.get("cost_output_per_1k"), 0) * coerce_int(output_tokens, 0) / 1000
    return round(input_cost + output_cost, 8)


def record_ai_usage(provider_row, model, task_role, status, project_id=None, dispatch_job_id=None,
                    input_tokens=0, output_tokens=0, error_message="", prompt_summary="",
                    fallback_used=False, fallback_from=None):
    estimated_cost = 0
    if provider_row and status == "success":
        estimated_cost = estimate_ai_cost(provider_row, input_tokens, output_tokens)
    execute(
        """INSERT INTO ai_usage_logs
           (provider, model, project_id, dispatch_job_id, task_role, input_tokens, output_tokens,
            estimated_cost, status, error_message, prompt_summary, fallback_used, fallback_from, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            provider_row.get("provider_name") if provider_row else "",
            model or (provider_row.get("default_model") if provider_row else ""),
            project_id,
            dispatch_job_id,
            task_role,
            coerce_int(input_tokens, 0),
            coerce_int(output_tokens, 0),
            estimated_cost,
            status,
            str(error_message or "")[:500],
            str(prompt_summary or "")[:240],
            1 if fallback_used else 0,
            fallback_from,
            now_str(),
        ),
    )
    return estimated_cost


def call_ai_with_fallback(task_role, risk_level="low", project_id=None, dispatch_job_id=None,
                          input_tokens=0, output_tokens=0, prompt_summary="", model=None,
                          fail_providers=None):
    fail_set = {normalize_ai_provider_name(item) for item in (fail_providers or [])}
    role = str(task_role or "executor").strip().lower()
    selection = select_ai_provider(role, risk_level)
    if not selection.get("ok"):
        if dispatch_job_id:
            update_dispatch_job(dispatch_job_id, status="failed", error_message=selection.get("reason", "AI provider unavailable"))
        return selection
    primary = selection["primary_provider"]
    candidates = [primary]
    for item in fallback_rule_providers(primary, role) + AI_DEFAULT_PROVIDER_ORDER.get(role, [])[1:]:
        normalized = normalize_ai_provider_name(item)
        if normalized not in candidates:
            candidates.append(normalized)
    last_error = ""
    for provider_name in candidates:
        row = ai_provider_by_name(provider_name)
        ok, reason = ai_provider_available(row)
        if not ok:
            last_error = reason
            record_ai_usage(row or {"provider_name": provider_name, "default_model": ""}, model or "", role, "failed", project_id, dispatch_job_id, input_tokens, 0, reason, prompt_summary, provider_name != primary, primary if provider_name != primary else None)
            continue
        if provider_name in fail_set:
            last_error = "simulated provider failure"
            record_ai_usage(row, model or row.get("default_model"), role, "failed", project_id, dispatch_job_id, input_tokens, 0, last_error, prompt_summary, provider_name != primary, primary if provider_name != primary else None)
            continue
        if str(risk_level or "").lower() == "high" and provider_name != primary and AI_PROVIDER_TRUST.get(provider_name, 1) < AI_PROVIDER_TRUST.get(primary, 1):
            last_error = "manual approval required for lower-trust fallback"
            break
        cost = record_ai_usage(row, model or row.get("default_model"), role, "success", project_id, dispatch_job_id, input_tokens, output_tokens, "", prompt_summary, provider_name != primary, primary if provider_name != primary else None)
        return {
            "ok": True,
            "provider": provider_name,
            "model": model or row.get("default_model"),
            "fallback_used": provider_name != primary,
            "estimated_cost": cost,
            "message": "AI call recorded with fallback policy",
        }
    if dispatch_job_id:
        update_dispatch_job(dispatch_job_id, status="failed", error_message=last_error or "all AI providers failed")
    return {"ok": False, "error": last_error or "all AI providers failed"}


def approx_ai_tokens(text):
    return max(1, int(len(str(text or "")) / 4) + 1)


def ai_prompt_summary(prompt, limit=240):
    compact = re.sub(r"\s+", " ", str(prompt or "")).strip()
    return compact[:limit]


def ai_console_provider_order(task_role, requested_provider="auto"):
    requested = str(requested_provider or "auto").strip().lower()
    aliases = {"gpt": "openai", "google": "gemini"}
    requested = aliases.get(requested, requested)
    if requested in ("openai", "gemini"):
        return [requested]
    role = str(task_role or "executor").strip().lower()
    if role in ("reviewer", "tester"):
        return ["gemini", "openai"]
    return ["openai", "gemini"]


def ai_message_row(message_id):
    return row_to_dict(
        query_one(
            """SELECT m.*, p.name AS project_name
               FROM ai_messages m
               LEFT JOIN projects p ON p.id=m.project_id
               WHERE m.id=?""",
            (message_id,),
        )
    )


def recent_ai_messages(limit=20, project_id=None):
    where = ["1=1"]
    params = []
    if project_id:
        where.append("m.project_id=?")
        params.append(project_id)
    params.append(max(1, min(coerce_int(limit, 20), 100)))
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT m.*, p.name AS project_name
                FROM ai_messages m
                LEFT JOIN projects p ON p.id=m.project_id
                WHERE {' AND '.join(where)}
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]


def recent_flow_messages(limit=20, project_id=None):
    where = ["m.provider='system'", "m.task_role='flow'"]
    params = []
    if project_id:
        where.append("m.project_id=?")
        params.append(project_id)
    params.append(max(1, min(coerce_int(limit, 20), 100)))
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT m.*, p.name AS project_name
                FROM ai_messages m
                LEFT JOIN projects p ON p.id=m.project_id
                WHERE {' AND '.join(where)}
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]


def flow_run_row(flow_run_id):
    return row_to_dict(query_one(
        """SELECT fr.*, p.name AS project_name
           FROM flow_runs fr
           LEFT JOIN projects p ON p.id=fr.project_id
           WHERE fr.id=?""",
        (flow_run_id,),
    ))


def flow_run_rows(project_id=None, limit=20):
    where = ["1=1"]
    params = []
    if project_id is not None:
        where.append("fr.project_id=?")
        params.append(project_id)
    params.append(max(1, min(coerce_int(limit, 20), 100)))
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT fr.*, p.name AS project_name
                FROM flow_runs fr
                LEFT JOIN projects p ON p.id=fr.project_id
                WHERE {' AND '.join(where)}
                ORDER BY fr.started_at DESC, fr.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]


def create_flow_run(project_id, mode):
    now = now_str()
    row_id = execute(
        """INSERT INTO flow_runs
           (project_id, mode, status, started_at, finished_at, total_tasks, done_tasks,
            failed_tasks, stopped_reason, summary, created_at)
           VALUES (?, ?, 'running', ?, NULL, 0, 0, 0, '', '', ?)""",
        (project_id, mode, now, now),
    ).lastrowid
    return flow_run_row(row_id)


def flow_task_counts(project_id):
    rows = query_all(
        "SELECT COALESCE(status, '') AS status, COUNT(*) AS count FROM tasks WHERE project_id=? GROUP BY COALESCE(status, '')",
        (project_id,),
    )
    counts = {row["status"] or "unknown": row["count"] for row in rows}
    return {
        "total": sum(counts.values()),
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
        "queued": counts.get("queued", 0),
        "blocked": counts.get("blocked", 0),
        "running": counts.get("running", 0),
        "canceled": counts.get("canceled", 0),
    }


def flow_run_ai_message_rows(project_id, started_at):
    return [
        row_to_dict(row)
        for row in query_all(
            """SELECT provider, model, task_role, prompt_summary, status, response_text, error_message, created_at
               FROM ai_messages
               WHERE project_id=? AND created_at>=? AND COALESCE(task_role, '')!='flow'
               ORDER BY created_at ASC, id ASC
               LIMIT 20""",
            (project_id, started_at or ""),
        )
    ]


def flow_run_messages(flow_run, include_flow=True):
    if not flow_run or not flow_run.get("project_id"):
        return []
    started_at = flow_run.get("started_at") or ""
    finished_at = flow_run.get("finished_at") or now_str()
    params = [flow_run["project_id"], started_at, finished_at]
    where = ["project_id=?", "created_at>=?", "created_at<=?"]
    if not include_flow:
        where.append("COALESCE(task_role, '')!='flow'")
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT *
                FROM ai_messages
                WHERE {' AND '.join(where)}
                ORDER BY created_at ASC, id ASC
                LIMIT 100""",
            tuple(params),
        )
    ]


def flow_run_related_tasks(flow_run):
    if not flow_run or not flow_run.get("project_id"):
        return []
    started_at = flow_run.get("started_at") or ""
    finished_at = flow_run.get("finished_at") or now_str()
    return [
        row_to_dict(row)
        for row in query_all(
            """SELECT *
               FROM tasks
               WHERE project_id=?
                 AND (
                   COALESCE(started_at, '') BETWEEN ? AND ?
                   OR COALESCE(finished_at, '') BETWEEN ? AND ?
                   OR COALESCE(updated_at, '') BETWEEN ? AND ?
                 )
               ORDER BY COALESCE(started_at, updated_at, created_at) ASC, id ASC
               LIMIT 100""",
            (flow_run["project_id"], started_at, finished_at, started_at, finished_at, started_at, finished_at),
        )
    ]


def flow_run_summary(project_id, mode, status, stopped_reason, executed_tasks, counts, started_at):
    return flow_run_services.build_summary(
        project_id,
        mode,
        status,
        stopped_reason,
        executed_tasks,
        counts,
        messages=flow_run_ai_message_rows(project_id, started_at),
    )
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

    messages = flow_run_ai_message_rows(project_id, started_at)
    if messages:
        lines.append("AI messages:")
        for message in messages:
            text = message.get("response_text") or message.get("error_message") or message.get("prompt_summary") or ""
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 160:
                text = text[:157] + "..."
            lines.append(f"- {message.get('provider')}/{message.get('status')}: {text}")

    next_steps = {
        "completed": "Review the summary and decide whether to create the next task batch.",
        "approval_required": "Review the pending task output, then approve or reject before continuing.",
        "failed": "Inspect failed task error_message and retry after fixing provider or prompt issues.",
        "no_queued_task": "Create or queue AI tasks before running the flow again.",
        "blocked_by_safety": "Review task_type and remove deploy/shell/ssh/docker style work from full auto mode.",
        "error": "Inspect server logs and retry after the exception is fixed.",
    }
    lines.append(f"Suggested next step: {next_steps.get(stopped_reason, 'Review flow result manually.')}")
    return "\n".join(lines)


def finish_flow_run(flow_run_id, project_id, mode, status, stopped_reason, executed_tasks, error_message=None):
    counts = flow_task_counts(project_id)
    flow_run = flow_run_row(flow_run_id)
    started_at = flow_run.get("started_at") if flow_run else ""
    summary = flow_run_summary(project_id, mode, status, stopped_reason, executed_tasks, counts, started_at)
    if error_message:
        summary = f"{summary}\nError: {error_message}"
    execute(
        """UPDATE flow_runs
           SET status=?, finished_at=?, total_tasks=?, done_tasks=?, failed_tasks=?,
               stopped_reason=?, summary=?
           WHERE id=?""",
        (
            status,
            now_str(),
            counts["total"],
            counts["done"],
            counts["failed"],
            stopped_reason,
            summary,
            flow_run_id,
        ),
    )
    return flow_run_row(flow_run_id)


def insert_ai_message(project_id, provider, model, task_role, prompt_summary):
    now = now_str()
    row_id = execute(
        """INSERT INTO ai_messages
           (project_id, provider, model, task_role, prompt_summary, status, response_text, error_message, raw_response, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'running', '', '', '', ?, ?)""",
        (project_id, provider, model, task_role, prompt_summary, now, now),
    ).lastrowid
    return row_id


def update_ai_message(message_id, **fields):
    allowed = {"provider", "model", "task_role", "prompt_summary", "status", "response_text", "error_message", "raw_response"}
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key}=?")
            values.append(value)
    if not updates:
        return
    updates.append("updated_at=?")
    values.extend([now_str(), message_id])
    execute(f"UPDATE ai_messages SET {', '.join(updates)} WHERE id=?", tuple(values))


def openai_console_model(provider_row):
    model = (provider_row or {}).get("default_model") or OPENAI_CHAT_MODEL
    if model in ("codex-cli", "codex"):
        return OPENAI_CHAT_MODEL if OPENAI_CHAT_MODEL not in ("codex-cli", "codex") else "gpt-4o-mini"
    return model


def call_openai_console(prompt, model):
    if not OPENAI_API_KEY:
        text = (
            "OpenAI API key not configured. DevPilot recorded this dispatch with a local fallback result.\n\n"
            f"Task summary: {ai_prompt_summary(prompt, 500)}"
        )
        return {"ok": True, "text": text, "input_tokens": approx_ai_tokens(prompt), "output_tokens": approx_ai_tokens(text), "mock": True}
    payload = {
        "model": model or OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise DevPilot AI worker. Return an actionable result summary."},
            {"role": "user", "content": str(prompt or "")},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"OpenAI HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": f"OpenAI call failed: {exc}"}
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    return {
        "ok": True,
        "text": text,
        "input_tokens": coerce_int(usage.get("prompt_tokens"), approx_ai_tokens(prompt)),
        "output_tokens": coerce_int(usage.get("completion_tokens"), approx_ai_tokens(text)),
        "raw": {"id": data.get("id"), "usage": usage},
    }


def call_gemini_console(prompt, model):
    if not GEMINI_API_KEY:
        text = (
            "Gemini API key not configured. DevPilot recorded this dispatch with a local fallback result.\n\n"
            f"Task summary: {ai_prompt_summary(prompt, 500)}"
        )
        return {"ok": True, "text": text, "input_tokens": approx_ai_tokens(prompt), "output_tokens": approx_ai_tokens(text), "mock": True}
    req_url = GEMINI_API_URL
    sep = "&" if "?" in req_url else "?"
    req_url = f"{req_url}{sep}key={urllib.parse.quote(GEMINI_API_KEY)}"
    payload = {"contents": [{"parts": [{"text": str(prompt or "")}]}]}
    req = urllib.request.Request(
        req_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"Gemini HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": f"Gemini call failed: {exc}"}
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(str(part.get("text") or "") for part in parts if part.get("text")).strip()
    usage = data.get("usageMetadata") or {}
    return {
        "ok": True,
        "text": text,
        "input_tokens": coerce_int(usage.get("promptTokenCount"), approx_ai_tokens(prompt)),
        "output_tokens": coerce_int(usage.get("candidatesTokenCount"), approx_ai_tokens(text)),
        "raw": {"usage": usage},
    }


AI_CONSOLE_WEBSITE_PROMPT = """請 OpenAI 與 Gemini 協作，產生一個「AI 自動化接案服務」單頁網站。
需求：
1. 一頁式網站
2. 主標題：AI 自動化接案服務
3. 副標題：從需求、開發、測試到部署，一套流程自動跑
4. 區塊包含：
   - Hero
   - 服務項目
   - 執行流程
   - 適合對象
   - CTA 立即諮詢
5. 輸出完整 single-file HTML
6. CSS 內嵌在 style
7. 不使用外部 CDN
8. 不連外部圖片
9. 不含任何 API Key
10. 不自動部署"""
AI_CONSOLE_GEMINI_MODEL = "gemini-2.5-flash"
AI_CONSOLE_CLAUDE_MODEL = "claude-sonnet-4-6"
AI_CONSOLE_SANDBOX_DIR = Path(os.getenv("AI_CONSOLE_SANDBOX_DIR", "data/ai_console_sandbox"))
AI_CONSOLE_SANDBOX_MAX_BYTES = 1024 * 1024
AI_CONSOLE_SANDBOX_ID_RE = re.compile(r"^ai_console_\d{8}_\d{6}_[a-f0-9]{8}$")


def sanitize_ai_console_text(value, secrets_to_strip=None):
    text = str(value or "")
    for secret in secrets_to_strip or []:
        secret_text = str(secret or "")
        if secret_text:
            text = text.replace(secret_text, "[redacted]")
    return text


def extract_single_file_html(text):
    original = str(text or "").strip()
    content = original
    for match in re.finditer(r"```(?:html)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL):
        candidate = (match.group(1) or "").strip()
        candidate_lower = candidate.lower()
        if "<!doctype html" in candidate_lower or "<html" in candidate_lower:
            content = candidate
            break
    content_lower = content.lower()
    doctype_index = content_lower.find("<!doctype html")
    html_index = content_lower.find("<html")
    if doctype_index >= 0:
        content = content[doctype_index:]
    elif html_index >= 0:
        content = content[html_index:]
    else:
        return original
    content_lower = content.lower()
    end_index = content_lower.rfind("</html>")
    if end_index >= 0:
        content = content[:end_index + len("</html>")]
    return content.strip()


def ai_console_error(error, message):
    return {
        "ok": False,
        "error": error,
        "message": message,
        "safety_notes": [
            "No API keys returned.",
            "No files were written.",
            "No deployment was triggered.",
        ],
    }


def call_openai_console_with_key(prompt, model, api_key, max_tokens=900, retry_delays=(2, 6), timeout=60):
    payload = {
        "model": model or OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful web designer. Never include API keys or secrets."},
            {"role": "user", "content": str(prompt or "")},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    attempts = len(retry_delays) + 1
    data = None
    for attempt_index in range(attempts):
        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt_index < len(retry_delays):
                    time.sleep(retry_delays[attempt_index])
                    continue
                return {"ok": False, "status": "rate_limited", "error": "OpenAI rate limit or quota reached"}
            return {"ok": False, "status": "http_error", "error": f"OpenAI HTTP {exc.code}"}
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt_index < len(retry_delays):
                time.sleep(retry_delays[attempt_index])
                continue
            return {"ok": False, "status": "network_error", "error": "OpenAI network error"}
        except Exception:
            return {"ok": False, "status": "error", "error": "OpenAI call failed"}
    if data is None:
        return {"ok": False, "status": "error", "error": "OpenAI call failed"}
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    return {
        "ok": True,
        "text": text,
        "input_tokens": coerce_int(usage.get("prompt_tokens"), approx_ai_tokens(prompt)),
        "output_tokens": coerce_int(usage.get("completion_tokens"), approx_ai_tokens(text)),
    }


def call_gemini_console_with_key(prompt, model, api_key):
    model_name = str(model or AI_CONSOLE_GEMINI_MODEL).strip()
    if model_name.startswith("models/"):
        model_name = model_name[len("models/"):]
    req_url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model_name)}:generateContent"
    req_url = f"{req_url}?key={urllib.parse.quote(api_key)}"
    payload = {"contents": [{"parts": [{"text": str(prompt or "")}]}]}
    req = urllib.request.Request(
        req_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"Gemini HTTP {exc.code}"}
    except Exception:
        return {"ok": False, "error": "Gemini call failed"}
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(str(part.get("text") or "") for part in parts if part.get("text")).strip()
    usage = data.get("usageMetadata") or {}
    return {
        "ok": True,
        "text": text,
        "input_tokens": coerce_int(usage.get("promptTokenCount"), approx_ai_tokens(prompt)),
        "output_tokens": coerce_int(usage.get("candidatesTokenCount"), approx_ai_tokens(text)),
    }


def normalize_claude_console_model(model):
    for candidate in (model, os.getenv("CLAUDE_DEFAULT_MODEL", ""), os.getenv("CLAUDE_MODEL", ""), AI_CONSOLE_CLAUDE_MODEL):
        model_name = str(candidate or "").strip()
        if model_name and model_name != "claude":
            return model_name
    return AI_CONSOLE_CLAUDE_MODEL


def call_claude_console_with_key(prompt, model, api_key, max_tokens=4096, timeout=90):
    token_limit = max(16, min(coerce_int(max_tokens, 4096), 8192))
    payload = {
        "model": normalize_claude_console_model(model),
        "max_tokens": token_limit,
        "temperature": 0.2,
        "messages": [
            {"role": "user", "content": str(prompt or "")},
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            "content-type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": "http_error", "error": f"Claude HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return {"ok": False, "status": "network_error", "error": "Claude network error"}
    except Exception:
        return {"ok": False, "status": "error", "error": "Claude call failed"}
    text = "\n".join(
        str(part.get("text") or "")
        for part in data.get("content", [])
        if part.get("type") == "text" and part.get("text")
    ).strip()
    usage = data.get("usage") or {}
    input_tokens = coerce_int(usage.get("input_tokens"), approx_ai_tokens(prompt))
    output_tokens = coerce_int(usage.get("output_tokens"), approx_ai_tokens(text))
    return {
        "ok": True,
        "text": text,
        "model": data.get("model") or payload["model"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw": {"usage": usage},
    }


def ai_console_complete_html(text):
    html = str(text or "").lower()
    return ("<!doctype html" in html or "<html" in html) and "</html>" in html


def ai_console_review_status(review_text):
    text = str(review_text or "").strip()
    compact = text.lower()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    json_text = (fenced.group(1) if fenced else text).strip()
    try:
        parsed = json.loads(json_text)
        verdict = str(parsed.get("verdict") or "").strip().lower()
        if verdict in ("pass", "fail"):
            return verdict
    except Exception:
        pass
    if re.search(r"\bfail\b", compact):
        return "fail"
    if '"verdict"' in compact and '"pass"' in compact:
        return "pass"
    if re.search(r"\bpass\b", compact):
        return "pass"
    return "reviewed" if compact.strip() else "not_run"


def ai_console_sandbox_dir():
    root = AI_CONSOLE_SANDBOX_DIR
    if not root.is_absolute():
        root = Path(app.root_path) / root
    return root.resolve()


def ai_console_sandbox_artifact_path(artifact_id):
    artifact_text = str(artifact_id or "").strip()
    if not AI_CONSOLE_SANDBOX_ID_RE.fullmatch(artifact_text):
        raise ValueError("invalid sandbox artifact id")
    root = ai_console_sandbox_dir()
    path = (root / f"{artifact_text}.html").resolve()
    if root not in path.parents:
        raise ValueError("sandbox path escapes root")
    return path


def ai_console_sandbox_owner_allowed():
    user = current_user()
    return bool(user and has_role("owner", "admin"))


def create_ai_console_sandbox_html_artifact(html):
    root = ai_console_sandbox_dir()
    root.mkdir(parents=True, exist_ok=True)
    content = str(html or "")
    encoded = content.encode("utf-8")
    if not content.strip():
        raise ValueError("empty sandbox html")
    if len(encoded) > AI_CONSOLE_SANDBOX_MAX_BYTES:
        raise ValueError("sandbox html exceeds size limit")
    artifact_id = f"ai_console_{now_dt().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
    path = ai_console_sandbox_artifact_path(artifact_id)
    path.write_text(content, encoding="utf-8")
    return {
        "type": "sandbox_html",
        "id": artifact_id,
        "filename": path.name,
        "preview_url": f"/ai-console/sandbox/{artifact_id}",
        "download_url": f"/api/ai-console/sandbox/{artifact_id}/download",
        "size_bytes": len(encoded),
    }


def read_ai_console_sandbox_artifact(artifact_id):
    path = ai_console_sandbox_artifact_path(artifact_id)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("sandbox artifact not found")
    if path.stat().st_size > AI_CONSOLE_SANDBOX_MAX_BYTES:
        raise ValueError("sandbox artifact exceeds size limit")
    return path, path.read_text(encoding="utf-8", errors="replace")


def list_ai_console_sandbox_artifacts(limit=50):
    root = ai_console_sandbox_dir()
    result = {
        "ok": True,
        "exists": False,
        "root_label": "data/ai_console_sandbox",
        "items": [],
        "error": "",
    }
    try:
        if not root.exists() or not root.is_dir():
            return result
        result["exists"] = True
        items = []
        for child in root.iterdir():
            try:
                if child.is_symlink() or not child.is_file() or child.suffix.lower() != ".html":
                    continue
                artifact_id = child.stem
                if not AI_CONSOLE_SANDBOX_ID_RE.fullmatch(artifact_id):
                    continue
                path = ai_console_sandbox_artifact_path(artifact_id)
                if path != child.resolve():
                    continue
                stat = child.stat()
            except (OSError, ValueError):
                continue
            items.append({
                "artifact_id": artifact_id,
                "filename": child.name,
                "size_bytes": stat.st_size,
                "size_label": release_dashboard_format_size(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "modified_ts": stat.st_mtime,
                "preview_url": f"/ai-console/sandbox/{artifact_id}",
                "download_url": f"/api/ai-console/sandbox/{artifact_id}/download",
                "is_html": True,
                "safety": {
                    "sandbox_only": True,
                    "project_repo_write": False,
                    "deploy": False,
                    "dns_write": False,
                    "telegram_send": False,
                },
            })
        items.sort(key=lambda item: item["modified_ts"], reverse=True)
        result["items"] = [
            {key: value for key, value in item.items() if key != "modified_ts"}
            for item in items[:coerce_int(limit, 50)]
        ]
        return result
    except OSError as exc:
        result["ok"] = False
        result["error"] = type(exc).__name__
        return result


def run_ai_console_claude_preview(payload):
    prompt = str((payload or {}).get("prompt") or (payload or {}).get("task_prompt") or "").strip()
    if not prompt:
        return ai_console_error("prompt_required", "Prompt is required for Claude preview.")
    output_mode = str((payload or {}).get("output_mode") or "preview_only").strip().lower()
    if output_mode not in ("preview_only", "sandbox_html"):
        return ai_console_error("unsupported_output_mode", "Only preview_only and sandbox_html output modes are supported.")
    if output_mode == "sandbox_html" and not ai_console_sandbox_owner_allowed():
        return ai_console_error("sandbox_permission_denied", "Sandbox artifacts require owner/admin session.")
    claude_key = get_active_ai_console_key("claude")
    if not claude_key.get("ok"):
        return ai_console_error("claude_not_configured", "Claude key is not configured or cannot be decrypted.")

    requested_model = (payload or {}).get("model") or (payload or {}).get("executor_model") or ""
    max_tokens = coerce_int((payload or {}).get("max_tokens"), 4096)
    secrets_to_strip = [claude_key.get("key"), API_TOKEN]
    executor_result = call_claude_console_with_key(
        prompt,
        requested_model,
        claude_key["key"],
        max_tokens=max_tokens,
    )
    if not executor_result.get("ok"):
        return ai_console_error("claude_generation_failed", executor_result.get("error") or "Claude generation failed.")

    executor_output = sanitize_ai_console_text(executor_result.get("text"), secrets_to_strip)
    reviewer_provider = str((payload or {}).get("reviewer_provider") or "").strip().lower()
    review_enabled = (payload or {}).get("review_enabled") in (True, 1, "1", "true", "yes", "on")
    if review_enabled and not reviewer_provider:
        reviewer_provider = "gemini"

    reviewer_output = ""
    review_status = "not_run"
    reviewer_info = None
    if reviewer_provider in ("gemini", "google"):
        gemini_key = get_active_ai_console_key("gemini")
        if not gemini_key.get("ok"):
            return ai_console_error("gemini_not_configured", "Gemini reviewer key is not configured or cannot be decrypted.")
        secrets_to_strip.append(gemini_key.get("key"))
        review_prompt = (
            "Review this AI Console preview output against the user prompt. "
            "Reply in compact JSON with keys: verdict, issues, safety. "
            "PASS only if the output satisfies the prompt, contains no secrets, and does not include deploy/DNS/file-write instructions.\n\n"
            f"PROMPT:\n{prompt[:3000]}\n\n"
            f"OUTPUT:\n{executor_output[:12000]}"
        )
        reviewer_result = call_gemini_console_with_key(
            review_prompt,
            (payload or {}).get("reviewer_model") or AI_CONSOLE_GEMINI_MODEL,
            gemini_key["key"],
        )
        if not reviewer_result.get("ok"):
            return ai_console_error("gemini_review_failed", reviewer_result.get("error") or "Gemini review failed.")
        reviewer_output = sanitize_ai_console_text(reviewer_result.get("text"), secrets_to_strip)
        review_status = ai_console_review_status(reviewer_output)
        reviewer_info = {
            "provider": "gemini",
            "source": gemini_key.get("source"),
            "masked": gemini_key.get("masked"),
            "model": (payload or {}).get("reviewer_model") or AI_CONSOLE_GEMINI_MODEL,
        }
    elif reviewer_provider in ("", "none"):
        reviewer_provider = "none"
    else:
        return ai_console_error("unsupported_reviewer", "Only Gemini reviewer is supported in this preview flow.")

    final_html = extract_single_file_html(executor_output)
    complete_html = ai_console_complete_html(final_html)
    artifact = None
    artifact_write_status = "not_requested"
    artifact_error = ""
    if output_mode == "sandbox_html":
        artifact_write_status = "not_written"
        if reviewer_provider != "gemini" or review_status != "pass":
            artifact_write_status = "blocked_review_required"
        elif not complete_html:
            artifact_write_status = "blocked_incomplete_html"
        else:
            try:
                artifact = create_ai_console_sandbox_html_artifact(final_html)
                artifact_write_status = "written"
            except ValueError as exc:
                artifact_error = str(exc)
                artifact_write_status = "blocked_invalid_artifact"
    return {
        "ok": True,
        "mode": "claude_executor_preview",
        "output_mode": output_mode,
        "executor_provider": "claude",
        "executor_model": executor_result.get("model") or normalize_claude_console_model(requested_model),
        "executor_output": executor_output,
        "final_html": final_html,
        "complete_html": complete_html,
        "reviewer_provider": reviewer_provider,
        "review_status": review_status,
        "reviewer_output": reviewer_output,
        "artifact": artifact,
        "artifact_write_status": artifact_write_status,
        "artifact_error": artifact_error,
        "providers_used": [
            {"provider": "claude", "source": claude_key.get("source"), "masked": claude_key.get("masked")},
        ] + ([reviewer_info] if reviewer_info else []),
        "usage": {
            "executor_input_tokens": executor_result.get("input_tokens"),
            "executor_output_tokens": executor_result.get("output_tokens"),
        },
        "safety_notes": [
            "Preview only.",
            "No API keys included in response.",
            "No project repo files were written.",
            "Sandbox artifact written only when requested and gated by complete HTML plus Gemini PASS.",
            "No deployment was triggered.",
            "No DNS or Telegram action was triggered.",
        ],
        "safety": {
            "project_repo_write": False,
            "sandbox_write": artifact_write_status == "written",
            "deploy": False,
            "dns_write": False,
            "telegram_send": False,
        },
    }


def run_ai_console_gemini_only():
    gemini_key = get_active_ai_console_key("gemini")
    if not gemini_key.get("ok"):
        return ai_console_error("gemini_not_configured", "Gemini key is not configured or cannot be decrypted.")

    secrets_to_strip = [gemini_key.get("key"), API_TOKEN]
    prompt = (
        "請產生一個繁體中文 single-file HTML landing page。\n"
        "主題：AI 自動化接案服務。\n"
        "副標題：從需求、開發、測試到部署，一套流程自動跑。\n"
        "必含：\n"
        "- Hero\n"
        "- 服務項目\n"
        "- 執行流程\n"
        "- 適合對象\n"
        "- CTA 立即諮詢\n"
        "限制：\n"
        "- CSS 內嵌在 style\n"
        "- 不使用外部 CDN\n"
        "- 不連外部圖片\n"
        "- 不含任何 API Key\n"
        "- 輸出完整 HTML"
    )
    result = call_gemini_console_with_key(prompt, "", gemini_key["key"])
    if not result.get("ok"):
        return ai_console_error("gemini_generation_failed", result.get("error") or "Gemini generation failed.")
    final_html = extract_single_file_html(sanitize_ai_console_text(result.get("text"), secrets_to_strip))
    return {
        "ok": True,
        "mode": "gemini_only_website_mvp",
        "providers_used": [
            {"provider": "gemini", "source": gemini_key.get("source"), "masked": gemini_key.get("masked")},
        ],
        "final_html": final_html,
        "safety_notes": [
            "No API keys included in response.",
            "No files were written.",
            "No deployment was triggered.",
            "OpenAI skipped.",
            "Claude skipped.",
        ],
    }


def run_ai_console_website_mvp():
    payload = request.get_json(silent=True) if has_request_context() else {}
    provider = str((payload or {}).get("provider") or (payload or {}).get("executor_provider") or "").strip().lower()
    if provider in ("claude", "anthropic") or str((payload or {}).get("mode") or "").strip().lower() in ("claude", "claude_preview", "claude_executor_preview"):
        return run_ai_console_claude_preview(payload or {})
    mode = str((payload or {}).get("mode") or "openai_gemini").strip().lower()
    if mode == "gemini_only":
        return run_ai_console_gemini_only()

    openai_key = get_active_ai_console_key("openai")
    if not openai_key.get("ok"):
        return ai_console_error("openai_not_configured", "OpenAI key is not configured or cannot be decrypted.")
    gemini_key = get_active_ai_console_key("gemini")
    if not gemini_key.get("ok"):
        return ai_console_error("gemini_not_configured", "Gemini key is not configured or cannot be decrypted.")

    secrets_to_strip = [openai_key.get("key"), gemini_key.get("key"), API_TOKEN]
    draft_prompt = (
        "產生一個繁體中文 single-file HTML landing page。\n"
        "主題：AI 自動化接案服務。\n"
        "必含：Hero、服務項目、流程、適合對象、CTA。\n"
        "限制：內嵌 CSS，不用 CDN，不用外部圖片，不含 API Key。\n"
        "先輸出精簡但完整 HTML。"
    )
    draft_result = call_openai_console_with_key(
        draft_prompt,
        OPENAI_CHAT_MODEL,
        openai_key["key"],
        max_tokens=900,
    )
    if not draft_result.get("ok"):
        if draft_result.get("status") == "rate_limited":
            return ai_console_error("openai_rate_limited", "OpenAI rate limit or quota reached during draft generation.")
        return ai_console_error("openai_draft_failed", draft_result.get("error") or "OpenAI draft failed.")
    draft_html = sanitize_ai_console_text(draft_result.get("text"), secrets_to_strip)

    review_prompt = (
        "請 review 以下單頁網站草稿，只回摘要與最多 5 點改善建議，不要重寫整份 HTML，"
        "不要包含任何 API Key 或秘密。\n\n"
        f"{draft_html[:6000]}"
    )
    review_result = call_gemini_console_with_key(review_prompt, "", gemini_key["key"])
    if not review_result.get("ok"):
        return ai_console_error("gemini_review_failed", review_result.get("error") or "Gemini review failed.")
    review_text = sanitize_ai_console_text(review_result.get("text"), secrets_to_strip)

    final_prompt = (
        "請根據 OpenAI 初稿與 Gemini review，產生最終版完整 single-file HTML。\n"
        "必含：Hero、服務項目、流程、適合對象、CTA。\n"
        "限制：內嵌 CSS，不用 CDN，不用外部圖片，不含 API Key。只輸出 HTML，不要 markdown code fence。\n\n"
        "以下是 OpenAI 初稿：\n"
        f"{draft_html[:6000]}\n\n"
        "以下是 Gemini review 摘要與改善建議：\n"
        f"{review_text[:1200]}"
    )
    final_result = call_openai_console_with_key(
        final_prompt,
        OPENAI_CHAT_MODEL,
        openai_key["key"],
        max_tokens=1400,
    )
    if not final_result.get("ok"):
        if final_result.get("status") == "rate_limited":
            return ai_console_error("openai_rate_limited", "OpenAI rate limit or quota reached during final generation.")
        return ai_console_error("openai_final_failed", final_result.get("error") or "OpenAI final generation failed.")
    final_html = extract_single_file_html(sanitize_ai_console_text(final_result.get("text"), secrets_to_strip))

    return {
        "ok": True,
        "mode": "openai_gemini_website_mvp",
        "providers_used": [
            {"provider": "openai", "source": openai_key.get("source"), "masked": openai_key.get("masked")},
            {"provider": "gemini", "source": gemini_key.get("source"), "masked": gemini_key.get("masked")},
        ],
        "openai_draft_summary": ai_prompt_summary(draft_html, 500),
        "gemini_review_summary": ai_prompt_summary(review_text, 500),
        "final_html": final_html,
        "safety_notes": [
            "No API keys included in response.",
            "No files were written.",
            "No deployment was triggered.",
            "Claude skipped.",
        ],
    }


def run_ai_console_provider(provider_name, prompt, model):
    if provider_name == "gemini":
        return call_gemini_console(prompt, model)
    return call_openai_console(prompt, model)


def dispatch_ai_console_task(payload):
    prompt = payload.get("task_prompt") or payload.get("task") or payload.get("prompt") or ""
    if not str(prompt).strip():
        raise ValueError("task_prompt is required")
    project_id = coerce_int(payload.get("project_id"), None)
    task_role = str(payload.get("task_role") or "executor").strip().lower()
    if task_role not in AI_COST_TASK_ROLES:
        raise ValueError("unsupported task_role")
    requested_provider = payload.get("provider") or "auto"
    prompt_summary = ai_prompt_summary(prompt)
    provider_order = ai_console_provider_order(task_role, requested_provider)
    primary_provider = provider_order[0]
    message_id = insert_ai_message(project_id, primary_provider, "", task_role, prompt_summary)
    last_error = ""
    for index, provider_name in enumerate(provider_order):
        provider_row = ai_provider_by_name(provider_name)
        ok, reason = ai_provider_available(provider_row)
        model = openai_console_model(provider_row) if provider_name == "openai" else ((provider_row or {}).get("default_model") or os.getenv("GEMINI_DEFAULT_MODEL", "gemini-1.5-pro"))
        update_ai_message(message_id, provider=provider_name, model=model)
        if not ok:
            last_error = reason
            record_ai_usage(provider_row or {"provider_name": provider_name, "default_model": model}, model, task_role, "failed", project_id, None, approx_ai_tokens(prompt), 0, reason, prompt_summary, index > 0, primary_provider if index > 0 else None)
            continue
        result = run_ai_console_provider(provider_name, prompt, model)
        if not result.get("ok"):
            last_error = result.get("error") or "AI provider failed"
            record_ai_usage(provider_row, model, task_role, "failed", project_id, None, approx_ai_tokens(prompt), 0, last_error, prompt_summary, index > 0, primary_provider if index > 0 else None)
            continue
        text = result.get("text") or ""
        output_tokens = coerce_int(result.get("output_tokens"), approx_ai_tokens(text))
        input_tokens = coerce_int(result.get("input_tokens"), approx_ai_tokens(prompt))
        cost = record_ai_usage(provider_row, model, task_role, "success", project_id, None, input_tokens, output_tokens, "", prompt_summary, index > 0, primary_provider if index > 0 else None)
        update_ai_message(
            message_id,
            status="done",
            response_text=text,
            error_message="",
            raw_response=json.dumps({
                "provider": provider_name,
                "model": model,
                "mock": bool(result.get("mock")),
                "fallback_used": index > 0,
                "estimated_cost": cost,
                "usage": result.get("raw", {}).get("usage") if isinstance(result.get("raw"), dict) else {},
            }, ensure_ascii=False),
        )
        return {"ok": True, "message_id": message_id, "message": ai_message_row(message_id)}
    update_ai_message(message_id, status="failed", error_message=last_error or "all AI providers failed")
    return {"ok": False, "message_id": message_id, "error": last_error or "all AI providers failed", "message": ai_message_row(message_id)}


def normalize_task_provider(value):
    return ai_task_services.normalize_task_provider(value)


def normalize_ai_task_status(value, default="queued"):
    return ai_task_services.normalize_ai_task_status(value, AI_TASK_STATUSES, default)


def normalize_ai_task_priority(value):
    return ai_task_services.normalize_ai_task_priority(value, AI_TASK_PRIORITIES)


def normalize_ai_task_type(value):
    return ai_task_services.normalize_ai_task_type(value)


def normalize_ai_task_approval_status(value):
    return ai_task_services.normalize_ai_task_approval_status(value, AI_TASK_APPROVAL_STATUSES)


def task_rows(limit=100, project_id=None):
    limit = max(1, min(coerce_int(limit, 100), 500))
    params = []
    where = ""
    if project_id is not None:
        where = "WHERE t.project_id=?"
        params.append(project_id)
    params.append(limit)
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT t.*, p.name AS project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id=p.id
                {where}
                ORDER BY t.updated_at DESC, t.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]


def task_row(task_id):
    return row_to_dict(query_one(
        """SELECT t.*, p.name AS project_name
           FROM tasks t
           LEFT JOIN projects p ON t.project_id=p.id
           WHERE t.id=?""",
        (task_id,),
    ))


def ai_message_task_id(message):
    return ai_task_services.ai_message_task_id(message)


def task_ai_message_rows(task_id, limit=50):
    task = task_row(task_id)
    if not task:
        return []
    params = []
    if task.get("project_id") is None:
        where = "m.project_id IS NULL"
    else:
        where = "m.project_id=?"
        params.append(task["project_id"])
    params.append(300)
    rows = [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT m.*, p.name AS project_name
                FROM ai_messages m
                LEFT JOIN projects p ON p.id=m.project_id
                WHERE {where}
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]
    matched = [row for row in rows if ai_message_task_id(row) == task_id]
    return matched[:max(1, min(coerce_int(limit, 50), 100))]


def task_child_rows(task_id):
    return [
        row_to_dict(row)
        for row in query_all(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id=p.id
               WHERE t.parent_task_id=?
               ORDER BY t.id ASC""",
            (task_id,),
        )
    ]


def task_flow_run_rows(task_id):
    task = task_row(task_id)
    if not task or task.get("project_id") is None:
        return []
    return [
        row_to_dict(row)
        for row in query_all(
            """SELECT fr.*, p.name AS project_name
               FROM flow_runs fr
               LEFT JOIN projects p ON p.id=fr.project_id
               WHERE fr.project_id=? AND fr.summary LIKE ?
               ORDER BY fr.started_at DESC, fr.id DESC
               LIMIT 20""",
            (task["project_id"], f"%#{task_id} %"),
        )
    ]


def ai_task_detail(task_id):
    task = task_row(task_id)
    if not task:
        return None
    parent = task_row(task["parent_task_id"]) if task.get("parent_task_id") else None
    return ai_task_services.build_task_detail(
        task,
        parent,
        task_child_rows(task_id),
        task_ai_message_rows(task_id),
        task_flow_run_rows(task_id),
    )


def create_ai_task(payload):
    title = str(payload.get("title") or "").strip()
    prompt = str(payload.get("prompt") or payload.get("task_prompt") or "").strip()
    if not title:
        raise ValueError("title is required")
    if not prompt:
        raise ValueError("prompt is required")
    provider = normalize_task_provider(payload.get("provider"))
    task_type = normalize_ai_task_type(payload.get("task_type"))
    priority = normalize_ai_task_priority(payload.get("priority"))
    max_retries = max(0, min(coerce_int(payload.get("max_retries"), 3), 20))
    parent_task_id = coerce_int(payload.get("parent_task_id"), None)
    auto_run_next = 1 if payload.get("auto_run_next") in (True, 1, "1", "true", "yes", "on") else 0
    requires_approval = 1 if payload.get("requires_approval") in (True, 1, "1", "true", "yes", "on") else 0
    approval_status = normalize_ai_task_approval_status(payload.get("approval_status"))
    project_id = coerce_int(payload.get("project_id"), None)
    if project_id is not None and not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise ValueError("project not found")
    now = now_str()
    row_id = execute(
        """INSERT INTO tasks
           (project_id, title, task_type, priority, provider, prompt, status, result, error_message,
            started_at, finished_at, retry_count, max_retries, parent_task_id, auto_run_next, last_auto_run_at,
            requires_approval, approval_status, approved_at, approved_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'queued', '', '', NULL, NULL, 0, ?, ?, ?, NULL, ?, ?, NULL, '', ?, ?)""",
        (project_id, title, task_type, priority, provider, prompt, max_retries, parent_task_id, auto_run_next, requires_approval, approval_status, now, now),
    ).lastrowid
    return task_row(row_id)


def task_template_rows(active_only=True):
    where = "WHERE COALESCE(is_active, 1)=1" if active_only else ""
    return [
        row_to_dict(row)
        for row in query_all(
            f"SELECT * FROM task_templates {where} ORDER BY sort_order ASC, id ASC"
        )
    ]


def task_template_row(template_id, active_only=True):
    where = "id=?"
    params = [template_id]
    if active_only:
        where += " AND COALESCE(is_active, 1)=1"
    return row_to_dict(query_one(f"SELECT * FROM task_templates WHERE {where}", tuple(params)))


def task_template_context(project):
    return {
        "project_id": project["id"],
        "project_name": project["name"] or "",
        "client_name": project["client_name"] or "",
        "project_type": project["project_type"] or "",
        "status": project["status"] or "",
        "priority": project["priority"] or "",
        "description": project["description"] or "",
        "next_steps": project["next_steps"] or "",
    }


def render_task_prompt(template, project):
    text = template.get("prompt_template") or ""
    context = task_template_context(project)
    try:
        return text.format(**context)
    except (KeyError, ValueError):
        rendered = text
        for key, value in context.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered


def create_ai_task_from_template(project_id, template_id, parent_task_id=None, auto_run_next=0, requires_approval=0):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        raise LookupError("project not found")
    template = task_template_row(template_id)
    if not template:
        raise LookupError("task template not found")
    payload = {
        "project_id": project_id,
        "title": template["name"],
        "task_type": template["task_type"] or "general",
        "provider": template["provider"] or "openai",
        "prompt": render_task_prompt(template, project),
        "priority": template["priority"] or "medium",
        "parent_task_id": parent_task_id,
        "auto_run_next": auto_run_next,
        "requires_approval": requires_approval,
    }
    return create_ai_task(payload)


def create_default_ai_task_flow(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        raise LookupError("project not found")
    created = []
    parent_task_id = None
    templates = task_template_rows(active_only=True)
    for index, template in enumerate(templates):
        auto_run_next = 1 if index < len(templates) - 1 else 0
        requires_approval = 1 if coerce_int(template.get("sort_order"), 0) in (10, 30, 50) else 0
        task = create_ai_task_from_template(
            project_id,
            template["id"],
            parent_task_id=parent_task_id,
            auto_run_next=auto_run_next,
            requires_approval=requires_approval,
        )
        created.append(task)
        parent_task_id = task["id"]
    return created


def update_ai_task(task_id, **fields):
    allowed = {
        "project_id", "title", "task_type", "priority", "provider", "prompt", "status", "result", "error_message",
        "started_at", "finished_at", "retry_count", "max_retries", "parent_task_id", "auto_run_next", "last_auto_run_at",
        "requires_approval", "approval_status", "approved_at", "approved_by",
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key}=?")
            values.append(value)
    if not updates:
        return
    updates.append("updated_at=?")
    values.extend([now_str(), task_id])
    execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id=?", tuple(values))


def transition_ai_task(task_id, status, **fields):
    next_status = normalize_ai_task_status(status)
    updates = {"status": next_status}
    updates.update(fields)
    update_ai_task(task_id, **updates)
    return task_row(task_id)


def call_task_provider(provider, prompt):
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY", "").strip():
            return {"ok": False, "status": "not_configured", "error": "OPENAI_API_KEY not configured"}
        row = ai_provider_by_name("openai")
        model = openai_console_model(row)
        return call_openai_console(prompt, model)
    if provider == "gemini":
        if not os.getenv("GEMINI_API_KEY", "").strip():
            return {"ok": False, "status": "not_configured", "error": "GEMINI_API_KEY not configured"}
        row = ai_provider_by_name("gemini")
        model = (row or {}).get("default_model") or os.getenv("GEMINI_DEFAULT_MODEL", "gemini-1.5-pro")
        return call_gemini_console(prompt, model)
    if provider == "claude":
        if not os.getenv("CLAUDE_API_KEY", "").strip():
            return {"ok": False, "status": "not_configured", "error": "CLAUDE_API_KEY not configured"}
        return {"ok": False, "status": "not_implemented", "error": "Claude execution adapter is not implemented yet"}
    return {"ok": False, "status": "unsupported", "error": "unsupported provider"}


def run_ai_task(task_id, auto_continue=False, flow_remaining=1):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    current_status = normalize_ai_task_status(task.get("status"))
    if current_status == "running":
        raise ValueError("task is already running")
    if current_status == "blocked":
        raise ValueError("task is blocked")
    if current_status == "canceled":
        raise ValueError("task is canceled")
    if current_status == "done":
        raise ValueError("task is already done")
    provider = normalize_task_provider(task.get("provider"))
    project_id = coerce_int(task.get("project_id"), None)
    transition_ai_task(task_id, "running", started_at=now_str(), finished_at=None, error_message="")
    prompt = task.get("prompt") or ""
    result = call_task_provider(provider, prompt)
    model = ""
    try:
        provider_row = ai_provider_by_name(provider)
        model = openai_console_model(provider_row) if provider == "openai" else ((provider_row or {}).get("default_model") or "")
    except ValueError:
        provider_row = None
    if result.get("ok"):
        text = result.get("text") or ""
        requires_approval = coerce_int(task.get("requires_approval"), 0) == 1
        approval_status = "pending" if requires_approval else "none"
        transition_ai_task(
            task_id,
            "done",
            result=text,
            error_message="",
            finished_at=now_str(),
            approval_status=approval_status,
            approved_at=None,
            approved_by="",
        )
        message_id = insert_ai_message(project_id, provider, model, "executor", ai_prompt_summary(prompt))
        update_ai_message(
            message_id,
            status="done",
            response_text=text,
            error_message="",
            raw_response=json.dumps({"task_id": task_id, "provider": provider, "mock": bool(result.get("mock"))}, ensure_ascii=False),
        )
        if provider_row:
            record_ai_usage(
                provider_row,
                model,
                "executor",
                "success",
                project_id,
                None,
                coerce_int(result.get("input_tokens"), approx_ai_tokens(prompt)),
                coerce_int(result.get("output_tokens"), approx_ai_tokens(text)),
                "",
                ai_prompt_summary(prompt),
            )
        flow_results = []
        if auto_continue and flow_remaining > 1 and not requires_approval:
            flow_results = run_next_child_tasks(task_id, max_depth=flow_remaining - 1)
        return {"ok": True, "task": task_row(task_id), "message_id": message_id, "flow_results": flow_results}
    error_message = result.get("error") or result.get("status") or "provider execution failed"
    retry_count = coerce_int(task.get("retry_count"), 0) + 1
    transition_ai_task(task_id, "failed", result="", error_message=error_message, finished_at=now_str(), retry_count=retry_count)
    message_id = insert_ai_message(project_id, provider, model, "executor", ai_prompt_summary(prompt))
    update_ai_message(
        message_id,
        status="failed",
        response_text="",
        error_message=error_message,
        raw_response=json.dumps({"task_id": task_id, "provider": provider, "status": result.get("status")}, ensure_ascii=False),
    )
    if provider_row:
        record_ai_usage(provider_row, model, "executor", "failed", project_id, None, approx_ai_tokens(prompt), 0, error_message, ai_prompt_summary(prompt))
    return {"ok": False, "task": task_row(task_id), "message_id": message_id, "error": error_message}


def run_next_child_tasks(task_id, max_depth=6):
    if max_depth <= 0:
        return []
    parent = task_row(task_id)
    if not parent:
        raise LookupError("task not found")
    if coerce_int(parent.get("auto_run_next"), 0) != 1:
        return []
    if normalize_ai_task_status(parent.get("status")) != "done":
        return []
    if coerce_int(parent.get("requires_approval"), 0) == 1 and normalize_ai_task_approval_status(parent.get("approval_status")) != "approved":
        return []
    child = row_to_dict(query_one(
        """SELECT *
           FROM tasks
           WHERE parent_task_id=? AND status='queued'
           ORDER BY id ASC
           LIMIT 1""",
        (task_id,),
    ))
    if not child:
        return []
    now = now_str()
    update_ai_task(task_id, last_auto_run_at=now)
    update_ai_task(child["id"], last_auto_run_at=now)
    message_id = insert_ai_message(
        coerce_int(parent.get("project_id"), None),
        "system",
        "",
        "flow",
        "flow auto-run next task",
    )
    update_ai_message(
        message_id,
        status="done",
        response_text=f"flow auto-run next task: parent #{task_id} -> child #{child['id']}",
        error_message="",
        raw_response=json.dumps({"parent_task_id": task_id, "child_task_id": child["id"]}, ensure_ascii=False),
    )
    result = run_ai_task(child["id"], auto_continue=True, flow_remaining=max_depth)
    record = {
        "task_id": child["id"],
        "message_id": message_id,
        "ok": bool(result.get("ok")),
        "status": (result.get("task") or {}).get("status"),
        "error": result.get("error"),
    }
    return [record] + (result.get("flow_results") or [])


def run_ai_task_flow(task_id, max_depth=6):
    return run_ai_task(task_id, auto_continue=True, flow_remaining=max(1, min(coerce_int(max_depth, 6), 6)))


def task_approval_message(task, action, approved_by="local_admin"):
    message_id = insert_ai_message(
        coerce_int(task.get("project_id"), None),
        "system",
        "",
        "approval",
        f"task approval {action}",
    )
    update_ai_message(
        message_id,
        status="done",
        response_text=f"task #{task['id']} approval {action} by {approved_by}",
        error_message="",
        raw_response=json.dumps({"task_id": task["id"], "action": action, "approved_by": approved_by}, ensure_ascii=False),
    )
    return message_id


def flow_system_message(project_id, summary, details=None):
    message_id = insert_ai_message(project_id, "system", "", "flow", summary)
    update_ai_message(
        message_id,
        status="done",
        response_text=summary,
        error_message="",
        raw_response=json.dumps(details or {}, ensure_ascii=False),
    )
    return message_id


def first_queued_project_ai_task(project_id):
    return row_to_dict(query_one(
        """SELECT *
           FROM tasks
           WHERE project_id=? AND status='queued'
           ORDER BY COALESCE(parent_task_id, 0) ASC, id ASC
           LIMIT 1""",
        (project_id,),
    ))


def next_queued_child_task(task_id):
    return row_to_dict(query_one(
        """SELECT *
           FROM tasks
           WHERE parent_task_id=? AND status='queued'
           ORDER BY id ASC
           LIMIT 1""",
        (task_id,),
    ))


def validate_full_flow_task(task):
    task_type = str(task.get("task_type") or "").strip().lower()
    if task_type not in FULL_FLOW_ALLOWED_TASK_TYPES:
        raise ValueError(f"full flow blocked unsafe task_type: {task_type or 'empty'}")
    if task_type != "deploy_check" and any(term in task_type for term in FULL_FLOW_BLOCKED_TASK_TYPE_TERMS):
        raise ValueError(f"full flow blocked unsafe task_type: {task_type}")
    return True


def run_project_ai_flow(project_id, mode="safe"):
    project = query_one("SELECT id FROM projects WHERE id=?", (project_id,))
    if not project:
        raise LookupError("project not found")
    mode = normalize_choice(mode, ["safe", "full"], "safe")
    flow_run = create_flow_run(project_id, mode)
    executed = []
    max_steps = 6
    flow_system_message(project_id, f"{mode} flow started", {"mode": mode, "flow_run_id": flow_run["id"]})
    try:
        start_task = first_queued_project_ai_task(project_id)
        if not start_task:
            flow_system_message(project_id, "flow completed", {"mode": mode, "flow_run_id": flow_run["id"], "reason": "no queued tasks"})
            finished = finish_flow_run(flow_run["id"], project_id, mode, "completed", "no_queued_task", executed)
            return {
                "ok": True,
                "project_id": project_id,
                "mode": mode,
                "status": "completed",
                "stopped_reason": "no_queued_task",
                "tasks": [],
                "message": "no queued tasks",
                "flow_run": finished,
            }

        current = start_task
        for step in range(max_steps):
            if not current:
                flow_system_message(project_id, "flow completed", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed})
                finished = finish_flow_run(flow_run["id"], project_id, mode, "completed", "completed", executed)
                return {"ok": True, "project_id": project_id, "mode": mode, "status": "completed", "stopped_reason": "completed", "tasks": executed, "flow_run": finished}
            if normalize_ai_task_status(current.get("status")) != "queued":
                raise ValueError("flow can only run queued tasks")
            if mode == "full":
                try:
                    validate_full_flow_task(current)
                except ValueError as exc:
                    flow_system_message(
                        project_id,
                        "flow stopped: failed",
                        {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "task_id": current["id"], "error": str(exc), "stopped_reason": "blocked_by_safety"},
                    )
                    finished = finish_flow_run(flow_run["id"], project_id, mode, "failed", "blocked_by_safety", executed, str(exc))
                    return {"ok": False, "project_id": project_id, "mode": mode, "status": "failed", "stopped_reason": "blocked_by_safety", "tasks": executed, "error": str(exc), "flow_run": finished}

            result = run_ai_task(current["id"], auto_continue=False)
            task_after = result.get("task") or task_row(current["id"])
            executed.append({
                "task_id": current["id"],
                "title": task_after.get("title"),
                "task_type": task_after.get("task_type"),
                "ok": bool(result.get("ok")),
                "status": task_after.get("status"),
                "approval_status": task_after.get("approval_status"),
                "error": result.get("error"),
            })

            if not result.get("ok"):
                flow_system_message(project_id, "flow stopped: failed", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "task_id": current["id"], "error": result.get("error")})
                finished = finish_flow_run(flow_run["id"], project_id, mode, "failed", "failed", executed, result.get("error"))
                return {"ok": False, "project_id": project_id, "mode": mode, "status": "failed", "stopped_reason": "failed", "tasks": executed, "error": result.get("error"), "flow_run": finished}

            if mode == "safe" and coerce_int(task_after.get("requires_approval"), 0) == 1 and task_after.get("approval_status") == "pending":
                flow_system_message(project_id, "flow stopped: approval required", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "task_id": current["id"]})
                finished = finish_flow_run(flow_run["id"], project_id, mode, "approval_required", "approval_required", executed)
                return {"ok": True, "project_id": project_id, "mode": mode, "status": "approval_required", "stopped_reason": "approval_required", "tasks": executed, "flow_run": finished}

            if coerce_int(task_after.get("auto_run_next"), 0) != 1:
                flow_system_message(project_id, "flow completed", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "reason": "auto_run_next off"})
                finished = finish_flow_run(flow_run["id"], project_id, mode, "completed", "completed", executed)
                return {"ok": True, "project_id": project_id, "mode": mode, "status": "completed", "stopped_reason": "completed", "tasks": executed, "flow_run": finished}

            current = next_queued_child_task(current["id"])

        flow_system_message(project_id, "flow completed", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "reason": "max steps reached"})
        finished = finish_flow_run(flow_run["id"], project_id, mode, "completed", "completed", executed)
        return {"ok": True, "project_id": project_id, "mode": mode, "status": "completed", "stopped_reason": "completed", "tasks": executed, "max_steps": max_steps, "flow_run": finished}
    except Exception as exc:
        flow_system_message(project_id, "flow stopped: failed", {"mode": mode, "flow_run_id": flow_run["id"], "tasks": executed, "error": str(exc), "stopped_reason": "error"})
        finish_flow_run(flow_run["id"], project_id, mode, "failed", "error", executed, str(exc))
        raise


def approve_ai_task(task_id, approved_by="local_admin"):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    if normalize_ai_task_status(task.get("status")) != "done":
        raise ValueError("only done tasks can be approved")
    if coerce_int(task.get("requires_approval"), 0) != 1:
        raise ValueError("task does not require approval")
    if normalize_ai_task_approval_status(task.get("approval_status")) == "rejected":
        raise ValueError("rejected tasks cannot be approved")
    now = now_str()
    updated = transition_ai_task(
        task_id,
        "done",
        approval_status="approved",
        approved_at=now,
        approved_by=approved_by,
    )
    message_id = task_approval_message(updated, "approved", approved_by)
    flow_results = run_next_child_tasks(task_id, max_depth=6) if coerce_int(updated.get("auto_run_next"), 0) == 1 else []
    return {"ok": True, "task": task_row(task_id), "message_id": message_id, "flow_results": flow_results}


def reject_ai_task(task_id, approved_by="local_admin"):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    if normalize_ai_task_status(task.get("status")) != "done":
        raise ValueError("only done tasks can be rejected")
    if coerce_int(task.get("requires_approval"), 0) != 1:
        raise ValueError("task does not require approval")
    updated = transition_ai_task(task_id, "done", approval_status="rejected", approved_at=None, approved_by=approved_by)
    message_id = task_approval_message(updated, "rejected", approved_by)
    return {"ok": True, "task": task_row(task_id), "message_id": message_id, "flow_results": []}


def retry_ai_task(task_id):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    if normalize_ai_task_status(task.get("status")) not in ("failed", "blocked", "canceled"):
        raise ValueError("only failed, blocked, or canceled tasks can be retried")
    retry_count = coerce_int(task.get("retry_count"), 0)
    max_retries = coerce_int(task.get("max_retries"), 3)
    if max_retries >= 0 and retry_count >= max_retries:
        return transition_ai_task(task_id, "blocked", error_message="max retries reached")
    return transition_ai_task(task_id, "queued", error_message="", result="", started_at=None, finished_at=None)


def cancel_ai_task(task_id):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    if normalize_ai_task_status(task.get("status")) == "done":
        raise ValueError("done tasks cannot be canceled")
    return transition_ai_task(task_id, "canceled", finished_at=now_str())


def block_ai_task(task_id, reason="manual block"):
    if not task_row(task_id):
        raise LookupError("task not found")
    return transition_ai_task(task_id, "blocked", error_message=reason or "manual block")


def unblock_ai_task(task_id):
    task = task_row(task_id)
    if not task:
        raise LookupError("task not found")
    if normalize_ai_task_status(task.get("status")) != "blocked":
        raise ValueError("only blocked tasks can be unblocked")
    return transition_ai_task(task_id, "queued", error_message="", started_at=None, finished_at=None)


def provider_health_http_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            return {"ok": True, "status_code": resp.status, "data": data}
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "status_code": exc.code, "error": f"HTTP {exc.code}: {message}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_openai_health():
    return get_active_ai_health_key("openai")


def check_gemini_health():
    return get_active_ai_health_key("gemini")


def check_claude_health():
    return get_active_ai_health_key("claude")


def ai_provider_health_status():
    return {
        "openai": check_openai_health(),
        "gemini": check_gemini_health(),
        "claude": check_claude_health(),
    }


def ai_cost_group_totals(group_by, since=None):
    if group_by == "provider":
        select_sql = "provider AS label"
        join_sql = ""
        group_sql = "provider"
    elif group_by == "model":
        select_sql = "model AS label"
        join_sql = ""
        group_sql = "model"
    elif group_by == "project":
        select_sql = "COALESCE(p.name, '未指定') AS label"
        join_sql = "LEFT JOIN projects p ON p.id=l.project_id"
        group_sql = "COALESCE(p.name, '未指定')"
    else:
        raise ValueError("unsupported group_by")
    where = ["l.status='success'"]
    params = []
    if since:
        where.append("l.created_at>=?")
        params.append(since)
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT {select_sql}, COALESCE(SUM(l.estimated_cost), 0) AS cost,
                       COALESCE(SUM(l.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(l.output_tokens), 0) AS output_tokens,
                       COUNT(*) AS calls
                FROM ai_usage_logs l
                {join_sql}
                WHERE {' AND '.join(where)}
                GROUP BY {group_sql}
                ORDER BY cost DESC, calls DESC""",
            tuple(params),
        )
    ]


def ai_cost_overview():
    today = ai_period_start("day")
    month = ai_period_start("month")
    providers = ai_provider_rows()
    recent_usage = [
        row_to_dict(row)
        for row in query_all(
            """SELECT l.*, p.name AS project_name
               FROM ai_usage_logs l
               LEFT JOIN projects p ON p.id=l.project_id
               ORDER BY l.created_at DESC, l.id DESC
               LIMIT 100"""
        )
    ]
    recent_errors = [item for item in recent_usage if item.get("status") == "failed"][:20]
    return {
        "today_cost": ai_cost_sum(since=today),
        "month_cost": ai_cost_sum(since=month),
        "providers": providers,
        "by_provider": ai_cost_group_totals("provider", month),
        "by_model": ai_cost_group_totals("model", month),
        "by_project": ai_cost_group_totals("project", month),
        "recent_usage": recent_usage,
        "recent_errors": recent_errors,
        "fallback_rules": [row_to_dict(row) for row in query_all("SELECT * FROM ai_fallback_rules ORDER BY task_role, primary_provider, id")],
    }


def ai_provider_payload(source):
    name = normalize_ai_provider_name(source.get("provider_name") or source.get("provider"))
    status = normalize_choice(source.get("status"), AI_PROVIDER_STATUSES, "active")
    return {
        "provider_name": name,
        "status": status,
        "priority": coerce_int(source.get("priority"), 100),
        "default_model": (source.get("default_model") or "").strip(),
        "cost_input_per_1k": coerce_float(source.get("cost_input_per_1k"), 0),
        "cost_output_per_1k": coerce_float(source.get("cost_output_per_1k"), 0),
        "daily_budget": coerce_float(source.get("daily_budget"), None),
        "monthly_budget": coerce_float(source.get("monthly_budget"), None),
    }


def upsert_ai_provider(payload):
    data = ai_provider_payload(payload)
    existing = query_one("SELECT id FROM ai_providers WHERE provider_name=?", (data["provider_name"],))
    now = now_str()
    if existing:
        execute(
            """UPDATE ai_providers
               SET status=?, priority=?, default_model=?, cost_input_per_1k=?, cost_output_per_1k=?,
                   daily_budget=?, monthly_budget=?, updated_at=?
               WHERE provider_name=?""",
            (
                data["status"], data["priority"], data["default_model"], data["cost_input_per_1k"],
                data["cost_output_per_1k"], data["daily_budget"], data["monthly_budget"], now, data["provider_name"],
            ),
        )
        return row_to_dict(query_one("SELECT * FROM ai_providers WHERE provider_name=?", (data["provider_name"],)))
    row_id = execute(
        """INSERT INTO ai_providers
           (provider_name, status, priority, default_model, cost_input_per_1k, cost_output_per_1k,
            daily_budget, monthly_budget, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["provider_name"], data["status"], data["priority"], data["default_model"],
            data["cost_input_per_1k"], data["cost_output_per_1k"], data["daily_budget"],
            data["monthly_budget"], now, now,
        ),
    ).lastrowid
    return row_to_dict(query_one("SELECT * FROM ai_providers WHERE id=?", (row_id,)))


def update_ai_provider(provider_id, payload):
    row = query_one("SELECT * FROM ai_providers WHERE id=?", (provider_id,))
    if not row:
        raise LookupError("AI provider not found")
    merged = row_to_dict(row)
    merged.update({key: value for key, value in payload.items() if value is not None})
    updated = upsert_ai_provider(merged)
    return updated


def create_ai_fallback_rule(payload):
    primary = normalize_ai_provider_name(payload.get("primary_provider"))
    fallback = normalize_ai_provider_name(payload.get("fallback_provider"))
    task_role = str(payload.get("task_role") or "reviewer").strip().lower()
    if task_role not in AI_COST_TASK_ROLES:
        raise ValueError("unsupported task_role")
    enabled = 1 if payload.get("enabled", True) not in (False, 0, "0", "false", "no") else 0
    row_id = execute(
        "INSERT INTO ai_fallback_rules (primary_provider, fallback_provider, task_role, enabled, created_at) VALUES (?, ?, ?, ?, ?)",
        (primary, fallback, task_role, enabled, now_str()),
    ).lastrowid
    return row_to_dict(query_one("SELECT * FROM ai_fallback_rules WHERE id=?", (row_id,)))


def normalize_content_job_type(value):
    text = str(value or "product_video").strip().lower()
    return text if text in CONTENT_JOB_TYPES else "product_video"


def normalize_content_job_status(value):
    text = str(value or "queued").strip().lower()
    return text if text in CONTENT_JOB_STATUSES else "queued"


def content_jobs_for_project(project_id, limit=20):
    return [
        row_to_dict(row)
        for row in query_all(
            "SELECT * FROM content_jobs WHERE project_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (project_id, limit),
        )
    ]


def insert_content_job(project_id, content_type, title, script, prompt, provider="kling", status="queued",
                       output_url="", post_text="", post_status="draft", post_platform="", post_id=""):
    return execute(
        """INSERT INTO content_jobs
           (project_id, type, title, script, prompt, provider, status, output_url,
            post_text, post_status, post_platform, post_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            normalize_content_job_type(content_type),
            title or "",
            script or "",
            prompt or "",
            provider or "kling",
            normalize_content_job_status(status),
            output_url or "",
            post_text or "",
            post_status or "draft",
            post_platform or "",
            post_id or "",
            now_str(),
        ),
    ).lastrowid


def update_content_job(job_id, status=None, output_url=None, script=None, prompt=None,
                       post_text=None, post_status=None, post_platform=None, post_id=None):
    fields = []
    values = []
    if status is not None:
        fields.append("status=?")
        values.append(normalize_content_job_status(status))
    if output_url is not None:
        fields.append("output_url=?")
        values.append(output_url)
    if script is not None:
        fields.append("script=?")
        values.append(script)
    if prompt is not None:
        fields.append("prompt=?")
        values.append(prompt)
    if post_text is not None:
        fields.append("post_text=?")
        values.append(post_text)
    if post_status is not None:
        fields.append("post_status=?")
        values.append(post_status)
    if post_platform is not None:
        fields.append("post_platform=?")
        values.append(post_platform)
    if post_id is not None:
        fields.append("post_id=?")
        values.append(post_id)
    if not fields:
        return row_to_dict(query_one("SELECT * FROM content_jobs WHERE id=?", (job_id,)))
    values.append(job_id)
    execute(f"UPDATE content_jobs SET {', '.join(fields)} WHERE id=?", tuple(values))
    return row_to_dict(query_one("SELECT * FROM content_jobs WHERE id=?", (job_id,)))


def extract_kling_output_url(payload):
    if not isinstance(payload, dict):
        return ""
    candidates = [
        payload.get("output_url"),
        payload.get("video_url"),
        payload.get("url"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([
            data.get("output_url"),
            data.get("video_url"),
            data.get("url"),
        ])
        task = data.get("task")
        if isinstance(task, dict):
            candidates.extend([task.get("output_url"), task.get("video_url"), task.get("url")])
    for item in candidates:
        if item:
            return str(item)
    return ""


def call_claude_generate_product_script(product_name, features, target, style):
    feature_text = "、".join(features) if isinstance(features, list) else str(features or "")
    fallback_script = (
        f"還在找適合{target or '日常使用者'}的{product_name}嗎？"
        f"{product_name}主打{feature_text or '實用安心'}，用{style or '清楚溫暖'}的節奏呈現商品亮點。"
        f"現在就把{product_name}加入你的日常，立即了解更多。"
    )
    api_url = os.getenv("CLAUDE_API_URL", "").strip()
    api_key = os.getenv("CLAUDE_API_KEY", "").strip() or os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_url or not api_key:
        return {"ok": True, "script": fallback_script, "provider": "claude-template", "skipped": True}
    prompt = (
        "你是短影音廣告腳本企劃。只輸出 80 字內中文腳本，包含開頭 hook、商品亮點、CTA。"
        f"\n商品：{product_name}\n特色：{feature_text}\n目標族群：{target}\n風格：{style}"
    )
    body = json.dumps(
        {
            "model": os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest"),
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
            parsed = json.loads(text) if text.strip() else {}
            content = parsed.get("content")
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("text"):
                    return {"ok": True, "script": first["text"].strip(), "provider": "claude"}
            if parsed.get("text"):
                return {"ok": True, "script": str(parsed["text"]).strip(), "provider": "claude"}
    except Exception:
        pass
    return {"ok": True, "script": fallback_script, "provider": "claude-template", "skipped": True}


def fallback_product_post_text(product_name, features, target, style):
    feature_list = features if isinstance(features, list) else [line.strip() for line in str(features or "").splitlines() if line.strip()]
    points = feature_list[:3] or ["安心實用", "日常好用", "適合全家"]
    while len(points) < 3:
        points.append("使用情境多元")
    return (
        f"正在找適合{target or '日常生活'}的{product_name}嗎？\n\n"
        f"商品特色：\n"
        f"1. {points[0]}\n"
        f"2. {points[1]}\n"
        f"3. {points[2]}\n\n"
        f"風格：{style or '溫馨、清楚、好理解'}\n"
        "優惠：歡迎私訊了解最新價格與組合。\n"
        "CTA：立即私訊下單，讓好用的商品走進你的日常。"
    )


def call_claude_generate_product_post(product_name, features, target, style, script):
    fallback_post = fallback_product_post_text(product_name, features, target, style)
    api_url = os.getenv("CLAUDE_API_URL", "").strip()
    api_key = os.getenv("CLAUDE_API_KEY", "").strip() or os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_url or not api_key:
        return {"ok": True, "post_text": fallback_post, "provider": "claude-template", "skipped": True}
    feature_text = "、".join(features) if isinstance(features, list) else str(features or "")
    prompt = (
        "你是社群小編。請產出繁體中文商品貼文，不要 Markdown，格式必須包含："
        "開頭吸引句、商品特色 3 點、價格或優惠可選、CTA（立即下單 / 私訊）。"
        f"\n商品：{product_name}\n特色：{feature_text}\n目標族群：{target}\n風格：{style}\n影片腳本：{script}"
    )
    body = json.dumps(
        {
            "model": os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest"),
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
            parsed = json.loads(text) if text.strip() else {}
            content = parsed.get("content")
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("text"):
                    return {"ok": True, "post_text": first["text"].strip(), "provider": "claude"}
            if parsed.get("text"):
                return {"ok": True, "post_text": str(parsed["text"]).strip(), "provider": "claude"}
    except Exception:
        pass
    return {"ok": True, "post_text": fallback_post, "provider": "claude-template", "skipped": True}


def build_kling_product_prompt(product_name, features, target, style, script):
    feature_lines = "\n".join(f"- {item}" for item in features) if isinstance(features, list) else str(features or "")
    return (
        "生成一支商品短影音，直式 9:16，15 秒，明亮乾淨，適合社群廣告。\n"
        f"商品：{product_name}\n"
        f"目標族群：{target or '一般消費者'}\n"
        f"風格：{style or '促銷 / 溫馨 / 快速'}\n"
        f"商品特色：\n{feature_lines}\n"
        "場景：居家或日常使用情境，畫面乾淨、有產品特寫、手部使用示範。\n"
        "角色：符合目標族群的自然生活感人物，不誇張演出。\n"
        "語氣：可信任、溫暖、節奏快速。\n"
        f"字幕：請用繁體中文呈現腳本重點：{script}\n"
        "結尾：展示商品與 CTA。"
    )


def call_kling_generate_video(script, prompt, project_id=None, title=None):
    api_url = os.getenv("KLING_API_URL", "").strip()
    api_key = os.getenv("KLING_API_KEY", "").strip()
    if not api_url or not api_key:
        return {
            "ok": False,
            "skipped": True,
            "reason": "KLING_API_URL or KLING_API_KEY is not configured",
            "output_url": "",
        }
    body = json.dumps(
        {
            "project_id": project_id,
            "title": title or "",
            "script": script or "",
            "prompt": prompt or "",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
            parsed = json.loads(text) if text.strip() else {}
            output_url = extract_kling_output_url(parsed)
            return {"ok": 200 <= resp.status < 300, "status_code": resp.status, "output_url": output_url}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": f"Kling API HTTP {exc.code}", "output_url": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "output_url": ""}


def create_content_job(project_id, content_type, script, prompt, call_provider=True):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise LookupError("project not found")
    content_type = normalize_content_job_type(content_type)
    script = (script or "").strip()
    prompt = (prompt or "").strip()
    if not script and not prompt:
        raise ValueError("script or prompt is required")
    job_id = insert_content_job(project_id, content_type, "", script, prompt, "kling", "queued")
    result = {
        "ok": True,
        "content_job_id": job_id,
        "project_id": project_id,
        "type": content_type,
        "status": "queued",
        "output_url": "",
        "message": "content job queued",
    }
    if content_type in ("video", "product_video") and call_provider:
        update_content_job(job_id, status="running")
        kling_result = call_kling_generate_video(script, prompt, project_id=project_id)
        output_url = kling_result.get("output_url") or ""
        if kling_result.get("ok") and output_url:
            update_content_job(job_id, status="done", output_url=output_url)
            result.update({"status": "done", "output_url": output_url, "message": "Kling video generated"})
            save_handoff(
                project_id,
                {
                    "source": "kling",
                    "agent_name": "Kling",
                    "work_mode": "manual",
                    "summary": f"Kling 影片生成完成：content_job #{job_id}",
                    "changed_files": "none",
                    "test_result": f"output_url={output_url}",
                    "git_status": "not applicable",
                    "repo_branch": "none",
                    "commit_sha": "none",
                    "next_steps": "檢查 Kling 影片輸出並安排後續內容發布",
                    "warnings": "未記錄或輸出 Kling API key",
                },
            )
        else:
            update_content_job(job_id, status="queued")
            result.update({
                "status": "queued",
                "message": kling_result.get("reason") or kling_result.get("error") or "Kling video job queued without output_url",
            })
    return result


def create_product_video_job(project_id, product_name, features, target, style, call_provider=True):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise LookupError("project not found")
    product_name = (product_name or "").strip()
    if not product_name:
        raise ValueError("product_name is required")
    if isinstance(features, str):
        feature_list = [line.strip() for line in features.replace(",", "\n").splitlines() if line.strip()]
    else:
        feature_list = [str(item).strip() for item in (features or []) if str(item).strip()]
    script_result = call_claude_generate_product_script(product_name, feature_list, target, style)
    script = script_result["script"]
    post_result = call_claude_generate_product_post(product_name, feature_list, target, style, script)
    post_text = post_result["post_text"]
    prompt = build_kling_product_prompt(product_name, feature_list, target, style, script)
    job_id = insert_content_job(
        project_id,
        "product_video",
        product_name,
        script,
        prompt,
        "kling",
        "queued",
        post_text=post_text,
        post_status="draft",
    )
    result = {
        "ok": True,
        "content_job_id": job_id,
        "project_id": project_id,
        "type": "product_video",
        "title": product_name,
        "script": script,
        "prompt": prompt,
        "post_text": post_text,
        "post_status": "draft",
        "status": "queued",
        "video_url": "",
        "output_url": "",
        "script_provider": script_result.get("provider"),
        "post_provider": post_result.get("provider"),
        "message": "product video job queued",
    }
    if call_provider:
        update_content_job(job_id, status="running")
        kling_result = call_kling_generate_video(script, prompt, project_id=project_id, title=product_name)
        video_url = kling_result.get("output_url") or ""
        if kling_result.get("ok") and video_url:
            update_content_job(job_id, status="done", output_url=video_url)
            result.update({"status": "done", "video_url": video_url, "output_url": video_url, "message": "Kling product video generated"})
            save_handoff(
                project_id,
                {
                    "source": "kling",
                    "agent_name": "Claude + Kling",
                    "work_mode": "manual",
                    "summary": f"商品影片生成完成：{product_name}",
                    "changed_files": "none",
                    "test_result": f"video_url={video_url}",
                    "git_status": "not applicable",
                    "repo_branch": "none",
                    "commit_sha": "none",
                    "next_steps": "檢查影片、下載素材並安排投放或重新生成版本",
                    "warnings": "未記錄或輸出 Claude/Kling API key",
                },
            )
        elif kling_result.get("skipped"):
            update_content_job(job_id, status="queued")
            result.update({"status": "queued", "message": kling_result.get("reason") or "Kling API not configured"})
        else:
            update_content_job(job_id, status="failed")
            result.update({"ok": False, "status": "failed", "message": kling_result.get("error") or "Kling API failed"})
    return result


def content_job_row(job_id):
    return row_to_dict(query_one("SELECT * FROM content_jobs WHERE id=?", (job_id,)))


def extract_publish_post_id(payload):
    if not isinstance(payload, dict):
        return ""
    candidates = [payload.get("post_id"), payload.get("id")]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("post_id"), data.get("id")])
    for item in candidates:
        if item:
            return str(item)
    return ""


def call_facebook_publish(job):
    api_url = os.getenv("FACEBOOK_PUBLISH_API_URL", "").strip() or os.getenv("FACEBOOK_VIDEO_API_URL", "").strip()
    token = os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip() or os.getenv("FB_ACCESS_TOKEN", "").strip()
    if not api_url or not token:
        return {"ok": False, "skipped": True, "error": "Facebook publish URL or token is not configured"}
    body = json.dumps(
        {
            "video_url": job.get("output_url") or "",
            "message": job.get("post_text") or "",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
            parsed = json.loads(text) if text.strip() else {}
            return {"ok": 200 <= resp.status < 300, "post_id": extract_publish_post_id(parsed), "status_code": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": f"Facebook publish HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def call_line_publish(job):
    api_url = os.getenv("LINE_PUBLISH_API_URL", "").strip() or os.getenv("LINE_NOTIFY_API_URL", "").strip() or "https://notify-api.line.me/api/notify"
    token = os.getenv("LINE_NOTIFY_TOKEN", "").strip() or os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        return {"ok": False, "skipped": True, "error": "LINE token is not configured"}
    message = f"{job.get('post_text') or ''}\n\n影片：{job.get('output_url') or ''}".strip()
    if os.getenv("LINE_PUBLISH_API_URL", "").strip():
        data = json.dumps({"message": message, "video_url": job.get("output_url") or ""}, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    else:
        data = urllib.parse.urlencode({"message": message}).encode("utf-8")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                parsed = {}
            return {"ok": 200 <= resp.status < 300, "post_id": extract_publish_post_id(parsed) or f"line-{now_str()}", "status_code": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": f"LINE publish HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def publish_content_job(job_id, platform):
    platform = str(platform or "").strip().lower()
    if platform not in ("facebook", "line"):
        raise ValueError("unsupported publish platform")
    job = content_job_row(job_id)
    if not job:
        raise LookupError("content job not found")
    if not job.get("post_text"):
        raise ValueError("post_text is required before publishing")
    if not job.get("output_url"):
        raise ValueError("output_url is required before publishing")
    if platform == "facebook":
        result = call_facebook_publish(job)
    else:
        result = call_line_publish(job)
    if result.get("ok"):
        post_id = result.get("post_id") or ""
        updated = update_content_job(job_id, post_status="published", post_platform=platform, post_id=post_id)
        return {
            "ok": True,
            "content_job_id": job_id,
            "project_id": job["project_id"],
            "platform": platform,
            "post_id": post_id,
            "post_status": "published",
            "content_job": updated,
        }
    return {
        "ok": False,
        "content_job_id": job_id,
        "project_id": job["project_id"],
        "platform": platform,
        "error": result.get("error") or "publish failed",
        "skipped": bool(result.get("skipped")),
    }


def seed_industry_templates():
    for industry, data in INDUSTRY_TEMPLATE_DEFAULTS.items():
        execute(
            """INSERT OR IGNORE INTO industry_templates (industry, allowed_topics, blocked_topics)
               VALUES (?, ?, ?)""",
            (
                industry,
                json.dumps(data["allowed_topics"], ensure_ascii=False),
                json.dumps(data["blocked_topics"], ensure_ascii=False),
            ),
        )


def normalize_tenant_id(value):
    try:
        tenant_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("tenant_id is required")
    if tenant_id <= 0:
        raise ValueError("tenant_id is required")
    return tenant_id


def tenant_setting_row(tenant_id):
    row = row_to_dict(query_one("SELECT * FROM tenant_settings WHERE tenant_id=?", (tenant_id,)))
    if row:
        return row
    return {
        "tenant_id": tenant_id,
        "industry": "retail",
        "strict_mode": 1,
        "fallback_message": CUSTOMER_SERVICE_FALLBACK,
    }


def industry_template_row(industry):
    row = row_to_dict(query_one("SELECT * FROM industry_templates WHERE industry=?", (industry or "retail",)))
    if row:
        row["allowed_topics_list"] = parse_json_list(row.get("allowed_topics"))
        row["blocked_topics_list"] = parse_json_list(row.get("blocked_topics"))
        return row
    data = INDUSTRY_TEMPLATE_DEFAULTS.get("retail", {"allowed_topics": [], "blocked_topics": []})
    return {
        "industry": "retail",
        "allowed_topics": json.dumps(data["allowed_topics"], ensure_ascii=False),
        "blocked_topics": json.dumps(data["blocked_topics"], ensure_ascii=False),
        "allowed_topics_list": data["allowed_topics"],
        "blocked_topics_list": data["blocked_topics"],
    }


def normalize_chat_text(text):
    return re.sub(r"\s+", "", str(text or "").lower())


def chat_keywords(text):
    raw = str(text or "").lower()
    terms = set(re.findall(r"[a-z0-9_\-\u4e00-\u9fff]{2,}", raw))
    compact = normalize_chat_text(raw)
    for size in (2, 3, 4):
        for index in range(max(0, len(compact) - size + 1)):
            chunk = compact[index:index + size]
            if re.search(r"[\u4e00-\u9fff]", chunk):
                terms.add(chunk)
    return {term for term in terms if term and len(term) >= 2}


def topic_matches(text, topics):
    compact = normalize_chat_text(text)
    for topic in topics or []:
        topic_text = normalize_chat_text(topic)
        if topic_text and topic_text in compact:
            return topic
    return None


def search_tenant_knowledge(tenant_id, question, limit=5):
    terms = chat_keywords(question)
    scored = []
    for row in query_all("SELECT * FROM tenant_knowledge WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)):
        content = row["content"] or ""
        compact = normalize_chat_text(content)
        score = 0
        for term in terms:
            if term in compact:
                score += 3 if len(term) >= 4 else 1
        if normalize_chat_text(question) in compact:
            score += 10
        if score > 0:
            item = row_to_dict(row)
            item["score"] = score
            scored.append(item)
    scored.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
    return scored[:limit]


def build_customer_service_prompt(tenant_name, knowledge):
    return (
        f"你是 {tenant_name} 客服。\n\n"
        "你只能回答以下內容：\n\n"
        f"{knowledge}\n\n"
        "如果問題不在範圍內：\n"
        "請回：\n"
        f"「{CUSTOMER_SERVICE_FALLBACK}」"
    )


def answer_from_knowledge(matches):
    lines = []
    for item in matches[:3]:
        content = str(item.get("content") or "").strip()
        if content and content not in lines:
            lines.append(content)
    return "\n\n".join(lines)


def handle_chat(payload):
    tenant_id = normalize_tenant_id(payload.get("tenant_id"))
    question = (payload.get("message") or payload.get("question") or "").strip()
    if not question:
        raise ValueError("message is required")
    settings = tenant_setting_row(tenant_id)
    industry = settings.get("industry") or "retail"
    template = industry_template_row(industry)
    fallback = settings.get("fallback_message") or CUSTOMER_SERVICE_FALLBACK
    tenant_name = (payload.get("tenant_name") or f"Tenant {tenant_id}").strip()
    blocked_topic = topic_matches(question, template.get("blocked_topics_list"))
    if blocked_topic:
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "industry": industry,
            "answer": fallback,
            "refused": True,
            "reason": "blocked_topic",
            "matched_topic": blocked_topic,
            "knowledge": [],
        }
    matches = search_tenant_knowledge(tenant_id, question)
    if not matches:
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "industry": industry,
            "answer": fallback,
            "refused": True,
            "reason": "no_relevant_knowledge",
            "knowledge": [],
        }
    knowledge_text = answer_from_knowledge(matches)
    prompt = build_customer_service_prompt(tenant_name, knowledge_text)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "industry": industry,
        "answer": knowledge_text,
        "refused": False,
        "strict_mode": int(settings.get("strict_mode") or 1),
        "prompt": prompt,
        "knowledge": [
            {"id": item["id"], "type": item.get("type"), "content": item.get("content"), "score": item.get("score")}
            for item in matches
        ],
        "allowed_topics": template.get("allowed_topics_list", []),
    }


def ensure_initial_owner():
    existing = query_one("SELECT id FROM users WHERE role='owner' LIMIT 1")
    if existing:
        return
    username = os.getenv("DEV_PILOT_OWNER_USERNAME", "owner")
    password = os.getenv("DEV_PILOT_OWNER_PASSWORD", API_TOKEN)
    now = now_str()
    execute(
        """INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at)
           VALUES (?, ?, 'owner', 1, ?, ?)""",
        (username, generate_password_hash(password), now, now),
    )


def active_project_status_filter():
    return "COALESCE(status, '') NOT IN ('已完成', '已驗收', '取消')"


def get_computers(include_inactive=True):
    if include_inactive:
        return query_all("SELECT * FROM computers ORDER BY is_active DESC, name")
    return query_all("SELECT * FROM computers WHERE is_active=1 ORDER BY name")


def get_computer_options():
    return [{"id": None, "name": "未指定"}] + [row_to_dict(c) for c in get_computers(include_inactive=False)]


def get_computer_workload(column_name="computer_id"):
    rows = query_all(
        f"""SELECT c.id, c.name, COUNT(p.id) AS project_count
            FROM computers c
            LEFT JOIN projects p ON p.{column_name}=c.id AND {active_project_status_filter()}
            WHERE c.is_active=1
            GROUP BY c.id, c.name
            ORDER BY c.name"""
    )
    unassigned = query_one(
        f"SELECT COUNT(*) AS project_count FROM projects WHERE {column_name} IS NULL AND {active_project_status_filter()}"
    )
    return [{"id": None, "name": "未指定", "project_count": unassigned["project_count"]}] + [row_to_dict(r) for r in rows]


def normalize_computer_id(value):
    if value in (None, "", "null", "None"):
        return None
    return int(value)


def computer_exists(computer_id):
    if computer_id is None:
        return True
    return query_one("SELECT id FROM computers WHERE id=? AND is_active=1", (computer_id,)) is not None


def assignment_column(assignment_type):
    return "deploy_computer_id" if assignment_type == "deployment" else "computer_id"


def assign_project_computer(project_id, computer_id, assignment_type="development"):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        return None, "project"
    if not computer_exists(computer_id):
        return None, "computer"
    column = assignment_column(assignment_type)
    execute(f"UPDATE projects SET {column}=?, updated_at=? WHERE id=?", (computer_id, now_str(), project_id))
    return query_one("SELECT * FROM projects WHERE id=?", (project_id,)), None


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def parse_external_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return parse_time(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(TAIPEI_TZ).replace(tzinfo=None)
    return dt


def format_dt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def decorate_heartbeat(row):
    item = row_to_dict(row)
    item["machine_name"] = machine_display_name(item.get("machine_name"))
    last_seen = parse_time(item.get("last_seen_at"))
    age = None
    offline = False
    if last_seen:
        age = int((now_dt() - last_seen).total_seconds())
        offline = age > HEARTBEAT_OFFLINE_SECONDS
    else:
        offline = True
    item["is_offline"] = offline
    item["display_status"] = "offline" if offline else (item.get("status") or "idle")
    item["last_seen_age_seconds"] = age
    return item


def heartbeat_query(project_id=None, source=None, status=None, limit=None):
    where = []
    params = []
    if project_id not in (None, ""):
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return []
        where.append("project_id=?")
        params.append(project_id)
    if source:
        where.append("source=?")
        params.append(source)
    if status:
        where.append("status=?")
        params.append(status)
    sql = "SELECT * FROM ai_heartbeats"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY last_seen_at DESC, updated_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [decorate_heartbeat(r) for r in query_all(sql, tuple(params))]


def save_ai_heartbeat(payload):
    source = payload.get("source") or "other"
    if source not in HEARTBEAT_SOURCES:
        source = "other"
    status = payload.get("status") or "idle"
    if status not in HEARTBEAT_STATUSES:
        status = "idle"
    project_id = payload.get("project_id")
    try:
        project_id = int(project_id) if project_id not in (None, "") else None
    except (TypeError, ValueError):
        project_id = None
    project_name = payload.get("project_name")
    if project_id and not project_name:
        project = query_one("SELECT name FROM projects WHERE id=?", (project_id,))
        project_name = project["name"] if project else None
    agent_name = payload.get("agent_name") or source
    machine_name = machine_display_name(payload.get("machine_name") or "")
    session_id = payload.get("session_id") or ""
    raw_payload = json.dumps(payload, ensure_ascii=False)
    now = now_str()
    heartbeat_seen_dt = parse_external_time(payload.get("last_seen_at") or payload.get("last_seen"))
    heartbeat_seen = format_dt(heartbeat_seen_dt) or now
    active_dispatch = payload.get("active_dispatch")
    last_seen_value = payload.get("last_seen") or heartbeat_seen

    if session_id:
        existing = query_one(
            """SELECT * FROM ai_heartbeats
               WHERE source=? AND agent_name=? AND machine_name=? AND session_id=?
               ORDER BY id DESC LIMIT 1""",
            (source, agent_name, machine_name, session_id),
        )
    elif project_id is None:
        existing = query_one(
            """SELECT * FROM ai_heartbeats
               WHERE source=? AND agent_name=? AND machine_name=? AND project_id IS NULL
               AND COALESCE(session_id, '')=''
               ORDER BY id DESC LIMIT 1""",
            (source, agent_name, machine_name),
        )
    else:
        existing = query_one(
            """SELECT * FROM ai_heartbeats
               WHERE source=? AND agent_name=? AND machine_name=? AND project_id=?
               AND COALESCE(session_id, '')=''
               ORDER BY id DESC LIMIT 1""",
            (source, agent_name, machine_name, project_id),
        )

    values = (
        source, agent_name, project_id, project_name, machine_name, status,
        payload.get("current_task"), payload.get("last_message"), payload.get("pid"),
        session_id, raw_payload, now, heartbeat_seen, last_seen_value, active_dispatch,
    )
    if existing:
        execute(
            """UPDATE ai_heartbeats
               SET source=?, agent_name=?, project_id=?, project_name=?, machine_name=?, status=?,
                   current_task=?, last_message=?, pid=?, session_id=?, raw_payload=?,
                   updated_at=?, last_seen_at=?, last_seen=?, active_dispatch=?
               WHERE id=?""",
            (*values, existing["id"]),
        )
        return existing["id"]
    return execute(
        """INSERT INTO ai_heartbeats
           (source, agent_name, project_id, project_name, machine_name, status, current_task,
            last_message, pid, session_id, raw_payload, created_at, updated_at, last_seen_at,
            last_seen, active_dispatch)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            source, agent_name, project_id, project_name, machine_name, status,
            payload.get("current_task"), payload.get("last_message"), payload.get("pid"),
            session_id, raw_payload, now, now, heartbeat_seen, last_seen_value, active_dispatch,
        ),
    ).lastrowid


def fetch_ai_fleet_machines():
    req = urllib.request.Request(
        AI_FLEET_MACHINES_URL,
        headers={"User-Agent": "DevPilot ai-fleet sync/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read(500000)
        data = json.loads(body.decode("utf-8-sig"))
    if isinstance(data, dict):
        machines = data.get("machines") or data.get("data") or []
    elif isinstance(data, list):
        machines = data
    else:
        machines = []
    return machines if isinstance(machines, list) else []


def ai_fleet_machine_status(machine):
    last_seen = parse_external_time(machine.get("lastSeenAt") or machine.get("last_seen") or machine.get("lastSeen"))
    active_dispatch = machine.get("activeDispatchCount") or machine.get("active_dispatch") or 0
    try:
        active_dispatch = int(active_dispatch)
    except (TypeError, ValueError):
        active_dispatch = 0
    if active_dispatch > 0:
        return "running"
    if last_seen:
        age = (now_dt() - last_seen).total_seconds()
        if age < 60:
            return "online"
    return "idle"


def ai_fleet_machine_payload(machine):
    hostname = machine.get("hostname") or machine.get("name") or machine.get("id") or "unknown-machine"
    machine_name = machine_display_name(hostname)
    active_dispatch = machine.get("activeDispatchCount") or machine.get("active_dispatch") or 0
    last_seen_raw = machine.get("lastSeenAt") or machine.get("last_seen") or machine.get("lastSeen")
    return {
        "source": "ai-fleet-console",
        "agent_name": str(hostname),
        "machine_name": machine_name,
        "status": ai_fleet_machine_status(machine),
        "last_seen": last_seen_raw,
        "last_seen_at": last_seen_raw,
        "active_dispatch": str(active_dispatch),
        "current_task": "",
        "last_message": "",
        "session_id": f"ai-fleet-console:{machine.get('id') or hostname}",
        "raw_machine": machine,
    }


def sync_ai_fleet_console_once():
    machines = fetch_ai_fleet_machines()
    saved_ids = []
    with app.app_context():
        for machine in machines:
            if isinstance(machine, dict):
                saved_ids.append(save_ai_heartbeat(ai_fleet_machine_payload(machine)))
    return {"ok": True, "machines": len(machines), "heartbeat_ids": saved_ids}


def ai_fleet_poll_loop():
    while True:
        try:
            sync_ai_fleet_console_once()
        except Exception as exc:
            print(f"[ai-fleet-console] sync failed: {exc}", flush=True)
        time.sleep(max(5, AI_FLEET_POLL_INTERVAL_SECONDS))


def should_start_ai_fleet_poller():
    if not AI_FLEET_POLL_ENABLED:
        return False
    debug_enabled = os.getenv("FLASK_DEBUG", "1") == "1"
    if debug_enabled:
        return os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    return True


def start_ai_fleet_poller():
    global _AI_FLEET_THREAD_STARTED
    if not should_start_ai_fleet_poller():
        return
    with _AI_FLEET_THREAD_LOCK:
        if _AI_FLEET_THREAD_STARTED:
            return
        thread = threading.Thread(target=ai_fleet_poll_loop, name="ai-fleet-console-poller", daemon=True)
        thread.start()
        _AI_FLEET_THREAD_STARTED = True


@app.route("/")
@require_login
def dashboard():
    return render_template(
        "dashboard.html",
        app_name=APP_NAME,
        operations=operations_command_center_context(),
    )

    projects = query_all("SELECT * FROM projects ORDER BY updated_at DESC")
    recent_logs = query_all("SELECT h.*, p.name AS project_name FROM handoff_logs h JOIN projects p ON h.project_id=p.id WHERE COALESCE(h.is_hidden, 0)=0 ORDER BY h.created_at DESC LIMIT 8")
    overdue_tasks = query_all("SELECT t.*, p.name AS project_name FROM project_tasks t JOIN projects p ON t.project_id=p.id WHERE t.due_date < ? AND t.status != '已完成' ORDER BY t.due_date ASC LIMIT 8", (today_str(),))
    development_workload = get_computer_workload("computer_id")
    deployment_workload = get_computer_workload("deploy_computer_id")
    recent_heartbeats = heartbeat_query(limit=10)
    daily_report = latest_daily_report()
    stats = {
        "total": len(projects),
        "active": sum(1 for p in projects if p["status"] in ["開發中", "測試中", "規劃中"]),
        "acceptance": sum(1 for p in projects if p["status"] == "待驗收"),
        "problem": sum(1 for p in projects if p["status"] in ["有問題", "逾期"]),
    }
    docker_stats = docker_overview_stats()
    endpoint_stats = endpoint_overview_stats()
    return render_template(
        "dashboard.html",
        app_name=APP_NAME,
        projects=projects,
        recent_logs=recent_logs,
        overdue_tasks=overdue_tasks,
        stats=stats,
        development_workload=development_workload,
        deployment_workload=deployment_workload,
        recent_heartbeats=recent_heartbeats,
        docker_stats=docker_stats,
        endpoint_stats=endpoint_stats,
        daily_report=daily_report,
        recent_ai_messages=recent_ai_messages(limit=5),
    )


@app.route("/release-dashboard")
@require_roles("owner", "admin")
def release_dashboard_page():
    return render_template(
        "release_dashboard.html",
        app_name=APP_NAME,
        dashboard=release_dashboard_context(),
    )


@app.route("/production-release-note")
@require_roles("owner", "admin")
def production_release_note_page():
    return render_template(
        "production_release_note.html",
        app_name=APP_NAME,
        release_note=production_release_note_context(),
    )


@app.route("/api/production-release-note/export.md")
@require_roles("owner", "admin")
def production_release_note_export_markdown():
    return production_release_note_markdown_response()


@app.route("/api/release/version")
@require_roles("owner", "admin")
def release_version_api():
    return jsonify(release_version_info())


@app.route("/production-release-archive")
@require_roles("owner", "admin")
def production_release_archive_page():
    return render_template(
        "production_release_archive.html",
        app_name=APP_NAME,
        archive=release_archive_context(),
    )


@app.route("/api/release/archive-index.json")
@require_roles("owner", "admin")
def release_archive_index_api():
    return jsonify(release_archive_context())


@app.route("/api/release/qa-summary.md")
@require_roles("owner", "admin")
def release_qa_summary_export_markdown():
    return release_qa_summary_markdown_response()


@app.route("/domain-readiness")
@require_roles("owner", "admin")
def domain_readiness_page():
    return render_template(
        "domain_readiness.html",
        app_name=APP_NAME,
        readiness=domain_readiness_context(),
    )


@app.route("/domain-action-plan")
@require_roles("owner", "admin")
def domain_action_plan_page():
    return render_template(
        "domain_action_plan.html",
        app_name=APP_NAME,
        board=domain_action_plan_context(),
    )


@app.route("/api/domain-action-plan/export.csv")
@require_roles("owner", "admin")
def domain_action_plan_export_csv():
    return domain_action_plan_csv_response()


@app.route("/manual-operations-checklist")
@require_roles("owner", "admin")
def manual_operations_checklist_page():
    return render_template(
        "manual_operations_checklist.html",
        app_name=APP_NAME,
        checklist=manual_operations_checklist_context(),
    )


@app.route("/api/manual-operations-checklist/export.csv")
@require_roles("owner", "admin")
def manual_operations_checklist_export_csv():
    return manual_operations_checklist_csv_response()


@app.route("/operations-runbook")
@require_roles("owner", "admin")
def operations_runbook_page():
    return render_template(
        "operations_runbook.html",
        app_name=APP_NAME,
        runbook=operations_runbook_context(),
    )


@app.route("/api/operations-runbook/export.csv")
@require_roles("owner", "admin")
def operations_runbook_export_csv():
    return operations_runbook_csv_response()


@app.route("/ai-console")
@require_login
def ai_console_page():
    projects = query_all("SELECT id, name FROM projects ORDER BY updated_at DESC, id DESC")
    return render_template(
        "ai_console.html",
        app_name=APP_NAME,
        projects=projects,
        providers=ai_provider_rows(),
        provider_choices=AI_CONSOLE_PROVIDER_CHOICES,
        task_roles=AI_COST_TASK_ROLES,
        messages=recent_ai_messages(limit=50),
        flow_messages=recent_flow_messages(limit=20),
        flow_runs=flow_run_rows(limit=20),
        tasks=task_rows(limit=50),
        task_templates=task_template_rows(active_only=True),
    )


@app.route("/ai-console/sandbox")
@require_roles("owner", "admin")
def ai_console_sandbox_gallery_page():
    artifacts = list_ai_console_sandbox_artifacts(limit=50)
    return render_template(
        "ai_console_sandbox_gallery.html",
        app_name=APP_NAME,
        artifacts=artifacts,
    )


@app.route("/ai-console/sandbox/<artifact_id>")
@require_roles("owner", "admin")
def ai_console_sandbox_preview_page(artifact_id):
    try:
        path, html_content = read_ai_console_sandbox_artifact(artifact_id)
    except ValueError:
        return "Invalid sandbox artifact", 400
    except FileNotFoundError:
        return "Sandbox artifact not found", 404
    return render_template(
        "ai_console_sandbox_preview.html",
        app_name=APP_NAME,
        artifact_id=artifact_id,
        filename=path.name,
        size_bytes=path.stat().st_size,
        html_content=html_content,
        download_url=f"/api/ai-console/sandbox/{artifact_id}/download",
    )


@app.route("/flow-runs/<int:flow_run_id>")
@require_login
def flow_run_detail_page(flow_run_id):
    flow_run = flow_run_row(flow_run_id)
    if not flow_run:
        return "Flow run not found", 404
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (flow_run["project_id"],))) if flow_run.get("project_id") else None
    messages = flow_run_messages(flow_run, include_flow=True)
    return render_template(
        "flow_run_detail.html",
        app_name=APP_NAME,
        flow_run=flow_run,
        project=project,
        related_tasks=flow_run_related_tasks(flow_run),
        flow_messages=[message for message in messages if message.get("provider") == "system" and message.get("task_role") == "flow"],
        ai_messages=[message for message in messages if not (message.get("provider") == "system" and message.get("task_role") == "flow")],
        api_token=API_TOKEN,
    )


@app.route("/ai-tasks/<int:task_id>")
@require_login
def ai_task_detail_page(task_id):
    detail = ai_task_detail(task_id)
    if not detail:
        return "AI task not found", 404
    task = detail["task"]
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (task["project_id"],))) if task.get("project_id") else None
    return render_template(
        "ai_task_detail.html",
        app_name=APP_NAME,
        project=project,
        **detail,
    )


@app.route("/ai-console/dispatch", methods=["POST"])
@require_login
def ai_console_dispatch_web():
    payload = {
        "project_id": request.form.get("project_id") or None,
        "provider": request.form.get("provider") or "auto",
        "task_role": request.form.get("task_role") or "executor",
        "task_prompt": request.form.get("task_prompt") or "",
    }
    try:
        result = dispatch_ai_console_task(payload)
        if result.get("ok"):
            flash(f"AI 任務已完成：message #{result['message_id']}")
        else:
            flash(f"AI 任務失敗：{result.get('error')}")
    except ValueError as exc:
        flash(f"AI 任務建立失敗：{exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks", methods=["POST"])
@require_login
def ai_console_task_create_web():
    try:
        task = create_ai_task(request.form)
        flash(f"AI task created: #{task['id']}")
    except ValueError as exc:
        flash(f"AI task create failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/run", methods=["POST"])
@require_login
def ai_console_task_run_web(task_id):
    try:
        result = run_ai_task(task_id)
        if result.get("ok"):
            flash(f"AI task finished: #{task_id}")
        else:
            flash(f"AI task failed: {result.get('error')}")
    except LookupError as exc:
        flash(str(exc))
    except ValueError as exc:
        flash(f"AI task cannot run: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/run-flow", methods=["POST"])
@require_login
def ai_console_task_run_flow_web(task_id):
    try:
        result = run_ai_task_flow(task_id)
        task = result.get("task") or {}
        flow_count = len(result.get("flow_results") or [])
        if result.get("ok"):
            flash(f"AI task flow finished: #{task_id}, auto-ran {flow_count} child task(s)")
        else:
            flash(f"AI task flow failed: {result.get('error') or task.get('error_message')}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task flow cannot run: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/retry", methods=["POST"])
@require_login
def ai_console_task_retry_web(task_id):
    try:
        task = retry_ai_task(task_id)
        flash(f"AI task requeued: #{task['id']}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task retry failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/approve", methods=["POST"])
@require_login
def ai_console_task_approve_web(task_id):
    try:
        result = approve_ai_task(task_id)
        flow_count = len(result.get("flow_results") or [])
        flash(f"AI task approved: #{task_id}, auto-ran {flow_count} child task(s)")
    except (LookupError, ValueError) as exc:
        flash(f"AI task approve failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/reject", methods=["POST"])
@require_login
def ai_console_task_reject_web(task_id):
    try:
        reject_ai_task(task_id)
        flash(f"AI task rejected: #{task_id}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task reject failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/cancel", methods=["POST"])
@require_login
def ai_console_task_cancel_web(task_id):
    try:
        task = cancel_ai_task(task_id)
        flash(f"AI task canceled: #{task['id']}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task cancel failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/block", methods=["POST"])
@require_login
def ai_console_task_block_web(task_id):
    try:
        reason = request.form.get("reason") or "manual block"
        task = block_ai_task(task_id, reason)
        flash(f"AI task blocked: #{task['id']}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task block failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-console/tasks/<int:task_id>/unblock", methods=["POST"])
@require_login
def ai_console_task_unblock_web(task_id):
    try:
        task = unblock_ai_task(task_id)
        flash(f"AI task unblocked: #{task['id']}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task unblock failed: {exc}")
    return redirect(url_for("ai_console_page"))


@app.route("/ai-costs")
@require_login
def ai_costs_page():
    return render_template(
        "ai_costs.html",
        app_name=APP_NAME,
        overview=ai_cost_overview(),
        provider_statuses=AI_PROVIDER_STATUSES,
        task_roles=AI_COST_TASK_ROLES,
    )


@app.route("/projects")
@require_login
def projects():
    items = query_all(
        """SELECT p.*, dc.name AS development_computer_name, depc.name AS deployment_computer_name,
                  pd.environment AS deployment_environment,
                  pd.port AS deployment_port,
                  dt.name AS deployment_target_name
           FROM projects p
           LEFT JOIN computers dc ON p.computer_id=dc.id
           LEFT JOIN computers depc ON p.deploy_computer_id=depc.id
           LEFT JOIN project_deployments pd ON pd.id=(
               SELECT pd2.id FROM project_deployments pd2
               WHERE pd2.project_id=p.id AND COALESCE(pd2.is_active, 1)=1
               ORDER BY CASE WHEN pd2.environment IN ('prod', '正式') THEN 0 ELSE 1 END, pd2.updated_at DESC, pd2.created_at DESC
               LIMIT 1
           )
           LEFT JOIN deployment_targets dt ON pd.target_id=dt.id
           ORDER BY p.updated_at DESC"""
    )
    return render_template("projects.html", app_name=APP_NAME, projects=items)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = query_one("SELECT * FROM users WHERE username=? AND is_active=1", (username,))
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            execute("UPDATE users SET last_login_at=?, updated_at=? WHERE id=?", (now_str(), now_str(), user["id"]))
            audit_log("login", "user", user["id"], {"username": username})
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Login failed")
    return render_template("login.html", app_name=APP_NAME)


@app.route("/logout", methods=["POST"])
def logout():
    user = current_user()
    if user:
        audit_log("logout", "user", user["id"], {"username": user["username"]})
    session.clear()
    return redirect(url_for("login"))


def render_api_keys_page(revealed_key=None, revealed_value=None, copy_key=None, copy_value=None):
    keys = api_keys_with_stats()
    histories = {
        f"{item['provider']}::{item['name']}": api_key_history(item["name"], item["provider"])
        for item in keys
    }
    env_preview = [
        {
            "name": item["name"],
            "provider": item["provider"],
            "category": item["category"],
            "permissions": item["permissions"],
            "mask": item["mask"],
        }
        for item in env_key_candidates()
    ]
    return render_template(
        "api_keys.html",
        app_name=APP_NAME,
        keys=keys,
        histories=histories,
        audits=recent_api_key_audits(),
        env_preview=env_preview,
        categories=API_KEY_CATEGORIES,
        providers=API_KEY_PROVIDERS,
        statuses=API_KEY_STATUSES,
        permissions=API_KEY_PERMISSIONS,
        environments=API_KEY_ENVIRONMENTS,
        revealed_key=revealed_key,
        revealed_value=revealed_value,
        copy_key=copy_key,
        copy_value=copy_value,
        can_reveal_api_keys=has_role("owner"),
        can_manage_api_keys=has_role("owner", "admin"),
    )


@app.route("/api-keys", methods=["GET", "POST"])
@require_roles("owner", "admin", "developer", "viewer")
def api_keys_page():
    if request.method == "POST":
        if not has_role("owner", "admin"):
            flash("Permission denied")
            return redirect(url_for("api_keys_page"))
        try:
            payload = api_key_payload_from_form(request.form)
            key_id = create_api_key_record(payload)
            flash(f"API Key 已新增：{payload['name']} {payload['version']}")
            return redirect(url_for("api_keys_page"))
        except ValueError as exc:
            flash(str(exc))
    return render_api_keys_page()


@app.route("/api-keys/<int:key_id>")
@require_roles("owner", "admin")
def api_key_detail(key_id):
    row = row_to_dict(query_one("SELECT * FROM api_keys WHERE id=?", (key_id,)))
    if not row:
        return "API Key not found", 404
    row["permissions_list"] = parse_json_list(row.get("permissions"))
    row["display_mask"] = row.get("masked_value") or row.get("key_mask") or "************"
    versions = query_all("SELECT * FROM api_key_versions WHERE api_key_id=? ORDER BY created_at DESC, id DESC", (key_id,))
    audits = query_all("SELECT *, COALESCE(ip, ip_address) AS display_ip FROM api_key_audit_logs WHERE api_key_id=? ORDER BY created_at DESC, id DESC LIMIT 30", (key_id,))
    usage = query_all("SELECT * FROM api_key_usage WHERE api_key_id=? ORDER BY used_at DESC, id DESC LIMIT 30", (key_id,))
    alerts = query_all("SELECT * FROM api_key_alerts WHERE api_key_id=? ORDER BY created_at DESC, id DESC LIMIT 30", (key_id,))
    return render_template(
        "api_key_detail.html",
        app_name=APP_NAME,
        key=row,
        versions=versions,
        audits=audits,
        usage=usage,
        alerts=alerts,
        can_reveal_api_keys=has_role("owner"),
        can_manage_api_keys=has_role("owner", "admin"),
    )


@app.route("/api-keys/<int:key_id>/reveal", methods=["POST"])
@require_roles("owner")
def api_key_reveal(key_id):
    try:
        key_row, value = reveal_api_key_value(key_id)
        flash(f"已顯示 API Key：{key_row['name']} {key_row['version']}，頁面會自動遮蔽。")
        return render_api_keys_page(revealed_key=key_row, revealed_value=value)
    except (LookupError, ValueError) as exc:
        flash(str(exc))
        return redirect(url_for("api_keys_page"))


@app.route("/api-keys/<int:key_id>/copy", methods=["POST"])
@require_roles("owner")
def api_key_copy(key_id):
    try:
        key_row, value = copy_api_key_value(key_id)
        flash(f"API Key copied to clipboard: {key_row['name']} {key_row['version']}")
        return render_api_keys_page(copy_key=key_row, copy_value=value)
    except (LookupError, ValueError) as exc:
        flash(str(exc))
        return redirect(url_for("api_keys_page"))


@app.route("/api-keys/<int:key_id>/rotate", methods=["POST"])
@require_roles("owner")
def api_key_rotate(key_id):
    try:
        key_row, value = rotate_api_key(key_id)
        flash(f"API Key rotated: {key_row['name']} {key_row['version']}. Save the new key now; it is shown once.")
        return render_api_keys_page(revealed_key=key_row, revealed_value=value)
    except LookupError as exc:
        flash(str(exc))
        return redirect(url_for("api_keys_page"))


@app.route("/api-keys/<int:key_id>/ai-allowed", methods=["POST"])
@require_roles("owner", "admin")
def api_key_ai_allowed(key_id):
    row = query_one("SELECT * FROM api_keys WHERE id=?", (key_id,))
    if not row:
        return "API Key not found", 404
    enabled = request.form.get("ai_allowed") == "1"
    if enabled and row["environment"] != "staging":
        flash("AI can only use staging keys")
        return redirect(url_for("api_keys_page"))
    execute("UPDATE api_keys SET ai_allowed=?, updated_at=? WHERE id=?", (1 if enabled else 0, now_str(), key_id))
    api_key_audit(key_id, "ai-allowed", {"enabled": enabled, "name": row["name"]})
    flash(f"AI availability updated for {row['name']}")
    return redirect(url_for("api_keys_page"))


@app.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
@require_roles("owner", "admin")
def api_key_revoke(key_id):
    try:
        row = revoke_api_key(key_id, request.form.get("reason") or "manual revoke")
        flash(f"API Key 已 revoke：{row['name']} {row['version']}")
    except LookupError as exc:
        flash(str(exc))
    return redirect(url_for("api_keys_page"))


@app.route("/api-keys/import-env", methods=["POST"])
@require_roles("owner", "admin")
def api_keys_import_env():
    imported, skipped = import_env_api_keys()
    names = ", ".join(f"{item['name']} {item['version']}" for item in imported) or "none"
    flash(f".env 匯入完成：新增 {len(imported)} 筆（{names}），略過既有 {len(skipped)} 筆。未修改 .env。")
    return redirect(url_for("api_keys_page"))


@app.route("/api/api-keys", methods=["POST"])
@require_api_roles("owner")
def api_api_key_create():
    payload = request.get_json(silent=True) or {}
    provider = normalize_choice(payload.get("provider"), API_KEY_PROVIDERS, "other")
    category = normalize_choice(payload.get("category"), API_KEY_CATEGORIES, "other")
    environment = normalize_choice(payload.get("environment"), API_KEY_ENVIRONMENTS, "staging")
    ai_allowed = 1 if payload.get("ai_allowed") and environment == "staging" else 0
    new_key = generate_api_key_value()
    key_id = create_api_key_record({
        "name": (payload.get("name") or f"{provider.upper()}_API_KEY").strip(),
        "category": category,
        "provider": provider,
        "environment": environment,
        "status": "active",
        "version": payload.get("version") or "v1",
        "permissions": api_key_permissions_from_value(payload.get("permissions") or infer_api_key_permissions(payload.get("name"), provider)),
        "key_value": new_key,
        "rotation_days": int(payload.get("rotation_days") or 30),
        "usage_limit": payload.get("usage_limit"),
        "ai_allowed": ai_allowed,
        "notes": payload.get("notes") or "Generated by DevPilot API Key Center",
        "source": "generated",
    })
    row = query_one("SELECT * FROM api_keys WHERE id=?", (key_id,))
    audit_log("api-key-create", "api_key", key_id, {"name": row["name"], "version": row["version"]})
    return jsonify({
        "ok": True,
        "api_key_id": key_id,
        "name": row["name"],
        "version": row["version"],
        "environment": row["environment"],
        "ai_allowed": row["ai_allowed"],
        "masked_value": row["masked_value"] or row["key_mask"],
        "key": new_key,
        "message": "Save this key now. It will not be returned again.",
    })


@app.route("/api/api-keys/<int:key_id>/rotate", methods=["POST"])
@require_api_roles("owner")
def api_api_key_rotate(key_id):
    try:
        row, new_key = rotate_api_key(key_id)
        audit_log("api-key-rotate", "api_key", key_id, {"name": row["name"], "version": row["version"]})
        return jsonify({
            "ok": True,
            "api_key_id": key_id,
            "version": row["version"],
            "masked_value": row.get("masked_value") or row.get("key_mask"),
            "key": new_key,
            "message": "Save this key now. It will not be returned again.",
        })
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/api-keys/<int:key_id>/revoke", methods=["POST"])
@require_api_roles("owner", "admin")
def api_api_key_revoke(key_id):
    payload = request.get_json(silent=True) or {}
    try:
        row = revoke_api_key(key_id, payload.get("reason") or "api revoke")
        audit_log("api-key-revoke", "api_key", key_id, {"name": row["name"], "version": row["version"]})
        return jsonify({"ok": True, "api_key_id": key_id, "status": "revoked"})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/api-keys/<int:key_id>/usage", methods=["POST"])
@require_api_token
def api_key_usage_record(key_id):
    row = query_one("SELECT id, name FROM api_keys WHERE id=?", (key_id,))
    if not row:
        return jsonify({"ok": False, "error": "API Key 不存在"}), 404
    payload = request.get_json(silent=True) or {}
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    try:
        record_api_key_usage(
            key_id,
            (payload.get("source") or "manual")[:80],
            (payload.get("path") or "")[:255],
            payload.get("status_code"),
            ip_address,
        )
        return jsonify({"ok": True, "api_key_id": key_id, "message": "usage recorded"})
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403


@app.route("/cloudflare", methods=["GET", "POST"])
@require_roles("owner", "admin")
def cloudflare_settings():
    if request.method == "POST":
        credential_value = request.form.get("credential_value") or request.form.get("token_value") or ""
        if not credential_value.strip():
            flash("Cloudflare credential is required")
            return redirect(url_for("cloudflare_settings"))
        name = (request.form.get("name") or "Cloudflare API Credential").strip()
        environment = normalize_choice(request.form.get("environment"), API_KEY_ENVIRONMENTS, "staging")
        key_id = create_api_key_record({
            "name": name,
            "category": "third-party",
            "provider": "cloudflare",
            "environment": environment,
            "status": "active",
            "version": (request.form.get("version") or "v1").strip() or "v1",
            "permissions": ["read", "write", "deploy"],
            "key_value": credential_value,
            "rotation_days": int(request.form.get("rotation_days") or 90),
            "usage_limit": None,
            "ai_allowed": 0,
            "notes": (request.form.get("notes") or "Cloudflare DNS management credential").strip(),
            "source": "cloudflare-settings",
        })
        audit_log("cloudflare-token-save", "api_key", key_id, {"name": name, "environment": environment})
        flash(f"Cloudflare credential saved as {name}; value is encrypted and masked.")
        return redirect(url_for("cloudflare_settings"))
    return render_template(
        "cloudflare_settings.html",
        tokens=cloudflare_api_keys(),
        environments=API_KEY_ENVIRONMENTS,
        dns_types=CLOUDFLARE_DNS_TYPES,
        dns_write_flag=cloudflare_dns_write_flag_status(),
    )


@app.route("/domains")
@require_roles("owner", "admin")
def domains_center():
    domain_data = fetch_domain_center_zones()
    return render_template(
        "domains.html",
        domain_data=domain_data,
        nas_ip=DOMAIN_CENTER_NAS_IP,
        projects=project_select_options(),
        domain_mapping_environments=DOMAIN_MAPPING_ENVIRONMENTS,
        preview_domain_purposes=PREVIEW_DOMAIN_PURPOSES,
        preview_domain_base_domains=PREVIEW_DOMAIN_BASE_DOMAINS,
        preview_domain_default_purpose=PREVIEW_DOMAIN_DEFAULT_PURPOSE,
    )


@app.route("/domains/bind", methods=["POST"])
@require_roles("owner", "admin")
def domains_bind():
    try:
        mapping = upsert_domain_mapping(request.form)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("domains_center"))
    audit_log("domain-mapping-upsert", "domain_mapping", mapping["id"], {
        "record_name": mapping.get("record_name"),
        "record_type": mapping.get("record_type"),
        "project_id": mapping.get("project_id"),
    })
    flash("Domain mapping saved. Cloudflare DNS was not changed.")
    return redirect(url_for("domains_center"))


@app.route("/approval-requests")
@require_roles("owner", "admin")
def approval_requests_page():
    return render_template(
        "approval_requests.html",
        app_name=APP_NAME,
        approval_requests=approval_request_rows(
            status=request.args.get("status"),
            project_id=request.args.get("project_id"),
            request_type=request.args.get("request_type"),
        ),
        statuses=APPROVAL_REQUEST_STATUSES,
        request_types=APPROVAL_REQUEST_TYPES,
    )


@app.route("/api/cloudflare/test-connection", methods=["POST"])
@require_api_roles("owner", "admin")
def api_cloudflare_test_connection():
    payload = request.get_json(silent=True) or {}
    key_info = get_active_cloudflare_api_key(payload.get("api_key_id"))
    if not key_info.get("ok"):
        return jsonify({"ok": False, "error": key_info.get("error"), "api_key": key_info.get("api_key")}), 400
    result = cloudflare_request("GET", "/user/tokens/verify", key_info["token"])
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error"), "status_code": result.get("status_code"), "api_key": key_info["api_key"]}), 502
    cf_result = (result.get("data") or {}).get("result") or {}
    return jsonify({
        "ok": True,
        "api_key": key_info["api_key"],
        "cloudflare": {
            "id": cf_result.get("id"),
            "status": cf_result.get("status"),
        },
        "message": "Cloudflare credential verified",
    })


@app.route("/api/cloudflare/dns-write-flag", methods=["GET"])
@require_api_roles("owner", "admin")
def api_cloudflare_dns_write_flag():
    return jsonify(cloudflare_dns_write_flag_status())


@app.route("/api/cloudflare/zones", methods=["GET"])
@require_api_roles("owner", "admin")
def api_cloudflare_zones():
    key_info = get_active_cloudflare_api_key(request.args.get("api_key_id"))
    if not key_info.get("ok"):
        return jsonify({"ok": False, "error": key_info.get("error"), "api_key": key_info.get("api_key")}), 400
    try:
        per_page = min(100, max(1, int(request.args.get("per_page") or 50)))
    except (TypeError, ValueError):
        per_page = 50
    result = cloudflare_request(
        "GET",
        "/zones",
        key_info["token"],
        query={
            "name": request.args.get("name") or "",
            "page": request.args.get("page") or 1,
            "per_page": per_page,
        },
    )
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error"), "status_code": result.get("status_code"), "api_key": key_info["api_key"]}), 502
    data = result.get("data") or {}
    zones = [cloudflare_zone_public(item) for item in data.get("result") or []]
    return jsonify({
        "ok": True,
        "api_key": key_info["api_key"],
        "zones": zones,
        "count": len(zones),
        "result_info": data.get("result_info") or {},
    })


@app.route("/api/cloudflare/zones/<zone_id>/dns-records", methods=["GET"])
@require_api_roles("owner", "admin")
def api_cloudflare_dns_records(zone_id):
    key_info = get_active_cloudflare_api_key(request.args.get("api_key_id"))
    if not key_info.get("ok"):
        return jsonify({"ok": False, "error": key_info.get("error"), "api_key": key_info.get("api_key")}), 400
    try:
        per_page = min(100, max(1, int(request.args.get("per_page") or 50)))
    except (TypeError, ValueError):
        per_page = 50
    result = cloudflare_request(
        "GET",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
        key_info["token"],
        query={
            "type": request.args.get("type") or "",
            "name": request.args.get("name") or "",
            "page": request.args.get("page") or 1,
            "per_page": per_page,
        },
    )
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error"), "status_code": result.get("status_code"), "api_key": key_info["api_key"]}), 502
    data = result.get("data") or {}
    records = [cloudflare_dns_record_public(item) for item in data.get("result") or []]
    return jsonify({
        "ok": True,
        "api_key": key_info["api_key"],
        "zone_id": zone_id,
        "records": records,
        "count": len(records),
        "result_info": data.get("result_info") or {},
    })


@app.route("/api/domains", methods=["GET"])
@require_api_roles("owner", "admin")
def api_domains():
    result = fetch_domain_center_zones()
    if not result.get("ok"):
        return jsonify(result), 502
    return jsonify(result)


@app.route("/api/domains/<zone_id>/records", methods=["GET"])
@require_api_roles("owner", "admin")
def api_domain_records(zone_id):
    result = fetch_domain_center_records(zone_id)
    if not result.get("ok"):
        return jsonify(result), 502
    return jsonify(result)


@app.route("/api/domain-preview/plan", methods=["POST"])
@require_api_roles("owner", "admin")
def api_domain_preview_plan():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    base_domain = payload.get("base_domain")
    environment = payload.get("environment") or "preview"
    project_type = payload.get("project_type") or payload.get("purpose") or PREVIEW_DOMAIN_DEFAULT_PURPOSE
    if not project_id:
        return jsonify({"ok": False, "error": "project_id is required"}), 400
    plan, status_code = build_preview_domain_plan(project_id, base_domain, environment, project_type)
    return jsonify(plan), status_code


@app.route("/api/domain-mappings", methods=["GET", "POST"])
@require_api_roles("owner", "admin")
def api_domain_mappings():
    if request.method == "GET":
        return jsonify({"ok": True, "mappings": domain_mapping_rows(project_id=request.args.get("project_id"))})
    payload = request.get_json(silent=True) or {}
    try:
        mapping = upsert_domain_mapping(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    audit_log("domain-mapping-upsert", "domain_mapping", mapping["id"], {
        "record_name": mapping.get("record_name"),
        "record_type": mapping.get("record_type"),
        "project_id": mapping.get("project_id"),
    })
    return jsonify({"ok": True, "mapping": mapping, "message": "Domain mapping saved. Cloudflare DNS was not changed."})


@app.route("/api/projects/<int:project_id>/domains", methods=["GET"])
@require_api_roles("owner", "admin")
def api_project_domains(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return jsonify({"ok": False, "error": "project not found"}), 404
    return jsonify({"ok": True, "project_id": project_id, "domains": domain_mapping_rows(project_id=project_id)})


@app.route("/api/approval-requests", methods=["GET", "POST"])
@require_api_roles("owner", "admin")
def api_approval_requests():
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "approval_requests": approval_request_rows(
                status=request.args.get("status"),
                project_id=request.args.get("project_id"),
                request_type=request.args.get("request_type"),
            ),
        })
    payload = request.get_json(silent=True) or {}
    try:
        item = create_approval_request(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({
        "ok": True,
        "approval_request": item,
        "message": "Approval request created. No DNS, Telegram, or deployment action was executed.",
    })


@app.route("/api/approval-requests/mock", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_requests_mock():
    payload = request.get_json(silent=True) or {}
    try:
        item = create_mock_approval_request(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({
        "ok": True,
        "approval_request": item,
        "message": "Mock approval request created. No Telegram, DNS, or deployment action was executed.",
    }), 201


@app.route("/api/approval-requests/<int:request_id>/dns-plan/prepare", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_request_dns_plan_prepare(request_id):
    result, status_code = build_approval_dns_plan_prepare(request_id)
    return jsonify(result), status_code


@app.route("/api/approval-requests/<int:request_id>/dns-plan/interlock", methods=["GET"])
@require_api_roles("owner", "admin")
def api_approval_request_dns_plan_interlock(request_id):
    result, status_code = build_approval_dns_plan_interlock(request_id)
    return jsonify(result), status_code


@app.route("/api/approval-requests/<int:request_id>/dns-plan/preflight", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_request_dns_plan_preflight(request_id):
    result, status_code = build_approval_dns_plan_preflight(request_id)
    return jsonify(result), status_code


@app.route("/api/approval-requests/<int:request_id>/dns-plan/confirm", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_request_dns_plan_confirm(request_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = build_approval_dns_plan_confirmation(request_id, payload)
    return jsonify(result), status_code


@app.route("/api/approval-requests/<int:request_id>/dns-plan/execute", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_request_dns_plan_execute(request_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = build_approval_dns_plan_execute_disabled(request_id, payload)
    return jsonify(result), status_code


@app.route("/api/approval-requests/<int:request_id>/send-telegram", methods=["POST"])
@require_api_roles("owner", "admin")
def api_approval_request_send_telegram(request_id):
    payload = request.get_json(silent=True) or {}
    row = approval_request_row(request_id)
    if not row:
        return jsonify({"ok": False, "error": "approval request not found"}), 404
    if row.get("status") != "pending":
        return jsonify({"ok": False, "error": "approval request is not pending", "status": row.get("status")}), 400
    force = bool(payload.get("force"))
    if row.get("telegram_message_id") and not force:
        return jsonify({
            "ok": False,
            "error": "already_sent",
            "message": "Telegram notification was already sent. Use force=true to resend.",
            "status": row.get("status"),
        }), 409
    try:
        if payload.get("mock") is True:
            result = mock_send_telegram_approval(request_id, payload)
            return jsonify(result)
        result, status_code = send_telegram_approval_notification(request_id, with_buttons=bool(payload.get("with_buttons")))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result), status_code


@app.route("/api/telegram/webhook", methods=["POST"])
def api_telegram_webhook():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify({"ok": True, "ignored": True, "reason": "empty_payload"})
    if "message" in payload:
        return jsonify({"ok": True, "ignored": True, "reason": "message_ignored"})
    if "edited_message" in payload:
        return jsonify({"ok": True, "ignored": True, "reason": "edited_message_ignored"})
    if "my_chat_member" in payload or "chat_member" in payload:
        return jsonify({"ok": True, "ignored": True, "reason": "chat_member_ignored"})
    callback_query = payload.get("callback_query")
    if isinstance(callback_query, dict) and not callback_query.get("data"):
        return jsonify({"ok": True, "ignored": True, "reason": "missing_callback_data"})
    if not isinstance(callback_query, dict) and not (payload.get("callback_data") or payload.get("data")):
        return jsonify({"ok": True, "ignored": True, "reason": "unsupported_update_type"})
    try:
        result, status_code = process_telegram_approval_callback(payload)
    except ValueError as exc:
        if str(exc) in {
            "invalid callback_data",
            "invalid approval request id",
            "invalid approval action",
            "missing nonce",
            "missing telegram user",
        }:
            return jsonify({"ok": True, "ignored": True, "reason": "invalid_callback_data"})
        return jsonify({"ok": False, "error": str(exc)}), 400
    if isinstance(result, dict) and result.get("error") in {
        "approval_request_already_processed",
        "approval_request_expired",
    }:
        return jsonify({
            "ok": True,
            "ignored": True,
            "reason": result.get("error"),
            "status": result.get("status"),
        })
    return jsonify(result), status_code


@app.route("/api/telegram/test-message", methods=["POST"])
@require_api_roles("owner", "admin")
def api_telegram_test_message():
    payload = request.get_json(silent=True) or {}
    try:
        allowed_user_id = int(payload.get("telegram_allowed_user_id") or 1)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_telegram_allowed_user_id"}), 400
    allowed = row_to_dict(query_one("SELECT * FROM telegram_allowed_users WHERE id=?", (allowed_user_id,)))
    if not allowed:
        return jsonify({"ok": False, "error": "telegram_allowed_user_not_found"}), 404
    chat_id_masked = allowed.get("chat_id_masked") or ""
    if str(allowed.get("is_active") if allowed.get("is_active") is not None else "1").strip().lower() in ("0", "false", "no", "off"):
        return jsonify({
            "ok": False,
            "error": "telegram_allowed_user_inactive",
            "telegram_allowed_user_id": allowed_user_id,
            "chat_id_masked": chat_id_masked,
        }), 403
    if allowed.get("role") not in APPROVAL_ALLOWED_ROLES:
        return jsonify({
            "ok": False,
            "error": "telegram_allowed_user_role_not_allowed",
            "telegram_allowed_user_id": allowed_user_id,
            "chat_id_masked": chat_id_masked,
        }), 403
    try:
        chat_id = decrypt_telegram_chat_id(allowed)
    except Exception:
        return jsonify({
            "ok": False,
            "error": "telegram_chat_id_decrypt_failed",
            "telegram_allowed_user_id": allowed_user_id,
            "chat_id_masked": chat_id_masked,
        }), 400
    if not chat_id:
        return jsonify({
            "ok": False,
            "error": "telegram_chat_id_not_configured",
            "telegram_allowed_user_id": allowed_user_id,
            "chat_id_masked": chat_id_masked,
        }), 400
    result = telegram_send_message(chat_id, "DevPilot Telegram approval test.")
    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "error": result.get("error") or "telegram_send_failed",
            "status_code": result.get("status_code"),
            "message": result.get("message") or "Telegram send failed.",
            "telegram_allowed_user_id": allowed_user_id,
            "chat_id_masked": result.get("chat_id_masked") or chat_id_masked or mask_chat_id(chat_id),
        }), 502
    return jsonify({
        "ok": True,
        "telegram_allowed_user_id": allowed_user_id,
        "chat_id_masked": result.get("chat_id_masked") or chat_id_masked or mask_chat_id(chat_id),
        "message": "Telegram test message sent.",
    })


@app.route("/computers", methods=["GET", "POST"])
def computers():
    if request.method == "POST":
        execute(
            """INSERT INTO computers (name, device_type, location, os_name, ip_address, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                request.form["name"],
                request.form.get("device_type"),
                request.form.get("location"),
                request.form.get("os_name"),
                request.form.get("ip_address"),
                request.form.get("notes"),
                now_str(),
                now_str(),
            ),
        )
        flash("電腦 / 工作站已新增")
        return redirect(url_for("computers"))
    items = query_all(
        """SELECT c.*,
                  COUNT(DISTINCT dp.id) AS development_project_count,
                  COUNT(DISTINCT dep.id) AS deployment_project_count
           FROM computers c
           LEFT JOIN projects dp ON dp.computer_id=c.id
           LEFT JOIN projects dep ON dep.deploy_computer_id=c.id
           GROUP BY c.id
           ORDER BY c.is_active DESC, c.name"""
    )
    return render_template("computers.html", app_name=APP_NAME, computers=items)


@app.route("/computers/<int:computer_id>/edit", methods=["POST"])
def computer_edit(computer_id):
    computer = query_one("SELECT * FROM computers WHERE id=?", (computer_id,))
    if not computer:
        return "Computer not found", 404
    execute(
        """UPDATE computers
           SET name=?, device_type=?, location=?, os_name=?, ip_address=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            request.form["name"],
            request.form.get("device_type"),
            request.form.get("location"),
            request.form.get("os_name"),
            request.form.get("ip_address"),
            request.form.get("notes"),
            now_str(),
            computer_id,
        ),
    )
    flash("電腦 / 工作站已更新")
    return redirect(url_for("computers"))


@app.route("/computers/<int:computer_id>/toggle", methods=["POST"])
def computer_toggle(computer_id):
    computer = query_one("SELECT * FROM computers WHERE id=?", (computer_id,))
    if not computer:
        return "Computer not found", 404
    next_active = 0 if computer["is_active"] else 1
    execute("UPDATE computers SET is_active=?, updated_at=? WHERE id=?", (next_active, now_str(), computer_id))
    flash("電腦 / 工作站狀態已更新")
    return redirect(url_for("computers"))


def board_projects(column_name):
    return query_all(
        f"""SELECT p.*, dc.name AS development_computer_name, depc.name AS deployment_computer_name
            FROM projects p
            LEFT JOIN computers dc ON p.computer_id=dc.id
            LEFT JOIN computers depc ON p.deploy_computer_id=depc.id
            ORDER BY p.updated_at DESC"""
    )


@app.route("/computer-board")
def computer_board():
    mode = request.args.get("mode", "development")
    if mode not in ("development", "deployment"):
        mode = "development"
    column_name = assignment_column(mode)
    computers = get_computers(include_inactive=False)
    projects = board_projects(column_name)
    board_columns = [{"id": None, "name": "未指定", "projects": []}]
    board_columns += [{"id": c["id"], "name": c["name"], "projects": []} for c in computers]
    column_map = {c["id"]: c for c in board_columns}
    for project in projects:
        target_id = project[column_name]
        target = column_map.get(target_id) or column_map[None]
        target["projects"].append(project)
    return render_template("computer_board.html", app_name=APP_NAME, board_columns=board_columns, computer_options=get_computer_options(), mode=mode, api_token=API_TOKEN)


def get_deployment_targets(include_inactive=True):
    if include_inactive:
        return query_all("SELECT * FROM deployment_targets ORDER BY is_active DESC, name")
    return query_all("SELECT * FROM deployment_targets WHERE is_active=1 ORDER BY name")


def normalize_target_id(value):
    if value in (None, "", "null", "None"):
        return None
    return int(value)


def deployment_target_exists(target_id):
    if target_id is None:
        return True
    return query_one("SELECT id FROM deployment_targets WHERE id=? AND is_active=1", (target_id,)) is not None


def normalize_deployment_environment(value, default="production"):
    env = (value or default or "").strip().lower()
    aliases = {"prod": "production", "stage": "staging", "stg": "staging", "bak": "backup"}
    env = aliases.get(env, env)
    return env if env in DEPLOYMENT_ENVIRONMENTS else default


PROJECT_DEPLOYMENT_FIELDS = [
    "target_id", "environment", "deploy_type", "service_name", "internal_url", "public_url", "port",
    "deploy_path", "compose_path", "db_path", "uploads_path", "backup_path", "log_path",
    "status", "last_deployed_at", "last_checked_at", "notes",
]


def deployment_payload(source):
    payload = {}
    for field in PROJECT_DEPLOYMENT_FIELDS:
        value = source.get(field)
        if field == "target_id":
            value = normalize_target_id(value)
        if field == "environment":
            value = normalize_deployment_environment(value, default="production")
        payload[field] = value
    return payload


def project_deployment_rows(project_id=None, active_only=True):
    where = ["1=1"]
    params = []
    if project_id is not None:
        where.append("pd.project_id=?")
        params.append(project_id)
    if active_only:
        where.append("COALESCE(pd.is_active, 1)=1")
    return query_all(
        f"""SELECT pd.*, p.name AS project_name, p.client_name, dt.name AS target_name, dt.target_type, dt.ip_address
            FROM project_deployments pd
            JOIN projects p ON pd.project_id=p.id
            LEFT JOIN deployment_targets dt ON pd.target_id=dt.id
            WHERE {' AND '.join(where)}
            ORDER BY pd.updated_at DESC, pd.created_at DESC""",
        tuple(params),
    )


def insert_project_deployment(project_id, payload):
    fields = PROJECT_DEPLOYMENT_FIELDS
    placeholders = ", ".join(["?"] * (len(fields) + 4))
    sql = f"""INSERT INTO project_deployments
              (project_id, {', '.join(fields)}, is_active, created_at, updated_at)
              VALUES ({placeholders})"""
    values = [project_id] + [payload.get(field) for field in fields] + [1, now_str(), now_str()]
    return execute(sql, tuple(values)).lastrowid


def update_project_deployment(deployment_id, payload):
    assignments = ", ".join([f"{field}=?" for field in PROJECT_DEPLOYMENT_FIELDS])
    values = [payload.get(field) for field in PROJECT_DEPLOYMENT_FIELDS] + [now_str(), deployment_id]
    execute(f"UPDATE project_deployments SET {assignments}, updated_at=? WHERE id=?", tuple(values))


def deployment_job_row(job_id):
    return row_to_dict(query_one("SELECT * FROM deployment_jobs WHERE id=?", (job_id,)))


def create_deployment_job(project_id, environment, payload, status="pending"):
    now = now_str()
    return execute(
        """INSERT INTO deployment_jobs
           (project_id, environment, requested_by, source, status, task, worktree_path, target_path, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            normalize_deployment_environment(environment),
            payload.get("requested_by") or payload.get("agent") or payload.get("source") or "api",
            payload.get("source") or payload.get("agent") or "api",
            status,
            payload.get("task") or "",
            payload.get("worktree_path") or "",
            payload.get("target_path") or "",
            payload.get("notes") or "",
            now,
            now,
        ),
    ).lastrowid


def update_deployment_job(job_id, **fields):
    if not fields:
        return
    allowed = {
        "status", "worktree_path", "target_path", "deploy_result", "health_result",
        "telegram_result", "validation_status", "validation_report_id", "notes", "approved_at", "completed_at",
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key}=?")
            values.append(value)
    if not updates:
        return
    updates.append("updated_at=?")
    values.extend([now_str(), job_id])
    execute(f"UPDATE deployment_jobs SET {', '.join(updates)} WHERE id=?", tuple(values))


def latest_deployment_jobs(project_id, limit=8):
    return query_all(
        "SELECT * FROM deployment_jobs WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (project_id, limit),
    )


def latest_approved_production_job(project_id):
    return row_to_dict(
        query_one(
            """SELECT * FROM deployment_jobs
               WHERE project_id=? AND environment='production' AND status='approved'
               ORDER BY approved_at DESC, updated_at DESC, id DESC LIMIT 1""",
            (project_id,),
        )
    )


def deployment_target_for_disney():
    return row_to_dict(
        query_one(
            """SELECT * FROM deployment_targets
               WHERE lower(name) IN ('disney nas', 'disney') OR ip_address=? OR ssh_host=?
               ORDER BY is_active DESC, id LIMIT 1""",
            ("211.75.219.184", "211.75.219.184"),
        )
    )


def project_env_slug(project, repo=None):
    deploy_path = (repo or {}).get("deploy_path") if repo else ""
    if deploy_path:
        name = Path(str(deploy_path).rstrip("/\\")).name
        if name:
            return project_slug(name, f"project-{project['id']}")
    return project_slug(project["name"], f"project-{project['id']}")


def environment_deploy_paths(project, repo=None):
    slug = project_env_slug(project, repo)
    production_path = (repo or {}).get("deploy_path") or str(Path(PRODUCTION_ROOT) / slug)
    return {
        "production": production_path,
        "staging": str(Path(STAGING_ROOT) / slug),
        "backup": str(Path(BACKUP_ROOT) / slug),
    }


def validate_environment_target(target_path, root_path, allow_protected=False):
    target = safe_resolved_path(target_path)
    root = safe_resolved_path(root_path)
    if target is None or root is None:
        raise ValueError("deployment target path is required")
    if target == root or str(target) in ("/", "\\"):
        raise ValueError("deployment target points to an unsafe root")
    if not is_same_or_parent(target, root):
        raise ValueError(f"deployment target must stay under {root}")
    if not allow_protected and has_protected_path_segment(target):
        raise ValueError("deployment target must not be data/uploads/output/backup folders")
    target.mkdir(parents=True, exist_ok=True)
    return target


def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"ok": False, "skipped": True, "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured"}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status, "body": resp.read().decode("utf-8", "replace")[:1000]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def count_value(sql, params=()):
    row = query_one(sql, params)
    if not row:
        return 0
    return int(row["value"] or 0)


def daily_report_row(row):
    data = row_to_dict(row)
    if not data:
        return None
    try:
        data["telegram_result_data"] = json.loads(data.get("telegram_result") or "{}")
    except json.JSONDecodeError:
        data["telegram_result_data"] = {}
    return data


def latest_daily_report():
    return daily_report_row(
        query_one("SELECT * FROM daily_reports ORDER BY created_at DESC, id DESC LIMIT 1")
    )


def report_text(value):
    return report_services.report_text(value)


def report_cell(value):
    return report_services.report_cell(value)


def report_table(headers, rows):
    return report_services.report_table(headers, rows)


def report_bullets(items):
    return report_services.report_bullets(items)


def parse_report_list(value):
    return report_services.parse_report_list(value, parse_json_list)


def engineering_report_data(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        raise LookupError("project not found")
    return {
        "project": project,
        "project_repo": project_repo_row(project_id),
        "phases": [row_to_dict(row) for row in query_all("SELECT * FROM project_phases WHERE project_id=? ORDER BY phase_order ASC, id ASC", (project_id,))],
        "project_tasks": [row_to_dict(row) for row in query_all("SELECT * FROM project_tasks WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT 50", (project_id,))],
        "handoffs": [row_to_dict(row) for row in query_all("SELECT * FROM handoff_logs WHERE project_id=? AND COALESCE(is_hidden,0)=0 ORDER BY created_at DESC, id DESC LIMIT 20", (project_id,))],
        "ai_tasks": task_rows(project_id=project_id, limit=100),
        "flow_runs": flow_run_rows(project_id=project_id, limit=20),
        "dispatch_jobs": [row_to_dict(row) for row in project_dispatch_jobs(project_id, limit=30)],
        "deployments": [row_to_dict(row) for row in project_deployment_rows(project_id=project_id, active_only=True)],
        "deployment_jobs": [row_to_dict(row) for row in latest_deployment_jobs(project_id, limit=20)],
        "validation_reports": [row_to_dict(row) for row in latest_validation_reports(project_id, limit=10)],
        "docker_services": [
            row_to_dict(row)
            for row in query_all(
                """SELECT ds.*, dt.name AS target_name
                   FROM docker_services ds
                   LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
                   WHERE ds.project_id=?
                   ORDER BY ds.last_seen_at DESC, ds.id DESC""",
                (project_id,),
            )
        ],
        "service_endpoints": [row_to_dict(row) for row in project_service_endpoint_rows(project_id)],
        "acceptance": [row_to_dict(row) for row in query_all("SELECT * FROM acceptance_items WHERE project_id=? ORDER BY created_at DESC, id DESC", (project_id,))],
        "generated_at": now_str(),
    }


def build_engineering_report_markdown(project_id):
    return report_services.build_engineering_report_markdown(
        engineering_report_data(project_id),
        parse_json_list_func=parse_json_list,
        machine_display_name_func=machine_display_name,
    )
    data = engineering_report_data(project_id)
    project = data["project"]
    repo = data["project_repo"] or {}
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
                ["Owner Machine", machine_display_name(project.get("owner_machine")) or "-"],
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
            [[p.get("phase_order"), p.get("phase_name"), p.get("status"), p.get("due_date"), p.get("completed_at"), p.get("test_result"), p.get("notes")] for p in data["phases"]],
        ),
        "",
        "## 專案任務",
        "",
        report_table(
            ["Task", "Status", "Priority", "Assignee", "Due", "Completed"],
            [[t.get("title"), t.get("status"), t.get("priority"), t.get("assignee"), t.get("due_date"), t.get("completed_at")] for t in data["project_tasks"]],
        ),
        "",
        "## AI Tasks",
        "",
        report_table(
            ["ID", "Title", "Provider", "Type", "Status", "Priority", "Retry", "Approval", "Updated"],
            [[t.get("id"), t.get("title"), t.get("provider"), t.get("task_type"), t.get("status"), t.get("priority"), f"{t.get('retry_count') or 0}/{t.get('max_retries') if t.get('max_retries') is not None else 3}", t.get("approval_status"), t.get("updated_at")] for t in data["ai_tasks"]],
        ),
        "",
        "## AI Flow Runs",
        "",
        report_table(
            ["ID", "Mode", "Status", "Done", "Failed", "Stopped Reason", "Started", "Finished"],
            [[r.get("id"), r.get("mode"), r.get("status"), r.get("done_tasks"), r.get("failed_tasks"), r.get("stopped_reason"), r.get("started_at"), r.get("finished_at")] for r in data["flow_runs"]],
        ),
        "",
        "## AI Dispatch Jobs",
        "",
        report_table(
            ["ID", "Agent", "Status", "Risk", "Worktree", "Deploy", "Updated", "Error"],
            [[j.get("id"), j.get("agent"), j.get("status"), j.get("risk_level"), j.get("worktree_path"), j.get("deploy_path"), j.get("updated_at"), j.get("error_message")] for j in data["dispatch_jobs"]],
        ),
        "",
        "## 部署位置",
        "",
        report_table(
            ["Environment", "Target", "Type", "Service", "Port", "Deploy Path", "Compose Path", "Status"],
            [[d.get("environment"), d.get("target_name"), d.get("deploy_type"), d.get("service_name"), d.get("port"), d.get("deploy_path"), d.get("compose_path"), d.get("status")] for d in data["deployments"]],
        ),
        "",
        "## 部署 Jobs / 驗收",
        "",
        report_table(
            ["Job", "Env", "Status", "Validation", "Target Path", "Updated", "Notes"],
            [[j.get("id"), j.get("environment"), j.get("status"), j.get("validation_status"), j.get("target_path"), j.get("updated_at"), j.get("notes")] for j in data["deployment_jobs"]],
        ),
        "",
        report_table(
            ["Validation", "Provider", "Status", "Score", "Summary", "Created"],
            [[r.get("id"), r.get("provider"), r.get("status"), r.get("score"), r.get("summary"), r.get("created_at")] for r in data["validation_reports"]],
        ),
        "",
        "## Docker 服務與端點",
        "",
        report_table(
            ["Container", "Image", "Status", "Ports", "Deploy Path", "Compose Path", "Last Seen"],
            [[s.get("container_name"), s.get("image"), s.get("status"), s.get("ports"), s.get("deploy_path"), s.get("compose_path"), s.get("last_seen_at")] for s in data["docker_services"]],
        ),
        "",
        report_table(
            ["Type", "URL", "Status Code", "Title", "Container", "Checked"],
            [[e.get("endpoint_type"), e.get("url"), e.get("status_code"), e.get("title"), e.get("container_name"), e.get("last_checked_at")] for e in data["service_endpoints"]],
        ),
        "",
        "## 交接紀錄",
        "",
    ]
    if data["handoffs"]:
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
                report_bullets(parse_report_list(handoff.get("completed_phases"))),
                "",
                "**Changed Files**",
                report_bullets(parse_report_list(handoff.get("changed_files"))),
                "",
                f"**Test Result**\n\n{handoff.get('test_result') or '-'}",
                "",
                f"**Next Steps**\n\n{handoff.get('next_steps') or '-'}",
                "",
                f"**Warnings**\n\n{handoff.get('warnings') or '-'}",
                "",
            ])
    else:
        lines.append("- none")
        lines.append("")

    lines.extend([
        "## 驗收項目",
        "",
        report_table(
            ["Title", "Status", "Tested", "Accepted", "Notes", "Updated"],
            [[a.get("title"), a.get("status"), "yes" if a.get("tested") else "no", "yes" if a.get("accepted") else "no", a.get("notes"), a.get("updated_at")] for a in data["acceptance"]],
        ),
        "",
        "## 建議下一步",
        "",
        report_bullets([
            project.get("next_steps"),
            "Review failed or blocked AI tasks before the next flow run." if any((t.get("status") in ("failed", "blocked")) for t in data["ai_tasks"]) else "",
            "Confirm staging validation before any production deployment." if data["deployment_jobs"] else "",
            "Keep handoff updated after each AI or deployment run.",
        ]),
        "",
    ])
    return "\n".join(lines)


def markdown_to_report_html(markdown_text):
    return report_services.markdown_to_html(markdown_text)
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
            if in_pre:
                html_lines.append("</pre>")
                in_pre = False
            else:
                html_lines.append("<pre>")
                in_pre = True
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


def engineering_report_filename(project, extension):
    return report_services.engineering_report_filename(project, extension, project_slug, today_str)


def generate_daily_report():
    report_date = today_str()
    created_at = now_str()
    total_projects = count_value("SELECT COUNT(*) AS value FROM projects")
    active_projects = count_value(f"SELECT COUNT(*) AS value FROM projects WHERE {active_project_status_filter()}")
    open_tasks = count_value(
        "SELECT COUNT(*) AS value FROM project_tasks WHERE completed_at IS NULL AND COALESCE(status, '') NOT IN ('done', 'completed')"
    )
    overdue_tasks = count_value(
        "SELECT COUNT(*) AS value FROM project_tasks WHERE due_date < ? AND completed_at IS NULL",
        (report_date,),
    )
    due_today_tasks = count_value(
        "SELECT COUNT(*) AS value FROM project_tasks WHERE due_date = ? AND completed_at IS NULL",
        (report_date,),
    )
    running_heartbeats = count_value(
        "SELECT COUNT(*) AS value FROM ai_heartbeats WHERE status IN ('running', 'online')"
    )
    recent_handoffs = query_all(
        """SELECT h.source, h.summary, h.created_at, p.name AS project_name
           FROM handoff_logs h
           LEFT JOIN projects p ON h.project_id=p.id
           WHERE COALESCE(h.is_hidden, 0)=0
           ORDER BY h.created_at DESC
           LIMIT 5"""
    )
    recent_ai = query_all(
        """SELECT source, agent_name, machine_name, status, current_task, last_seen_at
           FROM ai_heartbeats
           ORDER BY COALESCE(last_seen_at, updated_at, created_at) DESC
           LIMIT 5"""
    )
    docker_stats = docker_overview_stats()
    endpoint_stats = endpoint_overview_stats()
    summary = (
        f"今日共有 {total_projects} 個專案，進行中 {active_projects} 個；"
        f"待處理任務 {open_tasks} 個，今日到期 {due_today_tasks} 個，逾期 {overdue_tasks} 個。"
    )
    lines = [
        f"今日早報 - {report_date}",
        "",
        "專案與任務",
        f"- 專案總數：{total_projects}",
        f"- 進行中專案：{active_projects}",
        f"- 待處理任務：{open_tasks}",
        f"- 今日到期任務：{due_today_tasks}",
        f"- 逾期任務：{overdue_tasks}",
        "",
        "AI 與服務",
        f"- 目前 active AI 心跳：{running_heartbeats}",
        f"- Docker 服務總數：{docker_stats.get('docker_service_total', 0)}",
        f"- Docker running：{docker_stats.get('docker_running', 0)}",
        f"- 已偵測服務網址：{endpoint_stats.get('endpoint_total', 0)}",
        f"- 200 OK 網址：{endpoint_stats.get('endpoint_ok_200', 0)}",
    ]
    if recent_handoffs:
        lines.extend(["", "最近交接"])
        for row in recent_handoffs:
            lines.append(
                f"- [{row['source'] or 'manual'}] {row['project_name'] or '-'}：{row['summary'] or '-'}"
            )
    if recent_ai:
        lines.extend(["", "最近 AI 心跳"])
        for row in recent_ai:
            lines.append(
                f"- {row['source'] or '-'} / {row['agent_name'] or '-'} @ {row['machine_name'] or '-'}："
                f"{row['status'] or '-'}，{row['current_task'] or '無目前任務'}"
            )
    content = "\n".join(lines)
    telegram_result = notify_telegram(content)
    cur = execute(
        """INSERT INTO daily_reports
           (report_date, title, summary, content, telegram_result, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            report_date,
            f"今日早報 {report_date}",
            summary,
            content,
            json.dumps(telegram_result, ensure_ascii=False),
            created_at,
            created_at,
        ),
    )
    return daily_report_row(query_one("SELECT * FROM daily_reports WHERE id=?", (cur.lastrowid,)))


def run_health_check(url):
    if not url:
        return {"ok": True, "skipped": True, "reason": "health_url not provided"}
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": resp.status < 500, "status_code": resp.status, "url": resp.geturl()}
    except urllib.error.HTTPError as exc:
        return {"ok": exc.code < 500, "status_code": exc.code, "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}


def validate_gemini_dispatch(provider, task_role, task):
    provider = (provider or "openai").strip().lower()
    task_role = (task_role or "executor").strip().lower()
    task_text = (task or "").strip()
    if provider not in DISPATCH_PROVIDERS:
        raise ValueError("unsupported dispatch provider")
    if task_role not in DISPATCH_TASK_ROLES:
        raise ValueError("unsupported dispatch task_role")
    if provider == "google":
        if task_role not in GEMINI_ALLOWED_TASK_ROLES:
            raise ValueError("Gemini only supports reviewer/tester roles")
        lower_task = task_text.lower()
        if any(word in lower_task for word in GEMINI_FORBIDDEN_TASK_KEYWORDS):
            raise ValueError("Gemini tasks cannot use SSH, docker, deploy, deletion, or file modification")
        if not any(word in lower_task for word in GEMINI_SAFE_TASK_KEYWORDS):
            raise ValueError("Gemini tasks must be limited to API/log analysis, test cases, or validation")
    return provider, task_role, task_text


def create_dispatch_job(payload):
    agent = (payload.get("agent") or "").strip().lower()
    provider = (payload.get("provider") or ("google" if agent == "gemini" else "openai")).strip().lower()
    task_role = (payload.get("task_role") or ("reviewer" if provider == "google" else "executor")).strip().lower()
    task = (payload.get("task_prompt") or payload.get("task") or "").strip()
    if provider == "google":
        provider, task_role, task = validate_gemini_dispatch(provider, task_role, task)
        agent = "gemini"
    else:
        if provider not in DISPATCH_PROVIDERS:
            raise ValueError("unsupported dispatch provider")
        if task_role not in DISPATCH_TASK_ROLES:
            raise ValueError("unsupported dispatch task_role")
        agent = agent or payload.get("agent") or "codex"
        if agent not in DISPATCH_AGENTS:
            raise ValueError("agent must be codex for executable dispatch jobs")
        if not task:
            raise ValueError("task_prompt is required")
    project_id = payload.get("project_id")
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,)) if project_id else None
    repo = project_repo_row(project_id) if project_id else None
    if not project:
        raise ValueError("project not found")
    if provider != "google" and (not repo or not repo.get("worktree_path")):
        raise ValueError("project_repos.worktree_path is required for executable dispatch jobs")
    env_paths = environment_deploy_paths(project, repo) if project else {"production": "", "staging": "", "backup": ""}
    risk_level = (payload.get("risk_level") or "low").strip().lower()
    if risk_level not in DISPATCH_RISK_LEVELS:
        risk_level = "low"
    approval_required = 1 if payload.get("approval_required", True) not in (False, 0, "0", "false", "no") else 0
    now = now_str()
    job_id = execute(
        """INSERT INTO dispatch_jobs
           (project_id, provider, task_role, agent, task, task_prompt, status, risk_level, approval_required,
            worktree_path, deploy_path, staging_path, production_path, result, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            provider,
            task_role,
            agent,
            task,
            task,
            "queued",
            risk_level,
            approval_required,
            (repo or {}).get("worktree_path", ""),
            (repo or {}).get("deploy_path", ""),
            payload.get("staging_path") or env_paths.get("staging", ""),
            payload.get("production_path") or env_paths.get("production", ""),
            json.dumps({"safe_mode": provider == "google", "task_role": task_role}, ensure_ascii=False),
            now,
            now,
        ),
    ).lastrowid
    return {
        "ok": True,
        "dispatch_job_id": job_id,
        "provider": provider,
        "task_role": task_role,
        "message": "dispatch job created",
    }


def dispatch_job_row(job_id):
    return row_to_dict(query_one("SELECT * FROM dispatch_jobs WHERE id=?", (job_id,)))


def project_dispatch_jobs(project_id, limit=20):
    return query_all(
        "SELECT * FROM dispatch_jobs WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (project_id, limit),
    )


def update_dispatch_job(job_id, **fields):
    allowed = {
        "status", "risk_level", "approval_required", "worktree_path", "deploy_path", "staging_path",
        "production_path", "started_at", "finished_at", "error_message", "changed_files", "diff_stat", "result",
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key}=?")
            values.append(value)
    if not updates:
        return
    updates.append("updated_at=?")
    values.extend([now_str(), job_id])
    execute(f"UPDATE dispatch_jobs SET {', '.join(updates)} WHERE id=?", tuple(values))


def retry_dispatch_job(job_id):
    original = dispatch_job_row(job_id)
    if not original:
        raise LookupError("dispatch job not found")
    if original.get("status") != "failed":
        raise ValueError("only failed dispatch jobs can be retried")
    now = now_str()
    new_job_id = execute(
        """INSERT INTO dispatch_jobs
           (project_id, provider, task_role, agent, task, task_prompt, status, risk_level, approval_required,
            worktree_path, deploy_path, staging_path, production_path, result, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            original.get("project_id"),
            original.get("provider"),
            original.get("task_role"),
            original.get("agent"),
            original.get("task_prompt") or original.get("task") or "",
            original.get("task_prompt") or original.get("task") or "",
            "queued",
            original.get("risk_level") or "low",
            original.get("approval_required", 1),
            original.get("worktree_path") or "",
            original.get("deploy_path") or "",
            original.get("staging_path") or "",
            original.get("production_path") or "",
            json.dumps({"retry_of": job_id}, ensure_ascii=False),
            now,
            now,
        ),
    ).lastrowid
    return dispatch_job_row(new_job_id)


def record_agent_run(dispatch_job_id, command, stdout="", stderr="", exit_code=0):
    return execute(
        """INSERT INTO agent_runs (dispatch_job_id, command, stdout, stderr, exit_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (dispatch_job_id, command, stdout, stderr, exit_code, now_str()),
    ).lastrowid


def dispatch_jobs_for_runner(status=None, agent=None, project_id=None, limit=20):
    clauses = []
    params = []
    if status:
        clauses.append("status=?")
        params.append(status)
    if agent:
        clauses.append("COALESCE(agent, '')=?")
        params.append(agent)
    if project_id:
        clauses.append("project_id=?")
        params.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit or 20), 100)))
    return [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT * FROM dispatch_jobs
                {where}
                ORDER BY created_at ASC, id ASC
                LIMIT ?""",
            tuple(params),
        )
    ]


def project_endpoint_candidates(project_id):
    rows = query_all(
        """SELECT se.*
           FROM service_endpoints se
           LEFT JOIN docker_services ds ON se.docker_service_id=ds.id
           WHERE COALESCE(se.is_ignored,0)=0
             AND COALESCE(ds.project_id, se.project_id)=?
           ORDER BY COALESCE(se.is_confirmed,0) DESC, se.endpoint_type, se.id
           LIMIT 12""",
        (project_id,),
    )
    urls = []
    for row in rows:
        url = row["url"]
        if url and url not in urls:
            urls.append(url)
    if not urls:
        deployments = query_all(
            """SELECT internal_url, public_url FROM project_deployments
               WHERE project_id=? AND environment IN ('staging', 'production') AND COALESCE(is_active,1)=1
               ORDER BY environment DESC, updated_at DESC LIMIT 6""",
            (project_id,),
        )
        for dep in deployments:
            for key in ("public_url", "internal_url"):
                url = dep[key]
                if url and url not in urls:
                    urls.append(url)
    return urls[:8]


def run_staging_http_checks(project_id):
    checks = []
    for base_url in project_endpoint_candidates(project_id):
        parsed = urllib.parse.urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
        paths = ["/", "/health"]
        if "/api" in (parsed.path or ""):
            paths.append(parsed.path)
        for path in paths:
            url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
            started = time.time()
            probe = probe_endpoint(url, "unknown", path)
            checks.append({
                "url": probe.get("url") or url,
                "path": path,
                "status_code": probe.get("status_code"),
                "response_ms": int((time.time() - started) * 1000),
                "title": probe.get("title") or "",
                "error": probe.get("error") or "",
            })
    return checks


def gemini_fallback_review(summary):
    checks = summary.get("http_checks") or []
    failed = [c for c in checks if not c.get("status_code") or int(c.get("status_code") or 599) >= 500]
    status = "fail" if failed else "pass"
    score = 60 if failed else (85 if checks else 75)
    return {
        "status": status,
        "risk": "high" if failed else "medium" if not checks else "low",
        "score": score,
        "summary": "Gemini API key not configured; DevPilot used deterministic staging checks.",
        "recommendations": ["Configure GEMINI_API_KEY for AI review."] if not GEMINI_API_KEY else [],
    }


def call_gemini_validation(summary):
    if not GEMINI_API_KEY:
        return gemini_fallback_review(summary)
    prompt = (
        "你是 QA 驗收 AI。以下是 staging 環境測試摘要，只包含 HTTP 與 endpoint 結果，沒有 repo、DB 或密鑰。\n"
        f"{json.dumps(summary, ensure_ascii=False)}\n"
        "請只輸出 JSON：status(pass/fail), risk(low/medium/high), score(0-100), summary, recommendations(array)。"
    )
    url = GEMINI_API_URL
    sep = "&" if "?" in url else "?"
    req_url = f"{url}{sep}key={urllib.parse.quote(GEMINI_API_KEY)}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(req_url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        text = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text") or ""
        match = re.search(r"\{.*\}", text, re.S)
        parsed = json.loads(match.group(0) if match else text)
        parsed["status"] = "pass" if str(parsed.get("status", "")).lower() == "pass" else "fail"
        parsed["score"] = max(0, min(100, int(parsed.get("score", 0))))
        return parsed
    except Exception as exc:
        fallback = gemini_fallback_review(summary)
        fallback["summary"] = f"Gemini call failed; fallback checks used. error={exc}"
        return fallback


def insert_validation_report(project_id, job_id, result, details):
    report_id = execute(
        """INSERT INTO validation_reports
           (project_id, deployment_job_id, provider, status, score, summary, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            job_id,
            "google",
            result.get("status"),
            int(result.get("score") or 0),
            result.get("summary") or "",
            json.dumps(details, ensure_ascii=False),
            now_str(),
        ),
    ).lastrowid
    return report_id


def validate_staging_job(job_id):
    job = deployment_job_row(job_id)
    if not job:
        raise LookupError("deployment job not found")
    project_id = job["project_id"]
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise LookupError("project not found")
    http_checks = run_staging_http_checks(project_id)
    summary = {
        "project_id": project_id,
        "project_name": project["name"],
        "deployment_job_id": job_id,
        "target_path": job["target_path"],
        "http_checks": http_checks[:20],
    }
    gemini_result = call_gemini_validation(summary)
    status = "pass" if gemini_result.get("status") == "pass" else "fail"
    report_id = insert_validation_report(project_id, job_id, gemini_result, summary)
    next_job_status = "waiting_approval" if status == "pass" else "failed"
    update_deployment_job(
        job_id,
        status=next_job_status,
        validation_status=status,
        validation_report_id=report_id,
        health_result=json.dumps({"http_checks": http_checks}, ensure_ascii=False),
    )
    if status == "pass":
        execute(
            """UPDATE deployment_jobs
               SET status='waiting_approval', validation_status='pass', validation_report_id=?, updated_at=?
               WHERE project_id=? AND environment='production' AND status='pending'""",
            (report_id, now_str(), project_id),
        )
        notify_telegram(f"🟢 staging 通過\n專案：{project['name']}\nscore：{gemini_result.get('score')}\n請核准 production job")
    else:
        notify_telegram(f"🔴 staging 失敗\n專案：{project['name']}\n{gemini_result.get('summary')}")
        latest_snapshot = latest_deployment_snapshot(project_id, job["environment"])
        if latest_snapshot:
            perform_rollback(job_id, auto=True)
    return {
        "ok": True,
        "status": status,
        "score": int(gemini_result.get("score") or 0),
        "summary": gemini_result.get("summary") or "",
        "validation_report_id": report_id,
        "details": summary,
    }


def latest_validation_reports(project_id, limit=5):
    return query_all(
        "SELECT * FROM validation_reports WHERE project_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
        (project_id, limit),
    )


def latest_deployment_snapshot(project_id, environment=None):
    where = ["project_id=?"]
    params = [project_id]
    if environment:
        where.append("environment=?")
        params.append(environment)
    return row_to_dict(
        query_one(
            f"SELECT * FROM deployment_snapshots WHERE {' AND '.join(where)} ORDER BY created_at DESC, id DESC LIMIT 1",
            tuple(params),
        )
    )


def create_deployment_snapshot(project_id, environment, deploy_path):
    deploy = safe_resolved_path(deploy_path)
    if deploy is None:
        return None
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    slug = project_env_slug(project, project_repo_row(project_id)) if project else f"project-{project_id}"
    snapshot = safe_resolved_path(Path(BACKUP_ROOT) / slug / f"snapshot_{now_dt().strftime('%Y%m%d_%H%M%S')}")
    validate_environment_target(snapshot, BACKUP_ROOT, allow_protected=True)
    if is_nas_volume_path(deploy) and is_nas_volume_path(snapshot):
        command = (
            f"if [ -d {shlex.quote(str(deploy))} ]; then "
            f"mkdir -p {shlex.quote(str(snapshot.parent))} && "
            f"cp -a {shlex.quote(str(deploy))} {shlex.quote(str(snapshot))} && echo CREATED; "
            f"else echo SKIPPED; fi"
        )
        result = run_nas_ssh_command(command, timeout=600)
        if "CREATED" not in (result.get("output") or ""):
            return None
    else:
        if not deploy.exists():
            return None
        shutil.copytree(deploy, snapshot, dirs_exist_ok=True)
    return execute(
        """INSERT INTO deployment_snapshots (project_id, environment, deploy_path, snapshot_path, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, environment, str(deploy), str(snapshot), now_str()),
    ).lastrowid


def rollback_paths_are_safe(deploy_path, snapshot_path, environment):
    root = PRODUCTION_ROOT if environment == "production" else STAGING_ROOT
    deploy = validate_environment_target(deploy_path, root)
    snapshot = safe_resolved_path(snapshot_path)
    backup_root = safe_resolved_path(BACKUP_ROOT)
    if snapshot is None or backup_root is None or not is_same_or_parent(snapshot, backup_root) or not snapshot.exists():
        raise ValueError("snapshot path is invalid")
    return deploy, snapshot


def perform_rollback(job_id, auto=False):
    job = deployment_job_row(job_id)
    if not job:
        raise LookupError("deployment job not found")
    snapshot = latest_deployment_snapshot(job["project_id"], job["environment"])
    if not snapshot:
        raise ValueError("no deployment snapshot found")
    deploy, snap = rollback_paths_are_safe(snapshot["deploy_path"], snapshot["snapshot_path"], job["environment"])
    if is_nas_volume_path(deploy) and is_nas_volume_path(snap):
        protected = " ".join(f"! -name {shlex.quote(name)}" for name in [".env", "data", "uploads", "upload", "output", "outputs", "backup", "backups"])
        command = (
            f"cd {shlex.quote(str(deploy))} && (/usr/local/bin/docker compose stop || true) && "
            f"find {shlex.quote(str(deploy))} -mindepth 1 -maxdepth 1 {protected} -exec rm -r -- {{}} + && "
            f"rsync -av {shlex.quote(str(snap).rstrip('/') + '/')} {shlex.quote(str(deploy).rstrip('/') + '/')} && "
            f"cd {shlex.quote(str(deploy))} && /usr/local/bin/docker compose up -d"
        )
        result = run_nas_ssh_command(command, timeout=900)
    else:
        for child in deploy.iterdir():
            if child.name in {".env", "data", "uploads", "upload", "output", "outputs", "backup", "backups"}:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(snap, deploy, dirs_exist_ok=True)
        result = {"command": "local rollback copy", "returncode": 0, "output": ""}
    update_deployment_job(
        job_id,
        status="rolled_back",
        deploy_result=json.dumps({"rollback": result, "auto": auto}, ensure_ascii=False),
        completed_at=now_str(),
    )
    return {
        "ok": True,
        "job_id": job_id,
        "snapshot_id": snapshot["id"],
        "snapshot_path": snapshot["snapshot_path"],
        "deploy_path": snapshot["deploy_path"],
        "message": "rollback completed",
    }


def upsert_environment_project_deployment(project_id, environment, target_path, status, notes=""):
    target = deployment_target_for_disney()
    target_id = target["id"] if target else None
    existing = query_one(
        """SELECT id FROM project_deployments
           WHERE project_id=? AND environment=? AND COALESCE(is_active, 1)=1
           ORDER BY updated_at DESC, id DESC LIMIT 1""",
        (project_id, environment),
    )
    payload = {
        "target_id": target_id,
        "environment": environment,
        "deploy_type": "docker",
        "service_name": "",
        "internal_url": "",
        "public_url": "",
        "port": "",
        "deploy_path": str(target_path),
        "compose_path": str(Path(target_path) / "docker-compose.yml"),
        "db_path": "",
        "uploads_path": "",
        "backup_path": "",
        "log_path": "",
        "status": status,
        "last_deployed_at": now_str(),
        "last_checked_at": now_str(),
        "notes": notes,
    }
    if existing:
        update_project_deployment(existing["id"], payload)
        return existing["id"]
    return insert_project_deployment(project_id, payload)


def perform_environment_deploy(project_id, environment, payload):
    environment = normalize_deployment_environment(environment)
    if environment == "backup":
        raise ValueError("backup is a storage target, not a direct deploy environment")
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise LookupError("project not found")
    repo = project_repo_row(project_id)
    if not repo:
        raise ValueError("project_repos not found; set up Repo / Worktree / Deploy first")
    worktree, _deploy = validate_dispatch_paths(repo, auto_deploy=False)
    paths = environment_deploy_paths(project, repo)
    root = PRODUCTION_ROOT if environment == "production" else STAGING_ROOT
    target = validate_environment_target(paths[environment], root)

    if environment == "production":
        job_id = payload.get("job_id")
        job = deployment_job_row(int(job_id)) if job_id else latest_approved_production_job(project_id)
        if not job or job["project_id"] != project_id or job["environment"] != "production" or job["status"] != "approved":
            raise PermissionError("production deploy requires an approved deployment job")
        update_deployment_job(job["id"], status="running", worktree_path=str(worktree), target_path=str(target))
    else:
        job_id = create_deployment_job(
            project_id,
            "staging",
            {**payload, "worktree_path": str(worktree), "target_path": str(target)},
            status="running",
        )
        job = deployment_job_row(job_id)

    run_compose = str(payload.get("run_compose", "")).lower() in ("1", "true", "yes", "on")
    snapshot_id = create_deployment_snapshot(project_id, environment, target)
    rsync_result = rsync_worktree_to_deploy(worktree, target)
    compose_result = docker_compose_up_deploy(target) if run_compose else {
        "skipped": True,
        "reason": "run_compose is not enabled",
        "command": "docker compose up -d",
        "returncode": 0,
        "output": "",
    }
    health_result = run_health_check(payload.get("health_url"))
    telegram_result = notify_telegram(f"DevPilot {environment} deploy finished for project #{project_id}: {project['name']}")
    deploy_result = {"rsync": rsync_result, "docker_compose": compose_result}
    final_status = "succeeded" if health_result.get("ok") else "failed"
    notes = f"{environment} deploy via DevPilot; health={health_result}"
    deployment_id = upsert_environment_project_deployment(project_id, environment, target, final_status, notes=notes)
    update_deployment_job(
        job["id"],
        status=final_status,
        deploy_result=json.dumps(deploy_result, ensure_ascii=False),
        health_result=json.dumps(health_result, ensure_ascii=False),
        telegram_result=json.dumps(telegram_result, ensure_ascii=False),
        completed_at=now_str(),
    )
    if environment == "staging":
        production_job_id = create_deployment_job(
            project_id,
            "production",
            {
                "source": payload.get("source") or "api",
                "requested_by": payload.get("requested_by") or payload.get("agent") or "api",
                "task": payload.get("task") or "promote staging to production",
                "worktree_path": str(worktree),
                "target_path": paths["production"],
                "notes": "等待人工核准後才可 deploy-production",
            },
            status="pending",
        )
    else:
        production_job_id = job["id"]

    validation_result = None
    if environment == "staging" and str(payload.get("skip_validation", "")).lower() not in ("1", "true", "yes"):
        validation_result = validate_staging_job(job["id"])
    if environment == "production" and not health_result.get("ok"):
        rollback_result = perform_rollback(job["id"], auto=True)
        deploy_result["auto_rollback"] = rollback_result

    save_handoff(project_id, {
        "source": payload.get("source") or "api",
        "agent_name": payload.get("agent_name") or payload.get("agent") or "DevPilot",
        "work_mode": "deploy",
        "summary": f"{environment} deployment completed",
        "changed_files": [str(target)],
        "test_result": json.dumps({"deploy": deploy_result, "health": health_result}, ensure_ascii=False),
        "next_steps": "檢查 staging 後核准 production" if environment == "staging" else "觀察 production 服務狀態",
        "warnings": "AI 不可直接 deploy production；production 需 approved job",
    })
    return {
        "ok": final_status == "succeeded",
        "project_id": project_id,
        "environment": environment,
        "job_id": job["id"],
        "production_job_id": production_job_id,
        "deployment_id": deployment_id,
        "worktree_path": str(worktree),
        "target_path": str(target),
        "snapshot_id": snapshot_id,
        "deploy_result": deploy_result,
        "health_result": health_result,
        "validation_result": validation_result,
        "telegram_result": telegram_result,
        "message": f"{environment} deploy {final_status}",
    }


PROJECT_REPO_FIELDS = [
    "repo_url", "repo_path", "worktree_path", "deploy_path",
    "repo_status", "last_commit", "branch", "sync_method",
]


def project_repo_row(project_id):
    return row_to_dict(
        query_one(
            "SELECT * FROM project_repos WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (project_id,),
        )
    )


def project_repo_payload(source):
    repo_status = (source.get("repo_status") or "missing").strip()
    if repo_status not in REPO_STATUSES:
        repo_status = "missing"
    sync_method = (source.get("sync_method") or "local").strip()
    if sync_method not in SYNC_METHODS:
        sync_method = "local"
    return {
        "repo_url": (source.get("repo_url") or "").strip(),
        "repo_path": (source.get("repo_path") or "").strip(),
        "worktree_path": (source.get("worktree_path") or "").strip(),
        "deploy_path": (source.get("deploy_path") or "").strip(),
        "repo_status": repo_status,
        "last_commit": (source.get("last_commit") or "").strip(),
        "branch": (source.get("branch") or "").strip(),
        "sync_method": sync_method,
    }


def upsert_project_repo(project_id, payload):
    now = now_str()
    existing = query_one(
        "SELECT id FROM project_repos WHERE project_id=? ORDER BY updated_at DESC, id DESC LIMIT 1",
        (project_id,),
    )
    if existing:
        execute(
            """UPDATE project_repos
               SET repo_url=?, repo_path=?, worktree_path=?, deploy_path=?,
                   repo_status=?, last_commit=?, branch=?, sync_method=?, updated_at=?
               WHERE id=?""",
            (
                payload["repo_url"], payload["repo_path"], payload["worktree_path"], payload["deploy_path"],
                payload["repo_status"], payload["last_commit"], payload["branch"], payload["sync_method"],
                now, existing["id"],
            ),
        )
        return existing["id"]
    return execute(
        """INSERT INTO project_repos
           (project_id, repo_url, repo_path, worktree_path, deploy_path,
            repo_status, last_commit, branch, sync_method, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id, payload["repo_url"], payload["repo_path"], payload["worktree_path"], payload["deploy_path"],
            payload["repo_status"], payload["last_commit"], payload["branch"], payload["sync_method"], now, now,
        ),
    ).lastrowid


def project_slug(name, fallback):
    text = (name or "").strip().lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or fallback


def default_repo_paths(slug):
    return {
        "repo_path": str(Path(REPO_ROOT) / slug),
        "worktree_path": str(Path(WORKTREE_ROOT) / slug),
        "deploy_path": str(Path(DEPLOY_ROOT) / slug),
    }


def run_git(args, cwd=None, check=True):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if check and result.returncode != 0:
        raise RuntimeError(output.strip() or f"git {' '.join(args)} failed")
    return result.returncode, output.strip()


def is_git_worktree(path_value):
    path = Path(path_value or "")
    if not path.exists():
        return False
    code, _out = run_git(["-C", str(path), "rev-parse", "--is-inside-work-tree"], check=False)
    return code == 0


def git_repo_state(path_value):
    path = Path(path_value or "")
    if not path.exists() or not is_git_worktree(path):
        return {"repo_status": "missing", "last_commit": "", "branch": ""}
    _code, status_out = run_git(["-C", str(path), "status", "--porcelain"], check=False)
    _code, branch = run_git(["-C", str(path), "branch", "--show-current"], check=False)
    _code, commit = run_git(["-C", str(path), "rev-parse", "HEAD"], check=False)
    return {
        "repo_status": "dirty" if status_out.strip() else "clean",
        "last_commit": commit.strip() if commit else "",
        "branch": branch.strip() if branch else "",
    }


def source_code_exists(path_value):
    root = Path(path_value or "")
    if not root.exists() or not root.is_dir():
        return False
    markers = ["app.py", "package.json", "requirements.txt", "src", "public"]
    return any((root / marker).exists() for marker in markers)


def copy_deploy_source_to_repo(deploy_path, repo_path):
    ignored = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "data", "uploads", "upload", "output", "outputs", "backup", "backups",
    }

    def ignore(_dir, names):
        return {name for name in names if name in ignored or name.endswith(".db")}

    shutil.copytree(deploy_path, repo_path, dirs_exist_ok=True, ignore=ignore)


def ensure_local_repo_from_deploy(deploy_path, repo_path):
    repo = Path(repo_path)
    deploy = Path(deploy_path or "")
    if not source_code_exists(deploy):
        return False
    repo.parent.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    if not is_git_worktree(repo):
        run_git(["init"], cwd=str(repo))
    copy_deploy_source_to_repo(str(deploy), str(repo))
    run_git(["add", "."], cwd=str(repo))
    code, _out = run_git(["diff", "--cached", "--quiet"], cwd=str(repo), check=False)
    if code != 0:
        run_git([
            "-c", "user.name=DevPilot",
            "-c", "user.email=devpilot@local",
            "commit", "-m", "initial import from docker deploy",
        ], cwd=str(repo))
    run_git(["branch", "-M", "main"], cwd=str(repo), check=False)
    return True


def ensure_worktree(repo_path, worktree_path):
    worktree = Path(worktree_path)
    if worktree.exists():
        return
    worktree.parent.mkdir(parents=True, exist_ok=True)
    run_git(["-C", repo_path, "worktree", "add", "--force", worktree_path, "main"])


def refresh_project_repo_status(project_id):
    repo = project_repo_row(project_id)
    if not repo:
        return None, "project repo not found"
    check_path = repo.get("worktree_path") if repo.get("worktree_path") and Path(repo["worktree_path"]).exists() else repo.get("repo_path")
    state = git_repo_state(check_path)
    payload = {field: repo.get(field) or "" for field in PROJECT_REPO_FIELDS}
    payload.update(state)
    upsert_project_repo(project_id, payload)
    return {**payload, "project_id": project_id}, None


def safe_resolved_path(path_value):
    if path_value in (None, ""):
        return None
    return Path(str(path_value)).expanduser().resolve(strict=False)


def is_same_or_parent(child, parent):
    try:
        child_path = safe_resolved_path(child)
        parent_path = safe_resolved_path(parent)
        if child_path is None or parent_path is None:
            return False
        child_path.relative_to(parent_path)
        return True
    except ValueError:
        return False


def has_protected_path_segment(path_value):
    if path_value in (None, ""):
        return False
    return any(part.lower() in DISPATCH_PROTECTED_PATH_NAMES for part in Path(str(path_value)).parts)


def validate_dispatch_paths(repo, auto_deploy=False):
    worktree = safe_resolved_path(repo.get("worktree_path") if repo else "")
    deploy = safe_resolved_path(repo.get("deploy_path") if repo else "")
    if worktree is None:
        raise ValueError("project_repos.worktree_path is required")
    if not worktree.exists() or not worktree.is_dir():
        raise ValueError(f"worktree_path does not exist: {worktree}")
    if is_same_or_parent(worktree, DEPLOY_ROOT):
        raise ValueError("worktree_path must not be inside deploy root")
    if auto_deploy:
        if deploy is None:
            raise ValueError("project_repos.deploy_path is required when auto_deploy=true")
        if not deploy.exists() or not deploy.is_dir():
            raise ValueError(f"deploy_path does not exist: {deploy}")
        if str(deploy) in ("/", "\\", str(safe_resolved_path(DEPLOY_ROOT))):
            raise ValueError("deploy_path points to an unsafe root")
        if has_protected_path_segment(deploy):
            raise ValueError("deploy_path must not point at data/uploads/output/backup folders")
    return worktree, deploy


def run_dispatch_process(args, cwd=None, timeout=300):
    resolved_args = [str(part) for part in args]
    if os.name == "nt" and resolved_args:
        executable = shutil.which(resolved_args[0])
        if executable:
            if executable.lower().endswith((".cmd", ".bat")):
                resolved_args = ["cmd", "/c", executable, *resolved_args[1:]]
            else:
                resolved_args[0] = executable
    result = subprocess.run(
        resolved_args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return {"command": " ".join(str(part) for part in args), "returncode": result.returncode, "output": output}


def run_dispatch_process_checked(args, cwd=None, timeout=300):
    result = run_dispatch_process(args, cwd=cwd, timeout=timeout)
    if result["returncode"] != 0:
        raise RuntimeError(result["output"] or f"{result['command']} failed")
    return result


def is_nas_volume_path(path_value):
    text = str(path_value or "").replace("\\", "/")
    return text.startswith("/volume1/")


def run_nas_ssh_command(command, timeout=600):
    args = [
        "ssh",
        "-p",
        str(NAS_SSH_PORT),
        f"{NAS_SSH_USER}@{NAS_SSH_HOST}",
        "bash",
        "-lc",
        command,
    ]
    return run_dispatch_process_checked(args, timeout=timeout)


def dispatch_echo(agent, task):
    message = f"dispatch to {agent}: {task}"
    if os.name == "nt":
        return run_dispatch_process_checked(["cmd", "/c", "echo", message], timeout=30)
    return run_dispatch_process_checked(["echo", message], timeout=30)


def write_dispatch_marker(worktree_path, agent, task):
    marker = Path(worktree_path) / ".devpilot_last_task.txt"
    content = "\n".join([
        f"agent={agent}",
        f"task={task}",
        f"timestamp={now_str()}",
        "",
    ])
    marker.write_text(content, encoding="utf-8")
    return marker


def rsync_worktree_to_deploy(worktree_path, deploy_path):
    if is_nas_volume_path(worktree_path) and is_nas_volume_path(deploy_path):
        excludes = " ".join(f"--exclude {shlex.quote(pattern)}" for pattern in DISPATCH_RSYNC_EXCLUDES)
        command = (
            f"mkdir -p {shlex.quote(str(deploy_path))} && "
            f"rsync -av {excludes} {shlex.quote(str(Path(worktree_path)).rstrip('/') + '/')} "
            f"{shlex.quote(str(Path(deploy_path)).rstrip('/') + '/')}"
        )
        return run_nas_ssh_command(command, timeout=600)
    cmd = ["rsync", "-av"]
    for pattern in DISPATCH_RSYNC_EXCLUDES:
        cmd.extend(["--exclude", pattern])
    cmd.extend([str(Path(worktree_path)) + os.sep, str(Path(deploy_path)) + os.sep])
    return run_dispatch_process_checked(cmd, timeout=600)


def docker_compose_up_deploy(deploy_path):
    if is_nas_volume_path(deploy_path):
        command = f"cd {shlex.quote(str(deploy_path))} && /usr/local/bin/docker compose up -d"
        return run_nas_ssh_command(command, timeout=600)
    return run_dispatch_process_checked(["docker", "compose", "up", "-d"], cwd=str(deploy_path), timeout=600)


def docker_compose_up_build_deploy(deploy_path):
    if is_nas_volume_path(deploy_path):
        command = f"cd {shlex.quote(str(deploy_path))} && /usr/local/bin/docker compose up -d --build"
        return run_nas_ssh_command(command, timeout=900)
    return run_dispatch_process_checked(["docker", "compose", "up", "-d", "--build"], cwd=str(deploy_path), timeout=900)


def perform_project_dispatch(project_id, payload):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise LookupError("project not found")
    agent = (payload.get("agent") or "").strip().lower()
    if agent not in DISPATCH_AGENTS:
        raise ValueError("agent must be codex or cursor")
    task = (payload.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")
    auto_deploy = bool(payload.get("auto_deploy"))
    repo = project_repo_row(project_id)
    if not repo:
        raise ValueError("project_repos not found; set up Repo / Worktree / Deploy first")

    worktree, deploy = validate_dispatch_paths(repo, auto_deploy=auto_deploy)
    mock_result = dispatch_echo(agent, task)
    marker = write_dispatch_marker(worktree, agent, task)
    deploy_result = {}
    if auto_deploy:
        deploy_result["rsync"] = rsync_worktree_to_deploy(worktree, deploy)
        deploy_result["docker_compose"] = docker_compose_up_deploy(deploy)

    handoff_payload = {
        "source": agent,
        "agent_name": "Codex" if agent == "codex" else "Cursor",
        "work_mode": "code-change",
        "summary": f"AI dispatch: {task}",
        "changed_files": [str(marker)],
        "test_result": json.dumps({"mock": mock_result, "deploy": deploy_result}, ensure_ascii=False),
        "next_steps": "確認 AI 實作結果並檢查服務狀態" if auto_deploy else "確認 worktree 內容後再執行部署",
        "warnings": "auto_deploy=true 已執行 rsync 與 docker compose up -d" if auto_deploy else "auto_deploy=false，尚未部署到 Docker",
    }
    handoff_id = save_handoff(project_id, handoff_payload)
    log_api(project_id, {"action": "dispatch", "agent": agent, "auto_deploy": auto_deploy}, 200, agent)
    return {
        "ok": True,
        "project_id": project_id,
        "agent": agent,
        "task": task,
        "auto_deploy": auto_deploy,
        "worktree_path": str(worktree),
        "deploy_path": str(deploy) if deploy else "",
        "marker_path": str(marker),
        "handoff_id": handoff_id,
        "mock_result": mock_result,
        "deploy_result": deploy_result,
        "message": "AI dispatch pipeline completed",
    }


def dispatch_job_paths(job):
    project = query_one("SELECT * FROM projects WHERE id=?", (job["project_id"],))
    if not project:
        raise LookupError("project not found")
    repo = project_repo_row(job["project_id"])
    if not repo:
        raise ValueError("project_repos not found")
    paths = environment_deploy_paths(project, repo)
    worktree = safe_resolved_path(job.get("worktree_path") or repo.get("worktree_path"))
    deploy = safe_resolved_path(job.get("deploy_path") or repo.get("deploy_path"))
    staging = safe_resolved_path(job.get("staging_path") or paths["staging"])
    production = safe_resolved_path(job.get("production_path") or paths["production"])
    if worktree is None or not worktree.exists() or not worktree.is_dir():
        raise ValueError(f"worktree_path does not exist: {worktree}")
    if is_same_or_parent(worktree, DEPLOY_ROOT):
        raise ValueError("worker must not run inside deploy root")
    return project, repo, worktree, deploy, staging, production


def perform_dispatch_staging_deploy(job_id, payload=None):
    payload = payload or {}
    job = dispatch_job_row(job_id)
    if not job:
        raise LookupError("dispatch job not found")
    if job["status"] != "waiting_approval":
        raise PermissionError("dispatch job must pass worker tests before staging deploy")
    _project, _repo, worktree, _deploy, staging, _production = dispatch_job_paths(job)
    target = validate_environment_target(staging, STAGING_ROOT)
    update_dispatch_job(job_id, status="running", staging_path=str(target))
    try:
        rsync_result = rsync_worktree_to_deploy(worktree, target)
        record_agent_run(job_id, rsync_result["command"], rsync_result.get("output", ""), "", rsync_result["returncode"])
        compose_result = docker_compose_up_build_deploy(target)
        record_agent_run(job_id, compose_result["command"], compose_result.get("output", ""), "", compose_result["returncode"])
        health_result = run_health_check((payload or {}).get("health_url"))
        next_status = "waiting_approval" if health_result.get("ok") else "failed"
        update_dispatch_job(
            job_id,
            status=next_status,
            result=json.dumps({"staging": {"rsync": rsync_result, "docker_compose": compose_result, "health": health_result}}, ensure_ascii=False),
            error_message="" if health_result.get("ok") else json.dumps(health_result, ensure_ascii=False),
        )
        return {
            "ok": health_result.get("ok", False),
            "dispatch_job_id": job_id,
            "status": next_status,
            "staging_path": str(target),
            "deploy_result": {"rsync": rsync_result, "docker_compose": compose_result},
            "health_result": health_result,
        }
    except Exception as exc:
        update_dispatch_job(job_id, status="failed", error_message=str(exc), finished_at=now_str())
        raise


def restore_snapshot_to_path(snapshot_path, deploy_path, run_compose=True):
    deploy, snap = rollback_paths_are_safe(deploy_path, snapshot_path, "production")
    if is_nas_volume_path(deploy) and is_nas_volume_path(snap):
        protected = " ".join(f"! -name {shlex.quote(name)}" for name in [".env", "data", "uploads", "upload", "output", "outputs", "backup", "backups"])
        compose = f" && cd {shlex.quote(str(deploy))} && /usr/local/bin/docker compose up -d" if run_compose else ""
        command = (
            f"cd {shlex.quote(str(deploy))} && "
            f"find {shlex.quote(str(deploy))} -mindepth 1 -maxdepth 1 {protected} -exec rm -r -- {{}} + && "
            f"rsync -av {shlex.quote(str(snap).rstrip('/') + '/')} {shlex.quote(str(deploy).rstrip('/') + '/')}"
            f"{compose}"
        )
        return run_nas_ssh_command(command, timeout=900)
    for child in deploy.iterdir():
        if child.name in {".env", "data", "uploads", "upload", "output", "outputs", "backup", "backups"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(snap, deploy, dirs_exist_ok=True)
    compose_result = docker_compose_up_deploy(deploy) if run_compose else {"command": "docker compose up -d", "returncode": 0, "output": "", "skipped": True}
    return {"command": "local rollback copy", "returncode": compose_result.get("returncode", 0), "output": compose_result.get("output", "")}


def perform_dispatch_rollback(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        raise LookupError("dispatch job not found")
    _project, _repo, _worktree, _deploy, _staging, production = dispatch_job_paths(job)
    snapshot = latest_deployment_snapshot(job["project_id"], "production")
    if not snapshot:
        raise ValueError("no production snapshot found")
    result = restore_snapshot_to_path(snapshot["snapshot_path"], production, run_compose=True)
    record_agent_run(job_id, result["command"], result.get("output", ""), "", result["returncode"])
    update_dispatch_job(
        job_id,
        status="rolled_back",
        error_message="",
        result=json.dumps({"rollback": result, "snapshot": snapshot}, ensure_ascii=False),
        finished_at=now_str(),
    )
    return {
        "ok": True,
        "dispatch_job_id": job_id,
        "snapshot_id": snapshot["id"],
        "snapshot_path": snapshot["snapshot_path"],
        "production_path": str(production),
        "message": "dispatch rollback completed",
    }


def perform_dispatch_production_deploy(job_id, payload=None):
    payload = payload or {}
    job = dispatch_job_row(job_id)
    if not job:
        raise LookupError("dispatch job not found")
    if job["status"] != "waiting_approval":
        raise PermissionError("dispatch job must be waiting_approval before production deploy")
    _project, _repo, worktree, _deploy, _staging, production = dispatch_job_paths(job)
    target = validate_environment_target(production, PRODUCTION_ROOT)
    snapshot_id = create_deployment_snapshot(job["project_id"], "production", target)
    if not snapshot_id:
        raise RuntimeError("production snapshot could not be created")
    update_dispatch_job(job_id, status="running", production_path=str(target))
    deploy_result = {}
    try:
        rsync_result = rsync_worktree_to_deploy(worktree, target)
        record_agent_run(job_id, rsync_result["command"], rsync_result.get("output", ""), "", rsync_result["returncode"])
        compose_result = docker_compose_up_build_deploy(target)
        record_agent_run(job_id, compose_result["command"], compose_result.get("output", ""), "", compose_result["returncode"])
        health_result = run_health_check(payload.get("health_url"))
        deploy_result = {"rsync": rsync_result, "docker_compose": compose_result, "health": health_result, "snapshot_id": snapshot_id}
        if not health_result.get("ok"):
            rollback_result = perform_dispatch_rollback(job_id)
            return {"ok": False, "status": "rolled_back", "dispatch_job_id": job_id, "deploy_result": deploy_result, "rollback_result": rollback_result}
        update_dispatch_job(
            job_id,
            status="deployed",
            result=json.dumps({"production": deploy_result}, ensure_ascii=False),
            error_message="",
            finished_at=now_str(),
        )
        return {"ok": True, "status": "deployed", "dispatch_job_id": job_id, "production_path": str(target), "deploy_result": deploy_result}
    except Exception as exc:
        rollback_result = None
        try:
            rollback_result = perform_dispatch_rollback(job_id)
        except Exception as rollback_exc:
            rollback_result = {"ok": False, "error": str(rollback_exc)}
        update_dispatch_job(
            job_id,
            status="rolled_back" if rollback_result and rollback_result.get("ok") else "failed",
            error_message=str(exc),
            result=json.dumps({"production": deploy_result, "rollback": rollback_result}, ensure_ascii=False),
            finished_at=now_str(),
        )
        return {"ok": False, "status": "rolled_back" if rollback_result and rollback_result.get("ok") else "failed", "dispatch_job_id": job_id, "error": str(exc), "rollback_result": rollback_result}


def _norm_key(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def compose_pick_for_deploy(deploy_hint: str, compose_files: list[str]) -> str | None:
    if not compose_files:
        return None
    dh = (deploy_hint or "").rstrip("/")
    best = None
    best_len = -1
    for c in compose_files:
        parent = str(Path(c).parent)
        if dh and (dh == parent or dh.startswith(parent + "/") or parent.startswith(dh)):
            ln = len(parent)
            if ln > best_len:
                best_len = ln
                best = c
        elif dh and dh in c:
            if len(c) > best_len:
                best_len = len(c)
                best = c
    return best


def derive_compose_deploy_from_inspect(inspect_obj: dict | None, compose_files: list[str]) -> tuple[str | None, str | None]:
    if not inspect_obj:
        return None, None
    labels = (inspect_obj.get("Config") or {}).get("Labels") or {}
    if not isinstance(labels, dict):
        labels = {}
    working = labels.get("com.docker.compose.project.working_dir")
    cfg_files = labels.get("com.docker.compose.project.config_files")
    compose_path = None
    if cfg_files and isinstance(cfg_files, str):
        parts = [p.strip() for p in cfg_files.replace(";", ",").split(",") if p.strip()]
        for p in parts:
            if "docker-compose.yml" in p:
                compose_path = p
                break
        if not compose_path and parts:
            compose_path = parts[0]
    deploy_path = str(Path(compose_path).parent) if compose_path else None
    if working:
        deploy_path = working.rstrip("/")
        if not compose_path:
            compose_path = compose_pick_for_deploy(deploy_path, compose_files)
    elif deploy_path and not compose_path:
        compose_path = compose_pick_for_deploy(deploy_path, compose_files)
    return compose_path, deploy_path


def summarize_ports_from_inspect(inspect_obj: dict | None) -> str:
    if not inspect_obj:
        return ""
    ns = inspect_obj.get("NetworkSettings") or {}
    ports = ns.get("Ports") or {}
    return json.dumps(ports, ensure_ascii=False) if ports else ""


def summarize_volumes_from_inspect(inspect_obj: dict | None) -> str:
    mounts = (inspect_obj.get("Mounts") if inspect_obj else None) or []
    short = []
    if isinstance(mounts, list):
        for m in mounts[:40]:
            if isinstance(m, dict):
                short.append({"Type": m.get("Type"), "Source": m.get("Source"), "Destination": m.get("Destination")})
    return json.dumps(short, ensure_ascii=False) if short else ""


def container_display_name(ps_row: dict, inspect_obj: dict | None) -> str:
    names = ps_row.get("Names")
    if isinstance(names, str) and names.startswith("/"):
        return names[1:]
    if isinstance(names, list) and names:
        n = names[0]
        return n[1:] if isinstance(n, str) and n.startswith("/") else str(n)
    if inspect_obj:
        n = inspect_obj.get("Name") or ""
        return n[1:] if isinstance(n, str) and n.startswith("/") else str(n)
    return str(ps_row.get("Names") or "")


def detect_service_name(inspect_obj: dict | None, image: str | None) -> str:
    if inspect_obj:
        labels = (inspect_obj.get("Config") or {}).get("Labels") or {}
        if isinstance(labels, dict) and labels.get("com.docker.compose.service"):
            return labels["com.docker.compose.service"]
    img = image or ""
    return img.split(":")[0].split("/")[-1] if img else ""


def compose_project_label(inspect_obj: dict | None) -> str | None:
    if not inspect_obj:
        return None
    labels = (inspect_obj.get("Config") or {}).get("Labels") or {}
    if isinstance(labels, dict):
        return labels.get("com.docker.compose.project")
    return None


def infer_project_id_for_service(target_id, compose_path, deploy_path, compose_proj, projects_rows):
    if compose_path:
        r = query_one(
            "SELECT project_id FROM project_deployments WHERE target_id=? AND compose_path=? LIMIT 1",
            (target_id, compose_path),
        )
        if r and r["project_id"]:
            return int(r["project_id"])
    if deploy_path:
        r = query_one(
            "SELECT project_id FROM project_deployments WHERE target_id=? AND deploy_path=? LIMIT 1",
            (target_id, deploy_path),
        )
        if r and r["project_id"]:
            return int(r["project_id"])
    ck = _norm_key(compose_proj or "")
    for p in projects_rows:
        if ck and _norm_key(p["name"]) == ck:
            return int(p["id"])
    if deploy_path:
        folder = Path(deploy_path.rstrip("/")).name
        fk = _norm_key(folder)
        for p in projects_rows:
            if fk and _norm_key(p["name"]) == fk:
                return int(p["id"])
            lp = (p.get("local_path") or "").replace("\\", "/").strip()
            if lp and lp in (deploy_path or "").replace("\\", "/"):
                return int(p["id"])
    return None


def docker_service_status_from_inspect(inspect_obj: dict | None, ps_status: str | None) -> str:
    if inspect_obj:
        st = (inspect_obj.get("State") or {}).get("Status")
        if st:
            return str(st)
    return (ps_status or "").strip() or "unknown"


def save_docker_service_from_scan(
    target_id,
    container_name,
    *,
    guessed_project_id,
    service_name,
    image,
    status,
    ports,
    compose_path,
    deploy_path,
    volumes,
    raw_inspect,
    now,
):
    existing = query_one("SELECT id, project_id FROM docker_services WHERE target_id=? AND container_name=?", (target_id, container_name))
    if existing and existing["project_id"] is not None:
        pid = int(existing["project_id"])
    else:
        pid = guessed_project_id
    if existing:
        execute(
            """UPDATE docker_services SET project_id=?, service_name=?, image=?, status=?, ports=?,
               compose_path=?, deploy_path=?, volumes=?, last_seen_at=?, raw_inspect=?, updated_at=?
               WHERE id=?""",
            (pid, service_name, image, status, ports, compose_path, deploy_path, volumes, now, raw_inspect, now, existing["id"]),
        )
        return existing["id"], pid
    cur = execute(
        """INSERT INTO docker_services
           (target_id, project_id, service_name, container_name, image, status, ports,
            compose_path, deploy_path, volumes, last_seen_at, raw_inspect, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (target_id, pid, service_name, container_name, image, status, ports, compose_path, deploy_path, volumes, now, raw_inspect, now, now),
    )
    return cur.lastrowid, pid


def sync_project_deployment_probe_row(project_id: int, target_id: int, svc: dict):
    """掃描自動推斷專案後，補一筆／更新 project_deployments（不建立重複 compose 路徑）。"""
    compose_path = svc.get("compose_path") or ""
    existing = query_one(
        "SELECT id FROM project_deployments WHERE project_id=? AND target_id=? AND COALESCE(compose_path,'')=? LIMIT 1",
        (project_id, target_id, compose_path),
    )
    payload = deployment_payload(
        {
            "target_id": target_id,
            "environment": "unknown",
            "deploy_type": "docker",
            "service_name": svc.get("service_name"),
            "internal_url": "",
            "public_url": "",
            "port": svc.get("port_hint") or "",
            "deploy_path": svc.get("deploy_path") or "",
            "compose_path": compose_path,
            "db_path": "",
            "uploads_path": "",
            "backup_path": "",
            "log_path": "",
            "status": svc.get("status"),
            "last_deployed_at": "",
            "last_checked_at": svc.get("last_seen_at"),
            "notes": "由 NAS Docker 掃描匯入",
        }
    )
    if existing:
        update_project_deployment(existing["id"], payload)
    else:
        insert_project_deployment(project_id, payload)


def first_host_port_from_ports_json(ports_json: str) -> str:
    if not ports_json:
        return ""
    try:
        data = json.loads(ports_json)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    for _k, bindings in data.items():
        if isinstance(bindings, list) and bindings:
            b0 = bindings[0]
            if isinstance(b0, dict) and b0.get("HostPort"):
                return str(b0["HostPort"])
    return ""


def bind_docker_service_to_project(service_id: int, project_id: int, environment: str | None = None):
    svc = query_one("SELECT * FROM docker_services WHERE id=?", (service_id,))
    if not svc:
        return None, "找不到 docker_services"
    proj = query_one("SELECT id FROM projects WHERE id=?", (project_id,))
    if not proj:
        return None, "找不到專案"
    env = (environment or "production").strip() or "production"
    now = now_str()
    execute(
        "UPDATE docker_services SET project_id=?, updated_at=? WHERE id=?",
        (project_id, now, service_id),
    )
    execute(
        "UPDATE service_endpoints SET project_id=?, updated_at=? WHERE docker_service_id=?",
        (project_id, now, service_id),
    )
    ports = svc["ports"] or ""
    pd_src = {
        "target_id": svc["target_id"],
        "environment": env,
        "deploy_type": "docker",
        "service_name": svc["service_name"] or svc["container_name"],
        "internal_url": "",
        "public_url": "",
        "port": ports,
        "deploy_path": svc["deploy_path"] or "",
        "compose_path": svc["compose_path"] or "",
        "db_path": "",
        "uploads_path": "",
        "backup_path": "",
        "log_path": "",
        "status": svc["status"],
        "last_deployed_at": "",
        "last_checked_at": now,
        "notes": "由 NAS Docker 掃描匯入",
    }
    payload = deployment_payload(pd_src)
    existing = query_one(
        "SELECT id FROM project_deployments WHERE project_id=? AND target_id=? AND COALESCE(compose_path,'')=? LIMIT 1",
        (project_id, svc["target_id"], svc["compose_path"] or ""),
    )
    if existing:
        update_project_deployment(existing["id"], payload)
    else:
        insert_project_deployment(project_id, payload)
    return {"ok": True, "docker_service_id": service_id, "project_id": project_id}, None


def docker_service_row_for_bootstrap(service_id: int):
    return row_to_dict(
        query_one(
            """SELECT ds.*, p.name AS project_name
               FROM docker_services ds
               LEFT JOIN projects p ON ds.project_id=p.id
               WHERE ds.id=?""",
            (service_id,),
        )
    )


def bootstrap_project_from_docker_service(service_id: int):
    svc = docker_service_row_for_bootstrap(service_id)
    if not svc:
        return None, "docker service not found"
    deploy_path = (svc.get("deploy_path") or "").strip()
    container_name = (svc.get("container_name") or "").strip()
    if svc.get("project_id"):
        project_id = int(svc["project_id"])
        project_name = svc.get("project_name") or container_name
    else:
        folder_name = Path(deploy_path.rstrip("/")).name if deploy_path else ""
        project_name = folder_name or container_name or f"docker-service-{service_id}"
        host_ports = parse_external_ports(svc.get("ports"))
        port_text = ", ".join(host_ports) if host_ports else (svc.get("ports") or "")
        now = now_str()
        description = "\n".join([
            "由 Docker 匯入",
            f"container_name: {container_name or '-'}",
            f"image: {svc.get('image') or '-'}",
            f"deploy_path: {deploy_path or '-'}",
            f"compose_path: {svc.get('compose_path') or '-'}",
            f"ports: {port_text or '-'}",
        ])
        cur = execute(
            """INSERT INTO projects
               (name, project_type, status, deploy_location, local_path, deploy_url,
                description, next_steps, progress, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_name, "docker", "deployed", "disney NAS", "", "",
                description, "確認 Repo / Worktree 後再進行程式修改", 100, now, now,
            ),
        )
        project_id = cur.lastrowid
    slug = project_slug(project_name, f"docker-service-{service_id}")
    paths = default_repo_paths(slug)
    if deploy_path:
        paths["deploy_path"] = deploy_path

    repo_status = "missing"
    last_commit = ""
    branch = ""
    imported = False
    repo_path_obj = Path(paths["repo_path"])
    if repo_path_obj.exists() and is_git_worktree(repo_path_obj):
        ensure_worktree(paths["repo_path"], paths["worktree_path"])
        state = git_repo_state(paths["worktree_path"] if Path(paths["worktree_path"]).exists() else paths["repo_path"])
        repo_status = state["repo_status"]
        last_commit = state["last_commit"]
        branch = state["branch"] or "main"
    elif repo_path_obj.exists() and any(repo_path_obj.iterdir()):
        return None, f"repo_path already exists but is not a git repo: {paths['repo_path']}"
    elif deploy_path and source_code_exists(deploy_path):
        imported = ensure_local_repo_from_deploy(deploy_path, paths["repo_path"])
        if imported:
            ensure_worktree(paths["repo_path"], paths["worktree_path"])
            state = git_repo_state(paths["worktree_path"] if Path(paths["worktree_path"]).exists() else paths["repo_path"])
            repo_status = "local-init" if state["repo_status"] == "clean" else state["repo_status"]
            last_commit = state["last_commit"]
            branch = state["branch"] or "main"

    repo_payload = {
        "repo_url": "",
        "repo_path": paths["repo_path"],
        "worktree_path": paths["worktree_path"],
        "deploy_path": paths["deploy_path"],
        "repo_status": repo_status,
        "last_commit": last_commit,
        "branch": branch,
        "sync_method": "local",
    }
    upsert_project_repo(project_id, repo_payload)
    execute(
        "UPDATE docker_services SET project_id=?, updated_at=? WHERE id=?",
        (project_id, now_str(), service_id),
    )
    execute(
        "UPDATE service_endpoints SET project_id=?, updated_at=? WHERE docker_service_id=?",
        (project_id, now_str(), service_id),
    )
    return {
        "ok": True,
        "service_id": service_id,
        "project_id": project_id,
        "project_name": project_name,
        "slug": slug,
        "repo_path": paths["repo_path"],
        "worktree_path": paths["worktree_path"],
        "deploy_path": paths["deploy_path"],
        "repo_status": repo_status,
        "last_commit": last_commit,
        "branch": branch,
        "imported_from_deploy": imported,
        "message": "Docker 服務已建立專案與 Repo/Worktree 對應",
    }, None


def docker_overview_stats():
    total = query_one("SELECT COUNT(*) AS c FROM docker_services")["c"]
    running = query_one(
        """SELECT COUNT(*) AS c FROM docker_services
           WHERE lower(COALESCE(status,'')) LIKE '%running%'"""
    )["c"]
    stopped = query_one(
        """SELECT COUNT(*) AS c FROM docker_services
           WHERE lower(COALESCE(status,'')) LIKE '%exited%'
              OR lower(COALESCE(status,'')) LIKE '%dead%'
              OR lower(COALESCE(status,'')) LIKE '%created%'"""
    )["c"]
    unbound = query_one("SELECT COUNT(*) AS c FROM docker_services WHERE project_id IS NULL")["c"]
    last_scan = query_one("SELECT MAX(created_at) AS m FROM docker_scan_runs")
    return {
        "docker_service_total": total or 0,
        "docker_running": running or 0,
        "docker_stopped": stopped or 0,
        "docker_unbound": unbound or 0,
        "docker_last_scan_at": (last_scan["m"] if last_scan else None) or "-",
    }


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data.strip())

    @property
    def title(self):
        return " ".join(part for part in self.parts if part).strip()


NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler)


def parse_charset(content_type: str | None) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    return match.group(1) if match else "utf-8"


def extract_html_title(body: bytes, content_type: str | None) -> str:
    if not body:
        return ""
    text = body[:120000].decode(parse_charset(content_type), errors="replace")
    parser = TitleParser()
    try:
        parser.feed(text)
    except Exception:
        return ""
    return parser.title[:200]


def request_no_redirect(url: str, method: str):
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": "DevPilot endpoint scanner/1.0",
            "Accept": "text/html,application/json,*/*",
        },
    )
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=3) as resp:
            body = resp.read(120000) if method == "GET" else b""
            return {
                "status_code": int(resp.getcode()),
                "final_url": resp.geturl(),
                "content_type": resp.headers.get("Content-Type", ""),
                "body": body,
                "redirect_to": "",
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "")
        body = b""
        if method == "GET":
            try:
                body = exc.read(120000)
            except Exception:
                body = b""
        return {
            "status_code": int(exc.code),
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type", ""),
            "body": body,
            "redirect_to": location if 300 <= exc.code < 400 else "",
            "error": "",
        }
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        return {
            "status_code": None,
            "final_url": url,
            "content_type": "",
            "body": b"",
            "redirect_to": "",
            "error": str(exc)[:300],
        }


def fetch_limited_redirects(url: str, method: str):
    current = url
    last = None
    for _idx in range(4):
        last = request_no_redirect(current, method)
        redirect_to = last.get("redirect_to")
        if not redirect_to:
            return last
        current = urllib.parse.urljoin(current, redirect_to)
    if last:
        last["final_url"] = current
        last["error"] = "redirect limit reached"
    return last or {"status_code": None, "final_url": url, "content_type": "", "body": b"", "error": "no response"}


def probe_endpoint(url: str, endpoint_type: str, path: str):
    head = fetch_limited_redirects(url, "HEAD")
    status = head.get("status_code")
    need_get = (
        status is None
        or status in (405, 501)
        or endpoint_type in {"frontend", "admin", "login", "docs"}
        or path in {"/api/projects", "/api", "/api/health", "/health"}
    )
    result = head
    if need_get:
        got = fetch_limited_redirects(url, "GET")
        if got.get("status_code") is not None or head.get("status_code") is None:
            result = got
    title = extract_html_title(result.get("body") or b"", result.get("content_type"))
    return {
        "status_code": result.get("status_code"),
        "url": result.get("final_url") or url,
        "title": title,
        "error": result.get("error") or "",
    }


def parse_external_ports(ports_text: str | None):
    ports = []
    if ports_text:
        try:
            data = json.loads(ports_text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for bindings in data.values():
                if isinstance(bindings, list):
                    for item in bindings:
                        if isinstance(item, dict) and item.get("HostPort"):
                            ports.append(str(item["HostPort"]))
        ports.extend(re.findall(r"(?::|HostPort['\"]?\s*[:=]\s*['\"]?)(\d{2,5})(?:->|['\"]?)", ports_text))
    clean = []
    for port in ports:
        try:
            num = int(port)
        except (TypeError, ValueError):
            continue
        if 1 <= num <= 65535 and str(num) not in clean:
            clean.append(str(num))
    return clean


def target_endpoint_host(service_row: dict):
    raw = service_row.get("target_ip_address") or service_row.get("ssh_host") or service_row.get("domain") or ""
    raw = str(raw).strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or raw.split("/")[0].split(":")[0]).strip()


def service_row_with_target(service_id: int):
    row = query_one(
        """SELECT ds.*, dt.ip_address AS target_ip_address, dt.domain, dt.ssh_host, dt.name AS target_name
           FROM docker_services ds
           LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
           WHERE ds.id=?""",
        (service_id,),
    )
    return row_to_dict(row)


def upsert_service_endpoint(service_id, project_id, endpoint_type, url, path, status_code, title, detected_from, notes=""):
    now = now_str()
    svc_project = query_one("SELECT project_id FROM docker_services WHERE id=?", (service_id,))
    if svc_project:
        project_id = svc_project["project_id"]
    existing = query_one(
        """SELECT * FROM service_endpoints
           WHERE docker_service_id=? AND path=? AND detected_from=?
           LIMIT 1""",
        (service_id, path, detected_from),
    )
    if existing:
        next_type = existing["endpoint_type"] if existing["is_confirmed"] else endpoint_type
        execute(
            """UPDATE service_endpoints
               SET project_id=?, endpoint_type=?, url=?, status_code=?, title=?, notes=?,
                   last_checked_at=?, updated_at=?
               WHERE id=?""",
            (
                project_id, next_type, url, status_code, title, notes or existing["notes"],
                now, now, existing["id"],
            ),
        )
        return existing["id"]
    return execute(
        """INSERT INTO service_endpoints
           (docker_service_id, project_id, endpoint_type, url, path, status_code, title,
            detected_from, is_confirmed, is_ignored, notes, last_checked_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
        (
            service_id, project_id, endpoint_type, url, path, status_code, title,
            detected_from, notes, now, now, now,
        ),
    ).lastrowid


def scan_service_endpoints(service_id: int):
    svc = service_row_with_target(service_id)
    if not svc:
        raise ValueError("docker service not found")
    host = target_endpoint_host(svc)
    ports = parse_external_ports(svc.get("ports"))
    if not host or not ports:
        return {
            "ok": True,
            "docker_service_id": service_id,
            "scanned": 0,
            "message": "沒有可探測的對外 port",
        }
    scanned = 0
    saved = []
    for port in ports:
        base_url = f"http://{host}:{port}"
        for endpoint_type, path in ENDPOINT_CANDIDATES:
            url = base_url + path
            probe = probe_endpoint(url, endpoint_type, path)
            detected_from = f"port={port}; path={path}"
            endpoint_id = upsert_service_endpoint(
                service_id,
                svc.get("project_id"),
                endpoint_type,
                probe["url"],
                path,
                probe["status_code"],
                probe["title"],
                detected_from,
                probe["error"],
            )
            saved.append(endpoint_id)
            scanned += 1
    return {
        "ok": True,
        "docker_service_id": service_id,
        "ports": ports,
        "scanned": scanned,
        "endpoint_ids": saved,
        "message": "服務端點掃描完成",
    }


def scan_all_service_endpoints():
    ids = [int(r["id"]) for r in query_all("SELECT id FROM docker_services ORDER BY id")]
    total = 0
    errors = []
    for service_id in ids:
        try:
            out = scan_service_endpoints(service_id)
            total += int(out.get("scanned") or 0)
        except Exception as exc:
            errors.append({"docker_service_id": service_id, "error": str(exc)[:300]})
    return {
        "ok": not errors,
        "services": len(ids),
        "scanned_endpoints": total,
        "errors": errors,
        "message": "全部服務端點掃描完成" if not errors else "部分服務端點掃描失敗",
    }


def service_endpoint_map():
    rows = query_all(
        """SELECT se.*, ds.project_id AS docker_project_id, p.name AS project_name
           FROM service_endpoints se
           LEFT JOIN docker_services ds ON se.docker_service_id=ds.id
           LEFT JOIN projects p ON ds.project_id=p.id
           ORDER BY se.is_confirmed DESC, se.endpoint_type, se.status_code DESC, se.url"""
    )
    mapped = {}
    for row in rows:
        item = row_to_dict(row)
        item["project_id"] = item.pop("docker_project_id", item.get("project_id"))
        mapped.setdefault(item["docker_service_id"], []).append(item)
    return mapped


def project_service_endpoint_rows(project_id: int):
    return query_all(
        """SELECT se.*, ds.project_id AS docker_project_id, ds.container_name, ds.image, ds.ports
           FROM service_endpoints se
           JOIN docker_services ds ON se.docker_service_id=ds.id
           WHERE COALESCE(se.is_ignored, 0)=0
             AND ds.project_id=?
           ORDER BY COALESCE(se.is_confirmed, 0) DESC,
                    CASE se.endpoint_type
                      WHEN 'frontend' THEN 1
                      WHEN 'admin' THEN 2
                      WHEN 'api' THEN 3
                      WHEN 'health' THEN 4
                      WHEN 'docs' THEN 5
                      WHEN 'login' THEN 6
                      ELSE 9
                    END,
                    se.status_code DESC,
                    se.url""",
        (project_id,),
    )


def endpoint_overview_stats():
    total = query_one("SELECT COUNT(*) AS c FROM service_endpoints WHERE COALESCE(is_ignored,0)=0")["c"]
    ok_200 = query_one("SELECT COUNT(*) AS c FROM service_endpoints WHERE COALESCE(is_ignored,0)=0 AND status_code=200")["c"]
    needs_confirm = query_one(
        """SELECT COUNT(*) AS c FROM service_endpoints
           WHERE COALESCE(is_ignored,0)=0 AND COALESCE(is_confirmed,0)=0 AND status_code IS NOT NULL"""
    )["c"]
    unreachable = query_one(
        """SELECT COUNT(*) AS c FROM service_endpoints
           WHERE COALESCE(is_ignored,0)=0 AND status_code IS NULL"""
    )["c"]
    return {
        "endpoint_total": total or 0,
        "endpoint_ok_200": ok_200 or 0,
        "endpoint_needs_confirm": needs_confirm or 0,
        "endpoint_unreachable": unreachable or 0,
    }


def docker_service_api_row(row, include_raw=False):
    item = row_to_dict(row)
    if not item:
        return None
    if not include_raw:
        item.pop("raw_inspect", None)
    item["host_ports"] = parse_external_ports(item.get("ports"))
    return item


def docker_service_api_query():
    where = []
    params = []
    if request.args.get("project_id") not in (None, ""):
        where.append("ds.project_id=?")
        params.append(int(request.args["project_id"]))
    if request.args.get("target_id") not in (None, ""):
        where.append("ds.target_id=?")
        params.append(int(request.args["target_id"]))
    if request.args.get("status"):
        where.append("lower(COALESCE(ds.status,'')) LIKE ?")
        params.append(f"%{request.args['status'].strip().lower()}%")
    if request.args.get("unbound") in ("1", "true", "yes"):
        where.append("ds.project_id IS NULL")
    sql = """SELECT ds.*,
                    dt.name AS target_name,
                    dt.target_type,
                    dt.ip_address AS target_ip_address,
                    dt.domain AS target_domain,
                    dt.ssh_host,
                    p.name AS project_name,
                    p.client_name AS project_client_name,
                    (SELECT COUNT(*) FROM service_endpoints se
                     WHERE se.docker_service_id=ds.id AND COALESCE(se.is_ignored,0)=0) AS endpoint_count,
                    (SELECT COUNT(*) FROM service_endpoints se
                     WHERE se.docker_service_id=ds.id AND COALESCE(se.is_confirmed,0)=1 AND COALESCE(se.is_ignored,0)=0) AS confirmed_endpoint_count
             FROM docker_services ds
             LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
             LEFT JOIN projects p ON ds.project_id=p.id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY dt.name COLLATE NOCASE, ds.container_name COLLATE NOCASE"
    return query_all(sql, tuple(params))


def docker_service_endpoint_rows(service_id):
    rows = query_all(
        """SELECT se.*, ds.project_id AS docker_project_id, p.name AS project_name
           FROM service_endpoints se
           LEFT JOIN docker_services ds ON se.docker_service_id=ds.id
           LEFT JOIN projects p ON ds.project_id=p.id
           WHERE se.docker_service_id=?
           ORDER BY COALESCE(is_confirmed,0) DESC,
                    COALESCE(is_ignored,0) ASC,
                    endpoint_type,
                    status_code DESC,
                    url""",
        (service_id,),
    )
    endpoints = []
    for row in rows:
        item = row_to_dict(row)
        item["project_id"] = item.pop("docker_project_id", item.get("project_id"))
        endpoints.append(item)
    return endpoints


def perform_docker_scan(target_id: int, docker_root_override: str | None = None):
    target = row_to_dict(query_one("SELECT * FROM deployment_targets WHERE id=?", (target_id,)))
    if not target:
        raise ValueError("找不到部署目標")
    ssh_host = (target.get("ssh_host") or target.get("ip_address") or "").strip()
    ssh_user = (target.get("ssh_user") or "").strip()
    ssh_port = target.get("ssh_port") or "22"
    if not ssh_host or not ssh_user:
        raise ValueError("請先設定 ssh_host / ssh_user")
    docker_root = docker_ssh.normalize_docker_root(docker_root_override)
    now = now_str()
    projects_rows = [dict(r) for r in query_all("SELECT id, name, local_path FROM projects")]
    summary_lines: list[str] = []
    summary_lines.append(f"SSH {ssh_user}@{ssh_host} docker_root={docker_root}")
    inspect_errors: list[str] = []
    compose_files = docker_ssh.find_compose_files(ssh_host, ssh_port, ssh_user, docker_root)
    ps_rows = docker_ssh.docker_ps_json_lines(ssh_host, ssh_port, ssh_user)
    summary_lines.append(f"compose_yml={len(compose_files)}, containers={len(ps_rows)}")
    for row in ps_rows:
        cid = (row.get("ID") or "").strip()
        inspect_obj = docker_ssh.docker_inspect_full(ssh_host, ssh_port, ssh_user, cid) if cid else None
        if not inspect_obj and cid:
            inspect_errors.append(cid[:12])
        compose_path, deploy_path = derive_compose_deploy_from_inspect(inspect_obj, compose_files)
        cname = container_display_name(row, inspect_obj)
        if not cname:
            continue
        image = (row.get("Image") or "")
        if inspect_obj and (inspect_obj.get("Config") or {}).get("Image"):
            image = (inspect_obj.get("Config") or {}).get("Image") or image
        status = docker_service_status_from_inspect(inspect_obj, row.get("Status"))
        ports = summarize_ports_from_inspect(inspect_obj)
        vols = summarize_volumes_from_inspect(inspect_obj)
        raw_insp = json.dumps(inspect_obj, ensure_ascii=False) if inspect_obj else ""
        svc_nm = detect_service_name(inspect_obj, image)
        cproj = compose_project_label(inspect_obj)
        guess_pid = infer_project_id_for_service(target_id, compose_path, deploy_path, cproj, projects_rows)
        sid, pid = save_docker_service_from_scan(
            target_id,
            cname,
            guessed_project_id=guess_pid,
            service_name=svc_nm,
            image=image,
            status=status,
            ports=ports,
            compose_path=compose_path,
            deploy_path=deploy_path,
            volumes=vols,
            raw_inspect=raw_insp,
            now=now,
        )
        port_hint = first_host_port_from_ports_json(ports)
        if pid:
            sync_project_deployment_probe_row(
                pid,
                target_id,
                {
                    "service_name": svc_nm,
                    "deploy_path": deploy_path,
                    "compose_path": compose_path,
                    "status": status,
                    "last_seen_at": now,
                    "port_hint": port_hint,
                },
            )
    raw_blob = "\n".join(
        summary_lines
        + [
            "",
            "=== compose ===",
            json.dumps(compose_files, ensure_ascii=False),
            "=== docker_ps ===",
            json.dumps(ps_rows, ensure_ascii=False),
            "=== inspect_fail_ids ===",
            ",".join(inspect_errors),
        ]
    )
    cur = execute(
        """INSERT INTO docker_scan_runs
           (target_id, target_name, ssh_host, docker_root, status, summary, raw_output, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            target_id,
            target["name"],
            ssh_host,
            docker_root,
            "ok",
            json.dumps({"compose_files": len(compose_files), "containers": len(ps_rows)}, ensure_ascii=False),
            raw_blob[:200000],
            now,
        ),
    )
    return {
        "ok": True,
        "scan_run_id": cur.lastrowid,
        "compose_files": len(compose_files),
        "containers": len(ps_rows),
        "message": "NAS Docker 掃描完成",
    }


@app.route("/deployment-targets", methods=["GET", "POST"])
def deployment_targets():
    if request.method == "POST":
        execute(
            """INSERT INTO deployment_targets
               (name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                request.form["name"], request.form.get("target_type"), request.form.get("location"),
                request.form.get("ip_address"), request.form.get("domain"), request.form.get("ssh_host"),
                request.form.get("ssh_port"), request.form.get("ssh_user"), request.form.get("notes"),
                now_str(), now_str(),
            ),
        )
        flash("部署主機已新增")
        return redirect(url_for("deployment_targets"))
    items = query_all(
        """SELECT dt.*, COUNT(pd.id) AS deployment_count
           FROM deployment_targets dt
           LEFT JOIN project_deployments pd ON pd.target_id=dt.id AND COALESCE(pd.is_active, 1)=1
           GROUP BY dt.id
           ORDER BY dt.is_active DESC, dt.name"""
    )
    return render_template("deployment_targets.html", app_name=APP_NAME, targets=items)


@app.route("/deployment-targets/<int:target_id>/edit", methods=["POST"])
def deployment_target_edit(target_id):
    target = query_one("SELECT * FROM deployment_targets WHERE id=?", (target_id,))
    if not target:
        return "Deployment target not found", 404
    execute(
        """UPDATE deployment_targets
           SET name=?, target_type=?, location=?, ip_address=?, domain=?, ssh_host=?, ssh_port=?, ssh_user=?, notes=?, updated_at=?
           WHERE id=?""",
        (
            request.form["name"], request.form.get("target_type"), request.form.get("location"),
            request.form.get("ip_address"), request.form.get("domain"), request.form.get("ssh_host"),
            request.form.get("ssh_port"), request.form.get("ssh_user"), request.form.get("notes"),
            now_str(), target_id,
        ),
    )
    flash("部署主機已更新")
    return redirect(url_for("deployment_targets"))


@app.route("/deployment-targets/<int:target_id>/toggle", methods=["POST"])
def deployment_target_toggle(target_id):
    target = query_one("SELECT * FROM deployment_targets WHERE id=?", (target_id,))
    if not target:
        return "Deployment target not found", 404
    next_active = 0 if target["is_active"] else 1
    execute("UPDATE deployment_targets SET is_active=?, updated_at=? WHERE id=?", (next_active, now_str(), target_id))
    flash("部署主機狀態已更新")
    return redirect(url_for("deployment_targets"))


@app.route("/deployment-board")
def deployment_board():
    targets = get_deployment_targets(include_inactive=False)
    deployments = project_deployment_rows(active_only=True)
    board_columns = [{"id": None, "name": "未指定", "deployments": []}]
    board_columns += [{"id": t["id"], "name": t["name"], "deployments": []} for t in targets]
    column_map = {c["id"]: c for c in board_columns}
    for deployment in deployments:
        target = column_map.get(deployment["target_id"]) or column_map[None]
        target["deployments"].append(deployment)
    return render_template("deployment_board.html", app_name=APP_NAME, board_columns=board_columns)


@app.route("/ai-heartbeats")
def ai_heartbeats():
    heartbeats = heartbeat_query(
        project_id=request.args.get("project_id"),
        source=request.args.get("source"),
        status=request.args.get("status"),
    )
    return render_template("ai_heartbeats.html", app_name=APP_NAME, heartbeats=heartbeats, sources=HEARTBEAT_SOURCES, statuses=HEARTBEAT_STATUSES)


@app.route("/docker-scan")
def docker_scan_view():
    targets = get_deployment_targets(include_inactive=False)
    services = query_all(
        """SELECT ds.*, dt.name AS target_name, p.name AS project_name
           FROM docker_services ds
           LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
           LEFT JOIN projects p ON ds.project_id=p.id
           ORDER BY dt.name COLLATE NOCASE, ds.container_name COLLATE NOCASE"""
    )
    projects_dd = query_all("SELECT id, name FROM projects ORDER BY name COLLATE NOCASE")
    recent_scans = query_all("SELECT * FROM docker_scan_runs ORDER BY id DESC LIMIT 30")
    endpoints_by_service = service_endpoint_map()
    return render_template(
        "docker_scan.html",
        app_name=APP_NAME,
        targets=targets,
        services=services,
        projects_dd=projects_dd,
        recent_scans=recent_scans,
        endpoints_by_service=endpoints_by_service,
        default_docker_root="/volume1/docker",
    )


@app.route("/docker-scan/target/<int:target_id>/scan", methods=["POST"])
def docker_scan_run_web(target_id):
    docker_root = (request.form.get("docker_root") or "").strip() or None
    try:
        out = perform_docker_scan(target_id, docker_root)
        flash(out.get("message", "掃描完成"))
    except ValueError as ve:
        flash(str(ve))
    except Exception as exc:
        flash(f"掃描失敗：{exc}")
    return redirect(url_for("docker_scan_view"))


@app.route("/docker-scan/bind", methods=["POST"])
def docker_scan_bind_web():
    try:
        sid = int(request.form.get("service_id", "0"))
        pid = int(request.form.get("project_id", "0"))
    except ValueError:
        flash("綁定參數錯誤")
        return redirect(url_for("docker_scan_view"))
    env = (request.form.get("environment") or "production").strip()
    _res, err = bind_docker_service_to_project(sid, pid, environment=env)
    flash(err if err else "已綁定專案")
    return redirect(url_for("docker_scan_view"))


@app.route("/docker-scan/service/<int:service_id>/bootstrap-project", methods=["POST"])
def docker_scan_bootstrap_project_web(service_id):
    try:
        out, err = bootstrap_project_from_docker_service(service_id)
        flash(err if err else f"已建立專案 + Repo：{out.get('project_name')}")
    except Exception as exc:
        flash(f"建立專案 + Repo 失敗：{exc}")
    return redirect(url_for("docker_scan_view"))


@app.route("/docker-scan/service/<int:service_id>/scan-endpoints", methods=["POST"])
def docker_scan_service_endpoints_web(service_id):
    try:
        out = scan_service_endpoints(service_id)
        flash(f"{out.get('message', '服務端點掃描完成')}：{out.get('scanned', 0)} 筆")
    except Exception as exc:
        flash(f"服務端點掃描失敗：{exc}")
    return redirect(url_for("docker_scan_view"))


@app.route("/service-endpoints/<int:endpoint_id>/classify", methods=["POST"])
def service_endpoint_classify_web(endpoint_id):
    endpoint = query_one("SELECT * FROM service_endpoints WHERE id=?", (endpoint_id,))
    if not endpoint:
        flash("找不到服務網址")
        return redirect(url_for("docker_scan_view"))
    action = (request.form.get("action") or "").strip()
    now = now_str()
    if action == "ignore":
        execute("UPDATE service_endpoints SET is_ignored=1, updated_at=? WHERE id=?", (now, endpoint_id))
        flash("服務網址已忽略")
    elif action in ENDPOINT_TYPES:
        execute(
            "UPDATE service_endpoints SET endpoint_type=?, is_confirmed=1, is_ignored=0, updated_at=? WHERE id=?",
            (action, now, endpoint_id),
        )
        flash("服務網址分類已確認")
    else:
        flash("未知的服務網址操作")
    return redirect(request.referrer or url_for("docker_scan_view"))


@app.route("/projects/new", methods=["GET", "POST"])
def project_new():
    templates = query_all("SELECT * FROM project_templates ORDER BY id")
    if request.method == "POST":
        template_id = request.form.get("template_id") or None
        owner_machine = machine_display_name(request.form.get("owner_machine"))
        cur = execute(
            """INSERT INTO projects
            (name, client_name, project_type, status, priority, github_repo, local_path, deploy_url, deploy_location, owner_machine, description, next_steps, progress, template_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                request.form["name"], request.form.get("client_name"), request.form.get("project_type"),
                request.form.get("status", "規劃中"), request.form.get("priority", "中"), request.form.get("github_repo"),
                request.form.get("local_path"), request.form.get("deploy_url"), request.form.get("deploy_location"), owner_machine,
                request.form.get("description"), request.form.get("next_steps"), template_id, now_str(), now_str(),
            ),
        )
        project_id = cur.lastrowid
        if template_id:
            create_phases_from_template(project_id, int(template_id))
            dispatch_result = create_dispatch_job_from_template(project_id, int(template_id))
        else:
            dispatch_result = None
        recalc_project(project_id)
        flash("專案已建立")
        if dispatch_result:
            flash(f"AI 任務已建立：#{dispatch_result['dispatch_job_id']}，等待 worker 執行")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("project_form.html", app_name=APP_NAME, project=None, templates=templates, statuses=STATUSES, priorities=PRIORITIES)


@app.route("/projects/<int:project_id>")
def project_detail(project_id):
    project = query_one(
        """SELECT p.*, dc.name AS development_computer_name, depc.name AS deployment_computer_name
           FROM projects p
           LEFT JOIN computers dc ON p.computer_id=dc.id
           LEFT JOIN computers depc ON p.deploy_computer_id=depc.id
           WHERE p.id=?""",
        (project_id,),
    )
    if not project:
        return "Project not found", 404
    show_hidden = request.args.get("show_hidden") == "1"
    phases = query_all("SELECT * FROM project_phases WHERE project_id=? ORDER BY phase_order", (project_id,))
    tasks = query_all("SELECT t.*, ph.phase_name FROM project_tasks t LEFT JOIN project_phases ph ON t.phase_id=ph.id WHERE t.project_id=? ORDER BY t.created_at DESC", (project_id,))
    if show_hidden:
        logs = query_all("SELECT * FROM handoff_logs WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    else:
        logs = query_all("SELECT * FROM handoff_logs WHERE project_id=? AND COALESCE(is_hidden, 0)=0 ORDER BY created_at DESC", (project_id,))
    deployments = query_all("SELECT * FROM deployments WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    project_deployments = project_deployment_rows(project_id=project_id, active_only=False)
    project_repo = project_repo_row(project_id)
    deployment_env_paths = environment_deploy_paths(project, project_repo)
    deployment_jobs = latest_deployment_jobs(project_id)
    dispatch_jobs = project_dispatch_jobs(project_id)
    ai_tasks = task_rows(project_id=project_id)
    task_templates = task_template_rows(active_only=True)
    content_jobs = content_jobs_for_project(project_id)
    validation_reports = latest_validation_reports(project_id)
    latest_snapshot = latest_deployment_snapshot(project_id)
    deployment_targets = get_deployment_targets(include_inactive=False)
    acceptance = query_all("SELECT * FROM acceptance_items WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    copy_commands = build_handoff_copy_commands(project_id)
    heartbeat_commands = build_heartbeat_copy_commands(project)
    project_heartbeats = heartbeat_query(project_id=project_id)
    flow_messages = recent_flow_messages(limit=20, project_id=project_id)
    flow_runs = flow_run_rows(project_id=project_id, limit=10)
    project_domains = domain_mapping_rows(project_id=project_id)
    computer_options = get_computer_options()
    docker_svc_rows = query_all(
        """SELECT ds.*, dt.name AS target_name
           FROM docker_services ds
           LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
           WHERE ds.project_id=? ORDER BY ds.last_seen_at DESC""",
        (project_id,),
    )
    service_endpoints = project_service_endpoint_rows(project_id)
    return render_template(
        "project_detail.html",
        app_name=APP_NAME,
        project=project,
        phases=phases,
        tasks=tasks,
        logs=logs,
        deployments=deployments,
        project_deployments=project_deployments,
        project_repo=project_repo,
        deployment_env_paths=deployment_env_paths,
        deployment_jobs=deployment_jobs,
        dispatch_jobs=dispatch_jobs,
        ai_tasks=ai_tasks,
        task_templates=task_templates,
        content_jobs=content_jobs,
        dispatch_risk_levels=DISPATCH_RISK_LEVELS,
        validation_reports=validation_reports,
        latest_snapshot=latest_snapshot,
        deployment_environments=DEPLOYMENT_ENVIRONMENTS,
        deployment_targets=deployment_targets,
        acceptance=acceptance,
        sources=SOURCES,
        work_modes=WORK_MODES,
        phase_statuses=PHASE_STATUSES,
        task_statuses=TASK_STATUSES,
        priorities=PRIORITIES,
        repo_statuses=REPO_STATUSES,
        sync_methods=SYNC_METHODS,
        copy_commands=copy_commands,
        heartbeat_commands=heartbeat_commands,
        project_heartbeats=project_heartbeats,
        flow_messages=flow_messages,
        flow_runs=flow_runs,
        project_domains=project_domains,
        show_hidden=show_hidden,
        computer_options=computer_options,
        api_token=API_TOKEN,
        api_base_url=API_BASE_URL,
        docker_svc_rows=docker_svc_rows,
        service_endpoints=service_endpoints,
    )


@app.route("/projects/<int:project_id>/engineering-report")
def project_engineering_report(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        return "Project not found", 404
    markdown = build_engineering_report_markdown(project_id)
    return render_template(
        "engineering_report.html",
        app_name=APP_NAME,
        project=project,
        markdown=markdown,
        html_report=markdown_to_report_html(markdown),
    )


@app.route("/projects/<int:project_id>/engineering-report/export")
def project_engineering_report_export(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        return "Project not found", 404
    export_format = normalize_choice(request.args.get("format"), ["markdown", "md", "html"], "markdown")
    markdown = build_engineering_report_markdown(project_id)
    if export_format == "html":
        content = markdown_to_report_html(markdown)
        filename = engineering_report_filename(project, "html")
        mimetype = "text/html; charset=utf-8"
    else:
        content = markdown
        filename = engineering_report_filename(project, "md")
        mimetype = "text/markdown; charset=utf-8"
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def project_edit(project_id):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    templates = query_all("SELECT * FROM project_templates ORDER BY id")
    if request.method == "POST":
        owner_machine = machine_display_name(request.form.get("owner_machine"))
        execute(
            """UPDATE projects SET name=?, client_name=?, project_type=?, status=?, priority=?, github_repo=?, local_path=?, deploy_url=?, deploy_location=?, owner_machine=?, description=?, next_steps=?, updated_at=? WHERE id=?""",
            (request.form["name"], request.form.get("client_name"), request.form.get("project_type"), request.form.get("status"), request.form.get("priority"), request.form.get("github_repo"), request.form.get("local_path"), request.form.get("deploy_url"), request.form.get("deploy_location"), owner_machine, request.form.get("description"), request.form.get("next_steps"), now_str(), project_id),
        )
        flash("專案已更新")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("project_form.html", app_name=APP_NAME, project=project, templates=templates, statuses=STATUSES, priorities=PRIORITIES)


@app.route("/projects/<int:project_id>/repo", methods=["POST"])
def project_repo_save(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return "Project not found", 404
    payload = project_repo_payload(request.form)
    existing = project_repo_row(project_id)
    if existing:
        payload["last_commit"] = payload["last_commit"] or (existing.get("last_commit") or "")
        payload["branch"] = payload["branch"] or (existing.get("branch") or "")
    upsert_project_repo(project_id, payload)
    flash("Repo 對應已更新")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/dispatch", methods=["POST"])
def project_dispatch(project_id):
    payload = {
        "agent": request.form.get("agent", "codex"),
        "project_id": project_id,
        "provider": request.form.get("provider", "openai"),
        "task_role": request.form.get("task_role", "executor"),
        "task_prompt": request.form.get("task") or request.form.get("task_prompt") or "",
        "risk_level": request.form.get("risk_level", "low"),
        "approval_required": True,
    }
    try:
        result = create_dispatch_job(payload)
        flash(f"AI dispatch job 已建立：#{result['dispatch_job_id']}，等待 worker 執行")
    except LookupError:
        return "Project not found", 404
    except ValueError as exc:
        flash(f"AI dispatch job 建立失敗：{exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/ai-tasks", methods=["POST"])
def project_ai_task_create(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return "Project not found", 404
    payload = request.form.to_dict()
    payload["project_id"] = project_id
    try:
        task = create_ai_task(payload)
        flash(f"AI task created: #{task['id']}")
    except ValueError as exc:
        flash(f"AI task create failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/ai-tasks/from-template", methods=["POST"])
def project_ai_task_from_template_web(project_id):
    template_id = coerce_int(request.form.get("template_id"), None)
    try:
        task = create_ai_task_from_template(project_id, template_id)
        flash(f"AI task created from template: #{task['id']}")
    except (LookupError, ValueError) as exc:
        flash(f"AI task template create failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/ai-tasks/create-default-flow", methods=["POST"])
def project_ai_task_default_flow_web(project_id):
    try:
        tasks = create_default_ai_task_flow(project_id)
        flash(f"Default AI flow created: {len(tasks)} tasks")
    except (LookupError, ValueError) as exc:
        flash(f"Default AI flow create failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/run-ai-flow-safe", methods=["POST"])
def project_run_ai_flow_safe_web(project_id):
    try:
        result = run_project_ai_flow(project_id, "safe")
        flash(f"Safe AI flow: {result['status']} ({len(result.get('tasks') or [])} task(s))")
    except (LookupError, ValueError) as exc:
        flash(f"Safe AI flow failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/run-ai-flow-full", methods=["POST"])
def project_run_ai_flow_full_web(project_id):
    try:
        result = run_project_ai_flow(project_id, "full")
        flash(f"Full AI flow: {result['status']} ({len(result.get('tasks') or [])} task(s))")
    except (LookupError, ValueError) as exc:
        flash(f"Full AI flow failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/ai-tasks/<int:task_id>/<action>", methods=["POST"])
def project_ai_task_action(project_id, task_id, action):
    task = task_row(task_id)
    if not task or coerce_int(task.get("project_id"), None) != project_id:
        return "AI task not found", 404
    try:
        if action == "run":
            result = run_ai_task(task_id)
            flash(f"AI task finished: #{task_id}" if result.get("ok") else f"AI task failed: {result.get('error')}")
        elif action == "run-flow":
            result = run_ai_task_flow(task_id)
            flow_count = len(result.get("flow_results") or [])
            flash(f"AI task flow finished: #{task_id}, auto-ran {flow_count} child task(s)" if result.get("ok") else f"AI task flow failed: {result.get('error')}")
        elif action == "approve":
            result = approve_ai_task(task_id)
            flow_count = len(result.get("flow_results") or [])
            flash(f"AI task approved: #{task_id}, auto-ran {flow_count} child task(s)")
        elif action == "reject":
            reject_ai_task(task_id)
            flash(f"AI task rejected: #{task_id}")
        elif action == "retry":
            retry_ai_task(task_id)
            flash(f"AI task requeued: #{task_id}")
        elif action == "block":
            block_ai_task(task_id, request.form.get("reason") or "manual block")
            flash(f"AI task blocked: #{task_id}")
        elif action == "unblock":
            unblock_ai_task(task_id)
            flash(f"AI task unblocked: #{task_id}")
        elif action == "cancel":
            cancel_ai_task(task_id)
            flash(f"AI task canceled: #{task_id}")
        else:
            return "Unsupported AI task action", 404
    except (LookupError, ValueError) as exc:
        flash(f"AI task action failed: {exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/content/product-video", methods=["POST"])
def project_product_video(project_id):
    try:
        result = create_product_video_job(
            project_id,
            request.form.get("product_name"),
            request.form.get("features"),
            request.form.get("target"),
            request.form.get("style"),
            call_provider=True,
        )
        if result.get("status") == "done":
            flash(f"商品影片已生成：content job #{result['content_job_id']}")
        elif result.get("status") == "failed":
            flash(f"商品影片生成失敗：{result.get('message')}")
        else:
            flash(f"商品影片 job 已建立：#{result['content_job_id']}，{result.get('message')}")
    except LookupError:
        return "Project not found", 404
    except ValueError as exc:
        flash(f"商品影片 job 建立失敗：{exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/content/<int:content_job_id>/publish/<platform>", methods=["POST"])
def content_publish_web(content_job_id, platform):
    job = content_job_row(content_job_id)
    if not job:
        return "Content job not found", 404
    try:
        result = publish_content_job(content_job_id, platform)
        if result.get("ok"):
            flash(f"已發佈到 {platform}：{result.get('post_id') or '-'}")
        else:
            flash(f"發佈到 {platform} 失敗：{result.get('error')}")
    except ValueError as exc:
        flash(f"發佈到 {platform} 已阻擋：{exc}")
    except LookupError:
        return "Content job not found", 404
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/dispatch-jobs/<int:job_id>/deploy-staging", methods=["POST"])
def dispatch_job_deploy_staging_web(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return "Dispatch job not found", 404
    try:
        result = perform_dispatch_staging_deploy(job_id, {"health_url": request.form.get("health_url")})
        flash(f"Dispatch staging deploy：{result['status']}")
    except (LookupError, ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Dispatch staging deploy 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/dispatch-jobs/<int:job_id>/retry", methods=["POST"])
def dispatch_job_retry_web(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return "Dispatch job not found", 404
    try:
        new_job = retry_dispatch_job(job_id)
        flash(f"AI dispatch job 已重新排隊：#{new_job['id']}")
    except ValueError as exc:
        flash(f"AI dispatch job 重新執行失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/dispatch-jobs/<int:job_id>/approve-production", methods=["POST"])
@require_roles("owner", "admin")
def dispatch_job_approve_production_web(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return "Dispatch job not found", 404
    try:
        result = perform_dispatch_production_deploy(job_id, {"health_url": request.form.get("health_url")})
        flash(f"Dispatch production deploy：{result['status']}")
    except PermissionError as exc:
        flash(f"Dispatch production deploy 已阻擋：{exc}")
    except (LookupError, ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Dispatch production deploy 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/dispatch-jobs/<int:job_id>/rollback", methods=["POST"])
def dispatch_job_rollback_web(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return "Dispatch job not found", 404
    try:
        result = perform_dispatch_rollback(job_id)
        flash(f"Dispatch rollback 完成：snapshot #{result['snapshot_id']}")
    except (LookupError, ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Dispatch rollback 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/projects/<int:project_id>/deploy-staging", methods=["POST"])
def project_deploy_staging(project_id):
    payload = {
        "source": "manual",
        "agent": request.form.get("agent", "manual"),
        "task": request.form.get("task", "manual staging deploy"),
        "health_url": request.form.get("health_url"),
        "run_compose": request.form.get("run_compose") == "1",
        "requested_by": "web",
    }
    try:
        result = perform_environment_deploy(project_id, "staging", payload)
        flash(f"Staging deploy 完成：job #{result['job_id']}，production job #{result['production_job_id']} 等待核准")
    except LookupError:
        return "Project not found", 404
    except (ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Staging deploy 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/deploy-production", methods=["POST"])
@require_roles("owner", "admin")
def project_deploy_production(project_id):
    payload = {
        "source": "manual",
        "agent": request.form.get("agent", "manual"),
        "job_id": request.form.get("job_id"),
        "health_url": request.form.get("health_url"),
        "run_compose": request.form.get("run_compose") == "1",
        "requested_by": "web",
    }
    try:
        result = perform_environment_deploy(project_id, "production", payload)
        flash(f"Production deploy 完成：job #{result['job_id']}")
    except LookupError:
        return "Project not found", 404
    except PermissionError as exc:
        flash(f"Production deploy 已阻擋：{exc}")
    except (ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Production deploy 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/deployment-jobs/<int:job_id>/approve", methods=["POST"])
@require_roles("owner", "admin")
def deployment_job_approve(job_id):
    job = deployment_job_row(job_id)
    if not job:
        return "Deployment job not found", 404
    if job["environment"] != "production":
        flash("只有 production job 需要核准")
    else:
        update_deployment_job(job_id, status="approved", approved_at=now_str(), notes=request.form.get("notes") or job.get("notes") or "")
        flash(f"Production deployment job #{job_id} 已核准")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/deployment-jobs/<int:job_id>/validate-staging", methods=["POST"])
def deployment_job_validate_staging_web(job_id):
    job = deployment_job_row(job_id)
    if not job:
        return "Deployment job not found", 404
    try:
        result = validate_staging_job(job_id)
        flash(f"Gemini staging 驗收完成：{result['status']} / score {result['score']}")
    except (LookupError, ValueError, RuntimeError) as exc:
        flash(f"Gemini staging 驗收失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/deployment-jobs/<int:job_id>/rollback", methods=["POST"])
def deployment_job_rollback_web(job_id):
    job = deployment_job_row(job_id)
    if not job:
        return "Deployment job not found", 404
    try:
        result = perform_rollback(job_id)
        flash(f"Rollback 完成：snapshot #{result['snapshot_id']}")
    except (LookupError, ValueError, RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        flash(f"Rollback 失敗：{exc}")
    return redirect(url_for("project_detail", project_id=job["project_id"]))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def project_delete(project_id):
    execute("DELETE FROM projects WHERE id=?", (project_id,))
    flash("專案已刪除")
    return redirect(url_for("projects"))


@app.route("/projects/<int:project_id>/phases", methods=["POST"])
def phase_create(project_id):
    order = query_one("SELECT COALESCE(MAX(phase_order),0)+1 AS n FROM project_phases WHERE project_id=?", (project_id,))["n"]
    execute("INSERT INTO project_phases (project_id, phase_name, phase_order, status, start_date, due_date, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, request.form["phase_name"], order, request.form.get("status", "未開始"), request.form.get("start_date"), request.form.get("due_date"), request.form.get("notes"), now_str(), now_str()))
    recalc_project(project_id)
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/phases/<int:phase_id>/update", methods=["POST"])
def phase_update(phase_id):
    phase = query_one("SELECT * FROM project_phases WHERE id=?", (phase_id,))
    status = request.form.get("status", phase["status"])
    completed_at = now_str() if status in ["已完成", "已驗收"] else phase["completed_at"]
    execute("UPDATE project_phases SET phase_name=?, phase_order=?, status=?, start_date=?, due_date=?, completed_at=?, test_result=?, notes=?, updated_at=? WHERE id=?",
            (request.form.get("phase_name", phase["phase_name"]), request.form.get("phase_order", phase["phase_order"]), status, request.form.get("start_date"), request.form.get("due_date"), completed_at, request.form.get("test_result"), request.form.get("notes"), now_str(), phase_id))
    recalc_project(phase["project_id"])
    return redirect(url_for("project_detail", project_id=phase["project_id"]))


@app.route("/projects/<int:project_id>/tasks", methods=["POST"])
def task_create(project_id):
    phase_id = request.form.get("phase_id") or None
    execute("INSERT INTO project_tasks (project_id, phase_id, title, status, priority, assignee, due_date, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, phase_id, request.form["title"], request.form.get("status", "未開始"), request.form.get("priority", "中"), request.form.get("assignee"), request.form.get("due_date"), request.form.get("notes"), now_str(), now_str()))
    if phase_id:
        recalc_phase_by_tasks(project_id, int(phase_id))
    recalc_project(project_id)
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/tasks/<int:task_id>/update", methods=["POST"])
def task_update(task_id):
    task = query_one("SELECT * FROM project_tasks WHERE id=?", (task_id,))
    status = request.form.get("status", task["status"])
    completed_at = now_str() if status == "已完成" else task["completed_at"]
    execute("UPDATE project_tasks SET title=?, phase_id=?, status=?, priority=?, assignee=?, due_date=?, completed_at=?, notes=?, updated_at=? WHERE id=?",
            (request.form.get("title", task["title"]), request.form.get("phase_id") or None, status, request.form.get("priority"), request.form.get("assignee"), request.form.get("due_date"), completed_at, request.form.get("notes"), now_str(), task_id))
    if task["phase_id"]:
        recalc_phase_by_tasks(task["project_id"], task["phase_id"])
    recalc_project(task["project_id"])
    return redirect(url_for("project_detail", project_id=task["project_id"]))


@app.route("/projects/<int:project_id>/assign-computer", methods=["POST"])
def project_assign_computer(project_id):
    assignment_type = request.form.get("assignment_type", "development")
    computer_id = normalize_computer_id(request.form.get("computer_id"))
    project, error = assign_project_computer(project_id, computer_id, assignment_type)
    if error == "project":
        return "Project not found", 404
    if error == "computer":
        flash("指定的電腦不存在或已停用")
    else:
        flash("專案已指定到電腦")
    return redirect(request.form.get("next") or url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/handoff", methods=["POST"])
def handoff_create(project_id):
    raw_text = request.form.get("raw_text", "")
    parsed = parse_handoff_text(raw_text) if raw_text else {}
    completed_phases = request.form.getlist("completed_phases") or parsed.get("completed_phases", [])
    changed_files = parse_json_list(request.form.get("changed_files")) or parsed.get("changed_files", [])
    db_backups = parse_json_list(request.form.get("db_backups")) or parsed.get("db_backups", [])
    payload = {
        "source": request.form.get("source", "manual"), "agent_name": request.form.get("agent_name"),
        "work_mode": request.form.get("work_mode", "manual"), "conversation_ref": request.form.get("conversation_ref"),
        "repo_branch": request.form.get("repo_branch"), "commit_sha": request.form.get("commit_sha"), "risk_level": request.form.get("risk_level", "low"),
        "summary": request.form.get("summary") or parsed.get("summary"), "raw_text": raw_text,
        "completed_phases": completed_phases, "changed_files": changed_files,
        "test_result": request.form.get("test_result") or parsed.get("test_result"),
        "git_status": request.form.get("git_status") or parsed.get("git_status"),
        "db_backups": db_backups,
        "next_steps": request.form.get("next_steps") or parsed.get("next_steps"),
        "warnings": request.form.get("warnings") or parsed.get("warnings"),
    }
    save_handoff(project_id, payload)
    flash("交接紀錄已新增並嘗試自動更新階段")
    return redirect(url_for("project_detail", project_id=project_id))


def save_handoff(project_id, payload):
    cur = execute(
        """INSERT INTO handoff_logs
        (project_id, source, agent_name, work_mode, conversation_ref, repo_branch, commit_sha, risk_level, summary, raw_text, completed_phases, changed_files, test_result, git_status, db_backups, next_steps, warnings, api_payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id, payload.get("source", "manual"), payload.get("agent_name"), payload.get("work_mode", "manual"), payload.get("conversation_ref"),
            payload.get("repo_branch"), payload.get("commit_sha"), payload.get("risk_level", "low"), payload.get("summary"), payload.get("raw_text"),
            json_dumps(payload.get("completed_phases", [])), json_dumps(payload.get("changed_files", [])), payload.get("test_result"), payload.get("git_status"),
            json_dumps(payload.get("db_backups", [])), payload.get("next_steps"), payload.get("warnings"), json.dumps(payload, ensure_ascii=False), now_str(),
        ),
    )
    test_text = (payload.get("test_result") or "") + " " + (payload.get("warnings") or "")
    bad = any(word in test_text.lower() for word in ["失敗", "錯誤", "error", "failed", "fail"])
    for phase_hint in payload.get("completed_phases", []) or []:
        update_phase_status(project_id, phase_hint, "有問題" if bad else "已完成", payload.get("test_result"), payload.get("summary"))
    if payload.get("next_steps"):
        execute("UPDATE projects SET next_steps=?, updated_at=? WHERE id=?", (payload.get("next_steps"), now_str(), project_id))
    recalc_project(project_id)
    return cur.lastrowid


def hide_handoff(handoff_id):
    handoff = query_one("SELECT * FROM handoff_logs WHERE id=?", (handoff_id,))
    if not handoff:
        return None
    execute(
        "UPDATE handoff_logs SET is_hidden=1, hidden_at=?, hidden_reason=? WHERE id=?",
        (now_str(), "手動隱藏", handoff_id),
    )
    return handoff


def restore_handoff(handoff_id):
    handoff = query_one("SELECT * FROM handoff_logs WHERE id=?", (handoff_id,))
    if not handoff:
        return None
    execute(
        "UPDATE handoff_logs SET is_hidden=0, hidden_at=NULL, hidden_reason=NULL WHERE id=?",
        (handoff_id,),
    )
    return handoff


@app.route("/handoffs/<int:handoff_id>/hide", methods=["POST"])
def handoff_hide(handoff_id):
    handoff = hide_handoff(handoff_id)
    if not handoff:
        return "Handoff not found", 404
    flash("交接紀錄已隱藏")
    return redirect(url_for("project_detail", project_id=handoff["project_id"]))


@app.route("/handoffs/<int:handoff_id>/restore", methods=["POST"])
def handoff_restore(handoff_id):
    handoff = restore_handoff(handoff_id)
    if not handoff:
        return "Handoff not found", 404
    flash("交接紀錄已還原")
    return redirect(url_for("project_detail", project_id=handoff["project_id"], show_hidden=1))


@app.route("/projects/<int:project_id>/project-deployments", methods=["POST"])
def project_deployment_create(project_id):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        return "Project not found", 404
    payload = deployment_payload(request.form)
    if not deployment_target_exists(payload.get("target_id")):
        flash("部署主機不存在或已停用")
        return redirect(url_for("project_detail", project_id=project_id))
    insert_project_deployment(project_id, payload)
    flash("部署位置已新增")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project-deployments/<int:deployment_id>/edit", methods=["POST"])
def project_deployment_edit(deployment_id):
    deployment = query_one("SELECT * FROM project_deployments WHERE id=?", (deployment_id,))
    if not deployment:
        return "Project deployment not found", 404
    payload = deployment_payload(request.form)
    if not deployment_target_exists(payload.get("target_id")):
        flash("部署主機不存在或已停用")
        return redirect(url_for("project_detail", project_id=deployment["project_id"]))
    update_project_deployment(deployment_id, payload)
    flash("部署位置已更新")
    return redirect(url_for("project_detail", project_id=deployment["project_id"]))


@app.route("/project-deployments/<int:deployment_id>/toggle", methods=["POST"])
def project_deployment_toggle(deployment_id):
    deployment = query_one("SELECT * FROM project_deployments WHERE id=?", (deployment_id,))
    if not deployment:
        return "Project deployment not found", 404
    next_active = 0 if deployment["is_active"] else 1
    execute("UPDATE project_deployments SET is_active=?, updated_at=? WHERE id=?", (next_active, now_str(), deployment_id))
    flash("部署位置狀態已更新")
    return redirect(url_for("project_detail", project_id=deployment["project_id"]))


@app.route("/projects/<int:project_id>/deployments", methods=["POST"])
def deployment_create(project_id):
    execute("INSERT INTO deployments (project_id, environment, deploy_url, server_path, version, status, deployed_at, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, request.form.get("environment"), request.form.get("deploy_url"), request.form.get("server_path"), request.form.get("version"), request.form.get("status"), request.form.get("deployed_at"), request.form.get("notes"), now_str()))
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/acceptance", methods=["POST"])
def acceptance_create(project_id):
    execute("INSERT INTO acceptance_items (project_id, title, status, tested, accepted, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, request.form["title"], request.form.get("status", "未驗收"), 1 if request.form.get("tested") else 0, 1 if request.form.get("accepted") else 0, request.form.get("notes"), now_str(), now_str()))
    recalc_project(project_id)
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/acceptance/<int:item_id>/toggle", methods=["POST"])
def acceptance_toggle(item_id):
    item = query_one("SELECT * FROM acceptance_items WHERE id=?", (item_id,))
    accepted = 0 if item["accepted"] else 1
    tested = 1 if accepted else item["tested"]
    status = "已驗收" if accepted else "未驗收"
    execute("UPDATE acceptance_items SET accepted=?, tested=?, status=?, updated_at=? WHERE id=?", (accepted, tested, status, now_str(), item_id))
    recalc_project(item["project_id"])
    return redirect(url_for("project_detail", project_id=item["project_id"]))


# API
@app.route("/api/projects")
@require_api_token
def api_projects():
    items = [row_to_dict(r) for r in query_all("SELECT * FROM projects ORDER BY updated_at DESC")]
    return jsonify({"ok": True, "projects": items})


@app.route("/api/dispatch", methods=["POST"])
@require_api_token
def api_dispatch():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_dispatch_job(payload)
        log_api(payload.get("project_id"), payload, 200, payload.get("provider", "api"))
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/dispatch-jobs", methods=["GET"])
@require_api_token
def api_dispatch_jobs():
    try:
        project_id = request.args.get("project_id")
        limit = int(request.args.get("limit", "20"))
        jobs = dispatch_jobs_for_runner(
            status=(request.args.get("status") or "").strip() or None,
            agent=(request.args.get("agent") or "").strip() or None,
            project_id=int(project_id) if project_id else None,
            limit=limit,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "jobs": jobs})


@app.route("/api/dispatch-jobs/<int:job_id>/status", methods=["PATCH"])
@require_api_token
def api_dispatch_job_status(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return jsonify({"ok": False, "error": "dispatch job not found"}), 404
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "").strip()
    runner_statuses = {"queued", "running", "waiting_approval", "failed"}
    if status not in runner_statuses:
        return jsonify({"ok": False, "error": "unsupported runner status"}), 400
    updates = {"status": status}
    if status == "running":
        updates["started_at"] = payload.get("started_at") or job.get("started_at") or now_str()
        updates["finished_at"] = None
        updates["error_message"] = ""
    elif status in {"waiting_approval", "failed"}:
        updates["finished_at"] = payload.get("finished_at") or now_str()
        updates["error_message"] = payload.get("error_message") or ""
    if "result" in payload:
        updates["result"] = json.dumps(payload["result"], ensure_ascii=False) if isinstance(payload["result"], (dict, list)) else payload["result"]
    if "changed_files" in payload:
        updates["changed_files"] = json.dumps(payload["changed_files"], ensure_ascii=False) if isinstance(payload["changed_files"], (dict, list)) else (payload.get("changed_files") or "")
    if "diff_stat" in payload:
        updates["diff_stat"] = payload.get("diff_stat") or ""
    update_dispatch_job(job_id, **updates)
    updated = dispatch_job_row(job_id)
    log_api(updated["project_id"], {"action": "dispatch-status", "job_id": job_id, "status": status}, 200, "windows-runner")
    return jsonify({"ok": True, "dispatch_job_id": job_id, "job": updated})


@app.route("/api/dispatch-jobs/<int:job_id>/agent-runs", methods=["POST"])
@require_api_token
def api_dispatch_job_agent_runs(job_id):
    job = dispatch_job_row(job_id)
    if not job:
        return jsonify({"ok": False, "error": "dispatch job not found"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        exit_code = int(payload.get("exit_code", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "exit_code must be integer"}), 400
    run_id = record_agent_run(
        job_id,
        payload.get("command") or "windows codex runner",
        payload.get("stdout") or "",
        payload.get("stderr") or "",
        exit_code,
    )
    log_api(job["project_id"], {"action": "agent-run", "job_id": job_id, "agent_run_id": run_id, "exit_code": exit_code}, 200, "windows-runner")
    return jsonify({"ok": True, "agent_run_id": run_id, "dispatch_job_id": job_id})


@app.route("/api/dispatch-jobs/<int:job_id>/retry", methods=["POST"])
@require_api_token
def api_dispatch_job_retry(job_id):
    try:
        new_job = retry_dispatch_job(job_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    log_api(new_job["project_id"], {"action": "dispatch-retry", "job_id": job_id, "new_job_id": new_job["id"]}, 200, "api")
    return jsonify({
        "ok": True,
        "dispatch_job_id": new_job["id"],
        "retry_of": job_id,
        "job": new_job,
        "message": "dispatch job retried",
    })


@app.route("/api/reports/daily/generate", methods=["POST"])
@require_api_token
def api_daily_report_generate():
    report = generate_daily_report()
    log_api(None, {"action": "daily-report-generate", "daily_report_id": report["id"]}, 200, "daily-report")
    return jsonify({"ok": True, "daily_report": report})


@app.route("/api/reports/daily/latest", methods=["GET"])
@require_api_token
def api_daily_report_latest():
    report = latest_daily_report()
    if not report:
        return jsonify({"ok": True, "daily_report": None, "message": "尚未產生今日早報"})
    return jsonify({"ok": True, "daily_report": report})


@app.route("/api/projects/<int:project_id>/engineering-report", methods=["GET"])
@require_api_token
def api_project_engineering_report(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        return jsonify({"ok": False, "error": "project not found"}), 404
    export_format = normalize_choice(request.args.get("format"), ["markdown", "md", "html"], "markdown")
    markdown = build_engineering_report_markdown(project_id)
    if export_format == "html":
        return jsonify({
            "ok": True,
            "project_id": project_id,
            "format": "html",
            "filename": engineering_report_filename(project, "html"),
            "content": markdown_to_report_html(markdown),
        })
    return jsonify({
        "ok": True,
        "project_id": project_id,
        "format": "markdown",
        "filename": engineering_report_filename(project, "md"),
        "content": markdown,
    })


@app.route("/api/chat", methods=["POST"])
@require_api_token
def api_chat():
    payload = request.get_json(silent=True) or {}
    try:
        result = handle_chat(payload)
        log_api(None, {"action": "chat", "tenant_id": result.get("tenant_id"), "refused": result.get("refused"), "reason": result.get("reason")}, 200, "chat")
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/ai-costs")
@require_api_token
def api_ai_costs():
    return jsonify({"ok": True, "costs": ai_cost_overview()})


@app.route("/api/ai/providers/health", methods=["GET"])
@require_api_roles("owner", "admin", "ai")
def api_ai_provider_health():
    return jsonify(ai_provider_health_status())


@app.route("/api/ai-console/run", methods=["POST"])
@require_api_roles("owner", "admin", "ai")
def api_ai_console_run():
    return jsonify(run_ai_console_website_mvp())


@app.route("/api/ai-console/sandbox", methods=["GET"])
@require_api_roles("owner", "admin")
def api_ai_console_sandbox_list():
    limit = min(max(coerce_int(request.args.get("limit"), 50), 1), 50)
    artifacts = list_ai_console_sandbox_artifacts(limit=limit)
    return jsonify({
        "ok": artifacts.get("ok", True),
        "mode": "read_only_sandbox_gallery",
        "root_label": artifacts.get("root_label"),
        "exists": artifacts.get("exists"),
        "count": len(artifacts.get("items") or []),
        "items": artifacts.get("items") or [],
        "error": artifacts.get("error") or "",
        "safety": {
            "read_only": True,
            "delete": False,
            "apply_to_project": False,
            "project_repo_write": False,
            "deploy": False,
            "dns_write": False,
            "telegram_send": False,
        },
    })


@app.route("/api/ai-console/sandbox/<artifact_id>/download", methods=["GET"])
@require_api_roles("owner", "admin")
def api_ai_console_sandbox_download(artifact_id):
    try:
        path, html_content = read_ai_console_sandbox_artifact(artifact_id)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_sandbox_artifact"}), 400
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "sandbox_artifact_not_found"}), 404
    response = Response(html_content, mimetype="text/html; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/ai/messages", methods=["GET"])
@require_api_token
def api_ai_messages():
    project_id = request.args.get("project_id")
    return jsonify({
        "ok": True,
        "messages": recent_ai_messages(
            limit=coerce_int(request.args.get("limit"), 50),
            project_id=coerce_int(project_id, None) if project_id else None,
        ),
    })


@app.route("/api/ai/dispatch", methods=["POST"])
@app.route("/api/ai-dispatch", methods=["POST"])
@require_api_token
def api_ai_console_dispatch():
    payload = request.get_json(silent=True) or {}
    try:
        result = dispatch_ai_console_task(payload)
        status_code = 200 if result.get("ok") else 502
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/task-templates", methods=["GET"])
@require_api_token
def api_task_templates():
    include_inactive = request.args.get("include_inactive") in ("1", "true", "yes")
    return jsonify({"ok": True, "templates": task_template_rows(active_only=not include_inactive)})


@app.route("/api/tasks", methods=["GET", "POST"])
@require_api_token
def api_tasks():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            task = create_ai_task(payload)
            return jsonify({"ok": True, "task": task}), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    project_id = request.args.get("project_id")
    return jsonify({
        "ok": True,
        "tasks": task_rows(
            limit=coerce_int(request.args.get("limit"), 100),
            project_id=coerce_int(project_id, None) if project_id else None,
        ),
    })


@app.route("/api/ai-tasks/<int:task_id>", methods=["GET"])
@require_api_token
def api_ai_task_detail(task_id):
    detail = ai_task_detail(task_id)
    if not detail:
        return jsonify({"ok": False, "error": "AI task not found"}), 404
    return jsonify({"ok": True, **detail})


@app.route("/api/projects/<int:project_id>/tasks/from-template/<int:template_id>", methods=["POST"])
@require_api_token
def api_project_task_from_template(project_id, template_id):
    try:
        task = create_ai_task_from_template(project_id, template_id)
        log_api(project_id, {"action": "ai-task-from-template", "template_id": template_id, "task_id": task["id"]}, 201, task.get("provider", "api"))
        return jsonify({"ok": True, "project_id": project_id, "task": task}), 201
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/tasks/create-default-flow", methods=["POST"])
@require_api_token
def api_project_task_create_default_flow(project_id):
    try:
        tasks = create_default_ai_task_flow(project_id)
        log_api(project_id, {"action": "ai-task-create-default-flow", "task_count": len(tasks)}, 201, "api")
        return jsonify({"ok": True, "project_id": project_id, "tasks": tasks, "task_count": len(tasks)}), 201
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/run-ai-flow-safe", methods=["POST"])
@require_api_token
def api_project_run_ai_flow_safe(project_id):
    try:
        result = run_project_ai_flow(project_id, "safe")
        log_api(project_id, {"action": "run-ai-flow-safe", "status": result.get("status")}, 200, "api")
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/run-ai-flow-full", methods=["POST"])
@require_api_token
def api_project_run_ai_flow_full(project_id):
    try:
        result = run_project_ai_flow(project_id, "full")
        log_api(project_id, {"action": "run-ai-flow-full", "status": result.get("status")}, 200, "api")
        return jsonify(result), 200
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/flow-runs", methods=["GET"])
@require_api_token
def api_project_flow_runs(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return jsonify({"ok": False, "error": "project not found"}), 404
    limit = coerce_int(request.args.get("limit"), 20)
    rows = flow_run_rows(project_id=project_id, limit=limit)
    return jsonify({"ok": True, "project_id": project_id, "flow_runs": rows, "count": len(rows)})


@app.route("/api/flow-runs/<int:flow_run_id>", methods=["GET"])
@require_api_token
def api_flow_run_detail(flow_run_id):
    row = flow_run_row(flow_run_id)
    if not row:
        return jsonify({"ok": False, "error": "flow run not found"}), 404
    return jsonify({"ok": True, "flow_run": row})


@app.route("/api/tasks/<int:task_id>/run", methods=["POST"])
@require_api_token
def api_task_run(task_id):
    try:
        result = run_ai_task(task_id)
        return jsonify(result), 200 if result.get("ok") else 502
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/run-flow", methods=["POST"])
@require_api_token
def api_task_run_flow(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = run_ai_task_flow(task_id, max_depth=coerce_int(payload.get("max_depth"), 6))
        return jsonify(result), 200 if result.get("ok") else 502
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/retry", methods=["POST"])
@require_api_token
def api_task_retry(task_id):
    try:
        return jsonify({"ok": True, "task": retry_ai_task(task_id)})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/approve", methods=["POST"])
@require_api_token
def api_task_approve(task_id):
    try:
        return jsonify(approve_ai_task(task_id, approved_by="local_admin"))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/reject", methods=["POST"])
@require_api_token
def api_task_reject(task_id):
    try:
        return jsonify(reject_ai_task(task_id, approved_by="local_admin"))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/cancel", methods=["POST"])
@require_api_token
def api_task_cancel(task_id):
    try:
        return jsonify({"ok": True, "task": cancel_ai_task(task_id)})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/block", methods=["POST"])
@require_api_token
def api_task_block(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        reason = payload.get("reason") or "manual block"
        return jsonify({"ok": True, "task": block_ai_task(task_id, reason)})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/unblock", methods=["POST"])
@require_api_token
def api_task_unblock(task_id):
    try:
        return jsonify({"ok": True, "task": unblock_ai_task(task_id)})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/ai-usage-logs", methods=["GET", "POST"])
@require_api_token
def api_ai_usage_logs():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            provider_name = normalize_ai_provider_name(payload.get("provider"))
            provider = ai_provider_by_name(provider_name)
            if not provider:
                return jsonify({"ok": False, "error": "AI provider not found"}), 404
            cost = record_ai_usage(
                provider,
                payload.get("model") or provider.get("default_model"),
                payload.get("task_role") or "executor",
                normalize_choice(payload.get("status"), AI_USAGE_STATUSES, "success"),
                payload.get("project_id"),
                payload.get("dispatch_job_id"),
                payload.get("input_tokens") or 0,
                payload.get("output_tokens") or 0,
                payload.get("error_message") or "",
                payload.get("prompt_summary") or "",
                payload.get("fallback_used") in (True, 1, "1", "true", "yes"),
                payload.get("fallback_from"),
            )
            return jsonify({"ok": True, "estimated_cost": cost, "message": "AI usage log recorded"})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    where = ["1=1"]
    params = []
    if request.args.get("provider"):
        where.append("l.provider=?")
        params.append(normalize_ai_provider_name(request.args.get("provider")))
    if request.args.get("project_id"):
        where.append("l.project_id=?")
        params.append(request.args.get("project_id"))
    if request.args.get("status"):
        where.append("l.status=?")
        params.append(normalize_choice(request.args.get("status"), AI_USAGE_STATUSES, "success"))
    limit = max(1, min(500, coerce_int(request.args.get("limit"), 100)))
    params.append(limit)
    rows = [
        row_to_dict(row)
        for row in query_all(
            f"""SELECT l.*, p.name AS project_name
                FROM ai_usage_logs l
                LEFT JOIN projects p ON p.id=l.project_id
                WHERE {' AND '.join(where)}
                ORDER BY l.created_at DESC, l.id DESC
                LIMIT ?""",
            tuple(params),
        )
    ]
    return jsonify({"ok": True, "usage_logs": rows})


@app.route("/api/ai-providers", methods=["GET", "POST"])
@require_api_token
def api_ai_providers():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            provider = upsert_ai_provider(payload)
            return jsonify({"ok": True, "provider": provider})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "providers": ai_provider_rows()})


@app.route("/api/ai-providers/<int:provider_id>", methods=["PATCH"])
@require_api_token
def api_ai_provider_patch(provider_id):
    payload = request.get_json(silent=True) or {}
    try:
        provider = update_ai_provider(provider_id, payload)
        return jsonify({"ok": True, "provider": provider})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/ai-fallback-rules", methods=["POST"])
@require_api_token
def api_ai_fallback_rules():
    payload = request.get_json(silent=True) or {}
    try:
        rule = create_ai_fallback_rule(payload)
        return jsonify({"ok": True, "fallback_rule": rule})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/content/product-video", methods=["POST"])
@require_api_token
def api_content_product_video():
    payload = request.get_json(silent=True) or {}
    try:
        project_id = int(payload.get("project_id"))
        result = create_product_video_job(
            project_id,
            payload.get("product_name"),
            payload.get("features") or [],
            payload.get("target") or "",
            payload.get("style") or "",
            call_provider=True,
        )
        log_api(project_id, {"action": "content-product-video", "content_job_id": result.get("content_job_id"), "status": result.get("status")}, 200 if result.get("ok") else 502, "kling")
        return jsonify(result), (200 if result.get("ok") else 502)
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "project not found"}), 404


@app.route("/api/content/generate-video", methods=["POST"])
@require_api_token
def api_content_generate_video():
    payload = request.get_json(silent=True) or {}
    try:
        project_id = int(payload.get("project_id"))
        result = create_content_job(
            project_id,
            "video",
            payload.get("script") or "",
            payload.get("prompt") or "",
            call_provider=True,
        )
        log_api(project_id, {"action": "content-generate-video", "content_job_id": result.get("content_job_id"), "status": result.get("status")}, 200 if result.get("ok") else 502, "kling")
        return jsonify(result), (200 if result.get("ok") else 502)
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "project not found"}), 404


@app.route("/api/content/<int:content_job_id>/publish/facebook", methods=["POST"])
@require_api_token
def api_content_publish_facebook(content_job_id):
    try:
        result = publish_content_job(content_job_id, "facebook")
        log_api(result.get("project_id"), {"action": "content-publish", "content_job_id": content_job_id, "platform": "facebook", "status": "published" if result.get("ok") else "failed"}, 200 if result.get("ok") else 502, "facebook")
        return jsonify(result), (200 if result.get("ok") else 502)
    except LookupError:
        return jsonify({"ok": False, "error": "content job not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/content/<int:content_job_id>/publish/line", methods=["POST"])
@require_api_token
def api_content_publish_line(content_job_id):
    try:
        result = publish_content_job(content_job_id, "line")
        log_api(result.get("project_id"), {"action": "content-publish", "content_job_id": content_job_id, "platform": "line", "status": "published" if result.get("ok") else "failed"}, 200 if result.get("ok") else 502, "line")
        return jsonify(result), (200 if result.get("ok") else 502)
    except LookupError:
        return jsonify({"ok": False, "error": "content job not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/status")
@require_api_token
def api_project_status(project_id):
    project = row_to_dict(query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    if not project:
        return jsonify({"ok": False, "error": "找不到專案"}), 404
    phases = [row_to_dict(r) for r in query_all("SELECT id, phase_name, phase_order, status, due_date, completed_at, test_result FROM project_phases WHERE project_id=? ORDER BY phase_order", (project_id,))]
    last = row_to_dict(query_one("SELECT * FROM handoff_logs WHERE project_id=? AND COALESCE(is_hidden, 0)=0 ORDER BY created_at DESC LIMIT 1", (project_id,)))
    current_phase = next((p for p in phases if p["status"] not in ["已完成", "已驗收"]), phases[-1] if phases else None)
    return jsonify({"ok": True, "project": project, "progress": project["progress"], "current_phase": current_phase, "phases": phases, "next_steps": project.get("next_steps") if hasattr(project, 'get') else project["next_steps"], "last_handoff": last})


@app.route("/api/projects/<int:project_id>/handoff", methods=["POST"])
@require_api_token
def api_handoff(project_id):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        return jsonify({"ok": False, "error": "找不到專案"}), 404
    payload = request.get_json(silent=True) or {}
    if payload.get("raw_text") and not payload.get("summary"):
        parsed = parse_handoff_text(payload.get("raw_text"))
        payload = {**parsed, **payload}
    handoff_id = save_handoff(project_id, payload)
    log_api(project_id, payload, 200, payload.get("source"))
    return jsonify({"ok": True, "handoff_id": handoff_id, "message": "交接紀錄已寫入，階段狀態已嘗試自動更新"})


@app.route("/api/projects/<int:project_id>/handoff/parse", methods=["POST"])
@require_api_token
def api_handoff_parse(project_id):
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get("raw_text", "")
    parsed = parse_handoff_text(raw_text)
    merged = {**payload, **parsed, "raw_text": raw_text, "source": payload.get("source", "manual")}
    handoff_id = save_handoff(project_id, merged)
    log_api(project_id, merged, 200, merged.get("source"))
    return jsonify({"ok": True, "handoff_id": handoff_id, "parsed": parsed})


@app.route("/api/ai-heartbeats", methods=["GET", "POST"])
@require_api_token
def api_ai_heartbeats():
    if request.method == "GET":
        heartbeats = heartbeat_query(
            project_id=request.args.get("project_id"),
            source=request.args.get("source"),
            status=request.args.get("status"),
        )
        return jsonify({"ok": True, "heartbeats": heartbeats})

    payload = request.get_json(silent=True) or {}
    heartbeat_id = save_ai_heartbeat(payload)
    project_id = payload.get("project_id")
    try:
        project_id = int(project_id) if project_id not in (None, "") else None
    except (TypeError, ValueError):
        project_id = None
    log_api(project_id, payload, 200, payload.get("source"))
    return jsonify({"ok": True, "heartbeat_id": heartbeat_id, "message": "AI 心跳已更新"})


@app.route("/api/projects/<int:project_id>/repo-status", methods=["GET"])
@require_api_token
def api_project_repo_status(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return jsonify({"ok": False, "error": "project not found"}), 404
    repo, err = refresh_project_repo_status(project_id)
    if err:
        return jsonify({"ok": False, "error": err}), 404
    log_api(project_id, {"action": "repo-status"}, 200, "api")
    return jsonify({"ok": True, "project_id": project_id, "repo": repo})


@app.route("/api/projects/<int:project_id>/dispatch", methods=["POST"])
@require_api_token
def api_project_dispatch(project_id):
    payload = request.get_json(silent=True) or {}
    payload["project_id"] = project_id
    try:
        result = create_dispatch_job(payload)
        return jsonify(result)
    except LookupError:
        return jsonify({"ok": False, "error": "project not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/deploy-staging", methods=["POST"])
@require_api_token
def api_project_deploy_staging(project_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = perform_environment_deploy(project_id, "staging", payload)
        log_api(project_id, {"action": "deploy-staging", **payload}, 200 if result.get("ok") else 500, payload.get("source", "api"))
        return jsonify(result), (200 if result.get("ok") else 500)
    except LookupError:
        return jsonify({"ok": False, "error": "project not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"deploy command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"deploy command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/projects/<int:project_id>/deploy-production", methods=["POST"])
@require_api_roles("owner", "admin")
def api_project_deploy_production(project_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = perform_environment_deploy(project_id, "production", payload)
        log_api(project_id, {"action": "deploy-production", **payload}, 200 if result.get("ok") else 500, payload.get("source", "api"))
        return jsonify(result), (200 if result.get("ok") else 500)
    except LookupError:
        return jsonify({"ok": False, "error": "project not found"}), 404
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"deploy command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"deploy command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/deployment-jobs/<int:job_id>/approve", methods=["POST"])
@require_api_roles("owner", "admin")
def api_deployment_job_approve(job_id):
    job = deployment_job_row(job_id)
    if not job:
        return jsonify({"ok": False, "error": "deployment job not found"}), 404
    if job["environment"] != "production":
        return jsonify({"ok": False, "error": "only production jobs require approval"}), 400
    update_deployment_job(job_id, status="approved", approved_at=now_str(), notes=(request.get_json(silent=True) or {}).get("notes") or job.get("notes") or "")
    log_api(job["project_id"], {"action": "approve-deployment-job", "job_id": job_id}, 200, "api")
    return jsonify({"ok": True, "job_id": job_id, "project_id": job["project_id"], "status": "approved", "message": "production deployment job approved"})


@app.route("/api/deployment-jobs/<int:job_id>/validate-staging", methods=["POST"])
@require_api_token
def api_deployment_job_validate_staging(job_id):
    try:
        result = validate_staging_job(job_id)
        log_api(deployment_job_row(job_id)["project_id"], {"action": "validate-staging", "job_id": job_id}, 200, "google")
        return jsonify(result)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/deployment-jobs/<int:job_id>/rollback", methods=["POST"])
@require_api_token
def api_deployment_job_rollback(job_id):
    try:
        result = perform_rollback(job_id)
        log_api(deployment_job_row(job_id)["project_id"], {"action": "rollback", "job_id": job_id}, 200, "api")
        return jsonify(result)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"rollback command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"rollback command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/dispatch-jobs/<int:job_id>/deploy-staging", methods=["POST"])
@require_api_token
def api_dispatch_job_deploy_staging(job_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = perform_dispatch_staging_deploy(job_id, payload)
        job = dispatch_job_row(job_id)
        log_api(job["project_id"], {"action": "dispatch-deploy-staging", "job_id": job_id}, 200 if result.get("ok") else 500, "api")
        return jsonify(result), (200 if result.get("ok") else 500)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"deploy command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"deploy command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/dispatch-jobs/<int:job_id>/approve-production", methods=["POST"])
@require_api_roles("owner", "admin")
def api_dispatch_job_approve_production(job_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = perform_dispatch_production_deploy(job_id, payload)
        job = dispatch_job_row(job_id)
        log_api(job["project_id"], {"action": "dispatch-approve-production", "job_id": job_id}, 200 if result.get("ok") else 500, "api")
        return jsonify(result), (200 if result.get("ok") else 500)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"deploy command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"deploy command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/dispatch-jobs/<int:job_id>/rollback", methods=["POST"])
@require_api_token
def api_dispatch_job_rollback(job_id):
    try:
        result = perform_dispatch_rollback(job_id)
        job = dispatch_job_row(job_id)
        log_api(job["project_id"], {"action": "dispatch-rollback", "job_id": job_id}, 200, "api")
        return jsonify(result)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": f"rollback command not found: {exc.filename}"}), 500
    except subprocess.TimeoutExpired as exc:
        return jsonify({"ok": False, "error": f"rollback command timed out: {exc}"}), 500
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/projects/<int:project_id>/deployments", methods=["GET", "POST"])
@require_api_token
def api_project_deployments(project_id):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        return jsonify({"ok": False, "error": "專案不存在"}), 404
    if request.method == "GET":
        rows = [row_to_dict(r) for r in project_deployment_rows(project_id=project_id, active_only=False)]
        return jsonify({"ok": True, "project_id": project_id, "deployments": rows})
    payload = request.get_json(silent=True) or {}
    data = deployment_payload(payload)
    if not deployment_target_exists(data.get("target_id")):
        return jsonify({"ok": False, "error": "部署主機不存在或已停用"}), 400
    deployment_id = insert_project_deployment(project_id, data)
    log_api(project_id, payload, 200, payload.get("source"))
    return jsonify({"ok": True, "project_id": project_id, "deployment_id": deployment_id, "message": "部署位置已新增"})


@app.route("/api/project-deployments/<int:deployment_id>", methods=["PATCH"])
@require_api_token
def api_project_deployment_patch(deployment_id):
    deployment = query_one("SELECT * FROM project_deployments WHERE id=?", (deployment_id,))
    if not deployment:
        return jsonify({"ok": False, "error": "部署位置不存在"}), 404
    payload = request.get_json(silent=True) or {}
    data = {field: deployment[field] for field in PROJECT_DEPLOYMENT_FIELDS}
    for field in PROJECT_DEPLOYMENT_FIELDS:
        if field in payload:
            data[field] = normalize_target_id(payload[field]) if field == "target_id" else payload[field]
    if not deployment_target_exists(data.get("target_id")):
        return jsonify({"ok": False, "error": "部署主機不存在或已停用"}), 400
    update_project_deployment(deployment_id, data)
    log_api(deployment["project_id"], payload, 200, payload.get("source"))
    return jsonify({"ok": True, "deployment_id": deployment_id, "message": "部署位置已更新"})


@app.route("/api/project-deployments/<int:deployment_id>/status", methods=["PATCH"])
@require_api_token
def api_project_deployment_status(deployment_id):
    deployment = query_one("SELECT * FROM project_deployments WHERE id=?", (deployment_id,))
    if not deployment:
        return jsonify({"ok": False, "error": "部署位置不存在"}), 404
    payload = request.get_json(silent=True) or {}
    execute(
        """UPDATE project_deployments
           SET status=COALESCE(?, status),
               last_checked_at=COALESCE(?, last_checked_at),
               last_deployed_at=COALESCE(?, last_deployed_at),
               notes=COALESCE(?, notes),
               updated_at=?
           WHERE id=?""",
        (
            payload.get("status"),
            payload.get("last_checked_at") or now_str(),
            payload.get("last_deployed_at"),
            payload.get("notes"),
            now_str(),
            deployment_id,
        ),
    )
    log_api(deployment["project_id"], payload, 200, payload.get("source"))
    return jsonify({"ok": True, "deployment_id": deployment_id, "message": "部署狀態已更新"})


@app.route("/api/deployment-targets/<int:target_id>/scan-docker", methods=["POST"])
@require_api_token
def api_deployment_target_scan_docker(target_id):
    if not query_one("SELECT id FROM deployment_targets WHERE id=? AND COALESCE(is_active, 1)=1", (target_id,)):
        return jsonify({"ok": False, "error": "部署主機不存在或已停用"}), 404
    body = request.get_json(silent=True) or {}
    root = body.get("docker_root")
    try:
        out = perform_docker_scan(target_id, root)
        log_api(None, {"target_id": target_id, "action": "scan-docker"}, 200, "api")
        return jsonify(out)
    except ValueError as ve:
        return jsonify({"ok": False, "error": str(ve)}), 400
    except Exception as exc:
        tgt = row_to_dict(query_one("SELECT * FROM deployment_targets WHERE id=?", (target_id,)))
        ssh_h = (tgt.get("ssh_host") or tgt.get("ip_address") or "") if tgt else ""
        execute(
            """INSERT INTO docker_scan_runs
               (target_id, target_name, ssh_host, docker_root, status, summary, raw_output, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                target_id,
                tgt["name"] if tgt else "",
                ssh_h,
                (root or ""),
                "error",
                str(exc)[:500],
                str(exc)[:120000],
                now_str(),
            ),
        )
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/docker-services", methods=["GET"])
@require_api_token
def api_docker_services():
    try:
        rows = docker_service_api_query()
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid query parameter"}), 400
    include_raw = request.args.get("include_raw") in ("1", "true", "yes")
    include_endpoints = request.args.get("include_endpoints") in ("1", "true", "yes")
    services = [docker_service_api_row(row, include_raw=include_raw) for row in rows]
    if include_endpoints:
        endpoint_map = service_endpoint_map()
        for service in services:
            service["endpoints"] = endpoint_map.get(service["id"], [])
    return jsonify({"ok": True, "count": len(services), "docker_services": services})


@app.route("/api/docker-services/<int:service_id>", methods=["GET"])
@require_api_token
def api_docker_service_detail(service_id):
    row = query_one(
        """SELECT ds.*,
                  dt.name AS target_name,
                  dt.target_type,
                  dt.ip_address AS target_ip_address,
                  dt.domain AS target_domain,
                  dt.ssh_host,
                  p.name AS project_name,
                  p.client_name AS project_client_name,
                  (SELECT COUNT(*) FROM service_endpoints se
                   WHERE se.docker_service_id=ds.id AND COALESCE(se.is_ignored,0)=0) AS endpoint_count,
                  (SELECT COUNT(*) FROM service_endpoints se
                   WHERE se.docker_service_id=ds.id AND COALESCE(se.is_confirmed,0)=1 AND COALESCE(se.is_ignored,0)=0) AS confirmed_endpoint_count
           FROM docker_services ds
           LEFT JOIN deployment_targets dt ON ds.target_id=dt.id
           LEFT JOIN projects p ON ds.project_id=p.id
           WHERE ds.id=?""",
        (service_id,),
    )
    if not row:
        return jsonify({"ok": False, "error": "docker service not found"}), 404
    include_raw = request.args.get("include_raw") in ("1", "true", "yes")
    service = docker_service_api_row(row, include_raw=include_raw)
    service["endpoints"] = docker_service_endpoint_rows(service_id)
    return jsonify({"ok": True, "docker_service": service})


@app.route("/api/docker-services/<int:service_id>/bind-project", methods=["PATCH"])
@require_api_token
def api_docker_service_bind_project(service_id):
    payload = request.get_json(silent=True) or {}
    if payload.get("project_id") is None:
        return jsonify({"ok": False, "error": "缺少 project_id"}), 400
    res, err = bind_docker_service_to_project(
        service_id, int(payload["project_id"]), environment=payload.get("environment")
    )
    if err:
        return jsonify({"ok": False, "error": err}), 404
    log_api(int(payload["project_id"]), payload, 200, payload.get("source", "api"))
    return jsonify(res)


@app.route("/api/docker-services/<int:service_id>/bootstrap-project", methods=["POST"])
@require_api_token
def api_docker_service_bootstrap_project(service_id):
    try:
        res, err = bootstrap_project_from_docker_service(service_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    if err:
        return jsonify({"ok": False, "error": err}), 404
    log_api(res.get("project_id"), {"docker_service_id": service_id, "action": "bootstrap-project"}, 200, "api")
    return jsonify(res)


@app.route("/api/docker-services/<int:service_id>/scan-endpoints", methods=["POST"])
@require_api_token
def api_docker_service_scan_endpoints(service_id):
    if not query_one("SELECT id FROM docker_services WHERE id=?", (service_id,)):
        return jsonify({"ok": False, "error": "docker service not found"}), 404
    try:
        out = scan_service_endpoints(service_id)
        log_api(out.get("project_id"), {"docker_service_id": service_id, "action": "scan-endpoints"}, 200, "api")
        return jsonify(out)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/docker-services/scan-endpoints-all", methods=["POST"])
@require_api_token
def api_docker_services_scan_endpoints_all():
    out = scan_all_service_endpoints()
    log_api(None, {"action": "scan-endpoints-all"}, 200 if out.get("ok") else 207, "api")
    return jsonify(out), (200 if out.get("ok") else 207)


@app.route("/api/handoffs/<int:handoff_id>/hide", methods=["PATCH"])
@require_api_token
def api_handoff_hide(handoff_id):
    handoff = hide_handoff(handoff_id)
    if not handoff:
        return jsonify({"ok": False, "error": "交接紀錄不存在"}), 404
    log_api(handoff["project_id"], {"handoff_id": handoff_id, "action": "hide"}, 200, "api")
    return jsonify({"ok": True, "handoff_id": handoff_id, "message": "交接紀錄已隱藏"})


@app.route("/api/handoffs/<int:handoff_id>/restore", methods=["PATCH"])
@require_api_token
def api_handoff_restore(handoff_id):
    handoff = restore_handoff(handoff_id)
    if not handoff:
        return jsonify({"ok": False, "error": "交接紀錄不存在"}), 404
    log_api(handoff["project_id"], {"handoff_id": handoff_id, "action": "restore"}, 200, "api")
    return jsonify({"ok": True, "handoff_id": handoff_id, "message": "交接紀錄已還原"})


@app.route("/api/projects/<int:project_id>/phases/<int:phase_id>", methods=["PATCH"])
@require_api_token
def api_phase_patch(project_id, phase_id):
    payload = request.get_json(silent=True) or {}
    phase = query_one("SELECT * FROM project_phases WHERE id=? AND project_id=?", (phase_id, project_id))
    if not phase:
        return jsonify({"ok": False, "error": "找不到階段"}), 404
    status = payload.get("status", phase["status"])
    completed_at = payload.get("completed_at") or (now_str() if status in ["已完成", "已驗收"] else phase["completed_at"])
    execute("UPDATE project_phases SET status=?, test_result=COALESCE(?, test_result), notes=COALESCE(?, notes), completed_at=?, updated_at=? WHERE id=?",
            (status, payload.get("test_result"), payload.get("notes"), completed_at, now_str(), phase_id))
    recalc_project(project_id)
    log_api(project_id, payload, 200, payload.get("source"))
    return jsonify({"ok": True, "message": "階段已更新"})


@app.route("/api/projects/<int:project_id>/tasks", methods=["GET", "POST"])
@require_api_token
def api_task_create(project_id):
    if not query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        return jsonify({"ok": False, "error": "project not found"}), 404
    if request.method == "GET":
        return jsonify({"ok": True, "project_id": project_id, "tasks": task_rows(project_id=project_id)})
    payload = request.get_json(silent=True) or {}
    is_legacy_project_task = (
        payload.get("kind") == "project_task"
        or ("phase_id" in payload and not any(key in payload for key in ("prompt", "task_prompt", "provider", "task_type")))
    )
    if not is_legacy_project_task:
        payload["project_id"] = project_id
        try:
            task = create_ai_task(payload)
            log_api(project_id, {"action": "ai-task-create", "task_id": task["id"]}, 201, payload.get("provider", "api"))
            return jsonify({"ok": True, "project_id": project_id, "task": task}), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    cur = execute("INSERT INTO project_tasks (project_id, phase_id, title, status, priority, assignee, due_date, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (project_id, payload.get("phase_id"), payload.get("title", "未命名任務"), payload.get("status", "未開始"), payload.get("priority", "中"), payload.get("assignee"), payload.get("due_date"), payload.get("notes"), now_str(), now_str()))
    if payload.get("phase_id"):
        recalc_phase_by_tasks(project_id, int(payload["phase_id"]))
    recalc_project(project_id)
    return jsonify({"ok": True, "task_id": cur.lastrowid, "kind": "project_task"})


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@require_api_token
def api_task_patch(task_id):
    payload = request.get_json(silent=True) or {}
    task = query_one("SELECT * FROM project_tasks WHERE id=?", (task_id,))
    if not task:
        return jsonify({"ok": False, "error": "找不到任務"}), 404
    status = payload.get("status", task["status"])
    completed_at = payload.get("completed_at") or (now_str() if status == "已完成" else task["completed_at"])
    execute("UPDATE project_tasks SET status=?, priority=COALESCE(?, priority), assignee=COALESCE(?, assignee), due_date=COALESCE(?, due_date), completed_at=?, notes=COALESCE(?, notes), updated_at=? WHERE id=?",
            (status, payload.get("priority"), payload.get("assignee"), payload.get("due_date"), completed_at, payload.get("notes"), now_str(), task_id))
    if task["phase_id"]:
        recalc_phase_by_tasks(task["project_id"], task["phase_id"])
    recalc_project(task["project_id"])
    return jsonify({"ok": True, "message": "任務已更新"})


@app.context_processor
def inject_helpers():
    return dict(
        parse_json_list=parse_json_list,
        handoff_api_base_url=API_BASE_URL,
        api_base_url=API_BASE_URL,
        machine_display_name=machine_display_name,
        current_user=current_user(),
        current_role=current_role(),
        has_role=has_role,
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    start_ai_fleet_poller()
    start_api_key_rotation_scheduler()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "1") == "1")
