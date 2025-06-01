# AI Core: Multimodal LLM Research and Setup Guide

## 1. Multimodal LLM Selection

-   **Chosen LLM:** Google Gemini Pro Vision
    -   Specific Model Endpoint (example): `gemini-pro-vision` (when using the `google-generativeai` SDK) or through Vertex AI's model registry.
-   **Rationale:**
    -   **Strong Multimodal Capabilities:** Gemini Pro Vision is designed to understand and process both image and text inputs simultaneously, which is essential for analyzing web page screenshots alongside potential DOM context.
    -   **Structured JSON Output:** The model can be prompted to return responses in structured formats like JSON, which is crucial for parsing identified UI elements, their labels, bounding boxes, and types programmatically.
    -   **Google Ecosystem & Infrastructure:** Being a Google product, it integrates well with other Google Cloud services (like Vertex AI for MLOps, Google Cloud Storage for image storage) and benefits from Google's ongoing research and robust infrastructure.
    -   **Availability and API Access:** Google provides SDKs and clear API access patterns.
-   **Alternatives Considered (Briefly):**
    -   **OpenAI's GPT-4V(ision):** A strong contender with similar multimodal capabilities. The choice of Gemini might be influenced by existing cloud provider preferences, specific API features, or pricing models at the time of detailed implementation.
    -   **Other domain-specific models:** While powerful, general-purpose multimodal models like Gemini are preferred for their flexibility in handling diverse web page layouts without requiring specific pre-training for UI elements initially.
-   **Key Capabilities Required & Verified (Conceptually from Documentation):**
    -   **Image Input:** Accepts image data, typically as PNG or JPEG bytes, often passed as a base64 encoded string or directly as part of a multi-part prompt. (Verified via Gemini API documentation).
    -   **Text Input:** Accepts text prompts that can include contextual information (e.g., snippets of DOM, instructions for the task). (Verified).
    -   **Structured Output (JSON):** Can be instructed via prompting to return output in a JSON format. The reliability and consistency of this JSON structure depend heavily on prompt engineering. (Verified, a common technique for LLMs).
    -   **Bounding Box Identification:** While not explicitly "drawing" bounding boxes, LLMs like Gemini can be prompted to return coordinate data (e.g., `[x_min, y_min, x_max, y_max]` or `[x, y, width, height]`) based on visual analysis.

## 2. API Access and SDK Configuration

-   **API Provider:** Google Cloud (either via Google AI Studio for direct Gemini API access or Vertex AI for managed model endpoints).
-   **Client Library/SDK:**
    -   `google-generativeai`: For direct access to the Gemini API.
    -   `google-cloud-aiplatform`: For accessing Gemini models deployed or available via Vertex AI.
    -   **Confirmation:** These libraries were included in the `mvp_infrastructure_setup_guide.md` and should be part of the project's `requirements.txt`.
-   **Authentication:**
    -   **Method:**
        -   **API Keys:** Generated from Google AI Studio. Suitable for rapid prototyping and direct API calls.
        -   **Service Account Credentials (via Application Default Credentials - ADC):** The recommended method for applications running on Google Cloud (e.g., GCE, Cloud Run, GKE) or for local development when interacting with Vertex AI. `gcloud auth application-default login` is used for local ADC setup.
    -   **Secure Storage:**
        -   **API Keys:** Must be stored securely. **NEVER hardcode API keys in source code.** Use environment variables (e.g., `GOOGLE_API_KEY`) or a secret management service (like Google Secret Manager or HashiCorp Vault).
        -   **Service Account Keys:** If a JSON key file is downloaded for a service account, it must also be stored securely and its path typically referenced via an environment variable (e.g., `GOOGLE_APPLICATION_CREDENTIALS`).
-   **Verification:**
    -   The `scripts/check_llm_api.py` script, created as part of the MVP setup (`mvp_infrastructure_setup_guide.md`), serves as the primary method to confirm that the development environment is correctly configured for authentication and can reach the Google LLM APIs.

## 3. Key API Documentation Insights for Visual Perception Task

This section outlines how the chosen LLM API (Gemini Pro Vision) would be used for identifying form elements.

-   **Input Formatting:**
    -   **Image:**
        -   Preferred formats: PNG, JPEG.
        -   Transmission: Typically as a base64 encoded string or raw bytes within a multi-part prompt structure. The `google-generativeai` SDK handles Python PIL Images directly.
        -   Max resolution/size: Refer to official Gemini documentation for current limits (e.g., image resolution, file size in MB). These limits are important to avoid errors.
    -   **Text (DOM/HTML Context - Optional but potentially useful):**
        -   If providing DOM snippets or the full DOM (though full DOM might exceed token limits for large pages), it would be included as a text part in a multi-part prompt alongside the image.
        -   Strategy: For MVP, we might start with image-only and progressively add relevant DOM snippets if it improves accuracy for complex cases. The risk is exceeding token limits or making the prompt too complex.

-   **Prompt Engineering Strategies (Initial Thoughts for UI Element Detection):**
    -   **Role Setting/Task Definition:** Begin the prompt by clearly defining the LLM's role.
        *   Example: "You are an expert AI assistant specialized in analyzing web page screenshots to identify and locate user interface elements for web automation."
    -   **Elements to Identify:** Specify the types of form elements the system is interested in.
        *   Example: "Focus on common form elements including text input fields (single-line and multi-line textareas), email inputs, phone inputs, dropdowns/selects, checkboxes, radio buttons, and interactive buttons (like submit, next, cancel)."
    -   **Information to Extract per Element:** Detail the specific pieces of information required for each identified element.
        *   `visual_label_text`: The visible text label associated with the form element. If no direct label, infer from placeholder or surrounding text.
        *   `element_bbox`: Bounding box coordinates for the interactive element itself (e.g., the input area, the button area). Format: `[x_min, y_min, x_max, y_max]` relative to image dimensions (0,0 at top-left).
        *   `label_bbox`: Bounding box coordinates for the visual label corresponding to the element. Format: `[x_min, y_min, x_max, y_max]`.
        *   `predicted_element_type`: A standardized type string (e.g., "text_input", "textarea", "dropdown", "checkbox", "radio_button", "button").
    -   **Output Format Request (Crucial):** Explicitly request the output in a structured JSON format. Providing an example of the desired schema within the prompt can significantly improve consistency.
        *   Example: "Return your findings as a JSON object. The root object should have a single key 'identified_elements', which is a list of objects. Each object in the list should represent one identified UI element and must contain the following keys: 'visual_label_text', 'element_bbox', 'label_bbox', and 'predicted_element_type'."
    -   **Contextual Clues (Optional):**
        *   If providing DOM snippets: "Consider the provided HTML snippets for additional context if available, but prioritize visual identification from the screenshot."
    -   **Conceptual Prompt Snippet (Combining elements):**
        ```text
        "You are an expert AI assistant specialized in analyzing web page screenshots to identify user interface elements for web automation.
        Analyze the provided screenshot of a web page.
        Identify all common form elements such_as text inputs (single-line and multi-line textareas), email inputs, phone inputs, dropdowns/selects, checkboxes, radio buttons, and interactive buttons (like submit, next, cancel).
        For each element you identify, provide the following information:
        1.  `visual_label_text`: The visible text label clearly associated with the form element. If no direct label, try to infer from placeholder text or nearby text that functions as a label. If the element is a button, this should be the button's visible text.
        2.  `element_bbox`: The bounding box coordinates [x_min, y_min, x_max, y_max] for the interactive element itself (e.g., the clickable area of a button, the input area of a text field). Coordinates should be normalized to image dimensions if possible, or clearly specified as pixel values.
        3.  `label_bbox`: The bounding box coordinates [x_min, y_min, x_max, y_max] for the visual label corresponding to the element. If the element is a button and its text is within `element_bbox`, `label_bbox` can be the same as `element_bbox`.
        4.  `predicted_element_type`: A standardized type string from this list: ['text_input', 'textarea', 'dropdown', 'checkbox', 'radio_button', 'button', 'email_input', 'phone_input', 'other_input'].

        Return this information as a single JSON object. The root object must have a single key named 'identified_elements'. The value of 'identified_elements' must be a list of JSON objects, where each object represents one identified UI element and strictly adheres to the keys listed above.
        Example of a single element object:
        {
            "visual_label_text": "First Name",
            "element_bbox": [100, 50, 300, 80],
            "label_bbox": [20, 50, 90, 80],
            "predicted_element_type": "text_input"
        }
        Ensure your entire response is only this JSON object."
        ```

-   **Response Structure (Anticipated):**
    -   Based on the prompt, the system would expect a JSON string that can be parsed into a Python dictionary like:
        ```json
        {
            "identified_elements": [
                {
                    "visual_label_text": "First Name",
                    "element_bbox": [100, 50, 300, 80],
                    "label_bbox": [20, 50, 90, 80],
                    "predicted_element_type": "text_input"
                },
                {
                    "visual_label_text": "Submit",
                    "element_bbox": [100, 100, 250, 140],
                    "label_bbox": [100, 100, 250, 140],
                    "predicted_element_type": "button"
                }
                // ... more elements
            ]
        }
        ```
-   **Handling Errors and Limits:**
    -   **Common Error Codes:** Familiarize with API-specific error codes (e.g., 429 for rate limits, 400 for bad requests/invalid image, 500 for server-side errors). The application should handle these gracefully.
    -   **Rate Limits:** Be aware of requests per minute (RPM) or tokens per minute (TPM) limits for the chosen API. Implement client-side rate limiting or use SDKs that handle retries with exponential backoff.
    -   **Retries:** For transient errors (e.g., 5xx server errors, rate limits), implement an exponential backoff retry strategy.
    -   **Token Limits:** Prompts (text + image data representation) and responses consume tokens. Large images or extensive DOM text can exceed limits. Optimize prompt length and image size/resolution if necessary.
-   **Cost Model:**
    -   Review the pricing structure for Gemini Pro Vision (or chosen model on Vertex AI).
    -   Costs are typically based on the number of images processed, the amount of text in the prompt (input characters/tokens), and the amount of text generated (output characters/tokens). Vision models might have a per-image cost plus text token costs.
    -   Keep track of API usage during development and testing to manage costs.

## 4. Next Steps Confirmation

-   This research and the decisions documented herein directly inform the development of the `live_visual_perception.py` module (or the module that will make actual calls to the multimodal LLM, replacing `mvp_visual_linker.py`'s simulation for non-target URLs or enhancing it).
-   The immediate next practical step in implementing a live AI core would be to develop a utility for capturing actual screenshots of web pages using the browser automation layer (`MVPSeleniumWrapper`). This screenshot can then be passed to the live LLM.
-   Following that, a module will be developed to make live calls to the Gemini API, incorporating the prompt strategies discussed and parsing the actual JSON response.
