import pytest
import pytest
import sqlite3
import json
from app.database import save_job, get_jobs, get_db_connection, toggle_applied_status # Import toggle_applied_status
from datetime import datetime, date

# Sample job data for testing
SAMPLE_JOB_1 = {
    'title': 'Software Engineer',
    'company': 'TestCo',
    'location': 'Remote, USA',
    'description': 'Develop amazing software applications.',
    'url': 'http://example.com/job/swe1',
    'source': 'TestIndeed',
    'raw_job_data': {'id': 'swe1', 'details': 'More details here'}
}

SAMPLE_JOB_2 = {
    'title': 'Data Scientist',
    'company': 'AlphaOrg',
    'location': 'New York, NY',
    'description': 'Analyze complex datasets and build models.',
    'url': 'http://example.com/job/ds1',
    'source': 'TestLinkedIn',
    'raw_job_data': {'id': 'ds1', 'extra_field': 'value'}
}

SAMPLE_JOB_3 = {
    'title': 'Senior Software Engineer',
    'company': 'BetaCorp',
    'location': 'San Francisco, CA',
    'description': 'Lead development of new platform features. Python and SQL required.',
    'url': 'http://example.com/job/ssenior',
    'source': 'TestIndeed',
    'raw_job_data': {'id': 'ssenior', 'skills': ['python', 'sql']}
}


def test_save_new_job(test_db):
    """Test saving a completely new job."""
    save_job(SAMPLE_JOB_1)

    conn = get_db_connection() # Uses the patched DATABASE_NAME via test_db
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],))
    job_from_db = cursor.fetchone()
    conn.close()

    assert job_from_db is not None
    assert job_from_db['title'] == SAMPLE_JOB_1['title']
    assert job_from_db['company'] == SAMPLE_JOB_1['company']
    assert job_from_db['location'] == SAMPLE_JOB_1['location']
    assert job_from_db['description'] == SAMPLE_JOB_1['description']
    assert job_from_db['source'] == SAMPLE_JOB_1['source']
    assert json.loads(job_from_db['raw_job_data']) == SAMPLE_JOB_1['raw_job_data']
    assert 'date_scraped' in job_from_db and job_from_db['date_scraped'] is not None
    assert job_from_db['applied'] == 0 # Verify default applied status

def test_save_duplicate_job_url(test_db):
    """Test that saving a job with a duplicate URL is ignored (due to ON CONFLICT DO NOTHING)."""
    save_job(SAMPLE_JOB_1) # Save first time

    # Modify some details but keep URL same
    duplicate_job_data = SAMPLE_JOB_1.copy()
    duplicate_job_data['title'] = "Updated Software Engineer Title"
    duplicate_job_data['description'] = "Updated description"

    save_job(duplicate_job_data) # Attempt to save again

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],))
    count = cursor.fetchone()[0]

    cursor.execute("SELECT title FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],))
    title_in_db = cursor.fetchone()[0]
    conn.close()

    assert count == 1 # Should only be one record
    assert title_in_db == SAMPLE_JOB_1['title'] # Original title should persist

def test_get_all_jobs_no_filters(test_db):
    """Test fetching all jobs when no filters are applied."""
    save_job(SAMPLE_JOB_1)
    # Make date_scraped slightly different for ordering test later
    # This requires direct db interaction or modifying save_job for test purposes.
    # For simplicity, we'll assume save_job inserts with current time and test order by that.
    # To be more precise, one might insert with controlled timestamps.
    import time; time.sleep(0.01)
    save_job(SAMPLE_JOB_2)
    import time; time.sleep(0.01)
    save_job(SAMPLE_JOB_3)

    jobs = get_jobs()
    assert len(jobs) == 3
    # Check default order (date_scraped DESC)
    # Assuming SAMPLE_JOB_3 was last and thus most recent
    assert jobs[0]['url'] == SAMPLE_JOB_3['url']
    assert jobs[1]['url'] == SAMPLE_JOB_2['url']
    assert jobs[2]['url'] == SAMPLE_JOB_1['url']


def test_get_jobs_filter_by_keyword_in_title(test_db):
    save_job(SAMPLE_JOB_1) # title: Software Engineer
    save_job(SAMPLE_JOB_2) # title: Data Scientist
    save_job(SAMPLE_JOB_3) # title: Senior Software Engineer

    jobs = get_jobs(filters={'keyword': 'Software'})
    assert len(jobs) == 2
    urls = {job['url'] for job in jobs}
    assert SAMPLE_JOB_1['url'] in urls
    assert SAMPLE_JOB_3['url'] in urls

def test_get_jobs_filter_by_keyword_in_description(test_db):
    save_job(SAMPLE_JOB_1) # desc: Develop amazing software applications.
    save_job(SAMPLE_JOB_2) # desc: Analyze complex datasets and build models.
    save_job(SAMPLE_JOB_3) # desc: Lead development of new platform features. Python and SQL required.

    jobs = get_jobs(filters={'keyword': 'Python'})
    assert len(jobs) == 1
    assert jobs[0]['url'] == SAMPLE_JOB_3['url']

    jobs_platform = get_jobs(filters={'keyword': 'platform'})
    assert len(jobs_platform) == 1
    assert jobs_platform[0]['url'] == SAMPLE_JOB_3['url']

    jobs_applications = get_jobs(filters={'keyword': 'applications'})
    assert len(jobs_applications) == 1
    assert jobs_applications[0]['url'] == SAMPLE_JOB_1['url']


def test_get_jobs_filter_by_location(test_db):
    save_job(SAMPLE_JOB_1) # Remote, USA
    save_job(SAMPLE_JOB_2) # New York, NY
    save_job(SAMPLE_JOB_3) # San Francisco, CA

    jobs = get_jobs(filters={'location': 'New York'})
    assert len(jobs) == 1
    assert jobs[0]['url'] == SAMPLE_JOB_2['url']

    jobs_usa = get_jobs(filters={'location': 'USA'}) # Matches 'Remote, USA'
    assert len(jobs_usa) == 1
    assert jobs_usa[0]['url'] == SAMPLE_JOB_1['url']


def test_get_jobs_filter_by_source(test_db):
    save_job(SAMPLE_JOB_1) # TestIndeed
    save_job(SAMPLE_JOB_2) # TestLinkedIn
    save_job(SAMPLE_JOB_3) # TestIndeed

    jobs = get_jobs(filters={'source': 'TestLinkedIn'})
    assert len(jobs) == 1
    assert jobs[0]['url'] == SAMPLE_JOB_2['url']

    jobs_indeed = get_jobs(filters={'source': 'TestIndeed'})
    assert len(jobs_indeed) == 2
    urls = {job['url'] for job in jobs_indeed}
    assert SAMPLE_JOB_1['url'] in urls
    assert SAMPLE_JOB_3['url'] in urls


def test_get_jobs_combined_filters(test_db):
    save_job(SAMPLE_JOB_1) # Software Engineer, Remote, USA, TestIndeed
    save_job(SAMPLE_JOB_2) # Data Scientist, New York, NY, TestLinkedIn
    save_job(SAMPLE_JOB_3) # Senior Software Engineer, San Francisco, CA, TestIndeed. Desc: Python

    # Keyword "Software" and source "TestIndeed"
    filters1 = {'keyword': 'Software', 'source': 'TestIndeed'}
    jobs1 = get_jobs(filters=filters1)
    assert len(jobs1) == 2 # SAMPLE_JOB_1 and SAMPLE_JOB_3
    urls1 = {job['url'] for job in jobs1}
    assert SAMPLE_JOB_1['url'] in urls1
    assert SAMPLE_JOB_3['url'] in urls1

    # Keyword "Python" (in description) and location "San Francisco"
    filters2 = {'keyword': 'Python', 'location': 'Francisco'}
    jobs2 = get_jobs(filters=filters2)
    assert len(jobs2) == 1
    assert jobs2[0]['url'] == SAMPLE_JOB_3['url']

def test_get_jobs_no_match(test_db):
    save_job(SAMPLE_JOB_1)
    jobs = get_jobs(filters={'keyword': 'NonExistentKeyword123'})
    assert len(jobs) == 0

def test_get_jobs_empty_db(test_db):
    jobs = get_jobs()
    assert len(jobs) == 0

def test_job_raw_data_storage(test_db):
    """Test that raw_job_data is stored and retrieved correctly as JSON string."""
    job_data_with_complex_raw = {
        'title': 'Complex Job',
        'company': 'RawData Inc.',
        'location': 'JSON Ville',
        'description': 'Testing raw data.',
        'url': 'http://example.com/job/raw',
        'source': 'TestSourceRaw',
        'raw_job_data': {'key': 'value', 'nested': {'num': 1, 'bool': True, 'arr': [1,2,3]}}
    }
    save_job(job_data_with_complex_raw)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_job_data FROM jobs WHERE url = ?", (job_data_with_complex_raw['url'],))
    raw_json_from_db = cursor.fetchone()[0]
    conn.close()

    assert isinstance(raw_json_from_db, str)
    retrieved_raw_data = json.loads(raw_json_from_db)
    assert retrieved_raw_data == job_data_with_complex_raw['raw_job_data']

def test_date_scraped_auto_population(test_db):
    """Test that date_scraped is auto-populated."""
    save_job(SAMPLE_JOB_1)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT date_scraped FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],))
    date_val = cursor.fetchone()[0]
    conn.close()
    assert date_val is not None
    # Check if it's a valid timestamp string (SQLite stores it as TEXT)
    # Example: "YYYY-MM-DD HH:MM:SS.SSSSSS" or "YYYY-MM-DD HH:MM:SS"
    try:
        # Attempt to parse it if it's a full ISO-like string
        datetime.strptime(date_val.split('.')[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pytest.fail(f"date_scraped format is not as expected: {date_val}")

def test_save_job_with_dates_in_raw_data(test_db):
    """Test saving a job where raw_job_data contains date/datetime objects."""
    sample_job_with_dates = {
        "title": "Developer with Dates",
        "company": "DateCorp",
        "location": "Timezone City",
        "description": "A job with date objects.",
        "url": "http://example.com/jobwithdates",
        "source": "test_source_dates",
        "raw_job_data": {
            "id": "job_dates_123",
            "posted_on_date": date(2023, 1, 15),
            "last_updated_datetime": datetime(2023, 1, 16, 10, 30, 0),
            "event_times": [datetime(2023, 2, 1, 14, 0, 0), datetime(2023, 2, 2, 15, 30, 0)],
            "details": "Contains various date objects for testing serialization."
        }
    }
    save_job(sample_job_with_dates)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_job_data FROM jobs WHERE url = ?", (sample_job_with_dates['url'],))
    raw_json_from_db = cursor.fetchone()[0]
    conn.close()

    assert isinstance(raw_json_from_db, str)
    retrieved_raw_data = json.loads(raw_json_from_db)

    # Verify that the date/datetime objects were converted to ISO strings
    assert retrieved_raw_data['posted_on_date'] == "2023-01-15"
    assert retrieved_raw_data['last_updated_datetime'] == "2023-01-16T10:30:00"
    assert len(retrieved_raw_data['event_times']) == 2
    assert retrieved_raw_data['event_times'][0] == "2023-02-01T14:00:00"
    assert retrieved_raw_data['event_times'][1] == "2023-02-02T15:30:00"
    assert retrieved_raw_data['id'] == sample_job_with_dates['raw_job_data']['id']


# --- Tests for toggle_applied_status ---
def test_toggle_applied_status_success(test_db):
    """Test toggling the applied status of a job."""
    # Save a job first (it will have applied = 0 by default)
    save_job(SAMPLE_JOB_1)

    # Get its ID
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],))
    job_id = cursor.fetchone()['id']
    conn.close()

    # Toggle 1: 0 -> 1
    result1 = toggle_applied_status(job_id)
    assert result1 is not None
    assert result1['id'] == job_id
    assert result1['applied'] == 1

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,))
    status_in_db1 = cursor.fetchone()['applied']
    conn.close()
    assert status_in_db1 == 1

    # Toggle 2: 1 -> 0
    result2 = toggle_applied_status(job_id)
    assert result2 is not None
    assert result2['id'] == job_id
    assert result2['applied'] == 0

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,))
    status_in_db2 = cursor.fetchone()['applied']
    conn.close()
    assert status_in_db2 == 0

def test_toggle_applied_status_non_existent_job(test_db):
    """Test toggling applied status for a job ID that does not exist."""
    result = toggle_applied_status(99999) # Assuming 99999 does not exist
    assert result is None

def test_toggle_applied_status_db_error(test_db, monkeypatch):
    """Test toggle_applied_status behavior on database error."""
    save_job(SAMPLE_JOB_1)
    conn_temp = get_db_connection()
    job_id = conn_temp.execute("SELECT id FROM jobs WHERE url = ?", (SAMPLE_JOB_1['url'],)).fetchone()['id']
    conn_temp.close()

    # Mock commit to raise an error
    def mock_commit():
        raise sqlite3.OperationalError("Simulated commit error")

    # Find the connection object within the function to mock its commit
    # This is a bit more involved, might be simpler to mock cursor.execute on the UPDATE
    with patch('sqlite3.Connection.commit', side_effect=sqlite3.OperationalError("Simulated commit error")):
         with pytest.raises(sqlite3.OperationalError, match="Simulated commit error"):
            toggle_applied_status(job_id)

    # Verify status was not changed
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,))
    status_in_db = cursor.fetchone()['applied']
    conn.close()
    assert status_in_db == 0 # Should remain initial status


# --- Tests for get_jobs with 'applied' filter ---
def test_get_jobs_filter_by_applied_status(test_db):
    """Test filtering jobs by their 'applied' status."""
    # Helper to directly set applied status for testing get_jobs
    def set_applied_status(job_url, status):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET applied = ? WHERE url = ?", (status, job_url))
        conn.commit()
        conn.close()

    save_job(SAMPLE_JOB_1) # url: ...swe1, default applied=0
    save_job(SAMPLE_JOB_2) # url: ...ds1, default applied=0
    save_job(SAMPLE_JOB_3) # url: ...ssenior, default applied=0

    # Manually set some jobs as applied
    set_applied_status(SAMPLE_JOB_1['url'], 1) # swe1 is applied
    set_applied_status(SAMPLE_JOB_3['url'], 1) # ssenior is applied
                                            # ds1 remains not applied (0)

    # Test filter: applied
    jobs_applied = get_jobs(filters={'applied_status': 'applied'})
    assert len(jobs_applied) == 2
    applied_urls = {job['url'] for job in jobs_applied}
    assert SAMPLE_JOB_1['url'] in applied_urls
    assert SAMPLE_JOB_3['url'] in applied_urls

    # Test filter: not_applied
    jobs_not_applied = get_jobs(filters={'applied_status': 'not_applied'})
    assert len(jobs_not_applied) == 1
    assert jobs_not_applied[0]['url'] == SAMPLE_JOB_2['url']

    # Test filter: all (or no filter for applied status)
    jobs_all_by_status_all = get_jobs(filters={'applied_status': 'all'})
    assert len(jobs_all_by_status_all) == 3

    jobs_all_no_status_filter = get_jobs(filters={}) # No applied_status key
    assert len(jobs_all_no_status_filter) == 3


def test_get_jobs_combined_filter_with_applied_status(test_db):
    def set_applied_status(job_url, status):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET applied = ? WHERE url = ?", (status, job_url))
        conn.commit()
        conn.close()

    # SAMPLE_JOB_1: Software Engineer, TestIndeed, Remote, USA. Desc: ...applications.
    # SAMPLE_JOB_2: Data Scientist, TestLinkedIn, New York, NY. Desc: ...datasets.
    # SAMPLE_JOB_3: Senior Software Engineer, TestIndeed, San Francisco, CA. Desc: ...Python and SQL.
    save_job(SAMPLE_JOB_1)
    save_job(SAMPLE_JOB_2)
    save_job(SAMPLE_JOB_3)

    set_applied_status(SAMPLE_JOB_1['url'], 1) # Applied
    set_applied_status(SAMPLE_JOB_2['url'], 0) # Not Applied
    set_applied_status(SAMPLE_JOB_3['url'], 1) # Applied

    # Filter: keyword "Software", source "TestIndeed", applied_status "applied"
    filters = {
        'keyword': 'Software',
        'source': 'TestIndeed',
        'applied_status': 'applied'
    }
    jobs = get_jobs(filters=filters)
    assert len(jobs) == 2 # SAMPLE_JOB_1 and SAMPLE_JOB_3
    urls = {job['url'] for job in jobs}
    assert SAMPLE_JOB_1['url'] in urls
    assert SAMPLE_JOB_3['url'] in urls

    # Filter: keyword "Python", applied_status "not_applied"
    # (SAMPLE_JOB_3 has Python but is applied=1, so should not be found)
    filters_py_not_applied = {
        'keyword': 'Python',
        'applied_status': 'not_applied'
    }
    jobs_py_not_applied = get_jobs(filters=filters_py_not_applied)
    assert len(jobs_py_not_applied) == 0

    # Filter: location "USA", applied_status "applied"
    filters_loc_applied = {
        'location': 'USA', # SAMPLE_JOB_1
        'applied_status': 'applied'
    }
    jobs_loc_applied = get_jobs(filters=filters_loc_applied)
    assert len(jobs_loc_applied) == 1
    assert jobs_loc_applied[0]['url'] == SAMPLE_JOB_1['url']


# Example of how to use the app_context if some db functions might need it
# (though current ones don't seem to strictly require it for connection)
# def test_get_jobs_with_app_context(test_db, app):
#     with app.app_context():
#         save_job(SAMPLE_JOB_1)
#         jobs = get_jobs()
#         assert len(jobs) == 1
#         assert jobs[0]['title'] == SAMPLE_JOB_1['title']
