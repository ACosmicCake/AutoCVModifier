import sqlite3
import json
from datetime import datetime, date # Ensure date is also imported

DATABASE_NAME = 'instance/jobs.db'

# Helper function for JSON serialization with date/datetime handling
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)): # Handles both datetime.datetime and datetime.date
        return obj.isoformat()
    # Add handling for other non-serializable types if necessary in the future
    # For example, if jobspy returns other complex types not handled by default.
    # However, be cautious about overly broad try-except blocks or stringifying unknown types.
    # It's often better to explicitly handle known non-serializable types.
    raise TypeError (f"Type {type(obj)} not serializable for JSON")

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    """Initializes the database and creates the jobs table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
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
    # Commit the CREATE TABLE statement
    conn.commit()

    # Attempt to add the 'applied' column if it doesn't exist (for existing databases)
    # This is a common pattern for simple schema migrations in SQLite.
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN applied INTEGER NOT NULL DEFAULT 0;")
        conn.commit() # Commit the ALTER TABLE statement
        print("Column 'applied' added to 'jobs' table or already existed with default.")
    except sqlite3.OperationalError as e:
        # Check if the error is "duplicate column name"
        if "duplicate column name: applied" in str(e).lower():
            print("Column 'applied' already exists in 'jobs' table.")
        else:
            # If it's a different OperationalError, re-raise it
            print(f"An unexpected SQLite OperationalError occurred: {e}")
            raise

    conn.close()
    print("Database initialized and jobs table schema updated (if necessary).")

def save_job(job_data):
    """Saves a single job listing to the database.
    Handles duplicates based on the URL.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Prepare data for insertion
    # Ensure all expected keys are present, providing defaults if necessary.

    # Serialize raw_job_data with custom date/datetime handler
    # The 'raw_job_data' key in job_data should ideally hold the original dict from scraper.
    # If not, the whole job_data is used as a fallback.
    data_to_serialize_for_raw_json = job_data.get('raw_job_data', job_data)
    try:
        # Use the json_serial helper as the default for json.dumps
        raw_job_json_string = json.dumps(data_to_serialize_for_raw_json, default=json_serial)
    except TypeError as e:
        # This catch block is a fallback if json_serial itself can't handle a type
        # and raises TypeError, or if another unexpected serialization issue occurs.
        print(f"Error serializing raw_job_data for job URL {job_data.get('url')}: {e}. Storing as basic JSON object.")
        # Store a minimal representation or an error marker.
        # Storing the original job_data might also fail if it contains the problematic type.
        # A simple placeholder indicating serialization failure:
        raw_job_json_string = json.dumps({"error": "raw_job_data serialization failed", "details": str(e)})


    data_to_insert = (
        job_data.get('title'),
        job_data.get('company'),
        job_data.get('location'),
        job_data.get('description'),
        job_data.get('url'),
        job_data.get('source'),
        datetime.now(),  # date_scraped is always set to current timestamp on save
        raw_job_json_string # Use the safely serialized string
    )

    try:
        cursor.execute('''
            INSERT INTO jobs (title, company, location, description, url, source, date_scraped, raw_job_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO NOTHING
        ''', data_to_insert)
        conn.commit()
        if cursor.rowcount > 0:
            print(f"Job saved: {job_data.get('title')} at {job_data.get('company')}")
        else:
            print(f"Job already exists (or error): {job_data.get('title')} at {job_data.get('company')}")
    except sqlite3.Error as e:
        print(f"Database error while saving job {job_data.get('url')}: {e}")
    finally:
        conn.close()

def get_job_by_id(job_id: int) -> dict | None:
    """Fetches a single job by its ID from the database.

    Args:
        job_id: The ID of the job to fetch.

    Returns:
        A dictionary containing the job details if found, otherwise None.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # Ensure all relevant columns are selected, including 'url'
    query = "SELECT id, title, company, location, description, url, source, date_scraped, applied, raw_job_data FROM jobs WHERE id = ?"
    try:
        cursor.execute(query, (job_id,))
        job = cursor.fetchone() # fetchone() returns a single Row object or None
        if job:
            return dict(job) # Convert Row object to dictionary
        return None
    except sqlite3.Error as e:
        print(f"Database error while fetching job by ID {job_id}: {e}")
        return None # Return None on error
    finally:
        if conn:
            conn.close()

def toggle_applied_status(job_id: int) -> dict | None:
    """Toggles the 'applied' status of a job (0 to 1 or 1 to 0).

    Args:
        job_id: The ID of the job to update.

    Returns:
        A dictionary containing the job_id and the new_status if successful,
        None if the job_id is not found.
    Raises:
        sqlite3.Error: For database related errors during the transaction.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch the current 'applied' status
        cursor.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()

        if job is None:
            conn.close()
            return None # Job not found

        current_status = job['applied']
        new_status = 1 - current_status # Toggle logic (0 becomes 1, 1 becomes 0)

        # Update the 'applied' status
        cursor.execute("UPDATE jobs SET applied = ? WHERE id = ?", (new_status, job_id))
        conn.commit()

        conn.close()
        return {"id": job_id, "applied": new_status}

    except sqlite3.Error as e:
        # Rollback in case of error if 'conn' was opened with a transaction context manager,
        # but here we are manually committing. If an error occurs before commit, nothing is saved.
        # If after commit (unlikely here for a simple update), it's already committed.
        # For more complex transactions, explicit rollback might be needed.
        print(f"Database error toggling applied status for job {job_id}: {e}")
        if conn: # Ensure connection exists before trying to close
            conn.close()
        raise # Re-raise the exception to be handled by the caller (API endpoint)

if __name__ == '__main__':
    # For testing or manual initialization
    init_db()
    # Example usage:
    # test_job = {
    #     'title': 'Software Engineer',
    #     'company': 'Tech Co',
    #     'location': 'Remote',
    #     'description': 'Develop amazing software.',
    #     'url': 'http://example.com/job/123',
    #     'source': 'example_source',
    #     'raw_job_data': {'detail': 'more details here'}
    # }
    # save_job(test_job)
    # test_job_2 = { # Duplicate URL
    #     'title': 'Software Engineer II',
    #     'company': 'Tech Co',
    #     'location': 'Remote',
    #     'description': 'Develop amazing software, now with more experience.',
    #     'url': 'http://example.com/job/123',
    #     'source': 'example_source_new',
    #     'raw_job_data': {'detail': 'even more details here'}
    # }
    # save_job(test_job_2)

def get_jobs(filters=None):
    """Fetches jobs from the database based on provided filters.

    Args:
        filters (dict, optional): A dictionary where keys are column names
                                  and values are the values to filter by.
                                  Special filter 'keyword' searches title and description.
                                  Defaults to None (fetch all jobs).

    Returns:
        list: A list of job dictionaries, or an empty list if no jobs found or error.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Update base_query to include the new 'applied' column
    base_query = "SELECT id, title, company, location, description, url, source, date_scraped, applied FROM jobs"
    where_clauses = []
    params = []

    if filters:
        keyword = filters.get('keyword')
        location = filters.get('location')
        source = filters.get('source')
        applied_status = filters.get('applied_status')

        if keyword:
            where_clauses.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        if location:
            where_clauses.append("location LIKE ?")
            params.append(f"%{location}%")

        if source:
            where_clauses.append("source = ?")
            params.append(source)

        if applied_status == 'applied':
            where_clauses.append("applied = 1")
        elif applied_status == 'not_applied':
            where_clauses.append("applied = 0")
        # If applied_status is 'all', None, or any other value, do not add a filter for 'applied' status

    if where_clauses:
        query = f"{base_query} WHERE {' AND '.join(where_clauses)}"
    else:
        query = base_query

    query += " ORDER BY date_scraped DESC" # Always order by most recent

    try:
        cursor.execute(query, params)
        jobs = cursor.fetchall() # fetchall() returns a list of Row objects
        # Convert Row objects to dictionaries
        jobs_list = [dict(job) for job in jobs]
        return jobs_list
    except sqlite3.Error as e:
        print(f"Database error while fetching jobs: {e}")
        return [] # Return empty list on error
    finally:
        conn.close()
