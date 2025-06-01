# Phase 3.1 Summary: Live LLM Visual Perception Upgrade

## 1. Phase 3.1 Overview

-   **Goal:** To significantly upgrade the AI Core's visual perception capability by integrating a live Multimodal LLM (specifically Google Gemini Pro Vision). This replaces the MVP's simulated visual perception, which was hardcoded for a single target website, with a dynamic, AI-driven approach to understanding web page layouts.
-   **Scope:** This phase encompassed:
    -   Research into Multimodal LLM selection (Gemini Pro Vision) and API usage.
    -   Enhancement of screenshotting utilities within the browser automation layer.
    -   Development of a new Python module (`live_visual_perception.py`) to interface with the live LLM, including prompt engineering and response parsing.
    -   Creation of a strategy document for testing the live LLM and refining prompts.
    -   Integration of this new live visual perception pipeline into the existing MVP orchestrator (`mvp_orchestrator.py`).

## 2. Key Modules and Developments

**2.1. `docs/ai_core/ai_core_llm_research_and_setup.md`**
-   **Summary:** This document detailed the selection of Google Gemini Pro Vision as the Multimodal LLM. It covered rationale (strong multimodal capabilities, structured JSON output potential, Google ecosystem), alternatives considered (e.g., GPT-4V), API access methods (Google AI Studio/Vertex AI), SDKs (`google-generativeai`, `google-cloud-aiplatform`), secure API key management (environment variables, no hardcoding), and verification via a test script (`check_llm_api.py`). Crucially, it outlined key API documentation insights for the visual perception task, including input formatting, initial prompt engineering strategies (task definition, elements to identify, information to extract, JSON output request with schema examples), anticipated response structures, and considerations for error handling, rate limits, and cost.

**2.2. `app/browser_automation/mvp_selenium_wrapper.py` Enhancements**
-   **Summary:** The `MVPSeleniumWrapper` was enhanced by adding a new method: `get_full_page_screenshot_bytes()`. This method utilizes the Chrome DevTools Protocol (CDP) to capture a screenshot of the entire scrollable page, which is often more comprehensive than viewport-only screenshots for full-page analysis by the LLM. The existing `get_page_state()` method (providing a viewport screenshot) was retained for flexibility. The `if __name__ == '__main__':` demo script was updated to test and showcase both screenshot methods, saving output images for developer verification.

**2.3. `app/ai_core/live_visual_perception.py` (New Module)**
-   **Purpose:** This new module is the core of the live visual perception upgrade. It interfaces with the Google Gemini Pro Vision API to identify and extract information about UI elements from web page screenshots.
-   **Key Functions:**
    -   `_configure_gemini()`: A helper function to manage the one-time configuration of the Gemini API key.
    -   `get_llm_field_predictions()`:
        -   Handles API key retrieval from environment variables (`GEMINI_API_KEY`).
        -   Constructs a detailed prompt for the LLM based on the research in `ai_core_llm_research_and_setup.md`. This prompt directs the LLM to identify form elements, their visual labels, bounding boxes for elements and labels, and predicted element types, requesting output in a specific JSON format.
        -   Prepares the image (screenshot bytes) and optional DOM string for the API call.
        -   Conditionally makes a live API call (if `live_llm_call=True`) or returns a hardcoded, simulated JSON response for development and testing without API usage.
        -   Retrieves the raw text response from the LLM.
    -   `_parse_bbox()`: A helper function to parse bounding box coordinate lists (expected as `[x_min, y_min, x_max, y_max]`) from the LLM response into `VisualLocation` objects (`x, y, width, height`), including validation.
    -   `parse_llm_output_to_identified_elements()`:
        -   Takes the raw (parsed from JSON string) dictionary output from `get_llm_field_predictions`.
        -   Transforms this data into lists of structured `IdentifiedFormField` and `NavigationElement` objects (from `app.common.ai_core_data_structures`).
        -   This includes mapping string element types from the LLM to `PredictedFieldType` enums and classifying buttons as navigation or general action elements based on label keywords (populating `NavigationActionType`).
        -   Assigns unique IDs (`uuid.uuid4()`) and placeholder confidence scores.
-   **Features:** The module embodies the prompt engineering strategies from the research phase, offers flexibility with live/simulated modes, and includes robust parsing logic for the LLM's JSON output (including handling markdown code fences).

**2.4. `docs/ai_core/live_llm_testing_and_prompt_refinement_strategy.md`**
-   **Summary:** This document provides a systematic approach for testing the `live_visual_perception.py` module on real websites. It includes:
    -   Selection criteria for diverse test websites with varying complexities.
    -   Recap of the initial LLM prompt.
    -   A detailed breakdown of anticipated LLM output issues (e.g., missed elements, incorrect labels, inaccurate bounding boxes, wrong element types, malformed JSON).
    -   Specific prompt refinement strategies to address each anticipated issue.
    -   A developer workflow for iterative testing: setup, execution loop (capture screenshot, call LLM, log, parse), analysis (visual verification, accuracy checks), and prompt refinement.
    -   A plan for logging test data (screenshots, prompts, responses, parsed objects, errors, notes) to build a dataset for analysis and potential future improvements.

**2.5. `app/orchestrator/mvp_orchestrator.py` Integration**
-   **Summary:** The `_call_ai_core` method within the `MVCOrchestrator` was significantly updated:
    -   It now uses `MVPSeleniumWrapper` to capture actual screenshot bytes and DOM strings from a live browser session initiated by the orchestrator.
    -   These live data are passed to `live_visual_perception.get_llm_field_predictions(..., live_llm_call=True)`, triggering a real API call to the multimodal LLM (if the API key is configured).
    -   The raw output from the LLM is then parsed by `live_visual_perception.parse_llm_output_to_identified_elements()` to produce lists of `IdentifiedFormField` and `NavigationElement` objects based on live visual data.
    -   **Crucially, these live-identified elements (which do not yet have DOM paths from this new perception module) are then fed into the *existing MVP-era* semantic matching (`mvp_perform_semantic_matching`) and action generation (`mvp_generate_text_fill_actions`) functions from `mvp_field_filler.py`.**
    -   Logging throughout `_call_ai_core` was enhanced to trace this new data flow and highlight the current stage of integration.

## 3. Summary of Achievements in Phase 3.1

-   **Live LLM Foundation:** Successfully established the foundational components for using a live Multimodal LLM (Gemini Pro Vision) for visual perception of web pages.
-   **Live Perception Module:** Developed `live_visual_perception.py`, capable of constructing sophisticated prompts, making calls to the Gemini API with image and optional DOM data, and parsing the structured JSON response.
-   **Data Transformation:** Implemented logic to transform the LLM's JSON output into the system's standardized `IdentifiedFormField` and `NavigationElement` data structures.
-   **Enhanced Screenshotting:** Upgraded `MVPSeleniumWrapper` with full-page screenshot capabilities, providing better visual context for the LLM.
-   **Orchestrator Integration:** Integrated this new live visual perception pipeline into the `MVCOrchestrator`, enabling it to process pages beyond the original hardcoded MVP target site using real-time AI analysis.
-   **Strategic Planning:** Created detailed strategies for LLM API usage, testing, and iterative prompt refinement.

## 4. Current State and Known Limitations

-   **Live Visual Perception is Active:** The system can now take a screenshot of any web page, send it to Gemini, and get back a list of visually identified UI elements with their labels, types, and bounding boxes. This is a major step forward from simulated perception.
-   **Grounding is Still MVP-Based (Critical Limitation):**
    -   The most significant limitation is that the **Visual Grounding** step – linking the visually identified elements from the live LLM to their actual, interactable DOM paths (XPaths, CSS selectors) on *new, arbitrary websites* – **has not yet been upgraded in this phase.**
    -   The `IdentifiedFormField` and `NavigationElement` objects generated by `live_visual_perception.py` currently have empty `dom_path_primary` and `dom_path_label` attributes.
    -   Consequently, when these objects are passed to the existing MVP-era `mvp_generate_text_fill_actions` function, it will be unable to generate executable `FILL_TEXT` actions because these require DOM paths. Similarly, navigation actions will lack DOM targets.
    -   **This means that while the system can "see" new pages, it cannot yet reliably "interact" with them beyond the original MVP target site (for which `mvp_visual_linker` had hardcoded grounding).**
-   **Semantic Matching is MVP-Based:** The `mvp_perform_semantic_matching` function (from `mvp_field_filler.py`) still relies on a hardcoded map of labels to semantic meanings, which is primarily relevant to the original MVP target site. Its effectiveness on diverse labels from new websites will be limited until it's also upgraded (likely in a subsequent phase).

## 5. Next Steps (Leading to Phase 3.2 - Live Visual Grounding)

-   The immediate and critical next phase is **"Upgrading AI Core: Live Visual Grounding."** This phase will focus on:
    -   Developing new techniques and/or leveraging further LLM capabilities to take the visually identified elements (output of `live_visual_perception.py`) and the actual page DOM (from `MVPSeleniumWrapper`).
    -   Implementing robust logic to accurately determine and populate `dom_path_primary` (e.g., XPaths, CSS selectors) for these elements on arbitrary web pages. This might involve strategies like:
        -   Analyzing proximity of visual bounding boxes to DOM element bounding boxes (obtained via JavaScript execution).
        -   Matching label text or other attributes to DOM element properties.
        -   Utilizing the browser's accessibility tree.
        -   Potentially making additional targeted LLM calls with combined visual and DOM snippets for specific elements if initial heuristics fail.
-   **Outcome of Next Phase:** Once live grounding is implemented, the `IdentifiedFormField` and `NavigationElement` objects will be fully populated with actionable DOM paths. This will enable the action generation logic (even the current MVP version) to become effective on a much wider range of websites, allowing the system to truly start filling and submitting forms on new sites.
-   **Subsequent Phases:** After live grounding, focus will shift to upgrading semantic matching to be dynamic (LLM-based), enhancing interaction logic for more complex elements (dropdowns, checkboxes beyond simple text fills), and refining the multi-step navigation and error handling capabilities of the Orchestration Engine.

Phase 3.1 has successfully modernized the "eyes" of the AutoApply system. Phase 3.2 will focus on giving it "hands" to interact with what it sees.
