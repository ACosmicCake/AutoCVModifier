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
            return jsonify({"jobs": jobs})
        else:
            return jsonify({"error": "Failed to scrape jobs or an error occurred"}), 500

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
