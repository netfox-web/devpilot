import os
import json
import re
import sqlite3
from datetime import datetime, date
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, redirect, render_template, request, url_for, flash
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "DevPilot 專案開發管家"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "project_manager.db"))
API_TOKEN = os.getenv("API_TOKEN", "change-me-token")
API_BASE_URL = os.getenv("DEV_PILOT_API_URL", "http://127.0.0.1:5000")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devpilot-secret-key")

STATUSES = ["未開始", "規劃中", "開發中", "測試中", "待驗收", "已結案", "暫停", "有問題", "逾期"]
PHASE_STATUSES = ["未開始", "進行中", "已完成", "待驗收", "已驗收", "有問題", "逾期"]
TASK_STATUSES = ["未開始", "進行中", "已完成", "有問題", "逾期", "取消"]
PRIORITIES = ["低", "中", "高", "緊急"]
SOURCES = ["codex", "claude", "cursor", "antigravity", "manual", "github", "deploy"]
WORK_MODES = ["planning", "review", "code-change", "debug", "test", "deploy", "manual", "agent-run"]


def ps_quote(value):
    return str(value).replace("`", "``").replace('"', '`"')


def build_powershell_handoff_command(project_id, source, agent_name):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$ApiToken = "{ps_quote(API_TOKEN)}"
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
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers @{{ Authorization = "Bearer $ApiToken" }} -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_cursor_powershell_handoff_command(project_id):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$ApiToken = "{ps_quote(API_TOKEN)}"
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
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers @{{ Authorization = "Bearer $ApiToken" }} -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_antigravity_powershell_handoff_command(project_id):
    return f'''$ApiUrl = "{ps_quote(API_BASE_URL)}"
$ProjectId = {project_id}
$ApiToken = "{ps_quote(API_TOKEN)}"
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
Invoke-RestMethod -Uri "$ApiUrl/api/projects/$ProjectId/handoff" -Method Post -Headers @{{ Authorization = "Bearer $ApiToken" }} -ContentType "application/json; charset=utf-8" -Body $bytes'''


def build_python_handoff_command(project_id):
    return f'''python scripts/report_handoff.py --base-url "{API_BASE_URL}" --project-id {project_id} --source codex --agent-name "Codex" --work-mode code-change --summary "請填寫本次完成內容" --phase "請填寫完成階段" --changed-file "請填寫修改檔案" --test-result "請填寫測試結果" --next-steps "請填寫下一步" --warnings "請填寫注意事項"'''


def build_handoff_copy_commands(project_id):
    return {
        "claude_ps": build_powershell_handoff_command(project_id, "claude", "Claude Code"),
        "codex_ps": build_powershell_handoff_command(project_id, "codex", "Codex"),
        "cursor_ps": build_cursor_powershell_handoff_command(project_id),
        "antigravity_ps": build_antigravity_powershell_handoff_command(project_id),
        "python": build_python_handoff_command(project_id),
    }


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return date.today().isoformat()


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


def require_api_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth.replace("Bearer ", "", 1).strip() != API_TOKEN:
            return jsonify({"ok": False, "error": "API Token 錯誤或未提供 Authorization: Bearer TOKEN"}), 401
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
                project_id INTEGER NOT NULL,
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
        seed_demo_project()


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
            project_id INTEGER NOT NULL,
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
    seed_computers()
    seed_deployment_targets()
    ensure_disney_nas_info()


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
    existing = query_one(
        "SELECT * FROM deployment_targets WHERE name=? OR ip_address=? LIMIT 1",
        ("disney", "211.75.219.184"),
    )
    values = (
        "disney",
        "nas",
        "NAS",
        "211.75.219.184",
        "",
        "211.75.219.184",
        "22",
        "chaokun",
        "部署根目錄: /volume1/docker; SSH 已可免密登入",
        now_str(),
    )
    if existing:
        execute(
            """UPDATE deployment_targets
               SET name=?, target_type=?, location=?, ip_address=?, domain=?, ssh_host=?, ssh_port=?, ssh_user=?, notes=?, is_active=1, updated_at=?
               WHERE id=?""",
            (*values, existing["id"]),
        )
    else:
        execute(
            """INSERT INTO deployment_targets
               (name, target_type, location, ip_address, domain, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (*values, now_str()),
        )


def ensure_disney_nas_info():
    notes = (
        "已設定 SSH Key 免密登入，可供 Codex / Cursor / Claude Code 部署使用。"
        " 部署根目錄: /volume1/docker。"
        " 安全限制: 不可刪除 /volume1/docker；不可刪除 data/uploads/output/backup；"
        "不可覆蓋 .env，若需變更先產生 .env.example 或回報差異；不可清空 SQLite DB；"
        "不可執行 rm -rf /、rm -rf /volume1、rm -rf /volume1/docker；"
        "部署前必須先備份 docker-compose.yml；若專案已有 data 資料夾，部署前先確認 volume 掛載；"
        "部署完成後要執行 docker compose ps 與 docker compose logs --tail=80；"
        "完成後要回寫 DevPilot API，紀錄部署路徑、port、測試結果與下一步。"
    )
    existing = query_one(
        "SELECT * FROM deployment_targets WHERE name IN (?, ?) OR ip_address=? LIMIT 1",
        ("disney NAS", "disney", "211.75.219.184"),
    )
    if existing:
        execute(
            """UPDATE deployment_targets
               SET name=?, target_type=?, location=?, ip_address=?, ssh_host=?, ssh_port=?, ssh_user=?, notes=?, is_active=1, updated_at=?
               WHERE id=?""",
            ("disney NAS", "Synology NAS", "NAS", "211.75.219.184", "211.75.219.184", "22", "chaokun", notes, now_str(), existing["id"]),
        )
    else:
        execute(
            """INSERT INTO deployment_targets
               (name, target_type, location, ip_address, ssh_host, ssh_port, ssh_user, notes, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            ("disney NAS", "Synology NAS", "NAS", "211.75.219.184", "211.75.219.184", "22", "chaokun", notes, now_str(), now_str()),
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


@app.route("/")
def dashboard():
    projects = query_all("SELECT * FROM projects ORDER BY updated_at DESC")
    recent_logs = query_all("SELECT h.*, p.name AS project_name FROM handoff_logs h JOIN projects p ON h.project_id=p.id WHERE COALESCE(h.is_hidden, 0)=0 ORDER BY h.created_at DESC LIMIT 8")
    overdue_tasks = query_all("SELECT t.*, p.name AS project_name FROM project_tasks t JOIN projects p ON t.project_id=p.id WHERE t.due_date < ? AND t.status != '已完成' ORDER BY t.due_date ASC LIMIT 8", (today_str(),))
    development_workload = get_computer_workload("computer_id")
    deployment_workload = get_computer_workload("deploy_computer_id")
    stats = {
        "total": len(projects),
        "active": sum(1 for p in projects if p["status"] in ["開發中", "測試中", "規劃中"]),
        "acceptance": sum(1 for p in projects if p["status"] == "待驗收"),
        "problem": sum(1 for p in projects if p["status"] in ["有問題", "逾期"]),
    }
    return render_template("dashboard.html", app_name=APP_NAME, projects=projects, recent_logs=recent_logs, overdue_tasks=overdue_tasks, stats=stats, development_workload=development_workload, deployment_workload=deployment_workload)


@app.route("/projects")
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


@app.route("/projects/new", methods=["GET", "POST"])
def project_new():
    templates = query_all("SELECT * FROM project_templates ORDER BY id")
    if request.method == "POST":
        template_id = request.form.get("template_id") or None
        cur = execute(
            """INSERT INTO projects
            (name, client_name, project_type, status, priority, github_repo, local_path, deploy_url, deploy_location, owner_machine, description, next_steps, progress, template_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                request.form["name"], request.form.get("client_name"), request.form.get("project_type"),
                request.form.get("status", "規劃中"), request.form.get("priority", "中"), request.form.get("github_repo"),
                request.form.get("local_path"), request.form.get("deploy_url"), request.form.get("deploy_location"), request.form.get("owner_machine"),
                request.form.get("description"), request.form.get("next_steps"), template_id, now_str(), now_str(),
            ),
        )
        project_id = cur.lastrowid
        if template_id:
            create_phases_from_template(project_id, int(template_id))
        recalc_project(project_id)
        flash("專案已建立")
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
    deployment_targets = get_deployment_targets(include_inactive=False)
    acceptance = query_all("SELECT * FROM acceptance_items WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    copy_commands = build_handoff_copy_commands(project_id)
    computer_options = get_computer_options()
    return render_template("project_detail.html", app_name=APP_NAME, project=project, phases=phases, tasks=tasks, logs=logs, deployments=deployments, project_deployments=project_deployments, deployment_targets=deployment_targets, acceptance=acceptance, sources=SOURCES, work_modes=WORK_MODES, phase_statuses=PHASE_STATUSES, task_statuses=TASK_STATUSES, priorities=PRIORITIES, copy_commands=copy_commands, show_hidden=show_hidden, computer_options=computer_options, api_token=API_TOKEN)


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def project_edit(project_id):
    project = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    templates = query_all("SELECT * FROM project_templates ORDER BY id")
    if request.method == "POST":
        execute(
            """UPDATE projects SET name=?, client_name=?, project_type=?, status=?, priority=?, github_repo=?, local_path=?, deploy_url=?, deploy_location=?, owner_machine=?, description=?, next_steps=?, updated_at=? WHERE id=?""",
            (request.form["name"], request.form.get("client_name"), request.form.get("project_type"), request.form.get("status"), request.form.get("priority"), request.form.get("github_repo"), request.form.get("local_path"), request.form.get("deploy_url"), request.form.get("deploy_location"), request.form.get("owner_machine"), request.form.get("description"), request.form.get("next_steps"), now_str(), project_id),
        )
        flash("專案已更新")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("project_form.html", app_name=APP_NAME, project=project, templates=templates, statuses=STATUSES, priorities=PRIORITIES)


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


@app.route("/api/projects/<int:project_id>/tasks", methods=["POST"])
@require_api_token
def api_task_create(project_id):
    payload = request.get_json(silent=True) or {}
    cur = execute("INSERT INTO project_tasks (project_id, phase_id, title, status, priority, assignee, due_date, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (project_id, payload.get("phase_id"), payload.get("title", "未命名任務"), payload.get("status", "未開始"), payload.get("priority", "中"), payload.get("assignee"), payload.get("due_date"), payload.get("notes"), now_str(), now_str()))
    if payload.get("phase_id"):
        recalc_phase_by_tasks(project_id, int(payload["phase_id"]))
    recalc_project(project_id)
    return jsonify({"ok": True, "task_id": cur.lastrowid})


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
    return dict(parse_json_list=parse_json_list)


if __name__ == "__main__":
    init_db()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "1") == "1")
