# cv_tailor.py
# Main script for the AI-powered CV tailoring program.

import os
from dotenv import load_dotenv
import sys
import json # New import

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

def main():
    print("--- AI-Powered CV Tailoring Program ---")
    api_key = get_api_key()
    if not api_key: # get_api_key now exits on failure, but good practice to check
        return
    print("Successfully loaded API key.")

    cv_data = None
    job_description_text = None

    # 1. Get CV Data
    print("\n--- Step 1: Provide Your CV ---")
    cv_input_choice = input("How would you like to provide your CV? (json / text / skip): ").strip().lower()
    if cv_input_choice == 'json':
        cv_filepath = input("Enter path to your CV JSON file (e.g., my_cv.json): ").strip()
        cv_data = get_cv_from_json_file(cv_filepath)
        if cv_data:
            print(f"Successfully loaded CV from {cv_filepath}")
            # cv_data_for_prompt = json.dumps(cv_data, indent=2) # For actual use
    elif cv_input_choice == 'text':
        cv_filepath = input("Enter path to your CV text file (e.g., my_cv.txt): ").strip()
        cv_data = get_cv_from_text_file(cv_filepath)
        if cv_data:
            print(f"Successfully loaded CV from {cv_filepath}")
            # cv_data_for_prompt = cv_data # For actual use
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

    if cv_data and job_description_text:
        print("\n--- Step 3: Processing (Placeholders) ---")
        # 2.2. Prompt Engineering Stage (Placeholder)
        print("TODO: Construct the prompt for the Gemini API.")
        # combined_input_for_api = f"CV:\n{cv_data_for_prompt}\n\nJob Description:\n{job_description_text}"
        # print(f"Combined input for API (first 100 chars): {combined_input_for_api[:100]}...")


        # 2.3. API Call Stage (Placeholder)
        print("TODO: Call the Gemini API with the prompt.")
        # tailored_cv_output = call_gemini_api(api_key, combined_input_for_api) # Assuming a function call_gemini_api

        # 2.4. Output Stage (Placeholder)
        print("TODO: Receive and process the AI-generated tailored CV.")
        # print(f"Tailored CV Output: {tailored_cv_output}")

        # 2.5. Presentation/Storage Stage (Placeholder)
        print("TODO: Display the generated CV or save it to a file.")
        # save_to_file(tailored_cv_output, "tailored_cv.txt")
    else:
        print("\nSkipping processing as either CV or Job Description is missing.")

    print("\n--- Program End ---")

if __name__ == "__main__":
    main()
