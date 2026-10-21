# app/database.py
import json
import logging
import os
import sqlite3
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Absolute path so the app works no matter which directory it is started from.
# create_app() overrides this with the Flask instance path (and tests monkeypatch it).
DATABASE_NAME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "jobs.db")


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable for JSON")


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initializes the database and creates tables if they don't exist."""
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_NAME)), exist_ok=True)
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                description TEXT,
                url TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                date_scraped TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                raw_job_data TEXT,
                applied INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS generated_cvs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                cv_filename TEXT NOT NULL,
                tailored_cv_json TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_cvs_job_id ON generated_cvs (job_id);")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS applicant_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_at TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                url TEXT NOT NULL,
                cv_filename TEXT,
                status TEXT NOT NULL,
                message TEXT,
                ats TEXT,
                auto_submit INTEGER NOT NULL DEFAULT 0,
                model TEXT,
                log TEXT NOT NULL DEFAULT '[]',
                fields TEXT NOT NULL DEFAULT '[]',
                screenshot TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications (job_id);")

        # Simple migration for databases created before the 'applied' column existed.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "applied" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN applied INTEGER NOT NULL DEFAULT 0;")
            logger.info("Column 'applied' added to 'jobs' table.")
        conn.commit()
    finally:
        conn.close()
    logger.info("Database initialized at %s", DATABASE_NAME)


def save_job(job_data):
    """Saves a single job listing to the database. Duplicate URLs are ignored.
    Returns the new row id, or None if the job already existed or could not be saved.
    """
    data_to_serialize = job_data.get('raw_job_data', job_data)
    try:
        raw_job_json_string = json.dumps(data_to_serialize, default=json_serial)
    except (TypeError, ValueError) as e:
        logger.warning("Error serializing raw_job_data for %s: %s", job_data.get('url'), e)
        raw_job_json_string = json.dumps({"error": "raw_job_data serialization failed", "details": str(e)})

    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO jobs (title, company, location, description, url, source, date_scraped, raw_job_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO NOTHING
        ''', (
            job_data.get('title') or 'Untitled role',
            job_data.get('company'),
            job_data.get('location'),
            job_data.get('description'),
            job_data.get('url'),
            job_data.get('source'),
            datetime.now(),
            raw_job_json_string,
        ))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info("Job saved: %s at %s", job_data.get('title'), job_data.get('company'))
            return cursor.lastrowid
        logger.info("Job already exists: %s at %s", job_data.get('title'), job_data.get('company'))
        return None
    except sqlite3.Error as e:
        logger.error("Database error while saving job %s: %s", job_data.get('url'), e)
        return None
    finally:
        conn.close()


def toggle_applied_status(job_id: int) -> dict | None:
    """Toggles the 'applied' status of a job.

    Returns {"id": job_id, "applied": new_status}, or None if the job doesn't exist.
    Raises sqlite3.Error for database errors.
    """
    conn = get_db_connection()
    try:
        job = conn.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            return None
        new_status = 1 - job['applied']
        conn.execute("UPDATE jobs SET applied = ? WHERE id = ?", (new_status, job_id))
        conn.commit()
        return {"id": job_id, "applied": new_status}
    except sqlite3.Error as e:
        logger.error("Database error toggling applied status for job %s: %s", job_id, e)
        raise
    finally:
        conn.close()


def save_generated_cv(job_id: int, cv_filename: str, tailored_cv_json: str) -> int | None:
    """Saves a generated CV record for a job. Returns the new record id. Raises sqlite3.Error."""
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO generated_cvs (job_id, cv_filename, tailored_cv_json)
            VALUES (?, ?, ?)
        ''', (job_id, cv_filename, tailored_cv_json))
        conn.commit()
        logger.info("Generated CV for job ID %s saved: %s", job_id, cv_filename)
        return cursor.lastrowid
    finally:
        conn.close()


def get_generated_cv_by_job_id(job_id: int) -> dict | None:
    """Fetches the most recent generated CV record for a job."""
    conn = get_db_connection()
    try:
        row = conn.execute('''
            SELECT id, job_id, cv_filename, tailored_cv_json
            FROM generated_cvs
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 1
        ''', (job_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error("Database error while fetching generated CV for job ID %s: %s", job_id, e)
        return None
    finally:
        conn.close()


def job_url_exists(url: str) -> bool:
    """Checks if a job URL already exists in the database."""
    conn = get_db_connection()
    try:
        return conn.execute("SELECT 1 FROM jobs WHERE url = ? LIMIT 1", (url,)).fetchone() is not None
    except sqlite3.Error as e:
        logger.error("Database error while checking if URL exists %s: %s", url, e)
        return False
    finally:
        conn.close()


def get_job(job_id: int) -> dict | None:
    """Fetches one job (without raw data) by id."""
    conn = get_db_connection()
    try:
        row = conn.execute('''
            SELECT id, title, company, location, description, url, source, date_scraped, applied
            FROM jobs WHERE id = ?
        ''', (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_applied(job_id: int, applied: bool = True):
    """Sets (rather than toggles) a job's applied status."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE jobs SET applied = ? WHERE id = ?", (1 if applied else 0, job_id))
        conn.commit()
    finally:
        conn.close()


def get_job_apply_url(job_id: int) -> str | None:
    """The best URL to apply at: the employer's own page when the scraper found one, else the listing."""
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT url, raw_job_data FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        raw = json.loads(row["raw_job_data"] or "{}")
    except json.JSONDecodeError:
        raw = {}
    direct = raw.get("job_url_direct") if isinstance(raw, dict) else None
    return direct or row["url"]


def delete_job(job_id: int) -> bool:
    """Deletes a job and (via cascade) its generated CV records. Returns True if a row was deleted."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_jobs(filters=None):
    """Fetches jobs from the database based on provided filters.

    Supported filters: 'keyword' (title/company/description), 'location', 'source',
    'applied_status' ('applied' | 'not_applied' | 'all'). Each job includes the most
    recently generated CV (generated_cv_id, cv_filename), if any.
    """
    # Only join the latest generated CV per job, so a job with several CVs appears once.
    base_query = """
        SELECT j.id, j.title, j.company, j.location, j.description, j.url, j.source, j.date_scraped, j.applied,
               gc.id AS generated_cv_id, gc.cv_filename
        FROM jobs j
        LEFT JOIN generated_cvs gc
               ON gc.id = (SELECT MAX(id) FROM generated_cvs WHERE job_id = j.id)
    """
    where_clauses = []
    params = []

    filters = filters or {}
    keyword = filters.get('keyword')
    location = filters.get('location')
    source = filters.get('source')
    applied_status = filters.get('applied_status')

    if keyword:
        where_clauses.append("(j.title LIKE ? OR j.description LIKE ? OR j.company LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    if location:
        where_clauses.append("j.location LIKE ?")
        params.append(f"%{location}%")
    if source:
        where_clauses.append("j.source = ?")
        params.append(source)
    if applied_status == 'applied':
        where_clauses.append("j.applied = 1")
    elif applied_status == 'not_applied':
        where_clauses.append("j.applied = 0")

    query = base_query
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"
    query += " ORDER BY j.date_scraped DESC, j.id DESC"

    conn = get_db_connection()
    try:
        return [dict(job) for job in conn.execute(query, params).fetchall()]
    except sqlite3.Error as e:
        logger.error("Database error while fetching jobs: %s", e)
        return []
    finally:
        conn.close()


def get_sources() -> list[str]:
    """Distinct job sources present in the database (for the filter dropdown)."""
    conn = get_db_connection()
    try:
        return [row[0] for row in conn.execute("SELECT DISTINCT source FROM jobs WHERE source IS NOT NULL ORDER BY source")]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
