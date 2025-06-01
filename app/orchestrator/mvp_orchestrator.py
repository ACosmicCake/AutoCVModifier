# app/orchestrator/mvp_orchestrator.py
import time
import json
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
        self.auto_apply_mode = False # Add this line

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
        if not self.browser_wrapper.click_element(
            selector=login_button_selector_config['value'], find_by=login_button_selector_config['type']
        ):
            print(f"Login Error (after {trigger_button_name}): Could not click login button.")
            return False
        print(f"Login successful after clicking {trigger_button_name}.")
        time.sleep(2)  # Wait for page to potentially reload or redirect
        return True

    def _handle_login(self) -> bool:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Attempting auto-login...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Login Error: Browser wrapper not available.")
            return False

        default_site_selectors = SITE_SELECTORS.get("default")
        if not default_site_selectors:
            print("Login Error: 'default' site selectors not found in SITE_SELECTORS.")
            return False

        username = "testuser"
        password = "testpassword"

        username_selector_config = default_site_selectors.get("login_username")
        password_selector_config = default_site_selectors.get("login_password")
        login_button_selector_config = default_site_selectors.get("login_button")

        # Validate primary login selectors
        if not self._validate_selector_config(username_selector_config, "login_username"): return False
        if not self._validate_selector_config(password_selector_config, "login_password"): return False
        if not self._validate_selector_config(login_button_selector_config, "login_button"): return False

        # Type assertion for linters after validation
        username_sel_conf_typed = username_selector_config
        password_sel_conf_typed = password_selector_config
        login_btn_sel_conf_typed = login_button_selector_config


        # Attempt Primary Login
        print("Attempting Primary Login...")
        print(f"Attempting to fill username with selector: {username_sel_conf_typed}")
        if self.browser_wrapper.fill_text_field(
            selector=username_sel_conf_typed['value'], # type: ignore
            text=username,
            find_by=username_sel_conf_typed['type'] # type: ignore
        ):
            print("Filled username field.")
            time.sleep(0.2)

            print(f"Attempting to fill password with selector: {password_sel_conf_typed}")
            if not self.browser_wrapper.fill_text_field(
                selector=password_sel_conf_typed['value'], # type: ignore
                text=password,
                find_by=password_sel_conf_typed['type'] # type: ignore
            ):
                print("Login Error: Could not find or fill password field (username was filled).")
                return False
            print("Filled password field.")
            time.sleep(0.2)

            print(f"Attempting to click login button with selector: {login_btn_sel_conf_typed}")
            if not self.browser_wrapper.click_element(
                selector=login_btn_sel_conf_typed['value'], # type: ignore
                find_by=login_btn_sel_conf_typed['type'] # type: ignore
            ):
                print("Login Error: Could not find or click login button.")
                return False
            print("Primary login successful.")
            time.sleep(2)  # Wait for page to potentially reload or redirect
            return True
        else:
            # Username fill failed, proceed to secondary login triggers
            print("Primary login: Username field not found or could not be filled. Proceeding to Secondary Login Triggers.")

            # Attempt Secondary Login Triggers
            # 1. Login with Email button
            login_email_button_config = default_site_selectors.get("login_email_button")
            if self._attempt_login_after_trigger(
                "Login with Email button",
                login_email_button_config, # type: ignore
                username_sel_conf_typed, # type: ignore
                password_sel_conf_typed, # type: ignore
                login_btn_sel_conf_typed, # type: ignore
                username,
                password
            ):
                return True # Login successful via email button trigger

            # 2. Secondary Login Trigger button
            secondary_login_trigger_config = default_site_selectors.get("secondary_login_trigger_button")
            if self._attempt_login_after_trigger(
                "Secondary Login Trigger button",
                secondary_login_trigger_config, # type: ignore
                username_sel_conf_typed, # type: ignore
                password_sel_conf_typed, # type: ignore
                login_btn_sel_conf_typed, # type: ignore
                username,
                password
            ):
                return True # Login successful via secondary trigger

            print("Auto-login failed. All primary and secondary attempts exhausted. Check selectors or page structure.")
            return False


    def _handle_auto_click_apply(self) -> bool:
        """
        Attempts to find and click an "apply" button using a specific CSS selector.
        Returns True if the button is found and clicked successfully, False otherwise.
        """
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Attempting to auto-click 'apply' button...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for auto-click apply.")
            return False

        apply_button_selector = 'button[aria-label*="Apply"]'

        # Assuming click_element uses 'css_selector' by default if find_by is not specified,
        # or that it correctly interprets the selector.
        # For clarity, it's better to be explicit if the wrapper supports it.
        # Let's assume it needs explicit find_by for CSS selectors if not xpath.
        # The original code had `find_by="css_selector"` but the method signature expects `xpath` and then `find_by`.
        # This seems like a bug in the original `_handle_auto_click_apply`.
        # Correcting it to pass selector as the first argument, then find_by.
        if self.browser_wrapper.click_element(selector=apply_button_selector, find_by="css_selector"):
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Successfully clicked 'apply' button (selector: {apply_button_selector}).")
            time.sleep(2)
            return True
        else:
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Could not find or click 'apply' button (selector: {apply_button_selector}).")
            return False

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

        identified_elements_visual_only, navigation_elements_visual_only = parse_llm_output_to_identified_elements(raw_llm_output)
        logging.info(f"AI Core: Parsed LLM output. Found {len(identified_elements_visual_only)} visual form fields and {len(navigation_elements_visual_only)} visual navigation elements.")

        all_visual_elements_to_ground = identified_elements_visual_only + navigation_elements_visual_only
        if not all_visual_elements_to_ground:
            logging.warning("AI Core: No visual elements identified by LLM to ground.")
            print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing stopped early due to no visual elements identified by LLM to ground.")
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

        logging.info("AI Core: Performing LIVE semantic matching on grounded fields...")
        semantically_matched_fields = annotate_fields_with_semantic_meaning(grounded_form_fields, live_llm_call=True)
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
                question_answers_generated.append(qa_result)
                if qa_result.suggested_answer_draft and not qa_result.suggested_answer_draft.startswith("Error:") and not "blocked" in qa_result.suggested_answer_draft:
                    temp_user_profile_for_action_gen[field.semantic_meaning_predicted] = qa_result.suggested_answer_draft
                    logging.info(f"AI Core: QA answer for '{field.semantic_meaning_predicted}' will be used for action generation.")
                else:
                    logging.warning(f"AI Core: QA for '{field.semantic_meaning_predicted}' did not produce a usable answer. Original profile value (if any) will be used for this field's action.")

        logging.info("AI Core: Generating MVP text fill actions (potentially with QA answers in profile)...")
        fill_actions_details_obj_list = mvp_generate_text_fill_actions(
            semantically_matched_fields,
            temp_user_profile_for_action_gen
        )
        logging.info(f"AI Core: MVP text fill action generation complete. {len(fill_actions_details_obj_list)} fill actions proposed.")
        if not fill_actions_details_obj_list and count_successfully_grounded_fields > 0 and not any(qa.suggested_answer_draft for qa in question_answers_generated) :
             logging.warning("AI Core: No fill actions generated by MVP action generator (and no QA answers were generated/used). This might be due to semantic keys not matching user profile, no grounded paths, or no fillable types found.")

        fields_to_display = []
        for field in semantically_matched_fields:
            value_to_fill_display = temp_user_profile_for_action_gen.get(field.semantic_meaning_predicted, "N/A_IN_PROFILE") \
                                    if field.semantic_meaning_predicted else "N/A_SEMANTIC_MATCH"
            corresponding_qa: Optional[QuestionAnsweringResult] = next(
                (qa for qa in question_answers_generated if qa.dom_path_question == field.dom_path_primary and qa.suggested_answer_draft and not qa.suggested_answer_draft.startswith("Error:")), None
            )
            display_semantic_key = field.semantic_meaning_predicted if field.semantic_meaning_predicted else "NONE"
            if corresponding_qa:
                value_to_fill_display = f"[QA Draft]: {corresponding_qa.suggested_answer_draft[:100]}"
                if len(corresponding_qa.suggested_answer_draft) > 100:
                    value_to_fill_display += "..."
            elif field.semantic_meaning_predicted and field.semantic_meaning_predicted in temp_user_profile_for_action_gen and \
                 field.semantic_meaning_predicted not in [qa.semantic_key_of_question for qa in question_answers_generated if qa.suggested_answer_draft]:
                value_to_fill_display = temp_user_profile_for_action_gen[field.semantic_meaning_predicted]
            fields_to_display.append({
                "label": field.visual_label_text or "Unknown Label",
                "value": value_to_fill_display,
                "xpath": field.dom_path_primary if field.dom_path_primary else "NOT_GROUNDED",
                "semantic_key_assigned": display_semantic_key,
                "overall_confidence": field.confidence_score
            })

        final_actions_list = [action.to_dict() for action in fill_actions_details_obj_list]
        chosen_navigation_text = "No usable navigation found."
        nav_target: Optional[NavigationElement] = None

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
            "navigation_element_text": chosen_navigation_text,
            "question_answers_to_review": [qa.to_dict() for qa in question_answers_generated]
        }
        logging.debug(f"Final AI recommendations (with QA): {final_recommendations}")
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): AI Core processing finished, returning recommendations.")
        return final_recommendations

    def _execute_browser_automation(self, actions: List[Dict[str, Any]]) -> bool:
        print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Executing browser automation actions...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for executing actions.")
            return False

        for i, action_dict in enumerate(actions):
            action_type = action_dict.get('action_type')
            dom_path = action_dict.get('dom_path_target') # This is typically XPath
            value = action_dict.get('value_to_fill')
            # The find_by logic needs to be robust if dom_path_target is not always XPath
            # For now, assume it's XPath as per current fill_text_field/click_element calls.
            find_by_method = "xpath" # Default, assuming dom_path_target is XPath

            print(f"  Action {i+1}/{len(actions)}: Type: {action_type}, Path: {dom_path}" + (f", Value: '{str(value)[:30]}...'" if value else ""))

            success = False
            if action_type == "FILL_TEXT":
                if dom_path and value is not None and dom_path != "NOT_GROUNDED" and "MISSING" not in dom_path:
                    success = self.browser_wrapper.fill_text_field(selector=dom_path, text=str(value), find_by=find_by_method)
                else:
                    print(f"    Skipping FILL_TEXT due to missing path ('{dom_path}') or value.")
            elif action_type == "CLICK_ELEMENT":
                if dom_path and dom_path != "NOT_GROUNDED" and "MISSING" not in dom_path:
                    success = self.browser_wrapper.click_element(selector=dom_path, find_by=find_by_method)
                else:
                    print(f"    Skipping CLICK_ELEMENT due to missing path ('{dom_path}').")
            else:
                print(f"    Warning: Unknown action type '{action_type}' in action sequence.")
                continue

            if not success:
                print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Browser automation action failed: {action_type} on {dom_path}.")
                return False
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
                            print("Skipping auto-login. Proceeding to apply button check.")
                            self.current_state = OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL
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
                        # Refresh page data as login might have changed the page
                        print("Refreshing page data after login...")
                        current_url_after_login, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
                        url_to_load_after_login = current_url_after_login or self.job_url # Fallback
                        if not url_to_load_after_login:
                            print("Error: Could not determine URL after login. Critical state.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                        else:
                            self.page_data_cache = self._load_page_data(url_to_load_after_login)
                            if self.page_data_cache:
                                print("Page data refreshed. Proceeding to apply button check.")
                                self.current_state = OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL
                            else:
                                print("Error: Failed to reload page data after login.")
                                self.current_state = OrchestratorState.FAILED_ERROR
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
                    self.ai_recommendations_cache = self._call_ai_core(self.page_data_cache, self.user_profile)
                    if self.ai_recommendations_cache:
                        if self.ai_recommendations_cache.get("actions") or \
                           (self.ai_recommendations_cache.get("summary") and "Nothing to ground" in self.ai_recommendations_cache.get("summary", "")):
                            print("AI Core processing complete. Proceeding to user approval.")
                            self.current_state = OrchestratorState.AWAITING_USER_APPROVAL
                        else:
                            print("Error: Failed to get valid AI recommendations or no actionable items proposed by AI Core.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                    else:
                        print("Error: AI Core processing failed to return any recommendations.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_APPLY_BUTTON_APPROVAL:
                    if self.auto_apply_mode:
                        print("AutoApply Mode: Attempting to auto-click 'apply' button...")
                        self.current_state = OrchestratorState.EXECUTING_APPLY_BUTTON_CLICK
                    else:
                        apply_choice = input("Attempt to auto-click an 'apply' button on this page? (y/n/quit): ").lower()
                        if apply_choice == 'y':
                            self.current_state = OrchestratorState.EXECUTING_APPLY_BUTTON_CLICK
                        elif apply_choice == 'n':
                            print("Skipping auto-click of 'apply' button. Proceeding to AI Core analysis for form filling.")
                            self.current_state = OrchestratorState.CALLING_AI_CORE
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
                        current_url_after_apply, _, _ = self.browser_wrapper.get_page_state(get_screenshot=False, get_dom=False)
                        url_to_load_after_apply = current_url_after_apply or self.job_url
                        if not url_to_load_after_apply:
                             print("Error: Could not determine URL after apply click. Critical state.")
                             self.current_state = OrchestratorState.FAILED_ERROR
                        else:
                            self.page_data_cache = self._load_page_data(url_to_load_after_apply)
                            if self.page_data_cache:
                                self.current_state = OrchestratorState.CALLING_AI_CORE
                            else:
                                print("Error: Failed to reload page data after 'apply' click.")
                                self.current_state = OrchestratorState.FAILED_ERROR
                    else:
                        print("Auto-click 'apply' button failed or button not found. Proceeding to AI Core analysis of current page.")
                        self.current_state = OrchestratorState.CALLING_AI_CORE
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_USER_APPROVAL:
                    if not self.ai_recommendations_cache:
                        print("Error: No AI recommendations to approve. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue

                    print("\n--- AI Recommendations ---")
                    print(f"Summary: {self.ai_recommendations_cache.get('summary', 'N/A')}")
                    print("Fields to fill/identified:")
                    for field_info in self.ai_recommendations_cache.get('fields_to_fill', []):
                        print(f"  - Label: {field_info.get('label', 'N/A')}, "
                              f"Value to Fill: '{field_info.get('value', 'N/A')}', "
                              f"XPath: {field_info.get('xpath', 'N/A')}, "
                              f"Semantic Key: {field_info.get('semantic_key_assigned', 'N/A')}, "
                              f"Confidence: {field_info.get('overall_confidence', 'N/A')}")
                    print(f"Proposed Navigation: Click '{self.ai_recommendations_cache.get('navigation_element_text', 'N/A')}'")

                    qa_answers_review = self.ai_recommendations_cache.get('question_answers_to_review', [])
                    if qa_answers_review:
                        print("\n--- Suggested Answers to Application Questions (Review) ---")
                        for i, qa_info in enumerate(qa_answers_review):
                            print(f"  Question {i+1} for Path '{qa_info.get('dom_path_question')}': {qa_info.get('question_text_identified')}")
                            print(f"    Suggested Answer: {qa_info.get('suggested_answer_draft')}")
                        print("--- End of Suggested Answers (Review) ---")

                    if not self.ai_recommendations_cache.get("actions") and not qa_answers_review:
                        print("No actions proposed by AI and no QA answers to review. Resetting for new URL.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        time.sleep(1)
                        continue
                    elif not self.ai_recommendations_cache.get("actions") and qa_answers_review:
                        print("Only QA answers to review. No direct browser actions proposed. Please review the QA answers.")

                    if self.auto_apply_mode:
                        print("AutoApply Mode: Auto-approving AI recommendations.")
                        if self.ai_recommendations_cache.get("actions"):
                            self.current_state = OrchestratorState.EXECUTING_AUTOMATION
                        elif self.ai_recommendations_cache.get('question_answers_to_review'):
                            print("AutoApply Mode: Only QA answers to review. Logging them and completing this cycle.")
                            self._log_user_approval_of_qa_only()
                            self.current_state = OrchestratorState.COMPLETED_SUCCESS
                        else:
                            print("AutoApply Mode: No actions and no QA to approve. Setting to FAILED_ERROR.")
                            self.current_state = OrchestratorState.FAILED_ERROR
                    else:
                        approval = input("Approve and apply (this includes all fields and QA answers)? (y/n/quit): ").lower()
                        if approval == 'y':
                            if not self.ai_recommendations_cache.get("actions") and self.ai_recommendations_cache.get('question_answers_to_review'):
                                print("Approved QA answers. No direct browser actions to execute. Resetting for next URL.")
                                self._log_user_approval_of_qa_only()
                                self.current_state = OrchestratorState.AWAITING_JOB_URL
                                continue
                            else:
                                self.current_state = OrchestratorState.EXECUTING_AUTOMATION
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
                    print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Entering COMPLETED_SUCCESS state for job URL: {self.job_url}.")
                    print(f"\nApplication process for {self.job_url} completed successfully!")
                    self.job_url = None
                    self.current_state = OrchestratorState.AWAITING_JOB_URL
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.FAILED_ERROR:
                    print(f"Orchestrator ({'AutoApply' if self.auto_apply_mode else 'Manual'}): Entering FAILED_ERROR state for job URL: {self.job_url}.")
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
