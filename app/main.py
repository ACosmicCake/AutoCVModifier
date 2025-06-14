# app/main.py
import os
import uuid
import json # For get_cv_content_from_file if handling JSON CVs directly
import secrets # For generating a fallback SECRET_KEY
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# --- Import refactored utility functions ---
# Assuming these files are in the same directory 'app'
from .cv_utils import (
    get_api_key,
    process_cv_and_jd,
    get_cv_from_text_file,
    get_cv_from_pdf_file,
    get_cv_from_docx_file,
    get_cv_from_json_file # Used in helper
)
from .pdf_generator import generate_cv_pdf_from_json_string # Returns True/False
# analyze_cv_with_gemini removed
from .job_scraper import scrape_online_jobs
from .database import init_db, save_job, get_jobs, toggle_applied_status, save_generated_cv # Added save_generated_cv

# --- Configuration ---
# UPLOAD_FOLDER will be relative to the 'instance' folder, which should be at project root
# So, when app is created, app.instance_path will be '.../cv_tailor_project/instance'
UPLOAD_FOLDER_NAME = 'uploads'
GENERATED_PDFS_FOLDER_NAME = 'generated_pdfs'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'json'}
CV_FORMAT_FILENAME = 'CV_format.json' # Path relative to project root

# --- App Initialization ---
def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True) # instance_relative_config=True
    project_root = os.path.dirname(app.instance_path) # Get project root (/path/to/repo)

    # --- Load Environment Variables ---
    # .env is now at the project root
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print(f"Loaded .env file from {dotenv_path}")
    else:
        print(f".env file not found at {dotenv_path}. Relying on environment variables.")

    # --- Determine SECRET_KEY ---
    secret_key_env = os.environ.get('SECRET_KEY')
    if not secret_key_env:
        secret_key = secrets.token_hex(16)
        print(f"Warning: SECRET_KEY not found in environment. Using a temporary, auto-generated key: {secret_key[:8]}...")
        print("For production or persistent sessions, set a fixed SECRET_KEY in your .env file or environment.")
    else:
        secret_key = secret_key_env

    # --- App Configuration ---
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        UPLOAD_FOLDER=os.path.join(app.instance_path, UPLOAD_FOLDER_NAME),
        GENERATED_PDFS_FOLDER=os.path.join(app.instance_path, GENERATED_PDFS_FOLDER_NAME),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB upload limit
        CV_FORMAT_FILE_PATH=os.path.join(project_root, CV_FORMAT_FILENAME) # Path to CV_format.json at project root
    )

    if test_config:
        app.config.from_mapping(test_config)

    # --- Ensure instance folders exist ---
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['GENERATED_PDFS_FOLDER'], exist_ok=True)
        print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
        print(f"Generated PDFs folder: {app.config['GENERATED_PDFS_FOLDER']}")
    except OSError as e:
        print(f"Error creating instance folders: {e}")
        # Depending on severity, might want to raise an error here

    # --- Load API Key (once during app creation) ---
    # get_api_key() is from cv_utils, assumes .env has been loaded
    # This api_key will be accessible within the app context if needed, or passed to functions
    # For simplicity, we'll retrieve it per request or pass it from here if it's complex to get.
    # The issue's example retrieves it once.
    app.config['GOOGLE_API_KEY'] = get_api_key()
    if not app.config['GOOGLE_API_KEY']:
        print("CRITICAL: GOOGLE_API_KEY not found after loading .env. Please set it in .env file at project root or as an environment variable.")
        # In a production app, you might want to prevent the app from starting.
        # For now, it will proceed, and endpoints requiring it will fail.

    # --- Initialize Database ---
    # Ensure the instance folder (where jobs.db will be) exists
    # init_db itself will create jobs.db in instance/ if it doesn't exist
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        init_db() # Call the database initialization function
        print(f"Database will be initialized at: {os.path.join(app.instance_path, 'jobs.db')}")
    except OSError as e:
        print(f"Error during instance path creation or DB initialization: {e}")
        # Consider if the app should halt if DB init fails. For now, it prints an error.

    # --- Helper Functions ---
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def get_cv_content_from_file(filepath):
        """Extracts text content from various CV file types."""
        ext = filepath.rsplit('.', 1)[1].lower()
        content = None
        if ext == 'pdf':
            content = get_cv_from_pdf_file(filepath)
        elif ext == 'docx':
            content = get_cv_from_docx_file(filepath)
        elif ext == 'txt':
            content = get_cv_from_text_file(filepath)
        elif ext == 'json':
            # get_cv_from_json_file returns a dict. For Gemini prompt, we need string.
            cv_data_dict = get_cv_from_json_file(filepath)
            if cv_data_dict:
                content = json.dumps(cv_data_dict, indent=2)

        if content is None:
            print(f"Could not extract content from file {filepath} with extension {ext}.")
        return content

    # --- API Endpoints ---
    @app.route('/')
    def index():
        # This will look for templates/index.html in the app folder
        return render_template('index.html')

    @app.route('/api/tailor-cv', methods=['POST'])
    def tailor_cv_endpoint():
        current_api_key = app.config.get('GOOGLE_API_KEY')
        if not current_api_key:
            return jsonify({"error": "Server configuration error: API key not available"}), 500

        if 'cv_file' not in request.files:
            return jsonify({"error": "No CV file part"}), 400
        file = request.files['cv_file']
        if file.filename == '':
            return jsonify({"error": "No selected CV file"}), 400

        job_description = request.form.get('job_description')
        if not job_description:
            return jsonify({"error": "No job description provided"}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                file.save(filepath)
                cv_content_str = get_cv_content_from_file(filepath)
            except Exception as e_save:
                print(f"Error saving or processing uploaded file: {e_save}")
                return jsonify({"error": f"Error saving or processing file: {str(e_save)}"}), 500
            finally:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath) # Clean up uploaded file
                    except OSError as e_remove:
                        print(f"Error removing uploaded file {filepath}: {e_remove}")


            if not cv_content_str:
                return jsonify({"error": "Could not extract text from CV file"}), 500

            try:
                with open(app.config['CV_FORMAT_FILE_PATH'], 'r', encoding='utf-8') as f:
                    cv_template_content_str = f.read()
            except FileNotFoundError:
                print(f"Error: {app.config['CV_FORMAT_FILE_PATH']} not found.")
                return jsonify({"error": f"Server configuration error: CV format file not found."}), 500
            except Exception as e_format:
                print(f"Error reading CV format file: {e_format}")
                return jsonify({"error": f"Server configuration error: Could not read CV format file."}), 500

            tailored_cv_json_str = process_cv_and_jd(
                cv_content_str,
                job_description,
                cv_template_content_str,
                current_api_key
            )

            if not tailored_cv_json_str:
                return jsonify({"error": "Failed to tailor CV using Gemini API"}), 500

            # --- PDF Generation ---
            unique_pdf_filename = f"tailored_cv_{uuid.uuid4()}.pdf"
            full_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], unique_pdf_filename)

            pdf_generation_success = generate_cv_pdf_from_json_string(tailored_cv_json_str, full_pdf_path)

            if pdf_generation_success:
                return jsonify({
                    "message": "CV Tailored and PDF Generated!",
                    "pdf_download_url": f"/api/download-cv/{unique_pdf_filename}",
                    "tailored_cv_json": json.loads(tailored_cv_json_str) # Return parsed JSON
                })
            else:
                # Still return the JSON CV even if PDF fails, with a warning.
                return jsonify({
                    "message": "CV Tailored, but PDF generation failed.",
                    "error_pdf": "Failed to generate PDF from tailored CV. JSON is available.",
                    "tailored_cv_json": json.loads(tailored_cv_json_str)
                }), 500 # Or 207 Multi-Status if preferred for partial success
        else:
            return jsonify({"error": "Invalid file type for CV"}), 400

    # CV Analysis endpoint removed

    @app.route('/api/scrape-jobs', methods=['GET'])
    def scrape_jobs_endpoint():
        site_names_str = request.args.get('site_names', 'linkedin,indeed')
        site_names_list = [name.strip() for name in site_names_str.split(',') if name.strip()]
        search_term = request.args.get('search_term', 'software engineer')
        location = request.args.get('location', 'USA')
        results_wanted = request.args.get('results_wanted', 5, type=int)
        country_indeed = request.args.get('country_indeed', 'USA') # Example site-specific param

        if not site_names_list:
            return jsonify({"error": "No site names provided for scraping."}), 400

        jobs = scrape_online_jobs(
            site_names=site_names_list,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            country_indeed=country_indeed
        )
        if jobs is not None: # scrape_online_jobs returns [] for no jobs, None for error
            # --- Save jobs to database ---
            if isinstance(jobs, list) and jobs: # Ensure jobs is a list and not empty
                for job in jobs:
                    # Assuming scrape_online_jobs returns a list of dicts
                    # and each dict contains the necessary fields for save_job.
                    # 'source' might need to be inferred or passed along from scrape_online_jobs
                    # For now, let's assume 'source' is part of the job dict from the scraper.
                    # The jobspy library returns 'site' as the source name.
                    # We'll map it to 'source' for our database schema and also add raw_job_data.
                    db_job_data = {
                        'title': job.get('title'),
                        'company': job.get('company'),
                        'location': job.get('location'),
                        'description': job.get('description'),
                        'url': job.get('job_url'), # jobspy uses 'job_url'
                        'source': job.get('site'), # jobspy uses 'site'
                        # date_scraped is handled by the database
                        'raw_job_data': job # Store the original job dict from the scraper
                    }
                    # Ensure essential fields like URL and source are present before saving
                    if db_job_data['url'] and db_job_data['source']:
                        save_job(db_job_data)
                    else:
                        print(f"Skipping job due to missing URL or source: {job.get('title')}")
            return jsonify({"jobs": jobs})
        else:
            return jsonify({"error": "Failed to scrape jobs or an error occurred"}), 500

    @app.route('/api/jobs', methods=['GET'])
    def api_get_jobs():
        """API endpoint to get jobs from the database with optional filters."""
        filters = {
            'keyword': request.args.get('keyword'),
            'location': request.args.get('location'),
            'source': request.args.get('source'),
            'applied_status': request.args.get('applied_status') # Get the new filter
        }

        # Clean up None values from filters to avoid passing them if get_jobs expects no key
        # or ensure get_jobs handles None/empty string values appropriately (which it does for applied_status).
        # For keyword, location, source, if they are None, get_jobs won't add a clause.
        # For applied_status, get_jobs handles None or 'all' by not filtering.
        # So, direct pass-through of None is fine.
        # However, if a filter was an empty string from query param and you want to treat it as 'not set',
        # then cleaning is good:
        cleaned_filters = {k: v for k, v in filters.items() if v is not None and v != ''}

        retrieved_jobs = get_jobs(cleaned_filters) # get_jobs is from database.py

        # The 'date_scraped' is a datetime object, ensure it's JSON serializable (string)
        # get_jobs already converts rows to dicts, so date_scraped should be fine if stored as TEXT/TIMESTAMP
        # If it's a Python datetime object, it needs conversion:
        for job in retrieved_jobs:
            if hasattr(job['date_scraped'], 'isoformat'): # Check if it's a datetime object
                 job['date_scraped'] = job['date_scraped'].isoformat()
            # If date_scraped is already a string from DB (e.g. due to how it was stored or sqlite3.Row behavior),
            # this conversion might not be strictly necessary but is good for ensuring format.
            # SQLite typically returns strings for TIMESTAMP if not handled by a custom adapter/converter.

        return jsonify({"jobs": retrieved_jobs})

    @app.route('/api/jobs/<int:job_id>/toggle-applied', methods=['POST'])
    def api_toggle_applied(job_id):
        """API endpoint to toggle the 'applied' status of a job."""
        import sqlite3 # Import for specific exception handling
        try:
            result = toggle_applied_status(job_id)
            if result is None:
                return jsonify({"error": "Job not found"}), 404

            # 'result' is expected to be {"id": job_id, "applied": new_status}
            return jsonify({
                "message": "Applied status updated successfully",
                "job_id": result["id"],
                "new_status": result["applied"]
            }), 200
        except sqlite3.Error as e:
            # Log the exception e if you have logging configured
            print(f"Database error on toggle applied status for job_id {job_id}: {e}")
            return jsonify({"error": "Database operation failed"}), 500
        except Exception as e:
            # Catch any other unexpected errors
            print(f"Unexpected error on toggle applied status for job_id {job_id}: {e}")
            return jsonify({"error": "An unexpected server error occurred"}), 500


    @app.route('/api/batch-generate-cvs', methods=['POST'])
    def batch_generate_cvs_endpoint():
        current_api_key = app.config.get('GOOGLE_API_KEY')
        if not current_api_key:
            return jsonify({"error": "Server configuration error: API key not available"}), 500

        if 'cv_file' not in request.files:
            return jsonify({"error": "No CV file part"}), 400

        cv_file = request.files['cv_file']
        if cv_file.filename == '':
            return jsonify({"error": "No selected CV file"}), 400

        job_descriptions = request.form.getlist('job_descriptions[]')
        job_titles = request.form.getlist('job_titles[]') # For summary in results
        job_ids = request.form.getlist('job_ids[]') # Retrieve job_ids

        if not job_descriptions:
            return jsonify({"error": "No job descriptions provided"}), 400
        
        if not job_ids:
            return jsonify({"error": "No job IDs provided"}), 400

        if len(job_descriptions) != len(job_titles) or len(job_descriptions) != len(job_ids):
             # Fallback for titles, but job_ids length mismatch is more critical
            job_titles = [f"Job {i+1}" for i in range(len(job_descriptions))] # Keep this for titles
            if len(job_descriptions) != len(job_ids):
                # It's crucial that job_ids align with descriptions for saving CVs correctly.
                # Log this error, as client-side should prevent this.
                print(f"Error: Mismatch in lengths: descriptions ({len(job_descriptions)}), ids ({len(job_ids)})")
                return jsonify({"error": "Mismatch in the number of job descriptions and job IDs received."}), 400

        results = []
        cv_content_str = None
        temp_cv_filepath = None

        if cv_file and allowed_file(cv_file.filename):
            # Save CV file temporarily to process it
            # Use a unique name for the temp CV file in case of concurrent requests (though Python's UUID might be overkill here)
            temp_cv_filename = f"temp_cv_{uuid.uuid4()}_{secure_filename(cv_file.filename)}"
            temp_cv_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_cv_filename)

            try:
                cv_file.save(temp_cv_filepath)
                cv_content_str = get_cv_content_from_file(temp_cv_filepath)
                if not cv_content_str:
                    return jsonify({"error": "Could not extract text from uploaded CV file"}), 500
            except Exception as e_save:
                print(f"Error saving or processing uploaded CV file for batch: {e_save}")
                return jsonify({"error": f"Error saving or processing CV file: {str(e_save)}"}), 500
        else:
            return jsonify({"error": "Invalid CV file type"}), 400

        # Load CV format template (once)
        try:
            with open(app.config['CV_FORMAT_FILE_PATH'], 'r', encoding='utf-8') as f:
                cv_template_content_str = f.read()
        except Exception as e_format:
            print(f"Error reading CV format file: {e_format}")
            if temp_cv_filepath and os.path.exists(temp_cv_filepath): # Cleanup
                os.remove(temp_cv_filepath)
            return jsonify({"error": "Server configuration error: Could not read CV format file."}), 500

        # Process each job description
        for index, jd_content in enumerate(job_descriptions):
            job_title_summary = job_titles[index] if index < len(job_titles) else f"Job Description {index + 1}"
            current_job_id_str = job_ids[index]
            
            try:
                job_id_int = int(current_job_id_str) # Convert job_id to int
            except ValueError:
                print(f"Error: Invalid job_id format '{current_job_id_str}' for job '{job_title_summary}'. Skipping.")
                results.append({
                    "job_id": current_job_id_str, # Keep original string for reference in result
                    "job_title_summary": job_title_summary,
                    "status": "error",
                    "message": f"Invalid job_id format: {current_job_id_str}. Must be an integer."
                })
                continue

            if not jd_content:
                results.append({
                    "job_id": job_id_int,
                    "job_title_summary": job_title_summary,
                    "status": "error",
                    "message": "Empty job description provided."
                })
                continue

            try:
                tailored_cv_json_str = process_cv_and_jd(
                    cv_content_str, # Processed CV text
                    jd_content,     # Current job description
                    cv_template_content_str,
                    current_api_key
                )

                if not tailored_cv_json_str:
                    results.append({
                        "job_id": job_id_int,
                        "job_title_summary": job_title_summary,
                        "status": "error",
                        "message": "Failed to tailor CV (API processing failed)."
                    })
                    continue

                # PDF Generation for this tailored CV
                safe_title_part = secure_filename(job_title_summary)[:30] if job_title_summary else "job"
                # Ensure unique_pdf_filename is just the name, not the full path
                unique_pdf_filename_only = f"tailored_cv_{safe_title_part}_{job_id_int}_{uuid.uuid4()}.pdf"
                full_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], unique_pdf_filename_only)

                pdf_generation_success = generate_cv_pdf_from_json_string(tailored_cv_json_str, full_pdf_path)

                if pdf_generation_success:
                    # Save to generated_cvs table
                    try:
                        save_generated_cv(job_id_int, unique_pdf_filename_only, tailored_cv_json_str)
                        results.append({
                            "job_id": job_id_int,
                            "job_title_summary": job_title_summary,
                            "status": "success",
                            "pdf_url": f"/api/download-cv/{unique_pdf_filename_only}"
                        })
                    except Exception as e_db_save:
                        print(f"Error saving generated CV to database for job ID {job_id_int}: {e_db_save}")
                        results.append({
                            "job_id": job_id_int,
                            "job_title_summary": job_title_summary,
                            "status": "error",
                            "message": "CV generated and PDF created, but failed to save record to database.",
                            "pdf_url": f"/api/download-cv/{unique_pdf_filename_only}" # Still provide URL if PDF was made
                        })
                else:
                    results.append({
                        "job_id": job_id_int,
                        "job_title_summary": job_title_summary,
                        "status": "error",
                        "message": "Tailored, but PDF generation failed."
                        # Optionally include tailored_cv_json_str here if useful for debugging
                    })

            except Exception as e_proc:
                print(f"Error processing job description '{job_title_summary}' for job ID {job_id_int}: {e_proc}")
                results.append({
                    "job_id": job_id_int,
                    "job_title_summary": job_title_summary,
                    "status": "error",
                    "message": f"An unexpected error occurred: {str(e_proc)}"
                })

        # Clean up the temporarily saved CV file
        if temp_cv_filepath and os.path.exists(temp_cv_filepath):
            try:
                os.remove(temp_cv_filepath)
            except OSError as e_remove:
                print(f"Error removing temporary CV file {temp_cv_filepath}: {e_remove}")

        return jsonify({"results": results})

    @app.route('/api/download-cv/<filename>', methods=['GET'])
    def download_cv(filename):
        # Ensure filename is secure and points to the correct directory
        safe_filename = secure_filename(filename)
        if not safe_filename == filename: # Basic check against path manipulation
            print(f"Attempt to download non-secured filename: {filename}")
            return jsonify({"error": "Invalid filename"}), 400

        pdf_dir = app.config['GENERATED_PDFS_FOLDER']
        safe_path = os.path.join(pdf_dir, safe_filename)

        # Security: Check if the resolved path is still within the intended directory
        if not os.path.abspath(safe_path).startswith(os.path.abspath(pdf_dir)):
            print(f"Directory traversal attempt: {safe_filename}")
            return jsonify({"error": "Access denied"}), 403

        if os.path.exists(safe_path):
            try:
                return send_file(safe_path, as_attachment=True)
            except Exception as e:
                print(f"Error sending file {safe_path}: {e}")
                return jsonify({"error": "Could not send file"}), 500
        else:
            print(f"Download request for non-existent file: {safe_path}")
            return jsonify({"error": "File not found"}), 404

    return app

# The run.py script in the project root will use this create_app function.
# Example for run.py:
# from app.main import create_app
# app = create_app()
# if __name__ == '__main__':
#     app.run(debug=True, port=5001)
