# AI CV Tailor & Job Assistant Web Application

## Overview
This project provides a web-based user interface for the AI-Powered CV Tailoring Program. It allows users to:
*   Tailor their CV to specific job descriptions using Google's Gemini API.
*   Generate a PDF of the tailored CV.
*   Scrape job listings from popular job boards using JobSpy.

The core application logic is built with Python and Flask, with a user-friendly frontend.

## Project Structure
The main application code is structured in the repository root.
```
/
|-- app/            # Contains the Flask application modules
|   |-- static/     # CSS, JavaScript, images
|   |-- templates/  # HTML templates
|   |-- __init__.py
|   |-- main.py     # Flask app routes and core logic
|   |-- cv_utils.py # CV processing and Gemini API interaction
|   |-- pdf_generator.py # PDF generation for CVs
|   |-- job_scraper.py   # Job scraping logic
|-- instance/       # Instance-specific config (e.g., uploads, generated PDFs)
|-- .env            # Environment variables (GOOGLE_API_KEY, SECRET_KEY)
|-- CV_format.json  # Structure for the CV (used by the app)
|-- requirements.txt # Python dependencies
|-- run.py          # Script to run the Flask development server
|-- README.md       # This file
|-- job_description.txt # Example job description file (can be used for testing UI)
|-- my_cv.json          # Example CV file (can be used for testing UI)
|-- my_cv.txt           # Example CV file (can be used for testing UI)
```

## Prerequisites
*   Python 3.8 or higher
*   `pip` (Python package installer)
*   Access to Google's Gemini API and a `GOOGLE_API_KEY`.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url> # Replace <repository_url> with the actual URL
    cd <repository_directory_name>
    ```

2.  **Create and Configure `.env` File (Project Root):**
    *   In the **root directory** of the cloned repository, create a file named `.env`.
    *   Add your Google API key and a Flask secret key:
        ```env
        # .env (This file should be in the root of your cloned repository)
        GOOGLE_API_KEY="YOUR_ACTUAL_GOOGLE_API_KEY"

        # Flask SECRET_KEY:
        # Used for session management and security.
        # - If left blank or not set, a temporary key is auto-generated at startup (ideal for quick local testing).
        # - For development requiring stable sessions or for any production use,
        #   set this to a strong, unique, randomly generated string.
        #   You can generate one using: python -c 'import secrets; print(secrets.token_hex(16))'
        SECRET_KEY=""
        ```
        Replace `"YOUR_ACTUAL_GOOGLE_API_KEY"` with your real API key.
        For SECRET_KEY, you can leave it blank for the app to auto-generate a temporary one, or set a persistent strong random string for more stable development/production, e.g., by running the python command suggested in the comments and pasting the output.

3.  **Create a Virtual Environment (Recommended, in the project root directory):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

4.  **Install Dependencies (in project root and with venv activated):**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

1.  **Activate your virtual environment** (e.g., `source venv/bin/activate`).
2.  **Run the Flask Development Server (from the project root):**
    ```bash
    python run.py
    ```
3.  **Access the Web UI:**
    Open your web browser and go to `http://127.0.0.1:5001` (or the host/port shown in the console if you configured it differently via environment variables in your `.env` file like `FLASK_RUN_HOST` or `FLASK_RUN_PORT`).

## Features & API Endpoints

The application provides the following features through a web interface and corresponding API endpoints:

*   **CV Tailoring:**
    *   **UI:** Upload CV (PDF, DOCX, TXT, JSON), paste job description, get tailored CV (JSON preview) and PDF download.
    *   **API:** `POST /api/tailor-cv`
        *   `cv_file`: Uploaded CV file.
        *   `job_description`: Text of the job description.
        *   Returns: JSON with tailored CV data and a PDF download link.

*   **Job Scraping:**
    *   **UI:** Enter search term, location, sites (comma-separated), and number of results to scrape. Supported sites: `indeed`, `linkedin`, `zip_recruiter`, `glassdoor`, `google`, `bayt`, `naukri`.
    *   **API:** `GET /api/scrape-jobs`
        *   Query Parameters: `search_term`, `location`, `site_names`, `results_wanted`.
        *   Returns: JSON list of scraped job details.

*   **Download Tailored CV:**
    *   **UI:** Link provided after successful CV tailoring.
    *   **API:** `GET /api/download-cv/<filename>`
        *   `<filename>`: The unique filename of the generated PDF.

*   **AutoApply to Jobs (Experimental):**
    *   **UI:** After tailoring a CV, "AutoApply" buttons become available for job listings. Clicking this button will attempt to open the job URL and (currently) simulate the application process.
    *   **API:** `POST /api/auto-apply/<job_id>`
        *   `<job_id>`: The ID of the job in the database.
        *   Returns: JSON with a success or error message.
    *   **Note:** This feature uses Selenium to automate browser interaction.
        *   The current form-filling capability is a **simulation/placeholder**. It navigates to the job page and waits but does not fill out actual application forms. Real-world application forms are complex and vary greatly.
        *   Requires `chromedriver` (or another compatible WebDriver for your browser) to be installed and accessible in your system's PATH.

## Technology Stack
*   **Backend:** Python, Flask
*   **AI Integration:** Google Gemini API (via google-genai package)
*   **Job Scraping:** JobSpy
*   **PDF Generation:** ReportLab
*   **File Handling:** PyPDF2 (for PDF text extraction), python-docx (for DOCX text extraction)
*   **Frontend:** HTML, Tailwind CSS, JavaScript

## Original Command-Line Tool
The original command-line Python scripts and associated files (like `cv_tailor.py`, `generate_cv.py`) have been superseded by the web application now structured in the repository root. The example text files (`my_cv.txt`, `my_cv.json`, `job_description.txt`) in the root directory can still be used as sources of content to copy-paste into the web UI.
```
