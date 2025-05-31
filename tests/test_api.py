import pytest
import json
import os
from unittest.mock import patch, MagicMock # For mocking
from datetime import date, datetime # Import date and datetime

# Sample data for mocking jobspy
MOCK_JOBSPY_RESULT_DF_EMPTY = MagicMock()
MOCK_JOBSPY_RESULT_DF_EMPTY.empty = True
MOCK_JOBSPY_RESULT_DF_EMPTY.to_dict.return_value = []


MOCK_JOBSPY_JOB_1 = {
    'site': 'TestIndeed',
    'job_url': 'http://example.com/mockjob1',
    'title': 'Mock Software Engineer',
    'company': 'MockTestCo',
    'location': 'MockLocation, USA',
    'description': 'Develop mock applications.',
    # ... other fields jobspy might return
}
MOCK_JOBSPY_JOB_2 = {
    'site': 'TestLinkedIn',
    'job_url': 'http://example.com/mockjob2',
    'title': 'Mock Data Analyst',
    'company': 'AlphaMock',
    'location': 'MockCity, NY',
    'description': 'Analyze mock data.',
}
MOCK_JOBSPY_RESULT_DF_WITH_DATA = MagicMock()
MOCK_JOBSPY_RESULT_DF_WITH_DATA.empty = False
MOCK_JOBSPY_RESULT_DF_WITH_DATA.to_dict.return_value = [MOCK_JOBSPY_JOB_1, MOCK_JOBSPY_JOB_2]
MOCK_JOBSPY_RESULT_DF_WITH_DATA.fillna.return_value = MOCK_JOBSPY_RESULT_DF_WITH_DATA #Chain fillna

# Sample job data for populating DB for /api/jobs tests
DB_JOB_1 = {
    'title': 'API Test SWE',
    'company': 'APITestCo',
    'location': 'Remote, TestLocation',
    'description': 'API testing for software roles.',
    'url': 'http://example.com/apitest/swe1',
    'source': 'APISourceIndeed',
    'raw_job_data': {'id': 'apitest_swe1'}
}
DB_JOB_2 = {
    'title': 'API Test Data Scientist',
    'company': 'APITestOrg',
    'location': 'New York, TestLocation',
    'description': 'API testing for data science.',
    'url': 'http://example.com/apitest/ds1',
    'source': 'APISourceLinkedIn',
    'raw_job_data': {'id': 'apitest_ds1'}
}
DB_JOB_3 = { # For keyword search in description
    'title': 'API Test DevOps',
    'company': 'APITestInfra',
    'location': 'Austin, TX',
    'description': 'Infrastructure and CI/CD with Python.',
    'url': 'http://example.com/apitest/devops1',
    'source': 'APISourceIndeed',
    'raw_job_data': {'id': 'apitest_devops1'}
}


@pytest.mark.usefixtures("test_db", "mock_google_api_key")
class TestApiEndpoints:

    @patch('app.main.scrape_online_jobs') # Path to where scrape_online_jobs is IMPORTED in main.py
    def test_scrape_jobs_endpoint_success_and_save_with_dates(self, mock_scrape_online_jobs, client):
        # Updated mock job data to include date/datetime objects
        mock_job_with_dates_from_scraper = {
            'site': 'TestDateSource',
            'job_url': 'http://example.com/mockjobwithdates',
            'title': 'Mock Job With Dates',
            'company': 'DateMockCo',
            'location': 'MockDateLocation, USA',
            'description': 'Develop mock applications with date fields.',
            'date_posted': date(2023, 3, 10),  # datetime.date object
            'last_seen': datetime(2023, 3, 15, 12, 0, 0), # datetime.datetime object
            'misc_details': {'event_date': date(2023, 4, 1)}
        }

        mock_scrape_online_jobs.return_value = [mock_job_with_dates_from_scraper, MOCK_JOBSPY_JOB_1]

        response = client.get('/api/scrape-jobs?search_term=testdates&location=dateloc&site_names=TestDateSource,TestIndeed&results_wanted=2')

        assert response.status_code == 200
        json_data = response.get_json()
        assert 'jobs' in json_data
        assert len(json_data['jobs']) == 2
        mock_scrape_online_jobs.assert_called_once()

        # Verify jobs were saved and dates in raw_job_data are serialized
        from app.database import get_jobs
        db_jobs = get_jobs()
        assert len(db_jobs) == 2

        saved_job_with_dates = None
        for job in db_jobs:
            if job['url'] == mock_job_with_dates_from_scraper['job_url']:
                saved_job_with_dates = job
                break

        assert saved_job_with_dates is not None
        assert saved_job_with_dates['source'] == mock_job_with_dates_from_scraper['site']

        # Check raw_job_data serialization for dates
        raw_data_dict = json.loads(saved_job_with_dates['raw_job_data'])
        assert raw_data_dict['date_posted'] == "2023-03-10"
        assert raw_data_dict['last_seen'] == "2023-03-15T12:00:00"
        assert raw_data_dict['misc_details']['event_date'] == "2023-04-01"
        assert raw_data_dict['title'] == mock_job_with_dates_from_scraper['title'] # Ensure other fields are there


    @patch('app.main.scrape_online_jobs')
    def test_scrape_jobs_endpoint_no_jobs_found(self, mock_scrape_online_jobs, client):
        mock_scrape_online_jobs.return_value = [] # Simulate no jobs found by scraper

        response = client.get('/api/scrape-jobs?search_term=empty&location=void')
        assert response.status_code == 200
        json_data = response.get_json()
        assert 'jobs' in json_data
        assert len(json_data['jobs']) == 0

        from app.database import get_jobs
        db_jobs = get_jobs()
        assert len(db_jobs) == 0 # No jobs should be saved

    @patch('app.main.scrape_online_jobs')
    def test_scrape_jobs_endpoint_scraper_error(self, mock_scrape_online_jobs, client):
        mock_scrape_online_jobs.return_value = None # Simulate an error from the scraper function

        response = client.get('/api/scrape-jobs?search_term=error&location=error')
        assert response.status_code == 500
        json_data = response.get_json()
        assert 'error' in json_data
        assert "Failed to scrape jobs" in json_data['error']


    def test_get_jobs_api_no_filters(self, client):
        # Pre-populate database using app.database.save_job
        from app.database import save_job
        save_job(DB_JOB_1)
        save_job(DB_JOB_2)

        response = client.get('/api/jobs')
        assert response.status_code == 200
        json_data = response.get_json()
        assert 'jobs' in json_data
        assert len(json_data['jobs']) == 2
        # Dates are converted to string, check for one job's URL
        assert any(job['url'] == DB_JOB_1['url'] for job in json_data['jobs'])


    def test_get_jobs_api_with_filters(self, client):
        from app.database import save_job
        save_job(DB_JOB_1) # APISourceIndeed, location Remote, TestLocation, title API Test SWE
        save_job(DB_JOB_2) # APISourceLinkedIn, location New York, TestLocation, title API Test Data Scientist
        save_job(DB_JOB_3) # APISourceIndeed, location Austin, TX, desc Python

        # Filter by source
        response = client.get('/api/jobs?source=APISourceLinkedIn')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 1
        assert json_data['jobs'][0]['url'] == DB_JOB_2['url']

        # Filter by location
        response = client.get('/api/jobs?location=TestLocation') # Matches DB_JOB_1 and DB_JOB_2
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 2

        # Filter by keyword (in title)
        response = client.get('/api/jobs?keyword=SWE')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 1
        assert json_data['jobs'][0]['url'] == DB_JOB_1['url']

        # Filter by keyword (in description)
        response = client.get('/api/jobs?keyword=Python')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 1
        assert json_data['jobs'][0]['url'] == DB_JOB_3['url']

        # Combined filters
        response = client.get('/api/jobs?source=APISourceIndeed&keyword=API')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 2 # DB_JOB_1 and DB_JOB_3
        urls = {job['url'] for job in json_data['jobs']}
        assert DB_JOB_1['url'] in urls
        assert DB_JOB_3['url'] in urls

    def test_get_jobs_api_filter_by_applied_status(self, client):
        from app.database import save_job, get_db_connection

        # Save jobs
        save_job(DB_JOB_1) # default applied = 0
        save_job(DB_JOB_2) # default applied = 0
        save_job(DB_JOB_3) # default applied = 0

        # Manually update applied status for some jobs
        conn = get_db_connection()
        cursor = conn.cursor()
        # Get IDs first
        job1_id = cursor.execute("SELECT id FROM jobs WHERE url = ?", (DB_JOB_1['url'],)).fetchone()['id']
        job3_id = cursor.execute("SELECT id FROM jobs WHERE url = ?", (DB_JOB_3['url'],)).fetchone()['id']

        cursor.execute("UPDATE jobs SET applied = 1 WHERE id = ?", (job1_id,))
        cursor.execute("UPDATE jobs SET applied = 1 WHERE id = ?", (job3_id,))
        conn.commit()
        conn.close()

        # Test ?applied_status=applied
        response = client.get('/api/jobs?applied_status=applied')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 2
        urls_applied = {job['url'] for job in json_data['jobs']}
        assert DB_JOB_1['url'] in urls_applied
        assert DB_JOB_3['url'] in urls_applied

        # Test ?applied_status=not_applied
        response = client.get('/api/jobs?applied_status=not_applied')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 1
        assert json_data['jobs'][0]['url'] == DB_JOB_2['url']

        # Test ?applied_status=all (or no param) - should return all
        response_all = client.get('/api/jobs?applied_status=all')
        json_data_all = response_all.get_json()
        assert response_all.status_code == 200
        assert len(json_data_all['jobs']) == 3

        response_no_param = client.get('/api/jobs') # No applied_status param
        json_data_no_param = response_no_param.get_json()
        assert response_no_param.status_code == 200
        assert len(json_data_no_param['jobs']) == 3

    def test_get_jobs_api_combined_filter_with_applied(self, client):
        from app.database import save_job, get_db_connection
        save_job(DB_JOB_1) # APISourceIndeed, API Test SWE, Remote, TestLocation, default applied=0
        save_job(DB_JOB_2) # APISourceLinkedIn, API Test Data Scientist, New York, TestLocation, default applied=0
        save_job(DB_JOB_3) # APISourceIndeed, API Test DevOps, Austin, TX, desc Python, default applied=0

        conn = get_db_connection()
        cursor = conn.cursor()
        job1_id = cursor.execute("SELECT id FROM jobs WHERE url = ?", (DB_JOB_1['url'],)).fetchone()['id']
        cursor.execute("UPDATE jobs SET applied = 1 WHERE id = ?", (job1_id,)) # DB_JOB_1 is applied
        conn.commit()
        conn.close()

        # Keyword "API", source "APISourceIndeed", applied_status "applied"
        response = client.get('/api/jobs?keyword=API&source=APISourceIndeed&applied_status=applied')
        json_data = response.get_json()
        assert response.status_code == 200
        assert len(json_data['jobs']) == 1
        assert json_data['jobs'][0]['url'] == DB_JOB_1['url']

        # Keyword "API", source "APISourceIndeed", applied_status "not_applied"
        response_not_applied = client.get('/api/jobs?keyword=API&source=APISourceIndeed&applied_status=not_applied')
        json_data_not = response_not_applied.get_json()
        assert response_not_applied.status_code == 200
        assert len(json_data_not['jobs']) == 1
        assert json_data_not['jobs'][0]['url'] == DB_JOB_3['url'] # DB_JOB_3 matches keyword & source, and is not applied


    # --- Tests for /api/jobs/<job_id>/toggle-applied ---
    def test_toggle_applied_endpoint_success(self, client):
        from app.database import save_job, get_db_connection
        save_job(DB_JOB_1) # Default applied = 0

        conn = get_db_connection()
        cursor = conn.cursor()
        job_id = cursor.execute("SELECT id FROM jobs WHERE url = ?", (DB_JOB_1['url'],)).fetchone()['id']
        conn.close()

        # Toggle 1: 0 -> 1
        response1 = client.post(f'/api/jobs/{job_id}/toggle-applied')
        json_data1 = response1.get_json()
        assert response1.status_code == 200
        assert json_data1['message'] == "Applied status updated successfully"
        assert json_data1['job_id'] == job_id
        assert json_data1['new_status'] == 1

        conn = get_db_connection()
        db_status1 = conn.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,)).fetchone()['applied']
        conn.close()
        assert db_status1 == 1

        # Toggle 2: 1 -> 0
        response2 = client.post(f'/api/jobs/{job_id}/toggle-applied')
        json_data2 = response2.get_json()
        assert response2.status_code == 200
        assert json_data2['new_status'] == 0

        conn = get_db_connection()
        db_status2 = conn.execute("SELECT applied FROM jobs WHERE id = ?", (job_id,)).fetchone()['applied']
        conn.close()
        assert db_status2 == 0

    def test_toggle_applied_endpoint_not_found(self, client):
        response = client.post('/api/jobs/99999/toggle-applied') # Non-existent ID
        assert response.status_code == 404
        json_data = response.get_json()
        assert "Job not found" in json_data['error']

    @patch('app.database.toggle_applied_status') # Mock the database function
    def test_toggle_applied_endpoint_db_error(self, mock_toggle_db_func, client):
        from app.database import save_job, get_db_connection
        import sqlite3
        save_job(DB_JOB_1)
        conn = get_db_connection()
        job_id = conn.execute("SELECT id FROM jobs WHERE url = ?", (DB_JOB_1['url'],)).fetchone()['id']
        conn.close()

        mock_toggle_db_func.side_effect = sqlite3.Error("Simulated DB error on toggle")

        response = client.post(f'/api/jobs/{job_id}/toggle-applied')
        assert response.status_code == 500
        json_data = response.get_json()
        assert "Database operation failed" in json_data['error']


    @patch('app.main.process_cv_and_jd')
    @patch('app.main.generate_cv_pdf_from_json_string')
    def test_batch_generate_cvs_success(self, mock_generate_pdf, mock_process_cv, client):
        # Mock Gemini and PDF generation
        mock_process_cv.return_value = '{"cv_field": "tailored_value"}' # JSON string
        mock_generate_pdf.return_value = True # PDF generation success

        # Create a dummy CV file for upload
        dummy_cv_content = "This is a dummy CV content."
        # Need to create a temp file that can be "uploaded"
        # For simplicity, we use BytesIO to simulate a file.
        from io import BytesIO
        cv_file = (BytesIO(dummy_cv_content.encode('utf-8')), 'dummy_cv.txt')

        job_descs = ["Job desc 1 for SWE", "Job desc 2 for DS"]
        job_titles = ["SWE Role", "DS Role"]

        data = {
            'cv_file': cv_file,
            'job_descriptions[]': job_descs,
            'job_titles[]': job_titles
        }

        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        json_data = response.get_json()
        assert 'results' in json_data
        assert len(json_data['results']) == 2

        for i, result in enumerate(json_data['results']):
            assert result['status'] == 'success'
            assert result['job_title_summary'] == job_titles[i]
            assert '/api/download-cv/' in result['pdf_url']

        assert mock_process_cv.call_count == 2
        assert mock_generate_pdf.call_count == 2
        # Check args for one of the calls (optional, more detailed)
        # args_cv, kwargs_cv = mock_process_cv.call_args_list[0]
        # assert dummy_cv_content in args_cv # cv_content_str
        # assert job_descs[0] in args_cv      # jd_content


    @patch('app.main.process_cv_and_jd')
    @patch('app.main.generate_cv_pdf_from_json_string')
    def test_batch_generate_cvs_partial_failure(self, mock_generate_pdf, mock_process_cv, client):
        # First job succeeds, second fails at process_cv_and_jd, third fails at pdf_gen
        mock_process_cv.side_effect = [
            '{"cv_field": "success_cv"}', # Success for job 1
            None,                         # process_cv_and_jd fails for job 2
            '{"cv_field": "failure_pdf_cv"}' # Success for job 3 (process)
        ]
        mock_generate_pdf.side_effect = [
            True, # PDF success for job 1
            # No call for job 2 as process_cv failed
            False # PDF fails for job 3
        ]

        from io import BytesIO
        cv_file = (BytesIO(b"dummy cv content"), 'dummy.txt')
        job_descs = ["Desc 1", "Desc 2", "Desc 3"]
        job_titles = ["Title 1", "Title 2", "Title 3"]

        data = {
            'cv_file': cv_file,
            'job_descriptions[]': job_descs,
            'job_titles[]': job_titles
        }
        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        json_data = response.get_json()
        results = json_data['results']
        assert len(results) == 3

        assert results[0]['status'] == 'success'
        assert results[0]['job_title_summary'] == job_titles[0]
        assert '/api/download-cv/' in results[0]['pdf_url']

        assert results[1]['status'] == 'error'
        assert results[1]['job_title_summary'] == job_titles[1]
        assert "Failed to tailor CV" in results[1]['message']

        assert results[2]['status'] == 'error'
        assert results[2]['job_title_summary'] == job_titles[2]
        assert "PDF generation failed" in results[2]['message']

        assert mock_process_cv.call_count == 3 # Called for all three
        assert mock_generate_pdf.call_count == 2 # Called for 1 and 3


    def test_batch_generate_cvs_no_cv_file(self, client):
        response = client.post('/api/batch-generate-cvs', data={
            'job_descriptions[]': ["Desc 1"],
            'job_titles[]': ["Title 1"]
        }, content_type='multipart/form-data')
        assert response.status_code == 400
        json_data = response.get_json()
        assert "No CV file part" in json_data['error']

    def test_batch_generate_cvs_no_job_descriptions(self, client):
        from io import BytesIO
        cv_file = (BytesIO(b"dummy cv content"), 'dummy.txt')
        response = client.post('/api/batch-generate-cvs', data={
            'cv_file': cv_file
        }, content_type='multipart/form-data')
        assert response.status_code == 400
        json_data = response.get_json()
        assert "No job descriptions provided" in json_data['error']

    # Test for GOOGLE_API_KEY missing can be added if mock_google_api_key is not session-wide
    # or if specific endpoints need to be tested without it.
    # For that, you might need a way to 'unpatch' or run specific tests without the fixture.
    # Example:
    # def test_endpoint_fails_if_no_api_key(self, client, monkeypatch):
    #     monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    #     # If app loads config at startup, need to re-create app or modify its config
    #     # This is more complex and depends on app structure.
    #     # For now, assume mock_google_api_key fixture covers most cases or real key is present for testing.
    #     pass

    def test_cv_format_file_missing(self, client, app, monkeypatch):
        """Test server error if CV_FORMAT_FILE_PATH is incorrect."""
        # Temporarily change the CV_FORMAT_FILE_PATH to something invalid
        original_path = app.config['CV_FORMAT_FILE_PATH']
        monkeypatch.setitem(app.config, 'CV_FORMAT_FILE_PATH', 'non_existent_cv_format.json')

        from io import BytesIO
        cv_file = (BytesIO(b"dummy cv content"), 'dummy.txt')
        job_descs = ["Job desc 1"]
        job_titles = ["Title 1"]
        data = {'cv_file': cv_file, 'job_descriptions[]': job_descs, 'job_titles[]': job_titles}

        # Test /api/tailor-cv (as it's simpler for this case)
        # Need to add job_description for this endpoint
        data_single = data.copy()
        data_single['job_description'] = job_descs[0] # Use first job_desc
        del data_single['job_descriptions[]'] # remove batch fields
        del data_single['job_titles[]']

        response_single = client.post('/api/tailor-cv', data=data_single, content_type='multipart/form-data')
        assert response_single.status_code == 500
        assert "CV format file not found" in response_single.get_json()['error']

        # Test /api/batch-generate-cvs
        response_batch = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')
        assert response_batch.status_code == 500
        assert "CV format file not found" in response_batch.get_json()['error']

        # Restore original path (monkeypatch should do this, but good practice if not using setitem)
        # app.config['CV_FORMAT_FILE_PATH'] = original_path
        # For setitem, monkeypatch handles restoration.
