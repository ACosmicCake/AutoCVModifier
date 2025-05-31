# cv_tailor_project/app/cv_analyzer.py
import os
# Assuming call_gemini_api and get_api_key (if used directly here) are in cv_utils
# For this function, we expect api_key to be passed in, so get_api_key might not be directly needed here.
from .cv_utils import call_gemini_api

def analyze_cv_with_gemini(cv_content_str: str, api_key: str) -> str | None:
    """
    Analyzes the given CV content using the Gemini API.

    Args:
        cv_content_str: The CV content as a string.
        api_key: The Google API key.

    Returns:
        The analysis text from Gemini, or None if an error occurs or content is empty.
    """
    if not cv_content_str:
        print("Error: CV content string is empty. Cannot analyze.")
        return None
    if not api_key:
        print("Error: API key is missing. Cannot analyze CV.")
        return None

    # Formulate a new prompt for Gemini for "full CV analysis"
    # This prompt can be refined based on desired output.
    prompt_text = f"""
You are an expert CV analyst. Your task is to perform a comprehensive analysis of the provided CV.

Please provide a detailed analysis covering the following aspects:
1.  **Overall Impression:** General readability, structure, and professionalism.
2.  **Strengths:** Identify key strengths demonstrated in the CV (e.g., specific skills, strong experience in certain areas, quantifiable achievements).
3.  **Areas for Improvement:** Suggest specific areas where the CV could be improved (e.g., clarity, impact, missing information, formatting issues, conciseness).
4.  **Keyword Alignment (General):** Assess how well the CV uses common keywords and action verbs relevant to general professional roles. If the CV seems targeted to a specific industry (e.g., software engineering, marketing), mention that.
5.  **Actionable Recommendations:** Provide 3-5 concrete, actionable recommendations for the CV owner to enhance their document.

The CV content is as follows:
--- BEGIN CV CONTENT ---
{cv_content_str}
--- END CV CONTENT ---

Please provide your analysis as a well-structured text. Use markdown for headings and bullet points if it helps readability.
"""

    # print(f"CV Analysis Prompt (first 150 chars): {prompt_text[:150]}...") # For debugging

    analysis_result = call_gemini_api(api_key, prompt_text)

    if analysis_result:
        # Basic cleaning, though Gemini should ideally return clean text for this prompt
        return analysis_result.strip()
    else:
        print("Failed to get CV analysis from Gemini API (result was None).")
        return None

# Example usage (for testing this module directly)
if __name__ == '__main__':
    print("Testing cv_analyzer.py...")
    # This requires GOOGLE_API_KEY to be in the environment for testing
    # In a real app, load_dotenv would be called in main.py
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')) # Load .env from project root for testing

    sample_api_key = os.environ.get("GOOGLE_API_KEY")

    if not sample_api_key:
        print("GOOGLE_API_KEY not found in .env file for testing. Skipping direct test.")
    else:
        print(f"Using API_KEY: {sample_api_key[:5]}... for testing.")
        sample_cv = """
        John Doe
        Software Engineer

        Experience:
        - Developed web applications using Python and Django.
        - Led a team of 5 engineers.

        Skills:
        - Python, Java, C++
        - SQL, NoSQL
        """
        print(f"Analyzing sample CV: '{sample_cv[:50]}...'")
        analysis = analyze_cv_with_gemini(sample_cv, sample_api_key)

        if analysis:
            print("\n--- CV Analysis Result ---")
            print(analysis)
            print("--- End of Analysis ---")
        else:
            print("CV analysis failed or returned empty.")
