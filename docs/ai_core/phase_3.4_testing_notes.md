# Phase 3.4 (Advanced Interactions & QA) Testing Notes

This document outlines testing procedures for the advanced interaction handling (partially covered previously) and the newly integrated Question Answering (QA) module.

## I. Environment Setup for Testing

1.  **Ensure API Keys are Set:**
    *   Verify that the `GEMINI_API_KEY` environment variable is correctly set and has a valid API key for live LLM calls.
2.  **Prepare User Profile (`my_cv.json`):**
    *   Create a comprehensive `my_cv.json` file with diverse information:
        *   Multiple work experiences with detailed responsibilities.
        *   Various skills (technical, soft).
        *   Education details.
        *   Personal information.
        *   (Optional but recommended for thorough QA) A section for "career_summary" or "personal_statement".
    *   Create variations of this file:
        *   One with minimal information to test how the QA module handles missing data.
        *   One with very specific details that should be picked up by the QA module.
3.  **Prepare Job Description (`job_description.txt`):**
    *   Create a `job_description.txt` file for a sample job.
    *   Include specific requirements, company information, and job responsibilities.
    *   Prepare a few different job descriptions to test QA adaptability.
4.  **Target Application Form:**
    *   Use `test_form.html` or a live test website that includes:
        *   Standard input fields (name, email, phone).
        *   Textarea fields that would map to `application.custom_question.generic_response_1` etc. (e.g., "Describe your motivation", "Tell us about a challenge you faced").
        *   A field for a cover letter (e.g., a textarea that would map to `application.cover_letter_text_final`).
        *   Other complex fields like dropdowns and checkboxes (if testing advanced interactions from Phase 3.4 Part A).
5.  **Verify Semantic Schema (`semantic_field_schema.json`):**
    *   Ensure the schema correctly lists `application.custom_question.generic_response_1`, `..._2`, `..._3`, and `application.cover_letter_text_final` in `target_semantic_keys`.

## II. Testing the Question Answering (QA) Module Integration

**Test Case Execution:** For each test case, run `mvp_orchestrator.py` and proceed to the AI recommendations step.

**A. Identification of Question Fields:**

*   **TC-QA-ID-01:**
    *   **Objective:** Verify that fields labeled as open-ended questions (e.g., "Why are you interested in this role?") are correctly identified by the semantic matcher and trigger the QA module.
    *   **Expected Result:** The orchestrator log should show the `live_question_answerer` being called for these fields. The field should be listed in the "Suggested Answers to Application Questions" section during user review.
*   **TC-QA-ID-02 (Cover Letter):**
    *   **Objective:** Verify that a textarea intended for a cover letter is correctly identified (maps to `application.cover_letter_text_final`) and triggers the QA module.
    *   **Expected Result:** `live_question_answerer` called; cover letter draft appears in user review.
*   **TC-QA-ID-03 (Non-Question Fields):**
    *   **Objective:** Verify that standard fields (e.g., first name, email) do NOT trigger the QA module.
    *   **Expected Result:** No calls to `live_question_answerer` for these fields. They should be handled by the standard field filling logic.

**B. Contextual Data Loading for QA:**

*   **TC-QA-CTX-01 (User Profile):**
    *   **Objective:** Verify that `_load_user_profile()` in `live_question_answerer.py` successfully loads `my_cv.json`.
    *   **Expected Result:** Logs should indicate successful loading. QA answers should reflect information from the profile.
*   **TC-QA-CTX-02 (Job Description):**
    *   **Objective:** Verify that `_load_job_description()` successfully loads `job_description.txt`.
    *   **Expected Result:** Logs indicate successful loading. QA answers (especially cover letter) should incorporate job details.
*   **TC-QA-CTX-03 (Missing Profile/JobDesc):**
    *   **Objective:** Test system behavior when `my_cv.json` or `job_description.txt` are missing or empty.
    *   **Expected Result:** The system should handle this gracefully. QA module might produce more generic answers or indicate missing information, as per the strategy. Logs should show warnings/info about missing files.

**C. Prompt Engineering & LLM Answer Generation:**

*   **TC-QA-GEN-01 (Relevance of Answer):**
    *   **Objective:** Assess if the generated answer is relevant to the question asked and uses appropriate information from the profile and job context.
    *   **Procedure:** Use a well-populated profile and job description. Ask a specific question (e.g., "Describe your experience with Python relevant to a web development role.").
    *   **Expected Result:** The answer should focus on Python experience and mention web development aspects if present in the profile/job.
*   **TC-QA-GEN-02 (Cover Letter Generation):**
    *   **Objective:** Assess the quality and completeness of the generated cover letter.
    *   **Expected Result:** The letter should be well-structured, address the company/role, highlight relevant user skills/experience, and have a professional tone.
*   **TC-QA-GEN-03 (Handling Missing Data in Profile):**
    *   **Objective:** Test how the QA module responds when the profile lacks specific information needed for a question.
    *   **Procedure:** Ask a question like "Describe your experience with project management" when the profile has no project management experience listed.
    *   **Expected Result:** The answer should state that specific information is not available or provide a very general response, and `requires_user_review` should be `True`. The `sources_from_profile` list might be empty or reflect the lack of specific data.
*   **TC-QA-GEN-04 (Tone and Style):**
    *   **Objective:** Evaluate if the tone of the generated answers is professional and appropriate for job applications.
    *   **Expected Result:** Answers should be polite, avoid slang, and be generally positive.
*   **TC-QA-GEN-05 (Multiple Questions):**
    *   **Objective:** Test QA performance when a form has multiple open-ended questions.
    *   **Expected Result:** Each question should be answered independently and appropriately. All answers should be available for review.

**D. Orchestrator Integration & User Review:**

*   **TC-QA-INT-01 (Display of QA Answers):**
    *   **Objective:** Verify that generated QA answers are correctly displayed to the user in the `AWAITING_USER_APPROVAL` state.
    *   **Expected Result:** The "Suggested Answers to Application Questions" section should appear with the question and the draft answer.
*   **TC-QA-INT-02 (QA Answers in Profile for Action Generation):**
    *   **Objective:** Verify that the generated QA answers are temporarily added to the user profile (`temp_user_profile_for_action_gen`) and are used by `mvp_generate_text_fill_actions`.
    *   **Expected Result:** The "Fields to fill/identified" section should show `[QA Draft]: ...` for the value of question fields. The actual browser automation (if approved) should attempt to fill these drafts.
*   **TC-QA-INT-03 (Approval Workflow):**
    *   **Objective:** Test the user approval workflow with QA answers present.
    *   **Procedure:** Approve the recommendations.
    *   **Expected Result:** The orchestrator should proceed to `EXECUTING_AUTOMATION`, and the browser actions should include filling the QA-generated answers into the respective form fields.
*   **TC-QA-INT-04 (Disapproval Workflow):**
    *   **Objective:** Test user disapproval.
    *   **Expected Result:** Feedback should be logged (if that part of logging is active), and the orchestrator should reset.

## III. Advanced Interaction Handler Testing (Brief Revisit from Phase 3.4 Part A)

*   **TC-AIH-DD-01 (Dropdowns):**
    *   If `live_interaction_handler.py` was implemented and integrated for dropdowns:
    *   **Objective:** Verify that dropdown fields are correctly identified and options are selected based on profile data.
    *   **Expected Result:** Orchestrator proposes `SELECT_DROPDOWN_OPTION` actions; browser automation correctly selects the option.
*   **TC-AIH-CB-01 (Checkboxes):**
    *   If `live_interaction_handler.py` was implemented for checkboxes:
    *   **Objective:** Verify checkbox selection/deselection based on profile or predefined logic.
    *   **Expected Result:** Orchestrator proposes `CLICK_ELEMENT` actions for checkboxes; browser automation correctly checks/unchecks them.

## IV. Refinement Considerations

*   **Prompt Refinement:** Based on test results, are prompts for `live_question_answerer` clear? Do they need more specific instructions, examples, or constraints?
*   **Context Selection:** Is `_select_relevant_profile_sections` in `live_question_answerer.py` effective? Does it need more sophisticated logic to pick the best context?
*   **Error Handling:** How does the system behave with API errors from the LLM, malformed profile data, or unexpected form structures?
*   **Confidence Scores:** While not explicitly used by QA for now, consider if confidence from semantic matching should influence QA triggering.
*   **User Experience:** Is the presentation of QA answers for review clear and user-friendly?

This checklist provides a starting point. Actual testing may reveal other areas needing attention.
