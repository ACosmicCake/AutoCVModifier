# app/orchestrator/mvp_orchestrator.py
import time
import json
import os # Ensure os is imported
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime # For feedback logging timestamp

# Integration Imports
import logging # For more detailed logging in _call_ai_core
from app.browser_automation.mvp_selenium_wrapper import MVPSeleniumWrapper
from app.config_loader import SITE_SELECTORS # Changed import
# from app.ai_core.mvp_visual_linker import extract_and_ground_page_elements # No longer used directly here
from app.ai_core.mvp_field_filler import generate_text_fill_actions_for_mvp as mvp_generate_text_fill_actions # Keep for action gen
from app.ai_core.live_visual_perception import get_llm_field_predictions, parse_llm_output_to_identified_elements
from app.ai_core.live_visual_grounder import ground_visual_elements
from app.ai_core.live_semantic_matcher import annotate_fields_with_semantic_meaning # New integration
from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    NavigationElement,
    QuestionAnsweringResult,
    ActionSequenceRecommendation, # Added
    ActionSequenceActionType, # Added
    PredictedFieldType, # Added
    NavigationActionType,
    VisualLocation, # Added
    ActionDetail # Implicitly used by List[ActionDetail]
)
from app.ai_core.live_question_answerer import generate_answer_for_question, _load_user_profile, _load_job_description
# QuestionAnsweringResult is already imported via the grouped import above
from action_generation_orchestrator import orchestrate_action_sequence # Added for advanced action generation

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
        self.auto_apply_mode = False # Add this line
        self.current_target_url: Optional[str] = None # Added for multi-step navigation

        self.browser_wrapper = MVPSeleniumWrapper(webdriver_path=webdriver_path, headless=False)
        if not self.browser_wrapper.driver:
            print("CRITICAL: Browser wrapper failed to initialize. Orchestrator cannot function.")
            self.current_state = OrchestratorState.FAILED_ERROR
        print(f"Orchestrator initialized. AutoApply Mode: {self.auto_apply_mode}")

    def _load_page_data(self, url: str) -> Optional[Dict[str, Any]]:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Loading page data for {url}...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available.")
            return None

        if not self.browser_wrapper.navigate_to_url(url):
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Navigation failed for {url}.")
            return None

        current_url, screenshot_bytes, dom_string = self.browser_wrapper.get_page_state()

        if not current_url or not dom_string:
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Essential page state (URL or DOM) missing after loading {url}.")
            return None

        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Page data loaded successfully for {url}.")
        return {"url": current_url, "screenshot_bytes": screenshot_bytes, "dom_string": dom_string}

    def _validate_selector_config(self, config: Any, selector_name: str) -> bool:
        """Helper to validate a selector configuration."""
        if not (config and isinstance(config, dict) and 'type' in config and 'value' in config):
            print(f"Login Error: Invalid or missing selector configuration for '{selector_name}' in default selectors: {config}")
            return False
        return True

    def _attempt_login_after_trigger(self,
                                     trigger_button_name: str,
                                     trigger_selector_config: Optional[Dict[str, str]],
                                     username_selector_config: Dict[str, str],
                                     password_selector_config: Dict[str, str],
                                     login_button_selector_config: Dict[str, str],
                                     username: str,
                                     password: str) -> bool:
        """
        Helper function to attempt login after clicking a trigger button.
        """
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Attempting secondary login via '{trigger_button_name}'.")
        if not self._validate_selector_config(trigger_selector_config, trigger_button_name):
            return False

        print(f"Attempting to click {trigger_button_name} with selector: {trigger_selector_config}")
        if not self.browser_wrapper.click_element(
            selector=trigger_selector_config['value'], # type: ignore
            find_by=trigger_selector_config['type'] # type: ignore
        ):
            print(f"Failed to click {trigger_button_name}.")
            return False
        print(f"{trigger_button_name} clicked. Refreshing page data...")
        time.sleep(1) # Wait for potential modal or transition

        current_url_after_trigger, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
        # Use current_url_after_trigger or fallback to self.job_url if it's None (though it shouldn't be usually)
        url_to_load = current_url_after_trigger or self.job_url
        if not url_to_load: # Should ideally not happen if self.job_url is always set before login
             print("Login Error: Cannot determine URL to reload after trigger. Aborting secondary login.")
             return False

        self.page_data_cache = self._load_page_data(url_to_load)
        if not self.page_data_cache:
            print(f"Login Error: Failed to reload page data after clicking {trigger_button_name}.")
            return False
        print("Page data refreshed. Re-attempting login fields.")

        # Re-attempt to fill username
        print(f"Attempting to fill username (after {trigger_button_name}) with selector: {username_selector_config}")
        if not self.browser_wrapper.fill_text_field(
            selector=username_selector_config['value'], text=username, find_by=username_selector_config['type']
        ):
            print(f"Login Error (after {trigger_button_name}): Could not fill username.")
            return False
        print("Filled username field (after trigger).")
        time.sleep(0.2)

        # Re-attempt to fill password
        print(f"Attempting to fill password (after {trigger_button_name}) with selector: {password_selector_config}")
        if not self.browser_wrapper.fill_text_field(
            selector=password_selector_config['value'], text=password, find_by=password_selector_config['type']
        ):
            print(f"Login Error (after {trigger_button_name}): Could not fill password.")
            return False
        print("Filled password field (after trigger).")
        time.sleep(0.2)

        # Re-attempt to click login button
        print(f"Attempting to click login button (after {trigger_button_name}) with selector: {login_button_selector_config}")
        if self.browser_wrapper.click_element(
            selector=login_button_selector_config['value'], find_by=login_button_selector_config['type']
        ):
            print(f"Login button (configured, after {trigger_button_name}) clicked successfully.")
            time.sleep(2)  # Wait for page to potentially reload or redirect
            return True
        else:
            # Configured login button click failed after trigger
            print(f"Login Warning (after {trigger_button_name}): Configured login button (selector: {login_button_selector_config}) not found or failed to click. Attempting dynamic search...")
            if self._find_and_click_login_button_dynamically():
                print(f"Dynamic login button click successful (after {trigger_button_name}).")
                time.sleep(2) # Wait for page to potentially reload or redirect
                return True
            else:
                print(f"Login Error (after {trigger_button_name}): Dynamic login button search also failed. Login button click after trigger failed.")
                return False
    # _attempt_login_after_trigger is being removed.
    # def _attempt_login_after_trigger(...): ... (entire method removed)

    def _is_linkedin_url(self, url: str) -> bool:
        """Checks if 'linkedin.com' is in the URL (case-insensitive)."""
        if not url:
            return False
        return "linkedin.com" in url.lower()

    def _is_indeed_url(self, url: str) -> bool:
        """Checks if 'indeed.com' is in the URL (case-insensitive)."""
        if not url:
            return False
        return "indeed.com" in url.lower()

    def _handle_linkedin_login(self) -> bool:
        """Handles the login process for LinkedIn using selectors from SITE_SELECTORS."""
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Attempting LinkedIn login...")

        linkedin_selectors = SITE_SELECTORS.get("linkedin.com", {})

        initial_trigger_config = linkedin_selectors.get("login_initial_trigger_button")
        username_config = linkedin_selectors.get("login_username")
        password_config = linkedin_selectors.get("login_password")
        final_submit_config = linkedin_selectors.get("login_final_submit_button")

        # Validate crucial selectors
        if not self._validate_selector_config(initial_trigger_config, "login_initial_trigger_button (LinkedIn)"):
            return False
        if not self._validate_selector_config(username_config, "login_username (LinkedIn)"):
            return False
        if not self._validate_selector_config(password_config, "login_password (LinkedIn)"):
            return False
        if not self._validate_selector_config(final_submit_config, "login_final_submit_button (LinkedIn)"):
            return False

        # Type assertions for type checker after validation
        initial_trigger_config_typed = initial_trigger_config
        username_config_typed = username_config
        password_config_typed = password_config
        final_submit_config_typed = final_submit_config

        username = os.environ.get("LINKEDIN_USERNAME")
        password = os.environ.get("LINKEDIN_PASSWORD")

        if not username or not password:
            print("LinkedIn Login: LINKEDIN_USERNAME or LINKEDIN_PASSWORD not found in environment variables.")
            return False

        # Step 1: Click Initial Trigger Button
        print(f"LinkedIn Login: Attempting to click initial trigger button: {initial_trigger_config_typed}")
        if not self.browser_wrapper.click_element(
            selector=initial_trigger_config_typed['value'], find_by=initial_trigger_config_typed['type']
        ):
            print("LinkedIn Login: Failed to click initial trigger button.")
            return False
        print("LinkedIn Login: Successfully clicked initial trigger button.")
        time.sleep(1)  # Allow time for modal or UI changes

        # Step 2: Fill Username
        print(f"LinkedIn Login: Attempting to fill username using selector: {username_config_typed}")
        if not self.browser_wrapper.fill_text_field(
            selector=username_config_typed['value'], text=username, find_by=username_config_typed['type']
        ):
            print("LinkedIn Login: Failed to fill username.")
            return False
        print("LinkedIn Login: Successfully filled username.")
        time.sleep(0.2)

        # Step 3: Fill Password
        print(f"LinkedIn Login: Attempting to fill password using selector: {password_config_typed}")
        if not self.browser_wrapper.fill_text_field(
            selector=password_config_typed['value'], text=password, find_by=password_config_typed['type']
        ):
            print("LinkedIn Login: Failed to fill password.")
            return False
        print("LinkedIn Login: Successfully filled password.")
        time.sleep(0.2)

        # Step 4: Click Final Submit Button
        print(f"LinkedIn Login: Attempting to click final submit button: {final_submit_config_typed}")
        if not self.browser_wrapper.click_element(
            selector=final_submit_config_typed['value'], find_by=final_submit_config_typed['type']
        ):
            print("LinkedIn Login: Failed to click final submit button.")
            return False

        print("LinkedIn Login: Multi-step login process completed successfully.")

        # Attempt to click post-login apply button
        apply_button_config = linkedin_selectors.get("post_login_apply_button")
        apply_click_success = False # Initialize success flag

        if self._validate_selector_config(apply_button_config, "post_login_apply_button (LinkedIn)"):
            apply_button_config_typed = apply_button_config
            print(f"LinkedIn Login: Attempting to click post-login apply button with primary config: {apply_button_config_typed}")
            # Increased sleep and timeout from previous step
            time.sleep(3)
            apply_click_success = self.browser_wrapper.click_element(
                selector=apply_button_config_typed['value'],
                find_by=apply_button_config_typed['type'],
                timeout=20
            )
            if apply_click_success:
                print("LinkedIn Login: Successfully clicked post-login apply button (primary selector).")
            else:
                print("LinkedIn Login: Primary selector failed for post-login apply button. Trying fallbacks...")
        else:
            print("LinkedIn Login: 'post_login_apply_button' selector missing or invalid in site_selectors.json. Proceeding to fallbacks.")

        # Fallback 1: Try finding by text "Easy Apply"
        if not apply_click_success:
            print("LinkedIn Login: Attempting fallback selector for 'Easy Apply' button.")
            easy_apply_xpath = "//button[contains(normalize-space(.), 'Easy Apply') and not(@disabled)]"
            apply_click_success = self.browser_wrapper.click_element(
                selector=easy_apply_xpath,
                find_by='xpath',
                timeout=10 # Shorter timeout for fallbacks
            )
            if apply_click_success:
                print("LinkedIn Login: Successfully clicked post-login apply button (fallback 'Easy Apply').")
            else:
                print("LinkedIn Login: Fallback selector for 'Easy Apply' failed.")

        # Fallback 2: Try finding by text "Apply" (more generic), ensuring it's not an "Easy Apply" already tried
        if not apply_click_success:
            print("LinkedIn Login: Attempting fallback selector for 'Apply' button (excluding 'Easy Apply').")
            # This XPath tries to find "Apply" but not "Easy Apply" to avoid redundancy if "Easy Apply" contains "Apply"
            apply_xpath = "//button[contains(normalize-space(.), 'Apply') and not(contains(normalize-space(.), 'Easy Apply')) and not(@disabled)]"
            apply_click_success = self.browser_wrapper.click_element(
                selector=apply_xpath,
                find_by='xpath',
                timeout=10 # Shorter timeout for fallbacks
            )
            if apply_click_success:
                print("LinkedIn Login: Successfully clicked post-login apply button (fallback 'Apply').")
            else:
                # If the above specific "Apply" (not "Easy Apply") fails, try a broader "Apply" as a last resort for this text
                print("LinkedIn Login: Fallback selector for 'Apply' (excluding 'Easy Apply') failed. Trying broader 'Apply'.")
                broad_apply_xpath = "//button[contains(normalize-space(.), 'Apply') and not(@disabled)]"
                apply_click_success = self.browser_wrapper.click_element(
                    selector=broad_apply_xpath,
                    find_by='xpath',
                    timeout=10 # Shorter timeout for fallbacks
                )
                if apply_click_success:
                    print("LinkedIn Login: Successfully clicked post-login apply button (fallback broad 'Apply').")
                else:
                    print("LinkedIn Login: Fallback selector for broad 'Apply' also failed.")

        if not apply_click_success:
            print("LinkedIn Login: All attempts (primary and fallbacks) to click a post-login apply button failed.")
        # The function will then continue to the `return True` statement at the end of _handle_linkedin_login

        return True # Return True because login was successful, apply button is best-effort

    def _handle_indeed_login(self) -> bool:
        """Handles the login process for Indeed using selectors from SITE_SELECTORS."""
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Attempting Indeed login...")

        indeed_selectors = SITE_SELECTORS.get("indeed.com", {})

        username_config = indeed_selectors.get("login_username")
        # login_password_config = indeed_selectors.get("login_password") # Fetched but not used, as per instruction
        login_button_config = indeed_selectors.get("login_button")

        # Validate crucial selectors
        if not self._validate_selector_config(username_config, "login_username (Indeed)"):
            return False
        if not self._validate_selector_config(login_button_config, "login_button (Indeed)"):
            return False

        # Type assertions for type checker
        username_config_typed = username_config
        login_button_config_typed = login_button_config

        username = os.environ.get("INDEED_USERNAME")
        if not username:
            print("Indeed Login: INDEED_USERNAME not found in environment variables.")
            return False

        # Step 1: Fill Username
        print(f"Indeed Login: Attempting to fill username using selector: {username_config_typed}")
        if not self.browser_wrapper.fill_text_field(
            selector=username_config_typed['value'], text=username, find_by=username_config_typed['type']
        ):
            print("Indeed Login: Failed to fill username.")
            return False
        print("Indeed Login: Successfully filled username.")
        time.sleep(0.2)

        # Step 2: Skip Password (as per explicit instructions)
        print("Indeed Login: Skipping password field as per instructions.")

        # Step 3: Click Login Button
        print(f"Indeed Login: Attempting to click login button using selector: {login_button_config_typed}")
        if not self.browser_wrapper.click_element(
            selector=login_button_config_typed['value'], find_by=login_button_config_typed['type']
        ):
            print("Indeed Login: Failed to click login button.")
            return False

        print("Indeed Login: Process completed successfully.")
        return True

    def _handle_unknown_site_login(self) -> bool:
        """
        Handles the login process for unknown sites by skipping the login attempt.
        This method now simply logs that an unknown site was detected and returns True
        to allow the orchestrator to proceed to the next state (e.g., website analysis).
        """
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Unknown site detected. Skipping login attempt and proceeding to website analysis.")
        return True

    def _handle_login(self) -> bool:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Dispatching login based on URL...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Login Error: Browser wrapper not available.")
            return False

        current_url = self.browser_wrapper.driver.current_url
        if not current_url:
            print("Login Error: Could not retrieve current URL from browser.")
            return False

        print(f"Current URL for login dispatch: {current_url}")

        if self._is_linkedin_url(current_url):
            return self._handle_linkedin_login()
        elif self._is_indeed_url(current_url):
            return self._handle_indeed_login()
        else:
            return self._handle_unknown_site_login()

    # _find_and_click_login_button_dynamically is being removed.
    # Its logic has been integrated into _handle_unknown_site_login.
    # def _find_and_click_login_button_dynamically(self) -> bool: ... (entire method removed)

    def _call_ai_core(self, page_state: Dict[str, Any], user_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing started for {page_state.get('url')}.")
        logging.debug(f"Page state received (screenshot type): { {k: (type(v) if k=='screenshot_bytes' else v) for k,v in page_state.items()} }")

        screenshot_bytes = page_state.get("screenshot_bytes")
        dom_string = page_state.get("dom_string")

        if not screenshot_bytes:
            logging.error("AI Core: Screenshot bytes are missing in page_state. Cannot proceed.")
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing stopped early due to missing screenshot bytes.")
            return None
        if not dom_string:
            logging.warning("AI Core: DOM string is missing in page_state. Grounding quality may be affected.")

        logging.info("AI Core: Fetching all interactable DOM element details from browser...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            logging.error("AI Core: Browser wrapper not available for fetching DOM element details.")
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing stopped early due to unavailable browser wrapper for DOM details.")
            return None
        actual_dom_elements_details = self.browser_wrapper.get_all_interactable_elements_details()
        if not actual_dom_elements_details:
            logging.warning("AI Core: No interactable DOM elements found by browser_wrapper. Grounding will likely fail.")
        logging.info(f"AI Core: Found {len(actual_dom_elements_details)} interactable DOM elements on the page.")
        logging.debug(f"First few DOM elements: {actual_dom_elements_details[:2]}")

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

        # Ensure these are lists of IdentifiedFormField and NavigationElement
        parsed_visual_forms, parsed_visual_navs = parse_llm_output_to_identified_elements(raw_llm_output)
        identified_elements_visual_only: List[IdentifiedFormField] = [
            el if isinstance(el, IdentifiedFormField) else IdentifiedFormField(**el) for el in parsed_visual_forms # type: ignore
        ]
        navigation_elements_visual_only: List[NavigationElement] = [
            el if isinstance(el, NavigationElement) else NavigationElement(**el) for el in parsed_visual_navs # type: ignore
        ]
        logging.info(f"AI Core: Parsed LLM output. Found {len(identified_elements_visual_only)} visual form fields and {len(navigation_elements_visual_only)} visual navigation elements.")

        all_visual_elements_to_ground: List[Any] = [] # Using List[Any] to accommodate mixed types before filtering
        all_visual_elements_to_ground.extend(identified_elements_visual_only)
        all_visual_elements_to_ground.extend(navigation_elements_visual_only)


        if not all_visual_elements_to_ground:
            logging.warning("AI Core: No visual elements identified by LLM to ground.")
            # Return new structure even in this case
            return {
                "form_understanding": {
                    "fields": [],
                    "navigation_elements": []
                },
                "question_answers": [],
                "summary": "No visual elements identified by LLM. Nothing to ground or process further."
            }

        logging.info(f"AI Core: Starting visual grounding for {len(all_visual_elements_to_ground)} elements...")
        # Ensure ground_visual_elements returns lists of actual dataclass instances
        grounded_elements_mixed_raw = ground_visual_elements(all_visual_elements_to_ground, actual_dom_elements_details)

        grounded_form_fields: List[IdentifiedFormField] = []
        grounded_navigation_elements: List[NavigationElement] = []
        for el_data in grounded_elements_mixed_raw:
            if isinstance(el_data, IdentifiedFormField): # Already an instance
                grounded_form_fields.append(el_data)
            elif isinstance(el_data, NavigationElement): # Already an instance
                grounded_navigation_elements.append(el_data)
            # If they are dicts, convert them (assuming constructor can handle dicts)
            # Adding more specific checks for dictionary structure before attempting conversion
            elif isinstance(el_data, dict):
                # Heuristic for IdentifiedFormField dict: check for keys common to this type
                if all(k in el_data for k in ['visual_label_text', 'predicted_label', 'predicted_field_type']):
                    try:
                        grounded_form_fields.append(IdentifiedFormField(**el_data))
                    except TypeError as e:
                        logging.error(f"Failed to convert dict to IdentifiedFormField: {el_data}, error: {e}")
                # Heuristic for NavigationElement dict: check for keys common to this type
                elif all(k in el_data for k in ['visual_label_text', 'action_type_predicted']):
                    try:
                        grounded_navigation_elements.append(NavigationElement(**el_data))
                    except TypeError as e:
                        logging.error(f"Failed to convert dict to NavigationElement: {el_data}, error: {e}")
                else:
                    logging.warning(f"AI Core: Unknown dictionary structure in grounded_elements_mixed: {el_data}")
            else:
                logging.warning(f"AI Core: Unknown element type in grounded_elements_mixed: {type(el_data)}")


        count_successfully_grounded_fields = sum(1 for f in grounded_form_fields if f.dom_path_primary)
        count_successfully_grounded_navs = sum(1 for n in grounded_navigation_elements if n.dom_path_primary)
        logging.info(f"AI Core: Grounding complete. {count_successfully_grounded_fields}/{len(grounded_form_fields)} form fields and "
                     f"{count_successfully_grounded_navs}/{len(grounded_navigation_elements)} navigation elements were grounded.")

        logging.info("AI Core: Performing LIVE semantic matching on grounded fields...")
        # Ensure annotate_fields_with_semantic_meaning returns List[IdentifiedFormField]
        semantically_matched_fields_raw = annotate_fields_with_semantic_meaning(grounded_form_fields, live_llm_call=True)
        semantically_matched_fields: List[IdentifiedFormField] = [
            f if isinstance(f, IdentifiedFormField) else IdentifiedFormField(**f) for f in semantically_matched_fields_raw # type: ignore
        ]
        count_successfully_semantic_matched = sum(1 for f in semantically_matched_fields if f.semantic_meaning_predicted and f.semantic_meaning_predicted != "system_internal.other_unspecified_field")
        logging.info(f"AI Core: Live semantic matching complete. {count_successfully_semantic_matched}/{len(semantically_matched_fields)} fields have a specific semantic meaning assigned.")

        question_answers_generated: List[QuestionAnsweringResult] = []
        user_profile_for_qa = _load_user_profile()
        job_description_text_for_qa = _load_job_description()

        job_title_context = self.user_profile.get("application.job_details.job_title",
                                                  user_profile.get("application.job_details.job_title", "the current role"))
        company_name_context = self.user_profile.get("application.job_details.company_name",
                                                     user_profile.get("application.job_details.company_name", "the company"))

        job_context_for_qa = {
            "job_title": job_title_context,
            "company_name": company_name_context,
            "job_description_summary": job_description_text_for_qa if job_description_text_for_qa else ""
        }
        temp_user_profile_for_action_gen = user_profile.copy()

        for field in semantically_matched_fields:
            if field.semantic_meaning_predicted and \
               (field.semantic_meaning_predicted.startswith("application.custom_question") or \
                field.semantic_meaning_predicted == "application.cover_letter_text_final"):
                logging.info(f"AI Core: Identified question field: '{field.visual_label_text}' ({field.semantic_meaning_predicted})")
                question_text = field.visual_label_text if field.visual_label_text else f"Response for {field.semantic_meaning_predicted}"
                qa_result = generate_answer_for_question(
                    question_text=question_text,
                    dom_path_question=field.dom_path_primary,
                    semantic_key_of_question=field.semantic_meaning_predicted,
                    user_profile_data=user_profile_for_qa,
                    job_context_data=job_context_for_qa,
                    live_llm_call=True
                )
            # Ensure qa_result is a QuestionAnsweringResult instance
            if isinstance(qa_result, dict):
                try:
                    # Attempt to create QuestionAnsweringResult, ensure all required fields are present or provide defaults
                    qa_result_data = {
                        'question_text_identified': qa_result.get('question_text_identified', question_text),
                        'dom_path_question': qa_result.get('dom_path_question', field.dom_path_primary),
                        'semantic_key_of_question': qa_result.get('semantic_key_of_question', field.semantic_meaning_predicted),
                        'suggested_answer_draft': qa_result.get('suggested_answer_draft'),
                        'confidence_score_answer': qa_result.get('confidence_score_answer', 0.0),
                        'raw_llm_response_answer_generation': qa_result.get('raw_llm_response_answer_generation'),
                        'error_message': qa_result.get('error_message')
                    }
                    qa_result_obj = QuestionAnsweringResult(**qa_result_data)
                except TypeError as e:
                    logging.error(f"Failed to convert dict to QuestionAnsweringResult: {qa_result}, error: {e}")
                    qa_result_obj = QuestionAnsweringResult(
                        question_text_identified=question_text,
                        dom_path_question=field.dom_path_primary,
                        semantic_key_of_question=field.semantic_meaning_predicted,
                        suggested_answer_draft=f"Error: Could not parse QA result - {e}",
                        confidence_score_answer=0.0,
                        raw_llm_response_answer_generation=str(qa_result),
                        error_message=f"Conversion error: {e}"
                    )
            elif isinstance(qa_result, QuestionAnsweringResult): # Already a QuestionAnsweringResult object
                qa_result_obj = qa_result
            else: # Handle unexpected type for qa_result
                logging.error(f"Unexpected type for qa_result: {type(qa_result)}. Expected dict or QuestionAnsweringResult.")
                qa_result_obj = QuestionAnsweringResult(
                    question_text_identified=question_text,
                    dom_path_question=field.dom_path_primary,
                    semantic_key_of_question=field.semantic_meaning_predicted,
                    suggested_answer_draft="Error: Unexpected QA result type",
                    confidence_score_answer=0.0,
                    raw_llm_response_answer_generation=str(qa_result),
                    error_message="Unexpected QA result type"
                )

            question_answers_generated.append(qa_result_obj)
            # Note: The logic that used temp_user_profile_for_action_gen is removed as action generation is deferred.
            # We still log if an answer was usable or not.
            if qa_result_obj.suggested_answer_draft and not qa_result_obj.suggested_answer_draft.startswith("Error:") and not "blocked" in qa_result_obj.suggested_answer_draft:
                logging.info(f"AI Core: QA answer generated for '{field.semantic_meaning_predicted}'.")
                else:
                logging.warning(f"AI Core: QA for '{field.semantic_meaning_predicted}' did not produce a usable answer. Answer: '{qa_result_obj.suggested_answer_draft}', Error: '{qa_result_obj.error_message}'")

        # Action generation (mvp_generate_text_fill_actions) is REMOVED from this function.
        # Navigation action selection logic is REMOVED from this function.

        summary_message = (
            f"Visual Perception: {len(identified_elements_visual_only)} form fields, {len(navigation_elements_visual_only)} navigation elements. "
            f"Grounding: {count_successfully_grounded_fields}/{len(grounded_form_fields)} form fields, {count_successfully_grounded_navs}/{len(grounded_navigation_elements)} navigation elements. "
            f"Semantic Matching: {count_successfully_semantic_matched}/{len(semantically_matched_fields)} fields matched. "
            f"Question Answering: {len(question_answers_generated)} answers generated."
        )
        logging.info(f"AI Core Summary: {summary_message}")

        ai_recommendations_cache = {
            "form_understanding": {
                "fields": semantically_matched_fields,  # List[IdentifiedFormField]
                "navigation_elements": grounded_navigation_elements  # List[NavigationElement]
            },
            "question_answers": question_answers_generated,  # List[QuestionAnsweringResult]
            "summary": summary_message
        }
        # Old keys like "fields_to_fill", "actions", "navigation_element_text", "question_answers_to_review" are removed.

        logging.debug(f"New AI recommendations cache structure: {{'form_understanding': {{'fields': List[IdentifiedFormField], 'navigation_elements': List[NavigationElement]}}, 'question_answers': List[QuestionAnsweringResult], 'summary': str}}")
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing finished, returning new structured recommendations.")
        return ai_recommendations_cache

    def _execute_browser_automation(self, actions: List[ActionDetail]) -> bool:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Executing browser automation actions...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for executing actions.")
            return False

        for i, action in enumerate(actions):
            action_type = action.action_type
            dom_path = action.dom_path_target
            value_to_fill = action.value_to_fill
            option_to_select = action.option_to_select # For dropdowns
            file_path_to_upload = action.file_path_to_upload # For file uploads

            print(f"  Action {i+1}/{len(actions)}: Type: {action_type.name}, Path: {dom_path}" +
                  (f", Value: '{str(value_to_fill)[:30]}...'" if value_to_fill else "") +
                  (f", Option: '{option_to_select}'" if option_to_select else "") +
                  (f", File: '{file_path_to_upload}'" if file_path_to_upload else "")
            )

            success = False
            find_by_method = "xpath" # Assuming dom_path_target is usually XPath

            if action_type == ActionSequenceActionType.FILL_TEXT:
                if dom_path and value_to_fill is not None and "NOT_GROUNDED" not in dom_path and "MISSING" not in dom_path :
                    success = self.browser_wrapper.fill_text_field(selector=dom_path, text=str(value_to_fill), find_by=find_by_method)
                else:
                    print(f"    Skipping FILL_TEXT due to missing path ('{dom_path}') or value.")

            elif action_type == ActionSequenceActionType.CLICK_ELEMENT:
                if dom_path and "NOT_GROUNDED" not in dom_path and "MISSING" not in dom_path:
                    success = self.browser_wrapper.click_element(selector=dom_path, find_by=find_by_method)
                else:
                    print(f"    Skipping CLICK_ELEMENT due to missing path ('{dom_path}').")

            elif action_type == ActionSequenceActionType.SELECT_DROPDOWN_OPTION:
                if dom_path and option_to_select is not None and "NOT_GROUNDED" not in dom_path and "MISSING" not in dom_path :
                    if hasattr(self.browser_wrapper, 'select_dropdown_option_by_visible_text'):
                        success = self.browser_wrapper.select_dropdown_option_by_visible_text(selector=dom_path, text=option_to_select, find_by=find_by_method)
                    elif hasattr(self.browser_wrapper, 'select_dropdown_option'): # Generic fallback
                         success = self.browser_wrapper.select_dropdown_option(selector=dom_path, option=option_to_select, find_by=find_by_method) # type: ignore
                    else:
                        print(f"    SKIPPING SELECT_DROPDOWN_OPTION: MVPSeleniumWrapper does not have 'select_dropdown_option_by_visible_text' or 'select_dropdown_option' method.")
                else:
                    print(f"    Skipping SELECT_DROPDOWN_OPTION due to missing path ('{dom_path}') or option.")

            elif action_type == ActionSequenceActionType.UPLOAD_FILE:
                if dom_path and file_path_to_upload is not None and "NOT_GROUNDED" not in dom_path and "MISSING" not in dom_path :
                    if hasattr(self.browser_wrapper, 'upload_file_to_element'):
                        success = self.browser_wrapper.upload_file_to_element(selector=dom_path, file_path=file_path_to_upload, find_by=find_by_method)
                    else:
                        print(f"    SKIPPING UPLOAD_FILE: MVPSeleniumWrapper does not have 'upload_file_to_element' method.")
                else:
                    print(f"    Skipping UPLOAD_FILE due to missing path ('{dom_path}') or file path.")

            else:
                print(f"    Warning: Unknown or unhandled action type '{action_type.name}' in action sequence.")
                continue

            if not success:
                print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Browser automation action failed: {action_type.name} on {dom_path}.")
                return False # Stop on first failure
            time.sleep(0.5)

        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): All browser automation actions completed successfully.")
        return True

    def run(self):
        if self.current_state == OrchestratorState.FAILED_ERROR and not self.browser_wrapper.driver:
            print("Orchestrator cannot start due to browser initialization failure.")
            self.current_state = OrchestratorState.IDLE

        if self.current_state == OrchestratorState.IDLE and self.browser_wrapper.driver:
             self.current_state = OrchestratorState.AWAITING_JOB_URL

        print(f"State: {self.current_state}")
        if self.job_url :
             print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Starting run. Current state: {self.current_state}, Job URL: {self.job_url}")

        try:
            while True:
                if self.job_url and self.current_state != OrchestratorState.AWAITING_JOB_URL :
                    print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Processing. Current state: {self.current_state}, Job URL: {self.job_url}")

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
                        self.current_target_url = None
                    else:
                        self.current_target_url = self.job_url # Initialize current_target_url
                        self.current_state = OrchestratorState.LOADING_PAGE_DATA
                        print(f"State: {self.current_state} - URL: {self.current_target_url}")

                elif self.current_state == OrchestratorState.LOADING_PAGE_DATA:
                    if not self.current_target_url: # Changed from self.job_url
                        print("Error: No current target URL to load. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    # Determine URL for _load_page_data:
                    # If current_target_url is the same as browser's current url, it means we are continuing a flow.
                    # Otherwise, it's an initial load or a redirect we need to enforce.
                    # MVPSeleniumWrapper.navigate_to_url handles not re-navigating if already on the URL.
                    url_to_load = self.current_target_url

                    self.page_data_cache = self._load_page_data(url_to_load)
                    if self.page_data_cache:
                        self.current_state = OrchestratorState.AWAITING_LOGIN_APPROVAL
                    else:
                        print("Error: Failed to load page data.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_LOGIN_APPROVAL:
                    if self.auto_apply_mode:
                        print("AutoApply Mode: Attempting auto-login...")
                        self.current_state = OrchestratorState.EXECUTING_LOGIN
                    else:
                        login_choice = input("Attempt auto-login? (y/n/quit): ").lower()
                        if login_choice == 'y':
                            self.current_state = OrchestratorState.EXECUTING_LOGIN
                        elif login_choice == 'n':
                            print("Skipping auto-login. Proceeding to AI Core analysis.")
                            self.current_state = OrchestratorState.CALLING_AI_CORE
                        elif login_choice == 'quit':
                            self.current_state = OrchestratorState.IDLE
                        else:
                            print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.EXECUTING_LOGIN:
                    print("Executing auto-login...")
                    login_success = self._handle_login() # This now calls the new complex logic
                    if login_success:
                        print("Auto-login successful. Proceeding to next step.")
                        try:
                            # Refresh page data as login might have changed the page
                            print("Refreshing page data after login...")
                            current_url_after_login, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
                            url_to_load_after_login = current_url_after_login or self.job_url # Fallback
                            print(f"Orchestrator: Preparing to refresh page. current_url_after_login='{current_url_after_login}', self.job_url='{self.job_url}', effective url_to_load_after_login='{url_to_load_after_login}'")
                            if not url_to_load_after_login:
                                print("Error: Could not determine URL after login. Critical state.")
                                self.current_state = OrchestratorState.FAILED_ERROR
                            else:
                                self.page_data_cache = self._load_page_data(url_to_load_after_login)
                                if self.page_data_cache:
                                    print("Page data refreshed. Proceeding to AI Core analysis.")
                                    self.current_state = OrchestratorState.CALLING_AI_CORE
                                else:
                                    print("Error: Failed to reload page data after login.")
                                    self.current_state = OrchestratorState.FAILED_ERROR
                        except Exception as e:
                            print(f"CRITICAL ERROR during page refresh after login: {e}")
                            self.current_state = OrchestratorState.FAILED_ERROR
                            print(f"State set to FAILED_ERROR due to critical refresh error.")
                    else:
                        # _handle_login now prints its own failure reasons.
                        # print("Auto-login failed. Check selectors or page structure.") # Redundant
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.CALLING_AI_CORE:
                    if not self.page_data_cache:
                        print("Error: No page data to process. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue

                    ai_core_output = self._call_ai_core(self.page_data_cache, self.user_profile)

                    if not ai_core_output:
                        print("Error: AI Core processing failed to return any recommendations (_call_ai_core returned None).")
                        self.current_state = OrchestratorState.FAILED_ERROR
                        print(f"State: {self.current_state}")
                        continue

                    form_understanding = ai_core_output.get("form_understanding", {})
                    question_answers_generated = ai_core_output.get("question_answers", [])
                    ai_summary = ai_core_output.get("summary", "Summary not available.")

                    semantically_matched_fields = form_understanding.get("fields", [])
                    grounded_navigation_elements = form_understanding.get("navigation_elements", [])

                    print("Orchestrator: Calling orchestrate_action_sequence...")
                    action_sequence_recommendation = orchestrate_action_sequence(
                        processed_fields=semantically_matched_fields,
                        navigation_elements=grounded_navigation_elements,
                        user_profile_data=self.user_profile,
                        approved_qa_results=question_answers_generated,
                        # page_context={} # Omitting for now, or using default
                    )
                    # TODO: Add logic to handle ClarificationRequest if returned by AI Core.

                    if not action_sequence_recommendation:
                        print("Error: Action sequence generation failed (orchestrate_action_sequence returned None).")
                        self.current_state = OrchestratorState.FAILED_ERROR
                        self.ai_recommendations_cache = { # Store partial data for debugging
                            "action_sequence_recommendation": None,
                            "form_understanding": form_understanding,
                            "question_answers": question_answers_generated,
                            "summary": ai_summary + " | Action generation failed."
                        }
                        print(f"State: {self.current_state}")
                        continue

                    self.ai_recommendations_cache = {
                        "action_sequence_recommendation": action_sequence_recommendation,
                        "form_understanding": form_understanding,
                        "question_answers": question_answers_generated,
                        "summary": ai_summary # This summary is from _call_ai_core
                    }
                    logging.info(f"Orchestrator: New ai_recommendations_cache populated with action_sequence.")
                    logging.debug(f"Cache content: {self.ai_recommendations_cache}")


                    # Conditional Transition to AWAITING_USER_APPROVAL
                    has_actions = action_sequence_recommendation and action_sequence_recommendation.actions
                    has_qa_to_review = bool(question_answers_generated)
                    # Also consider if the initial _call_ai_core summary indicated "Nothing to ground"
                    nothing_to_ground = "Nothing to ground" in ai_summary

                    if has_actions or has_qa_to_review or nothing_to_ground:
                        print("AI Core and Action Generation processing complete. Proceeding to user approval.")
                        self.current_state = OrchestratorState.AWAITING_USER_APPROVAL
                    else:
                        print("Error: No actionable items (no actions, no QA) proposed by AI pipeline.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_USER_APPROVAL:
                    if not self.ai_recommendations_cache:
                        print("Error: No AI recommendations to approve. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue

                    print("\n--- AI Recommendations ---")
                    print(f"Summary: {self.ai_recommendations_cache.get('summary', 'N/A')}")

                    # Display Identified Form Fields & Data
                    form_understanding = self.ai_recommendations_cache.get("form_understanding", {})
                    identified_fields: List[IdentifiedFormField] = form_understanding.get("fields", [])
                    all_qa_results: List[QuestionAnsweringResult] = self.ai_recommendations_cache.get("question_answers", [])

                    print("\n--- Identified Form Fields & Data ---")
                    if identified_fields:
                        for field in identified_fields:
                            value_to_fill_display = "N/A_IN_PROFILE"
                            if field.semantic_meaning_predicted:
                                # Check if it's a QA field and if an answer exists
                                is_qa_field = field.semantic_meaning_predicted.startswith("application.custom_question") or \
                                              field.semantic_meaning_predicted == "application.cover_letter_text_final"
                                corresponding_qa = next(
                                    (qa for qa in all_qa_results if qa.semantic_key_of_question == field.semantic_meaning_predicted and qa.suggested_answer_draft), None
                                )
                                if is_qa_field and corresponding_qa:
                                    value_to_fill_display = f"[QA Draft]: {corresponding_qa.suggested_answer_draft[:100]}"
                                    if len(corresponding_qa.suggested_answer_draft) > 100:  value_to_fill_display += "..."
                                elif field.semantic_meaning_predicted in self.user_profile:
                                    value_to_fill_display = self.user_profile[field.semantic_meaning_predicted]

                            print(f"  - Label: {field.visual_label_text or 'Unknown Label'}")
                            print(f"    Value: '{value_to_fill_display}'")
                            print(f"    XPath: {field.dom_path_primary or 'NOT_GROUNDED'}")
                            print(f"    Semantic Key: {field.semantic_meaning_predicted or 'NONE'}")
                            print(f"    Confidence: {field.confidence_score:.2f}")
                    else:
                        print("  No form fields identified.")

                    # Display Proposed Actions
                    action_sequence_rec = self.ai_recommendations_cache.get("action_sequence_recommendation")
                    proposed_actions: List[ActionDetail] = action_sequence_rec.actions if action_sequence_rec else []

                    print("\n--- Proposed Actions ---")
                    if proposed_actions:
                        for i, action in enumerate(proposed_actions):
                            action_details = f"  Action {i+1}: {action.action_type.name}"
                            if action.dom_path_target: action_details += f", Target: {action.dom_path_target}"
                            if action.value_to_fill: action_details += f", Value: '{str(action.value_to_fill)[:30]}...'"
                            if action.option_to_select: action_details += f", Option: '{action.option_to_select}'"
                            if action.file_path_to_upload: action_details += f", File: '{action.file_path_to_upload}'"
                            print(action_details)
                    else:
                        print("  No actions proposed.")

                    # Display Suggested Answers (QA)
                    # qa_answers_review = self.ai_recommendations_cache.get('question_answers', []) # Already got this as all_qa_results
                    print("\n--- Suggested Answers to Application Questions (Review) ---")
                    if all_qa_results:
                        for i, qa_info in enumerate(all_qa_results):
                            print(f"  Question {i+1} for Field with DOM Path '{qa_info.dom_path_question}':")
                            print(f"    Identified Question Text: {qa_info.question_text_identified}")
                            print(f"    Suggested Answer: {qa_info.suggested_answer_draft}")
                            print(f"    Semantic Key: {qa_info.semantic_key_of_question}")
                        print("--- End of Suggested Answers (Review) ---")
                    else:
                        print("  No QA answers to review.")

                    # Approval Logic
                    has_actions = bool(proposed_actions)
                    has_qa = bool(all_qa_results)

                    if not has_actions and not has_qa:
                        print("No actions proposed by AI and no QA answers to review. Resetting for new URL.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        time.sleep(1)
                        continue
                    elif not has_actions and has_qa:
                        print("Only QA answers to review. No direct browser actions proposed. Please review the QA answers.")

                    if self.auto_apply_mode:
                        print("AutoApply Mode: Auto-approving AI recommendations.")
                        if has_actions:
                            self.current_state = OrchestratorState.EXECUTING_AUTOMATION
                        elif has_qa: # QA-only case
                            print("AutoApply Mode: Only QA answers to review. Logging them and completing this cycle.")
                            self._log_user_approval_of_qa_only()
                            self.current_state = OrchestratorState.COMPLETED_SUCCESS # Or AWAITING_JOB_URL if preferred for QA-only
                        else: # Should not be reached due to the check above
                            print("AutoApply Mode: No actions and no QA to approve. Setting to FAILED_ERROR.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                    else: # Manual approval mode
                        approval = input("Approve and apply (this includes all fields and QA answers)? (y/n/quit): ").lower()
                        if approval == 'y':
                            if has_actions:
                                self.current_state = OrchestratorState.EXECUTING_AUTOMATION
                            elif has_qa: # QA-only case, user approved
                                print("Approved QA answers. No direct browser actions to execute. Resetting for next URL.")
                                self._log_user_approval_of_qa_only()
                                self.current_state = OrchestratorState.AWAITING_JOB_URL # Consistent with previous logic for QA-only approval
                                # continue # This might be needed if AWAITING_JOB_URL doesn't immediately loop
                            else: # No actions, no QA, but user said 'y'. Should be caught by earlier check.
                                print("No actions or QA to apply. Resetting.")
                                self.current_state = OrchestratorState.AWAITING_JOB_URL
                        elif approval == 'n':
                            print("Application not approved by user. Logging feedback and resetting.")
                            self._log_user_disapproval()
                            self.current_state = OrchestratorState.AWAITING_JOB_URL
                        elif approval == 'quit':
                            self.current_state = OrchestratorState.IDLE
                        else:
                            print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.EXECUTING_AUTOMATION:
                    if not self.ai_recommendations_cache or \
                       not self.ai_recommendations_cache.get("action_sequence_recommendation") or \
                       not self.ai_recommendations_cache["action_sequence_recommendation"].actions:

                        # Check if there are QA answers, if so, this might be a valid state if user approved only QA
                        if self.ai_recommendations_cache and self.ai_recommendations_cache.get("question_answers"):
                             print("No browser actions to execute, but QA answers were present and potentially approved. Completing cycle.")
                             self.current_state = OrchestratorState.COMPLETED_SUCCESS
                        else:
                            print("Error: No browser actions to execute. Resetting.")
                            self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue

                    actions_to_execute = self.ai_recommendations_cache["action_sequence_recommendation"].actions
                    if not actions_to_execute: # Should be caught by the above, but as a safeguard
                        print("No actions to execute. Completing cycle as success.")
                        self.current_state = OrchestratorState.COMPLETED_SUCCESS
                        continue

                    success = self._execute_browser_automation(actions_to_execute)
                    if success:
                        # Check for multi-step navigation
                        action_seq_rec = self.ai_recommendations_cache.get("action_sequence_recommendation")
                        if action_seq_rec and action_seq_rec.expected_next_page_type:
                            next_page_type = action_seq_rec.expected_next_page_type.lower()
                            # Define completion types more explicitly
                            completion_types = ["confirmation_page", "application_submitted", "stay_on_page_completed"]

                            if any(comp_type in next_page_type for comp_type in completion_types) or \
                               next_page_type in ["stay_on_page_or_no_clear_nav", ""]: # Empty or None also means complete
                                print(f"Orchestrator: Application step/final submission likely complete. Expected next page: {next_page_type}")
                                self.current_state = OrchestratorState.COMPLETED_SUCCESS
                            else: # Indicates continuation
                                print(f"Orchestrator: Multi-step form detected. Expected next page type: {next_page_type}. Proceeding to load next page data.")
                                if self.browser_wrapper and self.browser_wrapper.driver:
                                    self.current_target_url = self.browser_wrapper.driver.current_url
                                    print(f"Orchestrator: Next target URL set to current browser URL: {self.current_target_url}")
                                else: # Should not happen if browser is active
                                    print("Orchestrator ERROR: Browser not available to get current URL for multi-step. Failing.")
                                    self.current_state = OrchestratorState.FAILED_ERROR
                                    self.current_target_url = None # Reset
                                    self.job_url = None # Reset
                                if self.current_state != OrchestratorState.FAILED_ERROR: # Only transition if not already failed
                                   self.current_state = OrchestratorState.LOADING_PAGE_DATA
                                # self.job_url is NOT reset here, as it's the overall application URL.
                        else:
                            # Default to COMPLETED_SUCCESS if expected_next_page_type is missing
                            print("Orchestrator: No explicit next page type. Assuming completion.")
                            self.current_state = OrchestratorState.COMPLETED_SUCCESS
                    else:
                        print("Orchestrator: Execution of browser automation failed.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.COMPLETED_SUCCESS:
                    print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Entering COMPLETED_SUCCESS state for job URL: {self.job_url}.")
                    print(f"\nApplication process for {self.job_url} completed successfully!")
                    self.job_url = None
                    self.current_target_url = None # Reset current_target_url
                    self.current_state = OrchestratorState.AWAITING_JOB_URL
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.FAILED_ERROR:
                    print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Entering FAILED_ERROR state for job URL: {self.job_url}.")
                    print(f"\nApplication process for {self.job_url} failed or encountered an error.")
                    self.job_url = None
                    self.current_target_url = None # Reset current_target_url
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
        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_url": self.job_url,
            "reason": "User approved QA-only recommendations.",
            "ai_recommendations": self.ai_recommendations_cache
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
