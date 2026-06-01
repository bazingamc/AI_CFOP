"""
用户管理模块 - 多用户模式
"""

import sqlite3
import random
import os
from datetime import datetime
from typing import Optional, List, Dict

from config import APP_DIR

DB_FILE = os.path.join(APP_DIR, "cfop_memory.db")

ADJECTIVES = [
    "忧郁的", "快乐的", "沉默的", "温柔的", "勇敢的", "灵动的", "安静的", "热情的",
    "淡定的", "调皮的", "优雅的", "慵懒的", "执着的", "洒脱的", "沉稳的", "活泼的",
    "冷静的", "浪漫的", "坚定的", "随性的", "睿智的", "飘逸的", "豪迈的", "细腻的",
    "从容的", "率真的", "内敛的", "奔放的", "温和的", "机敏的", "淡然的", "爽朗的",
    "深沉的", "纯真的", "坦荡的", "敏锐的", "洒脱的", "恬静的", "刚毅的", "悠然的",
]

NOUNS = [
    "斑马", "猎豹", "白鹤", "海豚", "雪狐", "苍鹰", "锦鲤", "云雀",
    "飞燕", "灵猫", "雪兔", "星鹿", "青鸾", "银狼", "金雕", "紫蝶",
    "玉兔", "火凤", "墨龙", "碧蛇", "赤狐", "翠鸟", "蓝鲸", "白鹭",
    "黑豹", "红鲤", "银鲨", "金凤", "雪豹", "云豹", "风隼", "雷鹰",
    "月熊", "星辰", "晨曦", "暮光", "清风", "流云", "落霞", "飞雪",
]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_table():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            avatar TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def generate_random_username() -> str:
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}{noun}"


def create_user(username: str, avatar: str = "") -> Optional[int]:
    if not username.strip():
        return None
    conn = _get_conn()
    c = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO users (username, avatar, created_at) VALUES (?, ?, ?)",
            (username.strip(), avatar, now)
        )
        conn.commit()
        user_id = c.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not c.fetchone():
        conn.close()
        return False
    c.execute("DELETE FROM phase_stats WHERE record_id IN (SELECT id FROM records WHERE user_id = ?)", (user_id,))
    c.execute("DELETE FROM records WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def get_all_users() -> List[Dict]:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, avatar, created_at FROM users ORDER BY id")
    users = []
    for row in c.fetchall():
        users.append({
            "id": row[0],
            "username": row[1],
            "avatar": row[2],
            "created_at": row[3],
        })
    conn.close()
    return users


def get_user(user_id: int) -> Optional[Dict]:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, avatar, created_at FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "avatar": row[2],
            "created_at": row[3],
        }
    return None


def update_user(user_id: int, username: str = None, avatar: str = None) -> bool:
    conn = _get_conn()
    c = conn.cursor()
    try:
        if username is not None:
            c.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        if avatar is not None:
            c.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def check_username_exists(username: str, exclude_id: int = None) -> bool:
    conn = _get_conn()
    c = conn.cursor()
    if exclude_id:
        c.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, exclude_id))
    else:
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone() is not None
    conn.close()
    return result


def ensure_default_user() -> int:
    users = get_all_users()
    if users:
        return users[0]["id"]
    user_id = create_user("默认用户")
    if user_id:
        return user_id
    return 1


def get_default_avatar_path() -> str:
    return os.path.join(APP_DIR, "default_avatar.png")


def generate_default_avatar():
    path = get_default_avatar_path()
    if os.path.exists(path):
        return path
    try:
        from PIL import Image, ImageDraw
        size = 128
        img = Image.new("RGBA", (size, size), (108, 92, 231, 255))
        draw = ImageDraw.Draw(img)
        cx, cy = size // 2, size // 2 - 8
        r_head = 28
        draw.ellipse([cx - r_head, cy - r_head, cx + r_head, cy + r_head],
                      fill=(255, 255, 255, 230))
        r_body = 36
        body_top = cy + r_head + 4
        draw.ellipse([cx - r_body, body_top, cx + r_body, body_top + r_body * 2],
                      fill=(255, 255, 255, 230))
        img.save(path, "PNG")
        return path
    except Exception:
        return ""
