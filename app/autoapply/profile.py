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
    "custom_answers": [],           # [{"question": "...", "answer": "..."}]
    "generate_cover_letter": True,  # bool
}

PROFILE_FIELD_NAMES = set(DEFAULT_PROFILE)


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
            answers = []
            for item in value if isinstance(value, list) else []:
                if isinstance(item, dict) and str(item.get("question", "")).strip() and str(item.get("answer", "")).strip():
                    answers.append({"question": str(item["question"]).strip(), "answer": str(item["answer"]).strip()})
            profile[key] = answers
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


def profile_completeness(profile: dict) -> list[str]:
    """Names of the essential fields that are still empty."""
    essentials = ["first_name", "last_name", "email", "phone", "city"]
    return [field for field in essentials if not str(profile.get(field) or "").strip()]
