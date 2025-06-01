# app/ai_core/live_semantic_matcher.py
import os
import json
import logging
import re
from typing import List, Dict, Optional, Any
import functools # For lru_cache
import io # For PIL Image in demo if needed, not directly here

import google.generativeai as genai
# from PIL import Image # Not directly needed here, but good for consistency if other modules use it

from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    PredictedFieldType,
    VisualLocation # For demo
)
# For copying dataclass instances
from dataclasses import replace as dataclass_replace


# --- Configuration & Constants ---
API_KEY_ENV_VAR = "GEMINI_API_KEY" # Consistent with live_visual_perception
SEMANTIC_SCHEMA_PATH = "app/common/data_schemas/semantic_field_schema.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

_gemini_configured_semantic = False

# --- Helper Functions ---
def _configure_gemini_semantic(api_key: str) -> bool:
    """Configures the Gemini API for semantic matching. Ensures it's called only once effectively."""
    global _gemini_configured_semantic
    if _gemini_configured_semantic:
        return True
    if not api_key:
        logging.error("SemanticMatcher: Gemini API key is missing.")
        return False
    try:
        genai.configure(api_key=api_key)
        _gemini_configured_semantic = True
        logging.info("SemanticMatcher: Gemini API configured successfully.")
        return True
    except Exception as e:
        logging.error(f"SemanticMatcher: Failed to configure Gemini API: {e}")
        return False

@functools.lru_cache(maxsize=1)
def _load_target_semantic_keys() -> List[str]:
    """
    Loads the semantic field schema and returns the flat list of target_semantic_keys.
    Uses LRU cache to load only once.
    """
    try:
        with open(SEMANTIC_SCHEMA_PATH, 'r') as f:
            schema_data = json.load(f)
        target_keys = schema_data.get("target_semantic_keys")
        if not target_keys or not isinstance(target_keys, list):
            logging.error(f"SemanticMatcher: '{SEMANTIC_SCHEMA_PATH}' is missing 'target_semantic_keys' list or it's invalid.")
            return []
        logging.info(f"SemanticMatcher: Loaded {len(target_keys)} target semantic keys from schema.")
        return target_keys
    except FileNotFoundError:
        logging.error(f"SemanticMatcher: Semantic schema file not found at '{SEMANTIC_SCHEMA_PATH}'.")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"SemanticMatcher: Error decoding JSON from schema file '{SEMANTIC_SCHEMA_PATH}': {e}")
        return []
    except Exception as e:
        logging.error(f"SemanticMatcher: An unexpected error occurred loading schema '{SEMANTIC_SCHEMA_PATH}': {e}")
        return []

# --- Core Semantic Matching Function ---
def get_semantic_match_for_field(
    visual_label: str,
    predicted_type: PredictedFieldType,
    target_keys: List[str],
    html_attributes: Optional[Dict[str, str]] = None, # Added from research doc
    additional_context: Optional[str] = None,
    live_llm_call: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Gets a semantic match for a given field using an LLM.
    """
    global _gemini_configured_semantic
    if live_llm_call and not _gemini_configured_semantic:
        api_key = os.getenv(API_KEY_ENV_VAR)
        if not api_key:
            logging.error(f"SemanticMatcher: Live LLM call requested, but API key env var '{API_KEY_ENV_VAR}' not found.")
            return None
        if not _configure_gemini_semantic(api_key):
            logging.error("SemanticMatcher: Live LLM call requested, but Gemini API configuration failed.")
            return None

    llm_output_text: Optional[str] = None

    if live_llm_call:
        logging.info(f"SemanticMatcher: Attempting LIVE call to Gemini Pro for label: '{visual_label}'")
        try:
            model = genai.GenerativeModel('gemini-pro') # Text model

            # Constructing the prompt based on research
            prompt_lines = [
                "You are an expert AI system that maps web form field information to a predefined list of semantic categories.",
                "Your task is to analyze the provided information about a form field and choose the single most appropriate semantic category from the 'Predefined Semantic Categories' list.",
                "If no category from the list is a good fit, you MUST return \"system_internal.other_unspecified_field\" as the semantic_key.",
                "\nField Information:",
                f"- Visual Label: \"{visual_label}\"",
                f"- Predicted Field Type: \"{predicted_type.value if predicted_type else 'unknown'}\""
            ]
            if html_attributes:
                prompt_lines.append("- HTML Attributes (if available and relevant):")
                if html_attributes.get("id"): prompt_lines.append(f"  - id: \"{html_attributes['id']}\"")
                if html_attributes.get("name"): prompt_lines.append(f"  - name: \"{html_attributes['name']}\"")
                if html_attributes.get("placeholder"): prompt_lines.append(f"  - placeholder: \"{html_attributes['placeholder']}\"")
                if html_attributes.get("aria-label"): prompt_lines.append(f"  - aria-label: \"{html_attributes['aria-label']}\"")

            if additional_context:
                prompt_lines.append(f"\nAdditional Context:\n{additional_context}")

            prompt_lines.append("\nPredefined Semantic Categories:")
            # Present keys in a way that's easy for LLM to parse, e.g., JSON array string or bullet points
            prompt_lines.append(json.dumps(target_keys, indent=2))

            prompt_lines.append("\nRespond with a single JSON object containing two keys: 'semantic_key' and 'confidence_score'.")
            prompt_lines.append("The 'semantic_key' MUST be one of the 'Predefined Semantic Categories' or 'system_internal.other_unspecified_field'.")
            prompt_lines.append("The 'confidence_score' must be a float between 0.0 and 1.0, representing your confidence in the mapping.")
            prompt_lines.append("Ensure your entire response is ONLY this JSON object.")

            prompt_string = "\n".join(prompt_lines)
            logging.debug(f"SemanticMatcher: Prompt for LLM:\n{prompt_string}")

            response = model.generate_content(prompt_string)

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logging.warning(f"SemanticMatcher: Gemini API call blocked for label '{visual_label}'. Reason: {response.prompt_feedback.block_reason}")
                return None

            llm_output_text = response.text
            logging.info(f"SemanticMatcher: Received response from Gemini API for label '{visual_label}'.")
            logging.debug(f"LLM raw output: {llm_output_text}")

        except Exception as e_api:
            logging.error(f"SemanticMatcher: Error during Gemini API call for label '{visual_label}': {e_api}")
            return None
    else: # Simulated response
        logging.info(f"SemanticMatcher: Using SIMULATED LLM response for label: '{visual_label}' (live_llm_call=False).")
        # Simplified simulation: chooses from a few hardcoded cases
        sim_label_lower = visual_label.lower()
        if "first name" in sim_label_lower or "given name" in sim_label_lower :
            llm_output_text = '```json\n{"semantic_key": "user.personal_info.first_name", "confidence_score": 0.95}\n```'
        elif "email" in sim_label_lower:
            llm_output_text = '```json\n{"semantic_key": "user.contact_info.email_primary", "confidence_score": 0.9}\n```'
        elif "motivation" in sim_label_lower and predicted_type == PredictedFieldType.TEXTAREA:
            llm_output_text = '```json\n{"semantic_key": "application.custom_question.generic_response_1", "confidence_score": 0.75}\n```'
        elif "zip" in sim_label_lower or "postal" in sim_label_lower:
            llm_output_text = '```json\n{"semantic_key": "user.address_primary.postal_code", "confidence_score": 0.88}\n```'
        elif "resume" in sim_label_lower and predicted_type == PredictedFieldType.FILE_UPLOAD: # Assuming FILE_UPLOAD enum exists
             llm_output_text = '```json\n{"semantic_key": "user.resume_url", "confidence_score": 0.8}\n```' # Map to URL if it's an upload field
        elif "country" in sim_label_lower and predicted_type == PredictedFieldType.DROPDOWN:
             llm_output_text = '```json\n{"semantic_key": "user.address_primary.country", "confidence_score": 0.82}\n```'
        else:
            llm_output_text = '```json\n{"semantic_key": "system_internal.other_unspecified_field", "confidence_score": 0.45}\n```'
        logging.debug(f"Simulated LLM output: {llm_output_text}")

    if not llm_output_text:
        logging.warning(f"SemanticMatcher: LLM output text is empty for label '{visual_label}'.")
        return None

    try:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", llm_output_text, re.IGNORECASE)
        json_str: Optional[str] = None
        if match:
            json_str = match.group(1)
            logging.debug(f"SemanticMatcher: Extracted JSON from markdown for label '{visual_label}'.")
        elif llm_output_text.strip().startswith('{') and llm_output_text.strip().endswith('}'):
            json_str = llm_output_text.strip()
            logging.debug(f"SemanticMatcher: Detected direct JSON for label '{visual_label}'.")
        else:
            logging.warning(f"SemanticMatcher: Could not find JSON for label '{visual_label}'. Raw output: {llm_output_text[:200]}")
            return None

        parsed_dict = json.loads(json_str)

        # Validate structure
        if "semantic_key" not in parsed_dict or "confidence_score" not in parsed_dict:
            logging.warning(f"SemanticMatcher: Parsed JSON for label '{visual_label}' is missing required keys 'semantic_key' or 'confidence_score'. Parsed: {parsed_dict}")
            return None
        if parsed_dict.get("semantic_key") and parsed_dict["semantic_key"] not in target_keys:
             # Allow "system_internal.other_unspecified_field" even if not explicitly in short list for some reason
            if parsed_dict["semantic_key"] != "system_internal.other_unspecified_field":
                logging.warning(f"SemanticMatcher: LLM returned semantic_key '{parsed_dict['semantic_key']}' which is not in the target_keys list for label '{visual_label}'.")
                # Optionally, force to "other_unspecified_field" or return None
                # For now, let it pass but with a warning. Or:
                # parsed_dict["semantic_key"] = "system_internal.other_unspecified_field"
                # parsed_dict["confidence_score"] = 0.3 # Lower confidence

        logging.info(f"SemanticMatcher: Successfully parsed LLM output for label '{visual_label}'. Key: {parsed_dict.get('semantic_key')}, Conf: {parsed_dict.get('confidence_score')}")
        return parsed_dict

    except json.JSONDecodeError as e_json:
        logging.error(f"SemanticMatcher: Failed to decode JSON from LLM output for label '{visual_label}': {e_json}. Output: {json_str[:500] if json_str else llm_output_text[:500]}")
        return None
    except Exception as e_parse:
        logging.error(f"SemanticMatcher: Unexpected error parsing LLM output for label '{visual_label}': {e_parse}")
        return None

# --- Orchestration Function ---
def annotate_fields_with_semantic_meaning(
    identified_fields: List[IdentifiedFormField],
    live_llm_call: bool = False,
    # Allow passing html_attributes if available from grounder. For now, not used in this simplified call structure.
    # dom_elements_details: Optional[List[Dict[str,Any]]] = None
) -> List[IdentifiedFormField]:
    """
    Annotates a list of IdentifiedFormField objects with semantic meaning using LLM.
    """
    logging.info(f"SemanticMatcher: Starting semantic annotation for {len(identified_fields)} fields. Live LLM: {live_llm_call}")
    target_keys = _load_target_semantic_keys()
    if not target_keys:
        logging.error("SemanticMatcher: Cannot perform annotation, target semantic keys failed to load.")
        return [dataclass_replace(field, semantic_meaning_predicted=None, confidence_score=0.0) for field in identified_fields]

    annotated_fields: List[IdentifiedFormField] = []
    for field in identified_fields:
        # Create a copy to modify. If IdentifiedFormField is a dataclass:
        copied_field = dataclass_replace(field)

        html_attrs_for_prompt = None # Placeholder. In a full pipeline, this would come from the grounding step for this field.
        # Example: if field.dom_path_primary and dom_elements_details:
        #   matched_dom_elem = next((d for d in dom_elements_details if d.get('xpath') == field.dom_path_primary), None)
        #   if matched_dom_elem: html_attrs_for_prompt = matched_dom_elem.get('attributes')

        if copied_field.visual_label_text and copied_field.visual_label_text.strip():
            match_dict = get_semantic_match_for_field(
                visual_label=copied_field.visual_label_text,
                predicted_type=copied_field.field_type_predicted,
                target_keys=target_keys,
                html_attributes=html_attrs_for_prompt, # Pass if available
                # additional_context= "Example additional context if any", # Pass if available
                live_llm_call=live_llm_call
            )

            if match_dict:
                copied_field.semantic_meaning_predicted = match_dict.get("semantic_key")
                # Set confidence score to LLM's confidence for semantic match.
                # The original confidence was from visual perception/grounding.
                # Consider how to combine these if needed. For now, overwrite with semantic match confidence.
                copied_field.confidence_score = round(float(match_dict.get("confidence_score", 0.0)), 3)
                logging.info(f"  Annotated '{copied_field.visual_label_text}': {copied_field.semantic_meaning_predicted} (Conf: {copied_field.confidence_score})")
            else:
                copied_field.semantic_meaning_predicted = "system_internal.other_unspecified_field" # Default on error
                copied_field.confidence_score = 0.1 # Low confidence for error/no match
                logging.warning(f"  No semantic match from LLM for '{copied_field.visual_label_text}'. Marked as unspecified.")
        else:
            logging.info(f"  Skipping semantic matching for field ID '{copied_field.id}' due to empty visual label.")
            copied_field.semantic_meaning_predicted = "system_internal.other_unspecified_field"
            copied_field.confidence_score = 0.05

        annotated_fields.append(copied_field)

    return annotated_fields

# --- Main Demo Block ---
if __name__ == '__main__':
    logging.info("--- Live Semantic Matcher Demo ---")

    # Check for API key (optional, as demo defaults to simulated)
    api_key_present = os.getenv(API_KEY_ENV_VAR)
    if api_key_present:
        logging.info(f"SemanticMatcher Demo: API Key '{API_KEY_ENV_VAR}' is SET. Live calls can be attempted.")
    else:
        logging.warning(f"SemanticMatcher Demo: API Key '{API_KEY_ENV_VAR}' is NOT SET. Demo will use simulated responses.")

    # Sample IdentifiedFormFields (simulating output from visual perception/grounding)
    sample_fields: List[IdentifiedFormField] = [
        IdentifiedFormField(id="f1", visual_label_text="First Name", field_type_predicted=PredictedFieldType.TEXT_INPUT, visual_location=VisualLocation(0,0,1,1), confidence_score=0.9, dom_path_primary="//input[@id='fname']"),
        IdentifiedFormField(id="f2", visual_label_text="Email address", field_type_predicted=PredictedFieldType.EMAIL_INPUT, visual_location=VisualLocation(0,0,1,1), confidence_score=0.88, dom_path_primary="//input[@id='email']"),
        IdentifiedFormField(id="f3", visual_label_text="Your Cover Letter", field_type_predicted=PredictedFieldType.TEXTAREA, visual_location=VisualLocation(0,0,1,1), confidence_score=0.8, dom_path_primary="//textarea[@id='cover']"), # Should map to custom
        IdentifiedFormField(id="f4", visual_label_text="ZIP / Postal Code", field_type_predicted=PredictedFieldType.TEXT_INPUT, visual_location=VisualLocation(0,0,1,1), confidence_score=0.92, dom_path_primary="//input[@id='zip']"),
        IdentifiedFormField(id="f5", visual_label_text="Please upload your CV/Resume", field_type_predicted=PredictedFieldType.FILE_UPLOAD, visual_location=VisualLocation(0,0,1,1), confidence_score=0.8, dom_path_primary="//input[@type='file']"),
        IdentifiedFormField(id="f6", visual_label_text="Country of Residence", field_type_predicted=PredictedFieldType.DROPDOWN, visual_location=VisualLocation(0,0,1,1), confidence_score=0.85, dom_path_primary="//select[@id='country']"),
        IdentifiedFormField(id="f7", visual_label_text="Some Weird Unmappable Field", field_type_predicted=PredictedFieldType.TEXT_INPUT, visual_location=VisualLocation(0,0,1,1), confidence_score=0.7, dom_path_primary="//input[@id='custom']"),
        IdentifiedFormField(id="f8", visual_label_text="", field_type_predicted=PredictedFieldType.TEXT_INPUT, visual_location=VisualLocation(0,0,1,1), confidence_score=0.7, dom_path_primary="//input[@id='nolabel']") # Empty label
    ]

    logging.info(f"\n--- Annotating fields with SIMULATED LLM responses (live_llm_call=False) ---")
    annotated_fields_simulated = annotate_fields_with_semantic_meaning(sample_fields, live_llm_call=False)

    for i, field in enumerate(annotated_fields_simulated):
        logging.info(f"  Field {i+1}: '{field.visual_label_text}' (Type: {field.field_type_predicted.name})")
        logging.info(f"    -> Semantic: '{field.semantic_meaning_predicted}', LLM Confidence: {field.confidence_score}")

    # Example of how to run with live calls (developer would uncomment and ensure API key is set)
    # if api_key_present:
    #     logging.info(f"\n--- Annotating fields with LIVE LLM responses (live_llm_call=True) ---")
    #     # To make this test more meaningful for live, one might want to pass actual HTML attributes
    #     # For example, for the "First Name" field:
    #     # sample_fields[0].html_attributes_for_llm = {"id": "fname", "name": "firstName", "placeholder": "Enter first name"}
    #     # Then modify annotate_fields_with_semantic_meaning to pass these to get_semantic_match_for_field
    #
    #     annotated_fields_live = annotate_fields_with_semantic_meaning(sample_fields, live_llm_call=True)
    #     for i, field in enumerate(annotated_fields_live):
    #         logging.info(f"  LIVE Field {i+1}: '{field.visual_label_text}' (Type: {field.field_type_predicted.name})")
    #         logging.info(f"    -> Semantic: '{field.semantic_meaning_predicted}', LLM Confidence: {field.confidence_score}")
    # else:
    #     logging.warning("\nSkipping LIVE LLM call test as API key is not set.")

    logging.info("\n--- Live Semantic Matcher Demo Finished ---")
