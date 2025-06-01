import re
import uuid
from typing import List, Optional, Dict, Any

# Assuming ai_core_data_structures.py is in the same directory or accessible in PYTHONPATH
from ai_core_data_structures import IdentifiedFormField, VisualLocation, PredictedFieldType

def ground_visual_elements_to_dom(
    identified_fields: List[IdentifiedFormField],
    dom_structure_str: str,
    page_url: str,
) -> List[IdentifiedFormField]:
    """
    Simulates grounding visually identified form elements to their DOM representations.
    """
    print(f"VisualGroundingModule: Attempting to ground {len(identified_fields)} fields for URL: {page_url}")
    print(f"VisualGroundingModule: DOM structure (first 200 chars): {dom_structure_str[:200]}...")

    updated_fields: List[IdentifiedFormField] = []

    for field in identified_fields:
        print(f"\nVisualGroundingModule: Processing field: '{field.visual_label_text}' (Type: {field.field_type_predicted.name})")
        updated_field = field # Start with the original field data

        # Simulate grounding logic
        # Strategy 1: Text Content Matching (for labels and elements with text)
        if field.visual_label_text:
            # Escape special characters for regex
            escaped_label_text = re.escape(field.visual_label_text)

            if field.field_type_predicted == PredictedFieldType.BUTTON:
                # For buttons, the label text is often the button's text content
                # Try to find <button>text</button> or <input type="submit/button" value="text">
                button_pattern_text = f"<button[^>]*>.*{escaped_label_text}.*</button>"
                button_pattern_input = f"<input[^>]+type=['\"](submit|button)['\"][^>]+value=['\"]{escaped_label_text}['\"][^>]*>"

                match_button_text = re.search(button_pattern_text, dom_structure_str, re.IGNORECASE)
                match_button_input = re.search(button_pattern_input, dom_structure_str, re.IGNORECASE)

                if match_button_text:
                    updated_field.dom_path_primary = f"//button[contains(.,'{field.visual_label_text}')]"
                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.1)
                    print(f"  Found button by text: {updated_field.dom_path_primary}")
                elif match_button_input:
                    input_type = match_button_input.group(1)
                    updated_field.dom_path_primary = f"//input[@type='{input_type}' and @value='{field.visual_label_text}']"
                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.1)
                    print(f"  Found input button by value: {updated_field.dom_path_primary}")
                else:
                    print(f"  Could not ground button '{field.visual_label_text}' by text/value.")

            else: # For non-button fields, look for labels
                label_pattern_for = f"<label[^>]+for=['\"]([^'\"]+)['\"][^>]*>.*{escaped_label_text}.*</label>"
                label_pattern_general = f"<label[^>]*>.*{escaped_label_text}.*</label>"

                match_label_for = re.search(label_pattern_for, dom_structure_str, re.IGNORECASE)
                match_label_general = None

                if match_label_for:
                    label_for_id = match_label_for.group(1)
                    updated_field.dom_path_label = f"//label[@for='{label_for_id}']"
                    updated_field.confidence_score = min(1.0, field.confidence_score + 0.05)
                    print(f"  Found label by text with 'for' attribute: {updated_field.dom_path_label}")

                    # Strategy 2: Proximity and Element Type (using for/id link)
                    # Try to find the input element linked by the label's 'for' attribute
                    # This is a simplified assumption for simulation
                    if field.field_type_predicted == PredictedFieldType.TEXT_INPUT:
                        # Broaden search for various text-like inputs
                        input_tag_pattern = f"<(input|textarea|select)[^>]+id=['\"]{label_for_id}['\"][^>]*>"
                    elif field.field_type_predicted == PredictedFieldType.CHECKBOX:
                        input_tag_pattern = f"<input[^>]+type=['\"]checkbox['\"][^>]+id=['\"]{label_for_id}['\"][^>]*>"
                    else: # General case if type is not specifically handled
                        input_tag_pattern = f"<(input|textarea|select)[^>]+id=['\"]{label_for_id}['\"][^>]*>"

                    match_input_by_id = re.search(input_tag_pattern, dom_structure_str, re.IGNORECASE)
                    if match_input_by_id:
                        tag_name = match_input_by_id.group(1)
                        updated_field.dom_path_primary = f"//{tag_name}[@id='{label_for_id}']"
                        updated_field.confidence_score = min(1.0, updated_field.confidence_score + 0.1)
                        print(f"  Found input by id '{label_for_id}' from label: {updated_field.dom_path_primary}")
                    else:
                        print(f"  Could not find input with id '{label_for_id}' linked by label.")
                else:
                    match_label_general = re.search(label_pattern_general, dom_structure_str, re.IGNORECASE)
                    if match_label_general:
                        # This is a weaker match, could be improved with proximity logic in a real system
                        updated_field.dom_path_label = f"//label[contains(.,'{field.visual_label_text}')]"
                        updated_field.confidence_score = min(1.0, field.confidence_score + 0.02) # Slightly less confidence
                        print(f"  Found label by general text match: {updated_field.dom_path_label}")
                        # Simulate finding an adjacent input (very simplified)
                        # In reality, this would involve analyzing DOM structure (siblings, parent-child)
                        # and potentially rendered positions relative to the label's bounding box.
                        # For this simulation, we'll just look for an input *near* the label text in the string.
                        # This is NOT robust HTML parsing.
                        search_start_index = match_label_general.end()
                        dom_snippet_after_label = dom_structure_str[search_start_index : search_start_index + 200] # Search in a small window after label

                        if field.field_type_predicted == PredictedFieldType.TEXT_INPUT:
                            input_match = re.search(r"<input[^>]+type=['\"](text|email|password|search|tel|url)['\"][^>]*name=['\"]([^'\"]+)['\"]", dom_snippet_after_label, re.IGNORECASE)
                            if input_match:
                                input_name = input_match.group(2)
                                updated_field.dom_path_primary = f"//input[@name='{input_name}']" # Example path
                                updated_field.confidence_score = min(1.0, updated_field.confidence_score + 0.05)
                                print(f"  Simulated adjacent input found by name: {updated_field.dom_path_primary}")
                        elif field.field_type_predicted == PredictedFieldType.CHECKBOX:
                             # Checkboxes might be before or after label, this only checks after
                            input_match = re.search(r"<input[^>]+type=['\"]checkbox['\"][^>]*name=['\"]([^'\"]+)['\"]", dom_snippet_after_label, re.IGNORECASE)
                            if input_match:
                                input_name = input_match.group(1)
                                updated_field.dom_path_primary = f"//input[@type='checkbox' and @name='{input_name}']"
                                updated_field.confidence_score = min(1.0, updated_field.confidence_score + 0.05)
                                print(f"  Simulated adjacent checkbox found by name: {updated_field.dom_path_primary}")


        # Strategy 3: Using predicted_field_type as a hint (if no strong label match or for elements without visible labels)
        # This part would be more complex, potentially looking for elements matching the type
        # within the field.visual_location (which we can't truly simulate here without rendering).
        # For now, if dom_path_primary is still empty, we just log it.
        if not updated_field.dom_path_primary and not updated_field.dom_path_label:
             print(f"  No strong DOM grounding found for '{field.visual_label_text}' based on text or type hints.")


        if not updated_field.dom_path_primary:
            print(f"  Warning: Could not determine dom_path_primary for '{field.visual_label_text}'.")
        if field.field_type_predicted != PredictedFieldType.BUTTON and not updated_field.dom_path_label:
             print(f"  Warning: Could not determine dom_path_label for '{field.visual_label_text}'.")


        updated_fields.append(updated_field)

    print(f"\nVisualGroundingModule: Grounding process completed for {len(updated_fields)} fields.")
    return updated_fields


if __name__ == "__main__":
    print("--- Running Visual Grounding Module Demo ---")

    # Sample IdentifiedFormField objects (output from Visual Perception Module)
    sample_fields_from_visual_module: List[IdentifiedFormField] = [
        IdentifiedFormField(
            id="vis_1", visual_label_text="First Name",
            visual_location=VisualLocation(x=100, y=50, width=200, height=30),
            field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.9, dom_path_primary="", dom_path_label="", semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_2", visual_label_text="Email Address",
            visual_location=VisualLocation(x=100, y=100, width=200, height=30),
            field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.88, dom_path_primary="", dom_path_label="", semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_3", visual_label_text="Subscribe to newsletter",
            visual_location=VisualLocation(x=100, y=150, width=20, height=20), # Checkbox itself
            field_type_predicted=PredictedFieldType.CHECKBOX,
            confidence_score=0.85, dom_path_primary="", dom_path_label="", semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_4", visual_label_text="Submit Application",
            visual_location=VisualLocation(x=100, y=200, width=150, height=40),
            field_type_predicted=PredictedFieldType.BUTTON,
            confidence_score=0.92, dom_path_primary="", dom_path_label="", semantic_meaning_predicted=""
        ),
         IdentifiedFormField( # Field with no direct label in this simple DOM
            id="vis_5", visual_label_text="Phone Number",
            visual_location=VisualLocation(x=100, y=250, width=200, height=30),
            field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.8, dom_path_primary="", dom_path_label="", semantic_meaning_predicted=""
        )
    ]

    # Sample DOM structure string
    sample_dom_str = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Form</title></head>
    <body>
      <h1>Application Form</h1>
      <form>
        <div>
          <label for="fname">First Name</label>
          <input type="text" id="fname" name="firstname">
        </div>
        <div>
          <p>Your Contact Information</p>
          <label>Email Address</label>
          <input type="email" name="email_contact" class="user-input">
        </div>
        <div class="checkbox-area">
          <input type="checkbox" id="subscribe_news" name="subscribe">
          <label for="subscribe_news" class="inline-label">Subscribe to newsletter</label>
        </div>
        <div style="margin-top: 20px;">
            <input type="tel" name="phone_number_field" placeholder="Your Phone">
        </div>
        <button type="submit" onclick="submitForm()">Submit Application</button>
        <input type="button" value="Cancel">
      </form>
    </body>
    </html>
    """

    print(f"\nInitial fields (before grounding):")
    for field in sample_fields_from_visual_module:
        print(f"  ID: {field.id}, Label: '{field.visual_label_text}', PrimaryPath: '{field.dom_path_primary}', LabelPath: '{field.dom_path_label}', Confidence: {field.confidence_score:.2f}")

    grounded_fields = ground_visual_elements_to_dom(
        identified_fields=sample_fields_from_visual_module,
        dom_structure_str=sample_dom_str,
        page_url="https://example.com/form"
    )

    print(f"\nGrounded fields:")
    for field in grounded_fields:
        print(f"  ID: {field.id}, Label: '{field.visual_label_text}', Type: {field.field_type_predicted.name}")
        print(f"    PrimaryPath: '{field.dom_path_primary}', LabelPath: '{field.dom_path_label}', Confidence: {field.confidence_score:.2f}")

    print("\n--- Visual Grounding Module Demo Finished ---")
