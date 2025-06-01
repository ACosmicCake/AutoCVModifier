# app/orchestrator/mvp_orchestrator.py
import time
import json
from typing import Dict, Any, List, Tuple, Optional # Added for type hinting
from datetime import datetime # For feedback logging timestamp

# Integration Imports
import logging # For more detailed logging in _call_ai_core
from app.browser_automation.mvp_selenium_wrapper import MVPSeleniumWrapper
# from app.ai_core.mvp_visual_linker import extract_and_ground_page_elements # No longer used directly here
from app.ai_core.mvp_field_filler import perform_semantic_matching_for_mvp as mvp_perform_semantic_matching, \
                                         generate_text_fill_actions_for_mvp as mvp_generate_text_fill_actions
from app.ai_core.live_visual_perception import get_llm_field_predictions, parse_llm_output_to_identified_elements
from app.ai_core.live_visual_grounder import ground_visual_elements
from app.common.ai_core_data_structures import IdentifiedFormField, NavigationElement, NavigationActionType # For isinstance and nav logic

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
    CALLING_AI_CORE = "CALLING_AI_CORE"
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    EXECUTING_AUTOMATION = "EXECUTING_AUTOMATION"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    FAILED_ERROR = "FAILED_ERROR"

class MVCOrchestrator: # Renamed from MVCOrchestrator for consistency
    def __init__(self, webdriver_path: Optional[str] = None):
        self.current_state = OrchestratorState.IDLE
        self.job_url = None
        self.page_data_cache: Optional[Dict[str, Any]] = None
        self.ai_recommendations_cache: Optional[Dict[str, Any]] = None
        self.user_profile = MVP_USER_PROFILE

        # Initialize Browser Wrapper
        # For MVP, assume ChromeDriver is in PATH or handle webdriver_path if provided by config
        self.browser_wrapper = MVPSeleniumWrapper(webdriver_path=webdriver_path)
        if not self.browser_wrapper.driver:
            print("CRITICAL: Browser wrapper failed to initialize. Orchestrator cannot function.")
            # In a real app, this might raise an exception or set state to a permanent error.
            # For MVP CLI, we'll let it proceed but operations will fail.
            self.current_state = OrchestratorState.FAILED_ERROR # Set error state
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

        if not current_url or not dom_string: # Screenshot can be optional for some steps
            print("Error: Failed to get essential page state (URL or DOM).")
            return None

        return {"url": current_url, "screenshot_bytes": screenshot_bytes, "dom_string": dom_string}

    def _call_ai_core(self, page_state: Dict[str, Any], user_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logging.info(f"Orchestrator: Calling AI Core with page data for {page_state.get('url')}")
        logging.debug(f"Page state received (screenshot type): { {k: (type(v) if k=='screenshot_bytes' else v) for k,v in page_state.items()} }")

        screenshot_bytes = page_state.get("screenshot_bytes")
        dom_string = page_state.get("dom_string") # Full DOM string from Selenium

        if not screenshot_bytes:
            logging.error("AI Core: Screenshot bytes are missing in page_state. Cannot proceed.")
            return None
        if not dom_string:
            logging.warning("AI Core: DOM string is missing in page_state. Grounding quality may be affected.")
            # Proceeding, but grounder might be less effective or rely on LLM context more if it used DOM snippets

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
            page_dom_string=dom_string, # Pass limited DOM to LLM for context if desired by get_llm_field_predictions
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
            # Construct a minimal response or return None
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

        # 4. MVP Semantic Matching (using live-grounded fields)
        logging.info("AI Core: Performing MVP semantic matching on grounded fields...")
        semantically_matched_fields = mvp_perform_semantic_matching(grounded_form_fields)
        logging.info(f"AI Core: MVP Semantic matching complete. {len([f for f in semantically_matched_fields if f.semantic_meaning_predicted])} fields have semantic meaning.")

        # 5. MVP Generate Text Fill Actions (now potentially with DOM paths from live grounding)
        logging.info("AI Core: Generating MVP text fill actions...")
        fill_actions_details_obj_list = mvp_generate_text_fill_actions(semantically_matched_fields, user_profile)
        logging.info(f"AI Core: MVP text fill action generation complete. {len(fill_actions_details_obj_list)} fill actions proposed.")

        # Construct ai_recommendations_cache
        summary_message = (
            f"LivePerception: {len(identified_elements_visual_only)} vis-fields, {len(navigation_elements_visual_only)} vis-navs. "
            f"Grounder: {count_successfully_grounded_fields}/{len(grounded_form_fields)} fields, {count_successfully_grounded_navs}/{len(grounded_navigation_elements)} navs. "
            f"MVP Semantics: {len(fill_actions_details_obj_list)} fill actions."
        )

        fields_to_display = []
        for field in semantically_matched_fields: # Display based on semantic match
            value_to_fill_display = user_profile.get(field.semantic_meaning_predicted, "N/A_IN_PROFILE") if field.semantic_meaning_predicted else "NO_SEMANTIC_MATCH"
            fields_to_display.append({
                "label": field.visual_label_text or "Unknown Label",
                "value": value_to_fill_display,
                "xpath": field.dom_path_primary if field.dom_path_primary else "NOT_GROUNDED",
                "grounding_confidence": round(field.confidence_score, 3) if field.confidence_score else 0.0
            })

        final_actions_list = [action.to_dict() for action in fill_actions_details_obj_list] # Convert ActionDetail objects to dicts

        chosen_navigation_text = "No usable navigation found."
        nav_target: Optional[NavigationElement] = None

        if grounded_navigation_elements:
            # Prioritize submit, then next, then first grounded
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
                    "visual_label": chosen_navigation_text # For display/logging
                })
                logging.info(f"AI Core: Selected navigation action: Click '{chosen_navigation_text}' (XPath: {nav_target.dom_path_primary})")
            elif any(n.dom_path_primary for n in grounded_navigation_elements):
                 chosen_navigation_text = "Grounded navigation found, but no clear submit/next."
                 logging.warning(f"AI Core: {chosen_navigation_text}")
            else:
                 chosen_navigation_text = "Navigation elements visually found but none could be grounded."
                 logging.warning(f"AI Core: {chosen_navigation_text}")
        else:
            logging.info("AI Core: No navigation elements identified by visual perception to begin with.")

        final_recommendations = {
            "summary": summary_message,
            "fields_to_fill": fields_to_display,
            "actions": final_actions_list,
            "navigation_element_text": chosen_navigation_text
        }
        logging.debug(f"Final AI recommendations: {final_recommendations}")
        return final_recommendations

    def _execute_browser_automation(self, actions: List[Dict[str, Any]]) -> bool:
        logging.info("Orchestrator: Executing browser automation actions...")
        if not self.browser_wrapper or not self.browser_wrapper.driver:
            print("Error: Browser wrapper not available for executing actions.")
            return False

        for i, action_dict in enumerate(actions):
            action_type = action_dict.get('action_type')
            dom_path = action_dict.get('dom_path_target')
            value = action_dict.get('value_to_fill') # For FILL_TEXT

            print(f"  Action {i+1}/{len(actions)}: Type: {action_type}, Path: {dom_path}" + (f", Value: '{str(value)[:30]}...'" if value else ""))

            success = False
            if action_type == "FILL_TEXT": # Using string as per current ActionDetail conversion
                if dom_path and value is not None:
                    success = self.browser_wrapper.fill_text_field(xpath=dom_path, text=str(value))
                else:
                    print(f"    Skipping FILL_TEXT due to missing path or value.")
            elif action_type == "CLICK_ELEMENT":
                if dom_path:
                    success = self.browser_wrapper.click_element(xpath=dom_path)
                else:
                    print(f"    Skipping CLICK_ELEMENT due to missing path.")
            else:
                print(f"    Warning: Unknown action type '{action_type}' in action sequence.")
                continue # Skip unknown action types

            if not success:
                print(f"  Action failed: {action_type} on {dom_path}")
                return False # Stop on first failure

            time.sleep(0.5) # Small delay between actions

        print("Orchestrator: All browser automation actions completed successfully.")
        return True

    def run(self):
        if self.current_state == OrchestratorState.FAILED_ERROR and not self.browser_wrapper.driver:
            print("Orchestrator cannot start due to browser initialization failure.")
            self.current_state = OrchestratorState.IDLE # Go to IDLE to allow shutdown

        if self.current_state == OrchestratorState.IDLE and self.browser_wrapper.driver: # Initial transition if browser is ok
             self.current_state = OrchestratorState.AWAITING_JOB_URL

        print(f"State: {self.current_state}")

        try:
            while True:
                if self.current_state == OrchestratorState.AWAITING_JOB_URL:
                    # For MVP, we can use a predefined target URL to simplify testing with mvp_visual_linker
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
                        # No break here, let the loop condition handle exit
                    else:
                        print("Invalid input. Please enter 'y', 'n', or 'quit'.")
                        continue

                    if self.job_url and self.job_url.lower() == 'quit': # Handles quit if 'n' was chosen then 'quit'
                        self.current_state = OrchestratorState.IDLE

                    if self.current_state == OrchestratorState.IDLE: # check before http validation
                        pass # will break at the end of the loop
                    elif not self.job_url or not self.job_url.startswith("http"):
                        print("Invalid or missing URL. Please include http:// or https:// or choose 'y' for predefined.")
                        self.job_url = None # Reset job_url if invalid
                        # Stay in AWAITING_JOB_URL state
                    else:
                        self.current_state = OrchestratorState.LOADING_PAGE_DATA
                        print(f"State: {self.current_state} - URL: {self.job_url}")

                elif self.current_state == OrchestratorState.LOADING_PAGE_DATA:
                    if not self.job_url: # Should not happen if logic is correct
                        print("Error: No job URL to load. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    self.page_data_cache = self._load_page_data(self.job_url)
                    if self.page_data_cache:
                        self.current_state = OrchestratorState.CALLING_AI_CORE
                    else:
                        print("Error: Failed to load page data.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.CALLING_AI_CORE:
                    if not self.page_data_cache: # Should not happen
                        print("Error: No page data to process. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    self.ai_recommendations_cache = self._call_ai_core(self.page_data_cache, self.user_profile)
                    if self.ai_recommendations_cache and self.ai_recommendations_cache.get("actions"):
                        self.current_state = OrchestratorState.AWAITING_USER_APPROVAL
                    else:
                        print("Error: Failed to get valid AI recommendations or no actions proposed.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.AWAITING_USER_APPROVAL:
                    if not self.ai_recommendations_cache: # Should not happen
                        print("Error: No AI recommendations to approve. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    print("\n--- AI Recommendations ---")
                    print(f"Summary: {self.ai_recommendations_cache.get('summary', 'N/A')}")
                    print("Fields to fill:")
                    for field in self.ai_recommendations_cache.get('fields_to_fill', []):
                        print(f"  - Label: {field.get('label', 'N/A')}, Value: '{field.get('value', 'N/A')}', Target: {field.get('dom_path', 'N/A')}")
                    print(f"Navigation: Click '{self.ai_recommendations_cache.get('navigation_element_text', 'N/A')}'")
                    print("--- End of AI Recommendations ---")

                    approval = input("Approve and apply? (y/n/quit): ").lower()
                    if approval == 'y':
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
                    if not self.ai_recommendations_cache or not self.ai_recommendations_cache.get("actions"): # Should not happen
                        print("Error: No actions to execute. Resetting.")
                        self.current_state = OrchestratorState.AWAITING_JOB_URL
                        continue
                    success = self._execute_browser_automation(self.ai_recommendations_cache['actions'])
                    if success:
                        self.current_state = OrchestratorState.COMPLETED_SUCCESS
                    else:
                        # Note: _execute_browser_automation already prints detailed error
                        print("Orchestrator: Execution of browser automation failed.")
                        self.current_state = OrchestratorState.FAILED_ERROR
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.COMPLETED_SUCCESS:
                    print(f"\nApplication process for {self.job_url} completed successfully!")
                    self.job_url = None # Reset for next run
                    self.current_state = OrchestratorState.AWAITING_JOB_URL
                    print(f"State: {self.current_state}")

                elif self.current_state == OrchestratorState.FAILED_ERROR:
                    print(f"\nApplication process for {self.job_url} failed or encountered an error.")
                    self.job_url = None # Reset for next run
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
        """Logs user disapproval feedback to a file."""
        if not self.ai_recommendations_cache:
            print("LogFeedback: No AI recommendations to log.")
            return

        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z", # ISO 8601 format with Z for UTC
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


if __name__ == "__main__":
    # You might need to provide a path to your chromedriver if it's not in PATH
    # Example: orchestrator = MVCOrchestrator(webdriver_path="/path/to/chromedriver")
    orchestrator = MVCOrchestrator()
    orchestrator.run()
