import json
from unittest.mock import MagicMock, patch

import pytest

from app import cv_utils, llm
from app.cv_utils import load_cv_template, normalize_cv_data, process_cv_and_jd
from app.llm import LLMConfigError, LLMError, extract_json, resolve_model
from app.pdf_generator import create_cv_pdf

PROJECT_TEMPLATE = "CV_format.json"


# --- JSON extraction ---------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ('{"CV": {"a": 1}}', {"CV": {"a": 1}}),
    ('```json\n{"CV": {"a": 1}}\n```', {"CV": {"a": 1}}),
    ('Sure! Here is the CV:\n```\n{"CV": {"a": 1}}\n```\nGood luck!', {"CV": {"a": 1}}),
    ('<think>Let me draft {"bad": </think>{"CV": {"a": 1}}', {"CV": {"a": 1}}),
    ('Result: {"CV": {"s": "a } brace"}} trailing text', {"CV": {"s": "a } brace"}}),
])
def test_extract_json_handles_common_model_output(text, expected):
    assert extract_json(text) == expected


def test_extract_json_raises_when_no_json():
    with pytest.raises(ValueError):
        extract_json("I could not do that.")


# --- Model routing -----------------------------------------------------------

def test_gemini_models_use_google_when_key_present(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert resolve_model("gemini/gemini-2.5-pro") == ("google", "gemini-2.5-pro")
    assert resolve_model("google/gemini-pro") == ("google", llm.DEFAULT_GEMINI_MODEL)  # legacy UI value
    assert resolve_model(None) == ("google", llm.DEFAULT_GEMINI_MODEL)


def test_gemini_models_fall_back_to_openrouter(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    assert resolve_model("gemini/gemini-2.5-pro") == ("openrouter", "google/gemini-2.5-pro")


def test_openrouter_models_require_openrouter_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
        resolve_model("anthropic/claude-sonnet-5.5")


def test_openrouter_model_id_is_passed_through(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    assert resolve_model("anthropic/claude-sonnet-5.5") == ("openrouter", "anthropic/claude-sonnet-5.5")


def _response(status, payload):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = json.dumps(payload)
    return resp


def test_openrouter_call_returns_content_and_sends_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    with patch("app.llm.requests.post", return_value=_response(200, {"choices": [{"message": {"content": "hi"}}]})) as post:
        assert llm.call_llm("prompt", "openai/gpt-5.5", system="sys") == "hi"
    body = json.loads(post.call_args.kwargs["data"])
    assert body["model"] == "openai/gpt-5.5"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert post.call_args.kwargs["timeout"]  # never hangs forever
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer o"


def test_openrouter_non_retryable_error_surfaces_message(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    with patch("app.llm.requests.post", return_value=_response(404, {"error": {"message": "No such model"}})) as post:
        with pytest.raises(LLMError, match="No such model"):
            llm.call_llm("prompt", "nope/model")
    assert post.call_count == 1


def test_openrouter_retries_rate_limits(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    responses = [_response(429, {"error": {"message": "slow down"}}),
                 _response(200, {"choices": [{"message": {"content": "ok"}}]})]
    with patch("app.llm.requests.post", side_effect=responses), patch("app.llm.time.sleep") as sleep:
        assert llm.call_llm("prompt", "openai/gpt-5.5") == "ok"
    sleep.assert_called_once()


# --- CV template & normalisation ---------------------------------------------

def test_template_summary_toggle():
    without = json.loads(load_cv_template(PROJECT_TEMPLATE, include_summary=False))
    with_summary = json.loads(load_cv_template(PROJECT_TEMPLATE, include_summary=True))
    assert "SummaryOrObjective" not in without["CV"]
    assert "SummaryOrObjective" in with_summary["CV"]


def test_template_must_be_valid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"CV": { // comment\n }}', encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_cv_template(str(bad), include_summary=False)


def test_normalize_removes_placeholders_and_wraps_cv():
    data = {
        "PersonalInformation": {"Name": "Jane"},
        "SummaryOrObjective": {"Statement": "hello"},
        "Education": [{"InstitutionName": "", "DegreeEarned": "", "HonorsAndAwardsOrRelevantCoursework": [""]}],
        "Skills": [{"SkillCategory": "Lang", "Skill": ["Python", ""]}],
    }
    result = normalize_cv_data(data, include_summary=False)
    cv = result["CV"]
    assert cv["Education"] == []
    assert cv["Skills"] == [{"SkillCategory": "Lang", "Skill": ["Python"]}]
    assert "SummaryOrObjective" not in cv


def test_process_cv_and_jd_parses_and_normalizes(monkeypatch):
    reply = 'Here you go:\n```json\n{"CV": {"PersonalInformation": {"Name": "Jane"}, "Projects": [{"ProjectName": ""}]}}\n```'
    with patch.object(cv_utils, "call_llm", return_value=reply) as call:
        result = process_cv_and_jd("my cv", "the jd", "{}", "gemini/x", include_summary=False)
    assert json.loads(result) == {"CV": {"PersonalInformation": {"Name": "Jane"}, "Projects": []}}
    prompt = call.call_args.args[0]
    assert "my cv" in prompt and "the jd" in prompt
    assert "Do not add one" in prompt  # no-summary instruction
    assert call.call_args.kwargs["json_mode"] is True


def test_process_cv_and_jd_returns_none_for_non_json():
    with patch.object(cv_utils, "call_llm", return_value="Sorry, I can't help."):
        assert process_cv_and_jd("cv", "jd", "{}", "gemini/x") is None


def test_process_cv_and_jd_propagates_llm_errors():
    with patch.object(cv_utils, "call_llm", side_effect=LLMError("boom")):
        with pytest.raises(LLMError):
            process_cv_and_jd("cv", "jd", "{}", "gemini/x")


# --- PDF ---------------------------------------------------------------------

def test_pdf_handles_markup_characters_and_odd_types(tmp_path):
    data = {
        "PersonalInformation": {"Name": "A&B <Dev>", "EmailAddress": "a@b.c"},
        "SummaryOrObjective": {"Statement": "Kept latency < 200ms for List<Order>"},
        "Education": [{"InstitutionName": "Uni", "HonorsAndAwardsOrRelevantCoursework": "Dean's List"}],
        "ProfessionalExperience": [{"CompanyName": "X", "ResponsibilitiesAndAchievements": ["a<b", "Used <b> tags", 42]}],
        "Skills": [{"SkillCategory": "Lang", "Skill": ["C++", "<script>"]}, "not a dict"],
        "Certifications": [{"CertificationName": "AWS & GCP"}],
    }
    out = tmp_path / "cv.pdf"
    assert create_cv_pdf(data, str(out)) is True
    assert out.read_bytes().startswith(b"%PDF")
