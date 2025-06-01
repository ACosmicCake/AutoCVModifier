# Live LLM Testing and Prompt Refinement Strategy for Visual Perception

## 1. Introduction

**Purpose:**
This document outlines the strategy and process for the initial testing of the live visual perception module (`app/ai_core/live_visual_perception.py`) using a real Multimodal LLM (Google Gemini Pro Vision) on actual websites. It details how to iteratively refine the LLM prompt to improve the accuracy and robustness of UI element identification.

**Importance:**
Effective visual perception is foundational to the AutoApply system. The performance of the Multimodal LLM in identifying form elements, labels, and their types directly impacts all subsequent AI Core modules and the overall success of automation. An iterative testing and prompt refinement process is crucial for achieving reliable AI performance across diverse web page layouts and styles.

## 2. Selection of Test Websites (Hypothetical Examples)

A diverse set of test websites is needed to evaluate the robustness of the prompt and the LLM's capabilities.

-   **Website A: `SimpleFormsCorp.com/careers/apply/software-engineer`** (Hypothetical)
    -   **Characteristics:** Clean, modern layout. Standard HTML form elements (text inputs, dropdowns, checkboxes, radio buttons). Labels are clearly associated and positioned close to their respective fields (e.g., to the left or directly above). Single, clearly labeled "Submit" or "Next" button.
    -   **Expected Performance:** The current prompt in `live_visual_perception.py` is expected to perform well on this type of site, serving as a baseline.
    -   **Test Focus:** Validate basic accuracy of bounding boxes, label text extraction, and element type prediction.

-   **Website B: `CreativeWidgetsInc.net/jobs/apply/designer`** (Hypothetical)
    -   **Characteristics:** Visually rich, potentially non-standard layout (e.g., multi-column forms, labels significantly above fields or as placeholders). Custom-styled input fields (e.g., appearing as just an underline). May use icons for actions (e.g., a send icon instead of "Submit" text).
    -   **Anticipated Challenges:**
        -   LLM might miss custom-styled fields if they don't visually resemble traditional inputs.
        -   Label association could be more challenging if labels are distant, embedded as placeholders, or if surrounding text is misidentified as a label.
        -   Accurate bounding boxes for non-rectangular elements or small icon-based buttons.
        -   Correctly typing fields that are visually ambiguous.
    -   **Test Focus:** Robustness to creative layouts, placeholder label extraction, identification of less standard-looking (but still standard HTML) elements.

-   **Website C: `LegacyEnterprises.org/apply-now/jobid/12345`** (Hypothetical)
    -   **Characteristics:** Older design, potentially using table-based layouts for forms. Labels might be verbose or part of longer descriptive sentences. Multiple buttons like "Submit Application," "Save for Later," "Reset Form."
    -   **Anticipated Challenges:**
        -   LLM correctly associating labels with fields across `<td>` or other structural HTML elements in table layouts.
        -   Distinguishing the primary "submit" or "next" button from secondary or tertiary action buttons.
        -   Parsing and extracting concise labels from verbose descriptions.
        -   Handling grouped elements like radio button groups where a single question label applies to multiple radio inputs.
    -   **Test Focus:** Performance on non-semantic HTML layouts, disambiguation of multiple action buttons, handling of complex label structures.

## 3. Initial Prompt (Recap from `live_visual_perception.py`)

The current prompt in `live_visual_perception.py` instructs the Gemini Pro Vision model to:
-   Act as an expert AI assistant for UI element detection.
-   Identify common form elements: text inputs, textareas, email/phone inputs, dropdowns, checkboxes, radio buttons, and interactive buttons.
-   For each element, extract:
    1.  `visual_label`: The visible text label.
    2.  `element_bbox`: Bounding box `[x_min, y_min, x_max, y_max]` for the interactive element.
    3.  `label_bbox`: Bounding box for its visual label.
    4.  `element_type`: A standardized type string (e.g., 'text_input', 'button').
-   Return this information as a single JSON object with a root key `"identified_elements"`, where the value is a list of element objects, each adhering to the specified keys. An example structure is provided in the prompt.

## 4. Anticipated LLM Output Issues & Corresponding Prompt Refinement Strategies

This section details potential issues and how the prompt might be adjusted to mitigate them.

**4.1. Issue: Missed Form Elements**
-   *Symptom:* The LLM fails to identify all visible and interactive input fields, dropdowns, checkboxes, buttons, etc., on the page.
-   *Possible Prompt Refinements:*
    -   **Increase Specificity of Element Types:** "Identify all of the following interactive form elements: single-line text input fields (including those for email, phone, date, password), multi-line text areas, select dropdowns (drop-down lists), checkboxes, radio buttons, and clickable buttons..."
    -   **Emphasize Comprehensive Scan:** "Ensure you meticulously scan the entire visible area of the screenshot. Do not overlook elements that might be smaller or in less common positions."
    -   **Leverage DOM Context (if used):** "If HTML DOM context is provided, use it to help confirm the presence and type of elements that are visually ambiguous or subtly styled, but ensure a visual correlate exists in the screenshot."
    -   **Negative Constraints (Careful Use):** "Do not identify static text or decorative images as interactive elements unless they function as part of a form field (e.g., a custom-styled select arrow)."

**4.2. Issue: Incorrect Label Association**
-   *Symptom:* The `visual_label` returned by the LLM is not the correct human-readable label for an element, or the `label_bbox` is inaccurate or encompasses non-label text.
-   *Possible Prompt Refinements:*
    -   **Proximity and Relevance Guidance:** "For each interactive element, find its closest and most semantically relevant textual label. Labels are typically found immediately preceding the element (left or right, depending on language direction), directly above it, or sometimes as placeholder text within the element itself if no external label is present."
    -   **Handling Missing Labels:** "If an interactive element has no discernible visible label text directly associated with it, return 'N/A' or an empty string for `visual_label`."
    -   **DOM Clues for Labels (if used):** "When available, consider `<label>` tags in the HTML DOM and their `for` attributes to correctly associate labels with input elements, but always verify the label is visible in the screenshot."

**4.3. Issue: Inaccurate Bounding Boxes**
-   *Symptom:* `element_bbox` or `label_bbox` does not accurately or tightly cover the intended object. Boxes might be too large, too small, or offset.
-   *Possible Prompt Refinements:*
    -   **Coordinate System & Precision:** "Provide precise bounding boxes as `[x_min, y_min, x_max, y_max]` pixel coordinates, where `(x_min, y_min)` is the top-left corner and `(x_max, y_max)` is the bottom-right corner of the box. Ensure coordinates are integers."
    -   **Tightness for Elements:** "The `element_bbox` must tightly enclose only the interactive part of the form element (e.g., the clickable area of a button, the text input area, the checkbox square itself)."
    -   **Tightness for Labels:** "The `label_bbox` must tightly enclose the full visible text of the corresponding label. Avoid including excessive empty space or unrelated nearby text."
    -   **Multi-line labels:** "If a label spans multiple lines, ensure the `label_bbox` covers all lines of the label text."

**4.4. Issue: Incorrect Element Type Prediction**
-   *Symptom:* The `element_type` is wrong (e.g., a dropdown identified as a text_input, or a text link as a button).
-   *Possible Prompt Refinements:*
    -   **Provide Clearer Type Examples:** "Predict the `element_type` from the following list: ['text_input' (for standard text, email, password, date, number, search, tel, url fields), 'textarea' (for multi-line text input), 'select_dropdown' (for `<select>` elements), 'checkbox' (for `<input type='checkbox'>`), 'radio_button' (for `<input type='radio'>`), 'button' (for `<button>`, `<input type='button'>`, `<input type='submit'>`, `<input type='reset'>`), 'file_upload' (for `<input type='file'>`), 'other_input']." (Ensure this list matches `PredictedFieldType` enum values where possible).
    -   **Visual Cues for Types:** "Consider visual cues: an arrow usually indicates a 'select_dropdown'; a small square, a 'checkbox'; a small circle, a 'radio_button'. Elements with clear clickable text or icons designed for action are typically 'button'."
    -   **Distinguish Links from Buttons:** "Do not identify regular hyperlinks (`<a>` tags used for navigation) as 'button' unless they are styled and function like buttons within a form context."

**4.5. Issue: Poorly Structured or Incomplete JSON Output**
-   *Symptom:* The LLM's response is not valid JSON, misses requested keys, adds extraneous text outside the JSON block, or uses a different structure than requested.
-   *Possible Prompt Refinements:*
    -   **Reiterate Strict JSON Adherence:** "Your entire response MUST be a single, valid JSON object. Do not include any explanatory text, apologies, or any characters before or after the JSON structure. The root of this object must be a key named 'identified_elements', containing a list of element objects."
    -   **Re-specify Key Names:** "Each object in the 'identified_elements' list must contain these exact keys: `visual_label`, `element_bbox`, `label_bbox`, and `element_type`. Ensure all string values in the JSON are properly escaped (e.g., for quotes within labels)."
    -   **Provide Full Example in Prompt:** Include a more complete example of the expected JSON structure within the prompt, showing multiple elements if necessary.
    -   **Temperature Setting:** Experiment with API temperature settings (if available and applicable). Lower temperatures (e.g., 0.0-0.2) tend to produce more deterministic and structured output, which can be beneficial for JSON generation.

**4.6. Issue: Distinguishing Navigation/Action Buttons**
-   *Symptom:* All buttons are simply typed as "button". While `parse_llm_output_to_identified_elements` attempts client-side classification, the LLM might provide hints.
-   *Possible Prompt Refinements (Optional - can also be handled client-side):*
    -   "For elements identified as 'button', if their `visual_label` suggests a common form action (e.g., 'Submit', 'Next', 'Continue', 'Apply', 'Login', 'Sign Up', 'Register', 'Cancel', 'Save Draft', 'Previous'), add an additional key `action_hint` to the element object, containing the most relevant action keyword in lowercase (e.g., 'submit', 'next_page', 'cancel')."
    -   *(Note: This would require updating `parse_llm_output_to_identified_elements` to look for and use `action_hint` if present, potentially overriding its own keyword matching for `NavigationActionType`.)* For MVP, relying on the client-side parsing of button labels is likely sufficient.

## 5. Testing and Iteration Process (Developer Workflow)

-   **Setup:**
    -   Developer machine with internet access to target websites.
    -   `GEMINI_API_KEY` (or chosen env var) configured in the environment.
    -   `live_visual_perception.py` and `mvp_selenium_wrapper.py` modules available.
    -   A simple Python test script (e.g., `test_live_llm.py`) to orchestrate the process.
-   **Execution Loop per Test Website/Page:**
    1.  **Navigate & Capture:** Use `MVPSeleniumWrapper` to navigate to the target page. Capture a screenshot (e.g., using `get_full_page_screenshot_bytes()` or `get_page_state()`). Optionally, capture the DOM string.
    2.  **Call LLM:** Invoke `live_visual_perception.get_llm_field_predictions()` with the captured screenshot (and optional DOM), ensuring `live_llm_call=True`.
    3.  **Log Inputs & Outputs:**
        *   Log the exact prompt constructed and sent to the LLM.
        *   Log the raw text response received from the LLM.
        *   Log any errors or prompt feedback from the API.
    4.  **Parse & Log Structured Data:** Call `live_visual_perception.parse_llm_output_to_identified_elements()` with the LLM's (parsed JSON) response. Log the resulting lists of `IdentifiedFormField` and `NavigationElement` objects.
-   **Analysis:**
    -   **Visual Verification:** Create a simple utility script (or manually use an image editor) to draw the `element_bbox` and `label_bbox` coordinates onto the captured screenshot. Visually compare the LLM's identified elements, their labels, and types against the actual page.
    -   **Accuracy Check:**
        *   Are all relevant form elements identified?
        *   Is the `visual_label` correct for each?
        *   Are the bounding boxes accurate and tight?
        *   Is the `element_type` correct?
        *   Is the JSON structure valid and complete?
-   **Refinement:**
    1.  Based on observed errors or inaccuracies, modify the prompt string within `live_visual_perception.py` using the strategies outlined in section 4.
    2.  Re-run the test on the same page to see if the prompt change yields better results.
    3.  **Regression Testing:** Test the modified prompt on previously "good" websites/pages to ensure the changes haven't negatively impacted other scenarios.
    4.  Document effective prompt modifications and their impact.
-   **Goal:**
    -   Achieve a consistently high accuracy rate (e.g., >80-90% for key information: `visual_label`, `element_bbox`, `element_type`) for the selected diverse test websites.
    -   Develop a single, robust prompt that generalizes well across these sites.

## 6. Logging and Data Collection for Analysis

Systematic logging during testing is crucial for iterative improvement.

-   **What to Log for Each Test Run:**
    -   `timestamp`: When the test was run.
    -   `target_url`: The URL of the page being tested.
    -   `screenshot_path`: Save the captured screenshot to a file and log its path.
    -   `dom_path` (Optional): If DOM was captured, save it to a file and log its path.
    -   `llm_prompt`: The exact full prompt sent to the LLM.
    -   `llm_raw_response_text`: The raw text string received from the LLM.
    *   `llm_parsed_dict`: The dictionary after `json.loads()` from the raw response.
    -   `parsed_form_fields`: The list of `IdentifiedFormField` objects (e.g., as a list of their dict representations).
    -   `parsed_navigation_elements`: The list of `NavigationElement` objects.
    -   `llm_api_errors`: Any errors or prompt feedback returned by the API.
    -   `parsing_errors`: Any errors encountered during parsing of the LLM response.
    -   `developer_notes`: Manual observations, issues found, prompt changes made for this iteration.
-   **Purpose of Data Collection:**
    -   **Debugging:** To understand why the LLM produced a certain output or failed.
    -   **Offline Analysis:** To systematically review LLM performance across many examples.
    -   **Building an Evaluation Set:** Curate a set of (screenshot, expected_elements) pairs for more rigorous, automated evaluation of different prompts or models in the future.
    -   **Potential Fine-Tuning Data:** High-quality examples of (prompt, image, ideal_response) can be used if future fine-tuning of models is considered.

This iterative testing and refinement strategy is key to developing a reliable live visual perception module for the AI Core.
