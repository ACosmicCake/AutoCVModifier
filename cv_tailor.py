# cv_tailor.py
# Main script for the AI-powered CV tailoring program.

import os
from dotenv import load_dotenv
import sys
import json # New import
import google.generativeai as genai # New import

def get_api_key() -> str | None:
    """Loads the Google API key from environment variables or .env file."""
    load_dotenv()
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found.")
        print("Please set it as an environment variable or in a .env file.")
        sys.exit(1) # Exit if key is not found
    return api_key

def get_cv_from_text_file(filepath: str) -> str | None:
    """Reads CV content from a plain text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: CV file not found at {filepath}")
        return None

def get_cv_from_json_file(filepath: str) -> dict | None:
    """Reads CV content from a JSON file and parses it into a dictionary."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f) # Parses JSON into a Python dictionary
    except FileNotFoundError:
        print(f"Error: CV JSON file not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}. Please ensure it's valid JSON.")
        return None

def get_job_description_from_user_paste() -> str:
    """Gets job description by asking the user to paste it into the console."""
    print("\nPaste the job description below. Press Ctrl+D (Unix/Linux) or Ctrl+Z then Enter (Windows) when done:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError: # Detects Ctrl+D or Ctrl+Z
            break
        lines.append(line)
    return "\n".join(lines)

def get_job_description_from_file(filepath: str) -> str | None:
    """Reads job description content from a plain text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Job description file not found at {filepath}")
        return None

def call_gemini_api(api_key: str, prompt_text: str) -> str | None:
    """
    Calls the Gemini API with the provided prompt and API key.

    Args:
        api_key: The Google API key.
        prompt_text: The complete prompt to send to the model.

    Returns:
        The AI-generated text response, or None if an error occurs.
    """
    try:
        # Configure the generative AI library with the API key
        # This only needs to be done once if the key doesn't change,
        # but doing it here encapsulates key usage within this function.
        genai.configure(api_key=api_key)

        # Initialize the generative model
        # For more options, see https://ai.google.dev/tutorials/python_quickstart
        model = genai.GenerativeModel('gemini-pro')

        # Generate content
        response = model.generate_content(prompt_text)

        return response.text
    except Exception as e:
        # Includes google.api_core.exceptions.GoogleAPIError and other potential errors
        print(f"Error calling Gemini API: {e}")
        return None

def main():
    print("--- AI-Powered CV Tailoring Program ---")
    api_key = get_api_key()
    if not api_key: # get_api_key now exits on failure, but good practice to check
        return
    print("Successfully loaded API key.")

    cv_data = None
    job_description_text = None
    cv_data_for_prompt = None # Initialize here

    # 1. Get CV Data
    print("\n--- Step 1: Provide Your CV ---")
    cv_input_choice = input("How would you like to provide your CV? (json / text / skip): ").strip().lower()
    if cv_input_choice == 'json':
        cv_filepath = input("Enter path to your CV JSON file (e.g., my_cv.json): ").strip()
        cv_data = get_cv_from_json_file(cv_filepath) # cv_data is a dict
        if cv_data:
            print(f"Successfully loaded CV from {cv_filepath}")
            cv_data_for_prompt = json.dumps(cv_data, indent=2) # Convert dict to JSON string
    elif cv_input_choice == 'text':
        cv_filepath = input("Enter path to your CV text file (e.g., my_cv.txt): ").strip()
        cv_data = get_cv_from_text_file(cv_filepath) # cv_data is a string
        if cv_data:
            print(f"Successfully loaded CV from {cv_filepath}")
            cv_data_for_prompt = cv_data # Already a string
    elif cv_input_choice == 'skip':
        print("CV input skipped.")
    else:
        print("Invalid choice for CV input. Skipping.")

    # 2. Get Job Description
    print("\n--- Step 2: Provide Job Description ---")
    jd_input_choice = input("How would you like to provide the Job Description? (paste / text / skip): ").strip().lower()
    if jd_input_choice == 'paste':
        job_description_text = get_job_description_from_user_paste()
        if job_description_text:
            print("Successfully received job description via paste.")
    elif jd_input_choice == 'text':
        jd_filepath = input("Enter path to the job description text file (e.g., job_description.txt): ").strip()
        job_description_text = get_job_description_from_file(jd_filepath)
        if job_description_text:
            print(f"Successfully loaded job description from {jd_filepath}")
    elif jd_input_choice == 'skip':
        print("Job description input skipped.")
    else:
        print("Invalid choice for job description input. Skipping.")

    if cv_data_for_prompt and job_description_text: # Check cv_data_for_prompt now
        print("\n--- Step 3: Processing ---")
        
        # Refined prompt construction
        prompt_text = f"""
You are an expert CV tailoring assistant. Your task is to rewrite the provided CV to be perfectly tailored for the given job description.

Follow these instructions carefully:
1.  Analyze the job description for key skills, experience, and keywords.
2.  Rewrite the CV's summary and work experience sections to highlight these aspects.
3.  Use strong action verbs and quantify achievements where possible.
4.  Ensure the tone is professional and matches the industry.
5.  The output should be a complete, well-formatted CV. Do not output anything else before or after the CV content itself.

Here is the original CV:
--- BEGIN CV ---
{cv_data_for_prompt}
--- END CV ---

Here is the target job description:
--- BEGIN JOB DESCRIPTION ---
{job_description_text}
--- END JOB DESCRIPTION ---

Now, please provide the tailored CV:
"""
        print(f"Generated prompt (first 100 chars): {prompt_text[:100]}...")

        print("Calling Gemini API...")
        tailored_cv_output = call_gemini_api(api_key, prompt_text)

        if tailored_cv_output:
            print("\n--- Step 4: Tailored CV Output ---")
            print(tailored_cv_output)
        else:
            print("\nFailed to get tailored CV from API.")

        # Placeholder for saving output (can be a future step)
        # print("\nTODO: Save the tailored CV to a file.")

    else:
        print("\nSkipping processing as either CV or Job Description is missing.")

    print("\n--- Program End ---")

if __name__ == "__main__":
    main()
