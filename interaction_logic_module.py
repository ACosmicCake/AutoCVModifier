from typing import List, Dict, Any

# Assuming ai_core_data_structures.py is in the same directory or accessible in PYTHONPATH
from ai_core_data_structures import (
    IdentifiedFormField,
    ActionDetail,
    ActionSequenceRecommendation,
    ActionSequenceActionType,
    PredictedFieldType,
    VisualLocation # Needed for constructing sample IdentifiedFormField
)

def generate_actions_for_basic_elements(
    processed_fields: List[IdentifiedFormField],
    user_profile_data: Dict[str, Any]
) -> ActionSequenceRecommendation:
    """
    Generates a sequence of actions for filling basic form elements based on
    semantic understanding and user profile data.
    """
    print(f"InteractionLogicModule: Starting action generation for {len(processed_fields)} fields.")
    actions_to_perform: List[ActionDetail] = []

    for field in processed_fields:
        print(f"\n  Processing field: '{field.visual_label_text}' (Semantic: {field.semantic_meaning_predicted}, Type: {field.field_type_predicted.name})")

        if not field.semantic_meaning_predicted:
            print(f"    Skipping field ID {field.id}: No semantic meaning predicted.")
            continue

        if not field.dom_path_primary:
            print(f"    Skipping field ID {field.id} ('{field.visual_label_text}'): No DOM path primary defined.")
            continue

        if field.semantic_meaning_predicted not in user_profile_data:
            print(f"    Skipping field ID {field.id} ('{field.visual_label_text}'): Semantic meaning '{field.semantic_meaning_predicted}' not found in user profile data.")
            continue

        value_from_profile = user_profile_data[field.semantic_meaning_predicted]

        action_detail = None

        # Handle Text Inputs (TEXT_INPUT, TEXTAREA - others could be added like EMAIL, PASSWORD etc.)
        if field.field_type_predicted in [PredictedFieldType.TEXT_INPUT, PredictedFieldType.TEXTAREA]:
            action_detail = ActionDetail(
                action_type=ActionSequenceActionType.FILL_TEXT,
                dom_path_target=field.dom_path_primary,
                value_to_fill=str(value_from_profile),
                visual_confirmation_cue=f"Fill '{field.visual_label_text or field.id}' with '{str(value_from_profile)[:20]}...'" # Truncate long values for cue
            )
            print(f"    Generated FILL_TEXT action for '{field.visual_label_text or field.id}'.")

        # Handle Simple Dropdowns (Simulated direct value match)
        elif field.field_type_predicted == PredictedFieldType.DROPDOWN:
            # In a real scenario, we might need to match value_from_profile against field.options
            # For this PoC, we assume value_from_profile is the exact option value/text to select.
            action_detail = ActionDetail(
                action_type=ActionSequenceActionType.SELECT_DROPDOWN_OPTION,
                dom_path_target=field.dom_path_primary,
                option_to_select=str(value_from_profile),
                visual_confirmation_cue=f"Select '{str(value_from_profile)}' in '{field.visual_label_text or field.id}'"
            )
            print(f"    Generated SELECT_DROPDOWN_OPTION action for '{field.visual_label_text or field.id}'.")

        # Handle Checkboxes (Example: if profile value is True, click it)
        elif field.field_type_predicted == PredictedFieldType.CHECKBOX:
            # Assuming the semantic meaning for a checkbox maps to a boolean in the user profile
            # e.g., "consent.newsletterSubscription": True
            if isinstance(value_from_profile, bool) and value_from_profile:
                action_detail = ActionDetail(
                    action_type=ActionSequenceActionType.CLICK_ELEMENT, # Checkboxes are clicked
                    dom_path_target=field.dom_path_primary,
                    visual_confirmation_cue=f"Check '{field.visual_label_text or field.id}'"
                )
                print(f"    Generated CLICK_ELEMENT action for checkbox '{field.visual_label_text or field.id}'.")
            else:
                print(f"    Skipping checkbox '{field.visual_label_text or field.id}': Profile value is falsy or not boolean ('{value_from_profile}').")


        # Placeholder for other types
        else:
            print(f"    Skipping field ID {field.id} ('{field.visual_label_text}'): Field type '{field.field_type_predicted.name}' not handled by basic logic yet.")

        if action_detail:
            actions_to_perform.append(action_detail)

    recommendation = ActionSequenceRecommendation(
        actions=actions_to_perform,
        expected_next_page_type="auto_determined" # Placeholder
    )
    print(f"\nInteractionLogicModule: Action generation completed. {len(actions_to_perform)} actions generated.")
    return recommendation


if __name__ == "__main__":
    print("--- Running Interaction Logic Module Demo ---")

    sample_user_data = {
        "user.firstName": "John",
        "user.lastName": "Doe",
        "user.email.primary": "john.doe@example.com",
        "user.address.country": "USA", # For dropdown
        "user.jobTitle": "Software Engineer",
        "consent.newsletterSubscription": True, # For checkbox
        "application.notes": "This is a test application note spanning multiple lines for the textarea example."
    }

    # Sample IdentifiedFormField objects (as if from Semantic Matching Module)
    fields_for_action: List[IdentifiedFormField] = [
        IdentifiedFormField(
            id="f1", visual_label_text="First Name",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.95, dom_path_primary="//input[@id='fname']", semantic_meaning_predicted="user.firstName"
        ),
        IdentifiedFormField(
            id="f2", visual_label_text="Last Name",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.95, dom_path_primary="//input[@id='lname']", semantic_meaning_predicted="user.lastName"
        ),
        IdentifiedFormField(
            id="f3", visual_label_text="Email",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT, # Assuming TEXT_INPUT covers email type for simplicity
            confidence_score=0.92, dom_path_primary="//input[@name='email']", semantic_meaning_predicted="user.email.primary"
        ),
        IdentifiedFormField(
            id="f4", visual_label_text="Country",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.DROPDOWN,
            confidence_score=0.90, dom_path_primary="//select[@id='country']", semantic_meaning_predicted="user.address.country",
            options=[] # In a real case, options might be populated
        ),
        IdentifiedFormField( # Field not in user_profile_data
            id="f5", visual_label_text="Job Title",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.85, dom_path_primary="//input[@id='jobtitle']", semantic_meaning_predicted="user.jobTitle.current" # Mismatch with sample_user_data
        ),
        IdentifiedFormField( # Field without DOM path
            id="f6", visual_label_text="Company Name",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.85, dom_path_primary="", semantic_meaning_predicted="user.companyName"
        ),
        IdentifiedFormField( # Checkbox example
            id="f7", visual_label_text="Subscribe to Newsletter",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.CHECKBOX,
            confidence_score=0.88, dom_path_primary="//input[@id='newsletter_opt_in']", semantic_meaning_predicted="consent.newsletterSubscription"
        ),
         IdentifiedFormField( # Textarea example
            id="f8", visual_label_text="Additional Notes",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXTAREA,
            confidence_score=0.80, dom_path_primary="//textarea[@id='notes']", semantic_meaning_predicted="application.notes"
        ),
        IdentifiedFormField( # Radio button - not handled
            id="f9", visual_label_text="Preferred Contact Method",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.RADIO_BUTTON,
            confidence_score=0.80, dom_path_primary="//input[@name='contact_pref']", semantic_meaning_predicted="user.contactPreference"
        )
    ]

    print(f"\nUser Profile Data: {sample_user_data}")

    action_sequence = generate_actions_for_basic_elements(
        processed_fields=fields_for_action,
        user_profile_data=sample_user_data
    )

    print(f"\nGenerated Action Sequence Recommendation:")
    if action_sequence.actions:
        for i, action in enumerate(action_sequence.actions):
            print(f"  Action {i+1}:")
            print(f"    Type: {action.action_type.name}")
            print(f"    Target DOM Path: {action.dom_path_target}")
            if action.value_to_fill:
                print(f"    Value to Fill: '{action.value_to_fill}'")
            if action.option_to_select:
                print(f"    Option to Select: '{action.option_to_select}'")
            if action.visual_confirmation_cue:
                print(f"    Visual Cue: '{action.visual_confirmation_cue}'")
    else:
        print("  No actions generated.")

    print("\n--- Interaction Logic Module Demo Finished ---")
