# app/cv_utils.py
import os
# import sys # No longer needed as sys.exit is removed
import json
from google import genai # Changed import for Client pattern
from PyPDF2 import PdfReader
import docx
# from dotenv import load_dotenv # load_dotenv will be called in main.py

def get_api_key() -> str | None:
    """Retrieves the Google API key from environment variables."""
    # This function assumes that load_dotenv() has already been called (e.g., in main.py)
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment variables.")
        # The calling code (e.g., in main.py) should handle the case where API key is None.
    return api_key

def get_cv_from_text_file(filepath: str) -> str | None:
    """Reads CV content from a plain text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: CV file not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error reading text file {filepath}: {e}")
        return None

def get_cv_from_json_file(filepath: str) -> dict | None: # Returns dict
    """Reads CV content from a JSON file and parses it into a dictionary."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: CV JSON file not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}.")
        return None
    except Exception as e:
        print(f"Error reading JSON file {filepath}: {e}")
        return None

def get_cv_from_pdf_file(filepath: str) -> str | None:
    """
    Extracts text content from a PDF file.
    Returns a string containing the extracted text, or None if an error occurs.
    """
    try:
        text_content = []
        with open(filepath, 'rb') as f:
            reader = PdfReader(f)
            if reader.is_encrypted:
                try:
                    reader.decrypt('')
                except Exception as decrypt_error:
                    print(f"Error: Could not decrypt PDF {filepath}. Error: {decrypt_error}")
                    return None
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        if not text_content:
            print(f"Warning: No text extracted from PDF {filepath}.")
            return "" # Return empty string if no text, but file was processed
        return "\n".join(text_content)
    except FileNotFoundError:
        print(f"Error: PDF file not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error processing PDF file {filepath}: {e}")
        return None

def get_cv_from_docx_file(filepath: str) -> str | None:
    """
    Extracts text content from a DOCX file.
    Returns a string containing the extracted text, or None if an error occurs.
    """
    try:
        document = docx.Document(filepath)
        text_content = [para.text for para in document.paragraphs]
        if not text_content:
            print(f"Warning: No text extracted from DOCX {filepath}.")
            return "" # Return empty string if no text, but file was processed
        return "\n".join(text_content)
    except FileNotFoundError:
        print(f"Error: DOCX file not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error processing DOCX file {filepath}: {e}")
        return None

def call_gemini_api(api_key: str, prompt_text: str) -> str | None:
    """
    Calls the Gemini API with the provided prompt and API key.
    Uses the google.genai Client.
    """
    try:
        client = genai.Client(api_key=api_key)
        # Model name as specified by user, without "models/" prefix for client.models.generate_content
        model_to_use = "gemini-2.5-flash"

        response = client.models.generate_content( # Changed to client.models.generate_content
            model=model_to_use,
            contents=prompt_text
        )

        # Accessing the text response, ensuring parts and text exist
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        # Fallback for older API versions or different response structures if needed
        elif hasattr(response, 'text') and response.text: # Check if response.text exists and is not empty
             return response.text
        else:
            print("Warning: Gemini API response structure was not as expected or content was empty.")
            # Log more details if available, e.g., response.prompt_feedback if it exists on this response object
            if hasattr(response, 'prompt_feedback'):
                 print(f"Prompt Feedback: {response.prompt_feedback}")
            return None
    except Exception as e:
        # Log the full error for debugging, especially for API configuration or call issues.
        import traceback
        print(f"Error calling Gemini API (genai.Client in cv_utils): {e}")
        print(traceback.format_exc())
        return None

def process_cv_and_jd(cv_content_str: str, job_description_text: str, cv_template_content_str: str, api_key: str, iterations: int = 1) -> str | None:
    """
    Processes the CV and Job Description using the Gemini API to tailor the CV.
    If iterations > 1, it generates multiple variations and then synthesizes them.
    Returns the tailored CV as a JSON string, or None on failure.
    """
    if not all([cv_content_str, job_description_text, api_key]):
        print("Error: CV content, job description, or API key is missing.")
        return None

    if iterations == 1:
        # Existing logic for a single generation
        prompt_text = f"""
        You are an elite, Tier-1 technical recruiter and career strategist, operating with the precision of a surgeon. Your task is to re-architect the provided CV into an interview-generating machine, meticulously populating the target JSON structure.

        **Guiding Principle: Dual-Optimization**
        The resulting CV must succeed on two fronts simultaneously:
        1.  **ATS Dominance**: Achieve a high relevance score by embedding essential keywords from the job description into the correct fields of the JSON structure.
        2.  **Human Persuasion**: Captivate the human reader by presenting a clear, compelling narrative of value and impact. Use Langauage that is natural and engaging, do not use general jargon such as "stakeholder", ensure the CV stands out in a sea of applicants.

        **Phase 1: Intelligence Gathering (Job Description Deconstruction)**
        Forensically analyze the `JOB DESCRIPTION` to extract the following intelligence:
        * **Dealbreaker Qualifications**: The absolute, must-have skills, certifications, or years of experience.
        * **Primary Directives**: The top 3-4 key responsibilities of the role.
        * **Underlying Business Goal**: The core business problem this role solves (e.g., increase market share, reduce technical debt).
        * **High-Value Keywords**: Technical terms, methodologies (e.g., Agile, Scrum), and tools mentioned repeatedly.

        **Phase 2: Narrative Engineering (Candidate Re-Positioning)**
        1.  **Define the Core Narrative**: Formulate a single, powerful sentence that defines the candidate's professional story for this specific role.
        2.  **Establish the Unique Value Proposition (UVP)**: Condense the narrative into a headline that will serve as the opening of the summary.

        **Phase 3: Content Re-Engineering (Populating the JSON)**
        1.  **High-Impact Summary**: Rewrite the summary as a dense, 3-4 line paragraph that maps the candidate's qualifications to the "Primary Directives." The final text must populate the `CV.SummaryOrObjective.Statement` field.

        2.  **Experience Section**: Select relevant roles to feature in the `CV.ProfessionalExperience` array. For each role, transform the bullet points using the **Impact-First C.A.R.L. Method (Context, Action, Result, Learning)**.
            * **Start with the Result**: Lead with a quantifiable outcome (e.g., "Increased API response time by 40%...").
            * Each generated achievement statement must be a string within the `ResponsibilitiesAndAchievements` array for that specific job object.
            * Make sure to edit the Experience section so that is it embellishing job titles and responsibilities, inflating the candidate's skills and accomplishments.

        3.  **Project Highlights**: Populate the `CV.Projects` section with relevant projects that will impress the recruiter. Use the `Description` field for a brief overview and populate the `KeyContributionsOrTechnologiesUsed` array with impactful, result-oriented bullet points.

        4.  **Strategic Skills Matrix**: This is critical. You must format the skills according to the target structure.
            * Populate the `CV.Skills` array with a list of 2-3 key objects.
            * For each object, define a `SkillCategory` (e.g., "Programming Languages", "Cloud & DevOps", "Databases", "Frameworks & Libraries", "Methodologies").
            * In the corresponding `Skill` array, list the specific skills the candidate possesses that are relevant to the job, drawn from your "High-Value Keywords" list.

        5.  **Remaining Sections**: Accurately transfer the `PersonalInformation`, `Education`, and `Certifications` from the original CV into their corresponding sections in the JSON structure. Ensure formatting is clean and professional.

        **Final Mandates & Output Format**:
        * **Raw JSON Output**: The final output MUST be a single, raw, and valid JSON object. Do not include any text, comments, or markdown formatting (like ```json) before or after the JSON.
        * **Strict Structural Adherence**: The final output must be a single JSON object that strictly follows the provided `LABELING STRUCTURE`, starting with the top-level `CV` key. All generated content must be placed in the correct nested fields as described above (e.g., `CV.SummaryOrObjective.Statement`, `CV.ProfessionalExperience[0].ResponsibilitiesAndAchievements`, `CV.Skills[0].Skill`).
        * **Handle Empty Fields**: Use `""`, `[]`, or `{{}}` for any fields that are not applicable after tailoring, as specified in the structure.
        * **Length**: The final CV PDF should be concise yet comprehensive, exactly 2 pages when printed (or around 900 words), the JSON structure should not be artificially limited in length.


        Here is the original CV (which could be plain text, or a JSON string itself):
        --- BEGIN CV ---
        {cv_content_str}
        --- END CV ---

        Here is the target job description:
        --- BEGIN JOB DESCRIPTION ---
        {job_description_text}
        --- END JOB DESCRIPTION ---

        Generate the tailored CV based on this labeling structure. Ensure the output is ONLY the JSON object:
        --- BEGIN LABELING STRUCTURE ---
        {cv_template_content_str}
        --- END LABELING STRUCTURE ---

        Generate the hyper-optimized CV as a single, valid JSON object now.
        """
        tailored_cv_output = call_gemini_api(api_key, prompt_text)
        return _clean_and_validate_json(tailored_cv_output)

    # New logic for multi-step generation
    generated_variations = []
    for i in range(iterations):
        print(f"Generating CV variation {i+1}/{iterations}...")
        prompt_text = f"""
        You are an expert CV tailoring assistant. Your task is to rewrite the provided CV to be perfectly tailored for the given job description.

        Follow these instructions carefully:
        1.  Analyze the job description for key skills, experience, and keywords.
        2.  Rewrite the CV's summary, work experience, and other relevant sections to highlight these aspects.
        3.  Use strong action verbs and quantify achievements where possible.
        4.  Ensure the tone is professional and matches the industry.
        5.  For the skills section, only generate a few skills, focus on keywords.
        6.  The output MUST be a single, complete, well-formatted JSON object that strictly adheres to the provided labeling structure.
        7.  Do NOT output anything before or after the JSON object itself. Specifically, do not use markdown like "```json" or "```".
        8.  If a field in the JSON structure is not applicable or has no content after tailoring, represent it as an empty string "" for string fields, or an empty list [] for list fields, or an empty object {{{{}}}} for object fields if appropriate, within the JSON structure.

        Here is the original CV (which could be plain text, or a JSON string itself):
        --- BEGIN CV ---
        {cv_content_str}
        --- END CV ---

        Here is the target job description:
        --- BEGIN JOB DESCRIPTION ---
        {job_description_text}
        --- END JOB DESCRIPTION ---

        Generate the tailored CV based on this labeling structure. Ensure the output is ONLY the JSON object:
        --- BEGIN LABELING STRUCTURE ---
        {cv_template_content_str}
        --- END LABELING STRUCTURE ---

        Now, provide the tailored CV as a valid JSON object:
        """
        variation = call_gemini_api(api_key, prompt_text)
        if variation:
            cleaned_variation = _clean_and_validate_json(variation)
            if cleaned_variation:
                generated_variations.append(cleaned_variation)

    if not generated_variations:
        print("Failed to generate any valid CV variations.")
        return None

    # Synthesis Step
    print(f"Synthesizing final CV from {len(generated_variations)} variations...")
    synthesis_prompt = f"""
    You are an expert CV editor with a keen eye for detail and professional presentation.
    You have been provided with {len(generated_variations)} different versions of a CV, all tailored for the same job description.
    Your task is to analyze all versions, identify the best parts of each, and synthesize them into a single, final, superior CV.

    Instructions:
    1.  **Compare Summaries:** Choose the most impactful and well-written summary statement.
    2.  **Combine Experiences:** For each role in the professional experience section, select the most powerful and achievement-oriented bullet points from all versions. You can merge and rephrase points to create the strongest possible description of responsibilities and achievements.
    3.  **Select Best Skills:** Consolidate the skills sections to create a concise yet comprehensive list that is highly relevant to the job description.
    4.  **Ensure Cohesion:** The final CV must be coherent, with a consistent tone and style. It should not look like a patchwork of different documents.
    5.  **Strict JSON Output:** The final output MUST be a single, complete, well-formatted JSON object that strictly adheres to the provided labeling structure. Do not output any text before or after the JSON object.

    Here are the CV variations:
    --- BEGIN CV VARIATIONS ---
    """
    for i, var in enumerate(generated_variations):
        synthesis_prompt += f"\n--- VARIATION {i+1} ---\n{var}\n"
    synthesis_prompt += "--- END CV VARIATIONS ---\n"

    synthesis_prompt += f"""
    Here is the labeling structure you MUST follow for the final output:
    --- BEGIN LABELING STRUCTURE ---
    {cv_template_content_str}
    --- END LABELING STRUCTURE ---

    Now, provide the final, synthesized CV as a single, valid JSON object:
    """

    final_cv = call_gemini_api(api_key, synthesis_prompt)
    return _clean_and_validate_json(final_cv)

def _clean_and_validate_json(json_string: str | None) -> str | None:
    """Helper function to clean and validate a JSON string from the API."""
    if not json_string:
        return None

    cleaned_output = json_string.strip()

    # More robust cleaning for potential markdown and other unwanted prefixes/suffixes
    if cleaned_output.startswith("```json"):
        cleaned_output = cleaned_output[len("```json"):]
    elif cleaned_output.startswith("```"): # Catch if only ``` is present
        cleaned_output = cleaned_output[len("```"):]

    if cleaned_output.endswith("```"):
        cleaned_output = cleaned_output[:-len("```")]

    cleaned_output = cleaned_output.strip() # Strip again after potential modifications

    try:
        json.loads(cleaned_output) # Validate if the cleaned output is valid JSON
        return cleaned_output
    except json.JSONDecodeError as e:
        print(f"Error: API output was not valid JSON after cleaning: {e}")
        print(f"Problematic output (first 500 chars): {cleaned_output[:500]}")
        return None
