# app/ai_core/live_visual_grounder.py
import logging
import math
import difflib # For text similarity
import uuid # Only if we need to generate new IDs, typically not in grounding
from typing import List, Dict, Union, Optional, Any, Tuple

from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    NavigationElement,
    VisualLocation,
    PredictedFieldType,
    NavigationActionType # For type checking if needed
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- Constants for Heuristics ---
# Intersection over Union thresholds
IOU_THRESHOLD_STRONG_MATCH = 0.5  # Minimum IoU for a match to be considered decent with other signals
IOU_THRESHOLD_GEOMETRIC_FALLBACK = 0.6 # Minimum IoU for a pure geometric fallback (needs to be higher)
IOU_THRESHOLD_PROXIMITY_CANDIDATE = 0.1 # Minimum IoU to even consider an element as a candidate in proximity search

# Scoring weights for Geometric Proximity + Filtered Text Matching
W_IOU_PROXIMITY = 0.6
W_TEXT_SIMILARITY_PROXIMITY = 0.4

# Scoring weights for Accessibility-Enhanced Text Matching (conceptual)
W_ARIA_LABEL_SIMILARITY = 0.5 # If direct aria-label match
W_LINKED_LABEL_SIMILARITY = 0.5 # If label element text matches (for linked labels)

# Confidence score thresholds (optional, for categorizing match strength)
CONF_THRESHOLD_HIGH = 0.75
CONF_THRESHOLD_MEDIUM = 0.5

# --- Helper Functions ---

def _calculate_iou(boxA: VisualLocation, boxB: VisualLocation) -> float:
    """Calculates Intersection over Union (IoU) for two VisualLocation objects."""
    # Determine the (x, y)-coordinates of the intersection rectangle
    xA = max(boxA.x, boxB.x)
    yA = max(boxA.y, boxB.y)
    xB = min(boxA.x + boxA.width, boxB.x + boxB.width)
    yB = min(boxA.y + boxA.height, boxB.y + boxB.height)

    # Compute the area of intersection rectangle
    interArea = max(0, xB - xA) * max(0, yB - yA)

    if interArea == 0:
        return 0.0

    # Compute the area of both the prediction and ground-truth rectangles
    boxAArea = boxA.width * boxA.height
    boxBArea = boxB.width * boxB.height

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

def _calculate_center_distance(boxA: VisualLocation, boxB: VisualLocation) -> float:
    """Calculates Euclidean distance between the center points of two VisualLocation objects."""
    centerAx = boxA.x + boxA.width / 2
    centerAy = boxA.y + boxA.height / 2
    centerBx = boxB.x + boxB.width / 2
    centerBy = boxB.y + boxB.height / 2
    return math.sqrt((centerAx - centerBx)**2 + (centerAy - centerBy)**2)

def _text_similarity(text1: Optional[str], text2: Optional[str]) -> float:
    """Calculates similarity score (0.0 to 1.0) between two strings."""
    if not text1 or not text2:
        return 0.0
    # TODO: Consider using a more advanced library like fuzzywuzzy for better results.
    return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def _get_dom_element_text_candidates(dom_element_details: Dict[str, Any]) -> List[str]:
    """Extracts potential text sources from a DOM element's details dictionary."""
    texts: List[str] = []
    attributes = dom_element_details.get("attributes", {})

    # Order of preference can matter
    if dom_element_details.get("text_content"): texts.append(dom_element_details["text_content"])
    if attributes.get("aria-label"): texts.append(attributes["aria-label"])
    if attributes.get("value"): texts.append(attributes["value"])
    if attributes.get("placeholder"): texts.append(attributes["placeholder"])
    if attributes.get("id"): texts.append(attributes["id"]) # Less likely a direct match, but can be useful
    if attributes.get("name"): texts.append(attributes["name"]) # Similar to id
    # For buttons, innerText or value are often primary
    if dom_element_details.get("tag_name") == "input" and attributes.get("type") in ["button", "submit", "reset"]:
        if attributes.get("value"): texts.insert(0, attributes["value"]) # Prioritize value for input buttons

    return [text.strip().lower() for text in texts if text and text.strip()]

def _are_types_compatible(
    predicted_type: PredictedFieldType,
    dom_tag: str,
    dom_type_attr: Optional[str]
) -> bool:
    """Checks if the LLM's PredictedFieldType is compatible with the DOM element's tag and type attribute."""
    dom_tag_lower = dom_tag.lower()
    dom_type_attr_lower = (dom_type_attr or "").lower()

    if predicted_type == PredictedFieldType.TEXT_INPUT:
        return (dom_tag_lower == "input" and dom_type_attr_lower in ["text", "email", "password", "search", "tel", "url", "number", "date", "datetime-local", "month", "week", "time", ""]) or \
               dom_tag_lower == "textarea"
    elif predicted_type == PredictedFieldType.EMAIL_INPUT:
        return dom_tag_lower == "input" and dom_type_attr_lower == "email"
    elif predicted_type == PredictedFieldType.PHONE_INPUT:
        return dom_tag_lower == "input" and dom_type_attr_lower == "tel"
    elif predicted_type == PredictedFieldType.TEXTAREA:
        return dom_tag_lower == "textarea"
    elif predicted_type == PredictedFieldType.CHECKBOX:
        return dom_tag_lower == "input" and dom_type_attr_lower == "checkbox"
    elif predicted_type == PredictedFieldType.RADIO_BUTTON:
        return dom_tag_lower == "input" and dom_type_attr_lower == "radio"
    elif predicted_type == PredictedFieldType.DROPDOWN:
        return dom_tag_lower == "select"
    elif predicted_type == PredictedFieldType.BUTTON:
        return dom_tag_lower == "button" or \
               (dom_tag_lower == "input" and dom_type_attr_lower in ["button", "submit", "reset", "image"]) or \
               dom_element_details.get("attributes", {}).get("role") == "button" # Check role for button too
    elif predicted_type == PredictedFieldType.OTHER_INPUT: # Catch-all for other input types
        return dom_tag_lower == "input"
    elif predicted_type == PredictedFieldType.UNKNOWN: # If LLM is unsure, be more lenient
        return True
    return False


# --- Main Grounding Function ---
def ground_visual_elements(
    identified_elements_from_vision: List[Union[IdentifiedFormField, NavigationElement]],
    actual_dom_elements_details: List[Dict[str, Any]]
) -> List[Union[IdentifiedFormField, NavigationElement]]:
    """
    Attempts to ground visually identified elements to their corresponding DOM elements
    using a hybrid heuristic approach.
    Updates the `dom_path_primary` and `confidence_score` (for grounding) of the input elements.
    """
    logging.info(f"Starting visual grounding for {len(identified_elements_from_vision)} visual elements against {len(actual_dom_elements_details)} DOM elements.")

    # Create a mutable copy to update, or update in-place if preferred
    grounded_elements: List[Union[IdentifiedFormField, NavigationElement]] = []

    for vis_idx, vis_elem in enumerate(identified_elements_from_vision):
        best_match_info = {"dom_elem_index": -1, "score": 0.0, "method": "None"}
        vis_elem_bbox = vis_elem.visual_location # Already a VisualLocation object

        logging.debug(f"\nAttempting to ground visual element {vis_idx+1}/{len(identified_elements_from_vision)}: Label='{vis_elem.visual_label_text}', Type={vis_elem.field_type_predicted.name if isinstance(vis_elem, IdentifiedFormField) else vis_elem.action_type_predicted.name}, BBox={vis_elem_bbox}")

        for dom_idx, dom_elem in enumerate(actual_dom_elements_details):
            if not dom_elem.get("is_visible", False): # Skip non-visible DOM elements
                continue

            dom_elem_bbox = VisualLocation(
                x=dom_elem['location_x'], y=dom_elem['location_y'],
                width=dom_elem['width'], height=dom_elem['height']
            )

            # Basic type compatibility check early on
            predicted_type = vis_elem.field_type_predicted if isinstance(vis_elem, IdentifiedFormField) else PredictedFieldType.BUTTON # Treat NavElement as Button for type check
            if not _are_types_compatible(predicted_type, dom_elem['tag_name'], dom_elem['attributes'].get('type')):
                # logging.debug(f"  DOM Elem {dom_idx} ('{dom_elem.get('attributes',{}).get('name', dom_elem['tag_name'])}'): Type incompatible.")
                continue

            current_score = 0.0
            current_method = "None"

            # A. Accessibility-Enhanced Text Matching (Simplified for MVP)
            # Prioritize direct matches on aria-label or strong text candidates if label is very close
            # This is a conceptual placeholder; full AT parsing would be more robust.
            dom_texts = _get_dom_element_text_candidates(dom_elem)
            aria_label_sim = 0.0
            if dom_elem.get("attributes", {}).get("aria-label"):
                aria_label_sim = _text_similarity(vis_elem.visual_label_text, dom_elem["attributes"]["aria-label"])

            # Consider a direct text match from prominent candidates if label is very close or IoU is high
            # This overlaps with heuristic B but gives a bonus if aria-label or primary text is a strong match
            best_candidate_text_sim = 0.0
            if vis_elem.visual_label_text:
                for candidate_text in dom_texts:
                    best_candidate_text_sim = max(best_candidate_text_sim, _text_similarity(vis_elem.visual_label_text, candidate_text))

            # Heuristic A Score (Conceptual)
            # If aria_label_sim is very high, or best_candidate_text_sim is very high AND geometric proximity is good
            # For MVP, let's keep it simpler and integrate this into Heuristic B's scoring more directly.
            # A high score here could be: score = max(aria_label_sim, best_candidate_text_sim) * 0.8 (if geometrically plausible)
            # For now, these text similarities will be used in Heuristic B.

            # B. Geometric Proximity + Filtered Text Matching
            iou = _calculate_iou(vis_elem_bbox, dom_elem_bbox)

            # Use label_visual_location for proximity if available and distinct, otherwise element's own bbox center
            # This is more complex; for MVP, primarily use vis_elem_bbox for IoU and center distance.
            # dist = _calculate_center_distance(vis_elem_bbox, dom_elem_bbox)
            # proximity_score = 1.0 / (1.0 + dist / 100.0) # Normalize distance, 100px is arbitrary scale factor

            if iou > IOU_THRESHOLD_PROXIMITY_CANDIDATE: # Must have some overlap to be a candidate via this method
                text_sim_score = best_candidate_text_sim # Calculated above

                # Combine IoU and text similarity
                # If vis_elem.visual_label_text is empty or weak, text_sim_score will be low, relying more on IoU.
                current_score = (iou * W_IOU_PROXIMITY) + (text_sim_score * W_TEXT_SIMILARITY_PROXIMITY)
                current_method = "Geometric+Text"
                # logging.debug(f"  DOM Elem {dom_idx}: IoU={iou:.2f}, TextSim={text_sim_score:.2f}, CombinedScore={current_score:.2f} ({current_method})")

                if current_score > best_match_info['score']:
                    best_match_info = {"dom_elem_index": dom_idx, "score": current_score, "method": current_method}

            # D. Fallback to Pure Geometric Matching (if no strong text-enhanced match found yet)
            # Only consider if the current best score is still low (e.g. indicating weak text match)
            # and IoU is high, and types are compatible (already checked).
            if best_match_info['score'] < CONF_THRESHOLD_MEDIUM and iou > IOU_THRESHOLD_GEOMETRIC_FALLBACK:
                current_score_geom_fallback = iou * 0.7 # Weight purely geometric matches a bit lower than combined
                current_method_geom_fallback = "GeometricFallback"
                # logging.debug(f"  DOM Elem {dom_idx}: IoU={iou:.2f}, Score={current_score_geom_fallback:.2f} ({current_method_geom_fallback})")
                if current_score_geom_fallback > best_match_info['score']:
                    best_match_info = {"dom_elem_index": dom_idx, "score": current_score_geom_fallback, "method": current_method_geom_fallback}

        # Post-Loop for vis_elem: Update the visual element with grounding info
        cloned_vis_elem = vis_elem.copy() # Assuming a .copy() method or manual deepcopy for dataclasses
                                        # For now, modify in place and add to new list.
                                        # If it's a dataclass, direct assignment works if not frozen.
                                        # Let's create new objects to be safe if original list items are from elsewhere.

        final_element_to_add: Union[IdentifiedFormField, NavigationElement]
        if isinstance(vis_elem, IdentifiedFormField):
            final_element_to_add = IdentifiedFormField(**vis_elem.__dict__) # Recreate from dict for a true copy
        elif isinstance(vis_elem, NavigationElement):
            final_element_to_add = NavigationElement(**vis_elem.__dict__)
        else:
            logging.warning(f"Unknown element type for visual element: {vis_elem}")
            continue # Should not happen

        if best_match_info['dom_elem_index'] != -1:
            matched_dom_elem = actual_dom_elements_details[best_match_info['dom_elem_index']]
            final_element_to_add.dom_path_primary = matched_dom_elem['xpath']
            # Store grounding confidence, not overall confidence. The original confidence was from visual perception.
            final_element_to_add.confidence_score = round(best_match_info['score'], 3)

            # Conceptual: dom_path_label would require finding the <label> element associated with matched_dom_elem if any.
            # This is complex. For now, if matched_dom_elem itself is a label for another input, this isn't handled here.
            # If vis_elem had a label_visual_location, and we found a DOM label element that matches it, we could set it.
            # For simplicity, this is skipped in this MVP grounder.

            logging.info(f"Successfully grounded: '{final_element_to_add.visual_label_text}' (Type: {final_element_to_add.field_type_predicted.name if isinstance(final_element_to_add, IdentifiedFormField) else final_element_to_add.action_type_predicted.name if isinstance(final_element_to_add, NavigationElement) else 'N/A'}) "
                         f"to DOM XPath: '{final_element_to_add.dom_path_primary}' "
                         f"with score: {final_element_to_add.confidence_score:.2f} (Method: {best_match_info['method']})")
        else:
            final_element_to_add.dom_path_primary = None # Explicitly set to None
            final_element_to_add.confidence_score = 0.0 # Grounding confidence
            logging.warning(f"Could not ground visual element: '{final_element_to_add.visual_label_text}' (Type: {final_element_to_add.field_type_predicted.name if isinstance(final_element_to_add, IdentifiedFormField) else final_element_to_add.action_type_predicted.name if isinstance(final_element_to_add, NavigationElement) else 'N/A'})")

        grounded_elements.append(final_element_to_add)

    return grounded_elements


if __name__ == '__main__':
    logging.info("--- Live Visual Grounder Demo ---")

    # 1. Sample Visual Elements (simulating output from live_visual_perception.parse_llm_output_to_identified_elements)
    vis_elements: List[Union[IdentifiedFormField, NavigationElement]] = [
        IdentifiedFormField(
            id="vis_fname", visual_label_text="First Name",
            visual_location=VisualLocation(x=50, y=50, width=100, height=20), # Label bbox
            label_visual_location=VisualLocation(x=50, y=50, width=100, height=20),
            element_visual_location=VisualLocation(x=160, y=48, width=200, height=25), # Actual field bbox
            field_type_predicted=PredictedFieldType.TEXT_INPUT, confidence_score=0.85 # Initial visual confidence
        ),
        IdentifiedFormField(
            id="vis_email", visual_label_text="Your Email Address",
            visual_location=VisualLocation(x=50, y=100, width=150, height=20), # Label bbox
            label_visual_location=VisualLocation(x=50, y=100, width=150, height=20),
            element_visual_location=VisualLocation(x=210, y=98, width=200, height=25),
            field_type_predicted=PredictedFieldType.EMAIL_INPUT, confidence_score=0.88
        ),
        NavigationElement(
            id="vis_submit", visual_label_text="Submit Now",
            visual_location=VisualLocation(x=150, y=150, width=120, height=30), # Button bbox
            action_type_predicted=NavigationActionType.SUBMIT_FORM, confidence_score=0.9
        ),
        IdentifiedFormField( # An element that might not have a clear DOM match or too ambiguous
            id="vis_comment", visual_label_text="Optional Comment",
            visual_location=VisualLocation(x=50, y=200, width=130, height=20),
            element_visual_location=VisualLocation(x=190, y=198, width=200, height=50),
            field_type_predicted=PredictedFieldType.TEXTAREA, confidence_score=0.7
        )
    ]
    # Correcting visual_location to be the element's bbox as per typical use
    vis_elements[0].visual_location = vis_elements[0].element_visual_location
    vis_elements[1].visual_location = vis_elements[1].element_visual_location
    # For NavElement, visual_location is already the button itself.
    vis_elements[3].visual_location = vis_elements[3].element_visual_location


    # 2. Sample DOM Element Details (simulating output from mvp_selenium_wrapper.get_all_interactable_elements_details)
    dom_elements_details: List[Dict[str, Any]] = [
        { # Matches vis_fname
            "xpath": "//form/div[1]/input", "tag_name": "input", "text_content": "",
            "location_x": 158, "location_y": 47, "width": 202, "height": 26, "is_visible": True,
            "attributes": {"id": "firstNameField", "name": "fname", "type": "text", "placeholder": "Enter First Name"}
        },
        { # Matches vis_email (good textual match with placeholder and name)
            "xpath": "//form/div[2]/input", "tag_name": "input", "text_content": "",
            "location_x": 208, "location_y": 97, "width": 203, "height": 27, "is_visible": True,
            "attributes": {"id": "emailAddr", "name": "email_address_field", "type": "email", "aria-label": "Your Email Address"}
        },
        { # Matches vis_submit (good text and type match)
            "xpath": "//form/button[1]", "tag_name": "button", "text_content": "Submit Now",
            "location_x": 148, "location_y": 149, "width": 122, "height": 32, "is_visible": True,
            "attributes": {"id": "submit_button", "type": "submit"}
        },
        { # A decoy input field, geometrically close to "First Name" label but text is different
            "xpath": "//form/input[@id='other']", "tag_name": "input", "text_content": "",
            "location_x": 50, "location_y": 75, "width": 100, "height": 25, "is_visible": True,
            "attributes": {"id": "otherInput", "name": "other", "type": "text", "placeholder": "Other info"}
        },
        { # A textarea that could match vis_comment, but text is slightly off.
            "xpath": "//form/textarea[1]", "tag_name": "textarea", "text_content": "",
            "location_x": 192, "location_y": 199, "width": 198, "height": 48, "is_visible": True,
            "attributes": {"id": "commentBox", "name": "user_comment", "aria-label": "Additional comments"}
        }
    ]

    logging.info(f"\n--- Input Visual Elements ({len(vis_elements)}) ---")
    for i, elem in enumerate(vis_elements):
        logging.info(f"  {i+1}. Label: '{elem.visual_label_text}', Type: {elem.field_type_predicted.name if isinstance(elem, IdentifiedFormField) else elem.action_type_predicted.name}, VisLocation: {elem.visual_location}")

    logging.info(f"\n--- Input DOM Elements ({len(dom_elements_details)}) ---")
    for i, elem_details in enumerate(dom_elements_details):
        logging.info(f"  {i+1}. XPath: {elem_details['xpath']}, Tag: {elem_details['tag_name']}, Attrs: {elem_details['attributes'].get('name','N/A')}, Text: '{elem_details.get('text_content','N/A')}', Loc: ({elem_details['location_x']},{elem_details['location_y']})")


    # 3. Perform Grounding
    grounded_results = ground_visual_elements(vis_elements, dom_elements_details)

    logging.info("\n--- Grounding Results ---")
    for i, elem in enumerate(grounded_results):
        log_prefix = f"  Visual Element {i+1} (Label: '{elem.visual_label_text}', OrigType: {elem.field_type_predicted.name if isinstance(elem, IdentifiedFormField) else elem.action_type_predicted.name}):"
        if elem.dom_path_primary:
            logging.info(f"{log_prefix} Grounded to XPath: '{elem.dom_path_primary}' with confidence: {elem.confidence_score:.3f}")
        else:
            logging.warning(f"{log_prefix} Could NOT be grounded. Final confidence: {elem.confidence_score:.3f}")

    logging.info("\n--- Live Visual Grounder Demo Finished ---")
