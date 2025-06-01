# app/orchestrator/mvp_orchestrator.py
import time
import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime # For feedback logging timestamp

# Integration Imports
import logging # For more detailed logging in _call_ai_core
from app.browser_automation.mvp_selenium_wrapper import MVPSeleniumWrapper
from app.main import SITE_SELECTORS # Added import
# from app.ai_core.mvp_visual_linker import extract_and_ground_page_elements # No longer used directly here
from app.ai_core.mvp_field_filler import generate_text_fill_actions_for_mvp as mvp_generate_text_fill_actions # Keep for action gen
from app.ai_core.live_visual_perception import get_llm_field_predictions, parse_llm_output_to_identified_elements
from app.ai_core.live_visual_grounder import ground_visual_elements
from app.ai_core.live_semantic_matcher import annotate_fields_with_semantic_meaning # New integration
from app.common.ai_core_data_structures import IdentifiedFormField, NavigationElement, NavigationActionType # For isinstance and nav logic
from app.ai_core.live_question_answerer import generate_answer_for_question, _load_user_profile, _load_job_description
from app.common.ai_core_data_structures import QuestionAnsweringResult

# (Simulated) User Profile for MVP
MVP_USER_PROFILE = {
    "user.firstName": "MVP_John",
    "user.lastName": "MVP_Doe",
    "user.email.primary": "mvp_john.doe@example.com",
    "user.phone.mobile": "123-456-7890",
    "automation_test_target_url": "https://www.realjobapply.com/apply/job123" # For mvp_visual_linker
}

LOG_FILE_PATH = "logs/mvp_feedback_log.txt"

# States
class OrchestratorState:
    IDLE = "IDLE"
    AWAITING_JOB_URL = "AWAITING_JOB_URL"
    LOADING_PAGE_DATA = "LOADING_PAGE_DATA"
    AWAITING_LOGIN_APPROVAL = "AWAITING_LOGIN_APPROVAL" # New state
    EXECUTING_LOGIN = "EXECUTING_LOGIN" # New state
    CALLING_AI_CORE = "CALLING_AI_CORE"
    AWAITING_APPLY_BUTTON_APPROVAL = "AWAITING_APPLY_BUTTON_APPROVAL" # New state
    EXECUTING_APPLY_BUTTON_CLICK = "EXECUTING_APPLY_BUTTON_CLICK" # New state
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    EXECUTING_AUTOMATION = "EXECUTING_AUTOMATION"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    FAILED_ERROR = "FAILED_ERROR"

class MVCOrchestrator:
    def __init__(self, webdriver_path: Optional[str] = None):
        self.current_state = OrchestratorState.IDLE
        self.job_url = None
        self.page_data_cache: Optional[Dict[str, Any]] = None
        self.ai_recommendations_cache: Optional[Dict[str, Any]] = None
        self.user_profile = MVP_USER_PROFILE

        self.browser_wrapper = MVPSeleniumWrapper(webdriver_path=webdriver_path)
        if not self.browser_wrapper.driver:
            print("CRITICAL: Browser wrapper failed to initialize. Orchestrator cannot function.")
            self.current_state = OrchestratorState.FAILED_ERROR
        print("MVP Orchestrator initialized.")

    def _load_page_data(self, url: str) -> Optional[Dict[str, Any]]:
        print(f"Orchestrator: Loading page data for {url}...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available.")
            return None

        if not self.browser_wrapper.navigate_to_url(url):
            print(f"Error: Failed to navigate to URL: {url}")
            return None

        current_url, screenshot_bytes, dom_string = self.browser_wrapper.get_page_state()

        if not current_url or not dom_string:
            print("Error: Failed to get essential page state (URL or DOM).")
            return None

        return {"url": current_url, "screenshot_bytes": screenshot_bytes, "dom_string": dom_string}

    def _handle_login(self) -> bool:
        """
        Handles the automated login process.
        Uses hardcoded credentials and selectors.
        Returns True if login attempt was successful (all steps executed), False otherwise.
        """
        print("Orchestrator: Attempting auto-login...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for login.")
            return False

        username = "testuser"
        password = "testpassword" # Hardcoded as per requirement

        default_site_selectors = SITE_SELECTORS.get("default", {})
        if not default_site_selectors:
            print("Login Error: 'default' site selectors not found in SITE_SELECTORS.")
            return False

        username_selector_config = default_site_selectors.get("login_username")
        password_selector_config = default_site_selectors.get("login_password")
        login_button_selector_config = default_site_selectors.get("login_button")

        # Validate selectors
        if not (username_selector_config and \
                isinstance(username_selector_config, dict) and \
                'type' in username_selector_config and 'value' in username_selector_config):
            print(f"Login Error: Invalid or missing selector configuration for 'login_username' in default selectors: {username_selector_config}")
            return False

        if not (password_selector_config and \
                isinstance(password_selector_config, dict) and \
                'type' in password_selector_config and 'value' in password_selector_config):
            print(f"Login Error: Invalid or missing selector configuration for 'login_password' in default selectors: {password_selector_config}")
            return False

        if not (login_button_selector_config and \
                isinstance(login_button_selector_config, dict) and \
                'type' in login_button_selector_config and 'value' in login_button_selector_config):
            print(f"Login Error: Invalid or missing selector configuration for 'login_button' in default selectors: {login_button_selector_config}")
            return False

        # Fill username
        print(f"Attempting to fill username with selector: {username_selector_config}")
        if not self.browser_wrapper.fill_text_field(
            selector=username_selector_config['value'],
            text=username,
            find_by=username_selector_config['type']
        ):
            print(f"Login Error: Could not find or fill username field using config: {username_selector_config}")
            return False
        print("Filled username field.")
        time.sleep(0.2) # Small delay

        # Fill password
        print(f"Attempting to fill password with selector: {password_selector_config}")
        if not self.browser_wrapper.fill_text_field(
            selector=password_selector_config['value'],
            text=password,
            find_by=password_selector_config['type']
        ):
            print(f"Login Error: Could not find or fill password field using config: {password_selector_config}")
            return False
        print("Filled password field.")
        time.sleep(0.2) # Small delay

        # Click login button
        print(f"Attempting to click login button with selector: {login_button_selector_config}")
        if not self.browser_wrapper.click_element(
            selector=login_button_selector_config['value'],
            find_by=login_button_selector_config['type']
        ):
            print(f"Login Error: Could not find or click login button using config: {login_button_selector_config}")
            return False
        print("Clicked login button.")

        # Assuming login leads to a new page or state, wait a bit for it to settle.
        # More robust check would be to verify if login was successful (e.g. new URL, element present/absent)
        time.sleep(2) # Wait for page to potentially reload or redirect

        # For now, success means all actions were attempted.
        # A more robust check would involve verifying the page content or URL after login.
        print("Orchestrator: Auto-login actions executed.")
        # Potentially refresh page_data_cache here if login changes the page significantly
        # current_url, screenshot_bytes, dom_string = self.browser_wrapper.get_page_state()
        # self.page_data_cache = {"url": current_url, "screenshot_bytes": screenshot_bytes, "dom_string": dom_string}
        # print("Refreshed page data after login attempt.")
        return True

    def _handle_auto_click_apply(self) -> bool:
        """
        Attempts to find and click an "apply" button using a specific CSS selector.
        Returns True if the button is found and clicked successfully, False otherwise.
        """
        print("Orchestrator: Attempting to auto-click 'apply' button...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for auto-click apply.")
            return False

        apply_button_selector = 'button[aria-label*="Apply"]' # As per requirement

        if self.browser_wrapper.click_element(xpath=apply_button_selector, find_by="css_selector"):
            print(f"Successfully clicked 'apply' button (selector: {apply_button_selector}).")
            time.sleep(2) # Wait for page to potentially reload or redirect
            return True
        else:
            print(f"Could not find or click 'apply' button (selector: {apply_button_selector}).")
            return False

    def _call_ai_core(self, page_state: Dict[str, Any], user_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logging.info(f"Orchestrator: Calling AI Core with page data for {page_state.get('url')}")
        logging.debug(f"Page state received (screenshot type): { {k: (type(v) if k=='screenshot_bytes' else v) for k,v in page_state.items()} }")

        screenshot_bytes = page_state.get("screenshot_bytes")
        dom_string = page_state.get("dom_string")

        if not screenshot_bytes:
            logging.error("AI Core: Screenshot bytes are missing in page_state. Cannot proceed.")
            return None
        if not dom_string:
            logging.warning("AI Core: DOM string is missing in page_state. Grounding quality may be affected.")

        # 1. Get All Interactable DOM Element Details from the live page
        logging.info("AI Core: Fetching all interactable DOM element details from browser...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            logging.error("AI Core: Browser wrapper not available for fetching DOM element details.")
            return None
        actual_dom_elements_details = self.browser_wrapper.get_all_interactable_elements_details()
        if not actual_dom_elements_details:
            logging.warning("AI Core: No interactable DOM elements found by browser_wrapper. Grounding will likely fail.")
        logging.info(f"AI Core: Found {len(actual_dom_elements_details)} interactable DOM elements on the page.")
        logging.debug(f"First few DOM elements: {actual_dom_elements_details[:2]}")

        # 2. Live Visual Perception (LLM Call)
        logging.info("AI Core: Attempting live LLM field predictions...")
        raw_llm_output = get_llm_field_predictions(
            screenshot_bytes=screenshot_bytes,
            page_dom_string=dom_string,
            live_llm_call=True
        )
        if not raw_llm_output:
            logging.error("AI Core: Live LLM prediction (get_llm_field_predictions) failed or returned no data.")
            return None
        logging.info("AI Core: Received raw output from LLM.")
        logging.debug(f"Raw LLM output dictionary: {raw_llm_output}")

        identified_elements_visual_only, navigation_elements_visual_only = parse_llm_output_to_identified_elements(raw_llm_output)
        logging.info(f"AI Core: Parsed LLM output. Found {len(identified_elements_visual_only)} visual form fields and {len(navigation_elements_visual_only)} visual navigation elements.")

        # 3. Live Visual Grounding
        all_visual_elements_to_ground = identified_elements_visual_only + navigation_elements_visual_only
        if not all_visual_elements_to_ground:
            logging.warning("AI Core: No visual elements identified by LLM to ground.")
            return {
                "summary": "No visual elements identified by LLM. Nothing to ground or process further.",
                "fields_to_fill": [], "actions": [], "navigation_element_text": "N/A"
            }

        logging.info(f"AI Core: Starting visual grounding for {len(all_visual_elements_to_ground)} elements...")
        grounded_elements_mixed = ground_visual_elements(all_visual_elements_to_ground, actual_dom_elements_details)

        grounded_form_fields: List[IdentifiedFormField] = []
        grounded_navigation_elements: List[NavigationElement] = []
        for el in grounded_elements_mixed:
            if isinstance(el, IdentifiedFormField):
                grounded_form_fields.append(el)
            elif isinstance(el, NavigationElement):
                grounded_navigation_elements.append(el)

        count_successfully_grounded_fields = sum(1 for f in grounded_form_fields if f.dom_path_primary)
        count_successfully_grounded_navs = sum(1 for n in grounded_navigation_elements if n.dom_path_primary)
        logging.info(f"AI Core: Grounding complete. {count_successfully_grounded_fields}/{len(grounded_form_fields)} form fields and "
                     f"{count_successfully_grounded_navs}/{len(grounded_navigation_elements)} navigation elements were grounded.")

        # 4. Live Semantic Matching (using live-grounded fields)
        logging.info("AI Core: Performing LIVE semantic matching on grounded fields...")
        semantically_matched_fields = annotate_fields_with_semantic_meaning(grounded_form_fields, live_llm_call=True)
        count_successfully_semantic_matched = sum(1 for f in semantically_matched_fields if f.semantic_meaning_predicted and f.semantic_meaning_predicted != "system_internal.other_unspecified_field")
        logging.info(f"AI Core: Live semantic matching complete. {count_successfully_semantic_matched}/{len(semantically_matched_fields)} fields have a specific semantic meaning assigned.")

        # --- START QA INTEGRATION ---
        question_answers_generated: List[QuestionAnsweringResult] = []
        # Note: user_profile is passed into _call_ai_core, but QA module uses its own loader for the full profile.
        # This is acceptable as MVP_USER_PROFILE might be a subset or different structure.
        user_profile_for_qa = _load_user_profile() # Loads "my_cv.json" by default
        job_description_text_for_qa = _load_job_description() # Loads "job_description.txt" by default

        # Extract job title and company from the orchestrator's user_profile (which might be enriched from various sources)
        job_title_context = self.user_profile.get("application.job_details.job_title",
                                                  user_profile.get("application.job_details.job_title", "the current role"))
        company_name_context = self.user_profile.get("application.job_details.company_name",
                                                     user_profile.get("application.job_details.company_name", "the company"))

        job_context_for_qa = {
            "job_title": job_title_context,
            "company_name": company_name_context,
            "job_description_summary": job_description_text_for_qa if job_description_text_for_qa else ""
        }

        # Use a copy of the orchestrator's current user_profile for action generation,
        # as this might contain data not in my_cv.json (e.g. pre-filled form data from previous steps if any)
        temp_user_profile_for_action_gen = user_profile.copy()

        for field in semantically_matched_fields:
            if field.semantic_meaning_predicted and \
               (field.semantic_meaning_predicted.startswith("application.custom_question") or \
                field.semantic_meaning_predicted == "application.cover_letter_text_final"):

                logging.info(f"AI Core: Identified question field: '{field.visual_label_text}' ({field.semantic_meaning_predicted})")
                question_text = field.visual_label_text if field.visual_label_text else f"Response for {field.semantic_meaning_predicted}"

                # Ensure user_profile_for_qa is not None before passing. If it is, QA will handle it.
                qa_result = generate_answer_for_question(
                    question_text=question_text,
                    dom_path_question=field.dom_path_primary,
                    semantic_key_of_question=field.semantic_meaning_predicted,
                    user_profile_data=user_profile_for_qa,
                    job_context_data=job_context_for_qa,
                    live_llm_call=True
                )
                question_answers_generated.append(qa_result)

                if qa_result.suggested_answer_draft and not qa_result.suggested_answer_draft.startswith("Error:") and not "blocked" in qa_result.suggested_answer_draft:
                    # Update the temporary profile with the generated answer
                    # This makes the QA answer available for the mvp_generate_text_fill_actions
                    temp_user_profile_for_action_gen[field.semantic_meaning_predicted] = qa_result.suggested_answer_draft
                    logging.info(f"AI Core: QA answer for '{field.semantic_meaning_predicted}' will be used for action generation.")
                else:
                    logging.warning(f"AI Core: QA for '{field.semantic_meaning_predicted}' did not produce a usable answer. Original profile value (if any) will be used for this field's action.")


        logging.info("AI Core: Generating MVP text fill actions (potentially with QA answers in profile)...")
        fill_actions_details_obj_list = mvp_generate_text_fill_actions(
            semantically_matched_fields,
            temp_user_profile_for_action_gen # Use the potentially augmented profile
        )
        logging.info(f"AI Core: MVP text fill action generation complete. {len(fill_actions_details_obj_list)} fill actions proposed.")
        if not fill_actions_details_obj_list and count_successfully_grounded_fields > 0 and not any(qa.suggested_answer_draft for qa in question_answers_generated) :
             logging.warning("AI Core: No fill actions generated by MVP action generator (and no QA answers were generated/used). This might be due to semantic keys not matching user profile, no grounded paths, or no fillable types found.")
        # --- END QA INTEGRATION (Action Generation Part) ---

        # Construct fields_to_display for user review using temp_user_profile_for_action_gen
        fields_to_display = []
        for field in semantically_matched_fields:
            # Default to profile value, then check if a QA answer overrode it
            value_to_fill_display = temp_user_profile_for_action_gen.get(field.semantic_meaning_predicted, "N/A_IN_PROFILE") \
                                    if field.semantic_meaning_predicted else "N/A_SEMANTIC_MATCH"

            corresponding_qa: Optional[QuestionAnsweringResult] = next(
                (qa for qa in question_answers_generated if qa.dom_path_question == field.dom_path_primary and qa.suggested_answer_draft and not qa.suggested_answer_draft.startswith("Error:")), None
            )
            display_semantic_key = field.semantic_meaning_predicted if field.semantic_meaning_predicted else "NONE"

            if corresponding_qa:
                # If there's a QA answer, make sure to display that, possibly truncated for brevity
                value_to_fill_display = f"[QA Draft]: {corresponding_qa.suggested_answer_draft[:100]}"
                if len(corresponding_qa.suggested_answer_draft) > 100:
                    value_to_fill_display += "..."
            elif field.semantic_meaning_predicted and field.semantic_meaning_predicted in temp_user_profile_for_action_gen and \
                 field.semantic_meaning_predicted not in [qa.semantic_key_of_question for qa in question_answers_generated if qa.suggested_answer_draft]: # Value from profile, not a failed QA
                value_to_fill_display = temp_user_profile_for_action_gen[field.semantic_meaning_predicted]


            fields_to_display.append({
                "label": field.visual_label_text or "Unknown Label",
                "value": value_to_fill_display, # This now reflects QA answers if available
                "xpath": field.dom_path_primary if field.dom_path_primary else "NOT_GROUNDED",
                "semantic_key_assigned": display_semantic_key,
                "overall_confidence": field.confidence_score
            })

        final_actions_list = [action.to_dict() for action in fill_actions_details_obj_list]

        chosen_navigation_text = "No usable navigation found." # Initialize here
        nav_target: Optional[NavigationElement] = None # Initialize here

        if grounded_navigation_elements:
            submit_navs = [n for n in grounded_navigation_elements if n.action_type_predicted == NavigationActionType.SUBMIT_FORM and n.dom_path_primary]
            if submit_navs: nav_target = submit_navs[0]
            else:
                next_navs = [n for n in grounded_navigation_elements if n.action_type_predicted == NavigationActionType.NEXT_PAGE and n.dom_path_primary]
                if next_navs: nav_target = next_navs[0]
                else:
                    first_grounded_nav = next((n for n in grounded_navigation_elements if n.dom_path_primary), None)
                    if first_grounded_nav: nav_target = first_grounded_nav

            if nav_target:
                chosen_navigation_text = nav_target.visual_label_text or "Unnamed Navigation"
                final_actions_list.append({
                    "action_type": "CLICK_ELEMENT",
                    "dom_path_target": nav_target.dom_path_primary,
                    "visual_label": chosen_navigation_text
                })
                logging.info(f"AI Core: Selected navigation action: Click '{chosen_navigation_text}' (XPath: {nav_target.dom_path_primary})")
            elif any(n.dom_path_primary for n in grounded_navigation_elements):
                 chosen_navigation_text = "Grounded navigation found, but no clear submit/next/usable target."
                 logging.warning(f"AI Core: {chosen_navigation_text}")
            else:
                 chosen_navigation_text = "Navigation elements visually found but none could be grounded with a DOM path."
                 logging.warning(f"AI Core: {chosen_navigation_text}")
        else:
            logging.info("AI Core: No navigation elements were passed from visual perception to grounding.")

        summary_message = (
            f"LivePerception: {len(identified_elements_visual_only)} vis-fields, {len(navigation_elements_visual_only)} vis-navs. "
            f"Grounder: {count_successfully_grounded_fields}/{len(grounded_form_fields)} fields, {count_successfully_grounded_navs}/{len(grounded_navigation_elements)} navs. "
            f"LiveSemantics: {count_successfully_semantic_matched}/{len(semantically_matched_fields)} fields matched. "
            f"MVPActions: {len(fill_actions_details_obj_list)} fill actions. QA Generated: {len(question_answers_generated)}."
        )

        final_recommendations = {
            "summary": summary_message,
            "fields_to_fill": fields_to_display,
            "actions": final_actions_list,
            "navigation_element_text": chosen_navigation_text, # This should be determined after all field processing
            "question_answers_to_review": [qa.to_dict() for qa in question_answers_generated]
        }
        logging.debug(f"Final AI recommendations (with QA): {final_recommendations}")
        return final_recommendations

    def _execute_browser_automation(self, actions: List[Dict[str, Any]]) -> bool:
        logging.info("Orchestrator: Executing browser automation actions...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for executing actions.")
            return False

        for i, action_dict in enumerate(actions):
            action_type = action_dict.get('action_type')
            dom_path = action_dict.get('dom_path_target')
            value = action_dict.get('value_to_fill')

            print(f"  Action {i+1}/{len(actions)}: Type: {action_type}, Path: {dom_path}" + (f", Value: '{str(value)[:30]}...'" if value else ""))

            success = False
            if action_type == "FILL_TEXT":
                if dom_path and value is not None and dom_path != "NOT_GROUNDED" and "MISSING" not in dom_path:
                    success = self.browser_wrapper.fill_text_field(xpath=dom_path, text=str(value))
                else:
                    print(f"    Skipping FILL_TEXT due to missing path ('{dom_path}') or value.")
            elif action_type == "CLICK_ELEMENT":
                if dom_path and dom_path != "NOT_GROUNDED" and "MISSING" not in dom_path:
                    success = self.browser_wrapper.click_element(xpath=dom_path)
                else:
                    print(f"    Skipping CLICK_ELEMENT due to missing path ('{dom_path}').")
            else:
                print(f"    Warning: Unknown action type '{action_type}' in action sequence.")
                continue

            if not success:
                print(f"  Action failed: {action_type} on {dom_path}")
                return False

            time.sleep(0.5)

        print("Orchestrator: All browser automation actions completed successfully.")
        return True

    def run(self):
        if self.current_state == OrchestratorState.FAILED_ERROR and not self.browser_wrapper.driver:
            print("Orchestrator cannot start due to browser initialization failure.")
            self.current_state = OrchestratorState.IDLE

        if self.current_state == OrchestratorState.IDLE and self.browser_wrapper.driver:
             self.current_state = OrchestratorState.AWAITING_JOB_URL

        print(f"State: {self.current_state}")

        try:
            while True:
                if self.current_state == OrchestratorState.AWAITING_JOB_URL:
                    use_predefined_url = input(f"Use predefined target URL ({MVP_USER_PROFILE.get('automation_test_target_url', 'N/A')})? (y/n/quit): ").lower()
                    if use_predefined_url == 'y':
                        self.job_url = MVP_USER_PROFILE.get('automation_test_target_url')
                        if not self.job_url:
                            print("Error: Predefined URL not set in profile. Please enter manually.")
                            continue
                    elif use_predefined_url == 'n':
                        self.job_url = input("Enter the job application URL (or 'quit'): ")
                    elif use_predefined_url == 'quit':
                        self.current_state = OrchestratorState.IDLE
                    else:
                        print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                        continue

                    if self.job_url and self.job_url.lower() == 'quit':
                        self.current_state = OrchestratorState.IDLE

                    if self.current_state == OrchestratorState.IDLE:
                        pass
                    elif not self.job_url or not self.job_url.startswith("http"):
                        print("Invalid or missing URL. Please include http:// or https:// or choose 'y' for predefined.")
                        self.job_url = None
                    else:
                        self.current_state = OrchestratorState.LOADING_PAGE_DATA
                        print(f"State: {self.current_state} - URL: {self.job_url}")

                elif self.current_state == OrchestratorState.LOADING_PAGE_DATA:
                    if not self.job_url:
                        print("Error: No job URL to load. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    self.page_data_cache = self._load_page_data(self.job_url)
                    if self.page_data_cache:
                        # Successfully loaded page, now ask about login
                        self.current_state = OrchestratorState.AWAITING_LOGIN_APPROVAL
                    else:
                        print("Error: Failed to load page data.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_LOGIN_APPROVAL:
                    login_choice = input("Attempt auto-login? (y/n/quit): ").lower()
                    if login_choice == 'y':
                        self.current_state = OrchestratorState.EXECUTING_LOGIN
                    elif login_choice == 'n':
                        print("Skipping auto-login. Proceeding to apply button check.")
                        self.current_state = OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL # Changed
                    elif login_choice == 'quit':
                        self.current_state = OrchestratorState.IDLE
                    else:
                        print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.EXECUTING_LOGIN:
                    print("Executing auto-login...")
                    login_success = self._handle_login()
                    if login_success:
                        print("Auto-login successful (actions performed). Proceeding to AI Core.")
                        # IMPORTANT: After login, the page content has likely changed.
                        # We should refresh the page data cache.
                        print("Refreshing page data after login...")
                        # Use current URL from browser after login attempt
                        current_url_after_login, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
                        if not current_url_after_login: # Fallback if get_page_state fails
                            current_url_after_login = self.job_url

                        self.page_data_cache = self._load_page_data(current_url_after_login)
                        if self.page_data_cache:
                             print("Page data refreshed after login. Proceeding to apply button check.")
                             self.current_state = OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL # Changed
                        else:
                             print("Error: Failed to reload page data after login attempt.")
                             self.current_state = OrchestratorState.FAILED_ERROR
                    else:
                        print("Auto-login failed. Check selectors or page structure.")
                        self.current_state = OrchestratorState.FAILED_ERROR # Or perhaps back to AWAITING_LOGIN_APPROVAL or CALLING_AI_CORE
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.CALLING_AI_CORE:
                    if not self.page_data_cache:
                        print("Error: No page data to process. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    self.ai_recommendations_cache = self._call_ai_core(self.page_data_cache, self.user_profile)
                    if self.ai_recommendations_cache: # Check if cache is not None
                        # Further check if actions exist, or if it's a "nothing to do" summary
                        # If AI core provides recommendations, move to user approval
                        if self.ai_recommendations_cache.get("actions") or \
                           (self.ai_recommendations_cache.get("summary") and "Nothing to ground" in self.ai_recommendations_cache.get("summary", "")):
                            print("AI Core processing complete. Proceeding to user approval.")
                            self.current_state = OrchestratorState.AWAITING_USER_APPROVAL # Changed
                        else: # No actions and not a 'nothing to do' summary, implies an issue
                            print("Error: Failed to get valid AI recommendations or no actionable items proposed by AI Core.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                    else: # ai_recommendations_cache is None
                        print("Error: AI Core processing failed to return any recommendations.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL:
                    apply_choice = input("Attempt to auto-click an 'apply' button on this page? (y/n/quit): ").lower()
                    if apply_choice == 'y':
                        self.current_state = OrchestratorState.EXECUTING_APPLY_BUTTON_CLICK
                    elif apply_choice == 'n':
                        print("Skipping auto-click of 'apply' button. Proceeding to AI Core analysis for form filling.")
                        self.current_state = OrchestratorState.CALLING_AI_CORE # Changed: Ensure AI Core runs if apply is skipped
                    elif apply_choice == 'quit':
                        self.current_state = OrchestratorState.IDLE
                    else:
                        print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.EXECUTING_APPLY_BUTTON_CLICK:
                    print("Executing auto-click 'apply' button...")
                    apply_clicked_successfully = self._handle_auto_click_apply()
                    if apply_clicked_successfully:
                        print("Auto-click 'apply' successful. Refreshing page data and re-running AI Core...")
                        # Refresh page data cache as the page likely changed
                        current_url_after_apply, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
                        if not current_url_after_apply:
                             current_url_after_apply = self.job_url # Fallback

                        self.page_data_cache = self._load_page_data(current_url_after_apply)
                        if self.page_data_cache:
                            self.current_state = OrchestratorState.CALLING_AI_CORE # Re-analyze the new page
                        else:
                            print("Error: Failed to reload page data after 'apply' click.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                    else:
                        print("Auto-click 'apply' button failed or button not found. Proceeding to AI Core analysis of current page.")
                        # If apply click fails, the page hasn't changed. We need to run AI core on this page.
                        self.current_state = OrchestratorState.CALLING_AI_CORE # Changed
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_USER_APPROVAL:
                    if not self.ai_recommendations_cache:
                        print("Error: No AI recommendations to approve. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    print("\n--- AI Recommendations ---")
                    print(f"Summary: {self.ai_recommendations_cache.get('summary', 'N/A')}")
                    print("Fields to fill/identified:") # Changed from "Fields to fill"
                    for field_info in self.ai_recommendations_cache.get('fields_to_fill', []): # fields_to_fill is now fields_to_display
                        print(f"  - Label: {field_info.get('label', 'N/A')}, "
                              f"Value to Fill: '{field_info.get('value', 'N/A')}', "
                              f"XPath: {field_info.get('xpath', 'N/A')}, "
                              f"Semantic Key: {field_info.get('semantic_key_assigned', 'N/A')}, "
                              f"Confidence: {field_info.get('overall_confidence', 'N/A')}")
                    print(f"Proposed Navigation: Click '{self.ai_recommendations_cache.get('navigation_element_text', 'N/A')}'")

                    # --- Display QA Answers ---
                    qa_answers_review = self.ai_recommendations_cache.get('question_answers_to_review', [])
                    if qa_answers_review:
                        print("\n--- Suggested Answers to Application Questions (Review) ---")
                        for i, qa_info in enumerate(qa_answers_review):
                            # Ensure qa_info is a dictionary here as to_dict() was called.
                            print(f"  Question {i+1} for Path '{qa_info.get('dom_path_question')}': {qa_info.get('question_text_identified')}")
                            print(f"    Suggested Answer: {qa_info.get('suggested_answer_draft')}")
                        print("--- End of Suggested Answers (Review) ---")
                    # --- END Display QA Answers ---

                    # Check if there are any actions to perform (could be just QA to review)
                    if not self.ai_recommendations_cache.get("actions") and not qa_answers_review:
                        print("No actions proposed by AI and no QA answers to review. Resetting for new URL.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        time.sleep(1) # Pause to allow user to read
                        continue
                    elif not self.ai_recommendations_cache.get("actions") and qa_answers_review:
                        print("Only QA answers to review. No direct browser actions proposed. Please review the QA answers.")
                        # Keep in this state for user to review QA, then they can decide what to do next.
                        # Potentially, they might want to manually use these answers.
                        # For now, we'll just let them decide to 'quit' or implicitly 'n' by not approving.


                    approval = input("Approve and apply (this includes all fields and QA answers)? (y/n/quit): ").lower()
                    if approval == 'y':
                        if not self.ai_recommendations_cache.get("actions") and qa_answers_review:
                            print("Approved QA answers. No direct browser actions to execute. Resetting for next URL.")
                            self._log_user_approval_of_qa_only() # Optional: log this specific scenario
                            self.current_state = OrchestratorState.AWAITING_JOB_URL
                            continue
                        self.current_state = OrchestratorState.EXECUTING_AUTOMATION
                    elif approval == 'n':
                        print("Application not approved by user. Logging feedback and resetting.")
                        self._log_user_disapproval() # This will log the full cache including QA
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                    elif approval == 'quit':
                        self.current_state = OrchestratorState.IDLE
                    else:
                        print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.EXECUTING_AUTOMATION:
                    # Ensure there are actions even if approval was for QA only (which should skip execution here)
                    if not self.ai_recommendations_cache or not self.ai_recommendations_cache.get("actions"):
                        print("Error: No browser actions to execute. This state should not be reached if only QA was approved. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue

                    success = self._execute_browser_automation(self.ai_recommendations_cache['actions'])
                    if success:
                        self.current_state = OrchestratorState.COMPLETED_SUCCESS
                    else:
                        print("Orchestrator: Execution of browser automation failed.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.COMPLETED_SUCCESS:
                    print(f"\nApplication process for {self.job_url} completed successfully!")
                    self.job_url = None
                    self.current_state = OrchestratorState.AWAITING_JOB_URL
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.FAILED_ERROR:
                    print(f"\nApplication process for {self.job_url} failed or encountered an error.")
                    self.job_url = None
                    self.current_state = OrchestratorState.AWAITING_JOB_URL
                    print(f"State: {self.current_state}")

                if self.current_state == OrchestratorState.IDLE:
                    print("Orchestrator preparing to shut down...")
                    break

                time.sleep(0.1)
        finally:
            if self.browser_wrapper:
                self.browser_wrapper.close_browser()
            print("Orchestrator shut down.")

    def _log_user_disapproval(self):
        if not self.ai_recommendations_cache:
            print("LogFeedback: No AI recommendations to log.")
            return

        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_url": self.job_url,
            "reason": "User disapproved AI recommendations.",
            "ai_recommendations": self.ai_recommendations_cache
        }

        try:
            with open(LOG_FILE_PATH, 'a') as f:
                f.write(json.dumps(feedback_entry) + "\n")
            print(f"LogFeedback: User disapproval logged to {LOG_FILE_PATH}")
        except IOError as e:
            print(f"LogFeedback: Error writing to log file {LOG_FILE_PATH}: {e}")
        except Exception as e:
            print(f"LogFeedback: An unexpected error occurred during logging: {e}")

    def _log_user_approval_of_qa_only(self):
        # Placeholder for logging when user approves only QA items and no browser actions
        # This method was referenced in the previous turn's code but not defined.
        # For now, just a print statement.
        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_url": self.job_url,
            "reason": "User approved QA-only recommendations.",
            "ai_recommendations": self.ai_recommendations_cache # Log the full cache for context
        }
        try:
            with open(LOG_FILE_PATH, 'a') as f:
                f.write(json.dumps(feedback_entry) + "\n")
            print(f"LogFeedback: User QA-only approval logged to {LOG_FILE_PATH}")
        except IOError as e:
            print(f"LogFeedback: Error writing to log file {LOG_FILE_PATH}: {e}")
        except Exception as e: # pylint: disable=broad-except
            print(f"LogFeedback: An unexpected error occurred during QA-only logging: {e}")


if __name__ == "__main__":
    orchestrator = MVCOrchestrator()
    orchestrator.run()
