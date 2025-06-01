# AutoApply MVP: Infrastructure and Environment Setup Guide

## 1. Introduction

**Purpose:**
This document details the necessary infrastructure, tools, and initial setup steps required to begin the development of the AutoApply Minimum Viable Product (MVP). It covers version control, development environment, browser automation, AI model access, and basic data storage.

**Goal:**
To establish a functional and consistent development environment that enables the project team to efficiently implement the core features of the AutoApply MVP based on the conceptual designs.

## 2. Core Components & Setup Instructions

### 2.1. Version Control System

-   **Tool:** Git
-   **Hosting Provider:** GitHub (Recommended, but GitLab, Bitbucket, or similar are also suitable)
-   **Setup Steps:**
    1.  **Create Repository:**
        *   On your chosen hosting provider, create a new private repository named `autoapply_mvp_implementation` (or a similar descriptive name).
    2.  **Branching Strategy:**
        *   Establish a main branch (e.g., `main` or `master`) for stable releases.
        *   Create a development branch (e.g., `develop`) branched from `main`. All feature branches will merge into `develop`.
        *   Feature branches should be used for individual features/modules (e.g., `feature/orchestrator`, `feature/ai-visual-perception`).
    3.  **Initialize Locally (if not cloned from remote):**
        ```bash
        git init
        git remote add origin <your_repository_url.git>
        ```
    4.  **Essential Files:**
        *   **README.md:** Create a `README.md` file with a project description, setup instructions (linking to this guide), and contribution guidelines.
        *   **.gitignore:** Create a `.gitignore` file. A good starting point for Python projects:
            ```gitignore
            # Byte-compiled / optimized / DLL files
            __pycache__/
            *.py[cod]
            *$py.class

            # C extensions
            *.so

            # Distribution / packaging
            .Python
            build/
            develop-eggs/
            dist/
            downloads/
            eggs/
            .eggs/
            lib/
            lib64/
            parts/
            sdist/
            var/
            wheels/
            pip-wheel-metadata/
            share/python-wheels/
            *.egg-info/
            .installed.cfg
            *.egg
            MANIFEST

            # PyInstaller
            #  Usually these files are written by a script, but they might be committed by
            #  accident.
            *.manifest
            *.spec

            # Installer logs
            pip-log.txt
            pip-delete-this-directory.txt

            # Unit test / coverage reports
            htmlcov/
            .tox/
            .nox/
            .coverage
            .coverage.*
            .cache
            nosetests.xml
            coverage.xml
            *.cover
            *.py,cover
            .hypothesis/
            .pytest_cache/

            # Translations
            *.mo
            *.pot
            *.log

            # Django stuff:
            *.log
            local_settings.py
            db.sqlite3
            db.sqlite3-journal

            # Flask stuff:
            instance/
            .webassets-cache

            # Scrapy stuff:
            .scrapy

            # Sphinx documentation
            docs/_build/

            # PyBuilder
            target/

            # Jupyter Notebook
            .ipynb_checkpoints

            # IPython
            profile_default/
            ipython_config.py

            # pyenv
            .python-version

            # PEP 582; __pypackages__ directory
            __pypackages__/

            # Celery stuff
            celerybeat-schedule
            celerybeat.pid

            # SageMath parsed files
            *.sage.py

            # Environments
            .env
            .venv
            env/
            venv/
            ENV/
            env.bak/
            venv.bak/

            # Spyder project settings
            .spyderproject
            .spyderworkspace

            # Rope project settings
            .ropeproject

            # mkdocs documentation
            /site

            # mypy
            .mypy_cache/
            .dmypy.json
            dmypy.json

            # Pyre type checker
            .pyre/
            ```
        *   **LICENSE:** Add a `LICENSE` file (e.g., MIT, Apache 2.0).
    5.  **Upload Conceptual Design:**
        *   Create a directory `docs/conceptual_design/`.
        *   Add all previously created Python modules (`ai_core_data_structures.py`, `visual_perception_module.py`, etc.) and Markdown documents (`multi_step_navigation_and_state_management.md`, etc.) to this directory.
    6.  **Commit and Push:**
        ```bash
        git add .
        git commit -m "Initial project setup with conceptual design documents"
        git push -u origin develop # Or main if develop is created on remote first
        ```

### 2.2. Development Environment

-   **Language:** Python 3.9+ (ensure consistency across the team).
-   **Package Management:** Pip with `requirements.txt` (recommended for simplicity in MVP). Poetry or Conda are alternatives for more complex dependency management.
-   **IDE:** VS Code (with Python extension), PyCharm Community/Professional, or any preferred Python IDE.
-   **Setup Steps:**
    1.  **Install Python:** If not already installed, download from [python.org](https://www.python.org/) or use a version manager like `pyenv`.
    2.  **Create Virtual Environment:**
        ```bash
        cd autoapply_mvp_implementation
        python -m venv .venv
        ```
        (For Windows: `python -m venv .venv` or `py -m venv .venv`)
    3.  **Activate Virtual Environment:**
        *   macOS/Linux: `source .venv/bin/activate`
        *   Windows (cmd.exe): `.venv\Scripts\activate.bat`
        *   Windows (PowerShell): `.venv\Scripts\Activate.ps1`
    4.  **Initial `requirements.txt`:** Create this file (see section 2.7 for content).
    5.  **Install Dependencies:**
        ```bash
        pip install -r requirements.txt
        ```

### 2.3. Cloud Platform (Optional for Local MVP, Recommended for Future)

While the MVP can be developed and tested locally, planning for cloud deployment is beneficial.

-   **Provider Choice:** Google Cloud Platform (GCP), Amazon Web Services (AWS), or Microsoft Azure. (Choice depends on team familiarity, existing credits, or specific service preferences).
-   **Services for MVP (if cloud-hosted development/testing):**
    -   **Compute Instance (VM):** For running the Orchestrator and Browser Automation Layer if a shared, non-local environment is needed.
    -   **Object Storage (e.g., GCS, S3, Azure Blob Storage):** Useful for:
        -   Storing screenshots taken during automation.
        -   Logging application state or detailed logs.
        -   Storing JSON-based user profiles or feedback data.
    -   **(Later Stages):** Managed Databases (SQL, NoSQL), AI Platform services for model hosting/training, Secret Management services.
-   **Conceptual Setup (General Steps):**
    1.  **Account & Project:** Create an account on the chosen platform and set up a new project for AutoApply.
    2.  **Billing:** Configure billing for the project.
    3.  **Service Account (if programmatic access needed):**
        *   Create a service account with minimal necessary permissions (e.g., read/write to a specific storage bucket, invoke AI APIs).
        *   Download the service account key JSON (store securely, do not commit to Git). Use environment variables to point to its path or for its content.

### 2.4. Browser Automation

-   **Tool:** Selenium with Python bindings. Playwright is a strong alternative.
-   **WebDriver:** ChromeDriver (for Chrome browser). Ensure the WebDriver version matches the installed Chrome browser version.
-   **Setup Steps:**
    1.  **Install Selenium:**
        ```bash
        pip install selenium
        ```
        (Ensure this is in your `requirements.txt`).
    2.  **WebDriver Setup:**
        *   **Download ChromeDriver:** From [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads). Select the version that corresponds to your installed Google Chrome version.
        *   **Placement:**
            *   Add the directory containing `chromedriver` to your system's PATH environment variable.
            *   Alternatively, specify the path to `chromedriver.exe` (or `chromedriver`) directly in your Selenium script when instantiating the driver.
    3.  **Initial Test Script (`scripts/check_webdriver.py`):**
        ```python
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.chrome.options import Options

        # Path to your ChromeDriver executable
        # If ChromeDriver is in your PATH, you might not need to specify this.
        # CHROMEDRIVER_PATH = "/path/to/your/chromedriver"
        # service = ChromeService(executable_path=CHROMEDRIVER_PATH)
        # driver = webdriver.Chrome(service=service)

        try:
            print("Attempting to start Chrome browser...")
            chrome_options = Options()
            # chrome_options.add_argument("--headless") # Optional: run headless
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")

            # Simpler way if chromedriver is in PATH
            driver = webdriver.Chrome(options=chrome_options)

            print("Browser started successfully.")
            driver.get("https://www.google.com")
            print(f"Navigated to: {driver.title}")
            driver.quit()
            print("Browser closed successfully. Selenium setup is OK.")
        except Exception as e:
            print(f"Error during Selenium setup test: {e}")
            print("Please ensure ChromeDriver is installed and its version matches your Chrome browser version.")
            print("Also, make sure ChromeDriver is in your PATH or its path is correctly specified in the script.")

        ```
        Run this script to verify the setup: `python scripts/check_webdriver.py`

### 2.5. AI Model Access (Multimodal LLM & General LLM)

This section assumes usage of Google Cloud AI services (Gemini, Vertex AI PaLM) as an example. Adapt if using other providers like OpenAI.

-   **Multimodal LLM Service:** Google Gemini API (via `google-generativeai` or Vertex AI).
-   **General LLM Service (if distinct):** Google Vertex AI PaLM API or other models available via Vertex AI.
-   **Setup Steps:**
    1.  **GCP Project & Enable APIs:**
        *   Ensure you have a GCP project.
        *   Enable the "Vertex AI API" and "Generative Language API" (if using Gemini directly outside Vertex).
    2.  **Authentication:**
        *   **Set up Application Default Credentials (ADC):** For local development, run `gcloud auth application-default login`.
        *   For services running on GCP (e.g., Cloud Run, GCE), the service account associated with the resource will be used automatically if it has the "Vertex AI User" role.
    3.  **API Keys (If using Gemini API directly without ADC):**
        *   Go to Google AI Studio ([https://aistudio.google.com/](https://aistudio.google.com/)) to get an API key for Gemini.
        *   **Secure API Keys:** Store keys in environment variables (e.g., `GOOGLE_API_KEY`) or a secret manager service (like Google Secret Manager). **DO NOT hardcode API keys in your source code.**
    4.  **Install Client Libraries:**
        ```bash
        pip install google-generativeai google-cloud-aiplatform Pillow # Pillow for image handling with Gemini
        ```
        (Ensure these are in `requirements.txt`).
    5.  **Initial Test Script (`scripts/check_llm_api.py`):**
        ```python
        import os
        import google.generativeai as genai
        from google.cloud import aiplatform
        from PIL import Image # For a dummy image with Gemini

        def test_gemini_api():
            print("\n--- Testing Google Gemini API (direct) ---")
            try:
                api_key = os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    print("GOOGLE_API_KEY environment variable not set. Skipping direct Gemini test.")
                    return

                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro-vision') # Example vision model

                # Create a dummy image (Pillow)
                img = Image.new('RGB', (60, 30), color = 'red')
                # img.save("dummy_pixel.png") # Optional: save to see it

                response = model.generate_content(["Describe this image in one word.", img])
                print(f"Gemini API Response: {response.text}")
                print("Gemini API (direct) configured and reachable.")
            except Exception as e:
                print(f"Error testing Gemini API (direct): {e}")

        def test_vertex_ai_palm():
            print("\n--- Testing Google Vertex AI (PaLM example) ---")
            try:
                project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
                location = "us-central1" # Or your preferred region
                if not project_id:
                    print("GOOGLE_CLOUD_PROJECT environment variable not set. Skipping Vertex AI PaLM test.")
                    return

                aiplatform.init(project=project_id, location=location)

                from vertexai.language_models import TextGenerationModel
                model = TextGenerationModel.from_pretrained("text-bison@002")
                response = model.predict("What is 2+2?", max_output_tokens=256)
                print(f"Vertex AI PaLM API Response: {response.text}")
                print("Vertex AI PaLM API configured and reachable.")
            except Exception as e:
                print(f"Error testing Vertex AI PaLM API: {e}")
                print("Ensure GOOGLE_CLOUD_PROJECT env var is set and you have authenticated via `gcloud auth application-default login`.")

        if __name__ == "__main__":
            test_gemini_api()
            test_vertex_ai_palm()
        ```
        Set environment variables (`GOOGLE_API_KEY`, `GOOGLE_CLOUD_PROJECT`) before running: `python scripts/check_llm_api.py`.

### 2.6. User Profile Database (MVP)

-   **Type:** JSON file stored locally (e.g., in the `data/` directory) or in cloud storage (e.g., GCS/S3 bucket) for the MVP.
-   **Structure (Example `data/user_profile_example.json`):**
    ```json
    {
      "user_id": "user123_mvp",
      "user.firstName": "John",
      "user.lastName": "Doe",
      "user.email.primary": "john.doe.mvp@example.com",
      "user.phone.mobile": "555-0101",
      "user.address.street": "123 Main St",
      "user.address.city": "Anytown",
      "user.address.postalCode": "12345",
      "user.address.country": "USA",
      "skills_summary": "Python, Selenium, AI-driven automation, problem-solving.",
      "career_goals": "To contribute to innovative automation projects and enhance application processes.",
      "past_projects": [
        {
          "title": "Automated Data Entry Tool",
          "description": "Developed a tool to automate data entry from PDFs into a database.",
          "challenge": "Handling varied PDF layouts.",
          "solution": "Used OCR and rule-based extraction.",
          "outcome": "Reduced manual entry time by 80%."
        }
      ],
      "salary_expectations": {
        "desired_annual_salary": "95000",
        "currency": "USD",
        "is_negotiable": true
      },
      "company_research_notes": {
        "ExampleCorp": "Known for strong engineering culture and work-life balance."
      }
    }
    ```
-   **Setup:** Create the `data` directory and place the example JSON file within it.

### 2.7. Initial `requirements.txt` (Example)

Create a `requirements.txt` file in the root of your repository:
```
# Web Automation
selenium

# Google Cloud AI Services (Examples - adapt to your chosen LLM provider)
google-generativeai  # For Gemini API directly
google-cloud-aiplatform # For Vertex AI (PaLM, Gemini on Vertex, etc.)
google-cloud-storage    # If using GCS for profiles/screenshots

# Image handling for Gemini Vision
Pillow

# Data validation and settings management (recommended for structured data like AICoreInput)
pydantic
# pydantic[email] # For email validation if needed

# For environment variables (if using .env files, though direct env vars are often better for prod)
# python-dotenv

# Optional: For improved CLI interactions if building a CLI
# click
# rich
```
Install with `pip install -r requirements.txt`.

## 3. Directory Structure (Proposed for Implementation Repo)

This structure organizes the codebase logically.

```
autoapply_mvp_implementation/
├── .git/                     # Git internal files
├── .venv/                    # Python virtual environment
├── app/                      # Main application source code
│   ├── __init__.py
│   ├── main.py                 # Main entry point for the Orchestrator/Application
│   ├── orchestrator/           # Orchestration Engine logic
│   │   └── __init__.py
│   ├── ai_core/                # Implemented AI modules (visual_perception.py, etc.)
│   │   └── __init__.py
│   ├── browser_automation/     # Browser interaction logic (Selenium/Playwright wrapper)
│   │   └── __init__.py
│   ├── user_interface/         # For CLI or a simple web UI (e.g., Flask/Streamlit for MVP)
│   │   └── __init__.py
│   └── common/                 # Shared utilities, data models (e.g., ai_core_data_structures.py)
│       └── __init__.py
├── data/                     # Data files used by the application
│   └── user_profile_example.json
├── tests/                    # Unit, integration, and E2E tests
│   ├── __init__.py
│   ├── test_orchestrator.py
│   └── test_ai_core/
├── scripts/                  # Utility and helper scripts
│   ├── __init__.py
│   ├── check_webdriver.py
│   └── check_llm_api.py
├── docs/                     # Documentation
│   ├── conceptual_design/      # Phase 1 conceptual .py and .md files
│   │   ├── ai_core_data_structures.py
│   │   ├── visual_perception_module.py
│   │   ├── visual_grounding_module.py
│   │   ├── semantic_matching_module.py
│   │   ├── interaction_logic_module.py
│   │   ├── question_answering_module.py
│   │   ├── action_generation_orchestrator.py
│   │   ├── multi_step_navigation_and_state_management.md
│   │   ├── integration_points_and_apis.md
│   │   └── user_feedback_and_learning_loop.md
│   └── mvp_infrastructure_setup_guide.md # This file
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## 4. Expected Outcome

Following this guide should result in:

-   A Git repository (`autoapply_mvp_implementation`) hosted on GitHub (or similar), initialized with the basic structure and conceptual design documents.
-   A local Python development environment where:
    -   Dependencies are managed via `requirements.txt` in a virtual environment.
    -   Selenium can launch and control a web browser.
    -   API calls can be successfully made to the chosen LLM services (e.g., Google Gemini/Vertex AI).
-   A placeholder JSON file for user profile data.
-   A clear directory structure for organizing implementation code, tests, and scripts.

This setup provides a solid foundation for the development team to begin implementing the core features of the AutoApply MVP.
