import sqlite3
import json
from datetime import datetime

DATABASE_NAME = 'instance/jobs.db'

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
            raw_job_data TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized and jobs table created (if it didn't exist).")

def save_job(job_data):
    """Saves a single job listing to the database.
    Handles duplicates based on the URL.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Prepare data for insertion
    # Ensure all expected keys are present, providing defaults if necessary
    # and converting raw_job_data to JSON string.
    data_to_insert = (
        job_data.get('title'),
        job_data.get('company'),
        job_data.get('location'),
        job_data.get('description'),
        job_data.get('url'),
        job_data.get('source'),
        datetime.now(),  # date_scraped
        json.dumps(job_data.get('raw_job_data', job_data)) # Store the whole job_data if raw_job_data specific key is not present
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

    base_query = "SELECT id, title, company, location, description, url, source, date_scraped FROM jobs"
    where_clauses = []
    params = []

    if filters:
        keyword = filters.get('keyword')
        location = filters.get('location')
        source = filters.get('source')
        # title_keyword = filters.get('title_keyword') # More specific if needed
        # description_keyword = filters.get('description_keyword') # More specific if needed

        if keyword:
            # Search keyword in both title and description
            where_clauses.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        if location:
            where_clauses.append("location LIKE ?")
            params.append(f"%{location}%")

        if source:
            where_clauses.append("source = ?") # Exact match for source
            params.append(source)

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
