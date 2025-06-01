# app/ai_core/live_visual_perception.py
import os
import json
import logging
import re
from typing import Optional, Dict, Any, List, Tuple # Added Tuple
import uuid # For generating unique IDs

import google.generativeai as genai
from PIL import Image # For creating dummy image data in demo, and potentially for image validation

# Data structures from common module
from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    NavigationElement,
    VisualLocation,
    PredictedFieldType,
    NavigationActionType
)


# Configuration
API_KEY_ENV_VAR = "GEMINI_API_KEY" # Or your chosen environment variable name
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

_gemini_configured = False

# Helper Function
def _configure_gemini(api_key: str) -> bool:
    """Configures the Gemini API. Ensures it's called only once effectively."""
    global _gemini_configured
    if _gemini_configured:
        return True
    if not api_key:
        logging.error("Gemini API key is missing.")
        return False
    try:
        genai.configure(api_key=api_key)
        _gemini_configured = True
        logging.info("Gemini API configured successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")
        return False

def get_llm_field_predictions(
    screenshot_bytes: bytes,
    page_dom_string: Optional[str] = None,
    live_llm_call: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Gets field predictions from a multimodal LLM (Gemini Pro Vision).
    Can use a live API call or return a simulated response.

    Args:
        screenshot_bytes: Bytes of the screenshot image (PNG/JPEG).
        page_dom_string: Optional string containing the page's DOM structure.
        live_llm_call: If True, attempts a live API call. Otherwise, returns simulated data.

    Returns:
        A dictionary parsed from the LLM's JSON response, or None on failure.
    """
    global _gemini_configured
    if live_llm_call and not _gemini_configured:
        api_key = os.getenv(API_KEY_ENV_VAR)
        if not api_key:
            logging.error(f"Live LLM call requested, but API key environment variable '{API_KEY_ENV_VAR}' not found.")
            return None
        if not _configure_gemini(api_key):
            logging.error("Live LLM call requested, but Gemini API configuration failed.")
            return None

    llm_output_text: Optional[str] = None

    if live_llm_call:
        logging.info("Attempting LIVE call to Gemini Pro Vision API...")
        try:
            model = genai.GenerativeModel('gemini-pro-vision')

            # Construct the prompt based on research
            # (docs/ai_core/ai_core_llm_research_and_setup.md)
            prompt_parts: List[Any] = [
                """You are an expert AI assistant specialized in analyzing web page screenshots to identify user interface elements for web automation.
Analyze the provided screenshot of a web page.
Identify all common form elements such as text inputs (single-line and multi-line textareas), email inputs, phone inputs, dropdowns/selects, checkboxes, radio buttons, and interactive buttons (like submit, next, cancel).

For each element you identify, provide the following information:
1.  `visual_label`: The visible text label clearly associated with the form element. If no direct label, try to infer from placeholder text or nearby text that functions as a label. If the element is a button, this should be the button's visible text.
2.  `element_bbox`: The bounding box coordinates [x_min, y_min, x_max, y_max] for the interactive element itself (e.g., the clickable area of a button, the input area of a text field). Coordinates should be pixel values relative to the image dimensions (0,0 at top-left).
3.  `label_bbox`: The bounding box coordinates [x_min, y_min, x_max, y_max] for the visual label corresponding to the element. If the element is a button and its text is within `element_bbox`, `label_bbox` can be the same as `element_bbox`.
4.  `element_type`: A standardized type string from this list: ['text_input', 'textarea', 'dropdown', 'checkbox', 'radio_button', 'button', 'email_input', 'phone_input', 'other_input'].

Return this information as a single JSON object. The root object must have a single key named 'identified_elements'. The value of 'identified_elements' must be a list of JSON objects, where each object represents one identified UI element and strictly adheres to the keys listed above.
Example of a single element object:
{
    "visual_label": "First Name",
    "element_bbox": [100, 50, 300, 80],
    "label_bbox": [20, 50, 90, 80],
    "element_type": "text_input"
}
Ensure your entire response is ONLY this JSON object, without any surrounding text or explanations.
""",
                Image.open(io.BytesIO(screenshot_bytes)) # Use PIL Image, SDK handles conversion
            ]

            if page_dom_string:
                prompt_parts.append("\n\nFor additional context, here is a snippet of the page's DOM structure (use it to refine your visual analysis if helpful, but prioritize visual evidence from the screenshot for element presence and labels):\n")
                prompt_parts.append(page_dom_string[:5000]) # Limit DOM string length

            logging.info("Sending request to Gemini API...")
            response = model.generate_content(prompt_parts)

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logging.warning(f"Gemini API call blocked. Reason: {response.prompt_feedback.block_reason}")
                logging.warning(f"Safety ratings: {response.prompt_feedback.safety_ratings}")
                return None

            llm_output_text = response.text
            logging.info(f"Received response from Gemini API (first 100 chars): {llm_output_text[:100]}...")

        except Exception as e_api:
            logging.error(f"Error during Gemini API call: {e_api}")
            return None
    else:
        logging.info("Using SIMULATED LLM response (live_llm_call=False).")
        # Corrected hardcoded sample JSON string
        simulated_llm_text_output = '''
```json
{
    "identified_elements": [
        {
            "element_type": "text_input",
            "visual_label": "Full Name",
            "element_bbox": [100, 50, 300, 80],
            "label_bbox": [20, 50, 90, 80]
        },
        {
            "element_type": "email_input",
            "visual_label": "Email Address",
            "element_bbox": [100, 100, 300, 130],
            "label_bbox": [20, 100, 90, 130]
        },
        {
            "element_type": "button",
            "visual_label": "Submit",
            "element_bbox": [100, 150, 200, 180],
            "label_bbox": [100, 150, 200, 180]
        },
        {
            "element_type": "checkbox",
            "visual_label": "Subscribe to newsletter",
            "element_bbox": [50, 200, 70, 220],
            "label_bbox": [80, 200, 250, 220]
        }
    ]
}
```
'''
        llm_output_text = simulated_llm_text_output

    if not llm_output_text:
        logging.warning("LLM output text is empty.")
        return None

    # Parsing LLM Output Text
    try:
        logging.debug(f"Raw LLM output: {llm_output_text}")
        # Extract JSON if wrapped in markdown code fences
        match = re.search(r"```json\s*([\s\S]*?)\s*```", llm_output_text, re.IGNORECASE)
        if match:
            json_str = match.group(1)
            logging.info("Extracted JSON from markdown code block.")
        else:
            # Try to find JSON directly if not in fences, or if it's the whole string
            # This might happen if the LLM doesn't use fences or if the regex fails.
            # A common case is the LLM returning JSON directly without fences if prompted correctly.
            if llm_output_text.strip().startswith('{') and llm_output_text.strip().endswith('}'):
                 json_str = llm_output_text.strip()
                 logging.info("Detected JSON directly without markdown fences.")
            else:
                logging.warning("Could not find JSON within markdown code fences, and output doesn't look like direct JSON. Attempting to parse as is, but may fail.")
                json_str = llm_output_text # Assume the whole string might be JSON (less robust)

        parsed_dict = json.loads(json_str)
        logging.info("Successfully parsed LLM output text to dictionary.")
        return parsed_dict
    except json.JSONDecodeError as e_json:
        logging.error(f"Failed to decode JSON from LLM output: {e_json}")
        logging.error(f"Problematic JSON string snippet: {json_str[:500] if 'json_str' in locals() else llm_output_text[:500]}")
        return None
    except Exception as e_parse:
        logging.error(f"An unexpected error occurred during LLM output parsing: {e_parse}")
        return None

if __name__ == '__main__':
    import io # Required for Image.open(io.BytesIO(...))

    logging.info("--- Live Visual Perception Module Demo ---")

    api_key_present = os.getenv(API_KEY_ENV_VAR)
    if api_key_present:
        logging.info(f"API Key '{API_KEY_ENV_VAR}' is SET.")
    else:
        logging.warning(f"API Key '{API_KEY_ENV_VAR}' is NOT SET. Live calls will fail unless key is passed directly or set.")

    # Create dummy screenshot bytes (e.g., a small 1x1 PNG)
    # In a real scenario, this would come from the browser automation layer
    try:
        img = Image.new('RGB', (600, 400), color = 'rgb(230, 230, 230)')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        dummy_screenshot_bytes = img_byte_arr.getvalue()
        logging.info(f"Created dummy screenshot: {len(dummy_screenshot_bytes)} bytes.")
    except Exception as e:
        logging.error(f"Could not create dummy image for demo: {e}")
        dummy_screenshot_bytes = b"fake_screenshot_data_for_demo" # fallback

    dummy_dom_string = "<html><body><h1>Login Page</h1><input type='text' name='username_field' placeholder='Username'></body></html>"

    # --- Test with Simulated Response (live_llm_call=False) ---
    logging.info("\n--- Testing with SIMULATED LLM response (live_llm_call=False) ---")
    simulated_output = get_llm_field_predictions(
        screenshot_bytes=dummy_screenshot_bytes,
        page_dom_string=dummy_dom_string,
        live_llm_call=False
    )
    if simulated_output:
        logging.info(f"Simulated output type: {type(simulated_output)}")
        logging.info(f"Simulated output content (pretty-printed):\n{json.dumps(simulated_output, indent=2)}")
    else:
        logging.error("Failed to get simulated output.")

    # --- Example for Live Call (Commented out by default to prevent accidental calls) ---
    # logging.info("\n--- Testing with LIVE LLM response (live_llm_call=True) ---")
    # logging.info(f"Ensure '{API_KEY_ENV_VAR}' environment variable is set with your Gemini API key.")
    # if api_key_present: # Only attempt if key seems to be there
    #     live_output = get_llm_field_predictions(
    #         screenshot_bytes=dummy_screenshot_bytes,
    #         page_dom_string=dummy_dom_string,
    #         live_llm_call=True
    #     )
    #     if live_output:
    #         logging.info(f"Live output type: {type(live_output)}")
    #         logging.info(f"Live output content (pretty-printed):\n{json.dumps(live_output, indent=2)}")
    #     else:
    #         logging.error("Failed to get live LLM output. Check API key, quota, and logs.")
    # else:
    #     logging.warning("Skipping live LLM call demo as API key is not detected in environment.")

    # --- Demonstrate the new parsing function ---
    if simulated_output:
        logging.info("\n--- Parsing the (simulated) LLM Output ---")
        parsed_forms, parsed_navs = parse_llm_output_to_identified_elements(simulated_output)

        logging.info(f"\nParsed IdentifiedFormFields ({len(parsed_forms)}):")
        for i, field in enumerate(parsed_forms):
            logging.info(f"  Field {i+1}: ID={field.id}, Label='{field.visual_label_text}', Type={field.field_type_predicted.name}, BBox={field.visual_location}")
            if field.label_visual_location:
                logging.info(f"    Label BBox={field.label_visual_location}")

        logging.info(f"\nParsed NavigationElements ({len(parsed_navs)}):")
        for i, nav in enumerate(parsed_navs):
            logging.info(f"  Nav {i+1}: ID={nav.id}, Label='{nav.visual_label_text}', ActionType={nav.action_type_predicted.name}, BBox={nav.visual_location}")
    else:
        logging.warning("Skipping parsing demo as simulated_output was None.")

    logging.info("\n--- Live Visual Perception Module Demo Finished ---")


# --- Added for LLM Output Parsing and Transformation ---

def _parse_bbox(bbox_coords_list: Optional[List[Any]]) -> Optional[VisualLocation]:
    """
    Parses a list of 4 bounding box coordinates (expected: [x_min, y_min, x_max, y_max])
    and converts it to a VisualLocation object (x, y, width, height).
    """
    if not bbox_coords_list or not isinstance(bbox_coords_list, list) or len(bbox_coords_list) != 4:
        logging.warning(f"Invalid bounding box coordinate list: {bbox_coords_list}. Expected list of 4 numbers.")
        return None

    try:
        # Ensure all coordinates are numbers (int or float)
        coords = [float(c) for c in bbox_coords_list]
    except (ValueError, TypeError):
        logging.warning(f"Non-numeric value in bounding box coordinates: {bbox_coords_list}")
        return None

    x_min, y_min, x_max, y_max = coords

    if x_max < x_min:
        logging.warning(f"Bounding box x_max ({x_max}) < x_min ({x_min}). Invalid.")
        # Option: return None, or a zero-width box at x_min, y_min
        # For now, let's allow it but width will be negative or zero, which VisualLocation should handle or be checked for.
        # Or, more strictly: return None
    if y_max < y_min:
        logging.warning(f"Bounding box y_max ({y_max}) < y_min ({y_min}). Invalid.")
        # Similar handling for height.

    # Convert to x, y, width, height
    # Ensure width and height are not negative. If x_max < x_min, width becomes 0.
    width = max(0, x_max - x_min)
    height = max(0, y_max - y_min)

    return VisualLocation(x=int(x_min), y=int(y_min), width=int(width), height=int(height))


def parse_llm_output_to_identified_elements(
    llm_output: Optional[Dict[str, Any]]
) -> Tuple[List[IdentifiedFormField], List[NavigationElement]]:
    """
    Parses the raw dictionary output from the LLM (after JSON parsing) and transforms it
    into lists of IdentifiedFormField and NavigationElement objects.
    """
    identified_form_fields: List[IdentifiedFormField] = []
    navigation_elements: List[NavigationElement] = []

    if not llm_output:
        logging.warning("LLM output dictionary is None. Cannot parse elements.")
        return identified_form_fields, navigation_elements

    elements_data = llm_output.get("identified_elements")
    if not isinstance(elements_data, list):
        logging.warning(f"LLM output missing 'identified_elements' list or it's not a list. Output: {str(llm_output)[:500]}")
        return identified_form_fields, navigation_elements

    logging.info(f"Parsing {len(elements_data)} elements from LLM output.")

    for i, element_dict in enumerate(elements_data):
        if not isinstance(element_dict, dict):
            logging.warning(f"Element item {i} is not a dictionary: {element_dict}")
            continue

        element_type_str = element_dict.get("element_type", "unknown").lower().strip()
        visual_label = element_dict.get("visual_label", f"Element_{i+1}") # Default label if missing

        element_bbox_coords = element_dict.get("element_bbox")
        label_bbox_coords = element_dict.get("label_bbox") # Optional

        element_visual_location = _parse_bbox(element_bbox_coords)
        if not element_visual_location:
            logging.warning(f"Skipping element '{visual_label}' due to invalid or missing element_bbox: {element_bbox_coords}")
            continue

        label_visual_location = _parse_bbox(label_bbox_coords) # Can be None

        # Map string type to PredictedFieldType enum
        predicted_type_enum = PredictedFieldType.UNKNOWN # Default
        if element_type_str == "text_input":
            predicted_type_enum = PredictedFieldType.TEXT_INPUT
        elif element_type_str == "email_input":
            predicted_type_enum = PredictedFieldType.EMAIL_INPUT # Assuming this enum exists
        elif element_type_str == "phone_input":
            predicted_type_enum = PredictedFieldType.PHONE_INPUT # Assuming this enum exists
        elif element_type_str == "textarea":
            predicted_type_enum = PredictedFieldType.TEXTAREA
        elif element_type_str == "button":
            predicted_type_enum = PredictedFieldType.BUTTON
        elif element_type_str == "checkbox":
            predicted_type_enum = PredictedFieldType.CHECKBOX
        elif element_type_str == "radio_button": # LLM might say "radio"
            predicted_type_enum = PredictedFieldType.RADIO_BUTTON
        elif element_type_str == "dropdown" or element_type_str == "select":
            predicted_type_enum = PredictedFieldType.DROPDOWN
        elif element_type_str == "other_input":
             predicted_type_enum = PredictedFieldType.OTHER_INPUT # Assuming this enum exists
        else:
            logging.warning(f"Unknown element type string '{element_type_str}' for label '{visual_label}'. Defaulting to UNKNOWN.")


        # Distinguish Navigation Elements (primarily buttons for now)
        is_navigation = False
        if predicted_type_enum == PredictedFieldType.BUTTON:
            label_lower = visual_label.lower()
            nav_action_type = NavigationActionType.CLICK_GENERIC_BUTTON # Default for non-specific buttons

            # Simple keyword matching for common navigation actions
            if any(kw in label_lower for kw in ["submit", "apply", "send", "complete"]):
                nav_action_type = NavigationActionType.SUBMIT_FORM
                is_navigation = True
            elif any(kw in label_lower for kw in ["next", "continue", "proceed"]):
                nav_action_type = NavigationActionType.NEXT_PAGE
                is_navigation = True
            elif any(kw in label_lower for kw in ["back", "previous"]):
                nav_action_type = NavigationActionType.PREVIOUS_PAGE
                is_navigation = True
            elif any(kw in label_lower for kw in ["cancel"]):
                nav_action_type = NavigationActionType.CANCEL
                is_navigation = True
            elif any(kw in label_lower for kw in ["login", "log in", "sign in"]):
                nav_action_type = NavigationActionType.LOGIN # Assuming this enum exists
                is_navigation = True
            # Add more keywords/logic as needed (e.g., "save draft")

            if is_navigation:
                nav_el = NavigationElement(
                    id=str(uuid.uuid4()),
                    visual_label_text=visual_label,
                    visual_location=element_visual_location,
                    dom_path="", # To be filled by grounding module
                    action_type_predicted=nav_action_type,
                    confidence_score=0.7  # Placeholder
                )
                navigation_elements.append(nav_el)
                logging.info(f"  Parsed as NavigationElement: '{visual_label}' (Type: {nav_action_type.name})")
            # If it's a button but not matched as navigation, it becomes a regular IdentifiedFormField below

        if not is_navigation: # Either not a button, or a button not classified as navigation
            form_field = IdentifiedFormField(
                id=str(uuid.uuid4()),
                visual_label_text=visual_label,
                visual_location=element_visual_location,
                label_visual_location=label_visual_location, # Can be None
                dom_path_primary="",  # To be filled by grounding
                dom_path_label="",    # To be filled by grounding
                field_type_predicted=predicted_type_enum,
                semantic_meaning_predicted="", # To be filled by semantic matching
                confidence_score=0.7,  # Placeholder
                is_required_predicted=False # Placeholder
            )
            identified_form_fields.append(form_field)
            logging.info(f"  Parsed as IdentifiedFormField: '{visual_label}' (Type: {predicted_type_enum.name})")

    return identified_form_fields, navigation_elements
