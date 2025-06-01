import pytest
import json
import os
from unittest.mock import patch, MagicMock, call # For mocking, call added
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
    # Removed save_generated_cv mock as we want the real one to run (it calls set_job_cv_generated_status)
    # @patch('app.main.save_generated_cv') # Keep this if we want to isolate from save_generated_cv's own DB ops for some reason
    @patch('app.main.set_job_cv_generated_status') # Mock this to verify it's called
    def test_batch_generate_cvs_success_and_db_update(
        self, mock_set_job_cv_generated_status, mock_generate_pdf, mock_process_cv, client, app
    ):
        from app.database import save_job, get_job_by_id # For saving and verifying
        from io import BytesIO

        # 1. Save some jobs to get actual job IDs
        job_to_batch1_data = {**DB_JOB_1, 'title': 'Batch Job 1', 'url': 'http://example.com/batchjob1', 'applied': 0}
        job_to_batch2_data = {**DB_JOB_2, 'title': 'Batch Job 2', 'url': 'http://example.com/batchjob2', 'applied': 0}

        saved_job1_id = save_job(job_to_batch1_data)
        saved_job2_id = save_job(job_to_batch2_data)
        assert saved_job1_id is not None
        assert saved_job2_id is not None

        # Mock Gemini and PDF generation
        mock_process_cv.return_value = '{"cv_field": "tailored_value"}' # JSON string
        mock_generate_pdf.return_value = True # PDF generation success

        # We are interested in set_job_cv_generated_status being called correctly by the endpoint.
        # The save_generated_cv mock is removed so the actual function runs, which in turn calls set_job_cv_generated_status.
        # If save_generated_cv itself was very complex and we wanted to avoid its DB writes for this specific test,
        # we could mock save_generated_cv to return a dummy DB ID, and then separately test set_job_cv_generated_status.
        # However, for integration, it's good to let save_generated_cv run if it's not too heavy.
        # For this test, we'll directly mock set_job_cv_generated_status to confirm it's called.

        dummy_cv_content = "This is a dummy CV content."
        cv_file = (BytesIO(dummy_cv_content.encode('utf-8')), 'dummy_cv.txt')

        job_descs = [job_to_batch1_data['description'], job_to_batch2_data['description']]
        job_titles = [job_to_batch1_data['title'], job_to_batch2_data['title']]
        job_ids = [str(saved_job1_id), str(saved_job2_id)] # Send IDs as strings, as form data would

        data = {
            'cv_file': cv_file,
            'job_descriptions[]': job_descs,
            'job_titles[]': job_titles,
            'job_ids[]': job_ids
        }

        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        json_data = response.get_json()
        assert 'results' in json_data
        assert len(json_data['results']) == 2

        generated_cv_db_ids_from_response = []
        for i, result in enumerate(json_data['results']):
            assert result['status'] == 'success'
            assert result['job_title_summary'] == job_titles[i]
            assert result['job_id'] == int(job_ids[i]) # Check if job_id is in response
            assert '/api/download-cv/' in result['pdf_url']
            assert 'generated_cv_db_id' in result # Check if the new key is present
            if result['generated_cv_db_id']:
                 generated_cv_db_ids_from_response.append(result['generated_cv_db_id'])


        assert mock_process_cv.call_count == 2
        assert mock_generate_pdf.call_count == 2

        # Verify set_job_cv_generated_status was called for each job
        # The actual save_generated_cv in app.main calls set_job_cv_generated_status
        # So, we check if our mock_set_job_cv_generated_status was called.
        expected_set_status_calls = [
            call(job_id=saved_job1_id, status=True),
            call(job_id=saved_job2_id, status=True)
        ]
        mock_set_job_cv_generated_status.assert_has_calls(expected_set_status_calls, any_order=True)
        assert mock_set_job_cv_generated_status.call_count == 2

        # Additionally, if we weren't mocking set_job_cv_generated_status,
        # we would check the database directly:
        # updated_job1 = get_job_by_id(saved_job1_id)
        # updated_job2 = get_job_by_id(saved_job2_id)
        # assert updated_job1['applied'] == 1
        # assert updated_job2['applied'] == 1

        # Verify that records were created in generated_cvs table (if checking more deeply)
        # This depends on whether save_generated_cv is mocked or not.
        # If not mocked (as is the case now for save_generated_cv), actual DB IDs should be returned.
        assert len(generated_cv_db_ids_from_response) == 2
        from app.database import get_db_connection
        conn = get_db_connection()
        for db_id in generated_cv_db_ids_from_response:
            cur = conn.execute("SELECT * FROM generated_cvs WHERE id = ?", (db_id,))
            row = cur.fetchone()
            assert row is not None
            assert row['pdf_filename'] is not None # Check some fields
            # Example: Check if associated job_id is correct if your schema stores it
            # For now, we assume the endpoint's response of generated_cv_db_id is sufficient proof of creation for this test.
        conn.close()


    @patch('app.main.process_cv_and_jd')
    @patch('app.main.generate_cv_pdf_from_json_string')
    @patch('app.main.set_job_cv_generated_status') # Mock to check calls
    def test_batch_generate_cvs_partial_failure(self, mock_set_status, mock_generate_pdf, mock_process_cv, client, app):
        from app.database import save_job
        from io import BytesIO

        # Save jobs to get IDs
        job1_data = {**DB_JOB_1, 'title': 'BatchFail Job 1', 'url': 'http://example.com/bfj1'}
        job2_data = {**DB_JOB_2, 'title': 'BatchFail Job 2', 'url': 'http://example.com/bfj2'}
        job3_data = {**DB_JOB_3, 'title': 'BatchFail Job 3', 'url': 'http://example.com/bfj3'}
        job1_id = save_job(job1_data)
        job2_id = save_job(job2_data)
        job3_id = save_job(job3_data)

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

        cv_file = (BytesIO(b"dummy cv content"), 'dummy.txt')
        job_descs = [job1_data['description'], job2_data['description'], job3_data['description']]
        job_titles = [job1_data['title'], job2_data['title'], job3_data['title']]
        job_ids = [str(job1_id), str(job2_id), str(job3_id)]


        data = {
            'cv_file': cv_file,
            'job_descriptions[]': job_descs,
            'job_titles[]': job_titles,
            'job_ids[]': job_ids
        }
        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        json_data = response.get_json()
        results = json_data['results']
        assert len(results) == 3

        assert results[0]['status'] == 'success'
        assert results[0]['job_title_summary'] == job_titles[0]
        assert results[0]['job_id'] == job1_id
        assert '/api/download-cv/' in results[0]['pdf_url']

        assert results[1]['status'] == 'error'
        assert results[1]['job_title_summary'] == job_titles[1]
        assert results[1]['job_id'] == job2_id
        assert "Failed to tailor CV" in results[1]['message']

        assert results[2]['status'] == 'error'
        assert results[2]['job_title_summary'] == job_titles[2]
        assert results[2]['job_id'] == job3_id
        assert "PDF generation failed" in results[2]['message']

        assert mock_process_cv.call_count == 3 # Called for all three
        assert mock_generate_pdf.call_count == 2 # Called for 1 and 3

        # Check that set_job_cv_generated_status was called only for the successful one
        mock_set_status.assert_called_once_with(job_id=job1_id, status=True)



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

    # --- Tests for /api/auto-apply/<job_id> ---

    @patch('app.main.time.sleep')
    @patch('app.main.os.path.exists')
    @patch('app.main._find_element_dynamically')
    @patch('app.main.webdriver.Chrome')
    @patch('app.main.get_job_by_id')
    @patch('app.main.SITE_SELECTORS', new_callable=dict) # Mock SITE_SELECTORS at the app.main level
    @patch('app.main.WebDriverWait') # Mock WebDriverWait
    @patch('app.main.EC') # Mock Expected Conditions
    @patch('app.main.By') # Mock By
    def test_auto_apply_scenario_question_found_answer_clicked(
        self, mock_by, mock_ec, mock_webdriverwait, mock_site_selectors, mock_get_job_by_id,
        mock_webdriver_chrome, mock_find_element_dynamically, mock_os_path_exists,
        mock_time_sleep, client, app
    ):
        """Scenario 1: Question found, answer successfully clicked."""
        sample_job_id = 1
        sample_job_url = 'http://example.com/job/1'
        sample_pdf_filename = "test_cv.pdf"
        manual_login_pause_seconds_value = 120

        mock_get_job_by_id.return_value = {'id': sample_job_id, 'url': sample_job_url, 'title': 'Test Job'}

        mock_driver_instance = MagicMock()
        mock_webdriver_chrome.return_value = mock_driver_instance

        # Mock for regular form fields
        mock_form_field_element = MagicMock()
        # Mock for the answer element to a screening question
        mock_answer_element = MagicMock()

        # Configure _find_element_dynamically:
        # 1. To return form field elements for initial fields
        # 2. To return the answer element for the screening question's answer
        # 3. To return the submit button
        # We'll make it more specific based on the selector value later if needed
        submit_button_element = MagicMock()
        mock_find_element_dynamically.side_effect = [
            mock_form_field_element, # Name
            mock_form_field_element, # Email
            mock_form_field_element, # Phone
            mock_form_field_element, # CV Upload
            mock_answer_element,     # Screening question's answer
            submit_button_element    # Submit button
        ]

        # Mock for question text element search
        mock_question_text_element = MagicMock()
        mock_question_text_element.is_displayed.return_value = True
        # WebDriverWait(...).until(...) will return this list
        mock_webdriverwait_until = MagicMock(return_value=[mock_question_text_element])
        mock_webdriverwait.return_value.until = mock_webdriverwait_until

        # Mock what EC.presence_of_all_elements_located would return (a locator condition)
        mock_locator_condition = MagicMock()
        mock_ec.presence_of_all_elements_located.return_value = mock_locator_condition

        # Define selectors including screening questions
        question_text_fragment = "Are you authorized?"
        answer_selector_for_yes = {"type": "xpath", "value": "//radio[@id='yes_auth']"}

        default_selectors_config = {
            "name": {"type": "id", "value": "default_name_id"},
            "email": {"type": "id", "value": "default_email_id"},
            "phone": {"type": "id", "value": "default_phone_id"},
            "cv_upload": {"type": "css", "value": "input[type='file'].default-cv"},
            "submit_button": {"type": "id", "value": "default_submit_btn"},
            "screening_questions": [
                {
                    "question_text_fragments": [question_text_fragment],
                    "answer_selectors": {"Yes": answer_selector_for_yes},
                    "target_answer": "Yes"
                }
            ]
        }
        mock_site_selectors.update({"default": default_selectors_config, "example.com": default_selectors_config}) # Ensure example.com uses this

        mock_os_path_exists.return_value = True
        expected_cv_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], sample_pdf_filename)

        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test User", "EmailAddress": "test@example.com", "PhoneNumber": "1234567890"}},
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 200
        json_data = response.get_json()
        assert "Navigated to job URL and attempted basic form filling" in json_data['message']

        mock_driver_instance.get.assert_called_once_with(sample_job_url)

        # Verify WebDriverWait was called for question search
        # The XPath for question search is complex due to multiple fragments and element types.
        # We check that it was called with an XPath for the fragment.
        # Example: //*[self::p or self::label ...][contains(normalize-space(.), "Are you authorized?")]
        # For simplicity, check that `mock_webdriverwait.return_value.until` was called.
        # A more robust check would be on the args of `EC.presence_of_all_elements_located`.
        assert mock_webdriverwait.return_value.until.called
        # Check that EC.presence_of_all_elements_located was called with By.XPATH and a string containing the fragment
        # This is a bit indirect. The actual call is `EC.presence_of_all_elements_located((By.XPATH, xpath_query))`
        # So, mock_ec.presence_of_all_elements_located needs to be checked.

        # Assert that WebDriverWait was called correctly
        mock_webdriverwait.assert_called_with(mock_driver_instance, 5)
        # Assert that EC.presence_of_all_elements_located was called with an XPath
        # The actual XPath is complex, so we check it was called with By.XPATH and any string (the XPath query)
        # This check will occur for each fragment in question_text_fragments. Here, one fragment.
        expected_xpath_call_for_question = call(mock_by.XPATH, f"//*[self::p or self::label or self::span or self::div or self::legend or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6][contains(normalize-space(.), \"{question_text_fragment.replace('\"', '\\\"')}\")]")
        mock_ec.presence_of_all_elements_located.assert_has_calls([expected_xpath_call_for_question])
        # Assert that the condition from EC was used in until()
        mock_webdriverwait.return_value.until.assert_called_with(mock_locator_condition)


        # Verify _find_element_dynamically calls
        expected_find_calls = [
            call(mock_driver_instance, default_selectors_config['name'], "Name"),
            call(mock_driver_instance, default_selectors_config['email'], "Email"),
            call(mock_driver_instance, default_selectors_config['phone'], "Phone"),
            call(mock_driver_instance, default_selectors_config['cv_upload'], "CV Upload"),
            call(mock_driver_instance, answer_selector_for_yes, f"Answer 'Yes' for question '{question_text_fragment}...'"),
            call(mock_driver_instance, default_selectors_config['submit_button'], "Submit Button"),
        ]
        mock_find_element_dynamically.assert_has_calls(expected_find_calls, any_order=False) # Order matters here
        assert mock_find_element_dynamically.call_count == len(expected_find_calls)

        # Verify interactions
        mock_form_field_element.send_keys.assert_any_call("Test User")
        mock_form_field_element.send_keys.assert_any_call("test@example.com")
        mock_form_field_element.send_keys.assert_any_call("1234567890")
        mock_form_field_element.send_keys.assert_any_call(expected_cv_pdf_path)

        # Crucially, check that the answer element was clicked
        mock_answer_element.click.assert_called_once()
        submit_button_element.click.assert_called_once()

        mock_driver_instance.quit.assert_called_once()

    # --- Tests for /api/batch-cv-history ---

    def test_get_batch_cv_history_empty(self, client):
        """Test fetching batch CV history when it's empty."""
        response = client.get('/api/batch-cv-history')
        assert response.status_code == 200
        json_data = response.get_json()
        assert 'history' in json_data
        assert len(json_data['history']) == 0

    def test_get_batch_cv_history_with_records(self, client, app):
        """Test fetching batch CV history with various records."""
        from app.database import save_job, save_generated_cv
        from datetime import datetime, timedelta

        # Setup: Create some jobs
        job1_data = {**DB_JOB_1, 'url': 'http://example.com/job_hist/1'}
        job2_data = {**DB_JOB_2, 'url': 'http://example.com/job_hist/2'}
        job1_id = save_job(job1_data)
        job2_id = save_job(job2_data)
        assert job1_id is not None
        assert job2_id is not None

        # Setup: Create some generated_cvs records
        cv_content1 = {"detail": "cv content for job 1"}
        cv_content2 = {"detail": "cv content for job 2"}
        cv_content_no_job = {"detail": "cv content for no specific job"}

        # Timestamps for ordering
        ts1 = datetime.now() - timedelta(days=2)
        ts2 = datetime.now() - timedelta(days=1)
        ts3 = datetime.now()

        # Use a direct DB connection to set specific timestamps, as save_generated_cv uses default CURRENT_TIMESTAMP
        conn = app.extensions['sqlite3_conn'] # Assuming using test_db fixture correctly setup this
        cursor = conn.cursor()

        # Record 1 (linked to job1)
        cursor.execute("INSERT INTO generated_cvs (job_id, generated_pdf_filename, tailored_cv_json_content, generation_timestamp) VALUES (?, ?, ?, ?)",
                       (job1_id, "cv1.pdf", json.dumps(cv_content1), ts1.isoformat()))
        gen_cv1_id = cursor.lastrowid

        # Record 2 (linked to job2, more recent)
        cursor.execute("INSERT INTO generated_cvs (job_id, generated_pdf_filename, tailored_cv_json_content, generation_timestamp) VALUES (?, ?, ?, ?)",
                       (job2_id, "cv2.pdf", json.dumps(cv_content2), ts2.isoformat()))
        gen_cv2_id = cursor.lastrowid

        # Record 3 (unlinked, most recent)
        cursor.execute("INSERT INTO generated_cvs (job_id, generated_pdf_filename, tailored_cv_json_content, generation_timestamp) VALUES (?, ?, ?, ?)",
                       (None, "cv3_no_job.pdf", json.dumps(cv_content_no_job), ts3.isoformat()))
        gen_cv3_id = cursor.lastrowid
        conn.commit()


        response = client.get('/api/batch-cv-history')
        assert response.status_code == 200
        json_data = response.get_json()
        assert 'history' in json_data
        history = json_data['history']
        assert len(history) == 3

        # Records should be in reverse chronological order (ts3, ts2, ts1)
        assert history[0]['generated_cv_db_id'] == gen_cv3_id
        assert history[0]['job_id'] is None
        assert history[0]['job_title_summary'] is None # As job_id is NULL
        assert history[0]['job_company'] is None
        assert history[0]['job_url'] is None
        assert history[0]['pdf_filename'] == "cv3_no_job.pdf"
        assert history[0]['pdf_url'] == f"/api/download-cv/cv3_no_job.pdf"
        assert history[0]['tailored_cv_json'] == cv_content_no_job
        assert datetime.fromisoformat(history[0]['generation_timestamp']).replace(tzinfo=None) == ts3.replace(tzinfo=None)


        assert history[1]['generated_cv_db_id'] == gen_cv2_id
        assert history[1]['job_id'] == job2_id
        assert history[1]['job_title_summary'] == job2_data['title']
        assert history[1]['job_company'] == job2_data['company']
        assert history[1]['job_url'] == job2_data['url']
        assert history[1]['pdf_filename'] == "cv2.pdf"
        assert history[1]['tailored_cv_json'] == cv_content2
        assert datetime.fromisoformat(history[1]['generation_timestamp']).replace(tzinfo=None) == ts2.replace(tzinfo=None)


        assert history[2]['generated_cv_db_id'] == gen_cv1_id
        assert history[2]['job_id'] == job1_id
        assert history[2]['job_title_summary'] == job1_data['title']
        assert history[2]['pdf_filename'] == "cv1.pdf"
        assert history[2]['tailored_cv_json'] == cv_content1
        assert datetime.fromisoformat(history[2]['generation_timestamp']).replace(tzinfo=None) == ts1.replace(tzinfo=None)


    def test_get_batch_cv_history_with_limit(self, client, app):
        from app.database import save_generated_cv # save_job not needed if job_id is None
        from datetime import datetime, timedelta
        conn = app.extensions['sqlite3_conn']
        cursor = conn.cursor()

        for i in range(5):
            # Insert with slightly different timestamps to ensure order
            ts = datetime.now() - timedelta(minutes=i*10)
            cursor.execute("INSERT INTO generated_cvs (generated_pdf_filename, tailored_cv_json_content, generation_timestamp) VALUES (?, ?, ?)",
                           (f"cv_limit_test_{i}.pdf", json.dumps({"count": i}), ts.isoformat()))
        conn.commit()

        response = client.get('/api/batch-cv-history?limit=3')
        assert response.status_code == 200
        json_data = response.get_json()
        assert 'history' in json_data
        assert len(json_data['history']) == 3
        # Check that the first item (most recent) corresponds to i=0
        assert json_data['history'][0]['pdf_filename'] == "cv_limit_test_0.pdf"
        assert json_data['history'][1]['pdf_filename'] == "cv_limit_test_1.pdf"
        assert json_data['history'][2]['pdf_filename'] == "cv_limit_test_2.pdf"

    def test_get_batch_cv_history_json_parsing(self, client, app):
        from app.database import save_generated_cv
        conn = app.extensions['sqlite3_conn']
        cursor = conn.cursor()

        valid_json_content = {"key": "value", "nested": {"num": 1}}
        invalid_json_string = '{"key": "value", "broken_json": True, }' # Invalid trailing comma, True not string

        # Record with valid JSON
        cursor.execute("INSERT INTO generated_cvs (generated_pdf_filename, tailored_cv_json_content) VALUES (?, ?)",
                       ("valid_json.pdf", json.dumps(valid_json_content)))
        valid_id = cursor.lastrowid

        # Record with invalid JSON
        cursor.execute("INSERT INTO generated_cvs (generated_pdf_filename, tailored_cv_json_content) VALUES (?, ?)",
                       ("invalid_json.pdf", invalid_json_string))
        invalid_id = cursor.lastrowid
        conn.commit()

        response = client.get('/api/batch-cv-history')
        assert response.status_code == 200
        json_data = response.get_json()
        history = json_data['history']

        found_valid = False
        found_invalid = False
        for item in history:
            if item['generated_cv_db_id'] == valid_id:
                assert item['tailored_cv_json'] == valid_json_content
                found_valid = True
            elif item['generated_cv_db_id'] == invalid_id:
                assert item['tailored_cv_json'] is None # Should be None due to parsing error
                found_invalid = True

        assert found_valid
        assert found_invalid

    @patch('app.main.time.sleep')
    @patch('app.main.os.path.exists')
    @patch('app.main._find_element_dynamically')
    @patch('app.main.webdriver.Chrome')
    @patch('app.main.get_job_by_id')
    @patch('app.main.SITE_SELECTORS', new_callable=dict)
    @patch('app.main.WebDriverWait')
    @patch('app.main.EC') # Mock Expected Conditions
    @patch('app.main.By') # Mock By
    def test_auto_apply_scenario_question_text_not_found(
        self, mock_by, mock_ec, mock_webdriverwait, mock_site_selectors, mock_get_job_by_id,
        mock_webdriver_chrome, mock_find_element_dynamically, mock_os_path_exists,
        mock_time_sleep, client, app
    ):
        """Scenario 2: Question text not found on the page."""
        sample_job_id = 2
        sample_job_url = 'http://example.com/job/2'
        sample_pdf_filename = "test_cv_q_not_found.pdf"

        mock_get_job_by_id.return_value = {'id': sample_job_id, 'url': sample_job_url, 'title': 'Test Job Q Not Found'}
        mock_driver_instance = MagicMock()
        mock_webdriver_chrome.return_value = mock_driver_instance

        mock_form_field_element = MagicMock()
        # mock_answer_element = MagicMock() # Answer element should not be found or clicked
        submit_button_element = MagicMock()

        # _find_element_dynamically will only be called for form fields and submit
        mock_find_element_dynamically.side_effect = [
            mock_form_field_element, # Name
            mock_form_field_element, # Email
            mock_form_field_element, # Phone
            mock_form_field_element, # CV Upload
            # No call for answer element
            submit_button_element    # Submit button
        ]

        # Simulate question text not found: WebDriverWait(...).until(...) returns an empty list
        mock_webdriverwait_until = MagicMock(return_value=[])
        mock_webdriverwait.return_value.until = mock_webdriverwait_until

        # Mock what EC.presence_of_all_elements_located would return
        mock_locator_condition_not_found = MagicMock()
        mock_ec.presence_of_all_elements_located.return_value = mock_locator_condition_not_found

        question_text_fragment = "NonExistentQuestion"
        answer_selector_for_yes = {"type": "xpath", "value": "//radio[@id='yes_auth_ne']"}

        default_selectors_config = {
            "name": {"type": "id", "value": "default_name_id"},
            "email": {"type": "id", "value": "default_email_id"},
            # ... other fields ...
            "phone": {"type": "id", "value": "default_phone_id"},
            "cv_upload": {"type": "css", "value": "input[type='file'].default-cv"},
            "submit_button": {"type": "id", "value": "default_submit_btn"},
            "screening_questions": [
                {
                    "question_text_fragments": [question_text_fragment],
                    "answer_selectors": {"Yes": answer_selector_for_yes},
                    "target_answer": "Yes"
                }
            ]
        }
        mock_site_selectors.update({"default": default_selectors_config, "example.com": default_selectors_config})
        mock_os_path_exists.return_value = True

        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test User"}}, # Simplified CV data
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 200 # The process should complete, just not answer the question

        # Verify that _find_element_dynamically was NOT called for the answer selector
        # Count calls to _find_element_dynamically: should be 4 for fields + 1 for submit = 5
        assert mock_find_element_dynamically.call_count == 5

        # Check that no click was attempted on an answer element (as none should be found)
        # mock_answer_element.click was never defined for this test, so this is implicitly true
        # if we wanted to be very explicit, we could set mock_answer_element = MagicMock() and assert mock_answer_element.click.called is False

        submit_button_element.click.assert_called_once() # Submit should still be clicked
        mock_driver_instance.quit.assert_called_once()

    @patch('app.main.time.sleep')
    @patch('app.main.os.path.exists')
    @patch('app.main._find_element_dynamically')
    @patch('app.main.webdriver.Chrome')
    @patch('app.main.get_job_by_id')
    @patch('app.main.SITE_SELECTORS', new_callable=dict)
    @patch('app.main.WebDriverWait')
    @patch('app.main.EC')
    @patch('app.main.By')
    def test_auto_apply_scenario_answer_element_not_found(
        self, mock_by, mock_ec, mock_webdriverwait, mock_site_selectors, mock_get_job_by_id,
        mock_webdriver_chrome, mock_find_element_dynamically, mock_os_path_exists,
        mock_time_sleep, client, app
    ):
        """Scenario 3: Question text found, but specific answer element not found."""
        sample_job_id = 3
        sample_job_url = 'http://example.com/job/3'
        sample_pdf_filename = "test_cv_ans_not_found.pdf"

        mock_get_job_by_id.return_value = {'id': sample_job_id, 'url': sample_job_url, 'title': 'Test Job Ans Not Found'}
        mock_driver_instance = MagicMock()
        mock_webdriver_chrome.return_value = mock_driver_instance

        mock_form_field_element = MagicMock()
        # Answer element will not be "found" by _find_element_dynamically
        mock_answer_element_that_will_not_be_clicked = MagicMock() # mock to ensure its click is not called
        submit_button_element = MagicMock()

        # _find_element_dynamically:
        # - Returns form field elements
        # - Returns None for the answer element selector
        # - Returns submit button
        mock_find_element_dynamically.side_effect = [
            mock_form_field_element, # Name
            mock_form_field_element, # Email
            mock_form_field_element, # Phone
            mock_form_field_element, # CV Upload
            None,                    # Answer element for screening question -> Not Found
            submit_button_element    # Submit button
        ]

        # Simulate question text IS found
        mock_question_text_element = MagicMock()
        mock_question_text_element.is_displayed.return_value = True
        mock_webdriverwait_until = MagicMock(return_value=[mock_question_text_element])
        mock_webdriverwait.return_value.until = mock_webdriverwait_until

        # Mock what EC.presence_of_all_elements_located would return
        mock_locator_condition_ans_not_found = MagicMock()
        mock_ec.presence_of_all_elements_located.return_value = mock_locator_condition_ans_not_found

        question_text_fragment = "Are you authorized for this role?"
        answer_selector_for_yes = {"type": "xpath", "value": "//radio[@id='yes_auth_ans_nf']"}

        default_selectors_config = {
            "name": {"type": "id", "value": "default_name_id"},
            "email": {"type": "id", "value": "default_email_id"},
            "phone": {"type": "id", "value": "default_phone_id"},
            "cv_upload": {"type": "css", "value": "input[type='file'].default-cv"},
            "submit_button": {"type": "id", "value": "default_submit_btn"},
            "screening_questions": [
                {
                    "question_text_fragments": [question_text_fragment],
                    "answer_selectors": {"Yes": answer_selector_for_yes},
                    "target_answer": "Yes"
                }
            ]
        }
        mock_site_selectors.update({"default": default_selectors_config, "example.com": default_selectors_config})
        mock_os_path_exists.return_value = True

        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test User"}},
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 200 # Process completes

        # Verify _find_element_dynamically was called for the answer, but it returned None
        expected_find_calls_for_answer = call(mock_driver_instance, answer_selector_for_yes, f"Answer 'Yes' for question '{question_text_fragment}...'")
        mock_find_element_dynamically.assert_any_call(*expected_find_calls_for_answer[0], **expected_find_calls_for_answer[1])

        # Ensure the mock answer element (if inadvertently created or returned) was not clicked
        mock_answer_element_that_will_not_be_clicked.click.assert_not_called()

        submit_button_element.click.assert_called_once() # Submit should still be clicked
        mock_driver_instance.quit.assert_called_once()


    def test_auto_apply_pdf_filename_missing(self, client):
        """Test auto-apply when pdf_filename is missing from the request."""
        sample_job_id = 10
        # No mocks for get_job_by_id or os.path.exists needed as it should fail before them.

        cv_data_payload = { # Missing pdf_filename
            "tailored_cv": {"PersonalInformation": {"Name": "Test User"}}
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)
        assert response.status_code == 400
        json_data = response.get_json()
        assert json_data['error'] == "CV PDF filename not provided for AutoApply."

    @patch('app.main.os.path.exists') # Only os.path.exists and get_job_by_id needed for this path
    @patch('app.main.get_job_by_id')
    def test_auto_apply_pdf_file_not_found_on_server(self, mock_get_job_by_id, mock_os_path_exists, client, app):
        """Test auto-apply when the specified PDF file does not exist on the server."""
        sample_job_id = 11
        sample_pdf_filename = "non_existent_cv.pdf"

        mock_get_job_by_id.return_value = { # Job itself is found
            'id': sample_job_id, 'url': 'http://example.com/job/11', 'title': 'Test Job PDF Missing'
        }

        expected_cv_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], sample_pdf_filename)
        mock_os_path_exists.return_value = False # PDF file does not exist

        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test User"}},
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 400
        json_data = response.get_json()
        assert json_data['error'] == "Specified CV PDF not found on server."
        assert json_data['filename'] == sample_pdf_filename
        mock_os_path_exists.assert_called_once_with(expected_cv_pdf_path)


    @patch('app.main.get_job_by_id')
    def test_auto_apply_job_not_found(self, mock_get_job_by_id, client): # No selenium mocks needed here if it's before pdf filename check
        """Test auto-apply when the job_id does not exist."""
        non_existent_job_id = 999
        mock_get_job_by_id.return_value = None

        response = client.post(f'/api/auto-apply/{non_existent_job_id}')

        assert response.status_code == 404
        json_data = response.get_json()
        assert json_data['error'] == "Job not found"
        mock_get_job_by_id.assert_called_once_with(non_existent_job_id)

    @patch('app.main.get_job_by_id')
    def test_auto_apply_job_url_missing(self, mock_get_job_by_id, client):
        """Test auto-apply when the job exists but its URL is missing."""
        job_id_no_url = 2
        mock_get_job_by_id.return_value = {
            'id': job_id_no_url,
            'url': None, # URL is missing
            'title': 'Test Job without URL'
        }

        response = client.post(f'/api/auto-apply/{job_id_no_url}')

        assert response.status_code == 500
        json_data = response.get_json()
        assert json_data['error'] == "Job found, but URL is missing"
        mock_get_job_by_id.assert_called_once_with(job_id_no_url)

    @patch('app.main.os.path.exists')
    @patch('app.main.webdriver.Chrome', side_effect=Exception("WebDriver init failed simulation"))
    @patch('app.main.get_job_by_id')
    # No SITE_SELECTORS mock needed if failure is before selector usage
    def test_auto_apply_webdriver_init_failure(self, mock_get_job_by_id, mock_webdriver_chrome, mock_os_path_exists, client):
        """Test auto-apply when WebDriver initialization fails."""
        sample_job_id = 3
        sample_pdf_filename = "cv_for_webdriver_fail.pdf"
        mock_get_job_by_id.return_value = {
            'id': sample_job_id,
            'url': 'http://example.com/job/3',
            'title': 'Job for WebDriver Fail Test'
        }
        mock_os_path_exists.return_value = True # Assume PDF file check passes

        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test"}},
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 500
        json_data = response.get_json()
        assert json_data['error'] == "WebDriver initialization failed."
        assert "WebDriver init failed simulation" in json_data['details']
        mock_webdriver_chrome.assert_called_once() # Attempted to init driver
        mock_get_job_by_id.assert_called_once_with(sample_job_id)


# Define site configurations for parametrized tests
LNKD_QUESTION_TEXT = "Are you authorized to work on LinkedIn?"
LNKD_ANSWER_SELECTOR_YES = {"type": "xpath", "value": "//linkedin/radio[@id='yes_auth_li']"}
LINKEDIN_FULL_SELECTORS_CONFIG = {
    "name": {"type": "css", "value": "input[id*='UNUSED-FOR-NOW-linkedin-name']"},
    "email": {"type": "css", "value": "input[id*='emailAddress']"},
    "phone": {"type": "css", "value": "input[id*='phoneNumber']"},
    "cv_upload": {"type": "css", "value": "input[type='file'][id*='resume-upload']"},
    "submit_button": {"type": "css", "value": "button[aria-label*='submit application']"},
    "screening_questions": [
        {
            "question_text_fragments": [LNKD_QUESTION_TEXT],
            "answer_selectors": {"Yes": LNKD_ANSWER_SELECTOR_YES},
            "target_answer": "Yes"
        }
    ]
}

INDD_QUESTION_TEXT = "Will you require sponsorship on Indeed?"
INDD_ANSWER_SELECTOR_NO = {"type": "xpath", "value": "//indeed/radio[@id='no_spons_ind']"}
INDEED_FULL_SELECTORS_CONFIG = {
    "name": {"type": "id", "value": "ia-fullName"},
    "email": {"type": "id", "value": "ia-email"},
    "phone": {"type": "id", "value": "ia-phoneNumber"},
    "cv_upload": {"type": "css", "value": "input#resumeupload_input[type='file']"},
    "submit_button": {"type": "css", "value": "button[class*='ia-continueButton']"},
    "screening_questions": [
        {
            "question_text_fragments": [INDD_QUESTION_TEXT],
            "answer_selectors": {"No": INDD_ANSWER_SELECTOR_NO},
            "target_answer": "No"
        }
    ]
}

@pytest.mark.parametrize(
    "domain_name, site_job_url, site_selectors_config, screening_scenario_params",
    [
        # LinkedIn Scenarios
        ("linkedin.com", "https://www.linkedin.com/jobs/view/li123", LINKEDIN_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Q_Found_Ans_Clicked", "q_text": LNKD_QUESTION_TEXT, "ans_sel": LNKD_ANSWER_SELECTOR_YES, "target_ans_key": "Yes", "q_found_on_page": True, "ans_element_found": True}),
        ("linkedin.com", "https://www.linkedin.com/jobs/view/li124", LINKEDIN_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Q_Not_Found", "q_text": LNKD_QUESTION_TEXT, "ans_sel": LNKD_ANSWER_SELECTOR_YES, "target_ans_key": "Yes", "q_found_on_page": False, "ans_element_found": False}), # ans_element_found is moot
        ("linkedin.com", "https://www.linkedin.com/jobs/view/li125", LINKEDIN_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Ans_Not_Found", "q_text": LNKD_QUESTION_TEXT, "ans_sel": LNKD_ANSWER_SELECTOR_YES, "target_ans_key": "Yes", "q_found_on_page": True, "ans_element_found": False}),

        # Indeed Scenarios
        ("indeed.com", "https://www.indeed.com/viewjob?jk=in456", INDEED_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Q_Found_Ans_Clicked", "q_text": INDD_QUESTION_TEXT, "ans_sel": INDD_ANSWER_SELECTOR_NO, "target_ans_key": "No", "q_found_on_page": True, "ans_element_found": True}),
        ("indeed.com", "https://www.indeed.com/viewjob?jk=in457", INDEED_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Q_Not_Found", "q_text": INDD_QUESTION_TEXT, "ans_sel": INDD_ANSWER_SELECTOR_NO, "target_ans_key": "No", "q_found_on_page": False, "ans_element_found": False}),
        ("indeed.com", "https://www.indeed.com/viewjob?jk=in458", INDEED_FULL_SELECTORS_CONFIG,
         {"scenario_name": "Ans_Not_Found", "q_text": INDD_QUESTION_TEXT, "ans_sel": INDD_ANSWER_SELECTOR_NO, "target_ans_key": "No", "q_found_on_page": True, "ans_element_found": False}),
    ]
)
@patch('app.main.time.sleep')
@patch('app.main.os.path.exists')
@patch('app.main._find_element_dynamically')
@patch('app.main.webdriver.Chrome')
@patch('app.main.get_job_by_id')
@patch('app.main.SITE_SELECTORS', new_callable=dict) # Patched at class level or here for test function
@patch('app.main.WebDriverWait')
@patch('app.main.EC')
@patch('app.main.By')
def test_auto_apply_site_specific_screening_scenarios(
    mock_by, mock_ec, mock_webdriverwait, mock_site_selectors_global, mock_get_job_by_id,
    mock_webdriver_chrome, mock_find_element_dynamically, mock_os_path_exists, mock_time_sleep,
    client, app, domain_name, site_job_url, site_selectors_config, screening_scenario_params
):
    sample_job_id = int(site_job_url.split('/')[-1].split('=')[-1].replace('li','').replace('in','')) # Extract ID
    sample_pdf_filename = f"{domain_name.split('.')[0]}_cv_{sample_job_id}.pdf"
    manual_login_pause_seconds_value = 120

    mock_get_job_by_id.return_value = {'id': sample_job_id, 'url': site_job_url, 'title': f'{domain_name} Job'}
    mock_driver_instance = MagicMock()
    mock_webdriver_chrome.return_value = mock_driver_instance

    mock_form_field_element = MagicMock()
    mock_answer_element = MagicMock()
    submit_button_element = MagicMock()

    # Configure side_effect for _find_element_dynamically
    # Order: name, email, phone, cv_upload, [answer (if applicable)], submit
    dynamic_elements_return_list = [
        mock_form_field_element, mock_form_field_element,
        mock_form_field_element, mock_form_field_element
    ]
    if screening_scenario_params["q_found_on_page"] and screening_scenario_params["ans_element_found"]:
        dynamic_elements_return_list.append(mock_answer_element)
    elif screening_scenario_params["q_found_on_page"] and not screening_scenario_params["ans_element_found"]:
        dynamic_elements_return_list.append(None) # Answer element not found
    dynamic_elements_return_list.append(submit_button_element)
    mock_find_element_dynamically.side_effect = dynamic_elements_return_list

    # Configure WebDriverWait for question search
    mock_question_text_element = MagicMock()
    mock_question_text_element.is_displayed.return_value = True # Assume found element is displayed

    mock_webdriverwait_until = MagicMock()
    if screening_scenario_params["q_found_on_page"]:
        mock_webdriverwait_until.return_value = [mock_question_text_element]
    else:
        mock_webdriverwait_until.return_value = [] # Question text not found
    mock_webdriverwait.return_value.until = mock_webdriverwait_until

    mock_locator_condition = MagicMock()
    mock_ec.presence_of_all_elements_located.return_value = mock_locator_condition

    # Update the globally patched SITE_SELECTORS for this specific test run
    mock_site_selectors_global.clear() # Clear any previous state if necessary
    mock_site_selectors_global.update({
        "default": {"name": {"type": "id", "value": "default_dummy_id"}}, # Minimal default
        domain_name: site_selectors_config
    })

    mock_os_path_exists.return_value = True
    expected_cv_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], sample_pdf_filename)
    cv_data_payload = {"tailored_cv": {"PersonalInformation": {"Name": "Test User"}}, "pdf_filename": sample_pdf_filename}

    response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)
    assert response.status_code == 200
    json_data = response.get_json()
    assert domain_name in json_data["manual_login_prompt_details"]

    # Assertions for WebDriverWait and EC calls (for question search)
    if site_selectors_config.get("screening_questions"): # Only if questions are configured
        mock_webdriverwait.assert_called_with(mock_driver_instance, 5)
        expected_xpath_q_text = site_selectors_config["screening_questions"][0]["question_text_fragments"][0]
        expected_xpath_call_for_q = call(mock_by.XPATH, f"//*[self::p or self::label or self::span or self::div or self::legend or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6][contains(normalize-space(.), \"{expected_xpath_q_text.replace('\"', '\\\"')}\")]")
        # This might be called multiple times if there are multiple fragments; for this test, we assume one fragment.
        mock_ec.presence_of_all_elements_located.assert_has_calls([expected_xpath_call_for_q], any_order=True) # any_order if multiple fragments
        mock_webdriverwait.return_value.until.assert_called_with(mock_locator_condition)

    # Assertions for _find_element_dynamically calls
    expected_find_calls = [
        call(mock_driver_instance, site_selectors_config['name'], "Name"),
        call(mock_driver_instance, site_selectors_config['email'], "Email"),
        call(mock_driver_instance, site_selectors_config['phone'], "Phone"),
        call(mock_driver_instance, site_selectors_config['cv_upload'], "CV Upload"),
    ]
    if screening_scenario_params["q_found_on_page"]:
        q_config = site_selectors_config["screening_questions"][0]
        answer_sel_config = q_config["answer_selectors"][q_config["target_answer"]]
        expected_find_calls.append(call(mock_driver_instance, answer_sel_config, f"Answer '{q_config['target_answer']}' for question '{q_config['question_text_fragments'][0]}...'"))
    expected_find_calls.append(call(mock_driver_instance, site_selectors_config['submit_button'], "Submit Button"))

    mock_find_element_dynamically.assert_has_calls(expected_find_calls, any_order=False)
    assert mock_find_element_dynamically.call_count == len(expected_find_calls)

    # Assertions for element interactions (clicks)
    if screening_scenario_params["q_found_on_page"] and screening_scenario_params["ans_element_found"]:
        mock_answer_element.click.assert_called_once()
    else:
        mock_answer_element.click.assert_not_called()

    submit_button_element.click.assert_called_once()
    mock_driver_instance.quit.assert_called_once()


    @patch('app.main.SITE_SELECTORS', new_callable=dict)
    @patch('app.main.os.path.exists')
    @patch('app.main.time.sleep')
    @patch('app.main.webdriver.Chrome')
    @patch('app.main.get_job_by_id')
    def test_auto_apply_navigation_failure(
        self, mock_get_job_by_id, mock_webdriver_chrome, mock_time_sleep,
        mock_os_path_exists, mock_site_selectors, client
    ):
        """Test auto-apply when WebDriver navigation (driver.get) fails."""
        sample_job_id = 4
        sample_job_url = 'http://navfail.com/job/4' # Unique domain for this test
        sample_pdf_filename = "cv_for_nav_fail.pdf"

        mock_get_job_by_id.return_value = {
            'id': sample_job_id, 'url': sample_job_url, 'title': 'Job for Nav Fail'
        }
        mock_driver_instance = MagicMock()
        mock_webdriver_chrome.return_value = mock_driver_instance
        mock_driver_instance.get.side_effect = Exception("Navigation error sim")
        mock_os_path_exists.return_value = True # PDF file exists

        # Ensure SITE_SELECTORS has an entry for this domain or default to avoid unrelated errors
        mock_site_selectors.update({
            "default": {"name": {"type": "id", "value": "default_name"}},
            "navfail.com": {"name": {"type": "id", "value": "some_name"}} # Specific or default
        })
        cv_data_payload = {
            "tailored_cv": {"PersonalInformation": {"Name": "Test"}},
            "pdf_filename": sample_pdf_filename
        }
        response = client.post(f'/api/auto-apply/{sample_job_id}', json=cv_data_payload)

        assert response.status_code == 500
        json_data = response.get_json()
        assert json_data['error'] == f"Failed to process job URL: {sample_job_url}"
        assert "Navigation error sim" in json_data['details']
        mock_driver_instance.quit.assert_called_once()