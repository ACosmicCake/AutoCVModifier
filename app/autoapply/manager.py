# app/autoapply/manager.py
"""
Runs applications on one background worker thread that owns the browser.

Flask request threads only enqueue work and post commands; every Playwright call happens on
the worker. Filled forms that wait for the user's review stay open in their own tab
("parked"), so a batch can fill several applications for the user to check and submit.
"""
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

from .. import database
from ..cv_utils import generate_cover_letter
from . import store
from .engine import (ApplyContext, ApplyFailed, Cancelled, Engine, MarkedSubmitted, NeedsManualStep, SUBMIT_RE,
                     BARE_APPLY_RE, find_button, is_confirmation, snapshot)
from .profile import get_profile

logger = logging.getLogger(__name__)

OPEN_BROWSER = "__open_browser__"
PARKED_POLL_SECONDS = 3


class BrowserSession:
    """A persistent Chrome profile, so sign-ins to job sites survive between runs."""

    def __init__(self, profile_dir: str, headless: bool):
        self.profile_dir = profile_dir
        self.headless = headless
        self._playwright = None
        self._context = None

    @property
    def is_open(self) -> bool:
        return self._context is not None

    def context(self):
        if self._context is not None:
            return self._context
        from playwright.sync_api import sync_playwright

        os.makedirs(self.profile_dir, exist_ok=True)
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        # Keep extensions enabled: blockers like Cold Turkey close any Chrome/Edge window whose
        # (policy-installed) extension isn't running, and Playwright disables extensions by default.
        options = dict(headless=self.headless, accept_downloads=False, ignore_default_args=["--disable-extensions"])
        if self.headless:
            options["viewport"] = {"width": 1280, "height": 900}
        else:
            options.update(viewport=None, args=["--start-maximized"])
        last_error = None
        for channel in ("chrome", "msedge", None):  # prefer the installed browsers, then Playwright's own
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    self.profile_dir, channel=channel, **options) if channel else \
                    self._playwright.chromium.launch_persistent_context(self.profile_dir, **options)
                logger.info("Auto-apply browser started (%s)", channel or "bundled chromium")
                break
            except Exception as e:
                last_error = e
                logger.warning("Could not start browser channel %s: %s", channel, str(e).splitlines()[0])
        if self._context is None:
            raise ApplyFailed(f"Could not start a browser. Install Google Chrome, or run 'playwright install chromium'. ({last_error})")
        self._context.on("close", lambda *_: setattr(self, "_context", None))
        return self._context

    def new_page(self):
        context = self.context()
        blank = [p for p in context.pages if p.url in ("about:blank", "chrome://newtab/")]
        return blank[0] if blank else context.new_page()

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        self._context = None
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None


class AutoApplyManager:
    def __init__(self, config: dict):
        self.config = config
        self.queue: queue.Queue = queue.Queue()
        self._commands: dict[int, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.current_app_id: int | None = None
        self.parked: dict[int, dict] = {}  # app_id -> {"page", "engine", "next_poll"}
        self.session = BrowserSession(config["AUTOAPPLY_PROFILE_DIR"], config.get("AUTOAPPLY_HEADLESS", False))
        self._logs: dict[int, list] = {}

    # --- Called from Flask threads -------------------------------------------------
    def ensure_started(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._worker, name="auto-apply-worker", daemon=True)
                self._thread.start()

    def enqueue(self, app_id: int):
        self.ensure_started()
        self.queue.put(app_id)

    def open_browser(self):
        self.ensure_started()
        self.queue.put(OPEN_BROWSER)

    def send_command(self, app_id: int, command: str):
        with self._lock:
            self._commands[app_id].append(command)
        # Cancelling a queued application takes effect immediately.
        if command == "cancel":
            app = store.get_application(app_id)
            if app and app["status"] == "queued":
                store.update_application(app_id, status="cancelled", message="Cancelled before it started")

    def status(self) -> dict:
        return {
            "worker_running": bool(self._thread and self._thread.is_alive()),
            "browser_open": self.session.is_open,
            "current_application": self.current_app_id,
            "queued": self.queue.qsize(),
            "awaiting_review": sorted(self.parked),
        }

    def stop(self, timeout: float = 15):
        """Stops the worker and closes the browser (waits up to `timeout` seconds)."""
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)
        self.parked.clear()

    # --- Worker thread ---------------------------------------------------------------
    def _take_command(self, app_id):
        with self._lock:
            commands = self._commands.get(app_id)
            return commands.popleft() if commands else None

    def _worker(self):
        logger.info("Auto-apply worker started")
        while not self._stop.is_set():
            try:
                self._service_parked()
                try:
                    item = self.queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                if item == OPEN_BROWSER:
                    page = self.session.new_page()
                    page.bring_to_front()
                    continue
                self._run_application(item)
            except Exception:
                logger.exception("Auto-apply worker error")
                time.sleep(1)
        self.session.close()

    def _log(self, app_id, message, level="info"):
        entries = self._logs.setdefault(app_id, (store.get_application(app_id) or {}).get("log", []))
        entries.append({"t": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": message})
        store.update_application(app_id, log=entries)
        getattr(logger, "warning" if level == "warning" else "info")("[application %s] %s", app_id, message)

    def _set_status(self, app_id, status, message):
        store.update_application(app_id, status=status, message=message)

    def _run_application(self, app_id: int):
        app = store.get_application(app_id)
        if not app or app["status"] != "queued":
            return
        self.current_app_id = app_id
        page = None
        try:
            self._set_status(app_id, "running", "Starting")
            ctx = self._build_context(app)
            for attempt in (1, 2):
                page = self.session.new_page()
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                engine = Engine(ctx)
                try:
                    outcome, message, page = engine.run(page)
                    break
                except Exception as e:
                    if attempt == 1 and "has been closed" in str(e) and not self.session.is_open:
                        self._log(app_id, "The browser closed unexpectedly; restarting it and trying again.", "warning")
                        self.session.close()
                        ctx.filled.clear()
                        continue
                    raise
            if outcome == "submitted":
                self._complete(app_id, app["job_id"], message, page)
            else:
                self._set_status(app_id, "ready_for_review", message)
                self._log(app_id, message)
                self.parked[app_id] = {"page": page, "engine": engine, "next_poll": time.time() + PARKED_POLL_SECONDS}
        except Cancelled:
            self._set_status(app_id, "cancelled", "Cancelled")
            self._log(app_id, "Cancelled")
            self._close(page)
        except MarkedSubmitted:
            self._complete(app_id, app["job_id"], "Marked as submitted.", page)
        except (ApplyFailed, NeedsManualStep) as e:
            self._set_status(app_id, "failed", str(e))
            self._log(app_id, str(e), "warning")
        except Exception as e:
            logger.exception("Application %s failed", app_id)
            if "has been closed" in str(e):
                message = "The browser window or tab was closed before the application finished."
            else:
                message = f"Unexpected error: {str(e).splitlines()[0][:300]}"
            self._set_status(app_id, "failed", message)
            self._log(app_id, message, "warning")
        finally:
            self.current_app_id = None
            self._logs.pop(app_id, None)

    def _complete(self, app_id, job_id, message, page=None):
        self._set_status(app_id, "submitted", message)
        self._log(app_id, message)
        if job_id:
            database.set_applied(job_id, True)
        self.parked.pop(app_id, None)
        self._close(page)
        self._logs.pop(app_id, None)

    @staticmethod
    def _close(page):
        try:
            if page is not None and not page.is_closed():
                page.close()
        except Exception:
            pass

    def _service_parked(self):
        for app_id in list(self.parked):
            item = self.parked[app_id]
            page, engine = item["page"], item["engine"]
            command = self._take_command(app_id)
            try:
                if command == "cancel":
                    self.parked.pop(app_id)
                    self._set_status(app_id, "cancelled", "Cancelled")
                    self._log(app_id, "Cancelled")
                    self._close(page)
                    continue
                if command == "mark_submitted":
                    app = store.get_application(app_id)
                    self._complete(app_id, app and app["job_id"], "Marked as submitted.", page)
                    continue
                if page.is_closed():
                    self.parked.pop(app_id)
                    self._set_status(app_id, "ready_for_review", "The browser tab was closed. Mark it submitted if you applied.")
                    continue
                if command == "submit":
                    snap = snapshot(page)
                    button = find_button(snap, SUBMIT_RE) or find_button(snap, BARE_APPLY_RE)
                    if not button:
                        self._log(app_id, "Couldn't find the submit button; please submit in the browser.", "warning")
                        continue
                    self._set_status(app_id, "running", "Submitting")
                    outcome, message = engine.submit(page, snap, button)
                    if outcome == "submitted":
                        app = store.get_application(app_id)
                        self._complete(app_id, app and app["job_id"], message, page)
                    else:
                        self._set_status(app_id, "ready_for_review", message)
                        self._log(app_id, message, "warning")
                    continue
                if time.time() >= item["next_poll"]:
                    item["next_poll"] = time.time() + PARKED_POLL_SECONDS
                    if is_confirmation(snapshot(page)):
                        app = store.get_application(app_id)
                        self._complete(app_id, app and app["job_id"], "Submitted (confirmation page detected).", page)
            except Cancelled:
                self.parked.pop(app_id, None)
                self._set_status(app_id, "cancelled", "Cancelled")
                self._close(page)
            except Exception as e:
                logger.debug("Polling application %s failed: %s", app_id, e)
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    self.parked.pop(app_id, None)
                    self._set_status(app_id, "ready_for_review", "The browser was closed. Mark it submitted if you applied.")

    # --- Context ------------------------------------------------------------------------
    def _build_context(self, app: dict) -> ApplyContext:
        app_id = app["id"]
        profile = get_profile()
        job = database.get_job(app["job_id"]) if app.get("job_id") else None
        job = job or {"title": "", "company": "", "description": ""}

        pdf_path = os.path.join(self.config["GENERATED_PDFS_FOLDER"], app["cv_filename"] or "")
        if not app["cv_filename"] or not os.path.isfile(pdf_path):
            raise ApplyFailed("The tailored CV PDF for this job is missing. Generate the CV again.")
        cv_json = load_cv_json(app["cv_filename"], self.config["GENERATED_JSONS_FOLDER"])

        uploads = os.path.join(self.config["AUTOAPPLY_UPLOADS_FOLDER"], str(app_id))
        os.makedirs(uploads, exist_ok=True)
        person = re.sub(r"[^A-Za-z0-9]+", "_", f"{profile.get('first_name', '')} {profile.get('last_name', '')}").strip("_") or "Resume"
        resume_path = os.path.join(uploads, f"{person}_Resume.pdf")  # what recruiters see, not our internal file name
        shutil.copyfile(pdf_path, resume_path)

        def cover_letter_factory():
            text = generate_cover_letter(cv_json, job.get("description") or "", app.get("model"))
            pdf = os.path.join(uploads, f"{person}_Cover_Letter.pdf")
            write_text_pdf(text, pdf)
            return text, pdf

        return ApplyContext(
            app_id=app_id,
            url=app["url"],
            job=job,
            cv_json=cv_json,
            profile=profile,
            resume_path=resume_path,
            model=app.get("model"),
            auto_submit=app["auto_submit"],
            allow_easy_apply=bool(profile.get("allow_linkedin_easy_apply")),
            screenshot_dir=self.config["AUTOAPPLY_SCREENSHOTS_FOLDER"],
            cover_letter_factory=cover_letter_factory,
            log=lambda msg, level="info": self._log(app_id, msg, level),
            set_status=lambda status, msg: self._set_status(app_id, status, msg),
            take_command=lambda: self._take_command(app_id),
            record_fields=lambda fields: store.update_application(app_id, fields=fields),
            record_screenshot=lambda name: store.update_application(app_id, screenshot=name),
        )


def load_cv_json(cv_filename: str, json_folder: str) -> dict:
    """The tailored CV data behind a generated PDF (DB record first, then the JSON file next to it)."""
    conn = database.get_db_connection()
    try:
        row = conn.execute("SELECT tailored_cv_json FROM generated_cvs WHERE cv_filename = ? ORDER BY id DESC LIMIT 1",
                           (cv_filename,)).fetchone()
    finally:
        conn.close()
    candidates = [row["tailored_cv_json"]] if row else []
    json_path = os.path.join(json_folder, os.path.splitext(cv_filename)[0] + ".json")
    if os.path.isfile(json_path):
        with open(json_path, encoding="utf-8") as f:
            candidates.append(f.read())
    for raw in candidates:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def write_text_pdf(text: str, path: str):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    story = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        story.append(Paragraph(escape(paragraph).replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 0.12 * inch))
    SimpleDocTemplate(path, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch).build(story)
