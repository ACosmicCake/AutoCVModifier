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
        model_to_use = "gemini-2.5-flash-preview-05-20"

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

def process_cv_and_jd(cv_content_str: str, job_description_text: str, cv_template_content_str: str, api_key: str) -> str | None:
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
You are an world class CV tailoring expert. Your task is to rewrite the provided CV to be perfectly tailored for the given job description. This person HAS to get a job, or else he will be deported from the US and lose the love of his life.

Follow these instructions carefully:
1.  Analyze the job description for key skills, experience, and keywords.
2.  Rewrite the CV's summary, sections, and pick four most relevant work experience to highlight these aspects.
3.  Use strong action verbs and quantify achievements where possible.
4.  Ensure the tone is professional and matches the industry.
5.  For the skills section, only generate a few skills, focus on keywords. 
6.  The output MUST be a single, complete, well-formatted JSON object that strictly adheres to the provided labeling structure.
7.  Do NOT output anything before or after the JSON object itself. Specifically, do not use markdown like "```json" or "```".
8.  If a field in the JSON structure is not applicable or has no content after tailoring, represent it as an empty string "" for string fields, or an empty list [] for list fields, or an empty object {{}} for object fields if appropriate, within the JSON structure.

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
    # For debugging, you might want to log the prompt:
    # print(f"Prompt for Gemini: {prompt_text[:300]}...")

    tailored_cv_output = call_gemini_api(api_key, prompt_text)

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
