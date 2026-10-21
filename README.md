# AI CV Tailor & Job Assistant

A local web app that tailors your CV to a specific job with an LLM, renders it as a clean PDF, writes cover letters and application answers, and helps you scrape and track job listings.

## Features

* **Tailor your CV** to a pasted job description or to a job you saved. Upload a PDF, DOCX, TXT or JSON CV, or paste the text.
* **Choose your model**: Google Gemini directly, or any model on [OpenRouter](https://openrouter.ai/models) (Claude, GPT, Grok, Kimi, Qwen, DeepSeek, free models, or a custom model id).
* **Truthful by design**: the prompt reframes and prioritises your real experience. It doesn't invent employers, titles, dates or numbers.
* **Optional summary section**, toggled per run.
* **Review and edit**: preview the PDF, edit the tailored content (JSON) and re-render the PDF, and download the JSON.
* **Cover letters and application answers**, one answer per question, with copy buttons.
* **Job scraping** from LinkedIn, Indeed, Glassdoor, ZipRecruiter and Google (via JobSpy), with "posted within" and remote filters. Results are saved to a local SQLite database without duplicates.
* **Job tracker**: live search and filters, applied/not-applied status, delete, and one-click "Tailor CV" for any saved job.
* **Batch generation**: select several jobs and generate a tailored CV for each (in parallel); each CV is linked to its job.

## Setup

Requires Python 3.10 or newer.

1. Create a virtual environment and install dependencies (from the project root):
    ```bash
    python -m venv venv
    venv\Scripts\activate        # macOS/Linux: source venv/bin/activate
    pip install -r requirements.txt
    ```
    > Note: the scraper package is `python-jobspy`. An unrelated package called `jobspy` exists on PyPI; if you installed it by mistake, run `pip uninstall jobspy`.

2. Copy `.env.example` to `.env` and add at least one API key:
    ```env
    GOOGLE_API_KEY="..."        # for gemini/* models (https://aistudio.google.com/apikey)
    OPENROUTER_API_KEY="..."    # for every other model (https://openrouter.ai/keys)
    SECRET_KEY=""               # optional; a temporary key is generated if blank
    ```
    With only an OpenRouter key, Gemini models are routed through OpenRouter automatically.

3. Run the app:
    ```bash
    python run.py
    ```
    Then open http://127.0.0.1:5001.

The server listens on `127.0.0.1` with debug mode off by default. Set `FLASK_RUN_HOST`, `FLASK_RUN_PORT` or `FLASK_DEBUG` to change that, but never expose the debugger (`FLASK_DEBUG=true`) on a network, because it allows remote code execution.

## Customising the CV structure

`CV_format.json` defines the JSON structure the model fills in and the PDF renders. It must be valid JSON (no `//` comments). Remove sections you don't want, or copy extra ones from `CV_format_backup.json` (Certifications, Awards, Volunteer Experience). The summary section is controlled by the "Include a summary section" checkbox rather than by editing the file.

## API

| Method & path | Purpose |
| --- | --- |
| `GET /api/models` | Model catalog, which providers have keys, supported scrape sites |
| `POST /api/tailor-cv` | Form: `cv_file` or `cv_text`, `job_description` and/or `job_id`, `model`, `include_summary` |
| `POST /api/render-pdf` | JSON: `cv_json` (edited CV), optional `job_id`. Re-renders the PDF |
| `POST /api/batch-generate-cvs` | Form: `cv_file` or `cv_text`, `job_ids[]`, `model`, `include_summary` |
| `POST /api/generate-cover-letter` | JSON: `cv_json`, `job_description`, `model` |
| `POST /api/answer-question` | JSON: `cv_json`, `job_description`, `question` (list), `model` |
| `GET /api/scrape-jobs` | Query: `search_term`, `location`, `site_names`, `results_wanted`, `hours_old`, `is_remote` |
| `GET /api/jobs` | Query: `keyword`, `location`, `source`, `applied_status` |
| `GET` / `DELETE /api/jobs/<id>` | Get or delete a saved job |
| `POST /api/jobs/<id>/toggle-applied` | Toggle applied status |
| `GET /api/download-cv/<file>` / `GET /api/download-json/<file>` | Download outputs (`?inline=1` to view in the browser) |

## Project structure

```
app/
  main.py           Flask app factory and routes
  llm.py            Model catalog, Gemini/OpenRouter routing, retries, JSON extraction
  cv_utils.py       CV file readers, prompts, template handling
  pdf_generator.py  ReportLab PDF rendering
  job_scraper.py    JobSpy wrapper
  database.py       SQLite storage for jobs and generated CVs
  templates/, static/
instance/           Local data: jobs.db, generated_pdfs/, generated_jsons/ (git-ignored)
tests/              pytest suite
CV_format.json      CV structure used for tailoring
```

## Tests

```bash
python -m pytest
```

Tests use temporary databases and folders and never call a real model.
