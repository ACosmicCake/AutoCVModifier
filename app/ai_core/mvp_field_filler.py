# app/ai_core/mvp_field_filler.py
from typing import List, Dict, Any

# Assumes ai_core_data_structures.py is in app/common/
from app.common.ai_core_data_structures import (
    IdentifiedFormField,
    ActionDetail,
    ActionSequenceActionType,
    PredictedFieldType,
    VisualLocation # For creating sample IdentifiedFormField in demo
)

# 1. MVP Semantic Map
# This map should align with the visual_label_text output by mvp_visual_linker.py's
# simulated LLM response for the target website.
MVP_SEMANTIC_MAP: Dict[str, str] = {
    "First Name:": "user.firstName",
    "Last Name:": "user.lastName",
    "Your Email:": "user.email.primary", # Matches the label text from mvp_visual_linker
    "Phone Number:": "user.phone.mobile"
    # Note: The submit button is handled as a NavigationElement and typically
    # doesn't need a semantic mapping to the user profile for filling.
}

# User Profile for MVP (can be imported or defined in orchestrator later)
MVP_USER_PROFILE_EXAMPLE = {
    "user.firstName": "MVP_John",
    "user.lastName": "MVP_Doe",
    "user.email.primary": "mvp_john.doe@example.com",
    "user.phone.mobile": "123-456-7890",
    "user.address.street": "121 MVP Street" # Example of an unused field for this map
}


# 2. Perform Semantic Matching
def perform_semantic_matching_for_mvp(
    identified_fields: List[IdentifiedFormField]
) -> List[IdentifiedFormField]:
    """
    Updates IdentifiedFormField objects with semantic meaning based on MVP_SEMANTIC_MAP.
    """
    print(f"MVPFieldFiller: Performing semantic matching for {len(identified_fields)} fields.")
    updated_fields: List[IdentifiedFormField] = []
    for field in identified_fields:
        if field.visual_label_text and field.visual_label_text in MVP_SEMANTIC_MAP:
            semantic_key = MVP_SEMANTIC_MAP[field.visual_label_text]
            field.semantic_meaning_predicted = semantic_key
            field.confidence_score = min(1.0, field.confidence_score + 0.1) # Boost confidence slightly
            print(f"  Matched '{field.visual_label_text}' to semantic key: '{semantic_key}'")
        else:
            print(f"  No semantic match for '{field.visual_label_text}' in MVP_SEMANTIC_MAP.")
        updated_fields.append(field)
    return updated_fields


# 3. Generate Text Fill Actions
def generate_text_fill_actions_for_mvp(
    semantically_matched_fields: List[IdentifiedFormField],
    user_profile: Dict[str, Any]
) -> List[ActionDetail]:
    """
    Generates ActionDetail objects for filling text fields based on semantic meaning
    and user profile data.
    """
    print(f"\nMVPFieldFiller: Generating text fill actions for {len(semantically_matched_fields)} semantically matched fields.")
    actions_to_perform: List[ActionDetail] = []

    # Supported field types for text filling in MVP
    text_fill_types = [
        PredictedFieldType.TEXT_INPUT,
        PredictedFieldType.EMAIL_INPUT, # Assuming this might be a future type
        PredictedFieldType.PHONE_INPUT, # Assuming this might be a future type
        PredictedFieldType.TEXTAREA
    ]

    for field in semantically_matched_fields:
        if field.semantic_meaning_predicted and \
           field.semantic_meaning_predicted in user_profile and \
           field.dom_path_primary and \
           field.field_type_predicted in text_fill_types:

            value_to_fill = user_profile[field.semantic_meaning_predicted]

            action = ActionDetail(
                action_type=ActionSequenceActionType.FILL_TEXT,
                dom_path_target=field.dom_path_primary,
                value_to_fill=str(value_to_fill), # Ensure it's a string
                visual_confirmation_cue=f"Fill '{field.visual_label_text}' with profile value."
            )
            actions_to_perform.append(action)
            print(f"  Generated FILL_TEXT action for '{field.visual_label_text}' (Semantic: {field.semantic_meaning_predicted}) with value '{str(value_to_fill)[:30]}...'")
        else:
            if not field.semantic_meaning_predicted:
                print(f"  Skipping action for '{field.visual_label_text}': No semantic meaning.")
            elif field.semantic_meaning_predicted not in user_profile:
                print(f"  Skipping action for '{field.visual_label_text}': Semantic key '{field.semantic_meaning_predicted}' not in user profile.")
            elif not field.dom_path_primary:
                print(f"  Skipping action for '{field.visual_label_text}': No DOM path primary.")
            elif field.field_type_predicted not in text_fill_types:
                print(f"  Skipping action for '{field.visual_label_text}': Field type '{field.field_type_predicted.name}' not suitable for text fill.")

    return actions_to_perform


if __name__ == '__main__':
    print("--- Running MVP Field Filler Demo ---")

    # Sample IdentifiedFormField objects (simulating output from mvp_visual_linker.py)
    # These labels MUST match those produced by the simulated LLM in mvp_visual_linker.py
    sample_fields_from_linker: List[IdentifiedFormField] = [
        IdentifiedFormField(
            id="vis_fname", visual_label_text="First Name:",
            visual_location=VisualLocation(x=100, y=50, width=200, height=30),
            dom_path_primary="//input[@id='fname']", dom_path_label="//label[@for='fname']",
            field_type_predicted=PredictedFieldType.TEXT_INPUT, confidence_score=0.9, semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_lname", visual_label_text="Last Name:",
            visual_location=VisualLocation(x=100, y=100, width=200, height=30),
            dom_path_primary="//input[@id='lname']", dom_path_label="//label[@for='lname']",
            field_type_predicted=PredictedFieldType.TEXT_INPUT, confidence_score=0.9, semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_email", visual_label_text="Your Email:", # Matches the key in MVP_SEMANTIC_MAP
            visual_location=VisualLocation(x=100, y=150, width=200, height=30),
            dom_path_primary="//input[@id='email_address']", dom_path_label="//label[@for='email_address']",
            field_type_predicted=PredictedFieldType.TEXT_INPUT, confidence_score=0.88, semantic_meaning_predicted=""
        ),
        IdentifiedFormField(
            id="vis_phone", visual_label_text="Phone Number:",
            visual_location=VisualLocation(x=100, y=200, width=200, height=30),
            dom_path_primary="//input[@id='phone_num']", dom_path_label="//label[@for='phone_num']",
            field_type_predicted=PredictedFieldType.TEXT_INPUT, confidence_score=0.85, semantic_meaning_predicted="" # Changed to TEXT_INPUT for this module
        ),
        IdentifiedFormField( # This one won't be in MVP_SEMANTIC_MAP
            id="vis_comment", visual_label_text="Additional Comments:",
            visual_location=VisualLocation(x=100, y=250, width=200, height=50),
            dom_path_primary="//textarea[@id='comments']",
            field_type_predicted=PredictedFieldType.TEXTAREA, confidence_score=0.80, semantic_meaning_predicted=""
        ),
         IdentifiedFormField( # This one is a button, should be ignored by text filler
            id="vis_submit_btn", visual_label_text="Submit Application",
            visual_location=VisualLocation(x=100, y=300, width=150, height=40),
            dom_path_primary="//button[@id='submitBtn']",
            field_type_predicted=PredictedFieldType.BUTTON, confidence_score=0.95, semantic_meaning_predicted=""
        )
    ]

    print("\n1. Performing Semantic Matching:")
    semantically_matched = perform_semantic_matching_for_mvp(sample_fields_from_linker)

    print("\nFields after semantic matching:")
    for field in semantically_matched:
        print(f"  Label: '{field.visual_label_text}', Semantic: '{field.semantic_meaning_predicted}', Confidence: {field.confidence_score:.2f}")

    print("\n2. Generating Text Fill Actions:")
    fill_actions = generate_text_fill_actions_for_mvp(semantically_matched, MVP_USER_PROFILE_EXAMPLE)

    print("\nGenerated Fill Actions:")
    if fill_actions:
        for i, action in enumerate(fill_actions):
            print(f"  Action {i+1}:")
            print(f"    Type: {action.action_type.name}")
            print(f"    Target DOM Path: {action.dom_path_target}")
            print(f"    Value to Fill: '{action.value_to_fill}'")
            print(f"    Visual Cue: '{action.visual_confirmation_cue}'")
    else:
        print("  No fill actions generated.")

    print("\n--- MVP Field Filler Demo Finished ---")
