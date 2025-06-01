from typing import List, Dict, Any, Optional

# Assuming ai_core_data_structures.py and interaction_logic_module.py are accessible
from ai_core_data_structures import (
    IdentifiedFormField,
    NavigationElement,
    QuestionAnsweringResult,
    ActionDetail,
    ActionSequenceRecommendation,
    ActionSequenceActionType,
    PredictedFieldType, # For sample data
    VisualLocation,     # For sample data
    NavigationActionType # For sample data
)
from interaction_logic_module import generate_actions_for_basic_elements

def orchestrate_action_sequence(
    processed_fields: List[IdentifiedFormField],
    navigation_elements: List[NavigationElement],
    user_profile_data: Dict[str, Any],
    approved_qa_results: List[QuestionAnsweringResult],
    page_context: Optional[Dict[str, Any]] = None
) -> ActionSequenceRecommendation:
    """
    Consolidates outputs from other AI modules and decides on a final sequence of actions,
    including field filling, QA, and navigation.
    """
    if page_context is None:
        page_context = {}
    print(f"ActionGenerationOrchestrator: Starting action sequence orchestration. Page context: {page_context}")

    final_actions_list: List[ActionDetail] = []

    # 3. Get Basic Field Filling Actions
    print("\n  Orchestrator: Generating basic field filling actions...")
    basic_field_actions_recommendation = generate_actions_for_basic_elements(
        processed_fields=processed_fields,
        user_profile_data=user_profile_data
    )
    if basic_field_actions_recommendation.actions:
        final_actions_list.extend(basic_field_actions_recommendation.actions)
        print(f"    Added {len(basic_field_actions_recommendation.actions)} basic field filling actions.")
    else:
        print("    No basic field filling actions generated.")


    # 4. Incorporate Approved QA Answers
    print("\n  Orchestrator: Incorporating approved QA answers...")
    if approved_qa_results:
        for qa_result in approved_qa_results:
            if qa_result.dom_path_question and qa_result.suggested_answer_draft:
                action = ActionDetail(
                    action_type=ActionSequenceActionType.FILL_TEXT,
                    dom_path_target=qa_result.dom_path_question,
                    value_to_fill=qa_result.suggested_answer_draft, # This is the user-approved/edited text
                    visual_confirmation_cue=f"Fill question '{qa_result.question_text_identified[:30]}...'"
                )
                final_actions_list.append(action)
                print(f"    Added FILL_TEXT action for QA: '{qa_result.question_text_identified[:30]}...'")
            else:
                print(f"    Skipping QA result for '{qa_result.question_text_identified[:30]}...' due to missing DOM path or answer draft.")
    else:
        print("    No approved QA results to incorporate.")

    # 5. Determine Navigation Action (Simulated Logic)
    print("\n  Orchestrator: Determining navigation action...")
    chosen_nav_action: Optional[ActionDetail] = None
    expected_next_page_hint: Optional[str] = None

    if navigation_elements:
        chosen_nav_element: Optional[NavigationElement] = None

        # Priority: "Submit", "Finish", "Apply"
        submit_keywords = ["submit", "finish", "apply", "complete", "send my application"]
        for nav_element in navigation_elements:
            label_lower = (nav_element.visual_label_text or "").lower()
            action_type_pred = nav_element.action_type_predicted # Assuming this might be populated
            if any(keyword in label_lower for keyword in submit_keywords) or \
               (action_type_pred and action_type_pred == NavigationActionType.SUBMIT_FORM):
                chosen_nav_element = nav_element
                expected_next_page_hint = "confirmation_page_or_next_step"
                print(f"    Prioritized 'Submit' type navigation: '{nav_element.visual_label_text}'")
                break

        # Secondary: "Next", "Continue"
        if not chosen_nav_element:
            next_keywords = ["next", "continue", "proceed"]
            for nav_element in navigation_elements:
                label_lower = (nav_element.visual_label_text or "").lower()
                action_type_pred = nav_element.action_type_predicted
                if any(keyword in label_lower for keyword in next_keywords) or \
                   (action_type_pred and action_type_pred == NavigationActionType.NEXT_PAGE):
                    chosen_nav_element = nav_element
                    expected_next_page_hint = "next_form_step"
                    print(f"    Found 'Next' type navigation: '{nav_element.visual_label_text}'")
                    break

        # Fallback: if only one, choose it. If multiple and no priority match, pick first.
        if not chosen_nav_element and navigation_elements:
            chosen_nav_element = navigation_elements[0]
            expected_next_page_hint = "unknown_next_page"
            print(f"    Defaulted to first available navigation element: '{chosen_nav_element.visual_label_text}'")


        if chosen_nav_element and chosen_nav_element.dom_path:
            chosen_nav_action = ActionDetail(
                action_type=ActionSequenceActionType.CLICK_ELEMENT,
                dom_path_target=chosen_nav_element.dom_path,
                visual_confirmation_cue=f"Click navigation button '{chosen_nav_element.visual_label_text}'"
            )
            final_actions_list.append(chosen_nav_action)
            print(f"    Added CLICK_ELEMENT action for navigation: '{chosen_nav_element.visual_label_text}'")
        elif chosen_nav_element:
             print(f"    Chosen navigation element '{chosen_nav_element.visual_label_text}' lacks a DOM path.")
    else:
        print("    No navigation elements provided or suitable navigation action found.")

    # 6. Create ActionSequenceRecommendation
    recommendation = ActionSequenceRecommendation(
        actions=final_actions_list,
        expected_next_page_type=expected_next_page_hint if chosen_nav_action else "stay_on_page_or_no_clear_nav"
    )

    print(f"\nActionGenerationOrchestrator: Orchestration complete. Total actions: {len(final_actions_list)}.")
    return recommendation


if __name__ == "__main__":
    print("--- Running Action Generation Orchestrator Demo ---")

    sample_user_data = {
        "user.firstName": "Alice",
        "user.lastName": "Automator",
        "user.email.primary": "alice.auto@example.com",
        "user.address.country": "Canada"
    }

    sample_processed_fields: List[IdentifiedFormField] = [
        IdentifiedFormField(
            id="f_fname", visual_label_text="First Name",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.TEXT_INPUT,
            confidence_score=0.95, dom_path_primary="//input[@id='fname']", semantic_meaning_predicted="user.firstName"
        ),
        IdentifiedFormField(
            id="f_country", visual_label_text="Country of Residence",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), field_type_predicted=PredictedFieldType.DROPDOWN,
            confidence_score=0.90, dom_path_primary="//select[@id='country']", semantic_meaning_predicted="user.address.country"
        )
    ]

    sample_navigation_elements: List[NavigationElement] = [
        NavigationElement(
            id="nav_save", visual_label_text="Save Draft", dom_path="//button[@id='save']",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), action_type_predicted=NavigationActionType.OTHER, confidence_score=0.9
        ),
        NavigationElement(
            id="nav_next", visual_label_text="Continue to Next Page", dom_path="//button[@id='nextPage']",
            visual_location=VisualLocation(x=1,y=1,w=1,h=1), action_type_predicted=NavigationActionType.NEXT_PAGE, confidence_score=0.95
        )
        # To test submit, could add:
        # NavigationElement(
        #     id="nav_submit", visual_label_text="Submit My Application", dom_path="//button[@id='submitApp']",
        #     visual_location=VisualLocation(x=1,y=1,w=1,h=1), action_type_predicted=NavigationActionType.SUBMIT_FORM, confidence_score=0.98
        # )
    ]

    sample_qa_results: List[QuestionAnsweringResult] = [
        QuestionAnsweringResult(
            question_text_identified="Tell us about your motivation for applying.",
            dom_path_question="//textarea[@id='motivation']",
            suggested_answer_draft="I am very motivated by this company's mission and my skills align well with the job requirements. I am eager to contribute.",
            sources_from_profile=["career_goals", "skills_summary"],
            requires_user_review=True # Assumed to be true after user review
        )
    ]

    page_ctx = {"current_page_number": 2, "total_pages": 5, "form_name": "General Profile"}

    print("\nInitial Data:")
    print(f"  Processed Fields: {len(sample_processed_fields)}")
    print(f"  Navigation Elements: {len(sample_navigation_elements)}")
    print(f"  User Profile Keys: {list(sample_user_data.keys())}")
    print(f"  Approved QA Results: {len(sample_qa_results)}")


    final_sequence_recommendation = orchestrate_action_sequence(
        processed_fields=sample_processed_fields,
        navigation_elements=sample_navigation_elements,
        user_profile_data=sample_user_data,
        approved_qa_results=sample_qa_results,
        page_context=page_ctx
    )

    print(f"\n--- Final Orchestrated Action Sequence ---")
    print(f"Expected Next Page Type: {final_sequence_recommendation.expected_next_page_type}")
    if final_sequence_recommendation.actions:
        for i, action in enumerate(final_sequence_recommendation.actions):
            print(f"  Action {i+1}:")
            print(f"    Type: {action.action_type.name}")
            print(f"    Target DOM Path: {action.dom_path_target}")
            if action.value_to_fill:
                print(f"    Value to Fill: '{action.value_to_fill[:50]}...'") # Truncate long values
            if action.option_to_select:
                print(f"    Option to Select: '{action.option_to_select}'")
            if action.visual_confirmation_cue:
                print(f"    Visual Cue: '{action.visual_confirmation_cue}'")
    else:
        print("  No actions in the final sequence.")

    print("\n--- Action Generation Orchestrator Demo Finished ---")
