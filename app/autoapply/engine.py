# app/autoapply/engine.py
"""
Browser automation for one application. All Playwright calls happen on the auto-apply
worker thread (see manager.py); nothing here is thread-safe on its own.
"""
import logging
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .mapper import COVER_RE, match_option, plan_fields

logger = logging.getLogger(__name__)

EXTRACT_JS = open(os.path.join(os.path.dirname(__file__), "extract.js"), encoding="utf-8").read()

MAX_STEPS = 10
WAIT_FOR_USER_TIMEOUT = 20 * 60  # seconds
NAV_TIMEOUT = 45_000  # ms

APPLY_RE = re.compile(r"^(apply|apply now|apply here|apply for (this )?(job|position|role)|apply (on|at|via) (the )?(company|employer)('s)? (website|site)|apply on company site|"
                      r"start (your |my )?application|begin application|i'?m interested|apply to this job|apply online)\b", re.I)
EXTERNAL_ONLY_RE = re.compile(r"easy apply|apply with (linkedin|indeed|google|seek)|quick apply|indeed apply", re.I)
SUBMIT_RE = re.compile(r"^(submit|submit (your |my |the )?application|send (my )?application|complete (my )?application|finish( application)?|submit & apply)$", re.I)
BARE_APPLY_RE = re.compile(r"^(apply|apply now)$", re.I)  # on a form page this is usually the submit button
NEXT_RE = re.compile(r"^(next|next step|next page|continue|save (and|&) continue|save (and|&) next|proceed|review( (my )?application)?|go to next)$", re.I)

ATS_HOSTS = {
    "greenhouse": ("greenhouse.io", "grnh.se"),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workday": ("myworkdayjobs.com", "workday.com"),
    "icims": ("icims.com",),
    "smartrecruiters": ("smartrecruiters.com",),
    "workable": ("workable.com",),
    "bamboohr": ("bamboohr.com",),
    "jobvite": ("jobvite.com",),
    "taleo": ("taleo.net",),
    "successfactors": ("successfactors.com", "successfactors.eu"),
    "adp": ("adp.com",),
    "dayforce": ("dayforcehcm.com",),
    "eightfold": ("eightfold.ai",),
    "linkedin": ("linkedin.com",),
    "indeed": ("indeed.com",),
}
JOB_BOARD_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com", "google.com")


def detect_ats(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, suffixes in ATS_HOSTS.items():
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return name
    return "other"


def browser_gone(error: Exception) -> bool:
    """The page/browser died (crash or closed by the user), as opposed to an ordinary failed action."""
    return "has been closed" in str(error) or type(error).__name__ == "TargetClosedError"


def is_job_board(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in JOB_BOARD_HOSTS)


class Cancelled(Exception):
    pass


class MarkedSubmitted(Exception):
    """The user applied by hand and clicked 'Mark submitted' while the engine was running."""


class ApplyFailed(Exception):
    pass


@dataclass
class ApplyContext:
    """Everything the engine needs for one application, plus callbacks into the manager."""
    app_id: int
    url: str
    job: dict
    cv_json: dict
    profile: dict
    resume_path: str
    model: str | None
    auto_submit: bool
    screenshot_dir: str
    cover_letter_factory: callable = None   # () -> (text, pdf_path)
    log: callable = None                     # (message, level="info")
    set_status: callable = None              # (status, message)
    take_command: callable = None            # () -> "continue" | "cancel" | "submit" | "mark_submitted" | None
    record_fields: callable = None           # (list of filled field dicts)
    record_screenshot: callable = None       # (filename)
    filled: list = field(default_factory=list)
    _cover: tuple | None = None

    def cover_letter(self):
        if self._cover is None and self.cover_letter_factory:
            self._cover = self.cover_letter_factory()
        return self._cover or (None, None)


# --- Page snapshot -----------------------------------------------------------------

def snapshot(page) -> dict:
    """Extracts fields/buttons from the page and every same-origin or cross-origin frame."""
    merged = {"fields": [], "buttons": [], "frames": {}, "signals": {"password": False, "captcha": False,
              "confirmation": False, "errors": [], "invalidIds": []}, "text": "", "url": page.url}
    for index, frame in enumerate(page.frames):
        try:
            data = frame.evaluate(EXTRACT_JS, f"k{index}_")
        except Exception as e:  # detached or restricted frames
            if index == 0:
                raise
            logger.debug("Could not inspect frame %s: %s", frame.url, e)
            continue
        if index == 0:
            merged["text"] = data.get("text", "")
            merged["title"] = data.get("title", "")
        for f in data["fields"]:
            merged["frames"][f["id"]] = frame
            for option in f.get("options") or []:
                if option.get("id"):
                    merged["frames"][option["id"]] = frame
        for b in data["buttons"]:
            merged["frames"][b["id"]] = frame
        merged["fields"].extend(data["fields"])
        merged["buttons"].extend(data["buttons"])
        signals = data["signals"]
        for key in ("password", "captcha", "confirmation"):
            merged["signals"][key] = merged["signals"][key] or signals[key]
        merged["signals"]["errors"].extend(signals["errors"])
        merged["signals"]["invalidIds"].extend(signals["invalidIds"])
    return merged


def is_application_form(snap: dict) -> bool:
    kinds = [f["kind"] for f in snap["fields"]]
    labels = " ".join((f.get("label") or "").lower() for f in snap["fields"])
    has_identity = "email" in kinds or "e-mail" in labels or "email" in labels or "first name" in labels or "name" in labels
    return (len(kinds) >= 3 and has_identity) or ("file" in kinds and len(kinds) >= 2)


def find_button(snap: dict, pattern: re.Pattern, exclude: re.Pattern | None = None) -> dict | None:
    for button in snap["buttons"]:
        text = button["text"].strip()
        if exclude and exclude.search(text):
            continue
        if pattern.search(text):
            return button
    return None


def button_locator(snap, button):
    return snap["frames"][button["id"]].locator(f'[data-aa-btn="{button["id"]}"]').first


def field_locator(snap, field_id):
    return snap["frames"][field_id].locator(f'[data-aa-id="{field_id}"]').first


def settle(page, timeout=6000):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass  # many sites never go fully idle
    page.wait_for_timeout(500)


# --- Filling -------------------------------------------------------------------------

def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "y", "1", "checked", "agree", "i agree")


def _check(locator, checked: bool):
    try:
        locator.set_checked(checked, timeout=3000)
    except Exception:
        # Visually hidden inputs: click the label instead.
        locator.evaluate("""(el, want) => {
            if (el.checked === want) return;
            const target = (el.labels && el.labels[0]) || el;
            target.click();
            if (el.checked !== want) { el.checked = want; el.dispatchEvent(new Event('change', {bubbles: true})); }
        }""", checked)


def read_combobox_options(snap: dict, field: dict, page) -> list[dict]:
    loc = field_locator(snap, field["id"])
    frame = snap["frames"][field["id"]]
    try:
        loc.click(timeout=3000)
        page.wait_for_timeout(400)
        texts = frame.locator('[role="option"]').all_inner_texts()
        loc.press("Escape")
    except Exception as e:
        if browser_gone(e):
            raise
        return []
    options, seen = [], set()
    for text in texts[:80]:
        text = " ".join(text.split())
        if text and text not in seen and not re.match(r"^(no options|loading)", text, re.I):
            seen.add(text)
            options.append({"label": text, "value": text})
    return options


def fill_field(snap: dict, field: dict, value, page) -> tuple[bool, str]:
    """Fills one field. Returns (ok, detail)."""
    kind = field["kind"]
    loc = field_locator(snap, field["id"])
    frame = snap["frames"][field["id"]]
    try:
        if kind == "file":
            loc.set_input_files(value)
            return True, os.path.basename(value)

        if kind in ("text", "email", "tel", "url", "number", "date", "textarea"):
            text = str(value)
            if field.get("maxlength"):
                text = text[: field["maxlength"]]
            loc.fill(text, timeout=5000)
            return True, text

        if kind == "select":
            option = match_option(value, field.get("options") or [])
            if not option:
                return False, f"no option matches '{value}'"
            loc.select_option(value=option["value"], timeout=5000)
            return True, option["label"]

        if kind == "multiselect":
            wanted = value if isinstance(value, list) else [value]
            values = [o["value"] for o in (match_option(v, field.get("options") or []) for v in wanted) if o]
            loc.select_option(values, timeout=5000)
            return bool(values), ", ".join(map(str, wanted))

        if kind == "radio":
            option = match_option(value, field.get("options") or [])
            if not option:
                return False, f"no option matches '{value}'"
            _check(frame.locator(f'[data-aa-id="{option["id"]}"]').first, True)
            return True, option["label"]

        if kind == "checkbox_group":
            wanted = value if isinstance(value, list) else [value]
            chosen = [o for o in (match_option(v, field.get("options") or []) for v in wanted) if o]
            for option in chosen:
                _check(frame.locator(f'[data-aa-id="{option["id"]}"]').first, True)
            return bool(chosen), ", ".join(o["label"] for o in chosen)

        if kind == "checkbox":
            _check(loc, _truthy(value))
            return True, "checked" if _truthy(value) else "unchecked"

        if kind == "combobox":
            text = str(value[0] if isinstance(value, list) else value)
            loc.click(timeout=3000)
            try:
                loc.fill(text, timeout=2000)
            except Exception:
                page.keyboard.type(text, delay=20)
            page.wait_for_timeout(900)
            option_els = frame.locator('[role="option"]')
            texts = option_els.all_inner_texts()
            option = match_option(text, [{"label": " ".join(t.split()), "value": i} for i, t in enumerate(texts)])
            if option is None and texts and len(texts) <= 3 and len(text) > 3:
                option = {"label": " ".join(texts[0].split()), "value": 0}  # autocomplete suggestion
            if option is not None:
                option_els.nth(option["value"]).click(timeout=3000)
                return True, option["label"]
            loc.press("Enter")
            return True, text
    except Exception as e:
        if browser_gone(e):
            raise
        return False, str(e).splitlines()[0][:160]
    return False, f"unsupported field type {kind}"


# --- The application flow --------------------------------------------------------------

class NeedsManualStep(Exception):
    """The rest has to be done by hand; the application is parked for review."""


class Engine:
    def __init__(self, ctx: ApplyContext):
        self.ctx = ctx
        self.step = 0

    # Helpers -----------------------------------------------------------------------
    def log(self, message, level="info"):
        if self.ctx.log:
            self.ctx.log(message, level)

    def check_commands(self):
        command = self.ctx.take_command() if self.ctx.take_command else None
        if command == "cancel":
            raise Cancelled()
        if command == "mark_submitted":
            raise MarkedSubmitted()
        return command

    def screenshot(self, page, label):
        os.makedirs(self.ctx.screenshot_dir, exist_ok=True)
        filename = f"app{self.ctx.app_id}_{int(time.time() * 1000)}_{label}.png"
        try:
            page.screenshot(path=os.path.join(self.ctx.screenshot_dir, filename), full_page=True, timeout=15000)
            if self.ctx.record_screenshot:
                self.ctx.record_screenshot(filename)
        except Exception as e:
            self.log(f"Could not take a screenshot: {e}", "warning")

    def wait_for_user(self, page, message, resolved):
        """Pauses until `resolved(snapshot)` is true or the user clicks Continue in the app."""
        self.ctx.set_status("needs_attention", message)
        self.log(message, "warning")
        try:
            page.bring_to_front()
        except Exception:
            pass
        deadline = time.time() + WAIT_FOR_USER_TIMEOUT
        while True:
            if self.check_commands() == "continue":
                break
            if time.time() > deadline:
                raise ApplyFailed("Timed out waiting for you to finish the step in the browser.")
            page.wait_for_timeout(1500)
            try:
                if resolved(snapshot(page)):
                    break
            except Exception as e:
                if browser_gone(e):
                    raise
                # otherwise the page is mid-navigation; check again next tick
        self.ctx.set_status("running", "Continuing")
        self.log("Continuing")
        settle(page)

    def handle_blockers(self, page, snap) -> dict:
        signals = snap["signals"]
        if signals["captcha"]:
            self.wait_for_user(page, "A CAPTCHA appeared. Please solve it in the browser window; I'll continue automatically.",
                               lambda s: not s["signals"]["captcha"])
            return snapshot(page)
        if signals["password"] and not is_application_form(snap):
            self.wait_for_user(page, "This site needs you to sign in or create an account. Do that in the browser window "
                                     "(I'll continue once the application form appears, or click Continue here).",
                               lambda s: not s["signals"]["password"] and is_application_form(s))
            return snapshot(page)
        return snap

    def click(self, page, snap, button):
        """Clicks a button and returns the page to continue on (a new tab if the click opened one)."""
        loc = button_locator(snap, button)
        pages_before = list(page.context.pages)
        try:
            loc.click(timeout=8000)
        except Exception as e:
            self.log(f"Normal click on '{button['text']}' failed ({str(e).splitlines()[0][:80]}); retrying", "warning")
            loc.evaluate("el => el.click()")
        page.wait_for_timeout(1200)
        new_pages = [p for p in page.context.pages if p not in pages_before]
        if new_pages:
            self.log(f"'{button['text']}' opened a new tab")
            page = new_pages[-1]
        settle(page)
        return page

    # Flow ----------------------------------------------------------------------------
    def reach_form(self, page):
        for attempt in range(5):
            self.check_commands()
            snap = self.handle_blockers(page, snapshot(page))
            if is_application_form(snap):
                return page, snap
            apply_button = find_button(snap, APPLY_RE, exclude=EXTERNAL_ONLY_RE)
            if not apply_button:
                if find_button(snap, EXTERNAL_ONLY_RE):
                    raise NeedsManualStep("This job only offers the job board's built-in apply (e.g. LinkedIn Easy Apply). "
                                          "That isn't automated because those sites forbid bots and restrict accounts that use them. "
                                          "Apply in the browser window, then click 'Mark submitted'.")
                if attempt == 0:
                    page.wait_for_timeout(2500)  # single-page apps can render late
                    continue
                raise NeedsManualStep("Couldn't find an application form or an Apply button on this page. "
                                      "Open the form in the browser window and click Continue, or apply manually.")
            self.log(f"Clicking '{apply_button['text']}'")
            page = self.click(page, snap, apply_button)
        snap = snapshot(page)
        if is_application_form(snap):
            return page, snap
        raise NeedsManualStep("Clicked through several pages but never reached an application form. Please continue in the browser.")

    def fill_step(self, page, snap, done_ids: set) -> list[dict]:
        fields = [f for f in snap["fields"] if f["id"] not in done_ids]
        if snap["signals"]["password"]:
            self.log("This form asks for a password; fill that in yourself.", "warning")
        if not fields:
            return []
        for f in fields:
            if f["kind"] == "combobox" and not f.get("options"):
                f["options"] = read_combobox_options(snap, f, page)

        files = {"resume": self.ctx.resume_path}
        wants_cover = self.ctx.profile.get("generate_cover_letter") and any(
            COVER_RE.search(f.get("label") or "") and f["kind"] in ("file", "textarea") for f in fields)
        if wants_cover:
            self.log("Writing a cover letter for this job")
            text, pdf_path = self.ctx.cover_letter()
            files.update(cover_letter_text=text, cover_letter=pdf_path)

        self.log(f"Found {len(fields)} field(s); deciding values")
        plan = plan_fields(fields, self.ctx.profile, self.ctx.cv_json, self.ctx.job, files, self.ctx.model)
        by_id = {f["id"]: f for f in fields}
        results = []
        for entry in plan:
            field = by_id[entry["id"]]
            done_ids.add(entry["id"])
            if entry["source"] == "prefilled":
                results.append({**entry, "status": "kept", "value": _display(entry["value"])})
                continue
            if entry["value"] in (None, "", []):
                results.append({**entry, "status": "missing" if entry["required"] else "skipped", "value": ""})
                if entry["required"]:
                    self.log(f"No value for required field '{entry['label']}'", "warning")
                continue
            self.check_commands()
            ok, detail = fill_field(snap, field, entry["value"], page)
            results.append({**entry, "status": "filled" if ok else "error",
                            "value": _display(detail if ok else entry["value"]), "detail": None if ok else detail})
            if not ok:
                self.log(f"Couldn't fill '{entry['label']}': {detail}", "warning")
        filled = sum(1 for r in results if r["status"] == "filled")
        self.log(f"Filled {filled} of {len(results)} field(s) on this page")
        self.ctx.filled.extend(results)
        if self.ctx.record_fields:
            self.ctx.record_fields(self.ctx.filled)
        return results

    def run(self, page):
        """Fills the application. Returns ("submitted" | "review", message, page)."""
        ctx = self.ctx
        self.log(f"Opening {ctx.url}")
        page.goto(ctx.url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        settle(page)
        try:
            page, snap = self.reach_form(page)
        except NeedsManualStep as e:
            self.screenshot(page, "manual")
            return "review", str(e), page
        ctx.set_status("running", f"Filling the application ({detect_ats(page.url)})")

        done_ids: set = set()
        for self.step in range(1, MAX_STEPS + 1):
            self.check_commands()
            snap = self.handle_blockers(page, snapshot(page))
            self.fill_step(page, snap, done_ids)
            snap = snapshot(page)

            submit = find_button(snap, SUBMIT_RE)
            next_button = find_button(snap, NEXT_RE)
            if not submit and not next_button:
                submit = find_button(snap, BARE_APPLY_RE)
            if submit:
                status, message = self.finish(page, snap, submit)
                return status, message, page
            if not next_button:
                self.screenshot(page, f"step{self.step}")
                return "review", "Filled what I could, but couldn't find a Next or Submit button. Please finish in the browser.", page

            self.log(f"Page {self.step} done; clicking '{next_button['text']}'")
            page = self.advance(page, snap, next_button, done_ids)
        self.screenshot(page, "max_steps")
        return "review", "Reached the maximum number of form pages. Please finish in the browser.", page

    def advance(self, page, snap, next_button, done_ids):
        """Clicks Next; if the form rejects the page, re-fills the invalid fields once, then asks the user."""
        url_before, ids_before = page.url, {f["id"] for f in snap["fields"]}
        page = self.click(page, snap, next_button)

        def stuck(s):
            return s["signals"]["errors"] and page.url == url_before and ids_before <= {f["id"] for f in s["fields"]}

        after = snapshot(page)
        if not stuck(after):
            return page
        self.log("The form reported errors: " + "; ".join(after["signals"]["errors"][:3]), "warning")
        retry_ids = set(after["signals"]["invalidIds"]) & done_ids
        if retry_ids:
            done_ids -= retry_ids
            self.fill_step(page, after, done_ids)
            again = snapshot(page)
            button = find_button(again, NEXT_RE)
            if button:
                page = self.click(page, again, button)
            after = snapshot(page)
        if stuck(after):
            self.screenshot(page, f"page{self.step}_errors")
            self.wait_for_user(page, "The form shows errors I couldn't fix. Please correct them in the browser and go to the "
                                     "next page; I'll continue when it changes (or click Continue here).",
                               lambda s: not stuck(s))
        return page

    def finish(self, page, snap, submit_button):
        ctx = self.ctx
        self.screenshot(page, "ready")
        missing = [f["label"] for f in ctx.filled if f["status"] in ("missing", "error") and f["required"]]
        if not ctx.auto_submit:
            note = f" {len(missing)} required field(s) need your input." if missing else ""
            return "review", f"Form filled. Review it in the browser and press '{submit_button['text']}' yourself.{note}"
        if missing:
            return "review", "Auto-submit skipped because these required fields need your input: " + ", ".join(missing[:5])
        return self.submit(page, snap, submit_button)

    def submit(self, page, snap, submit_button):
        self.log(f"Submitting ('{submit_button['text']}')")
        page = self.click(page, snap, submit_button)
        for _ in range(10):
            after = snapshot(page)
            if is_confirmation(after):
                self.screenshot(page, "submitted")
                return "submitted", "Application submitted."
            if after["signals"]["captcha"]:
                self.wait_for_user(page, "A CAPTCHA appeared after submitting. Please solve it in the browser window.",
                                   lambda s: not s["signals"]["captcha"])
            page.wait_for_timeout(1500)
        after = snapshot(page)
        self.screenshot(page, "after_submit")
        if after["signals"]["errors"]:
            return "review", "The form reported errors after submitting: " + "; ".join(after["signals"]["errors"][:3])
        return "review", "Clicked Submit but couldn't confirm it went through. Check the browser and mark it submitted."


def is_confirmation(snap: dict) -> bool:
    """A thank-you page: confirmation wording and (almost) no form left."""
    return snap["signals"]["confirmation"] and len(snap["fields"]) <= 2


def _display(value):
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return text if len(text) <= 400 else text[:400] + "..."
