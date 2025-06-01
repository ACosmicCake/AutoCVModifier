# app/ai_core/mvp_visual_linker.py
import json
import uuid
import re
from typing import Tuple, Optional, List, Dict, Any

# Assumes ai_core_data_structures.py is now in app/common/
from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    NavigationElement,
    VisualLocation,
    PredictedFieldType,
    NavigationActionType
)

TARGET_URL = "https://www.realjobapply.com/apply/job123"

# Sample DOM for the target website. In a real scenario, this would be fetched.
SAMPLE_DOM_REALJOBAPPLY = """
<!DOCTYPE html>
<html>
<head><title>Job Application for Job123</title></head>
<body>
    <h1>Application Form - Job123</h1>
    <form id="applicationForm">
        <div>
            <label for="fname" style="position:absolute; left:20px; top:50px;">First Name:</label>
            <input type="text" id="fname" name="firstName" style="position:absolute; left:100px; top:50px; width:200px; height:30px;">
        </div>
        <div>
            <label for="lname" style="position:absolute; left:20px; top:100px;">Last Name:</label>
            <input type="text" id="lname" name="lastName" style="position:absolute; left:100px; top:100px; width:200px; height:30px;">
        </div>
        <div>
            <label for="email_address" style="position:absolute; left:20px; top:150px;">Your Email:</label>
            <input type="email" id="email_address" name="email" style="position:absolute; left:100px; top:150px; width:200px; height:30px;">
        </div>
        <div>
            <label for="phone_num" style="position:absolute; left:20px; top:200px;">Phone Number:</label>
            <input type="tel" id="phone_num" name="phone" style="position:absolute; left:100px; top:200px; width:200px; height:30px;">
        </div>
        <button type="submit" id="submitBtn" name="submitApplication" style="position:absolute; left:100px; top:250px; width:150px; height:40px;">Submit Application</button>
    </form>
</body>
</html>
"""

# 1. Simulated Screenshot and DOM Capture
def capture_screenshot_and_dom(url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Simulates capturing screenshot and DOM for a given URL.
    For MVP, returns predefined data if URL matches the target website.
    """
    print(f"MVPVisualLinker: Attempting to capture data for URL: {url}")
    if url == TARGET_URL:
        print(f"MVPVisualLinker: Target URL matched. Returning predefined DOM and dummy screenshot bytes.")
        return b"dummy_screenshot_bytes_for_realjobapply", SAMPLE_DOM_REALJOBAPPLY
    print(f"MVPVisualLinker: URL does not match target. Returning None.")
    return None, None

# 2. Simulated Multimodal LLM Call
def call_multimodal_llm_for_fields(screenshot_bytes: bytes, dom_string: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Simulates calling a multimodal LLM. Returns a hardcoded JSON-like dictionary
    specific to the layout of www.realjobapply.com/apply/job123.
    """
    print(f"MVPVisualLinker: Simulating call to Multimodal LLM with screenshot data.")
    if not screenshot_bytes: # Basic check
        return None

    # This response is tailored to SAMPLE_DOM_REALJOBAPPLY
    # Bounding boxes are plausible based on the style attributes in SAMPLE_DOM_REALJOBAPPLY
    llm_response = {
        "identified_elements": [
            {
                "label_text": "First Name:",
                "field_bounding_box": [100, 50, 200, 30], # x, y, width, height
                "label_bounding_box": [20, 50, 70, 30],  # Approximated
                "field_type_guess": "text_input"
            },
            {
                "label_text": "Last Name:",
                "field_bounding_box": [100, 100, 200, 30],
                "label_bounding_box": [20, 100, 70, 30],
                "field_type_guess": "text_input"
            },
            {
                "label_text": "Your Email:",
                "field_bounding_box": [100, 150, 200, 30],
                "label_bounding_box": [20, 150, 70, 30],
                "field_type_guess": "text_input" # Could be "email_input"
            },
            {
                "label_text": "Phone Number:",
                "field_bounding_box": [100, 200, 200, 30],
                "label_bounding_box": [20, 200, 75, 30], # Adjusted width for "Phone Number:"
                "field_type_guess": "text_input" # Could be "phone_input"
            },
            {
                "label_text": "Submit Application", # For buttons, label is often the button text itself
                "field_bounding_box": [100, 250, 150, 40],
                "label_bounding_box": [100, 250, 150, 40], # Same as field for button
                "field_type_guess": "button"
            }
        ]
    }
    print(f"MVPVisualLinker: Simulated LLM response generated.")
    return llm_response

# 3. Parse LLM Response
def parse_llm_response(llm_response: Dict[str, Any]) -> List[IdentifiedFormField]:
    """
    Parses the (simulated) LLM JSON response and transforms items into IdentifiedFormField objects.
    """
    print(f"MVPVisualLinker: Parsing LLM response.")
    parsed_fields: List[IdentifiedFormField] = []
    if not llm_response or "identified_elements" not in llm_response:
        return parsed_fields

    for element in llm_response["identified_elements"]:
        field_bbox = element["field_bounding_box"]

        try:
            # Simplified mapping for MVP
            if element["field_type_guess"] == "text_input":
                field_type = PredictedFieldType.TEXT_INPUT
            elif element["field_type_guess"] == "button":
                field_type = PredictedFieldType.BUTTON
            else:
                field_type = PredictedFieldType.TEXT_INPUT # Default
        except KeyError:
            field_type = PredictedFieldType.TEXT_INPUT

        form_field = IdentifiedFormField(
            id=f"vis_{uuid.uuid4()}",
            visual_label_text=element.get("label_text"),
            visual_location=VisualLocation(x=field_bbox[0], y=field_bbox[1], width=field_bbox[2], height=field_bbox[3]),
            dom_path_primary="", # To be filled by grounding
            dom_path_label="",   # To be filled by grounding (if applicable)
            field_type_predicted=field_type,
            semantic_meaning_predicted="", # To be filled by semantic matcher
            confidence_score=0.80,  # Placeholder for visually identified elements
            is_required_predicted=False # Visual model might not always infer this
        )
        parsed_fields.append(form_field)
    print(f"MVPVisualLinker: Parsed {len(parsed_fields)} elements from LLM response.")
    return parsed_fields

# 4. Ground Elements to DOM
def ground_elements_to_dom(identified_elements: List[IdentifiedFormField], dom_string: str) -> List[IdentifiedFormField]:
    """
    Implements rule-based/heuristic logic to find XPaths for elements
    based on the sample DOM of www.realjobapply.com/apply/job123.
    """
    print(f"MVPVisualLinker: Grounding {len(identified_elements)} elements to DOM.")
    updated_elements: List[IdentifiedFormField] = []

    for element in identified_elements:
        label = (element.visual_label_text or "").lower()
        # Basic XPath grounding based on expected IDs/names in SAMPLE_DOM_REALJOBAPPLY
        if "first name" in label:
            element.dom_path_primary = "//input[@id='fname']"
            element.dom_path_label = "//label[@for='fname']"
        elif "last name" in label:
            element.dom_path_primary = "//input[@id='lname']"
            element.dom_path_label = "//label[@for='lname']"
        elif "your email" in label: # Matches "Your Email:" from LLM
            element.dom_path_primary = "//input[@id='email_address']"
            element.dom_path_label = "//label[@for='email_address']"
        elif "phone number" in label:
            element.dom_path_primary = "//input[@id='phone_num']"
            element.dom_path_label = "//label[@for='phone_num']"
        elif "submit application" in label and element.field_type_predicted == PredictedFieldType.BUTTON:
            element.dom_path_primary = "//button[@id='submitBtn']"

        if element.dom_path_primary:
            print(f"  Grounded '{element.visual_label_text}' to DOM path: {element.dom_path_primary}")
            element.confidence_score = min(1.0, element.confidence_score + 0.15) # Boost confidence
        else:
            print(f"  Could not ground '{element.visual_label_text}' to DOM.")

        updated_elements.append(element)
    return updated_elements

# 5. Main Orchestration Function
def extract_and_ground_page_elements(url: str) -> Tuple[List[IdentifiedFormField], List[NavigationElement]]:
    """
    Orchestrates the capture, LLM call, parsing, and grounding for a given URL.
    """
    print(f"\nMVPVisualLinker: Starting extraction and grounding for URL: {url}")
    form_fields: List[IdentifiedFormField] = []
    navigation_elements: List[NavigationElement] = []

    screenshot_bytes, dom_string = capture_screenshot_and_dom(url)

    if not screenshot_bytes or not dom_string:
        print("MVPVisualLinker: Failed to capture screenshot or DOM. Aborting.")
        return form_fields, navigation_elements

    llm_response = call_multimodal_llm_for_fields(screenshot_bytes, dom_string)
    if not llm_response:
        print("MVPVisualLinker: Failed to get response from LLM. Aborting.")
        return form_fields, navigation_elements

    visually_identified_elements = parse_llm_response(llm_response)
    if not visually_identified_elements:
        print("MVPVisualLinker: No elements parsed from LLM response. Aborting.")
        return form_fields, navigation_elements

    grounded_elements = ground_elements_to_dom(visually_identified_elements, dom_string)

    # Separate into form fields and navigation elements
    for element in grounded_elements:
        if element.field_type_predicted == PredictedFieldType.BUTTON and \
           ("submit" in (element.visual_label_text or "").lower() or \
            "next" in (element.visual_label_text or "").lower() or \
            "continue" in (element.visual_label_text or "").lower() ): # Basic check

            action_type = NavigationActionType.OTHER # Default
            if "submit" in (element.visual_label_text or "").lower():
                action_type = NavigationActionType.SUBMIT_FORM
            elif "next" in (element.visual_label_text or "").lower() or "continue" in (element.visual_label_text or "").lower():
                 action_type = NavigationActionType.NEXT_PAGE

            nav_el = NavigationElement(
                id=f"nav_{uuid.uuid4()}",
                visual_label_text=element.visual_label_text,
                visual_location=element.visual_location,
                dom_path=element.dom_path_primary,
                action_type_predicted=action_type,
                confidence_score=element.confidence_score
            )
            navigation_elements.append(nav_el)
            print(f"  Identified as NavigationElement: {nav_el.visual_label_text} ({nav_el.action_type_predicted})")
        elif element.dom_path_primary: # Only add if successfully grounded
            form_fields.append(element)
        else:
            print(f"  Skipping element '{element.visual_label_text}' from final list due to failed grounding.")


    print(f"MVPVisualLinker: Extraction and grounding complete. Found {len(form_fields)} form fields and {len(navigation_elements)} navigation elements.")
    return form_fields, navigation_elements


if __name__ == '__main__':
    print("--- Running MVP Visual Linker Demo ---")

    target_url_test = TARGET_URL
    print(f"Testing with target URL: {target_url_test}")

    fields, nav_elements = extract_and_ground_page_elements(target_url_test)

    print("\n--- Results ---")
    print("\nIdentified Form Fields:")
    if fields:
        for i, field in enumerate(fields):
            print(f"  Field {i+1}:")
            print(f"    ID: {field.id}")
            print(f"    Visual Label: '{field.visual_label_text}'")
            print(f"    Visual Location: {field.visual_location}")
            print(f"    Predicted Type: {field.field_type_predicted.name}")
            print(f"    DOM Path Primary: '{field.dom_path_primary}'")
            print(f"    DOM Path Label: '{field.dom_path_label}'")
            print(f"    Confidence: {field.confidence_score:.2f}")
    else:
        print("  No form fields identified or grounded.")

    print("\nIdentified Navigation Elements:")
    if nav_elements:
        for i, nav_el in enumerate(nav_elements):
            print(f"  Navigation Element {i+1}:")
            print(f"    ID: {nav_el.id}")
            print(f"    Visual Label: '{nav_el.visual_label_text}'")
            print(f"    Visual Location: {nav_el.visual_location}")
            print(f"    Predicted Action Type: {nav_el.action_type_predicted.name}")
            print(f"    DOM Path: '{nav_el.dom_path}'")
            print(f"    Confidence: {nav_el.confidence_score:.2f}")
    else:
        print("  No navigation elements identified.")

    print("\n--- Testing with a non-target URL ---")
    non_target_url_test = "https://www.someotherwebsite.com/apply/jobXYZ"
    fields_non_target, nav_elements_non_target = extract_and_ground_page_elements(non_target_url_test)
    print("\n--- Results for Non-Target URL ---")
    print(f"  Form Fields Found: {len(fields_non_target)}")
    print(f"  Navigation Elements Found: {len(nav_elements_non_target)}")


    print("\n--- MVP Visual Linker Demo Finished ---")
