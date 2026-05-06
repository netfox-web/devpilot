import getpass
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "project_manager.db"


def resolve_db_path():
    configured = os.getenv("DATABASE_PATH")
    if not configured:
        return DEFAULT_DB_PATH
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_new_password():
    password = os.getenv("DEV_PILOT_OWNER_PASSWORD")
    if password:
        return password

    password = getpass.getpass("請輸入新的 owner 密碼：")
    if not password:
        raise ValueError("密碼不可為空")
    confirm = getpass.getpass("請再次輸入新的 owner 密碼：")
    if password != confirm:
        raise ValueError("兩次輸入的密碼不一致")
    return password


def table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def reset_owner_password(db_path, password):
    if not db_path.exists():
        raise FileNotFoundError(f"找不到資料庫：{db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if not table_exists(conn, "users"):
            raise RuntimeError("資料庫內沒有 users 表")

        owner = conn.execute(
            "SELECT id, username FROM users WHERE username=?",
            ("owner",),
        ).fetchone()
        if not owner:
            raise RuntimeError("找不到 username=owner 的使用者")

        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=? WHERE username=?",
            (
                generate_password_hash(password),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "owner",
            ),
        )
        conn.commit()
        return owner["id"]
    finally:
        conn.close()


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        db_path = resolve_db_path()
        password = read_new_password()
        owner_id = reset_owner_password(db_path, password)
    except Exception as exc:
        print(f"owner 密碼重設失敗：{exc}", file=sys.stderr)
        return 1

    print(f"owner 密碼已成功重設（user_id={owner_id}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
