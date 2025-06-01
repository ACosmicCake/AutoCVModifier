# Multi-Step Navigation and State Management Strategy for AutoApply

## 1. Introduction

**Purpose:**
This document outlines the strategy for the AutoApply system, primarily driven by the Orchestration Engine and supported by the AI Core, to effectively handle job applications that span multiple web pages. The goal is to ensure a robust, context-aware, and user-supervised process from start to submission.

**Key Challenges:**
- **Maintaining Context:** Understanding the current stage of the application across different pages.
- **Tracking Progress:** Knowing what has been completed, what data has been entered, and what remains.
- **Error Handling:** Detecting, reporting, and recovering from errors during form filling or navigation.
- **Robust Navigation:** Reliably moving between pages, including handling variations in "Next," "Submit," and other navigation cues.
- **State Synchronization:** Keeping the system's internal state aligned with the actual state of the web application.

## 2. Data to be Tracked by the Orchestration Engine (State)

The Orchestration Engine will maintain a comprehensive state for each application attempt. This state includes:

-   **`application_id`**:
    *   Type: String (e.g., UUID)
    *   Description: A unique identifier for the current, specific job application attempt.
-   **`target_job_details`**:
    *   Type: Object
    *   Description: Information about the job being applied for.
    *   Example: `{ "url": "https://jobs.example.com/123", "title": "Software Engineer", "company": "ExampleCorp" }`
-   **`current_page_identifier`**:
    *   Type: Object
    *   Description: Snapshot of the current page being processed.
    *   Fields:
        *   `url`: String (Current page URL)
        *   `ai_page_summary`: String (AI-generated summary, e.g., "Personal Details," "Work Experience," "Review Application," "Confirmation" - from `FormUnderstandingResult.page_summary`)
        *   `ai_page_type_predicted`: String (e.g., "form_step", "confirmation_page", "error_page" - a more structured classification by AI)
        *   `screenshot_hash`: String (e.g., MD5 or SHA256 hash of the screenshot for quick comparison/change detection)
        *   `timestamp`: ISO 8601 Datetime string
-   **`page_history`**:
    *   Type: List of `current_page_identifier` objects
    *   Description: An ordered list of all pages visited during the current application attempt, allowing for backtracking or review.
-   **`action_history`**:
    *   Type: List of Objects
    *   Description: A log of all actions executed by the Browser Automation Layer.
    *   Each object includes:
        *   `action_detail`: The `ActionDetail` object that was executed.
        *   `timestamp`: ISO 8601 Datetime string of execution.
        *   `status`: Enum ("success", "failure_element_not_found", "failure_value_not_accepted", "user_corrected_value", "user_skipped_action")
        *   `error_message`: String (If status indicates failure)
        *   `user_correction_details`: Object (Details if the user modified the action or its value)
-   **`accumulated_form_data`**:
    *   Type: Object (Dictionary)
    *   Description: A consolidated view of data entered across all pages, especially for information not directly from the user's profile (e.g., application-specific tracking IDs provided by the site, answers to questions like "How did you hear about us?"). Keys could be semantic meanings or field IDs.
-   **`ai_confidence_scores_history`**:
    *   Type: List of Objects
    *   Description: A log of relevant confidence scores from various AI modules at each step.
    *   Each object: `{ "page_url": "...", "module": "SemanticMatching", "field_id": "...", "score": 0.85, "timestamp": "..." }`
-   **`user_intervention_points`**:
    *   Type: List of Objects
    *   Description: A log detailing when and why user input or review was required.
    *   Each object: `{ "page_url": "...", "reason": "ClarificationRequest", "details": "Ambiguous field 'Email'", "timestamp": "..." }` or `{ "reason": "QA_Review", "question_text": "...", "timestamp": "..." }`
-   **`overall_application_status`**:
    *   Type: Enum
    *   Description: The current high-level status of the application process.
    *   Values: "NotStarted", "InProgress", "AwaitingUserReview_QA", "AwaitingUserReview_Clarification", "AwaitingUserReview_FinalSubmission", "ErrorEncountered_AI", "ErrorEncountered_Browser", "SubmittedSuccessfully", "UserCancelled", "UserPaused".

## 3. AI Core's Role in Supporting Multi-Step Navigation

The AI Core modules provide critical information to the Orchestration Engine for managing multi-step processes:

-   **Robust Navigation Element Identification:**
    *   The `FormUnderstandingResult` (from `VisualPerception` + `VisualGrounding`) will include a list of `NavigationElement` objects.
    *   Each `NavigationElement` should have a clearly `action_type_predicted` (e.g., `NEXT_PAGE`, `PREVIOUS_PAGE`, `SUBMIT_FORM`, `SAVE_DRAFT`, `CANCEL`).
    *   Confidence scores associated with these identifications help the Orchestrator decide how much to trust the prediction.
-   **Page Understanding & Context:**
    *   The `page_summary` string within `FormUnderstandingResult` (e.g., "Contact Information Page," "Work History Section") helps the Orchestration Engine understand its current location within the application flow.
    *   The `expected_next_page_type` string from `ActionSequenceRecommendation` (generated by the `ActionGenerationOrchestrator`) provides a hint for validating the outcome of a navigation action. For example, if AI expects a "confirmation page" after clicking "Submit," the Orchestrator can verify this.
-   **Error Detection Support:**
    *   The AI Core (potentially a dedicated sub-module or an enhancement to `FormUnderstandingResult`) could be trained to identify common error messages or visual patterns on a page (e.g., "This field is required," "Invalid email format," red-bordered input fields).
    *   This would be reported, perhaps as a list of `{ "error_message_text": "...", "associated_field_id_or_path": "..." }` within `FormUnderstandingResult`.
-   **Identifying Application Completion:**
    *   The AI Core needs to recognize submission confirmation pages. This can be achieved by:
        *   Looking for keywords like "Thank you for your application," "Successfully submitted," "Your application ID is:".
        *   Identifying common visual cues of a successful submission.
    *   This could be indicated by a specific `page_summary` (e.g., "Application Submitted Confirmation") or a dedicated boolean flag like `is_submission_confirmation_page: true` in the `FormUnderstandingResult`.

## 4. Orchestration Engine Logic for Multi-Step Processes

The Orchestration Engine manages the overall flow:

-   **Main Loop:**
    1.  **Capture Page State:** Instruct Browser Automation Layer to capture screenshot, DOM, URL. Update `current_page_identifier`.
    2.  **AI Core Processing (Understanding):** Call AI Core (`VisualPerception`, `VisualGrounding`, `SemanticMatching`) with page data to get `FormUnderstandingResult` (identified fields, navigation elements, page summary, potential form errors).
    3.  **Handle Open-Ended Questions:**
        *   If `FormUnderstandingResult` contains fields identified as open-ended questions not yet answered:
            *   Call AI Core (`QuestionAnsweringModule`) to generate draft answers.
            *   Present these drafts to the user for review/approval (e.g., via a `ClarificationRequest` mechanism or a dedicated UI section for QA). Store approved answers. Update `user_intervention_points`.
    4.  **AI Core Processing (Action Generation):** Call AI Core (`ActionGenerationOrchestrator`) with processed fields, navigation elements, user profile, and approved QA answers to get an `ActionSequenceRecommendation`.
    5.  **User Review of Actions (Optional/Configurable):**
        *   Depending on the configured level of autonomy, present the recommended actions (filling fields, clicking navigation) to the user for review and approval. Update `user_intervention_points` if review occurs.
    6.  **Execute Actions:** Instruct Browser Automation Layer to execute the (approved) `ActionDetail` list from `ActionSequenceRecommendation`.
    7.  **Update State:** Log executed actions and their outcomes in `action_history`. Update `accumulated_form_data` if new, non-profile data was entered. Update `overall_application_status`. Add `current_page_identifier` to `page_history`.
    8.  **Evaluate Post-Action State:**
        *   Check for errors reported by Browser Automation or identified by AI on the new page (if navigation occurred) or current page (if an action like "submit" was on the same page but led to errors).
        *   Check if AI identifies the current page as a submission confirmation page.
    9.  **Loop or Conclude:**
        *   If application is identified as complete: Set `overall_application_status` to "SubmittedSuccessfully". Inform user. End process for this application.
        *   If errors occurred that require user intervention: Set `overall_application_status` to "ErrorEncountered" or "AwaitingUserReview". Pause and inform user.
        *   If not complete and no critical errors: The last action should have been navigation. Verify successful navigation. Loop back to step 1 for the new page.

-   **Navigation Decision Making:**
    *   Primarily relies on the navigation action within the `ActionSequenceRecommendation` provided by the `ActionGenerationOrchestrator`.
    *   If the AI provides multiple navigation options and the Orchestrator cannot decide (e.g., "Save Draft" vs. "Next Page"), it may use predefined rules (e.g., prefer "Next Page" if all required fields seem filled) or prompt the user.
    *   **Validation:** After a navigation action, verify success by:
        *   Checking if the URL has changed.
        *   Comparing new page's AI-generated summary/type with `expected_next_page_type` from the AI's recommendation.
        *   Checking for unexpected error messages on the new page.

-   **Error Handling & Recovery Strategies:**
    *   **Browser Automation Failure** (e.g., element not found, element not interactable):
        1.  Log the error with details from Browser Automation.
        2.  Re-capture page state (screenshot, DOM).
        3.  Request AI Core to re-analyze the page, possibly providing context about the failed action (e.g., "Attempted to click DOM path X, but it was not found. Re-ground elements.").
        4.  If AI provides an updated action that seems plausible, retry (once or twice).
        5.  If AI cannot resolve or retries fail, set status to "ErrorEncountered_Browser" and present the issue to the user for manual intervention or correction.
    *   **AI-Detected Form Errors** (e.g., "Email is invalid" message appears after attempting to submit/navigate):
        1.  AI's `FormUnderstandingResult` should highlight these error messages and ideally link them to specific `IdentifiedFormField` objects.
        2.  Orchestrator checks if the user's profile contains alternative data for the problematic field (e.g., `user.email.work` if `user.email.primary` was rejected).
        3.  If a correction can be made automatically, generate a new action to fix the field and re-attempt the navigation/submission action.
        4.  If no automatic correction is possible, set status to "AwaitingUserReview_Clarification" and present the error and problematic field to the user.
    *   **AI Confidence Too Low:** If AI modules consistently return low confidence scores for crucial elements or page understanding, the Orchestrator might pause and request user confirmation before proceeding.

-   **Timeout Management:** Implement timeouts for:
    *   Page load operations.
    *   AI Core processing steps.
    *   User response times (if interaction is blocking).
    On timeout, log the event and potentially trigger an error state or a retry.

## 5. User Interaction in Multi-Step Processes

User interaction is key for supervision, correction, and handling ambiguities:

-   **Initial Review (Optional but Recommended):** Before starting an application, allow the user to review the target job details and the relevant sections of their profile data that will be used.
-   **QA Review (Mandatory):** AI-generated answers for open-ended questions (`QuestionAnsweringResult.suggested_answer_draft`) *must* be presented to the user for review, editing, and approval before being used.
-   **Ambiguity Resolution:** If the AI Core issues a `ClarificationRequest` (e.g., "Which of these two 'Date' fields is 'Start Date'?"), the user must provide input.
-   **Error Correction:** When the AI or Browser Automation layer fails and cannot self-recover, the user will be prompted to provide correct information, confirm an action, or manually perform a step.
-   **Final Submission Review (Highly Recommended):** Before the final "Submit Application" action is executed, offer the user an option to review all data automatically filled across all pages, ideally on the application website's own review page if available. If not, the system could present a summary.
-   **Post-Submission:** Clearly display any confirmation messages, application IDs, or next steps provided by the website to the user. Store this in `action_history` or `accumulated_form_data`.
-   **Cancellation/Pausing:** Allow the user to gracefully cancel or pause the multi-step application process at any point. State should be saved to allow resumption if paused.

## 6. Future Considerations

-   **Learning from User Corrections:** Systematically log user corrections (e.g., re-mapping a field's semantic meaning, correcting a filled value, choosing a different navigation button). This data can be invaluable for fine-tuning AI models or heuristics over time.
-   **Handling CAPTCHAs:** This is a significant challenge. Initial versions will likely require human intervention. Future exploration could involve integrating with third-party CAPTCHA-solving services (with ethical and cost considerations).
-   **More Sophisticated State Synchronization:** If the user is allowed to manually interact with the form (e.g., fill a field themselves) while the automation is also running, ensuring the AI's understanding of the page state remains accurate is complex. This might involve re-scraping field values after user interaction or more tightly coupled browser event monitoring.
-   **Dynamic Profile Updates:** Allowing the user to update their profile mid-application if they realize some information is missing or incorrect, and having those changes reflected in subsequent steps.
-   **Conditional Logic in Forms:** Handling forms where selections in one field dynamically change the availability or requirements of other fields on the same page. This requires re-triggering AI analysis after such changes.
-   **Saving and Resuming Applications:** Persisting the full application state to allow users to resume lengthy applications later.
