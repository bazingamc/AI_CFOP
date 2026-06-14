"""
记忆数据库 - SQLite存储分析历史数据
"""

import sqlite3
import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import APP_DIR, COLOR_NAMES

DB_FILE = os.path.join(APP_DIR, "cfop_memory.db")

PHASE_FIELDS = ["steps", "time", "observation_time", "stutter_count", "wasted_moves", "tps"]

_current_user_id = None


def set_current_user(user_id: int):
    global _current_user_id
    _current_user_id = user_id


def get_current_user() -> Optional[int]:
    return _current_user_id


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 0,
            date TEXT NOT NULL,
            scramble TEXT NOT NULL DEFAULT '',
            solution TEXT NOT NULL DEFAULT '',
            total_time REAL NOT NULL DEFAULT 0,
            bottom_color TEXT NOT NULL DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS phase_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            phase TEXT NOT NULL,
            steps INTEGER NOT NULL DEFAULT 0,
            time REAL NOT NULL DEFAULT 0,
            observation_time REAL NOT NULL DEFAULT 0,
            stutter_count INTEGER NOT NULL DEFAULT 0,
            wasted_moves INTEGER NOT NULL DEFAULT 0,
            tps REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (record_id) REFERENCES records(id)
        )
    """)

    col_check = c.execute("PRAGMA table_info(records)").fetchall()
    col_names = [col[1] for col in col_check]
    if 'user_id' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
    if 'analyzed' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN analyzed INTEGER NOT NULL DEFAULT 0")
    if 'strength_tags' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN strength_tags TEXT NOT NULL DEFAULT ''")
    if 'weakness_tags' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN weakness_tags TEXT NOT NULL DEFAULT ''")
    if 'total_steps' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN total_steps INTEGER NOT NULL DEFAULT 0")
    if 'total_tps' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN total_tps REAL NOT NULL DEFAULT 0")
    if 'processed_solve' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN processed_solve TEXT NOT NULL DEFAULT ''")
    if 'oll_case' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN oll_case TEXT NOT NULL DEFAULT ''")
    if 'pll_case' not in col_names:
        c.execute("ALTER TABLE records ADD COLUMN pll_case TEXT NOT NULL DEFAULT ''")

    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_stats_record ON phase_stats(record_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_stats_phase ON phase_stats(phase)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_records_user_id ON records(user_id)")
    conn.commit()
    conn.close()


def save_record(scramble: str, solution: str, total_time: float,
                bottom_color: str, phase_stats: Dict,
                total_steps: int = 0, total_tps: float = 0.0,
                processed_solve: str = "", oll_case: str = "", pll_case: str = "") -> int:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute(
        "SELECT id FROM records WHERE user_id = ? AND scramble = ? AND solution = ? AND ABS(total_time - ?) < 0.01 LIMIT 1",
        (uid, scramble, solution, total_time)
    )
    if c.fetchone():
        conn.close()
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO records (user_id, date, scramble, solution, total_time, bottom_color, total_steps, total_tps, processed_solve, oll_case, pll_case) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, now, scramble, solution, total_time, bottom_color, total_steps, total_tps, processed_solve, oll_case, pll_case)
    )
    record_id = c.lastrowid
    for phase, stats in phase_stats.items():
        c.execute(
            "INSERT INTO phase_stats (record_id, phase, steps, time, observation_time, stutter_count, wasted_moves, tps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, phase,
             stats.get("steps", 0), stats.get("time", 0),
             stats.get("observation_time", 0), stats.get("stutter_count", 0),
             stats.get("wasted_moves", 0), stats.get("tps", 0))
        )
    conn.commit()
    conn.close()
    return record_id


def get_record_count() -> int:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT COUNT(*) FROM records WHERE user_id = ?", (uid,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_date_range() -> str:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT MIN(date), MAX(date) FROM records WHERE user_id = ?", (uid,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return f"{row[0][:10]} ~ {row[1][:10]}"
    return "无数据"


def _trimmed_mean(values: list, trim_pct: float = 0.05) -> float:
    if not values:
        return 0.0
    n = len(values)
    if n < 20:
        return sum(values) / n
    values = sorted(values)
    trim = max(1, int(n * trim_pct))
    trimmed = values[trim:n - trim]
    if not trimmed:
        return sum(values) / n
    return sum(trimmed) / len(trimmed)


def _std_dev(values: list) -> float:
    if not values or len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    variance = sum((x - avg) ** 2 for x in values) / len(values)
    return variance ** 0.5


def get_averages(days: Optional[int] = None, limit: int = 1000) -> Dict[str, Dict[str, float]]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id FROM records WHERE user_id = ? AND date >= ? ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute("SELECT id FROM records WHERE user_id = ? ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute("SELECT id FROM records WHERE user_id = ? ORDER BY date DESC", (uid,))
    record_ids = [row[0] for row in c.fetchall()]
    if not record_ids:
        conn.close()
        return {}

    placeholders = ",".join("?" * len(record_ids))
    c.execute(f"SELECT phase, steps, time, observation_time, stutter_count, wasted_moves, tps "
              f"FROM phase_stats WHERE record_id IN ({placeholders})",
              record_ids)

    phase_data = {}
    for row in c.fetchall():
        phase = row[0]
        if phase not in phase_data:
            phase_data[phase] = {"steps": [], "time": [], "observation_time": [],
                                 "stutter_count": [], "wasted_moves": [], "tps": []}
        phase_data[phase]["steps"].append(row[1])
        phase_data[phase]["time"].append(row[2])
        phase_data[phase]["observation_time"].append(row[3])
        phase_data[phase]["stutter_count"].append(row[4])
        phase_data[phase]["wasted_moves"].append(row[5])
        phase_data[phase]["tps"].append(row[6])
    conn.close()

    result = {}
    for phase, data in phase_data.items():
        cnt = len(data["steps"])
        result[phase] = {
            "count": cnt,
            "steps": round(_trimmed_mean(data["steps"]), 1),
            "steps_std": round(_std_dev(data["steps"]), 1),
            "time": round(_trimmed_mean(data["time"]), 2),
            "time_std": round(_std_dev(data["time"]), 2),
            "observation_time": round(_trimmed_mean(data["observation_time"]), 2),
            "observation_time_std": round(_std_dev(data["observation_time"]), 2),
            "stutter_count": round(_trimmed_mean(data["stutter_count"]), 1),
            "wasted_moves": round(_trimmed_mean(data["wasted_moves"]), 1),
            "tps": round(_trimmed_mean(data["tps"]), 1),
            "tps_std": round(_std_dev(data["tps"]), 1),
        }
    return result


def get_records_by_date(date_str: str = None, start_date: str = None, end_date: str = None) -> List[Dict]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    fields = "id, date, scramble, solution, total_time, bottom_color, analyzed, strength_tags, weakness_tags, total_steps, total_tps, processed_solve, oll_case, pll_case"
    if start_date and end_date:
        c.execute(
            f"SELECT {fields} FROM records WHERE user_id = ? AND date >= ? AND date <= ? ORDER BY date ASC",
            (uid, start_date, end_date + " 23:59:59")
        )
    elif date_str:
        c.execute(
            f"SELECT {fields} FROM records WHERE user_id = ? AND date LIKE ? ORDER BY date ASC",
            (uid, f"{date_str}%")
        )
    else:
        c.execute(
            f"SELECT {fields} FROM records WHERE user_id = ? ORDER BY date ASC",
            (uid,)
        )
    records = []
    for row in c.fetchall():
        records.append({
            "id": row[0], "date": row[1], "scramble": row[2],
            "solution": row[3], "total_time": row[4], "bottom_color": row[5],
            "analyzed": row[6], "strength_tags": row[7], "weakness_tags": row[8],
            "total_steps": row[9], "total_tps": row[10], "processed_solve": row[11],
            "oll_case": row[12], "pll_case": row[13]
        })
    conn.close()
    return records


def get_record_detail(record_id: int) -> Optional[Dict]:
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, date, scramble, solution, total_time, bottom_color, analyzed, strength_tags, weakness_tags, oll_case, pll_case, total_steps, total_tps "
        "FROM records WHERE id = ?",
        (record_id,)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    record = {
        "id": row[0], "date": row[1], "scramble": row[2],
        "solution": row[3], "total_time": row[4], "bottom_color": row[5],
        "analyzed": row[6], "strength_tags": row[7], "weakness_tags": row[8],
        "oll_case": row[9], "pll_case": row[10],
        "total_steps": row[11], "total_tps": row[12]
    }
    c.execute(
        "SELECT phase, steps, time, observation_time, stutter_count, wasted_moves, tps "
        "FROM phase_stats WHERE record_id = ?",
        (record_id,)
    )
    phase_stats = {}
    for prow in c.fetchall():
        phase_stats[prow[0]] = {
            "steps": prow[1], "time": prow[2], "observation_time": prow[3],
            "stutter_count": prow[4], "wasted_moves": prow[5], "tps": prow[6]
        }
    record["phase_stats"] = phase_stats
    conn.close()
    return record


def get_available_dates() -> List[str]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute(
        "SELECT DISTINCT SUBSTR(date, 1, 10) as d FROM records "
        "WHERE user_id = ? ORDER BY d DESC",
        (uid,)
    )
    dates = [row[0] for row in c.fetchall()]
    conn.close()
    return dates


def get_all_averages_by_period() -> Dict[str, Dict[str, Dict[str, float]]]:
    result = {}
    periods = [
        ("近7天", 7), ("近30天", 30), ("近1年", 365), ("全部", None)
    ]
    for label, days in periods:
        avg = get_averages(days)
        if avg:
            total_count = max(v["count"] for v in avg.values()) if avg else 0
            if total_count >= 3 or days is None:
                result[label] = avg
    return result


def get_total_time_avg(days: Optional[int] = None, analyzed_only: bool = True, limit: int = 1000) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    analyzed_cond = " AND analyzed = 1" if analyzed_only else ""
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"SELECT total_time FROM records WHERE user_id = ? AND date >= ?{analyzed_cond} ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute(f"SELECT total_time FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute(f"SELECT total_time FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC", (uid,))
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values:
        return None
    return round(_trimmed_mean(values), 2)


def get_total_time_std(days: Optional[int] = None, analyzed_only: bool = True, limit: int = 1000) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    analyzed_cond = " AND analyzed = 1" if analyzed_only else ""
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"SELECT total_time FROM records WHERE user_id = ? AND date >= ?{analyzed_cond} ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute(f"SELECT total_time FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute(f"SELECT total_time FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC", (uid,))
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values or len(values) < 2:
        return None
    return round(_std_dev(values), 2)


def get_pb() -> Optional[dict]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT MIN(total_time), date FROM records WHERE user_id = ?", (uid,))
    row = c.fetchone()
    conn.close()
    if row and row[0] is not None:
        return {"time": round(row[0], 2), "date": row[1][:10] if row[1] else ""}
    return None


def get_total_tps_avg(days: Optional[int] = None, analyzed_only: bool = True, limit: int = 1000) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    analyzed_cond = " AND analyzed = 1" if analyzed_only else ""
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"SELECT total_tps FROM records WHERE user_id = ? AND date >= ?{analyzed_cond} ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute(f"SELECT total_tps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute(f"SELECT total_tps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC", (uid,))
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values:
        return None
    return round(_trimmed_mean(values), 2)


def get_total_tps_std(days: Optional[int] = None, analyzed_only: bool = True, limit: int = 1000) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    analyzed_cond = " AND analyzed = 1" if analyzed_only else ""
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"SELECT total_tps FROM records WHERE user_id = ? AND date >= ?{analyzed_cond} ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute(f"SELECT total_tps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute(f"SELECT total_tps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC", (uid,))
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values or len(values) < 2:
        return None
    return round(_std_dev(values), 2)


def get_total_steps_avg(days: Optional[int] = None, analyzed_only: bool = True, limit: int = 1000) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    analyzed_cond = " AND analyzed = 1" if analyzed_only else ""
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(f"SELECT total_steps FROM records WHERE user_id = ? AND date >= ?{analyzed_cond} ORDER BY date DESC",
                  (uid, since))
    else:
        if limit is not None:
            c.execute(f"SELECT total_steps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC LIMIT ?", (uid, limit))
        else:
            c.execute(f"SELECT total_steps FROM records WHERE user_id = ?{analyzed_cond} ORDER BY date DESC", (uid,))
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values:
        return None
    return round(_trimmed_mean(values), 1)


def get_record_count_by_period(days: Optional[int] = None) -> int:
    """获取指定时段内的记录数（所有记录，不限是否分析）"""
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT COUNT(*) FROM records WHERE user_id = ? AND date >= ?",
                  (uid, since))
    else:
        c.execute("SELECT COUNT(*) FROM records WHERE user_id = ?", (uid,))
    count = c.fetchone()[0]
    conn.close()
    return count


def find_record_id(scramble: str, solution: str, total_time: float) -> Optional[int]:
    """根据打乱公式、还原步骤和总用时查找已有记录ID"""
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute(
        "SELECT id FROM records WHERE user_id = ? AND scramble = ? AND solution = ? AND ABS(total_time - ?) < 0.01 LIMIT 1",
        (uid, scramble, solution, total_time)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def update_record_tags(record_id: int, strength_tags: list, weakness_tags: list):
    """更新记录的优缺点标签，并标记为已分析"""
    conn = _get_conn()
    c = conn.cursor()
    s_str = ",".join(strength_tags) if strength_tags else ""
    w_str = ",".join(weakness_tags) if weakness_tags else ""
    c.execute("UPDATE records SET analyzed = 1, strength_tags = ?, weakness_tags = ? WHERE id = ?",
              (s_str, w_str, record_id))
    conn.commit()
    conn.close()


def update_oll_pll_case(record_id: int, oll_case: str, pll_case: str):
    """更新记录的OLL/PLL识别结果"""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("UPDATE records SET oll_case = ?, pll_case = ? WHERE id = ?",
              (oll_case, pll_case, record_id))
    conn.commit()
    conn.close()


def recalculate_all_records(progress_cb=None) -> dict:
    """根据打乱公式和原始还原数据，重新计算并更新所有记录的计算字段

    更新内容：bottom_color, total_steps, total_tps, processed_solve, phase_stats

    Args:
        progress_cb: 进度回调函数 callback(current, total)

    Returns:
        {"total": 总数, "updated": 成功数, "failed": 失败数}
    """
    from analyzer import CFOPAnalyzer, set_logger as a_set_logger, PHASE_ORDER
    import logging

    a_set_logger(logging.getLogger('memory_db'))

    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT id, scramble, solution, total_time FROM records WHERE user_id = ?", (uid,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {"total": 0, "updated": 0, "failed": 0}

    total = len(rows)
    updated = 0
    failed = 0

    for idx, (record_id, scramble, solution, total_time) in enumerate(rows):
        if progress_cb:
            progress_cb(idx, total)

        try:
            bottom_color, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)
            stats = analyzer.get_phase_stats()
            bottom_color_name = COLOR_NAMES.get(bottom_color, "白")
            total_steps = sum(s.get("steps", 0) for s in stats.values())
            total_tps = total_steps / total_time if total_time > 0 else 0
            processed_solve = analyzer.generate_processed_solve()
            oll_case, pll_case = analyzer.identify_oll_pll()

            conn = _get_conn()
            c2 = conn.cursor()
            c2.execute(
                "UPDATE records SET bottom_color=?, total_steps=?, total_tps=?, processed_solve=?, oll_case=?, pll_case=? WHERE id=?",
                (bottom_color_name, total_steps, total_tps, processed_solve, oll_case, pll_case, record_id)
            )
            # 删除旧的phase_stats并重新插入
            c2.execute("DELETE FROM phase_stats WHERE record_id=?", (record_id,))
            for phase in PHASE_ORDER:
                if phase in stats:
                    s = stats[phase]
                    c2.execute(
                        "INSERT INTO phase_stats (record_id, phase, steps, time, observation_time, stutter_count, wasted_moves, tps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (record_id, phase,
                         s.get("steps", 0), s.get("time", 0),
                         s.get("observation_time", 0), s.get("stutter_count", 0),
                         s.get("wasted_moves", 0), s.get("tps", 0))
                    )
            conn.commit()
            conn.close()
            updated += 1
        except Exception:
            failed += 1

    if progress_cb:
        progress_cb(total, total)

    return {"total": total, "updated": updated, "failed": failed}


def backfill_processed_solve():
    """为现有记录回填processed_solve字段"""
    from analyzer import CFOPAnalyzer, set_logger
    import logging

    set_logger(logging.getLogger('memory_db'))

    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id, scramble, solution, bottom_color FROM records WHERE processed_solve = '' OR processed_solve IS NULL")
    rows = c.fetchall()
    if not rows:
        conn.close()
        return 0

    updated = 0
    for row in rows:
        record_id, scramble, solution, bottom_color = row
        try:
            if bottom_color:
                from config import COLOR_CODES
                bc = COLOR_CODES.get(bottom_color, bottom_color)
                if bc and len(bc) <= 1:
                    analyzer = CFOPAnalyzer.from_bottom_color(scramble, solution, bc)
                else:
                    _, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)
            else:
                _, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)

            processed = analyzer.generate_processed_solve()
            if processed:
                c.execute("UPDATE records SET processed_solve = ? WHERE id = ?", (processed, record_id))
                updated += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    return updated


def get_tag_stats() -> dict:
    """获取优缺点标签的出现次数统计"""
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT strength_tags, weakness_tags FROM records WHERE user_id = ? AND analyzed = 1", (uid,))

    strength_count = {}
    weakness_count = {}
    for row in c.fetchall():
        if row[0]:
            for tag in row[0].split(","):
                tag = tag.strip()
                if tag:
                    strength_count[tag] = strength_count.get(tag, 0) + 1
        if row[1]:
            for tag in row[1].split(","):
                tag = tag.strip()
                if tag:
                    weakness_count[tag] = weakness_count.get(tag, 0) + 1
    conn.close()

    # 按次数降序排列，取TOP3
    top_strengths = sorted(strength_count.items(), key=lambda x: x[1], reverse=True)[:3]
    top_weaknesses = sorted(weakness_count.items(), key=lambda x: x[1], reverse=True)[:3]
    return {"top_strengths": top_strengths, "top_weaknesses": top_weaknesses}


def delete_records(record_ids: List[int]) -> int:
    if not record_ids:
        return 0
    conn = _get_conn()
    c = conn.cursor()
    placeholders = ",".join("?" * len(record_ids))
    c.execute(f"DELETE FROM phase_stats WHERE record_id IN ({placeholders})", record_ids)
    c.execute(f"DELETE FROM records WHERE id IN ({placeholders})", record_ids)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def clear_all():
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT id FROM records WHERE user_id = ?", (uid,))
    record_ids = [row[0] for row in c.fetchall()]
    if record_ids:
        placeholders = ",".join("?" * len(record_ids))
        c.execute(f"DELETE FROM phase_stats WHERE record_id IN ({placeholders})", record_ids)
    c.execute("DELETE FROM records WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()


def export_csv(path: str) -> int:
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("""
        SELECT r.date, r.scramble, r.solution, r.total_time, r.bottom_color,
               p.phase, p.steps, p.time, p.observation_time,
               p.stutter_count, p.wasted_moves, p.tps
        FROM records r
        LEFT JOIN phase_stats p ON r.id = p.record_id
        WHERE r.user_id = ?
        ORDER BY r.date, p.phase
    """, (uid,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return 0

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "日期", "打乱公式", "还原步骤", "总时间(s)", "底色",
            "阶段", "步数", "用时(s)", "观察时间(s)",
            "卡顿次数", "废步数量", "TPS"
        ])
        for row in rows:
            writer.writerow(row)

    return len(rows)


def _is_cross_pre_solved(scramble: str) -> bool:
    from cube import Cube
    from move_utils import parse_moves

    cube = Cube()
    for move in parse_moves(scramble):
        cube.apply_standard_move(move)

    face_edges = {
        'U': [0, 1, 2, 3],
        'D': [4, 5, 6, 7],
        'F': [1, 5, 8, 9],
        'B': [3, 7, 10, 11],
        'L': [2, 6, 9, 10],
        'R': [0, 4, 8, 11]
    }
    for face, edge_indices in face_edges.items():
        all_solved = all(
            cube.ep[i] == i and cube.eo[i] == 0
            for i in edge_indices
        )
        if all_solved:
            return True
    return False


def import_csv(file_path: str, progress_cb=None) -> dict:
    from analyzer import CFOPAnalyzer, set_logger as a_set_logger, PHASE_ORDER

    results = {"total": 0, "imported": 0, "skipped_no_review": 0, "skipped_parse_error": 0,
               "skipped_duplicate": 0, "skipped_incomplete": 0, "skipped_abnormal": 0,
               "skipped_cross_solved": 0}

    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT scramble, solution, total_time FROM records WHERE user_id = ?", (uid,))
    existing_keys = set((row[0], row[1], row[2]) for row in c.fetchall())

    c.execute("SELECT total_time FROM records WHERE user_id = ?", (uid,))
    all_times = [row[0] for row in c.fetchall() if row[0] is not None]
    db_count = len(all_times)
    db_avg_time = _trimmed_mean(all_times) if db_count > 0 else None

    # 读取CSV并按还原分组
    groups = {}
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("日期", "").strip()
            scramble = row.get("打乱公式", "").strip()
            solution = row.get("还原步骤", "").strip()
            total_time_str = row.get("总时间(s)", "").strip()
            bottom_color = row.get("底色", "").strip()
            phase = row.get("阶段", "").strip()

            key = (date, scramble, solution)
            if key not in groups:
                try:
                    total_time = float(total_time_str)
                except (ValueError, TypeError):
                    results["skipped_parse_error"] += 1
                    continue
                groups[key] = {
                    "date": date, "scramble": scramble, "solution": solution,
                    "total_time": total_time, "bottom_color": bottom_color,
                    "phases": {}
                }
            if phase:
                try:
                    groups[key]["phases"][phase] = {
                        "steps": int(float(row.get("步数", 0))),
                        "time": float(row.get("用时(s)", 0)),
                        "observation_time": float(row.get("观察时间(s)", 0)),
                        "stutter_count": int(float(row.get("卡顿次数", 0))),
                        "wasted_moves": int(float(row.get("废步数量", 0))),
                        "tps": float(row.get("TPS", 0)),
                    }
                except (ValueError, TypeError):
                    pass

    group_list = list(groups.values())
    results["total"] = len(group_list)

    for idx, g in enumerate(group_list):
        if progress_cb and idx % 10 == 0:
            progress_cb(idx, len(group_list))

        try:
            scramble = g["scramble"]
            solution = g["solution"]
            total_time = g["total_time"]

            # 去重检查
            if (scramble, solution, total_time) in existing_keys:
                results["skipped_duplicate"] += 1
                continue

            # 无还原步骤
            if not solution or "@" not in solution:
                results["skipped_no_review"] += 1
                continue

            # Cross预还原检测
            if scramble and _is_cross_pre_solved(scramble):
                results["skipped_cross_solved"] += 1
                continue

            # 重新分析验证合理性
            try:
                bottom_color, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)
                phase_result = analyzer.analyze()
            except Exception:
                results["skipped_parse_error"] += 1
                continue

            if not phase_result or all(len(v) == 0 for v in phase_result.values()):
                results["skipped_parse_error"] += 1
                continue

            if not analyzer.is_solve_complete():
                results["skipped_incomplete"] += 1
                continue

            # 异常时间检测
            if db_count >= 100 and db_avg_time and total_time > db_avg_time * 2:
                results["skipped_abnormal"] += 1
                continue

            # 使用重新分析的结果（而非CSV中的阶段数据，确保一致性）
            stats = analyzer.get_phase_stats()
            bottom_color_name = COLOR_NAMES.get(bottom_color, "白")
            total_steps = sum(s.get("steps", 0) for s in stats.values())
            total_tps = total_steps / total_time if total_time > 0 else 0
            processed_solve = analyzer.generate_processed_solve()
            oll_case, pll_case = analyzer.identify_oll_pll()

            c.execute(
                "INSERT INTO records (user_id, date, scramble, solution, total_time, bottom_color, total_steps, total_tps, processed_solve, oll_case, pll_case) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, g["date"], scramble, solution, total_time, bottom_color_name, total_steps, total_tps, processed_solve, oll_case, pll_case)
            )
            record_id = c.lastrowid
            for phase in PHASE_ORDER:
                if phase in stats:
                    s = stats[phase]
                    c.execute(
                        "INSERT INTO phase_stats (record_id, phase, steps, time, observation_time, stutter_count, wasted_moves, tps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (record_id, phase,
                         s.get("steps", 0), s.get("time", 0),
                         s.get("observation_time", 0), s.get("stutter_count", 0),
                         s.get("wasted_moves", 0), s.get("tps", 0))
                    )
            existing_keys.add((scramble, solution, total_time))
            results["imported"] += 1
        except Exception:
            results["skipped_parse_error"] += 1

    conn.commit()
    conn.close()

    if progress_cb:
        progress_cb(len(group_list), len(group_list))

    return results


def import_cstimer(file_path: str, progress_cb=None) -> dict:
    import json
    from analyzer import CFOPAnalyzer, set_logger as a_set_logger, PHASE_ORDER, AI_PAUSE_THRESHOLD_SEC

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = {"total": 0, "imported": 0, "skipped_no_review": 0, "skipped_parse_error": 0, "skipped_duplicate": 0, "skipped_incomplete": 0, "skipped_abnormal": 0, "skipped_cross_solved": 0}

    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute("SELECT scramble FROM records WHERE user_id = ?", (uid,))
    existing_scrambles = set(row[0] for row in c.fetchall())

    c.execute("SELECT total_time FROM records WHERE user_id = ?", (uid,))
    all_times = [row[0] for row in c.fetchall() if row[0] is not None]
    db_count = len(all_times)
    db_avg_time = _trimmed_mean(all_times) if db_count > 0 else None

    records = []
    for key in data:
        if not key.startswith("session") or not isinstance(data[key], list):
            continue
        for rec in data[key]:
            if not isinstance(rec, list) or len(rec) < 5:
                continue
            records.append(rec)

    results["total"] = len(records)

    for idx, rec in enumerate(records):
        if progress_cb and idx % 10 == 0:
            progress_cb(idx, len(records))

        try:
            time_info = rec[0]
            scramble = rec[1] if len(rec) > 1 else ""
            if scramble and scramble in existing_scrambles:
                results["skipped_duplicate"] += 1
                continue

            if scramble and _is_cross_pre_solved(scramble):
                results["skipped_cross_solved"] += 1
                continue
            timestamp = rec[3] if len(rec) > 3 else 0
            review_data = rec[4] if len(rec) > 4 else []

            if not review_data or not isinstance(review_data, list) or len(review_data) == 0:
                results["skipped_no_review"] += 1
                continue

            review_str = review_data[0]
            if not review_str or "@" not in review_str:
                results["skipped_no_review"] += 1
                continue

            total_time_ms = time_info[1] if len(time_info) > 1 else 0
            total_time = total_time_ms / 1000.0

            try:
                bottom_color, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, review_str)
                phase_result = analyzer.analyze()
            except Exception:
                results["skipped_parse_error"] += 1
                continue

            if not phase_result or all(len(v) == 0 for v in phase_result.values()):
                results["skipped_parse_error"] += 1
                continue

            if not analyzer.is_solve_complete():
                results["skipped_incomplete"] += 1
                continue

            if db_count >= 100 and db_avg_time and total_time > db_avg_time * 2:
                results["skipped_abnormal"] += 1
                continue

            stats = analyzer.get_phase_stats()
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else ""

            bottom_color_name = COLOR_NAMES.get(bottom_color, "白")
            total_steps = sum(s.get("steps", 0) for s in stats.values())
            total_tps = total_steps / total_time if total_time > 0 else 0
            processed_solve = analyzer.generate_processed_solve()
            oll_case, pll_case = analyzer.identify_oll_pll()
            c.execute(
                "INSERT INTO records (user_id, date, scramble, solution, total_time, bottom_color, total_steps, total_tps, processed_solve, oll_case, pll_case) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, date_str, scramble, review_str, total_time, bottom_color_name, total_steps, total_tps, processed_solve, oll_case, pll_case)
            )
            record_id = c.lastrowid
            for phase in PHASE_ORDER:
                if phase in stats:
                    s = stats[phase]
                    c.execute(
                        "INSERT INTO phase_stats (record_id, phase, steps, time, observation_time, stutter_count, wasted_moves, tps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (record_id, phase,
                         s.get("steps", 0), s.get("time", 0),
                         s.get("observation_time", 0), s.get("stutter_count", 0),
                         s.get("wasted_moves", 0), s.get("tps", 0))
                    )
            existing_scrambles.add(scramble)
            results["imported"] += 1
        except Exception:
            results["skipped_parse_error"] += 1

    conn.commit()
    conn.close()

    if progress_cb:
        progress_cb(len(records), len(records))

    return results


def get_oll_pll_stats() -> dict:
    """获取OLL和PLL各状态的出现次数、平均步数、平均用时、平均TPS、平均识别时间、步数标准差、用时标准差

    统计的是OLL/PLL阶段本身的步数、用时、TPS、观察时间（来自phase_stats表），
    而非整体还原的total_steps/total_time/total_tps。

    Returns:
        {
            "oll": { "1": {"count": N, "avg_steps": X, "avg_time": Y, "avg_tps": Z,
                           "avg_obs_time": W, "std_steps": S1, "std_time": S2}, ... },
            "pll": { "Aa": {"count": N, ...}, ... }
        }
    """
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0

    result = {"oll": {}, "pll": {}}

    # OLL统计 - 关联phase_stats获取OLL阶段的步数/用时/TPS/观察时间
    c.execute(
        "SELECT r.oll_case, p.steps, p.time, p.tps, p.observation_time "
        "FROM records r "
        "JOIN phase_stats p ON r.id = p.record_id AND p.phase = 'oll' "
        "WHERE r.user_id = ? AND r.oll_case != '' AND r.oll_case IS NOT NULL",
        (uid,)
    )
    oll_data = {}
    for row in c.fetchall():
        case = row[0]
        if case not in oll_data:
            oll_data[case] = {"steps": [], "time": [], "tps": [], "obs_time": []}
        oll_data[case]["steps"].append(row[1])
        oll_data[case]["time"].append(row[2])
        oll_data[case]["tps"].append(row[3])
        oll_data[case]["obs_time"].append(row[4])

    for case, d in sorted(oll_data.items(), key=lambda x: len(x[1]["steps"]), reverse=True):
        cnt = len(d["steps"])
        result["oll"][case] = {
            "count": cnt,
            "avg_steps": round(_trimmed_mean(d["steps"]), 1),
            "avg_time": round(_trimmed_mean(d["time"]), 2),
            "avg_tps": round(_trimmed_mean(d["tps"]), 1),
            "avg_obs_time": round(_trimmed_mean(d["obs_time"]), 2),
            "std_steps": round(_std_dev(d["steps"]), 1),
            "std_time": round(_std_dev(d["time"]), 2),
        }

    # PLL统计 - 关联phase_stats获取PLL阶段的步数/用时/TPS/观察时间
    c.execute(
        "SELECT r.pll_case, p.steps, p.time, p.tps, p.observation_time "
        "FROM records r "
        "JOIN phase_stats p ON r.id = p.record_id AND p.phase = 'pll' "
        "WHERE r.user_id = ? AND r.pll_case != '' AND r.pll_case IS NOT NULL",
        (uid,)
    )
    pll_data = {}
    for row in c.fetchall():
        case = row[0]
        if case not in pll_data:
            pll_data[case] = {"steps": [], "time": [], "tps": [], "obs_time": []}
        pll_data[case]["steps"].append(row[1])
        pll_data[case]["time"].append(row[2])
        pll_data[case]["tps"].append(row[3])
        pll_data[case]["obs_time"].append(row[4])

    for case, d in sorted(pll_data.items(), key=lambda x: len(x[1]["steps"]), reverse=True):
        cnt = len(d["steps"])
        result["pll"][case] = {
            "count": cnt,
            "avg_steps": round(_trimmed_mean(d["steps"]), 1),
            "avg_time": round(_trimmed_mean(d["time"]), 2),
            "avg_tps": round(_trimmed_mean(d["tps"]), 1),
            "avg_obs_time": round(_trimmed_mean(d["obs_time"]), 2),
            "std_steps": round(_std_dev(d["steps"]), 1),
            "std_time": round(_std_dev(d["time"]), 2),
        }

    conn.close()
    return result


def get_today_records() -> List[Dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_conn()
    c = conn.cursor()
    uid = _current_user_id if _current_user_id else 0
    c.execute(
        "SELECT id, date, scramble, solution, total_time, bottom_color "
        "FROM records WHERE user_id = ? AND date LIKE ? ORDER BY date ASC",
        (uid, f"{today}%")
    )
    records = []
    for row in c.fetchall():
        records.append({
            "id": row[0], "date": row[1], "scramble": row[2],
            "solution": row[3], "total_time": row[4], "bottom_color": row[5]
        })
    conn.close()
    return records


def get_today_phase_stats(record_ids: List[int]) -> Dict[str, Dict]:
    if not record_ids:
        return {}
    conn = _get_conn()
    c = conn.cursor()
    placeholders = ",".join("?" * len(record_ids))
    c.execute(
        f"SELECT phase, steps, time, observation_time, stutter_count, wasted_moves, tps "
        f"FROM phase_stats WHERE record_id IN ({placeholders})",
        record_ids
    )
    phase_data = {}
    for row in c.fetchall():
        phase = row[0]
        if phase not in phase_data:
            phase_data[phase] = {"steps": [], "time": [], "observation_time": [],
                                 "stutter_count": [], "wasted_moves": [], "tps": []}
        phase_data[phase]["steps"].append(row[1])
        phase_data[phase]["time"].append(row[2])
        phase_data[phase]["observation_time"].append(row[3])
        phase_data[phase]["stutter_count"].append(row[4])
        phase_data[phase]["wasted_moves"].append(row[5])
        phase_data[phase]["tps"].append(row[6])
    conn.close()

    result = {}
    for phase, data in phase_data.items():
        cnt = len(data["steps"])
        result[phase] = {
            "count": cnt,
            "steps": round(_trimmed_mean(data["steps"]), 1),
            "steps_std": round(_std_dev(data["steps"]), 1),
            "time": round(_trimmed_mean(data["time"]), 2),
            "time_std": round(_std_dev(data["time"]), 2),
            "observation_time": round(_trimmed_mean(data["observation_time"]), 2),
            "observation_time_std": round(_std_dev(data["observation_time"]), 2),
            "stutter_count": round(_trimmed_mean(data["stutter_count"]), 1),
            "wasted_moves": round(_trimmed_mean(data["wasted_moves"]), 1),
            "tps": round(_trimmed_mean(data["tps"]), 1),
            "tps_std": round(_std_dev(data["tps"]), 1),
        }
    return result
