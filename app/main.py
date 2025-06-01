# app/main.py
import os
import uuid
import json # For get_cv_content_from_file if handling JSON CVs directly
import secrets # For generating a fallback SECRET_KEY
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from selenium import webdriver
# -----------------------------------------------------------------------------
# IMPORTANT: Selenium WebDriver Configuration
#
# To use Selenium, the appropriate WebDriver for your browser (e.g., chromedriver
# for Chrome, geckodriver for Firefox) must be installed and accessible.
#
# 1. Installation: Download the WebDriver executable matching your browser version.
# 2. Accessibility:
#    a) PATH: Ensure the directory containing the WebDriver executable is in your
#       system's PATH environment variable. This is the simplest approach if
#       `webdriver.Chrome()` (or equivalent) is called without arguments.
#    b) Explicit Path: Alternatively, provide the path to the executable directly:
#       from selenium.webdriver.chrome.service import Service as ChromeService
#       service = ChromeService(executable_path='/path/to/your/chromedriver')
#       driver = webdriver.Chrome(service=service)
# 3. Automation Libraries: Consider using a library like `webdriver-manager`
#    which can automatically download and manage WebDrivers for you:
#       from webdriver_manager.chrome import ChromeDriverManager
#       service = ChromeService(ChromeDriverManager().install())
#       driver = webdriver.Chrome(service=service)
#
# The current basic implementation `driver = webdriver.Chrome()` assumes option 2a.
# -----------------------------------------------------------------------------
# from selenium.webdriver.chrome.service import Service as ChromeService # Example for explicit path
# from webdriver_manager.chrome import ChromeDriverManager # Example for webdriver-manager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException # Added TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

from urllib.parse import urlparse

# --- Global Variables ---
# SITE_SELECTORS stores configurations for website-specific element locators,
# loaded from `site_selectors.json` at application startup.
# This allows the AutoApply Selenium logic to adapt to different job site structures
# by using predefined selectors (ID, CSS, XPath, etc.) for common form fields
# (name, email, phone, CV upload) and the submit button.
# The `load_selector_config()` function below handles the loading.
# Refer to `site_selectors.json` for the expected structure and examples.
SITE_SELECTORS = {}

# --- Load Site Selector Configuration ---
def load_selector_config():
    global SITE_SELECTORS
    # Assuming main.py is in 'app/' and site_selectors.json is at project root '../'
    # Adjust path if your project structure is different.
    # os.path.dirname(__file__) gives the directory of the current file (app)
    # os.path.abspath() ensures it's an absolute path before going up.
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site_selectors.json')

    default_selectors = {
        "name": { "type": "id", "value": "full_name" },
        "email": { "type": "id", "value": "email" },
        "phone": { "type": "id", "value": "phone" },
        "cv_upload": { "type": "css", "value": "input[type='file']" },
        "submit_button": { "type": "id", "value": "submit_application" }
    }

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            SITE_SELECTORS = json.load(f)
            if "default" not in SITE_SELECTORS: # Ensure default is present
                SITE_SELECTORS["default"] = default_selectors
                print("Warning: 'default' selectors not found in site_selectors.json, using hardcoded defaults.")
            print(f"Successfully loaded site selectors from {config_path}")
    except FileNotFoundError:
        print(f"Error: site_selectors.json not found at {config_path}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from site_selectors.json at {config_path}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}
    except Exception as e:
        print(f"An unexpected error occurred while loading site_selectors.json: {e}. Using default selectors only.")
        SITE_SELECTORS = {"default": default_selectors}

load_selector_config() # Load configuration when module is loaded

# --- Selenium Helper Function ---
def _find_element_dynamically(driver, selector_config, field_name_for_logging="Unknown"):
    """
    Finds an element using a selector configuration.
    selector_config should be a dict like: {"type": "id", "value": "some_id"}
    Supported types: id, css, name, xpath, class_name, link_text, partial_link_text.
    """
    if not selector_config or not isinstance(selector_config, dict) or \
       not selector_config.get('type') or not selector_config.get('value'):
        print(f"Selector for '{field_name_for_logging}' is missing, invalid, or incomplete.")
        return None

    selector_type_str = selector_config['type'].lower()
    selector_value = selector_config['value']
    by_type = None
    timeout = 10 # seconds

    # Map string selector type to Selenium By object
    if selector_type_str == 'id':
        by_type = By.ID
    elif selector_type_str == 'css':
        by_type = By.CSS_SELECTOR
    elif selector_type_str == 'name':
        by_type = By.NAME
    elif selector_type_str == 'xpath':
        by_type = By.XPATH
    elif selector_type_str == 'class_name':
        by_type = By.CLASS_NAME
    elif selector_type_str == 'link_text':
        by_type = By.LINK_TEXT
    elif selector_type_str == 'partial_link_text':
        by_type = By.PARTIAL_LINK_TEXT
    else:
        print(f"Unsupported selector type '{selector_type_str}' for '{field_name_for_logging}'.")
        return None

    try:
        wait = WebDriverWait(driver, timeout)
        if field_name_for_logging == 'Submit Button': # Specific handling for submit button
            element = wait.until(
                EC.element_to_be_clickable((by_type, selector_value))
            )
        else: # For all other elements, check for presence
            element = wait.until(
                EC.presence_of_element_located((by_type, selector_value))
            )
        print(f"Found '{field_name_for_logging}' using {selector_type_str}: {selector_value}")
        return element
    except TimeoutException:
        print(f"'{field_name_for_logging}' not found within {timeout}s using {selector_type_str}: {selector_value}")
        return None
    except Exception as e: # Catch other potential errors during find or wait
        print(f"An unexpected error occurred while finding '{field_name_for_logging}' using {selector_type_str}: {selector_value}. Error: {e}")
        return None

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
from .database import init_db, save_job, get_jobs, get_job_by_id, save_generated_cv, set_job_cv_generated_status, toggle_cv_generated_status # Updated import

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

    # --- API Endpoints ---
    @app.route('/')
    def index():
        # This will look for templates/index.html in the app folder
        return render_template('index.html')

    @app.route('/api/auto-apply/<int:job_id>', methods=['POST'])
    def auto_apply(job_id):
        """
        Attempts to auto-apply to a job by navigating to its URL and filling
        form fields using Selenium.

        Key Limitations:
        - On-Platform Focus: The current implementation is primarily designed for
          on-platform application forms on sites like LinkedIn and Indeed.
          It may not work if the 'Apply' button redirects to an external company
          career portal (ATS).
        - CAPTCHAs: Automation will likely fail if CAPTCHAs are encountered.
          The script does not include CAPTCHA solving capabilities.
        - Complex Forms: Highly complex or multi-page forms (beyond a single
          'continue' or 'submit' action) might not be fully completed. The current
          submit logic is basic and attempts a single submission.
        - Selector Maintenance: Selectors in `site_selectors.json` are based on
          observed HTML structures and may need frequent updates as websites change.
          This is a critical point of brittleness for UI automation.
        """
        job = get_job_by_id(job_id)
        if job is None:
            return jsonify({"error": "Job not found"}), 404

        job_url = job.get('url')
        if not job_url:
            return jsonify({"error": "Job found, but URL is missing"}), 500

        request_data = request.get_json()
        tailored_cv_data = None
        pdf_filename = None

        if request_data:
            tailored_cv_data = request_data.get('tailored_cv')
            # The `pdf_filename` is expected in the request body, provided by the client.
            # This filename should correspond to a PDF previously generated by the
            # `tailor_cv_endpoint` and stored in `app.config['GENERATED_PDFS_FOLDER']`.
            # Its presence and the file's existence on server are validated below.
            pdf_filename = request_data.get('pdf_filename')

        # --- CV PDF Path Validation ---
        # The client must provide `pdf_filename`. This filename is then used to
        # construct the full server path to the PDF in the `GENERATED_PDFS_FOLDER`.
        # The existence of this file is verified before proceeding.
        if not pdf_filename:
            return jsonify({"error": "CV PDF filename not provided for AutoApply."}), 400

        safe_pdf_filename = secure_filename(pdf_filename) # Sanitize filename
        cv_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], safe_pdf_filename)

        if not os.path.exists(cv_pdf_path):
            return jsonify({"error": "Specified CV PDF not found on server.", "filename": safe_pdf_filename}), 400

        if not tailored_cv_data:
            # Handle missing CV data gracefully for now
            print(f"Warning: No tailored CV data (JSON) received for job ID {job_id}, but PDF filename '{safe_pdf_filename}' was provided and found. Proceeding.")
            # In a real scenario, might return an error or use a default CV from user profile if JSON is also needed.

        # --- Selector Configuration Logic ---
        # Determine which set of selectors (domain-specific from site_selectors.json
        # or default) to use based on the job_url's domain. This allows the Selenium
        # logic to adapt to different website HTML structures by looking up the
        # appropriate locators in the pre-loaded SITE_SELECTORS dictionary.
        try:
            parsed_url = urlparse(job_url)
            domain = parsed_url.netloc.replace('www.', '') # Simple domain extraction
        except Exception as e_parse_url:
            print(f"Error parsing job_url '{job_url}': {e_parse_url}. Using default selectors.")
            domain = "default" # Fallback to default if URL parsing fails

        current_selectors = SITE_SELECTORS.get(domain, SITE_SELECTORS.get("default", {}))
        if domain != "default" and current_selectors == SITE_SELECTORS.get("default", {}):
            print(f"Selectors for domain '{domain}' not found. Using default selectors.")
        else:
            print(f"Using selectors for domain: {domain if domain != 'default' else 'default'}")


        driver = None
        try:
            # Initialize WebDriver. Assumes chromedriver is in PATH.
            # For robust setup, use webdriver_manager or specify service object:
            # driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
            # For now, basic initialization:
            driver = webdriver.Chrome()

            # Navigate to the job URL
            driver.get(job_url)
            time.sleep(2) # Allow page to load a bit, can be replaced by explicit waits

            # --- Manual Login Pause ---
            # This section pauses script execution to allow the user to manually
            # log in to the target website in the Selenium-controlled browser window.
            # This is necessary for sites requiring authentication before application submission.
            # Clear instructions are printed to the server console.
            # `manual_login_pause_seconds` determines the pause duration.
            # Automation resumes after the pause, regardless of login success at this stage.
            manual_login_pause_seconds = 120
            # The 'domain' variable is derived from job_url a few lines above for selector logic.
            print(f"--- MANUAL LOGIN REQUIRED FOR: {domain} ---")
            print(f"The script will now pause for {manual_login_pause_seconds} seconds.")
            print(f"Please log in to '{domain}' in the automated browser window that has opened.")
            print(f"Once logged in, please leave the browser window open.")
            print(f"The script will automatically continue after the pause.")
            print(f"----------------------------------------------------")
            time.sleep(manual_login_pause_seconds)
            print(f"--- RESUMING AUTOMATION FOR: {domain} ---")
            print(f"Resuming automated form filling.")
            print(f"If login was not successful or the correct page is not active, subsequent steps may fail.")
            print(f"--------------------------------------------------")

            # Extract CV data for form filling
            personal_info = tailored_cv_data.get("PersonalInformation", {}) if tailored_cv_data else {}
            cv_name = personal_info.get("Name", "Default Name")
            cv_email = personal_info.get("EmailAddress", "default@example.com")
            cv_phone = personal_info.get("PhoneNumber", "0000000000")

            # --- Example Form Filling (Highly Simplified) ---
            # IMPORTANT NOTE ON FORM STRUCTURE:
            # The element locators used below (IDs, names, CSS selectors) are generic examples.
            # Real-world job application forms have vastly different HTML structures.
            # These locators WILL NEED TO BE ADAPTED for each specific job application site
            # to correctly identify the target input fields. This often involves inspecting
            # the webpage's HTML source to find suitable and stable selectors.

            # Name Field
            name_selector_config = current_selectors.get('name')
            name_field = _find_element_dynamically(driver, name_selector_config, "Name")
            if name_field:
                try:
                    name_field.send_keys(cv_name)
                    print(f"Filled 'Name' field with: {cv_name}")
                except Exception as e_fill:
                    print(f"Error filling 'Name' field: {e_fill}")

            # Email Field
            email_selector_config = current_selectors.get('email')
            email_field = _find_element_dynamically(driver, email_selector_config, "Email")
            if email_field:
                try:
                    email_field.send_keys(cv_email)
                    print(f"Filled 'Email' field with: {cv_email}")
                except Exception as e_fill:
                    print(f"Error filling 'Email' field: {e_fill}")

            # Phone Field
            phone_selector_config = current_selectors.get('phone')
            phone_field = _find_element_dynamically(driver, phone_selector_config, "Phone")
            if phone_field:
                try:
                    phone_field.send_keys(cv_phone)
                    print(f"Filled 'Phone' field with: {cv_phone}")
                except Exception as e_fill:
                    print(f"Error filling 'Phone' field: {e_fill}")

            # CV File Upload
            cv_upload_selector_config = current_selectors.get('cv_upload')
            cv_upload_field = _find_element_dynamically(driver, cv_upload_selector_config, "CV Upload")
            if cv_upload_field:
                # --- IMPORTANT: CV File Upload Path ---
                # The path `dummy_cv_file_path` currently points to a placeholder PDF
                # (`instance/dummy_cv_for_upload.pdf`) located on the server.
                #
                # For a real application, this mechanism needs to be robust:
                # 1. Identification: The correct, tailored PDF (generated by `tailor_cv_endpoint`)
                #    must be identified for the current application attempt. This might involve:
                #    - Passing the unique PDF filename from the client when AutoApply is clicked.
                #    - Storing a reference to the generated PDF in the user's session or
                #      associating it with the `job_id` temporarily.
                #    - Querying the `GENERATED_PDFS_FOLDER` for the most recent file
                #      attributable to this user/session (less reliable in concurrent scenarios).
                # 2. Accessibility: The identified PDF path must be accessible by the Selenium
                #    WebDriver process running on the server.
                #
                # Using a static dummy file path is a major simplification for this development stage.
                # Now using the dynamic cv_pdf_path validated earlier.
                try:
                    cv_upload_field.send_keys(cv_pdf_path)
                    print(f"Attempted to upload CV from: {cv_pdf_path}")
                except Exception as e_fill: # Catch more general errors for send_keys
                    print(f"Error uploading CV: {e_fill}")

            # Submit Button
            submit_button_config = current_selectors.get('submit_button')
            submit_button_element = _find_element_dynamically(driver, submit_button_config, "Submit Button")
            if submit_button_element:
                try:
                    print("Attempting to click submit button...")
                    submit_button_element.click()
                    time.sleep(5) # Allow time for page to react after submission
                    print("Clicked submit button.")
                except Exception as e_click:
                    print(f"Error clicking submit button: {e_click}")
            else:
                print("Submit button not found or not configured.")

            # The time.sleep(5) for general inspection is now after submit attempt or can be removed
            # if the submit click itself implies waiting.
            # For now, let's keep a final short sleep if no submit was clicked.
            if not submit_button_element:
                 time.sleep(5) # For visual inspection during dev; remove for production/tests.

            # --- Automated Screening Questions ---
            screening_questions_config = current_selectors.get("screening_questions", [])
            if screening_questions_config:
                print(f"Processing {len(screening_questions_config)} screening questions...")
                for q_config in screening_questions_config:
                    question_found_on_page = False
                    question_text_fragments = q_config.get("question_text_fragments", [])
                    target_answer_key = q_config.get("target_answer")
                    answer_selectors = q_config.get("answer_selectors", {})

                    if not question_text_fragments or not target_answer_key or not answer_selectors:
                        print(f"Skipping question due to incomplete configuration: {q_config.get('question_text_fragments', ['Unknown Question'])}")
                        continue

                    print(f"Attempting to find question containing any of: {question_text_fragments}")

                    # Try to find the question text on the page
                    # This is a generic approach. Robustness depends on site structure.
                    # We'll search for common text-holding elements.
                    possible_text_elements_xpaths = []
                    for fragment in question_text_fragments:
                        # Escaping quotes within the XPath string for `contains`
                        escaped_fragment = fragment.replace("'", "\\'").replace('"', '\\"')
                        possible_text_elements_xpaths.append(f"//*[self::p or self::label or self::span or self::div or self::legend or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6][contains(normalize-space(.), \"{escaped_fragment}\")]")

                    question_element = None
                    # Check a few common parent elements for the question text
                    # This is a simplified approach. A more robust solution might involve
                    # checking all elements or using more specific selectors if questions are in known containers.
                    for xpath_query in possible_text_elements_xpaths:
                        try:
                            # Use a shorter timeout for finding the question text itself
                            question_elements_found = WebDriverWait(driver, 5).until(
                                EC.presence_of_all_elements_located((By.XPATH, xpath_query))
                            )
                            if question_elements_found:
                                # For simplicity, assume the first visible one is the target.
                                # Real applications might need more logic to disambiguate.
                                for el in question_elements_found:
                                    if el.is_displayed(): # Check if element is visible
                                        question_element = el
                                        question_found_on_page = True
                                        print(f"Found question text element for fragments {question_text_fragments} using XPath: {xpath_query}")
                                        break
                                if question_found_on_page:
                                    break
                        except TimeoutException:
                            # This fragment didn't find a visible element, try next fragment's XPath
                            continue
                        except Exception as e_find_q_text:
                            print(f"Error while searching for question text with XPath {xpath_query}: {e_find_q_text}")
                            continue # Try next XPath

                    if question_found_on_page and question_element:
                        print(f"Question containing '{question_text_fragments}' found. Attempting to answer '{target_answer_key}'.")

                        answer_selector_config = answer_selectors.get(target_answer_key)
                        if not answer_selector_config:
                            print(f"No selector found for target answer '{target_answer_key}' for question '{question_text_fragments}'.")
                            continue

                        # Use _find_element_dynamically to find the answer choice
                        # Pass a more descriptive name for logging
                        answer_element_name = f"Answer '{target_answer_key}' for question '{question_text_fragments[0]}...'"
                        answer_element = _find_element_dynamically(driver, answer_selector_config, answer_element_name)

                        if answer_element:
                            try:
                                # Scroll into view if necessary, then click
                                driver.execute_script("arguments[0].scrollIntoView(true);", answer_element)
                                time.sleep(0.5) # Brief pause after scroll before click

                                # For radio buttons or checkboxes, a direct click is usually what's needed.
                                # If it's a dropdown, _find_element_dynamically would get the dropdown,
                                # and then further Select logic would be needed. Assuming clickable inputs for now.
                                answer_element.click()
                                print(f"Successfully clicked answer '{target_answer_key}' for question '{question_text_fragments}'.")
                            except Exception as e_click_answer:
                                print(f"Error clicking answer '{target_answer_key}' for question '{question_text_fragments}': {e_click_answer}")
                        else:
                            print(f"Could not find answer element for '{target_answer_key}' for question '{question_text_fragments}'.")
                    else:
                        print(f"Question containing any of '{question_text_fragments}' not found or not visible on the page.")
                print("Finished processing screening questions.")
            else:
                print("No screening questions configured for this site or in default.")

            # The manual_login_pause_seconds variable was defined earlier in this 'try' block.
            # The domain variable was also defined earlier based on job_url.
            # The 'manual_login_prompt_details' field in the response informs the client
            # that a pause for manual login was initiated.
            return jsonify({
                "message": f"Navigated to job URL and attempted basic form filling for {job_url}. " +
                           "Please verify the application on the site. See server logs for field-specific status.",
                "job_url": job_url,
                "cv_data_received": bool(tailored_cv_data),
                "manual_login_prompt_details": f"User was prompted via server console to manually log in to '{domain}' during a {manual_login_pause_seconds}-second pause. Automation resumed afterwards."
            }), 200

        except Exception as e_selenium:
            # Catch broad exceptions from Selenium operations (init, navigation)
            # More specific exceptions (WebDriverException, TimeoutException) can be caught if needed.
            error_message = f"Selenium operation failed: {str(e_selenium)}"
            print(f"Error during AutoApply for job ID {job_id} at URL {job_url}: {error_message}")

            # Determine if it was WebDriver init or navigation failure based on driver state
            if driver is None and not "driver.get" in str(e_selenium).lower(): # Heuristic: if driver is still None, init likely failed
                 return jsonify({"error": "WebDriver initialization failed.", "details": str(e_selenium)}), 500
            else: # Otherwise, assume navigation or other Selenium step failed
                 return jsonify({"error": f"Failed to process job URL: {job_url}", "details": str(e_selenium)}), 500
        finally:
            if driver:
                driver.quit()

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
                    "tailored_cv_json": json.loads(tailored_cv_json_str), # Return parsed JSON
                    "pdf_filename": unique_pdf_filename # New field
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

    @app.route('/api/jobs/<int:job_id>/toggle-applied', methods=['POST']) # URL path remains for client compatibility
    def api_toggle_cv_generated_status_endpoint(job_id): # Function name updated
        """API endpoint to toggle the 'CV generated' status of a job."""
        import sqlite3 # Import for specific exception handling
        try:
            result = toggle_cv_generated_status(job_id) # Call updated DB function
            if result is None:
                return jsonify({"error": "Job not found"}), 404

            # 'result' is expected to be {"id": job_id, "applied": new_status}
            # The key "applied" in the result dict refers to the database column name.
            return jsonify({
                "message": "CV generated status updated successfully", # Updated message
                "job_id": result["id"],
                "new_status": result["applied"]
            }), 200
        except sqlite3.Error as e:
            # Log the exception e if you have logging configured
            print(f"Database error on toggle CV generated status for job_id {job_id}: {e}")
            return jsonify({"error": "Database operation failed"}), 500
        except Exception as e:
            # Catch any other unexpected errors
            print(f"Unexpected error on toggle CV generated status for job_id {job_id}: {e}")
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
        job_ids = request.form.getlist('job_ids[]') # Retrieve job IDs

        if not job_descriptions:
            return jsonify({"error": "No job descriptions provided"}), 400

        # Basic validation for consistent lengths of received arrays
        if not (len(job_descriptions) == len(job_titles) == len(job_ids)):
            print(f"Warning: Mismatch in lengths of job_descriptions ({len(job_descriptions)}), "
                  f"job_titles ({len(job_titles)}), and job_ids ({len(job_ids)}). "
                  "This may lead to incorrect associations in batch results.")
            # Fallback for job_titles if its length doesn't match job_descriptions
            if len(job_descriptions) != len(job_titles):
                job_titles = [f"Job Description {i+1}" for i in range(len(job_descriptions))]
            # job_ids will be accessed conditionally using index to avoid errors if its length is short

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
            job_title_summary = job_titles[index] # Assumes job_titles is now aligned or correctly fallen back
            current_job_id = job_ids[index] if index < len(job_ids) else None

            if not jd_content:
                results.append({
                    "job_id": current_job_id,
                    "job_title_summary": job_title_summary,
                    "status": "error",
                    "message": "Empty job description provided."
                })
                continue

            tailored_cv_json_str = None # Initialize for broader scope
            try:
                tailored_cv_json_str = process_cv_and_jd(
                    cv_content_str, # Processed CV text
                    jd_content,     # Current job description
                    cv_template_content_str,
                    current_api_key
                )

                if not tailored_cv_json_str:
                    results.append({
                        "job_id": current_job_id,
                        "job_title_summary": job_title_summary,
                        "status": "error",
                        "message": "Failed to tailor CV (API processing failed)."
                    })
                    continue

                # PDF Generation for this tailored CV
                # Sanitize title for use in filename (optional, uuid is main uniqueness)
                safe_title_part = secure_filename(job_title_summary)[:30] if job_title_summary else "job"
                unique_pdf_filename = f"tailored_cv_{safe_title_part}_{uuid.uuid4()}.pdf"
                full_pdf_path = os.path.join(app.config['GENERATED_PDFS_FOLDER'], unique_pdf_filename)

                pdf_generation_success = generate_cv_pdf_from_json_string(tailored_cv_json_str, full_pdf_path)

                if pdf_generation_success:
                    # Save to generated_cvs table
                    if tailored_cv_json_str and unique_pdf_filename: # Ensure we have data to save
                        generated_cv_db_id = save_generated_cv(
                            job_id=current_job_id, # This variable should be defined from job_ids[index]
                            pdf_filename=unique_pdf_filename,
                            tailored_cv_json_string=tailored_cv_json_str
                        )
                        if generated_cv_db_id:
                            print(f"Batch: Saved generated CV metadata for job_id {current_job_id}, pdf {unique_pdf_filename}. DB ID: {generated_cv_db_id}")
                        else:
                            print(f"Batch: WARNING - Failed to save generated CV metadata for job_id {current_job_id}, pdf {unique_pdf_filename} to DB.")
                    else:
                        print(f"Batch: WARNING - Missing tailored_cv_json_str or unique_pdf_filename for job_id {current_job_id}. Cannot save to DB.")

                    # After saving CV metadata, update the job's 'applied' status (meaning CV generated)
                    if generated_cv_db_id and current_job_id is not None:
                        status_updated = set_job_cv_generated_status(
                            job_id=current_job_id,
                            status=True
                        )
                        if status_updated:
                            print(f"Batch: Marked job_id {current_job_id} as 'CV generated' (applied=1).")
                        else:
                            print(f"Batch: WARNING - Failed to mark job_id {current_job_id} as 'CV generated'.")
                    elif current_job_id is None and generated_cv_db_id:
                        print(f"Batch: CV metadata saved (DB ID: {generated_cv_db_id}), but no job_id was associated with this batch item. Cannot mark 'CV generated'.")

                    results.append({
                        "job_id": current_job_id,
                        "job_title_summary": job_title_summary,
                        "status": "success",
                        "pdf_url": f"/api/download-cv/{unique_pdf_filename}",
                        "pdf_filename": unique_pdf_filename,
                        "tailored_cv_json": json.loads(tailored_cv_json_str),
                        "generated_cv_db_id": generated_cv_db_id # New field
                    })
                else:
                    results.append({
                        "job_id": current_job_id,
                        "job_title_summary": job_title_summary,
                        "status": "error",
                        "message": "Tailored, but PDF generation failed.",
                        "tailored_cv_json": json.loads(tailored_cv_json_str) if tailored_cv_json_str else None
                    })

            except Exception as e_proc:
                print(f"Error processing job description '{job_title_summary}': {e_proc}")
                results.append({
                    "job_id": current_job_id,
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
