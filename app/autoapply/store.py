# app/autoapply/store.py
"""Persistence for application attempts."""
import json
from datetime import datetime

from .. import database

# Lifecycle: queued -> running -> (needs_attention <-> running) -> ready_for_review -> submitted
#                                                              \-> submitted (auto-submit)
# Any state can end in failed or cancelled.
ACTIVE_STATUSES = ("queued", "running", "needs_attention", "ready_for_review")
FINAL_STATUSES = ("submitted", "failed", "cancelled")
MAX_LOG_ENTRIES = 300


def _row_to_dict(row) -> dict:
    app = dict(row)
    for key in ("log", "fields"):
        try:
            app[key] = json.loads(app.get(key) or "[]")
        except json.JSONDecodeError:
            app[key] = []
    app["auto_submit"] = bool(app.get("auto_submit"))
    return app


def create_application(job_id, url, cv_filename, auto_submit, model) -> int:
    conn = database.get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO applications (job_id, url, cv_filename, status, message, auto_submit, model, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', 'Waiting in queue', ?, ?, ?, ?)",
            (job_id, url, cv_filename, int(bool(auto_submit)), model, datetime.now(), datetime.now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_application(app_id: int) -> dict | None:
    conn = database.get_db_connection()
    try:
        row = conn.execute('''
            SELECT a.*, j.title AS job_title, j.company AS job_company
            FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
            WHERE a.id = ?
        ''', (app_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_applications(limit: int = 50) -> list[dict]:
    conn = database.get_db_connection()
    try:
        rows = conn.execute('''
            SELECT a.id, a.job_id, a.url, a.cv_filename, a.status, a.message, a.ats, a.auto_submit, a.model,
                   a.screenshot, a.created_at, a.updated_at, j.title AS job_title, j.company AS job_company
            FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
            ORDER BY a.id DESC LIMIT ?
        ''', (limit,)).fetchall()
        result = []
        for row in rows:
            app = dict(row)
            app["auto_submit"] = bool(app["auto_submit"])
            result.append(app)
        return result
    finally:
        conn.close()


def active_application_for_job(job_id: int) -> dict | None:
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            f"SELECT id, status FROM applications WHERE job_id = ? AND status IN ({','.join('?' * len(ACTIVE_STATUSES))}) "
            "ORDER BY id DESC LIMIT 1",
            (job_id, *ACTIVE_STATUSES),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_application(app_id: int, **fields):
    if not fields:
        return
    for key in ("log", "fields"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key][-MAX_LOG_ENTRIES:] if key == "log" else fields[key])
    fields["updated_at"] = datetime.now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    conn = database.get_db_connection()
    try:
        conn.execute(f"UPDATE applications SET {assignments} WHERE id = ?", (*fields.values(), app_id))
        conn.commit()
    finally:
        conn.close()


def count_applications_today() -> int:
    """Applications started today that weren't cancelled (counts toward the daily limit)."""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    conn = database.get_db_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM applications WHERE created_at >= ? AND status != 'cancelled'",
                            (start,)).fetchone()[0]
    finally:
        conn.close()


def mark_stale_applications():
    """Applications left active by a previous server run can't resume (their browser is gone)."""
    conn = database.get_db_connection()
    try:
        conn.execute(
            f"UPDATE applications SET status = 'failed', message = 'Interrupted: the server restarted.', updated_at = ? "
            f"WHERE status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
            (datetime.now(), *ACTIVE_STATUSES),
        )
        conn.commit()
    finally:
        conn.close()


def application_summaries_by_job() -> dict[int, dict]:
    """Latest application per job, for badges in the job list."""
    conn = database.get_db_connection()
    try:
        rows = conn.execute('''
            SELECT a.job_id, a.id, a.status FROM applications a
            WHERE a.id = (SELECT MAX(id) FROM applications WHERE job_id = a.job_id)
        ''').fetchall()
        return {row["job_id"]: {"id": row["id"], "status": row["status"]} for row in rows if row["job_id"] is not None}
    finally:
        conn.close()
