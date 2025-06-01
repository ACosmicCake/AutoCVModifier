# Research on LLM and Prompt Strategies for Semantic Field Matching

## 1. Introduction

**Purpose:**
This document outlines the research and proposed strategies for using Large Language Models (LLMs) to perform semantic matching. The goal is to accurately map the visually identified labels of form fields (obtained from the visual perception module) to a predefined schema of semantic keys (e.g., `user.firstName`, `user.address.street`). This capability is crucial for understanding the meaning of form fields encountered on diverse websites.

**Goal:**
To enable accurate, adaptable, and context-aware understanding of form field meanings, moving beyond hardcoded mappings (like `MVP_SEMANTIC_MAP` in `mvp_field_filler.py`) and leveraging the natural language understanding capabilities of LLMs.

## 2. LLM Choice Considerations

**Primary Candidates:**
-   **Google Gemini Pro:** A highly capable multimodal model, but its text-only capabilities are also strong and can be accessed efficiently. If already integrated for vision, using its text processing features provides consistency.
-   **Google PaLM 2 (e.g., `text-bison` on Vertex AI):** Specifically optimized for text-based tasks, known for good performance in classification, summarization, and Q&A. Often offers a good balance of performance and cost.
-   **OpenAI GPT Series (e.g., GPT-3.5-turbo, GPT-4):** Powerful models with strong text understanding and instruction-following capabilities.

**Decision Criteria:**
-   **Accuracy for Classification:** The primary task is to classify a field label into one of the predefined semantic keys.
-   **Context Handling:** Ability to effectively use provided context (field type, nearby labels, DOM attributes) to disambiguate and improve accuracy.
-   **Cost:** Price per token (input and output) and overall cost for the expected volume of calls.
-   **Latency:** Speed of response, as this can impact the overall user experience of the automation.
-   **Ease of Prompting/Fine-Tuning:** How well the model responds to zero-shot or few-shot prompting for this task, and the feasibility of fine-tuning if required later.
-   **Structured Output Generation:** Reliability in generating responses in the requested format (e.g., JSON).

**Initial Recommendation:**
-   Start with **Gemini Pro** (if using its text capabilities) or a cost-effective and performant **PaLM 2 model (e.g., `text-bison@002` or latest stable version on Vertex AI)**.
-   These models offer a good starting point due to their strong language understanding, integration within the Google Cloud ecosystem (aligning with potential Gemini Vision use), and generally good performance on structured output tasks with appropriate prompting.
-   Benchmarking against other models (like GPT series) might be necessary if initial results with the chosen Google model do not meet accuracy or cost-effectiveness targets.

## 3. Context Provision to LLM for Semantic Matching

To enable the LLM to make accurate semantic matches, providing relevant context alongside the primary field label is crucial.

-   **Primary Input:**
    -   `visual_label_text`: The text label associated with the form field, as identified by the visual perception module (e.g., "First Name", "Email Address", "Zip Code").

-   **Key Secondary Contextual Inputs (to be included in the prompt):**
    -   `predicted_field_type`: The type of the field as predicted by the visual perception module (e.g., `TEXT_INPUT`, `EMAIL_INPUT`, `DROPDOWN`, `CHECKBOX`). This helps the LLM understand the nature of the expected data.
    -   `target_semantic_keys`: The complete list of predefined semantic keys that the LLM must choose from (e.g., `["user.firstName", "user.lastName", "user.email.primary", "user.address.street", "user.address.postalCode", "application.startDate", "custom.field_xyz"]`). This frames the task as a classification problem.
    -   **(Optional but Recommended) Key HTML Attributes:** If available from the visual grounding step, attributes of the input field can be highly informative:
        -   `id`: e.g., "fname", "userEmail"
        -   `name`: e.g., "firstName", "email"
        -   `placeholder`: e.g., "Enter your first name"
        -   `aria-label`: Explicit accessible name.
        These attributes often contain semantic clues.
    -   **(Optional for Ambiguity Resolution) Snippets of Nearby DOM Text / Other Labels:**
        -   If a label is ambiguous (e.g., "Date"), providing text of nearby labels (e.g., "Start Date" for a previous field, "End Date" for a following field) can help the LLM disambiguate.
        -   This can be complex to manage in the prompt but powerful for specific cases.

## 4. Prompt Engineering Strategies

The effectiveness of the LLM will heavily depend on the quality of the prompt.

-   **Core Task Definition for LLM:**
    -   Frame the task clearly as a classification or mapping task.
    -   Instruct the LLM to act as an expert system for understanding web forms.
    -   Example: "You are an expert AI assistant. Your task is to analyze the provided information about a form field from a web page and map it to the most appropriate semantic category from a given list of categories."

-   **Zero-Shot Prompting (Initial Approach):**
    -   **Detailed Instructions:**
        -   Clearly explain the input fields being provided (label text, field type, HTML attributes).
        -   Clearly explain the expected output format (JSON with specific keys).
        -   Provide the full list of `target_semantic_keys` and instruct the LLM to choose only from this list or a designated "no match" value.
    -   **Inputs to Include in Prompt (Example Structure):**
        ```text
        Visual Label Text: "{visual_label_text}"
        Predicted Field Type: "{predicted_field_type}"
        HTML Attributes (if available):
          id: "{id_attribute}"
          name: "{name_attribute}"
          placeholder: "{placeholder_attribute}"
          aria-label: "{aria_label_attribute}"

        Available Semantic Categories:
        {target_semantic_keys_json_array}
        ```
    -   **Explicit Output Format Request:**
        -   "Respond with a single JSON object containing two keys: 'semantic_key' and 'confidence_score'.
        -   The 'semantic_key' must be one of the provided 'Available Semantic Categories' or 'null' if no suitable category is found.
        -   The 'confidence_score' should be a float between 0.0 and 1.0, representing your confidence in the mapping."
    -   **Conceptual Zero-Shot Prompt Snippet:**
        ```text
        "You are an expert AI system that maps web form field information to a predefined list of semantic categories.

        Field Information:
        - Visual Label: "{visual_label_text}"
        - Predicted Type: "{predicted_field_type_str}"
        - HTML ID: "{html_id}"
        - HTML Name: "{html_name}"
        - HTML Placeholder: "{html_placeholder}"

        Predefined Semantic Categories:
        ["user.firstName", "user.lastName", "user.email.primary", "user.address.postalCode", "custom.reference_number", "other.unspecified"]

        Based on all the provided field information, choose the single most appropriate semantic category from the list above.
        If no category is a good fit, choose "other.unspecified" or null.

        Return your answer as a JSON object with the following keys:
        {{
          "semantic_key": "CHOSEN_CATEGORY_OR_NULL",
          "confidence_score": YOUR_CONFIDENCE_SCORE_0_TO_1
        }}
        Ensure your entire response is only this JSON object."
        ```

-   **Few-Shot Prompting (As an Enhancement if Zero-Shot is Insufficient):**
    -   **Benefits:** Can significantly improve accuracy for ambiguous labels, non-standard terminology, or if the LLM struggles with the desired mapping style or confidence scoring.
    -   **Method:** Include 2-5 examples (shots) of input field information and the desired JSON output directly within the prompt before presenting the actual field to be classified.
    -   **Example of a Few-Shot Addition to the Prompt:**
        ```text
        Here are some examples:

        Example 1:
        Field Information:
        - Visual Label: "Given Name"
        - Predicted Type: "text_input"
        - HTML ID: "givenName123"
        - HTML Name: "gn"
        - HTML Placeholder: "Your first name"
        Predefined Semantic Categories: ["user.firstName", "user.lastName", "user.email.primary"]
        Output:
        {{
          "semantic_key": "user.firstName",
          "confidence_score": 0.95
        }}

        Example 2:
        Field Information:
        - Visual Label: "Comment"
        - Predicted Type: "textarea"
        - HTML ID: "userComment"
        - HTML Name: "comment"
        - HTML Placeholder: ""
        Predefined Semantic Categories: ["user.firstName", "application.notes", "other.unspecified"]
        Output:
        {{
          "semantic_key": "application.notes",
          "confidence_score": 0.8
        }}

        Now, classify the following field:
        Field Information:
        ... (actual field to classify) ...
        Predefined Semantic Categories: ...
        Output:
        ```
    -   **Selection of Examples:** Choose examples that are representative of common cases, ambiguous cases you want to guide the LLM on, and cases demonstrating the desired "no match" behavior.

-   **Handling Ambiguity (e.g., "Email" vs. "Work Email"):**
    -   **Strategy:** If the broader page context is available (e.g., other field labels already processed or identified on the page), this can be fed into the prompt for the specific ambiguous field.
    -   **Example Prompt Snippet for Disambiguation:**
        ```text
        "Context: The form also contains a field explicitly labeled 'Work Email'.

        Field Information to Classify:
        - Visual Label: "Email"
        - Predicted Type: "email_input"
        ...
        Predefined Semantic Categories: ["user.email.primary", "user.email.work", "user.email.personal"]
        Output:
        ..."
        ```
    -   **Expected LLM Behavior:** The LLM should use the context to infer that "Email" in this case likely refers to `user.email.personal` or `user.email.primary`, not `user.email.work`.

-   **Handling No Match / Out-of-Schema Fields:**
    -   **Instruction to LLM:** Clearly instruct the LLM what to output if no category from the `target_semantic_keys` list is appropriate.
        -   Example: "If none of the 'Available Semantic Categories' are a suitable match for the field label, return `null` (or a specific string like 'other.unspecified' or 'custom.field') for the 'semantic_key'."
    -   **Importance:** This prevents the LLM from "forcing" a field into an incorrect category, which can be worse than no match. Unmatched fields can be flagged for user review or handled differently.

## 5. Expected Output Format from LLM

A consistent and machine-parsable output format is essential.

-   **JSON Structure:** The LLM should be prompted to return a single JSON object (not a string containing JSON, if possible, though often it's a JSON string that needs parsing).
    ```json
    {
      "semantic_key": "CHOSEN_KEY_FROM_PROVIDED_LIST_OR_NULL_OR_DESIGNATED_NO_MATCH_KEY",
      "confidence_score": 0.85
    }
    ```
    -   `semantic_key`: The chosen key from the `target_semantic_keys` list, or `null` / a specific "no match" key (e.g., `other.unspecified`).
    -   `confidence_score`: A float between 0.0 and 1.0 indicating the LLM's confidence in its mapping.
-   **Importance of LLM-Provided Confidence Score:**
    -   While LLM confidence scores can sometimes be uncalibrated, they can still be useful.
    -   Low confidence scores can be used by the Orchestration Engine to flag mappings for mandatory user review, even if a semantic key was assigned.
    -   Helps in prioritizing which fields to focus on for manual verification during testing and feedback collection.

## 6. Iteration and Evaluation

-   **Iterative Refinement:** The effectiveness of any prompt strategy will only be known through testing on diverse, real-world examples. Expect to iterate on:
    -   The clarity and specificity of instructions.
    -   The amount and type of context provided.
    -   The examples used in few-shot prompts (if implemented).
    -   The list of `target_semantic_keys` itself.
-   **Metrics for Evaluation:**
    -   **Accuracy:** Percentage of fields correctly mapped to the intended semantic key.
    -   **Precision/Recall/F1-score per Semantic Key:** Especially for important or commonly confused keys.
    -   **"No Match" Accuracy:** How well the LLM correctly identifies fields that do not fit any predefined category (i.e., correctly returns `null` or the designated "no match" key).
    -   **Confidence Score Calibration (Qualitative):** Do higher confidence scores from the LLM generally correlate with more accurate mappings?
    -   **Error Analysis:** Categorize common error types (e.g., mapping to a related but incorrect key, failing to find a match when one exists, hallucinating new keys not in the provided list).

## 7. Impact on Development

-   This research directly informs the implementation of the `live_semantic_matcher.py` module. Specifically, it guides:
    -   The construction of prompts sent to the LLM.
    -   The handling of context provided to the LLM.
    -   The parsing and interpretation of the LLM's JSON response.
-   It also underscores the importance of the next immediate step: **defining the comprehensive list of `target_semantic_keys`** that will form the schema for user profiles and application-specific data. This list is fundamental to the entire semantic matching process.

By employing these strategies, the aim is to create a semantic matching module that is significantly more flexible and accurate than the MVP's hardcoded approach, enabling AutoApply to understand a wider variety of forms.
