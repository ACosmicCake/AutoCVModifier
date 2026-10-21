"""
Auto-apply tests. The engine runs a real headless browser against local fake ATS pages
(tests/fixtures/ats); the LLM is replaced by a fake that answers from the prompt's field list.
"""
import json
import os
import threading
import time
from unittest.mock import patch

import pytest
from flask import Flask, request, send_from_directory
from werkzeug.serving import make_server

from app.autoapply import mapper, store
from app.autoapply.engine import ApplyContext, Cancelled, Engine, detect_ats
from app.autoapply.mapper import match_option, plan_fields
from app.autoapply.profile import DEFAULT_PROFILE, clean_profile, profile_from_cv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "ats")

PROFILE = {**DEFAULT_PROFILE, "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com",
           "phone": "555-123-4567", "city": "New York", "state": "NY", "linkedin_url": "https://linkedin.com/in/jane",
           "years_experience": "4"}
CV = {"CV": {"PersonalInformation": {"Name": "Jane Doe"},
             "ProfessionalExperience": [{"CompanyName": "Tech Co", "JobTitle": "Data Engineer", "EmploymentDates": "2021 - Present"}]}}
JOB = {"title": "Data Engineer", "company": "Acme", "description": "Build pipelines in Python."}


def fake_llm(prompt, model=None, **kwargs):
    """Answers every field in the prompt like a sensible model would."""
    fields = json.loads(prompt.split("FORM FIELDS:\n", 1)[1])
    answers = []
    for f in fields:
        question = f["question"].lower()
        options = f.get("options") or []
        if "last name" in question and getattr(fake_llm, "refuse_last_name", False):
            value = None
        elif options:
            if "sponsor" in question and "No" in options:
                value = "No"
            elif "Yes" in options:
                value = "Yes"
            else:
                value = options[0]
        elif f["type"] == "checkbox":
            value = True
        elif f["type"] == "number":
            value = "4"
        else:
            value = "I enjoy building reliable data pipelines with Python."
        answers.append({"id": f["id"], "value": value, "confidence": "high"})
    return json.dumps({"answers": answers})


# --- Fake ATS server -------------------------------------------------------------------

@pytest.fixture(scope="module")
def ats_server():
    server_app = Flask("fake_ats")
    server_app.submissions = []

    @server_app.route("/<path:name>")
    def page(name):
        if name.startswith("recaptcha"):
            return "<html><body>captcha</body></html>"
        return send_from_directory(FIXTURES, name)

    @server_app.route("/submit", methods=["POST"])
    def submit():
        server_app.submissions.append({
            "form": request.form.to_dict(),
            "files": {k: v.filename for k, v in request.files.items() if v.filename},
        })
        return "<html><body><h1>Thank you for applying!</h1><p>Your application has been submitted.</p></body></html>"

    server = make_server("127.0.0.1", 0, server_app, threaded=True)  # browsers hold keep-alive connections
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server_app.base_url = f"http://127.0.0.1:{server.server_port}"
    yield server_app
    server.shutdown()


class BrowserPool:
    """One headless browser for the module, relaunched if it crashes (headless Chrome is occasionally flaky)."""

    def __init__(self, pw):
        self.pw, self.browser = pw, None

    def page(self):
        if self.browser is None or not self.browser.is_connected():
            self.browser = None
            for channel in ("chrome", "msedge", None):
                try:
                    kwargs = {"channel": channel} if channel else {}
                    # Extensions stay enabled so site blockers (e.g. Cold Turkey) don't kill the browser.
                    self.browser = self.pw.chromium.launch(headless=True, timeout=20000,
                                                           ignore_default_args=["--disable-extensions"], **kwargs)
                    break
                except Exception:
                    continue
            if self.browser is None:
                pytest.skip("No browser available for Playwright")
        return self.browser.new_context().new_page()


@pytest.fixture(scope="module")
def browser_pool():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    pool = BrowserPool(pw)
    yield pool
    if pool.browser is not None:
        pool.browser.close()
    pw.stop()


@pytest.fixture
def run_engine(browser_pool):
    """Runs the engine on a fresh page, retrying if the browser itself crashes."""
    def run(ctx):
        for attempt in range(3):
            page = browser_pool.page()
            try:
                return Engine(ctx).run(page)
            except Exception as e:
                if "has been closed" not in str(e) or attempt == 2:
                    raise
                ctx.filled.clear()
    return run


@pytest.fixture
def resume(tmp_path):
    path = tmp_path / "Jane_Doe_Resume.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return str(path)


def make_ctx(url, resume, tmp_path, auto_submit=True, cancel_when_paused=False):
    statuses, logs = [], []

    def take_command():
        # Simulates the user pressing Cancel as soon as the engine pauses for them.
        return "cancel" if cancel_when_paused and statuses and statuses[-1][0] == "needs_attention" else None

    cover_pdf = tmp_path / "Jane_Doe_Cover_Letter.pdf"
    cover_pdf.write_bytes(b"%PDF-1.4 cover")
    ctx = ApplyContext(
        app_id=1, url=url, job=JOB, cv_json=CV, profile=dict(PROFILE), resume_path=resume, model="gemini/test",
        auto_submit=auto_submit, screenshot_dir=str(tmp_path / "shots"),
        cover_letter_factory=lambda: ("Dear Acme team, ...", str(cover_pdf)),
        log=lambda msg, level="info": logs.append((level, msg)),
        set_status=lambda status, msg: statuses.append((status, msg)),
        take_command=take_command,
    )
    return ctx, statuses, logs


# --- Engine against fake ATS pages ---------------------------------------------------------

@patch("app.autoapply.mapper.call_llm", side_effect=fake_llm)
def test_single_page_application_is_filled_and_submitted(_llm, ats_server, run_engine, resume, tmp_path):
    ats_server.submissions.clear()
    ctx, statuses, logs = make_ctx(f"{ats_server.base_url}/job.html", resume, tmp_path)

    outcome, message, _ = run_engine(ctx)

    assert outcome == "submitted", (message, logs)
    submission = ats_server.submissions[-1]
    form, files = submission["form"], submission["files"]
    assert form["first_name"] == "Jane" and form["last_name"] == "Doe"
    assert form["email"] == "jane@example.com"
    assert form["phone"] == "555-123-4567"
    assert form["linkedin"] == "https://linkedin.com/in/jane"
    assert form["location"] == "New York, NY"          # custom autocomplete dropdown
    assert form["authorized"] == "1"                    # profile: authorized_to_work = Yes
    assert form["sponsorship"] == "no"                  # radio group, profile: requires_sponsorship = No
    assert form["gender"] == "d"                        # profile default declines -> "Decline To Self Identify"
    assert form["why"].startswith("I enjoy")            # free-text question answered by the (fake) model
    assert form["privacy"] == "agreed"
    assert form.get("website_hp", "") == ""             # honeypot untouched
    assert files == {"resume": "Jane_Doe_Resume.pdf", "cover_letter": "Jane_Doe_Cover_Letter.pdf"}
    sources = {f["label"]: f["source"] for f in ctx.filled}
    assert sources["First Name *"] == "profile"
    assert sources["Why do you want to work at Acme? *"] == "ai"


@patch("app.autoapply.mapper.call_llm", side_effect=fake_llm)
def test_review_mode_fills_but_never_submits(_llm, ats_server, run_engine, resume, tmp_path):
    ats_server.submissions.clear()
    ctx, _, _ = make_ctx(f"{ats_server.base_url}/form.html", resume, tmp_path, auto_submit=False)

    outcome, message, page_after = run_engine(ctx)

    assert outcome == "review"
    assert "Submit application" in message
    assert ats_server.submissions == []
    assert page_after.input_value("#first_name") == "Jane"


@patch("app.autoapply.mapper.call_llm", side_effect=fake_llm)
def test_multi_step_form(_llm, ats_server, run_engine, resume, tmp_path):
    ctx, _, logs = make_ctx(f"{ats_server.base_url}/multistep.html", resume, tmp_path)

    outcome, message, page_after = run_engine(ctx)

    assert outcome == "submitted", (message, logs)
    submitted = page_after.evaluate("window.submitted")
    assert submitted == {"fn": "Jane", "ln": "Doe", "em": "jane@example.com", "years": "4",
                         "start": submitted["start"], "cv": "Jane_Doe_Resume.pdf"}
    assert submitted["start"]


@patch("app.autoapply.mapper.call_llm", side_effect=fake_llm)
def test_validation_errors_retry_then_ask_the_user(_llm, ats_server, run_engine, resume, tmp_path):
    ctx, statuses, logs = make_ctx(f"{ats_server.base_url}/multistep.html", resume, tmp_path, cancel_when_paused=True)
    ctx.profile["last_name"] = ""
    fake_llm.refuse_last_name = True
    try:
        with pytest.raises(Cancelled):
            run_engine(ctx)
    finally:
        fake_llm.refuse_last_name = False
    assert any("errors" in msg for _, msg in logs)
    assert statuses[-1][0] == "needs_attention"


def test_easy_apply_only_jobs_are_left_for_the_user(ats_server, run_engine, resume, tmp_path):
    ctx, _, _ = make_ctx(f"{ats_server.base_url}/easyapply.html", resume, tmp_path)
    outcome, message, _ = run_engine(ctx)
    assert outcome == "review"
    assert "Easy Apply" in message


def test_captcha_pauses_for_the_user(ats_server, run_engine, resume, tmp_path):
    ctx, statuses, _ = make_ctx(f"{ats_server.base_url}/captcha.html", resume, tmp_path, cancel_when_paused=True)
    with pytest.raises(Cancelled):
        run_engine(ctx)
    assert statuses[0][0] == "needs_attention"
    assert "CAPTCHA" in statuses[0][1]


# --- Mapper unit tests ------------------------------------------------------------------------

@pytest.mark.parametrize("value, labels, expected", [
    ("Yes", ["Yes", "No"], "Yes"),
    ("yes", ["Yes, I am authorized", "No, I am not"], "Yes, I am authorized"),
    ("No", ["Yes", "No"], "No"),
    ("I don't wish to answer", ["Male", "Female", "Decline To Self Identify"], "Decline To Self Identify"),
    ("I don't wish to answer", ["Yes", "No", "I prefer not to say"], "I prefer not to say"),
    ("United States", ["Canada", "United States of America", "Mexico"], "United States of America"),
    ("Banana", ["Yes", "No"], None),
    ("Yes", ["Maybe", "Unsure"], None),
])
def test_match_option(value, labels, expected):
    option = match_option(value, [{"label": l, "value": l} for l in labels])
    assert (option["label"] if option else None) == expected


def test_plan_uses_rules_saved_answers_then_llm():
    fields = [
        {"id": "a", "kind": "text", "label": "First Name *", "required": True},
        {"id": "b", "kind": "text", "label": "Full name", "required": True},
        {"id": "c", "kind": "select", "label": "Do you require visa sponsorship?", "required": True,
         "options": [{"label": "Yes", "value": "1"}, {"label": "No", "value": "0"}]},
        {"id": "d", "kind": "textarea", "label": "What is your favourite data tool and why?", "required": False},
        {"id": "e", "kind": "text", "label": "Email", "required": True, "value": "already@there.com"},
        {"id": "f", "kind": "file", "label": "Resume", "required": True},
        {"id": "g", "kind": "radio", "label": "Pick a team", "required": True,
         "options": [{"label": "Data", "value": "d", "id": "g1"}, {"label": "Web", "value": "w", "id": "g2"}]},
    ]
    profile = {**PROFILE, "custom_answers": [{"question": "What is your favourite data tool and why?", "answer": "dbt"}]}
    seen = []

    def llm(fs, *args):
        seen.extend(f["id"] for f in fs)
        return {"g": ("Something else", "high")}

    plan = {e["id"]: e for e in plan_fields(fields, profile, CV, JOB, {"resume": "/tmp/cv.pdf"}, None, llm=llm)}
    assert plan["a"]["value"] == "Jane" and plan["a"]["source"] == "profile"
    assert plan["b"]["value"] == "Jane Doe"
    assert plan["c"]["value"] == "No"
    assert plan["d"]["value"] == "dbt" and plan["d"]["source"] == "saved answer"
    assert plan["e"]["source"] == "prefilled"
    assert plan["f"]["value"] == "/tmp/cv.pdf"
    assert seen == ["g"]                                   # only the unknown field goes to the model
    assert plan["g"]["confidence"] == "low"                # model picked a value that isn't an option


def test_mapping_prompt_contains_rules_and_fields():
    prompt = mapper.build_mapping_prompt([{"id": "x", "kind": "select", "label": "Q?", "required": True,
                                           "options": [{"label": "A"}, {"label": "B"}]}], PROFILE, CV, JOB)
    assert "Never invent" in prompt
    fields = json.loads(prompt.split("FORM FIELDS:\n", 1)[1])
    assert fields == [{"id": "x", "type": "select", "question": "Q?", "required": True, "options": ["A", "B"]}]


def test_detect_ats():
    assert detect_ats("https://job-boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/1") == "lever"
    assert detect_ats("https://acme.wd5.myworkdayjobs.com/x") == "workday"
    assert detect_ats("https://example.com/careers") == "other"


def test_profile_helpers():
    assert clean_profile({"linkedin_url": "linkedin.com/in/ann"})["linkedin_url"] == "https://linkedin.com/in/ann"
    assert clean_profile({"github_url": "http://github.com/ann"})["github_url"] == "http://github.com/ann"
    cleaned = clean_profile({"first_name": "  Ann ", "generate_cover_letter": 0, "unknown": "x",
                             "custom_answers": [{"question": "Q", "answer": "A"}, {"question": "", "answer": "B"}]})
    assert cleaned["first_name"] == "Ann"
    assert cleaned["generate_cover_letter"] is False
    assert "unknown" not in cleaned
    assert cleaned["custom_answers"] == [{"question": "Q", "answer": "A"}]

    suggestions = profile_from_cv({"CV": {"PersonalInformation": {"Name": "Ann Lee", "EmailAddress": "a@b.c",
                                                                  "WebsiteOrLinkedInURL": "linkedin.com/in/ann"},
                                          "Education": [{"InstitutionName": "MIT", "GraduationDateOrExpected": "May 2020"}]}})
    assert suggestions == {"first_name": "Ann", "last_name": "Lee", "email": "a@b.c",
                           "linkedin_url": "linkedin.com/in/ann", "school": "MIT", "graduation_year": "2020"}


# --- API + background worker ------------------------------------------------------------------

def _wait_for(client, app_id, statuses, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        application = client.get(f"/api/applications/{app_id}").get_json()["application"]
        if application["status"] in statuses:
            return application
        time.sleep(0.5)
    raise AssertionError(f"Application stuck in {application['status']}: {application['message']} {application['log'][-5:]}")


@pytest.mark.usefixtures("test_db", "mock_google_api_key")
class TestAutoApplyApi:
    def _job_with_cv(self, client, url):
        from app.database import save_job
        job_id = save_job({"title": "Data Engineer", "company": "Acme", "description": "Build pipelines.",
                           "url": "https://www.linkedin.com/jobs/view/1", "source": "linkedin",
                           "raw_job_data": {"job_url_direct": url}})
        response = client.post("/api/render-pdf", json={"cv_json": CV, "job_id": job_id})
        assert response.status_code == 200
        return job_id

    def test_profile_roundtrip(self, client):
        body = client.get("/api/profile").get_json()
        assert "first_name" in body["missing"]
        saved = client.put("/api/profile", json={"profile": PROFILE}).get_json()
        assert saved["missing"] == []
        assert client.get("/api/profile").get_json()["profile"]["email"] == "jane@example.com"

    def test_apply_requires_profile_and_cv(self, client):
        from app.database import save_job
        job_id = save_job({"title": "t", "url": "http://x/1", "source": "indeed"})
        assert "profile" in client.post("/api/apply", json={"job_id": job_id}).get_json()["error"]
        client.put("/api/profile", json={"profile": PROFILE})
        response = client.post("/api/apply", json={"job_id": job_id})
        assert response.status_code == 400
        assert "Generate a tailored CV" in response.get_json()["error"]
        assert client.post("/api/apply", json={"job_id": 9999}).status_code == 404

    @patch("app.autoapply.mapper.call_llm", side_effect=fake_llm)
    @patch("app.autoapply.manager.generate_cover_letter", return_value="Dear Acme team,\n\nI would love to join.")
    def test_worker_fills_parks_for_review_then_submits(self, _cover, _llm, client, app, ats_server):
        try:
            self._run_worker_flow(client, ats_server)
        finally:
            app.extensions["autoapply"].stop()  # close the worker's browser

    def _run_worker_flow(self, client, ats_server):
        ats_server.submissions.clear()
        client.put("/api/profile", json={"profile": PROFILE})
        job_id = self._job_with_cv(client, f"{ats_server.base_url}/form.html")

        response = client.post("/api/apply", json={"job_id": job_id, "auto_submit": False})
        assert response.status_code == 202
        app_id = response.get_json()["application"]["id"]
        assert client.post("/api/apply", json={"job_id": job_id}).status_code == 409  # one at a time per job

        application = _wait_for(client, app_id, {"ready_for_review", "failed"})
        assert application["status"] == "ready_for_review", application["message"]
        assert application["url"].endswith("/form.html")  # employer's page preferred over the job board
        assert ats_server.submissions == []
        assert any(f["status"] == "filled" for f in application["fields"])
        assert client.get(f"/api/applications/{app_id}/screenshot").status_code == 200

        jobs = client.get("/api/jobs").get_json()["jobs"]
        assert jobs[0]["application"] == {"id": app_id, "status": "ready_for_review"}

        client.post(f"/api/applications/{app_id}/action", json={"action": "submit"})
        application = _wait_for(client, app_id, {"submitted", "failed"})
        assert application["status"] == "submitted", application["message"]
        assert ats_server.submissions[-1]["form"]["first_name"] == "Jane"
        assert ats_server.submissions[-1]["files"]["resume"] == "Jane_Doe_Resume.pdf"
        assert client.get("/api/jobs").get_json()["jobs"][0]["applied"] == 1

    def test_actions_on_finished_applications(self, client):
        from app.database import save_job
        job_id = save_job({"title": "t", "url": "http://x/2", "source": "indeed"})
        app_id = store.create_application(job_id, "http://x/2", "cv.pdf", False, None)
        store.update_application(app_id, status="failed", message="boom")

        assert client.post(f"/api/applications/{app_id}/action", json={"action": "bogus"}).status_code == 400
        assert client.post(f"/api/applications/{app_id}/action", json={"action": "continue"}).status_code == 409
        response = client.post(f"/api/applications/{app_id}/action", json={"action": "mark_submitted"})
        assert response.get_json()["application"]["status"] == "submitted"
        assert client.get("/api/jobs").get_json()["jobs"][0]["applied"] == 1
