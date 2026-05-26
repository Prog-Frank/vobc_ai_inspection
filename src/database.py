"""
SQLite 案例库管理
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime


DB_DIR = Path(__file__).parent.parent / "database"
DB_PATH = DB_DIR / "cases.db"


def _get_conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fault_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            system TEXT NOT NULL,
            serial_no TEXT DEFAULT '',
            fault_reason TEXT DEFAULT '',
            fault_phenomenon TEXT DEFAULT '',
            handling TEXT DEFAULT '',
            train_no TEXT DEFAULT '',
            event_time TEXT DEFAULT '',
            raw_log TEXT NOT NULL,
            UNIQUE(system, serial_no, event_time)
        );

        CREATE TABLE IF NOT EXISTS fault_case_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES fault_cases(id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            field_value TEXT DEFAULT '',
            is_fault_field INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_case_fields_name_value
            ON fault_case_fields(field_name, field_value);

        CREATE INDEX IF NOT EXISTS idx_cases_system
            ON fault_cases(system);
    """)
    conn.commit()


# ============================================================
# 案例 CRUD
# ============================================================
def create_case(system: str, serial_no: str, fault_reason: str,
                fault_phenomenon: str, handling: str, train_no: str,
                event_time: str, raw_log: str,
                fields: list[dict]) -> int:
    """
    创建案例。
    fields: [{"name": "字段名", "value": "值", "is_fault": 1/0}, ...]
    """
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO fault_cases
               (created_at, system, serial_no, fault_reason, fault_phenomenon,
                handling, train_no, event_time, raw_log)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             system, serial_no, fault_reason, fault_phenomenon,
             handling, train_no, event_time, raw_log)
        )
        if cursor.lastrowid == 0:
            # 已存在，获取已有 id
            row = conn.execute(
                "SELECT id FROM fault_cases WHERE system=? AND serial_no=? AND event_time=?",
                (system, serial_no, event_time)
            ).fetchone()
            return row["id"] if row else 0

        case_id = cursor.lastrowid

        # 插入字段详情
        for f in fields:
            conn.execute(
                """INSERT INTO fault_case_fields (case_id, field_name, field_value, is_fault_field)
                   VALUES (?, ?, ?, ?)""",
                (case_id, f["name"], f.get("value", ""), 1 if f.get("is_fault") else 0)
            )
        conn.commit()
        return case_id
    finally:
        conn.close()


def list_cases(page: int = 1, size: int = 20, system: str = "",
               keyword: str = "") -> dict:
    """分页查询案例列表"""
    conn = _get_conn()
    try:
        where, params = [], []
        if system:
            where.append("system = ?")
            params.append(system)
        if keyword:
            where.append("(fault_reason LIKE ? OR fault_phenomenon LIKE ? OR handling LIKE ?)")
            params.extend([f"%{keyword}%"] * 3)

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(f"SELECT COUNT(*) FROM fault_cases{clause}", params).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, created_at, system, serial_no, fault_reason,
                       fault_phenomenon, handling, train_no, event_time
                FROM fault_cases{clause}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params + [size, (page - 1) * size]
        ).fetchall()

        return {
            "total": total,
            "page": page,
            "cases": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def get_case(case_id: int) -> dict | None:
    """获取案例详情（含字段详情）"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM fault_cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        case = dict(row)

        fields = conn.execute(
            "SELECT field_name, field_value, is_fault_field FROM fault_case_fields WHERE case_id = ?",
            (case_id,)
        ).fetchall()
        case["fields"] = [dict(f) for f in fields]
        return case
    finally:
        conn.close()


def delete_case(case_id: int) -> bool:
    """删除案例"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM fault_cases WHERE id = ?", (case_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def match_cases(system: str, field_values: dict) -> list[dict]:
    """
    精确匹配：按系统 + 字段名/字段值匹配已有案例。
    返回匹配的案例列表（按匹配度排序）。
    """
    conn = _get_conn()
    try:
        # 先按系统筛选
        rows = conn.execute(
            """SELECT fc.id, fc.created_at, fc.system, fc.serial_no,
                      fc.fault_reason, fc.fault_phenomenon, fc.handling,
                      fc.train_no, fc.event_time
               FROM fault_cases fc
               WHERE fc.system = ?
               ORDER BY fc.id DESC""",
            (system,)
        ).fetchall()

        if not rows:
            return []

        # 获取所有候选案例的字段
        case_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(case_ids))
        field_rows = conn.execute(
            f"""SELECT case_id, field_name, field_value, is_fault_field
                FROM fault_case_fields
                WHERE case_id IN ({placeholders})""",
            case_ids
        ).fetchall()

        # 按案例分组字段
        case_fields = {}
        for fr in field_rows:
            cid = fr["case_id"]
            if cid not in case_fields:
                case_fields[cid] = {}
            case_fields[cid][fr["field_name"]] = {
                "value": fr["field_value"],
                "is_fault": fr["is_fault_field"],
            }

        # 计算匹配度
        matches = []
        for row in rows:
            cid = row["id"]
            cf = case_fields.get(cid, {})

            if not field_values:
                # 没有指定匹配条件，返回所有
                matches.append({**dict(row), "score": 0.0, "matched_fields": []})
                continue

            matched = []
            for fname, fval in field_values.items():
                if fname in cf and cf[fname]["value"] == str(fval):
                    matched.append(fname)

            if matched:
                score = len(matched) / len(field_values)
                matches.append({
                    **dict(row),
                    "score": round(score, 2),
                    "matched_fields": matched,
                })

        matches.sort(key=lambda x: x.get("score", 0), reverse=True)
        return matches[:20]
    finally:
        conn.close()
