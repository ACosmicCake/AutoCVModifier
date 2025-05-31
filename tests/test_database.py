import pytest
import sqlite3
import json
from app.database import save_job, get_jobs, get_db_connection
from datetime import datetime

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

# Example of how to use the app_context if some db functions might need it
# (though current ones don't seem to strictly require it for connection)
# def test_get_jobs_with_app_context(test_db, app):
#     with app.app_context():
#         save_job(SAMPLE_JOB_1)
#         jobs = get_jobs()
#         assert len(jobs) == 1
#         assert jobs[0]['title'] == SAMPLE_JOB_1['title']
