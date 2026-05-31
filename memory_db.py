"""
记忆数据库 - SQLite存储分析历史数据
"""

import sqlite3
import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import APP_DIR

DB_FILE = os.path.join(APP_DIR, "cfop_memory.db")

PHASE_FIELDS = ["steps", "time", "observation_time", "stutter_count", "wasted_moves", "tps"]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_stats_record ON phase_stats(record_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_stats_phase ON phase_stats(phase)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)")
    conn.commit()
    conn.close()


def save_record(scramble: str, solution: str, total_time: float,
                bottom_color: str, phase_stats: Dict) -> int:
    conn = _get_conn()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO records (date, scramble, solution, total_time, bottom_color) VALUES (?, ?, ?, ?, ?)",
        (now, scramble, solution, total_time, bottom_color)
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
    c.execute("SELECT COUNT(*) FROM records")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_date_range() -> str:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT MIN(date), MAX(date) FROM records")
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


def get_averages(days: Optional[int] = None) -> Dict[str, Dict[str, float]]:
    conn = _get_conn()
    c = conn.cursor()
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id FROM records WHERE date >= ?", (since,))
    else:
        c.execute("SELECT id FROM records")
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
            "time": round(_trimmed_mean(data["time"]), 2),
            "observation_time": round(_trimmed_mean(data["observation_time"]), 2),
            "stutter_count": round(_trimmed_mean(data["stutter_count"]), 1),
            "wasted_moves": round(_trimmed_mean(data["wasted_moves"]), 1),
            "tps": round(_trimmed_mean(data["tps"]), 1),
        }
    return result


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


def get_total_time_avg(days: Optional[int] = None) -> Optional[float]:
    conn = _get_conn()
    c = conn.cursor()
    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT total_time FROM records WHERE date >= ?", (since,))
    else:
        c.execute("SELECT total_time FROM records")
    values = [row[0] for row in c.fetchall() if row[0] is not None]
    conn.close()
    if not values:
        return None
    return round(_trimmed_mean(values), 2)


def get_pb() -> Optional[dict]:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT MIN(total_time), date FROM records")
    row = c.fetchone()
    conn.close()
    if row and row[0] is not None:
        return {"time": round(row[0], 2), "date": row[1][:10] if row[1] else ""}
    return None


def clear_all():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM phase_stats")
    c.execute("DELETE FROM records")
    conn.commit()
    conn.close()


def export_csv(path: str) -> int:
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT r.date, r.scramble, r.solution, r.total_time, r.bottom_color,
               p.phase, p.steps, p.time, p.observation_time,
               p.stutter_count, p.wasted_moves, p.tps
        FROM records r
        LEFT JOIN phase_stats p ON r.id = p.record_id
        ORDER BY r.date, p.phase
    """)
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


def import_cstimer(file_path: str, progress_cb=None) -> dict:
    import json
    from analyzer import CFOPAnalyzer, set_logger as a_set_logger, PHASE_ORDER, AI_PAUSE_THRESHOLD_SEC

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = {"total": 0, "imported": 0, "skipped_no_review": 0, "skipped_parse_error": 0, "skipped_duplicate": 0, "skipped_incomplete": 0, "skipped_abnormal": 0, "skipped_cross_solved": 0}

    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT scramble FROM records")
    existing_scrambles = set(row[0] for row in c.fetchall())

    c.execute("SELECT total_time FROM records")
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
                analyzer = CFOPAnalyzer.from_bottom_color(scramble, review_str, "W")
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

            c.execute(
                "INSERT INTO records (date, scramble, solution, total_time, bottom_color) VALUES (?, ?, ?, ?, ?)",
                (date_str, scramble, review_str, total_time, "白")
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
