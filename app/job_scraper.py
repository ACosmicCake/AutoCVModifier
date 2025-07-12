# app/job_scraper.py
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from jobspy import scrape_jobs as jobspy_scrape
import pandas as pd # jobspy returns a pandas DataFrame
import requests # For catching specific network exceptions like ReadTimeout

SUPPORTED_JOBSPY_SITES = {"indeed", "linkedin", "zip_recruiter", "glassdoor", "google", "bayt", "naukri"}

def scrape_online_jobs(
    site_names: list[str] = ["indeed", "linkedin"],
    search_term: str = "software engineer",
    location: str = "USA",
    results_wanted: int = 5,
    country_indeed: str = 'USA', # Example of a site-specific parameter
    linkedin_fetch_description: bool = True # New parameter
    ) -> list[dict] | None:
    """
    Scrapes jobs from specified sites using JobSpy.

    Args:
        site_names: A list of site names to scrape (e.g., ["indeed", "linkedin"]).
        search_term: The job title or keywords to search for.
        location: The location to search for jobs in.
        results_wanted: The desired number of results from each site.
        country_indeed: Country for Indeed searches (JobSpy specific parameter).

    Returns:
        A list of job dictionaries, or None if an error occurs or no jobs are found.
    """
    if not site_names: # Initial check if site_names is empty or None from the start
        print("Error: No site names provided for job scraping.")
        return None # Or [] if preferred for consistency

    processed_site_names = []
    for name in site_names:
        if isinstance(name, str):
            cleaned_name = name.strip().lower()
            if cleaned_name in SUPPORTED_JOBSPY_SITES:
                if cleaned_name not in processed_site_names: # Avoid duplicates
                    processed_site_names.append(cleaned_name)
            else:
                print(f"Warning: Invalid or unsupported site name '{name}' provided. It will be ignored.")
        else:
            print(f"Warning: Non-string site name '{name}' found in list. It will be ignored.")

    if not processed_site_names:
        print("Error: No valid site names remaining after validation. Please provide supported sites.")
        return [] # Return empty list as no valid sites to scrape

    site_names_to_scrape = processed_site_names

    print(f"Attempting to scrape jobs from {site_names_to_scrape} for '{search_term}' in '{location}', results_wanted={results_wanted}")

    try:
        jobs_df = jobspy_scrape(
            site_name=site_names_to_scrape,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            country_indeed=country_indeed, # Pass site-specific params if needed
            linkedin_fetch_description=linkedin_fetch_description # Added parameter
            # Add other relevant parameters for jobspy if required by the UI/feature set
            # e.g., distance_km, job_type
        )

        if jobs_df is not None and not jobs_df.empty:
            # Convert DataFrame to a list of dictionaries for easier JSON response
            # Handle potential NaN values that are not JSON serializable directly
            jobs_df_filled = jobs_df.fillna('') # Replace NaN with empty strings
            return jobs_df_filled.to_dict(orient='records')
        elif jobs_df is not None and jobs_df.empty:
            print("No jobs found matching the criteria.")
            return [] # Return empty if no jobs found but no error occurred
        else: # Should not happen if jobspy_scrape returns None on error
            print("Job scraping returned None, indicating an issue.")
            return None
    except requests.exceptions.ReadTimeout as rte:
        print(f"Timeout error while scraping jobs: {rte}")
        print("This could be due to network issues or the site (e.g., Indeed) being slow/blocking the request.")
        # For now, a general timeout message. Consistent return with other errors.
        return None
    except Exception as e:
        print(f"An unexpected error occurred while scraping jobs using JobSpy: {e}")
        import traceback
        traceback.print_exc()
        return None
