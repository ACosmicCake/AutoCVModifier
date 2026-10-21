# app/main.py
import json
import logging
import os
import secrets  # For generating a fallback SECRET_KEY
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from . import database
from .cv_utils import (
    answer_question,
    generate_cover_letter,
    get_cv_content_from_file,
    load_cv_template,
    normalize_cv_data,
    process_cv_and_jd,
)
from .database import (
    delete_job,
    get_job,
    get_jobs,
    get_sources,
    init_db,
    job_url_exists,
    save_generated_cv,
    save_job,
)
from .job_scraper import SUPPORTED_JOBSPY_SITES, scrape_online_jobs
from .llm import DEFAULT_MODEL, LLMConfigError, LLMError, available_models, provider_status, resolve_model
from .pdf_generator import generate_cv_pdf_from_json_string  # Returns True/False

logger = logging.getLogger(__name__)

# --- Configuration ---
UPLOAD_FOLDER_NAME = 'uploads'
GENERATED_PDFS_FOLDER_NAME = 'generated_pdfs'
GENERATED_JSONS_FOLDER_NAME = 'generated_jsons'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'json'}
CV_FORMAT_FILENAME = 'CV_format.json'  # Path relative to project root


class TemplateError(Exception):
    """CV_format.json is missing or invalid."""


# --- App Initialization ---
def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    project_root = os.path.dirname(app.instance_path)

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # --- Load Environment Variables (.env at the project root) ---
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        logger.info("Loaded .env file from %s", dotenv_path)
    else:
        logger.info(".env file not found at %s. Relying on environment variables.", dotenv_path)

    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_key = secrets.token_hex(16)
        logger.warning("SECRET_KEY not set; using a temporary auto-generated key.")

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        UPLOAD_FOLDER=os.path.join(app.instance_path, UPLOAD_FOLDER_NAME),
        GENERATED_PDFS_FOLDER=os.path.join(app.instance_path, GENERATED_PDFS_FOLDER_NAME),
        GENERATED_JSONS_FOLDER=os.path.join(app.instance_path, GENERATED_JSONS_FOLDER_NAME),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB upload limit
        CV_FORMAT_FILE_PATH=os.path.join(project_root, CV_FORMAT_FILENAME),
        DATABASE=os.path.join(app.instance_path, 'jobs.db'),
        BATCH_MAX_WORKERS=int(os.environ.get('BATCH_MAX_WORKERS', 3)),
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.from_mapping(test_config)
    app.json.sort_keys = False  # keep CV sections in template order

    for folder_key in ('UPLOAD_FOLDER', 'GENERATED_PDFS_FOLDER', 'GENERATED_JSONS_FOLDER'):
        os.makedirs(app.config[folder_key], exist_ok=True)

    status = provider_status()
    if not any(status.values()):
        logger.warning("No LLM API key found. Set GOOGLE_API_KEY and/or OPENROUTER_API_KEY in .env.")

    # --- Initialize Database ---
    database.DATABASE_NAME = app.config['DATABASE']
    init_db()

    # --- Helper Functions ---
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def form_bool(name, default=False):
        value = request.form.get(name)
        if value is None:
            return default
        return value.strip().lower() in ('1', 'true', 'on', 'yes')

    def error(message, status_code):
        return jsonify({"error": message}), status_code

    def read_cv_input():
        """Returns (cv_text, None) or (None, error_response) from an uploaded file or pasted text."""
        file = request.files.get('cv_file')
        pasted = (request.form.get('cv_text') or '').strip()

        if file and file.filename:
            if not allowed_file(file.filename):
                return None, error("Invalid file type for CV. Use PDF, DOCX, TXT or JSON.", 400)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{secure_filename(file.filename) or 'cv.txt'}")
            try:
                file.save(temp_path)
                content = get_cv_content_from_file(temp_path)
            except Exception as e:
                logger.exception("Error saving or processing uploaded CV")
                return None, error(f"Error saving or processing file: {e}", 500)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError as e:
                        logger.warning("Could not remove uploaded file %s: %s", temp_path, e)
            if not content or not content.strip():
                return None, error("Could not extract text from the CV file. If it is a scanned PDF, paste the text instead.", 422)
            return content, None

        if pasted:
            return pasted, None
        if 'cv_file' in request.files:
            return None, error("No selected CV file", 400)
        return None, error("No CV file part: upload a CV file or paste your CV text.", 400)

    def read_template(include_summary):
        try:
            return load_cv_template(app.config['CV_FORMAT_FILE_PATH'], include_summary)
        except FileNotFoundError:
            logger.error("%s not found.", app.config['CV_FORMAT_FILE_PATH'])
            raise TemplateError("Server configuration error: CV format file not found.")
        except (OSError, ValueError) as e:
            logger.error("Error reading CV format file: %s", e)
            raise TemplateError(f"Server configuration error: Could not read CV format file ({e}).")

    def reserve_unique_file(folder, stem, ext):
        """Atomically creates an empty file with a unique name, so concurrent jobs never collide."""
        counter = 0
        while True:
            filename = f"{stem}{f'_{counter}' if counter else ''}.{ext}"
            path = os.path.join(folder, filename)
            try:
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return filename, path
            except FileExistsError:
                counter += 1

    def save_outputs(tailored_cv_json_str, job_title_hint=None):
        """Writes the tailored JSON and PDF to disk. Returns a dict describing the result."""
        try:
            cv_data = json.loads(tailored_cv_json_str)
        except (json.JSONDecodeError, TypeError):
            cv_data = {}
        cv_section = cv_data.get("CV", cv_data) if isinstance(cv_data, dict) else {}
        personal = cv_section.get("PersonalInformation") if isinstance(cv_section.get("PersonalInformation"), dict) else {}

        safe_applicant_name = secure_filename(str(personal.get("Name") or "")) or "UnknownApplicant"
        safe_job_title = secure_filename(str(job_title_hint or cv_section.get("JobTitle") or "")) or "Application"
        stem = f"CV_{safe_job_title[:60]}_{safe_applicant_name[:40]}"

        json_filename, json_path = reserve_unique_file(app.config['GENERATED_JSONS_FOLDER'], stem, 'json')
        with open(json_path, 'w', encoding='utf-8') as f_json:
            f_json.write(tailored_cv_json_str)

        pdf_filename, pdf_path = reserve_unique_file(app.config['GENERATED_PDFS_FOLDER'], stem, 'pdf')
        pdf_ok = generate_cv_pdf_from_json_string(tailored_cv_json_str, pdf_path)
        if not pdf_ok and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

        return {
            "cv_data": cv_data,
            "pdf_ok": pdf_ok,
            "pdf_filename": pdf_filename if pdf_ok else None,
            "pdf_download_url": f"/api/download-cv/{pdf_filename}" if pdf_ok else None,
            "json_filename": json_filename,
            "json_download_url": f"/api/download-json/{json_filename}",
            "job_title": cv_section.get("JobTitle") or job_title_hint or "",
        }

    def link_cv_to_job(job_id, outputs, tailored_cv_json_str):
        if job_id is None or not outputs["pdf_ok"]:
            return
        try:
            save_generated_cv(job_id, outputs["pdf_filename"], tailored_cv_json_str)
        except sqlite3.Error as e:
            logger.error("Could not link generated CV to job %s: %s", job_id, e)

    def parse_job_id(value):
        try:
            return int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    # --- Error handlers: always JSON for API routes ---
    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        if request.path.startswith('/api/'):
            message = "File too large (max 16 MB)." if e.code == 413 else e.description
            return jsonify({"error": message}), e.code
        return e

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            return handle_http_error(e)
        logger.exception("Unhandled error on %s", request.path)
        return jsonify({"error": "An unexpected server error occurred."}), 500

    # --- Pages ---
    @app.route('/')
    def index():
        return render_template('index.html')

    # --- Meta ---
    @app.route('/api/models', methods=['GET'])
    def api_models():
        return jsonify({
            "models": available_models(),
            "default": DEFAULT_MODEL,
            "providers": provider_status(),
            "sites": sorted(SUPPORTED_JOBSPY_SITES),
        })

    # --- CV tailoring ---
    @app.route('/api/tailor-cv', methods=['POST'])
    def tailor_cv_endpoint():
        model = (request.form.get('model') or DEFAULT_MODEL).strip()
        include_summary = form_bool('include_summary')
        job_id = parse_job_id(request.form.get('job_id'))
        job_description = (request.form.get('job_description') or '').strip()

        if not job_description and job_id is not None:
            job = get_job(job_id)
            job_description = (job or {}).get('description') or ''

        cv_content_str, err = read_cv_input()
        if err:
            return err
        if not job_description:
            return error("No job description provided", 400)

        try:
            cv_template_content_str = read_template(include_summary)
            resolve_model(model)
            tailored_cv_json_str = process_cv_and_jd(cv_content_str, job_description, cv_template_content_str,
                                                     model, include_summary)
        except TemplateError as e:
            return error(str(e), 500)
        except LLMConfigError as e:
            return error(str(e), 400)
        except LLMError as e:
            return error(f"The model call failed: {e}", 502)

        if not tailored_cv_json_str:
            return error("The model did not return a valid CV. Try again or choose a different model.", 502)

        outputs = save_outputs(tailored_cv_json_str)
        link_cv_to_job(job_id, outputs, tailored_cv_json_str)

        body = {
            "message": "CV tailored and PDF generated!" if outputs["pdf_ok"] else "CV tailored, but PDF generation failed.",
            "pdf_download_url": outputs["pdf_download_url"],
            "json_download_url": outputs["json_download_url"],
            "tailored_cv_json": outputs["cv_data"],
            "job_title": outputs["job_title"],
            "job_description": job_description,
            "model": model,
        }
        if not outputs["pdf_ok"]:
            body["error_pdf"] = "Failed to generate PDF from tailored CV. JSON is available."
            return jsonify(body), 500
        return jsonify(body)

    @app.route('/api/render-pdf', methods=['POST'])
    def render_pdf_endpoint():
        """Re-renders a PDF from (possibly hand-edited) CV JSON."""
        data = request.get_json(silent=True) or {}
        cv_json = data.get('cv_json')
        if isinstance(cv_json, str):
            try:
                cv_json = json.loads(cv_json)
            except json.JSONDecodeError as e:
                return error(f"CV JSON is not valid: {e}", 400)
        if not isinstance(cv_json, dict) or not cv_json:
            return error("Missing CV JSON", 400)

        cv_json = normalize_cv_data(cv_json)
        cv_json_str = json.dumps(cv_json, indent=2, ensure_ascii=False)
        outputs = save_outputs(cv_json_str)
        if not outputs["pdf_ok"]:
            return error("Failed to generate PDF from the CV JSON.", 500)
        link_cv_to_job(parse_job_id(data.get('job_id')), outputs, cv_json_str)
        return jsonify({
            "message": "PDF regenerated.",
            "pdf_download_url": outputs["pdf_download_url"],
            "json_download_url": outputs["json_download_url"],
            "tailored_cv_json": outputs["cv_data"],
        })

    @app.route('/api/batch-generate-cvs', methods=['POST'])
    def batch_generate_cvs_endpoint():
        model = (request.form.get('model') or DEFAULT_MODEL).strip()
        include_summary = form_bool('include_summary')
        job_ids = request.form.getlist('job_ids[]')
        job_descriptions = request.form.getlist('job_descriptions[]')
        job_titles = request.form.getlist('job_titles[]')

        cv_content_str, err = read_cv_input()
        if err:
            return err
        if not job_ids and not job_descriptions:
            return error("No job descriptions provided (select at least one job).", 400)
        if job_descriptions and job_ids and len(job_descriptions) != len(job_ids):
            return error("Mismatch in the number of job descriptions and job IDs received.", 400)

        try:
            cv_template_content_str = read_template(include_summary)
            resolve_model(model)
        except TemplateError as e:
            return error(str(e), 500)
        except LLMConfigError as e:
            return error(str(e), 400)

        # Build the work list. Descriptions and titles come from the database unless the client sent them.
        tasks = []
        count = max(len(job_ids), len(job_descriptions))
        for index in range(count):
            raw_id = job_ids[index] if index < len(job_ids) else None
            job_id = parse_job_id(raw_id)
            job = get_job(job_id) if job_id is not None else None
            description = job_descriptions[index] if index < len(job_descriptions) else (job or {}).get('description')
            title = job_titles[index] if index < len(job_titles) and job_titles[index] else (job or {}).get('title') or f"Job {index + 1}"
            tasks.append({"index": index, "raw_id": raw_id, "job_id": job_id, "job": job,
                          "description": (description or '').strip(), "title": title})

        def run_task(task):
            result = {"job_id": task["job_id"] if task["job_id"] is not None else task["raw_id"],
                      "job_title_summary": task["title"]}
            if task["raw_id"] is not None and task["job_id"] is None:
                return {**result, "status": "error", "message": f"Invalid job_id format: {task['raw_id']}. Must be an integer."}
            if task["job_id"] is not None and task["job"] is None and not task["description"]:
                return {**result, "status": "error", "message": "Job not found."}
            if not task["description"]:
                return {**result, "status": "error", "message": "Empty job description provided."}
            try:
                tailored = process_cv_and_jd(cv_content_str, task["description"], cv_template_content_str,
                                             model, include_summary)
                if not tailored:
                    return {**result, "status": "error", "message": "Failed to tailor CV (the model did not return valid JSON)."}
                outputs = save_outputs(tailored, job_title_hint=task["title"])
                if not outputs["pdf_ok"]:
                    return {**result, "status": "error", "message": "Tailored, but PDF generation failed.",
                            "json_url": outputs["json_download_url"]}
                if task["job_id"] is not None:
                    try:
                        save_generated_cv(task["job_id"], outputs["pdf_filename"], tailored)
                    except sqlite3.Error as e:
                        logger.error("Error saving generated CV for job %s: %s", task["job_id"], e)
                        return {**result, "status": "error", "pdf_url": outputs["pdf_download_url"],
                                "message": "CV and PDF created, but failed to save the record to the database."}
                return {**result, "status": "success", "pdf_url": outputs["pdf_download_url"],
                        "json_url": outputs["json_download_url"]}
            except LLMError as e:
                return {**result, "status": "error", "message": f"Failed to tailor CV: {e}"}
            except Exception as e:
                logger.exception("Error processing batch job %s", task["title"])
                return {**result, "status": "error", "message": f"An unexpected error occurred: {e}"}

        workers = max(1, min(app.config['BATCH_MAX_WORKERS'], len(tasks)))
        if workers == 1:
            results = [run_task(t) for t in tasks]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(run_task, tasks))  # map keeps the original order

        return jsonify({"results": results})

    @app.route('/api/download-cv/<path:filename>', methods=['GET'])
    def download_cv(filename):
        return _send_generated(app.config['GENERATED_PDFS_FOLDER'], filename)

    @app.route('/api/download-json/<path:filename>', methods=['GET'])
    def download_json(filename):
        return _send_generated(app.config['GENERATED_JSONS_FOLDER'], filename)

    def _send_generated(folder, filename):
        if secure_filename(filename) != filename:
            logger.warning("Attempt to download non-secured filename: %s", filename)
            return error("Invalid filename", 400)
        if not os.path.isfile(os.path.join(folder, filename)):
            return error("File not found", 404)
        inline = request.args.get('inline') in ('1', 'true')
        return send_from_directory(folder, filename, as_attachment=not inline)

    # --- Follow-ups ---
    @app.route('/api/generate-cover-letter', methods=['POST'])
    def generate_cover_letter_endpoint():
        data = request.get_json(silent=True)
        if not data:
            return error("Invalid request body", 400)
        cv_json = data.get('cv_json')
        job_description = data.get('job_description')
        model = data.get('model') or DEFAULT_MODEL
        if not cv_json or not job_description:
            return error("Missing CV JSON or job description", 400)
        try:
            resolve_model(model)
            cover_letter = generate_cover_letter(cv_json, job_description, model)
        except LLMConfigError as e:
            return error(str(e), 400)
        except LLMError as e:
            return error(f"Failed to generate cover letter: {e}", 502)
        if not cover_letter:
            return error("Failed to generate cover letter", 502)
        return jsonify({"cover_letter": cover_letter})

    @app.route('/api/answer-question', methods=['POST'])
    def answer_question_endpoint():
        data = request.get_json(silent=True)
        if not data:
            return error("Invalid request body", 400)
        cv_json = data.get('cv_json')
        job_description = data.get('job_description')
        questions = data.get('question') or data.get('questions')
        if isinstance(questions, str):
            questions = [questions]
        questions = [q.strip() for q in (questions or []) if isinstance(q, str) and q.strip()]
        model = data.get('model') or DEFAULT_MODEL

        if not cv_json or not job_description or not questions:
            return error("Missing CV JSON, job description, or questions", 400)
        try:
            resolve_model(model)
        except LLMConfigError as e:
            return error(str(e), 400)

        def answer_one(question):
            try:
                return {"question": question, "answer": answer_question(cv_json, job_description, question, model), "ok": True}
            except LLMError as e:
                return {"question": question, "answer": f"Could not generate an answer: {e}", "ok": False}

        with ThreadPoolExecutor(max_workers=min(4, len(questions))) as pool:
            answers = list(pool.map(answer_one, questions))
        if not any(a["ok"] for a in answers):
            return error(answers[0]["answer"], 502)
        return jsonify({"answers": answers, "answer": [a["answer"] for a in answers]})

    # --- Jobs ---
    @app.route('/api/scrape-jobs', methods=['GET'])
    def scrape_jobs_endpoint():
        site_names_list = [name.strip() for name in request.args.get('site_names', 'linkedin,indeed').split(',') if name.strip()]
        search_term = request.args.get('search_term', 'software engineer').strip() or 'software engineer'
        location = request.args.get('location', 'USA').strip()
        country_indeed = request.args.get('country_indeed', 'USA').strip() or 'USA'
        hours_old = request.args.get('hours_old', type=int)
        is_remote = request.args.get('is_remote') in ('1', 'true', 'on')
        results_wanted = max(1, min(request.args.get('results_wanted', 5, type=int) or 5, 100))

        if not site_names_list:
            return error("No site names provided for scraping.", 400)

        new_jobs_found = []
        processed_urls = set()
        batch_fetch_size = 15  # How many to request per site per JobSpy call
        max_iterations = 10    # Max number of scraping batches
        scanned = 0

        for iteration in range(max_iterations):
            batch = scrape_online_jobs(
                site_names=site_names_list,
                search_term=search_term,
                location=location,
                results_wanted=batch_fetch_size,
                country_indeed=country_indeed,
                offset=iteration * batch_fetch_size,  # page forward instead of re-fetching the same results
                hours_old=hours_old,
                is_remote=is_remote,
            )
            if batch is None:
                if iteration == 0:
                    return error("Failed to scrape jobs: scraper error on first attempt (the site may be blocking requests; try fewer sites).", 500)
                logger.warning("Scraper error after %d iterations. Returning what was found so far.", iteration)
                break
            if not batch:
                break

            for job_data in batch:
                scanned += 1
                job_url = job_data.get('job_url') or job_data.get('job_url_direct')
                if not job_url or job_url in processed_urls:
                    continue
                processed_urls.add(job_url)
                if job_url_exists(job_url):
                    continue

                db_job_data = {
                    'title': job_data.get('title'),
                    'company': job_data.get('company'),
                    'location': job_data.get('location'),
                    'description': job_data.get('description'),
                    'url': job_url,
                    'source': job_data.get('site'),
                    'raw_job_data': job_data,
                }
                if not db_job_data['source']:
                    continue
                new_id = save_job(db_job_data)
                if new_id is not None:
                    new_jobs_found.append({"id": new_id, "title": db_job_data['title'], "company": db_job_data['company'],
                                           "location": db_job_data['location'], "url": job_url, "source": db_job_data['source']})
                if len(new_jobs_found) >= results_wanted:
                    break

            if len(new_jobs_found) >= results_wanted:
                break
            if len(batch) < batch_fetch_size:  # the sites have no more results for this query
                break

        return jsonify({"jobs": new_jobs_found, "scanned": scanned})

    @app.route('/api/jobs', methods=['GET'])
    def api_get_jobs():
        """Jobs from the database with optional filters."""
        filters = {
            'keyword': request.args.get('keyword'),
            'location': request.args.get('location'),
            'source': request.args.get('source'),
            'applied_status': request.args.get('applied_status'),
        }
        cleaned_filters = {k: v for k, v in filters.items() if v}
        retrieved_jobs = get_jobs(cleaned_filters)
        for job in retrieved_jobs:
            if hasattr(job.get('date_scraped'), 'isoformat'):
                job['date_scraped'] = job['date_scraped'].isoformat()
        return jsonify({"jobs": retrieved_jobs, "sources": get_sources()})

    @app.route('/api/jobs/<int:job_id>', methods=['GET'])
    def api_get_job(job_id):
        job = get_job(job_id)
        if job is None:
            return error("Job not found", 404)
        return jsonify({"job": job})

    @app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
    def api_delete_job(job_id):
        if not delete_job(job_id):
            return error("Job not found", 404)
        return jsonify({"message": "Job deleted", "job_id": job_id})

    @app.route('/api/jobs/<int:job_id>/toggle-applied', methods=['POST'])
    def api_toggle_applied(job_id):
        """Toggles the 'applied' status of a job."""
        try:
            result = database.toggle_applied_status(job_id)
        except sqlite3.Error as e:
            logger.error("Database error on toggle applied status for job_id %s: %s", job_id, e)
            return error("Database operation failed", 500)
        if result is None:
            return error("Job not found", 404)
        return jsonify({
            "message": "Applied status updated successfully",
            "job_id": result["id"],
            "new_status": result["applied"],
        }), 200

    return app
