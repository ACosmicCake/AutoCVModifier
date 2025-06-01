# Integration Points and APIs

## 1. Introduction

**Purpose:**
This document defines the primary communication interfaces (APIs) and interaction patterns between the core components of the AutoApply system: the Orchestration Engine, the AI Core Module, the Browser Automation Layer, and the User Profile Database. Establishing clear contracts is crucial for modularity, enabling independent development, testing, and evolution of each component.

**Importance:**
Clear APIs ensure that components can interact reliably, even if their internal implementations change. This promotes a separation of concerns and simplifies the overall system architecture.

## 2. AI Core Module API

The AI Core Module encapsulates all AI-driven analysis and decision-making.

-   **Primary Endpoint/Function:** `process_page_and_generate_recommendations`
    -   **Description:** This is the main entry point for the Orchestration Engine to get a comprehensive analysis of a web page and a recommended set of actions.
    -   **Input:** `AICoreInput` (object, as defined in `ai_core_data_structures.py`). This composite object includes:
        -   `page_screenshot`: Image data of the current page view (bytes or path).
        -   `dom_structure`: HTML content as a string or a structured JSON representation of the DOM.
        -   `accessibility_tree` (Optional): Structured accessibility information (e.g., JSON).
        -   `metadata`: Contains `url`, `timestamp`, and an optional `user_profile_summary` (high-level user context like preferred language, target role).
        -   `previous_actions_summary` (Optional): A list of actions taken on previous steps of a form, providing context for multi-step interactions.
    -   **Output:** `AICoreOutput` (object, a Union type as defined in `ai_core_data_structures.py`). The output will be one of the following types, depending on the AI's assessment and needs:
        -   `FormUnderstandingResult`: Detailed analysis of form fields (labels, locations, types, semantic meaning) and identified navigation elements. This is typical for standard form pages.
        -   `QuestionAnsweringResult`: A drafted answer for an open-ended question identified on the page. This *always* requires user review and approval.
        -   `ActionSequenceRecommendation`: A suggested sequence of browser actions (e.g., fill field, click button) for the Browser Automation Layer to execute. This is the most common output when the AI is confident about how to proceed.
        -   `ClarificationRequest`: Issued when the AI encounters ambiguity that it cannot resolve on its own (e.g., two fields with similar labels, uncertain field mapping) and requires user input.
    -   **Interaction Pattern:** Synchronous request/response. The Orchestration Engine sends the `AICoreInput` and waits for the `AICoreOutput`.
    -   **Internal Orchestration within AI Core:**
        A single call to `process_page_and_generate_recommendations` is expected to trigger the AI Core's internal pipeline. This typically involves:
        1.  Visual Perception Module: Analyzes `page_screenshot` to identify visual elements.
        2.  Visual Grounding Module: Maps visual elements to the `dom_structure`.
        3.  Semantic Matching Module: Infers the meaning of identified fields using `visual_label_text`, DOM context, and `user_profile_summary`.
        4.  Question Answering Module (Conditional): If an open-ended question field is identified and needs an answer, this module drafts one using the full `user_profile_data` (which the Orchestrator would need to ensure is available to the AI Core, potentially by including more detail than just the summary if a question is anticipated). *Alternatively, the Orchestrator might call a separate QA endpoint after identifying a question field.*
        5.  Interaction Logic / Action Generation Orchestrator (internal to AI Core): Consolidates all findings, including QA drafts (if any), and generates the final `ActionSequenceRecommendation`, or decides if a `ClarificationRequest` or `QuestionAnsweringResult` (for review) is more appropriate.

    *Note on Granularity:* While a single, comprehensive endpoint simplifies initial integration, the AI Core *could* expose finer-grained functions (e.g., `get_form_understanding(screenshot, dom)`, `draft_answer_for_question(question_text, profile_data)`). This might be useful if the Orchestration Engine needs to run parts of the AI pipeline selectively or in a different order based on complex external logic. However, for the current conceptual design, a single primary endpoint is assumed for the main processing loop.

## 3. Browser Automation Layer Interface

This layer abstracts the underlying browser manipulation library (e.g., Selenium, Playwright) and provides a clean interface to the Orchestration Engine.

-   **Key Functions/Methods exposed to Orchestration Engine:**
    -   `initialize_browser(browser_type: str, options: Dict) -> bool`:
        *   Description: Starts a browser instance (e.g., Chrome, Firefox).
        *   Inputs: `browser_type` (e.g., "chrome", "firefox"), `options` (e.g., headless mode, user agent).
        *   Output: `True` on success, `False` on failure.
    -   `navigate_to_url(url: str) -> PageStateResult`:
        *   Description: Navigates the browser to the specified URL.
        *   Input: `url` (string).
        *   Output: `PageStateResult` object containing the state of the page after navigation.
    -   `get_current_page_state() -> PageStateResult`:
        *   Description: Captures and returns the current state of the active browser page.
        *   Output: `PageStateResult` object.
    -   `execute_browser_action(action: ActionDetail) -> BrowserActionResult`:
        *   Description: Executes a single `ActionDetail` object (e.g., fill text, click element, select dropdown option).
        *   Input: `action` (an `ActionDetail` object).
        *   Output: `BrowserActionResult` indicating success/failure and the new page state if the action caused a page change.
    -   `execute_action_sequence(actions: List[ActionDetail]) -> List[BrowserActionResult]`:
        *   Description: Executes a list of `ActionDetail` objects in sequence.
        *   Input: `actions` (a list of `ActionDetail` objects).
        *   Output: A list of `BrowserActionResult` objects, one for each action executed. The Orchestrator should check each result.
    -   `close_browser() -> bool`:
        *   Description: Closes the browser instance.
        *   Output: `True` on success, `False` on failure.

-   **Supporting Data Structures (to be formally defined, similar to `ai_core_data_structures.py`):**
    -   `PageStateResult`:
        *   `status`: Enum ("success", "failure")
        *   `url`: Optional[str] (Current URL after action/load)
        *   `screenshot_bytes`: Optional[bytes] (Screenshot image data)
        *   `dom_string`: Optional[str] (Full HTML of the page)
        *   `accessibility_tree_json`: Optional[str] (JSON string of the accessibility tree)
        *   `error_message`: Optional[str] (If status is "failure")
    -   `BrowserActionResult`:
        *   `action_id`: Optional[str] (Correlates to `ActionDetail.id` if provided in the input action, helping Orchestrator track specific actions)
        *   `status`: Enum ("success", "failure_element_not_found", "failure_element_not_interactable", "failure_timeout", "failure_unknown")
        *   `new_page_state`: Optional[PageStateResult] (The state of the page *after* the action, especially if it caused navigation or significant change. Could be None if action didn't change page context much.)
        *   `error_message`: Optional[str] (Detailed error if status indicates failure)
        *   `console_logs`: Optional[List[str]] (Any relevant browser console logs captured during the action)

## 4. User Profile Database Interface

This component is responsible for storing and retrieving user profile data. It could be a relational database, a NoSQL store, or even a local file system for simpler implementations.

-   **Conceptual API Endpoints/Functions for Orchestration Engine (RESTful or direct method calls):**
    -   `get_user_profile(user_id: str) -> UserProfileDataResult`:
        *   Description: Retrieves the full profile for a given user.
        *   Input: `user_id` (string).
        *   Output: `UserProfileDataResult` object.
            -   `UserProfileDataResult`:
                -   `status`: Enum ("success", "failure", "not_found")
                -   `data`: Optional[Dict[str, Any]] (The user's profile data, structured as expected by AI modules, e.g., `{"user.firstName": "John", "past_projects": [...]}`)
                -   `error_message`: Optional[str]
    -   `update_user_profile_section(user_id: str, section_key: str, section_data: Any) -> UpdateResult`:
        *   Description: Updates a specific section or key in the user's profile (e.g., `section_key` = "user.email.work", `section_data` = "new.email@example.com").
        *   Input: `user_id` (string), `section_key` (string, dot-notation for nesting), `section_data` (the new data).
        *   Output: `UpdateResult` object.
            -   `UpdateResult`:
                -   `status`: Enum ("success", "failure")
                -   `error_message`: Optional[str]
    -   `get_user_profile_summary(user_id: str, summary_fields: List[str]) -> UserProfileDataResult`:
        *   Description: Retrieves only specific high-level fields for the `AICoreInput.metadata.user_profile_summary`.
        *   Input: `user_id` (string), `summary_fields` (list of keys, e.g., ["preferred_language", "target_role_type"]).
        *   Output: `UserProfileDataResult` containing only the requested summary data.
    -   `get_relevant_profile_data_for_query(user_id: str, query_context: Dict[str, Any]) -> UserProfileDataResult`: (More Advanced)
        *   Description: Retrieves parts of the user profile deemed relevant to a specific query or context (e.g., for answering a specific open-ended question). The `query_context` might be structured by the AI Core or Orchestrator.
        *   Input: `user_id` (string), `query_context` (e.g., `{"keywords": ["experience", "python"], "field_type": "textarea"}`).
        *   Output: `UserProfileDataResult` with filtered/relevant data.

## 5. Orchestration Engine - Central Controller

The Orchestration Engine acts as the central nervous system. It does not expose an API in the same way as other components but rather *consumes* their APIs.

-   **Responsibilities:**
    -   Manages the overall application workflow as detailed in `multi_step_navigation_and_state_management.md`.
    -   Interfaces with the User Interface (not defined here) to present information, get approvals, and handle user interventions.
    -   Calls the Browser Automation Layer to interact with web pages.
    -   Calls the AI Core Module to understand page content and get action recommendations.
    -   Calls the User Profile Database to fetch and potentially update user data.
    -   Maintains the application state.

## 6. Communication Flow Example (Simplified Single Page Fill)

This illustrates a typical sequence for processing one page of a form:

1.  **Orchestrator (OE) -> Browser Automation Layer (BAL):**
    *   OE: `BAL.navigate_to_url("https://example.com/job_app_page_1")`
    *   BAL returns `PageStateResult_A` (URL, screenshot, DOM of page 1).
2.  **OE -> User Profile Database (UPDB):**
    *   OE: `UPDB.get_user_profile("user123")` (to get full profile for potential QA)
    *   UPDB returns `UserProfileDataResult_Full` (containing all user data).
    *   OE: `UPDB.get_user_profile_summary("user123", ["preferred_language", "target_role_type"])` (for `AICoreInput`)
    *   UPDB returns `UserProfileDataResult_Summary`.
3.  **OE -> AI Core Module (AIC):**
    *   OE constructs `AICoreInput` using `PageStateResult_A` and `UserProfileDataResult_Summary.data`.
    *   OE: `AIC.process_page_and_generate_recommendations(AICoreInput)`
    *   AIC returns `AICoreOutput`. Let's assume it's an `ActionSequenceRecommendation` (`ASR_1`) containing actions to fill fields and a "Next" button click. If it were a `QuestionAnsweringResult`, OE would handle user review first.
4.  **OE (User Review - Optional/Conditional):**
    *   If `ASR_1` contains high-impact actions or QA drafts (not in this specific flow path, but generally), OE presents them to the user for approval via the UI.
5.  **OE -> BAL:**
    *   OE: `BAL.execute_action_sequence(ASR_1.actions)`
    *   BAL executes each action (e.g., fill "First Name", fill "Email", click "Next"). It returns a list of `BrowserActionResult` objects. One of these results might indicate a page navigation occurred, providing the new `PageStateResult_B`.
6.  **OE (State Update & Next Step):**
    *   OE updates its internal state (action history, page history with `PageStateResult_B`, etc.) based on `BrowserActionResult` list.
    *   OE analyzes the results. If all successful and navigation occurred, it prepares to process the new page (`PageStateResult_B`) by looping back to step 3 (or step 1 if a fresh capture is needed), now using `PageStateResult_B`.

This flow provides a clear structure for how the components collaborate to automate the application process.
