# Live Semantic Matching: Initial Testing and Refinement Strategy

## 1. Introduction

**Purpose:**
This document outlines the strategy for the initial testing and iterative refinement of the `live_semantic_matcher.py` module. The primary focus is on evaluating the performance of the chosen Large Language Model (LLM) and prompt strategies in accurately mapping visually perceived field labels (complemented by predicted field types and other context) to a predefined schema of semantic keys.

**Goal:**
To achieve reliable, accurate, and contextually aware semantic key assignment for a diverse range of form field labels encountered on real-world websites. This will ensure the system correctly understands the purpose of each field before attempting to fill it.

## 2. Recap of Testing Workflow

The testing of `live_semantic_matcher.py` involves the following data flow, typically orchestrated by a test script or during integrated testing with the `MVCOrchestrator`:

1.  **Upstream Data:** The system first obtains `IdentifiedFormField` objects. In a live scenario, these objects are the result of:
    *   `MVPSeleniumWrapper.get_page_state()` (screenshot, DOM).
    *   `MVPSeleniumWrapper.get_all_interactable_elements_details()` (detailed DOM element list).
    *   `live_visual_perception.get_llm_field_predictions()` (raw visual perception from LLM).
    *   `live_visual_perception.parse_llm_output_to_identified_elements()` (parsed visual elements).
    *   `live_visual_grounder.ground_visual_elements()` (visual elements linked to DOM XPaths).
    At this stage, each `IdentifiedFormField` should have `visual_label_text`, `predicted_field_type`, `dom_path_primary`, and potentially some extracted HTML attributes (though passing these attributes to the semantic matcher is a refinement step for the `live_semantic_matcher` itself).

2.  **Semantic Matching (THE STEP BEING TESTED):**
    *   The list of `IdentifiedFormField` objects is passed to `live_semantic_matcher.annotate_fields_with_semantic_meaning(identified_fields, live_llm_call=True)`.
    *   Inside this function, for each field, `live_semantic_matcher.get_semantic_match_for_field()` is called, which constructs a prompt and queries the live LLM.

3.  **Analysis:** The core analysis focuses on the `semantic_meaning_predicted` and `confidence_score` attributes assigned to each `IdentifiedFormField` by the `live_semantic_matcher`.

## 3. Hypothetical Test Cases & Anticipated Issues (Examples using diverse field labels)

Testing should cover a variety of label types and contextual situations. The `target_semantic_keys` are loaded from `app/common/data_schemas/semantic_field_schema.json`.

**3.1. Common Variations & Synonyms:**
-   *Labels to Test:* "First Name", "Given Name", "Forename", "Surname", "Family Name", "E-mail", "Contact Number".
-   *Expected Keys (Examples):* `user.personal_info.first_name`, `user.personal_info.last_name`, `user.contact_info.email_primary`, `user.contact_info.phone_mobile`.
-   *Anticipated Challenge:* The LLM might not consistently map all synonyms to the exact same key without guidance, or might be overly influenced by minor variations if the prompt isn't robust.
-   *Prompt Refinement Strategies:*
    -   If using few-shot prompting, include examples covering common synonyms for critical fields.
    -   Ensure the prompt strongly emphasizes that the `semantic_key` **must** be chosen from the provided `target_semantic_keys` list.
    -   The descriptions within `semantic_field_schema.json` (though not directly passed in the prompt's key list) could inform future fine-tuning or more advanced context injection if simple key-list prompting is insufficient.

**3.2. Ambiguous Labels Requiring Context:**
-   *Label Example:* "Email"
-   *Field Type:* `PredictedFieldType.EMAIL_INPUT`
-   *Context Scenarios:*
    1.  "Email" appears alone on a general contact form. (Expected: `user.contact_info.email_primary`)
    2.  "Email" appears on a form page that also has "Work Email". (Expected: `user.contact_info.email_personal` or `user.contact_info.email_secondary` if `email_primary` is already used or if "Work Email" maps to `email_work`).
    3.  "Email" appears in a section titled "Emergency Contact". (Expected: Could be a new key like `user.emergency_contact[].email` if schema supports lists of contacts, or `system_internal.other_unspecified_field` if not).
-   *Anticipated Challenge:* Without sufficient context, the LLM will likely default to the most common mapping (e.g., `user.contact_info.email_primary`).
-   *Prompt Refinement Strategies:*
    -   The `get_semantic_match_for_field` function in `live_semantic_matcher.py` accepts an `additional_context` parameter. The calling code (e.g., orchestrator or a higher-level AI module) would need to be responsible for gathering this context (e.g., nearby field labels, section titles from DOM analysis or visual cues).
    -   The prompt can be enhanced to instruct the LLM on how to use this `additional_context`: "Use the 'Additional Context' provided, if any, to disambiguate common labels. For example, if the context indicates a 'Work' section, an 'Email' label might refer to a work email."

**3.3. Culturally Specific or Uncommon Labels:**
-   *Label Examples:* "National Insurance Number" (UK), "Social Insurance Number" (Canada), "TFN" (Australia Tax File Number), "CPF" (Brazil).
-   *Expected Keys (if schema supports):* `user.identity.national_id.uk_ni`, `user.identity.national_id.ca_sin`, `user.identity.national_id.au_tfn`, or a more generic `user.identity.national_id_number` if specific regional keys are not defined. If no relevant key exists, `system_internal.other_unspecified_field`.
-   *Anticipated Challenge:* The LLM might not recognize these terms or map them correctly if the `target_semantic_keys` list lacks appropriate options or if the LLM's general training data doesn't cover these specific national identifiers well.
-   *Prompt Refinement & Schema Considerations:*
    -   The `target_semantic_keys` list in `semantic_field_schema.json` must be reviewed and expanded to include common national/regional identifiers if these are important targets.
    -   If using few-shot prompting, including examples of such mappings would be beneficial.
    -   The prompt could include a general instruction: "For country-specific identification numbers, map to the closest available 'national_id' or specific regional ID type from the list. If none match, use 'system_internal.other_unspecified_field'."

**3.4. Very Long or Descriptive Labels (e.g., from textareas or complex questions):**
-   *Label Example:* "Please describe your previous experience with agile project management methodologies and any tools you have used (e.g., JIRA, Trello)."
-   *Field Type:* `PredictedFieldType.TEXTAREA`
-   *Expected Key Examples:* `application.custom_question.generic_response_1`, `application.experience.project_management_tools`, or `application.essay.describe_experience_agile`.
-   *Anticipated Challenge:* The LLM might get distracted by keywords within the long label and try to match them to multiple, narrower semantic keys, or fail to categorize the overall intent.
-   *Prompt Refinement & Schema Considerations:*
    -   The prompt should guide the LLM: "For long, descriptive labels that represent open-ended questions or essay-type answers, determine the core subject of the question. Map it to a specific semantic key from the list if one accurately reflects this subject (e.g., 'application.experience.project_management_tools'). If the question is highly specific and not covered, use a generic key like 'application.custom_question.generic_response_N'. Avoid mapping based on isolated keywords if the overall context points to a broader question."
    -   The `target_semantic_keys` list in `semantic_field_schema.json` should include several generic custom question placeholders (e.g., `application.custom_question.generic_response_1`, `_2`, `_3`) and potentially some common thematic essay/question keys (e.g., `application.statement.personal_goals`, `application.summary.relevant_experience`).

**3.5. Fields with No Clear Schema Match:**
-   *Label Example:* "Dietary Restrictions (for team lunch)", "Preferred T-Shirt Size (for company swag)"
-   *Expected Key:* `system_internal.other_unspecified_field` or `null` (as per current prompt design, it should choose `system_internal.other_unspecified_field`).
-   *Anticipated Challenge:* The LLM might attempt to force a match to a tangentially related key (e.g., mapping "T-Shirt Size" to `user.preferences.clothing_size` if such a key existed, even if it's too specific for the current schema).
-   *Prompt Refinement:*
    -   Re-emphasize and strengthen the instruction in the prompt: "It is crucial that if no category from the 'Predefined Semantic Categories' list is a strong and appropriate fit for the field's meaning, you MUST return 'system_internal.other_unspecified_field' as the 'semantic_key'. Do not attempt to force a match to an incorrect category."
    -   Few-shot examples demonstrating correct use of the "no match" key are very important.

**3.6. Confidence Score Calibration:**
-   *Symptom:* The LLM consistently returns very high confidence (e.g., >0.9) even for incorrect matches, or very low confidence (e.g., <0.5) for clearly correct matches.
-   *Refinement Strategy:*
    -   This is one of the hardest aspects to directly control via prompting for many proprietary LLMs, as their internal confidence mechanisms are complex.
    -   Focus on making the task definition as clear as possible and the `target_semantic_keys` as unambiguous as possible.
    -   If few-shot prompting is used, provide `confidence_score` examples in the shots that reflect realistic and well-calibrated scores.
    -   Analyze patterns: If confidence is consistently miscalibrated for certain types of labels or semantic keys, it might indicate those parts of the schema or prompt need more clarity or examples.
    -   External Calibration: If LLM scores remain unhelpful, a layer of external calibration might be needed (e.g., mapping LLM score ranges to different trust levels based on empirical observation).

## 4. Key Parameters and Strategies for Refinement in `live_semantic_matcher.py`

-   **The Prompt Content:** This is the primary area for refinement.
    -   Clarity of task definition and instructions.
    -   Wording used to describe input fields (label, type, attributes).
    -   Effectiveness of instructions for handling ambiguity and no-match scenarios.
    -   Quality and relevance of examples in few-shot prompts (if used).
-   **`target_semantic_keys` List:** The comprehensiveness and clarity of this list (loaded from `semantic_field_schema.json`) are vital. If the LLM frequently fails to find appropriate keys, the schema itself may need additions or revisions.
-   **Context Provision (`additional_context`, `html_attributes`):**
    -   Determining *what* context is most useful (e.g., which HTML attributes, how many nearby labels, section headers).
    -   How this context is formatted and presented within the prompt.
-   **LLM API Parameters (If available and relevant for text models like Gemini Pro):**
    -   **Temperature:** Lower values (e.g., 0.0-0.2) make the output more deterministic and focused, which is generally preferred for classification and JSON generation. Higher values increase creativity/randomness.
    -   **Top-P/Top-K:** Alternative sampling strategies that can also influence determinism.
    -   (Note: `gemini-pro` via `google-generativeai` SDK might have less direct control over some of these compared to Vertex AI endpoints, but check documentation for available `generation_config` options).

## 5. Developer Workflow for Testing and Refinement

-   **Tooling:**
    1.  **Test Orchestration Script:** A Python script (e.g., `test_semantic_matcher_live.py`) that:
        *   Loads `IdentifiedFormField` objects from a pre-collected set (e.g., output from running visual perception and grounding on test websites, saved as JSON). This allows focusing solely on the semantic matching step.
        *   Allows easy selection of which fields to test.
        *   Calls `live_semantic_matcher.annotate_fields_with_semantic_meaning(fields, live_llm_call=True)`.
    2.  **Data Caching:** The script should use cached inputs (`IdentifiedFormField` data) to allow rapid iteration on the `live_semantic_matcher.py` prompts and logic without re-running upstream modules.
-   **Iterative Process:**
    1.  **Prepare Test Set:** Collect a diverse set of `IdentifiedFormField` instances from various target websites. Each instance should have at least `visual_label_text` and `predicted_field_type`. Manually determine the "ground truth" `semantic_meaning_predicted` for each test case.
    2.  **Run Semantic Matcher:** Execute `annotate_fields_with_semantic_meaning` on the test set with `live_llm_call=True`.
    3.  **Log Extensively:** For each field, log:
        *   Input: `visual_label_text`, `predicted_field_type`, any provided `html_attributes` or `additional_context`.
        *   The full prompt sent to the LLM.
        *   The raw JSON string response from the LLM.
        *   The final parsed `semantic_meaning_predicted` and `confidence_score`.
    4.  **Review and Analyze:** Compare the LLM's assigned `semantic_meaning_predicted` against the ground truth. Categorize errors:
        *   Correct match.
        *   Incorrect match (wrong key assigned).
        *   No match when one was expected (e.g., returned `system_internal.other_unspecified_field` incorrectly).
        *   Correctly no match (returned `system_internal.other_unspecified_field` appropriately).
        *   Malformed JSON response or API error.
    5.  **Formulate Hypotheses:** For mismatches, determine the likely cause (e.g., ambiguous prompt instruction, missing context, unclear semantic key in schema, LLM misunderstanding).
    6.  **Refine Logic:** Adjust the prompt construction (zero-shot instructions, few-shot examples), context provision strategy in `live_semantic_matcher.py`, or potentially update/clarify keys in `semantic_field_schema.json`.
    7.  **Re-run on Test Set:** Use the cached inputs to quickly test the impact of refinements.
    8.  **Regression Test:** Ensure changes haven't negatively impacted previously correct classifications.
    9.  **Document:** Keep a log of prompt versions, changes made, and their impact on accuracy for different test cases.

## 6. Logging for Semantic Matching Debugging

Within `get_semantic_match_for_field`:
-   Log all inputs: `visual_label`, `predicted_type`, `target_keys` (or at least its length/source), `html_attributes`, `additional_context`.
-   Log the complete prompt string sent to the LLM.
-   Log the raw text response from the LLM before JSON parsing.
-   Log the extracted JSON string if parsing from markdown.
-   Log the final parsed dictionary (or error if parsing fails).
-   Log any API errors or prompt feedback (blocks).

Within `annotate_fields_with_semantic_meaning`:
-   Log the semantic key and confidence assigned to each field.
-   Log if a field was skipped (e.g., no visual label).

## 7. Success Criteria for this Step (Initial)

-   **Quantitative:** Achieve >85-95% accuracy in assigning the correct `semantic_meaning_predicted` for common and clearly defined field labels found on the selected diverse test websites. Accuracy for more ambiguous or complex cases might initially be lower but should show improvement through iteration.
-   **Qualitative:**
    -   The LLM's `confidence_score` should generally correlate with the actual correctness of the match (higher confidence for more certain mappings).
    -   The system should reliably use the designated "no match" key (e.g., `system_internal.other_unspecified_field`) for labels that genuinely do not fit the defined schema.
    -   Develop a good understanding of the types of labels or contexts where the current prompting strategy struggles, informing future refinements or the need for more advanced techniques.

This iterative testing and refinement process is essential for building a robust and accurate live semantic matching capability.
