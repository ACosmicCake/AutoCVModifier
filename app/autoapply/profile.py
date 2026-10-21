# app/autoapply/profile.py
"""Applicant profile: the personal details used to fill application forms."""
import copy
import json
import logging
import re
from datetime import datetime

from .. import database

logger = logging.getLogger(__name__)

DECLINE = "I don't wish to answer"

# Every field the UI can edit. Values are strings unless noted.
DEFAULT_PROFILE = {
    "first_name": "",
    "last_name": "",
    "preferred_name": "",
    "email": "",
    "phone": "",
    "address_line1": "",
    "city": "",
    "state": "",
    "postal_code": "",
    "country": "United States",
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "other_url": "",
    "current_company": "",
    "current_title": "",
    "years_experience": "",
    "highest_degree": "",
    "school": "",
    "graduation_year": "",
    "authorized_to_work": "Yes",
    "requires_sponsorship": "No",
    "willing_to_relocate": "Yes",
    "earliest_start_date": "Two weeks after offer",
    "salary_expectation": "",
    "how_did_you_hear": "Online job board",
    "pronouns": "",
    "gender": DECLINE,
    "race_ethnicity": DECLINE,
    "hispanic_latino": DECLINE,
    "veteran_status": DECLINE,
    "disability_status": DECLINE,
    "additional_info": "",          # free text the AI may use when answering questions
    "custom_answers": [],           # [{"question": "...", "answer": "..."}]  matched to whole questions
    "answer_rules": [],             # [{"keyword": "...", "answer": "..."}]   any question containing the keyword
    "generate_cover_letter": True,  # bool

    # Which jobs to apply to (comma-separated lists, case-insensitive)
    "blacklist_companies": "",
    "blacklist_title_keywords": "",
    "required_title_keywords": "",
    "blocked_description_keywords": "",
    "daily_application_limit": "25",

    # LinkedIn Easy Apply (against LinkedIn's terms; off by default)
    "allow_linkedin_easy_apply": False,
    "follow_companies": False,
}

PROFILE_FIELD_NAMES = set(DEFAULT_PROFILE)
LIST_FIELDS = {"custom_answers": ("question", "answer"), "answer_rules": ("keyword", "answer")}


def get_profile() -> dict:
    """Returns the saved profile merged over the defaults."""
    conn = database.get_db_connection()
    try:
        row = conn.execute("SELECT data FROM applicant_profile WHERE id = 1").fetchone()
    finally:
        conn.close()
    profile = copy.deepcopy(DEFAULT_PROFILE)
    if row:
        try:
            saved = json.loads(row["data"])
            profile.update({k: v for k, v in saved.items() if k in PROFILE_FIELD_NAMES})
        except (json.JSONDecodeError, TypeError):
            logger.warning("Stored applicant profile is corrupt; using defaults.")
    return profile


def clean_profile(data: dict) -> dict:
    """Validates and normalises profile input from the UI."""
    profile = copy.deepcopy(DEFAULT_PROFILE)
    for key, default in DEFAULT_PROFILE.items():
        if key not in data:
            continue
        value = data[key]
        if isinstance(default, bool):
            profile[key] = bool(value)
        elif isinstance(default, list):
            first, second = LIST_FIELDS[key]
            items, seen = [], set()
            for item in value if isinstance(value, list) else []:
                if not isinstance(item, dict):
                    continue
                a, b = str(item.get(first, "")).strip(), str(item.get(second, "")).strip()
                if a and b and a.lower() not in seen:
                    seen.add(a.lower())
                    items.append({first: a, second: b})
            profile[key] = items
        elif key == "daily_application_limit":
            digits = re.sub(r"\D", "", str(value or ""))
            profile[key] = str(min(int(digits), 500)) if digits else default
        else:
            profile[key] = "" if value is None else str(value).strip()
            # Application forms often reject links without a scheme ("linkedin.com/in/x").
            if key.endswith("_url") and profile[key] and not re.match(r"^https?://", profile[key], re.I):
                profile[key] = "https://" + profile[key]
    return profile


def save_profile(data: dict) -> dict:
    profile = clean_profile(data)
    conn = database.get_db_connection()
    try:
        conn.execute(
            "INSERT INTO applicant_profile (id, data, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (json.dumps(profile), datetime.now()),
        )
        conn.commit()
    finally:
        conn.close()
    return profile


def profile_from_cv(cv_json: dict) -> dict:
    """Suggests profile values from a tailored CV (only fields the CV actually contains)."""
    cv = cv_json.get("CV", cv_json) if isinstance(cv_json, dict) else {}
    info = cv.get("PersonalInformation") if isinstance(cv.get("PersonalInformation"), dict) else {}
    suggestions = {}

    name = str(info.get("Name") or "").strip()
    if name:
        parts = name.split()
        suggestions["first_name"] = parts[0]
        if len(parts) > 1:
            suggestions["last_name"] = parts[-1]
    if info.get("EmailAddress"):
        suggestions["email"] = str(info["EmailAddress"]).strip()
    if info.get("PhoneNumber"):
        suggestions["phone"] = str(info["PhoneNumber"]).strip()
    url = str(info.get("WebsiteOrLinkedInURL") or "").strip()
    if url:
        suggestions["linkedin_url" if "linkedin" in url.lower() else "portfolio_url"] = url

    experience = [e for e in cv.get("ProfessionalExperience") or [] if isinstance(e, dict)]
    if experience:
        latest = experience[0]
        if "present" in str(latest.get("EmploymentDates", "")).lower():
            suggestions["current_company"] = str(latest.get("CompanyName") or "")
            suggestions["current_title"] = str(latest.get("JobTitle") or "")

    education = [e for e in cv.get("Education") or [] if isinstance(e, dict)]
    if education:
        suggestions["school"] = str(education[0].get("InstitutionName") or "")
        suggestions["highest_degree"] = str(education[0].get("DegreeEarned") or "")
        year = "".join(ch for ch in str(education[0].get("GraduationDateOrExpected") or "") if ch.isdigit())[-4:]
        if len(year) == 4:
            suggestions["graduation_year"] = year
    return {k: v for k, v in suggestions.items() if v}


def add_saved_answer(question: str, answer: str) -> dict:
    """Adds (or replaces) one whole-question answer in the saved profile."""
    profile = get_profile()
    answers = [a for a in profile["custom_answers"] if a["question"].strip().lower() != question.strip().lower()]
    answers.append({"question": question.strip(), "answer": answer.strip()})
    profile["custom_answers"] = answers
    return save_profile(profile)


def merge_answer_rules(rules: list[dict]) -> tuple[dict, int]:
    """Adds keyword rules, keeping existing ones for keywords already present. Returns (profile, added)."""
    profile = get_profile()
    existing = {r["keyword"].lower() for r in profile["answer_rules"]}
    new = [r for r in rules if r["keyword"].lower() not in existing]
    profile["answer_rules"] = profile["answer_rules"] + new
    return save_profile(profile), len(new)


def _split_list(text) -> list[str]:
    return [part.strip().lower() for part in re.split(r"[,;\n]", str(text or "")) if part.strip()]


def job_rule_violation(job: dict, profile: dict) -> str | None:
    """Why a job shouldn't be applied to under the profile's job rules, or None if it's fine."""
    title = (job.get("title") or "").lower()
    company = (job.get("company") or "").lower()
    description = (job.get("description") or "").lower()
    for name in _split_list(profile.get("blacklist_companies")):
        if name in company:
            return f"Company '{job.get('company')}' is on your blacklist"
    for word in _split_list(profile.get("blacklist_title_keywords")):
        if re.search(rf"\b{re.escape(word)}\b", title):
            return f"Title contains blacklisted word '{word}'"
    required = _split_list(profile.get("required_title_keywords"))
    if required and not any(re.search(rf"\b{re.escape(word)}\b", title) for word in required):
        return "Title has none of your required words (" + ", ".join(required) + ")"
    for word in _split_list(profile.get("blocked_description_keywords")):
        if re.search(rf"\b{re.escape(word)}\b", description):
            return f"Description mentions blocked phrase '{word}'"
    return None


# Contact/identity answers come from the profile itself; importing them as keyword rules would
# override it (the sample answers file ships with someone else's name, address and website).
PERSONAL_KEYWORD_RE = re.compile(r"\b(name|phone|mobile|e-?mail|address|street|city|state|zip|postal|country|"
                                 r"linkedin|website|github|portfolio|twitter)\b", re.I)


def parse_bot_answers(text: str) -> list[dict]:
    """
    Reads an EasyApplyJobsBot `additionalQuestions.yaml` (sections of `keyword: answer` lines)
    into keyword rules. Tolerant of the file's loose indentation; comments, empty answers and
    contact/identity keys (see PERSONAL_KEYWORD_RE) are skipped.
    """
    rules, seen = [], set()
    for raw in (text or "").splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        if not raw.startswith((" ", "\t")):
            continue  # section header such as "inputField:" or "radio:"
        keyword, _, answer = stripped.partition(":")
        keyword, answer = keyword.strip().strip("'\""), answer.strip().strip("'\"")
        if PERSONAL_KEYWORD_RE.search(keyword):
            continue
        if keyword and answer and keyword.lower() not in seen:
            seen.add(keyword.lower())
            rules.append({"keyword": keyword, "answer": answer})
    return rules


def profile_completeness(profile: dict) -> list[str]:
    """Names of the essential fields that are still empty."""
    essentials = ["first_name", "last_name", "email", "phone", "city"]
    return [field for field in essentials if not str(profile.get(field) or "").strip()]
