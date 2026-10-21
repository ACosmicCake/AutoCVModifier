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

        # Check raw_job_data serialization for dates (get_jobs doesn't return raw data, so read it directly)
        from app.database import get_db_connection
        conn = get_db_connection()
        raw_json = conn.execute("SELECT raw_job_data FROM jobs WHERE id = ?", (saved_job_with_dates['id'],)).fetchone()[0]
        conn.close()
        raw_data_dict = json.loads(raw_json)
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

    # --- Batch CV generation ---
    def _save_jobs(self, *jobs):
        from app.database import save_job
        return [save_job(job) for job in jobs]

    @patch('app.main.process_cv_and_jd')
    @patch('app.main.generate_cv_pdf_from_json_string')
    def test_batch_generate_cvs_success(self, mock_generate_pdf, mock_process_cv, client):
        mock_process_cv.return_value = '{"CV": {"PersonalInformation": {"Name": "Jane Doe"}}}'
        mock_generate_pdf.return_value = True
        job_ids = self._save_jobs(DB_JOB_1, DB_JOB_2)

        from io import BytesIO
        data = {
            'cv_file': (BytesIO(b"This is a dummy CV content."), 'dummy_cv.txt'),
            'job_ids[]': [str(i) for i in job_ids],
            'model': 'gemini/gemini-2.5-pro',
            'include_summary': 'true',
        }
        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        results = response.get_json()['results']
        assert len(results) == 2
        for result, job_id, job in zip(results, job_ids, (DB_JOB_1, DB_JOB_2)):
            assert result['status'] == 'success'
            assert result['job_id'] == job_id
            assert result['job_title_summary'] == job['title']
            assert '/api/download-cv/' in result['pdf_url']

        # The selected model and the job's own description (from the DB) reach the tailoring call.
        assert mock_process_cv.call_count == 2
        first_args = mock_process_cv.call_args_list[0].args
        assert first_args[1] == DB_JOB_1['description']
        assert first_args[3] == 'gemini/gemini-2.5-pro'
        assert first_args[4] is True

        # Generated CVs are linked to their jobs.
        jobs = client.get('/api/jobs').get_json()['jobs']
        assert all(job['cv_filename'] for job in jobs)

    @patch('app.main.process_cv_and_jd')
    @patch('app.main.generate_cv_pdf_from_json_string')
    def test_batch_generate_cvs_partial_failure(self, mock_generate_pdf, mock_process_cv, client):
        # First job succeeds, second fails at process_cv_and_jd, third fails at pdf_gen
        mock_process_cv.side_effect = ['{"cv_field": "success_cv"}', None, '{"cv_field": "failure_pdf_cv"}']
        mock_generate_pdf.side_effect = [True, False]
        job_ids = self._save_jobs(DB_JOB_1, DB_JOB_2, DB_JOB_3)

        from io import BytesIO
        data = {'cv_file': (BytesIO(b"dummy cv content"), 'dummy.txt'), 'job_ids[]': [str(i) for i in job_ids]}
        response = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        results = response.get_json()['results']
        assert [r['status'] for r in results] == ['success', 'error', 'error']
        assert '/api/download-cv/' in results[0]['pdf_url']
        assert "Failed to tailor CV" in results[1]['message']
        assert "PDF generation failed" in results[2]['message']
        assert mock_process_cv.call_count == 3
        assert mock_generate_pdf.call_count == 2

    @patch('app.main.process_cv_and_jd')
    def test_batch_generate_cvs_llm_error_is_reported_per_job(self, mock_process_cv, client):
        from app.llm import LLMError
        mock_process_cv.side_effect = LLMError("rate limited")
        job_ids = self._save_jobs(DB_JOB_1)

        from io import BytesIO
        data = {'cv_file': (BytesIO(b"cv"), 'cv.txt'), 'job_ids[]': [str(job_ids[0])]}
        result = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data').get_json()['results'][0]
        assert result['status'] == 'error'
        assert "rate limited" in result['message']

    @patch('app.main.process_cv_and_jd')
    def test_batch_generate_cvs_unknown_and_invalid_ids(self, mock_process_cv, client):
        data = {'cv_text': 'pasted cv', 'job_ids[]': ['99999', 'abc']}
        results = client.post('/api/batch-generate-cvs', data=data, content_type='multipart/form-data').get_json()['results']
        assert results[0]['message'] == "Job not found."
        assert "Invalid job_id" in results[1]['message']
        mock_process_cv.assert_not_called()

    def test_batch_generate_cvs_no_cv_file(self, client):
        response = client.post('/api/batch-generate-cvs', data={'job_ids[]': ["1"]}, content_type='multipart/form-data')
        assert response.status_code == 400
        assert "No CV file part" in response.get_json()['error']

    def test_batch_generate_cvs_no_job_descriptions(self, client):
        from io import BytesIO
        response = client.post('/api/batch-generate-cvs', data={'cv_file': (BytesIO(b"dummy cv content"), 'dummy.txt')},
                               content_type='multipart/form-data')
        assert response.status_code == 400
        assert "No job descriptions provided" in response.get_json()['error']

    def test_cv_format_file_missing(self, client, app, monkeypatch):
        """Test server error if CV_FORMAT_FILE_PATH is incorrect."""
        monkeypatch.setitem(app.config, 'CV_FORMAT_FILE_PATH', 'non_existent_cv_format.json')
        from io import BytesIO

        response_single = client.post('/api/tailor-cv', data={
            'cv_file': (BytesIO(b"dummy cv content"), 'dummy.txt'), 'job_description': "Job desc 1",
        }, content_type='multipart/form-data')
        assert response_single.status_code == 500
        assert "CV format file not found" in response_single.get_json()['error']

        response_batch = client.post('/api/batch-generate-cvs', data={
            'cv_file': (BytesIO(b"dummy cv content"), 'dummy.txt'), 'job_descriptions[]': ["Job desc 1"],
        }, content_type='multipart/form-data')
        assert response_batch.status_code == 500
        assert "CV format file not found" in response_batch.get_json()['error']

    # --- Single CV tailoring ---
    @patch('app.main.process_cv_and_jd')
    def test_tailor_cv_success_generates_pdf_and_json(self, mock_process_cv, client):
        mock_process_cv.return_value = json.dumps({"CV": {
            "PersonalInformation": {"Name": "Jane Doe"}, "JobTitle": "Data Engineer",
            "Skills": [{"SkillCategory": "Languages", "Skill": ["Python", "a<b"]}],
        }})
        from io import BytesIO
        response = client.post('/api/tailor-cv', data={
            'cv_file': (BytesIO(b"my cv"), 'cv.txt'), 'job_description': "Build data pipelines",
            'model': 'gemini/gemini-2.5-flash',
        }, content_type='multipart/form-data')

        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['pdf_download_url'] == '/api/download-cv/CV_Data_Engineer_Jane_Doe.pdf'
        assert body['json_download_url'].endswith('.json')
        assert body['tailored_cv_json']['CV']['PersonalInformation']['Name'] == "Jane Doe"
        assert mock_process_cv.call_args.args[3] == 'gemini/gemini-2.5-flash'

        pdf = client.get(body['pdf_download_url'])
        assert pdf.status_code == 200
        assert pdf.data.startswith(b'%PDF')
        assert client.get(body['json_download_url']).status_code == 200

        # A second run never overwrites the first file.
        second = client.post('/api/tailor-cv', data={
            'cv_text': "pasted cv", 'job_description': "Build data pipelines",
        }, content_type='multipart/form-data').get_json()
        assert second['pdf_download_url'] == '/api/download-cv/CV_Data_Engineer_Jane_Doe_1.pdf'

    @patch('app.main.process_cv_and_jd')
    def test_tailor_cv_for_saved_job_uses_its_description_and_links_cv(self, mock_process_cv, client):
        mock_process_cv.return_value = '{"CV": {"PersonalInformation": {"Name": "Sam"}}}'
        job_id = self._save_jobs(DB_JOB_1)[0]

        response = client.post('/api/tailor-cv', data={'cv_text': "cv", 'job_id': str(job_id)},
                               content_type='multipart/form-data')
        assert response.status_code == 200
        assert mock_process_cv.call_args.args[1] == DB_JOB_1['description']
        job = client.get('/api/jobs').get_json()['jobs'][0]
        assert job['cv_filename'] == response.get_json()['pdf_download_url'].rsplit('/', 1)[1]

    @patch('app.main.process_cv_and_jd')
    def test_tailor_cv_llm_failure_returns_502(self, mock_process_cv, client):
        from app.llm import LLMError
        mock_process_cv.side_effect = LLMError("model not found")
        response = client.post('/api/tailor-cv', data={'cv_text': "cv", 'job_description': "jd"},
                               content_type='multipart/form-data')
        assert response.status_code == 502
        assert "model not found" in response.get_json()['error']

    def test_tailor_cv_without_provider_key_returns_400(self, client, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        response = client.post('/api/tailor-cv', data={'cv_text': "cv", 'job_description': "jd"},
                               content_type='multipart/form-data')
        assert response.status_code == 400
        assert "API_KEY" in response.get_json()['error']

    def test_tailor_cv_rejects_bad_file_type(self, client):
        from io import BytesIO
        response = client.post('/api/tailor-cv', data={'cv_file': (BytesIO(b"x"), 'cv.exe'), 'job_description': "jd"},
                               content_type='multipart/form-data')
        assert response.status_code == 400
        assert "Invalid file type" in response.get_json()['error']

    def test_render_pdf_from_edited_json(self, client):
        cv = {"CV": {"PersonalInformation": {"Name": "R&D <Lead>"},
                     "ProfessionalExperience": [{"CompanyName": "AT&T", "ResponsibilitiesAndAchievements": ["Used <b> tags", "x<y"]}]}}
        response = client.post('/api/render-pdf', json={'cv_json': cv})
        assert response.status_code == 200
        assert client.get(response.get_json()['pdf_download_url']).data.startswith(b'%PDF')

        assert client.post('/api/render-pdf', json={'cv_json': '{not json'}).status_code == 400

    # --- Downloads ---
    def test_download_rejects_traversal_and_missing_files(self, client):
        assert client.get('/api/download-cv/..%2F..%2Fsecret.pdf').status_code == 400
        assert client.get('/api/download-cv/does_not_exist.pdf').status_code == 404
        assert client.get('/api/download-json/does_not_exist.json').status_code == 404

    # --- Follow-ups ---
    @patch('app.main.answer_question')
    def test_answer_question_answers_each_question(self, mock_answer, client):
        mock_answer.side_effect = lambda cv, jd, q, model: f"answer to {q}"
        response = client.post('/api/answer-question', json={
            'cv_json': {"CV": {}}, 'job_description': "jd", 'question': ["Why us?", "Why you?"], 'model': 'gemini/x',
        })
        assert response.status_code == 200
        body = response.get_json()
        assert [a['question'] for a in body['answers']] == ["Why us?", "Why you?"]
        assert body['answer'] == ["answer to Why us?", "answer to Why you?"]

    @patch('app.main.generate_cover_letter')
    def test_cover_letter(self, mock_cover, client):
        mock_cover.return_value = "Dear team"
        response = client.post('/api/generate-cover-letter', json={'cv_json': {"CV": {}}, 'job_description': "jd"})
        assert response.status_code == 200
        assert response.get_json()['cover_letter'] == "Dear team"
        assert client.post('/api/generate-cover-letter', json={'cv_json': {}}).status_code == 400

    # --- Jobs CRUD / meta ---
    def test_delete_job_and_get_job(self, client):
        job_id = self._save_jobs(DB_JOB_1)[0]
        assert client.get(f'/api/jobs/{job_id}').get_json()['job']['title'] == DB_JOB_1['title']
        assert client.delete(f'/api/jobs/{job_id}').status_code == 200
        assert client.get(f'/api/jobs/{job_id}').status_code == 404
        assert client.delete(f'/api/jobs/{job_id}').status_code == 404

    def test_jobs_with_multiple_cvs_are_listed_once(self, client):
        from app.database import save_generated_cv
        job_id = self._save_jobs(DB_JOB_1)[0]
        save_generated_cv(job_id, "old.pdf", "{}")
        save_generated_cv(job_id, "new.pdf", "{}")
        jobs = client.get('/api/jobs').get_json()['jobs']
        assert len(jobs) == 1
        assert jobs[0]['cv_filename'] == "new.pdf"

    def test_models_endpoint(self, client):
        body = client.get('/api/models').get_json()
        assert body['providers'] == {'google': True, 'openrouter': False}
        assert any(m['id'] == body['default'] for m in body['models'])
        openrouter_models = [m for m in body['models'] if m['provider'] == 'openrouter']
        assert openrouter_models and not any(m['available'] for m in openrouter_models)

    @patch('app.main.scrape_online_jobs')
    def test_scrape_pages_forward_with_offset(self, mock_scrape, client):
        """Repeated scraper calls must page forward rather than re-fetching the same results."""
        def page(offset):
            return [{'site': 'indeed', 'job_url': f'http://example.com/p/{offset + i}', 'title': f'Job {offset + i}'}
                    for i in range(15)]
        self._save_jobs(*[{'title': 't', 'url': f'http://example.com/p/{i}', 'source': 'indeed'} for i in range(15)])
        mock_scrape.side_effect = lambda **kw: page(kw['offset'])

        response = client.get('/api/scrape-jobs?results_wanted=3&site_names=indeed')
        assert response.status_code == 200
        assert [j['url'] for j in response.get_json()['jobs']] == [f'http://example.com/p/{i}' for i in (15, 16, 17)]
        assert [c.kwargs['offset'] for c in mock_scrape.call_args_list] == [0, 15]


