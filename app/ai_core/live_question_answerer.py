# app/ai_core/live_question_answerer.py
import os
import json
import logging
from typing import Dict, Any, List, Optional, Union

import google.generativeai as genai

from app.common.ai_core_data_structures import QuestionAnsweringResult, UserProfileSummary # Assuming UserProfileSummary might be expanded or used
# If we have a more detailed user profile structure, import that instead/as well
# from app.common.data_schemas.user_profile_schema import UserProfile # Example if you create this

# --- Configuration & Constants ---
API_KEY_ENV_VAR = "GEMINI_API_KEY" # Consistent with other modules
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

_gemini_configured_qa = False

# --- Helper Functions ---
def _configure_gemini_qa(api_key: str) -> bool:
    """Configures the Gemini API for Question Answering. Ensures it's called only once effectively."""
    global _gemini_configured_qa
    if _gemini_configured_qa:
        return True
    if not api_key:
        logging.error("QA_Module: Gemini API key is missing.")
        return False
    try:
        genai.configure(api_key=api_key)
        _gemini_configured_qa = True
        logging.info("QA_Module: Gemini API configured successfully.")
        return True
    except Exception as e:
        logging.error(f"QA_Module: Failed to configure Gemini API: {e}")
        return False

def _load_user_profile(profile_path: str = "my_cv.json") -> Optional[Dict[str, Any]]:
    """Loads the user's CV/profile from a JSON file."""
    try:
        with open(profile_path, 'r') as f:
            profile_data = json.load(f)
        logging.info(f"QA_Module: Successfully loaded user profile from {profile_path}.")
        return profile_data
    except FileNotFoundError:
        logging.error(f"QA_Module: User profile file not found at {profile_path}.")
        return None
    except json.JSONDecodeError:
        logging.error(f"QA_Module: Error decoding JSON from user profile file {profile_path}.")
        return None
    except Exception as e:
        logging.error(f"QA_Module: An unexpected error occurred loading user profile: {e}")
        return None

def _load_job_description(job_desc_path: str = "job_description.txt") -> Optional[str]:
    """Loads the job description from a text file."""
    try:
        with open(job_desc_path, 'r') as f:
            job_desc = f.read()
        logging.info(f"QA_Module: Successfully loaded job description from {job_desc_path}.")
        return job_desc
    except FileNotFoundError:
        logging.info(f"QA_Module: Job description file not found at {job_desc_path}. This may be acceptable for some questions.")
        return None
    except Exception as e:
        logging.error(f"QA_Module: An unexpected error occurred loading job description: {e}")
        return None

def _select_relevant_profile_sections(user_profile: Dict[str, Any], question_text: str) -> Dict[str, Any]:
    """
    Selects relevant sections from the user profile based on the question.
    This is a placeholder for a more sophisticated relevance detection mechanism.
    For now, it might return a few key sections or a summary.
    """
    # Simple heuristic: if "experience" in question, include work experience. If "education", include education.
    # This should be improved, possibly with LLM-based selection or keyword matching.
    relevant_sections = {}
    profile_summary = {}

    if user_profile.get("user", {}).get("personal_info"):
        relevant_sections["personal_info"] = user_profile["user"]["personal_info"]
        # Create a summary for prompts
        pi = user_profile["user"]["personal_info"]
        profile_summary["name"] = f"{pi.get('first_name', '')} {pi.get('last_name', '')}".strip()


    if "experience" in question_text.lower() or "role" in question_text.lower() or "company" in question_text.lower() or "job" in question_text.lower():
        if user_profile.get("user", {}).get("work_experience"):
            relevant_sections["work_experience"] = user_profile["user"]["work_experience"]
            profile_summary["work_experience_summary"] = [
                f"{exp.get('job_title')} at {exp.get('company_name')} ({exp.get('start_date')} to {exp.get('end_date', 'Present')})"
                for exp in user_profile["user"]["work_experience"][:2] # First 2 for brevity
            ]


    if "education" in question_text.lower() or "degree" in question_text.lower() or "school" in question_text.lower():
        if user_profile.get("user", {}).get("education"):
            relevant_sections["education"] = user_profile["user"]["education"]
            profile_summary["education_summary"] = [
                f"{edu.get('degree_name')} in {edu.get('major_field_of_study')} from {edu.get('institution_name')}"
                for edu in user_profile["user"]["education"][:1] # First 1 for brevity
            ]

    if user_profile.get("user", {}).get("skills"): # Skills are generally useful
        relevant_sections["skills"] = user_profile["user"]["skills"]
        # Check if skills is a list of strings or objects
        skills_data = user_profile["user"]["skills"]
        if skills_data and isinstance(skills_data, list):
            if isinstance(skills_data[0], dict) and "skill_name" in skills_data[0]:
                 profile_summary["skills_list"] = [s.get("skill_name") for s in skills_data[:10] if s.get("skill_name")] # First 10 skills
            elif isinstance(skills_data[0], str):
                 profile_summary["skills_list"] = skills_data[:10]


    # For cover letter type questions, we might want to pull more comprehensive data
    if "cover letter" in question_text.lower() or "application.cover_letter_text" in question_text.lower() : # Check actual key if passed
        # Potentially load full resume text or a more detailed summary if available
        # For now, rely on the sections above.
        pass

    # Fallback: if no specific sections matched, provide a general summary if possible
    if not relevant_sections and profile_summary: # If specific sections were not chosen but we have a summary
        logging.info("QA_Module: No specific profile sections matched, using general summary.")
        # This might mean returning the `profile_summary` itself, or deciding to return more.
        # For the LLM prompt, a string representation of `profile_summary` is better.
        return profile_summary # Return the summarized version for the prompt

    logging.info(f"QA_Module: Selected {len(relevant_sections)} profile sections for the question.")
    return profile_summary # Return the summarized version for the prompt

# --- Core QA Function ---
def generate_answer_for_question(
    question_text: str,
    dom_path_question: str, # For the output structure
    semantic_key_of_question: str, # e.g. "application.custom_question_generic_response_1"
    user_profile_data: Optional[Dict[str, Any]] = None,
    job_context_data: Optional[Dict[str, Any]] = None, # e.g. {"job_title": "...", "company_name": "...", "job_description_summary": "..."}
    live_llm_call: bool = False
) -> QuestionAnsweringResult:
    """
    Generates a draft answer for a given application question using an LLM.
    """
    global _gemini_configured_qa
    if live_llm_call and not _gemini_configured_qa:
        api_key = os.getenv(API_KEY_ENV_VAR)
        if not api_key:
            logging.error(f"QA_Module: Live LLM call requested, but API key env var '{API_KEY_ENV_VAR}' not found.")
            return QuestionAnsweringResult(
                question_text_identified=question_text,
                dom_path_question=dom_path_question,
                suggested_answer_draft="Error: Gemini API key not configured.",
                sources_from_profile=[],
                requires_user_review=True
            )
        if not _configure_gemini_qa(api_key):
            logging.error("QA_Module: Live LLM call requested, but Gemini API configuration failed.")
            return QuestionAnsweringResult(
                question_text_identified=question_text,
                dom_path_question=dom_path_question,
                suggested_answer_draft="Error: Gemini API configuration failed.",
                sources_from_profile=[],
                requires_user_review=True
            )

    llm_output_text: Optional[str] = None
    sources_used: List[str] = []

    # Prepare context
    profile_for_prompt = {}
    if user_profile_data:
        profile_for_prompt = _select_relevant_profile_sections(user_profile_data, question_text)
        sources_used.extend(profile_for_prompt.keys()) # Track which parts of summary were included

    job_desc_summary_for_prompt = ""
    if job_context_data:
        job_desc_summary_for_prompt = job_context_data.get("job_description_summary", "")
        # Potentially add job_title, company_name to sources if used in prompt
        if job_context_data.get("job_title"): sources_used.append("job_details.job_title")


    if live_llm_call:
        logging.info(f"QA_Module: Attempting LIVE call to Gemini Pro for question: '{question_text[:100]}...'")
        try:
            model = genai.GenerativeModel('gemini-pro')

            # Constructing the prompt based on research
            prompt_lines = [
                "You are an expert AI assistant helping a job applicant draft a response to a question on a job application form.",
                "The applicant's summary profile information and details about the job are provided below.",
                "Based *only* on the provided information, please draft a professional, concise, and truthful answer to the application question."
            ]

            if "application.cover_letter_text" in semantic_key_of_question: # Specific instructions for cover letter
                 prompt_lines.extend([
                    "This question requires a full cover letter.",
                    "Address the letter to the Hiring Manager at the company mentioned in the job details if available.",
                    "Highlight how the applicant's skills and experience (from their profile) match the job description.",
                    "Maintain a professional and enthusiastic tone.",
                    "Structure the response as a standard cover letter."
                 ])
            else: # For other custom questions
                prompt_lines.append("Keep the answer focused on the question asked.")


            prompt_lines.append("\n**Application Question:**")
            prompt_lines.append(question_text)

            if profile_for_prompt:
                prompt_lines.append("\n**Applicant Profile Summary:**")
                # Convert dict to a string format suitable for LLM prompt
                for key, value in profile_for_prompt.items():
                    if isinstance(value, list):
                        prompt_lines.append(f"- {key.replace('_', ' ').title()}: {', '.join(map(str,value))}")
                    else:
                        prompt_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
            else:
                prompt_lines.append("\nApplicant Profile Summary: Not available or not deemed relevant for this question.")

            if job_context_data:
                prompt_lines.append("\n**Job Details:**")
                if job_context_data.get("job_title"):
                    prompt_lines.append(f"- Job Title: {job_context_data['job_title']}")
                if job_context_data.get("company_name"):
                    prompt_lines.append(f"- Company: {job_context_data['company_name']}")
                if job_desc_summary_for_prompt:
                    prompt_lines.append(f"- Job Description Summary: {job_desc_summary_for_prompt[:500]}...") # Limit length

            prompt_lines.append("\n**Draft Answer:**")
            # (LLM will generate here)

            if not profile_for_prompt and not job_desc_summary_for_prompt and "application.cover_letter_text" not in semantic_key_of_question :
                 prompt_lines.append("\nNote: Limited profile and job data provided. Generate a general response if possible, or state if more information is needed to provide a specific answer.")


            prompt_string = "\n".join(prompt_lines)
            logging.debug(f"QA_Module: Prompt for LLM:\n{prompt_string}")

            response = model.generate_content(prompt_string)

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logging.warning(f"QA_Module: Gemini API call blocked for question '{question_text[:50]}...'. Reason: {response.prompt_feedback.block_reason}")
                llm_output_text = f"AI response generation was blocked. Reason: {response.prompt_feedback.block_reason}. Please try rephrasing or contact support if this persists."
            else:
                llm_output_text = response.text
                logging.info(f"QA_Module: Received response from Gemini API for question '{question_text[:50]}...'.")
                logging.debug(f"LLM raw output: {llm_output_text}")

        except Exception as e_api:
            logging.error(f"QA_Module: Error during Gemini API call for question '{question_text[:50]}...': {e_api}")
            llm_output_text = f"Error generating answer via LLM: {e_api}"
    else: # Simulated response
        logging.info(f"QA_Module: Using SIMULATED LLM response for question: '{question_text[:100]}...' (live_llm_call=False).")
        if "cover letter" in question_text.lower() or "application.cover_letter_text" in semantic_key_of_question:
            llm_output_text = (
                f"Dear Hiring Manager,\n\nI am writing to express my interest in the {job_context_data.get('job_title', 'position')} at "
                f"{job_context_data.get('company_name', 'your company')}. "
                f"My skills in {profile_for_prompt.get('skills_list', ['relevant areas'])} and experience at "
                f"{profile_for_prompt.get('work_experience_summary', ['previous roles'])} make me a strong candidate.\n\n"
                "Thank you for your time and consideration.\n\nSincerely,\n[Your Name]"
            )
            sources_used.extend(["user.cover_letter_template_url_SIMULATED"]) # Simulate using a template
        elif "experience with Python" in question_text:
            llm_output_text = "I have approximately 3 years of experience with Python, primarily in developing web applications and data analysis scripts. (Simulated)"
            sources_used.append("user.work_experience[].responsibilities_summary_SIMULATED")
        elif not profile_for_prompt:
             llm_output_text = "I'm sorry, but I don't have enough information from your profile to answer that question specifically. Please provide more details. (Simulated)"
        else:
            llm_output_text = f"This is a simulated answer to: '{question_text}'. It leverages profile info like: {json.dumps(profile_for_prompt)}. (Simulated)"

    if not llm_output_text: # Should ideally not happen if errors are caught and assigned to llm_output_text
        llm_output_text = "Could not generate an answer for this question."


    return QuestionAnsweringResult(
        question_text_identified=question_text,
        dom_path_question=dom_path_question,
        suggested_answer_draft=llm_output_text.strip(),
        sources_from_profile=list(set(sources_used)), # Unique sources
        requires_user_review=True # Always true for now
    )


# --- Main Demo Block ---
if __name__ == '__main__':
    logging.info("--- Live Question Answerer Demo ---")

    # Check for API key
    api_key_present = os.getenv(API_KEY_ENV_VAR)
    if api_key_present:
        logging.info(f"QA_Module Demo: API Key '{API_KEY_ENV_VAR}' is SET. Live calls can be attempted.")
        # Attempt to configure Gemini for the demo if key is present
        _configure_gemini_qa(api_key_present)
    else:
        logging.warning(f"QA_Module Demo: API Key '{API_KEY_ENV_VAR}' is NOT SET. Demo will use simulated responses for LLM calls.")

    # Create dummy user profile and job description for demo
    if not os.path.exists("my_cv.json"):
        dummy_profile = {
            "user": {
                "personal_info": {"first_name": "Demo", "last_name": "User"},
                "work_experience": [
                    {"company_name": "Tech Solutions Inc.", "job_title": "Software Developer", "start_date": "2020-01", "end_date": "2023-12", "responsibilities_summary": "Developed web apps using Python and Django."},
                    {"company_name": "Old Company LLC", "job_title": "Junior Intern", "start_date": "2019-06", "end_date": "2019-12", "responsibilities_summary": "Assisted senior developers with various tasks."}
                ],
                "education": [{"institution_name": "State University", "degree_name": "B.Sc. Computer Science", "major_field_of_study": "Computer Science", "graduation_date": "2019-05"}],
                "skills": [{"skill_name": "Python"}, {"skill_name": "Django"}, {"skill_name": "JavaScript"}, {"skill_name": "SQL"}]
            }
        }
        with open("my_cv.json", "w") as f:
            json.dump(dummy_profile, f, indent=2)
        logging.info("QA_Module Demo: Created dummy 'my_cv.json'.")

    if not os.path.exists("job_description.txt"):
        dummy_job_desc = "We are looking for a Python Developer with experience in web frameworks and databases. The ideal candidate will be a team player with strong problem-solving skills."
        with open("job_description.txt", "w") as f:
            f.write(dummy_job_desc)
        logging.info("QA_Module Demo: Created dummy 'job_description.txt'.")

    user_profile = _load_user_profile()
    job_description_text = _load_job_description()
    job_context = {
        "job_title": "Python Developer",
        "company_name": "Innovatech Corp",
        "job_description_summary": job_description_text if job_description_text else ""
    }

    sample_questions = [
        {"text": "Describe your experience with Python.", "dom": "//textarea[@id='q1']", "key": "application.custom_question.generic_response_1"},
        {"text": "Why are you interested in this role?", "dom": "//textarea[@id='q2']", "key": "application.custom_question.generic_response_2"},
        {"text": "Please provide a cover letter for your application.", "dom": "//textarea[@id='cover_letter']", "key": "application.cover_letter_text_final"},
        {"text": "What are your salary expectations? (Question not ideal for full auto-answer but testing)", "dom": "//input[@id='q3']", "key": "application.salary_expectations.desired_amount"}, # Example of a question that might be harder
    ]

    # --- Test with SIMULATED LLM calls ---
    logging.info(f"\n--- Generating answers with SIMULATED LLM responses (live_llm_call=False) ---")
    for q_data in sample_questions:
        result = generate_answer_for_question(
            question_text=q_data["text"],
            dom_path_question=q_data["dom"],
            semantic_key_of_question=q_data["key"],
            user_profile_data=user_profile,
            job_context_data=job_context,
            live_llm_call=False
        )
        logging.info(f"  Question: {result.question_text_identified}")
        logging.info(f"  Answer: {result.suggested_answer_draft[:150]}...") # Print snippet
        logging.info(f"  Sources: {result.sources_from_profile}")
        logging.info(f"  Review Req: {result.requires_user_review}\n")

    # --- Test with LIVE LLM calls (if API key is available) ---
    if api_key_present and _gemini_configured_qa:
        logging.info(f"\n--- Generating answers with LIVE LLM responses (live_llm_call=True) ---")
        for q_data in sample_questions:
            # For live, let's test one specific question to avoid too many calls in demo
            if "experience with Python" not in q_data["text"] and "cover letter" not in q_data["text"]:
                logging.info(f"Skipping live call for '{q_data['text'][:30]}...' in this demo run to limit API calls.")
                continue

            logging.info(f"Attempting live call for: {q_data['text']}")
            result_live = generate_answer_for_question(
                question_text=q_data["text"],
                dom_path_question=q_data["dom"],
                semantic_key_of_question=q_data["key"],
                user_profile_data=user_profile,
                job_context_data=job_context,
                live_llm_call=True
            )
            logging.info(f"  LIVE Question: {result_live.question_text_identified}")
            logging.info(f"  LIVE Answer: {result_live.suggested_answer_draft[:200]}...")
            logging.info(f"  LIVE Sources: {result_live.sources_from_profile}")
            logging.info(f"  LIVE Review Req: {result_live.requires_user_review}\n")
    else:
        logging.warning("\nSkipping LIVE LLM call tests as API key is not set or Gemini not configured.")

    # Clean up dummy files
    # if os.path.exists("my_cv.json"): os.remove("my_cv.json")
    # if os.path.exists("job_description.txt"): os.remove("job_description.txt")
    logging.info("--- Live Question Answerer Demo Finished (dummy files retained for inspection) ---")
