# app/autoapply/mapper.py
"""Decides what value goes into each form field: deterministic rules first, then the LLM."""
import difflib
import json
import logging
import re

from ..llm import call_llm, extract_json
from .profile import DECLINE

logger = logging.getLogger(__name__)

CHOICE_KINDS = {"select", "radio", "combobox", "multiselect", "checkbox_group"}
DECLINE_RE = re.compile(r"decline|don.?t wish|do not wish|prefer not|not to (answer|disclose|say|self.?identify)|choose not|rather not", re.I)


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def match_option(value, options: list[dict]) -> dict | None:
    """Finds the option that best matches a desired value (by label, then value)."""
    if value is None or not options:
        return None
    wanted = _norm(value)
    if not wanted:
        return None
    labels = [(_norm(o.get("label")), o) for o in options]

    for label, option in labels:
        if label == wanted or _norm(option.get("value")) == wanted:
            return option
    if wanted == _norm(DECLINE) or DECLINE_RE.search(str(value)):
        for label, option in labels:
            if DECLINE_RE.search(label):
                return option
    # "Yes" should match "Yes, I am authorized to work in the US"
    for label, option in labels:
        if label.startswith(wanted + " ") or wanted.startswith(label + " "):
            return option
    if wanted in ("yes", "no"):
        return None
    for label, option in labels:
        if len(wanted) >= 4 and (wanted in label or (len(label) >= 4 and label in wanted)):
            return option
    best, best_ratio = None, 0.0
    for label, option in labels:
        ratio = difflib.SequenceMatcher(None, wanted, label).ratio()
        if ratio > best_ratio:
            best, best_ratio = option, ratio
    return best if best_ratio >= 0.72 else None


# --- Deterministic rules -------------------------------------------------------

def _full_name(p):
    return " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)


def _location(p):
    return ", ".join(x for x in (p.get("city"), p.get("state")) if x)


# (label regex, profile key or callable). First match wins, so specific patterns go first.
RULES = [
    (r"\b(first|given)\s*name|forename", "first_name"),
    (r"\b(last|family)\s*name|surname", "last_name"),
    (r"preferred\s*(first\s*)?name|nickname", lambda p: p.get("preferred_name") or p.get("first_name")),
    (r"^(your\s+)?(full\s+|legal\s+)?name\b(?!.*(company|employer|school|reference|manager|university))", _full_name),
    (r"e-?mail", "email"),
    (r"(phone\s*)?country\s*code|dial(l)?ing code", "country"),  # "United States" matches "United States (+1)"
    (r"(phone|mobile|telephone|cell)(?!.*(type|country|extension|device))", "phone"),
    (r"linkedin", "linkedin_url"),
    (r"github", "github_url"),
    (r"portfolio|personal\s*(web)?site|^website|blog", lambda p: p.get("portfolio_url") or p.get("other_url")),
    (r"twitter|\bx\.com", None),
    (r"address\s*(line)?\s*1|street\s*address|^address$", "address_line1"),
    (r"\bcity\b|town", "city"),
    (r"\bstate\b|province|region", "state"),
    (r"zip|postal", "postal_code"),
    (r"^country$|country of residence|which country", "country"),
    (r"(current\s+)?location|where are you (located|based)", _location),
    (r"current\s*(company|employer)|most recent (company|employer)", "current_company"),
    (r"current\s*(job\s*)?title|current\s*position|most recent (job )?title", "current_title"),
    (r"years of (professional )?experience|how many years", "years_experience"),
    (r"(school|university|college|institution)(?!.*(year|date|gpa))", "school"),
    (r"(highest\s*)?(degree|level of education)(?!.*(year|date))", "highest_degree"),
    (r"graduation (year|date)|year of graduation", "graduation_year"),
    (r"(legally )?(authori[sz]ed|eligible|permitted) to work|right to work|work authori[sz]ation", "authorized_to_work"),
    (r"sponsor", "requires_sponsorship"),
    (r"relocat", "willing_to_relocate"),
    (r"(earliest|available|availability).*start|start date|notice period", "earliest_start_date"),
    (r"salary|compensation|pay expectation", "salary_expectation"),
    (r"how did you (hear|find|learn)|where did you (hear|find|learn)|referral source|source of application", "how_did_you_hear"),
    (r"pronoun", "pronouns"),
    (r"hispanic|latin[oax]", "hispanic_latino"),
    (r"\bgender\b|\bsex\b", "gender"),
    (r"\brace\b|ethnicit", "race_ethnicity"),
    (r"veteran", "veteran_status"),
    (r"disabilit", "disability_status"),
]
COMPILED_RULES = [(re.compile(pattern, re.I), source) for pattern, source in RULES]
RESUME_RE = re.compile(r"resume|résumé|\bcv\b|curriculum", re.I)
COVER_RE = re.compile(r"cover\s*letter|motivation letter|letter of interest", re.I)


FOLLOW_RE = re.compile(r"\bfollow\b.*\b(company|page|us)\b|stay up to date with", re.I)
OPT_OUT_RE = re.compile(r"top choice|newsletter|marketing|promotional|job alerts?|talent (network|community)|"
                        r"keep me (updated|informed)|future (job )?opportunit|text messages?|sms", re.I)
YEARS_RE = re.compile(r"\byears?\b|how many|how long|\bexperience\b", re.I)


def _keyword_answer(label: str, kind: str, profile: dict) -> str | None:
    """The answer of the most specific answer rule whose keyword appears in the question."""
    if kind in ("textarea", "file"):
        return None  # keyword answers are short; free-text questions go to saved answers or the model
    best = None
    for rule in profile.get("answer_rules") or []:
        keyword = rule.get("keyword", "").strip()
        if not keyword or not re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", label, re.I):
            continue
        answer = rule.get("answer", "")
        if re.fullmatch(r"\d+(\.\d+)?", answer.strip()) and not YEARS_RE.search(label):
            continue  # a number like "Python: 3" only answers "how many years" style questions
        if best is None or len(keyword) > len(best[0]):
            best = (keyword, answer)
    return best[1] if best else None


def _saved_answer(label: str, profile: dict) -> str | None:
    best, best_ratio = None, 0.0
    for item in profile.get("custom_answers") or []:
        ratio = difflib.SequenceMatcher(None, _norm(label), _norm(item.get("question"))).ratio()
        if ratio > best_ratio:
            best, best_ratio = item.get("answer"), ratio
    return best if best_ratio >= 0.85 else None


def deterministic_value(field: dict, profile: dict, files: dict):
    """Returns (value, source) for fields we can fill without the LLM, else (None, None)."""
    label = field.get("label") or field.get("name") or ""
    kind = field.get("kind")

    if kind == "file":
        if COVER_RE.search(label):
            return (files.get("cover_letter"), "file") if files.get("cover_letter") else (None, None)
        if RESUME_RE.search(label) or field.get("name", "").lower() in ("resume", "cv") or not files.get("cover_letter_needed"):
            return (files.get("resume"), "file") if files.get("resume") else (None, None)
        return None, None

    if kind == "textarea" and COVER_RE.search(label):
        return (files.get("cover_letter_text"), "cover letter") if files.get("cover_letter_text") else (None, None)

    saved = _saved_answer(label, profile)
    if saved:
        return saved, "saved answer"

    if kind == "checkbox":
        if FOLLOW_RE.search(label):
            return bool(profile.get("follow_companies")), "rule"
        if OPT_OUT_RE.search(label) and not field.get("required"):
            return False, "rule"

    keyword_answer = _keyword_answer(label, kind, profile)
    if keyword_answer is not None:
        if kind in CHOICE_KINDS and kind != "combobox" and field.get("options"):
            option = match_option(keyword_answer, field["options"])
            if option:
                return option["label"], "answer rule"
        else:
            return keyword_answer, "answer rule"

    if kind == "email":
        return profile.get("email") or None, "profile"
    if kind == "tel":
        return profile.get("phone") or None, "profile"

    for pattern, source in COMPILED_RULES:
        if pattern.search(label):
            if source is None:
                return None, None
            value = source(profile) if callable(source) else profile.get(source)
            if not value:
                return None, None
            if kind in CHOICE_KINDS and kind != "combobox" and field.get("options"):
                option = match_option(value, field["options"])
                return (option["label"], "profile") if option else (None, None)
            if kind == "checkbox":
                return None, None
            return value, "profile"
    return None, None


# --- LLM mapping -----------------------------------------------------------------

def _describe_field(field: dict) -> dict:
    item = {"id": field["id"], "type": field["kind"], "question": field.get("label") or field.get("name") or "(unlabelled)"}
    if field.get("required"):
        item["required"] = True
    if field.get("options"):
        item["options"] = [o.get("label") for o in field["options"]][:60]
    if field.get("maxlength"):
        item["max_length"] = field["maxlength"]
    if field.get("placeholder"):
        item["placeholder"] = field["placeholder"]
    return item


def build_mapping_prompt(fields: list[dict], profile: dict, cv_json: dict, job: dict) -> str:
    profile_view = {k: v for k, v in profile.items() if k not in ("generate_cover_letter",)}
    return f"""
You are filling in a job application form on behalf of the candidate. Decide the value for each form field below.

Rules:
* Use only facts from the CANDIDATE PROFILE and CV. Never invent employers, degrees, certifications, dates, licences or numbers.
* For fields with "options", the value MUST be copied exactly from that field's options.
* "checkbox": true or false. "checkbox_group" / "multiselect": a list of option strings.
* Free-text questions: answer in the first person, concise, specific and truthful, using the CV and job description. Respect max_length.
* Demographic / EEO questions: use the profile's value; if it is "{DECLINE}" pick the option that declines to answer.
* Required acknowledgement / privacy-policy checkboxes may be set to true.
* If you don't have the information for an OPTIONAL field, use null. For a REQUIRED field you can't answer from the facts, give your best honest answer and set "confidence": "low".
* Return ONLY JSON: {{"answers": [{{"id": "<field id>", "value": <value or null>, "confidence": "high" | "low"}}]}}

JOB: {job.get('title') or ''} at {job.get('company') or ''}
JOB DESCRIPTION (truncated):
{(job.get('description') or '')[:3500]}

CANDIDATE PROFILE:
{json.dumps(profile_view, indent=1, ensure_ascii=False)}

CANDIDATE CV:
{json.dumps(cv_json, ensure_ascii=False)[:8000]}

FORM FIELDS:
{json.dumps([_describe_field(f) for f in fields], indent=1, ensure_ascii=False)}
"""


def llm_values(fields: list[dict], profile: dict, cv_json: dict, job: dict, model: str | None) -> dict:
    """Asks the model for values. Returns {field_id: (value, confidence)}."""
    if not fields:
        return {}
    output = call_llm(build_mapping_prompt(fields, profile, cv_json, job), model, json_mode=True, temperature=0.2)
    try:
        data = extract_json(output)
    except ValueError:
        logger.error("Field-mapping reply was not JSON: %s", output[:300])
        return {}
    result = {}
    for item in data.get("answers") or []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = (item.get("value"), item.get("confidence") or "high")
    return result


def plan_fields(fields: list[dict], profile: dict, cv_json: dict, job: dict, files: dict, model: str | None,
                llm=llm_values) -> list[dict]:
    """
    Produces a fill plan: [{id, label, kind, value, source, confidence, required}].
    Fields that already have a value are left alone (except files, which are always attached).
    """
    plan, needs_llm = [], []
    files = {**files, "cover_letter_needed": any(f["kind"] == "file" and COVER_RE.search(f.get("label") or "") for f in fields)}

    for field in fields:
        entry = {"id": field["id"], "label": field.get("label") or field.get("name") or "", "kind": field["kind"],
                 "required": bool(field.get("required")), "value": None, "source": None, "confidence": "high"}
        current = field.get("value")
        value, source = deterministic_value(field, profile, files)
        if field["kind"] == "checkbox" and source == "rule":
            pass  # opt-out rules beat pre-ticked boxes (e.g. LinkedIn's "Follow company")
        elif field["kind"] != "file" and current not in (None, "", [], False):
            entry.update(value=current, source="prefilled")
            plan.append(entry)
            continue
        if value not in (None, ""):
            entry.update(value=value, source=source)
        elif field["kind"] != "file":
            needs_llm.append(field)
        plan.append(entry)

    if needs_llm:
        answers = llm(needs_llm, profile, cv_json, job, model)
        by_id = {f["id"]: f for f in needs_llm}
        for entry in plan:
            if entry["id"] in answers:
                value, confidence = answers[entry["id"]]
                field = by_id[entry["id"]]
                if field["kind"] in ("select", "radio") and field.get("options") and value is not None:
                    option = match_option(value, field["options"])
                    if option is None:
                        confidence = "low"
                    value = option["label"] if option else value
                entry.update(value=value, source="ai", confidence=confidence if confidence in ("high", "low") else "high")
    return plan
