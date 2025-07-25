# app/cv_utils.py
import os
# import sys # No longer needed as sys.exit is removed
import json
import requests
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

def call_gemini_api(api_key: str, prompt_text: str, model: str) -> str | None:
    """
    Calls the Gemini API with the provided prompt and API key.
    Uses the google.genai Client.
    """
    if "google" in model:
        try:
            client = genai.Client(api_key=api_key)
            # Model name as specified by user, without "models/" prefix for client.models.generate_content
            model_to_use = "gemini-2.5-pro"

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
    else:
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", api_key)  # Use environment variable if available
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
                data=json.dumps({
                    "model": model,
                    "messages": [
                        { "role": "user", "content": prompt_text }
                    ]
                })
            )
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            import traceback
            print(f"Error calling OpenRouter API: {e}")
            print(traceback.format_exc())
            return None

def generate_cover_letter(cv_json: str, job_description: str, api_key: str, model: str) -> str | None:
    """
    Generates a cover letter using the Gemini API.
    """
    prompt = f"""
As a career strategist, your task is to write a compelling cover letter based on the provided CV and job description.

**Guiding Principles:**
*   **Narrative of Value:** Don't just list skills. Weave a story that shows how the candidate's experience solves the employer's specific problems.
*   **Show, Don't Tell:** Instead of saying "experienced leader," describe a situation where the candidate led a team to success.
*   **Humble & Natural Tone:** Use straightforward, engaging, and humble language. Avoid jargon like "stakeholder," "visionary," or "pioneer."

**Instructions:**
1.  **Introduction:** Start with a strong opening that grabs the reader's attention and clearly states the purpose of the letter.
2.  **Body Paragraphs:**
    *   Connect the candidate's experience directly to the requirements of the job description.
    *   Highlight 2-3 key achievements from the CV that are most relevant to the role.
3.  **Conclusion:** End with a confident closing that reiterates the candidate's interest and includes a call to action.

**Input Data:**

**Tailored CV:**
```json
{cv_json}
```

**Job Description:**
```
{job_description}
```

Please generate the cover letter now.
"""
    return call_gemini_api(api_key, prompt, model=model)

def answer_question(cv_json: str, job_description: str, questions: list[str], api_key: str, model: str) -> list[str] | None:
    """
    Answers application questions using the Gemini API.
    """
    answers = []
    for question in questions:
        prompt = f"""
As a career strategist, your task is to answer the following application question based on the provided CV and job description.

**Guiding Principles:**
*   **Be Direct and Concise:** Provide a clear and straightforward answer to the question.
*   **Show, Don't Tell:** Use specific examples from the CV to support your answer.
*   **Maintain a Humble Tone:** Use natural and engaging language.

**Instructions:**
1.  Analyze the question and identify the key information being requested.
2.  Review the CV and job description to find relevant experiences and skills.
3.  Formulate a concise and compelling answer that directly addresses the question. Don't use bullet points or lists.
4.  Present the final output in a clear question-and-answer format. 

**Input Data:**

**Tailored CV:**
```json
{cv_json}
```

**Job Description:**
```
{job_description}
```

**Application Question:**
```
{question}
```

--------

**Output Format:**

Question 1:  [rewrite the question here]

Answer 1: [Your concise and compelling answer here] 

Question 2: [rewrite the question here]

Answer 2: [Your concise and compelling answer here] 

--------


Please provide the answer now.
"""
        answer = call_gemini_api(api_key, prompt, model=model)
        if answer:
            answers.append(answer)
        else:
            answers.append("Could not generate an answer for this question.")
    return answers

def process_cv_and_jd(cv_content_str: str, job_description_text: str, cv_template_content_str: str, api_key: str, model: str) -> str | None:
    """
    Processes the CV and Job Description using the Gemini API to tailor the CV.
    Returns the tailored CV as a JSON string, or None on failure.
    The cv_template_content_str is the content of CV_format.json.
    """
    if not cv_content_str:
        print("Error: CV content is missing for processing.")
        return None
    if not job_description_text:
        print("Error: Job Description is missing for processing.")
        return None
    if not api_key:
        print("Error: API key is missing for processing.")
        return None
    # cv_template_content_str can be empty, so no check for it here.

    prompt_text = f"""
You are an elite, best in the world technical recruiter and career strategist. Your task is to hyper-optimize a CV for a specific job description using advanced AI techniques. You will take the provided CV and job description, analyze them deeply, and generate a tailored CV in JSON format. 

**Guiding Principle: Dual-Optimization**
The resulting CV must succeed on two fronts simultaneously:
1.  **ATS Dominance**: Achieve a high relevance score by embedding essential keywords from the job description into the correct fields of the JSON structure.
2.  **Human Persuasion**: Captivate the human reader by presenting a clear, compelling narrative of value and impact. Use Langauage that is humble, straight forward, natural and engaging, do not use general jargon such as "stakeholder", "Visionary", "Pionneer", "Innovator", etc.

**Phase 1: Intelligence Gathering (Job Description Deconstruction)**
Forensically analyze the `JOB DESCRIPTION` to extract the following intelligence:
* **Job Title**: Pick only two key words for the job title of the role, no special characters.
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
    * Populate the `CV.Skills` array with a list of key objects.
    * For each object, define a `SkillCategory` (e.g., "Programming Languages", "Cloud & DevOps", "Databases", "Frameworks & Libraries", "Methodologies").
    * In the corresponding `Skill` array, list the specific skills the candidate possesses that are relevant to the job, drawn from your "High-Value Keywords" list.

5.  **Remaining Sections**: Accurately transfer the `PersonalInformation`, `Education`, and `Certifications` from the original CV into their corresponding sections in the JSON structure. Ensure formatting is clean and professional.

**Final Mandates & Output Format**:
* **Raw JSON Output**: The final output MUST be a single, raw, and valid JSON object. Do not include any text, comments, or markdown formatting (like ```json) before or after the JSON.
* **Strict Structural Adherence**: The final output must be a single JSON object that strictly follows the provided `LABELING STRUCTURE`, starting with the top-level `CV` key. All generated content must be placed in the correct nested fields as described above (e.g., `CV.SummaryOrObjective.Statement`, `CV.ProfessionalExperience[0].ResponsibilitiesAndAchievements`, `CV.Skills[0].Skill`).
* **Handle Empty Fields**: Use `""`, `[]`, or `{{}}` for any fields that are not applicable after tailoring, as specified in the structure.
* **Length**: The final CV PDF should be concise yet comprehensive. Longer is better. Ensure the JSON structure is not overly verbose but still captures all necessary details.


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
    # For debugging, you might want to log the prompt:
    # print(f"Prompt for Gemini: {prompt_text[:300]}...")

    tailored_cv_output = call_gemini_api(api_key, prompt_text, model)

    if tailored_cv_output:
        cleaned_output = tailored_cv_output.strip()

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
            print(f"Error: Gemini API output was not valid JSON after cleaning: {e}")
            print(f"Problematic output (first 500 chars): {cleaned_output[:500]}")
            return None
    else:
        print("Failed to get tailored CV from API in process_cv_and_jd (output was None).")
        return None
