# cv_tailor_project/app/job_scraper.py
from jobspy import scrape_jobs as jobspy_scrape
import pandas as pd # jobspy returns a pandas DataFrame

def scrape_online_jobs(
    site_names: list[str] = ["indeed", "linkedin"],
    search_term: str = "software engineer",
    location: str = "USA",
    results_wanted: int = 5,
    country_indeed: str = 'USA' # Example of a site-specific parameter
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
    if not site_names:
        print("Error: No site names provided for job scraping.")
        return None

    print(f"Attempting to scrape jobs from {site_names} for '{search_term}' in '{location}', results_wanted={results_wanted}")

    try:
        jobs_df = jobspy_scrape(
            site_name=site_names,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            country_indeed=country_indeed # Pass site-specific params if needed
            # Add other relevant parameters for jobspy if required by the UI/feature set
            # e.g., distance_km, job_type, full_description
        )

        if jobs_df is not None and not jobs_df.empty:
            # Convert DataFrame to a list of dictionaries for easier JSON response
            # Handle potential NaN values that are not JSON serializable directly
            jobs_df_filled = jobs_df.fillna('') # Replace NaN with empty strings
            return jobs_df_filled.to_dict(orient='records')
        elif jobs_df is not None and jobs_df.empty:
            print("No jobs found matching the criteria.")
            return [] # Return empty list if no jobs found but no error occurred
        else: # Should not happen if jobspy_scrape returns None on error
            print("Job scraping returned None, indicating an issue.")
            return None

    except Exception as e:
        print(f"Error scraping jobs using JobSpy: {e}")
        import traceback
        traceback.print_exc()
        return None

# Example usage (for testing this module directly)
if __name__ == '__main__':
    import json # Added for printing job details in test cases
    print("Testing job_scraper.py...")

    # Test Case 1: Default parameters
    print("\n--- Test Case 1: Default Parameters ---")
    scraped_jobs_default = scrape_online_jobs(results_wanted=1) # Keep results low for testing
    if scraped_jobs_default is not None:
        print(f"Found {len(scraped_jobs_default)} jobs (default):")
        for job in scraped_jobs_default[:1]: # Print details of the first job
            print(json.dumps(job, indent=2))
    else:
        print("Job scraping failed or returned no results for default parameters.")

    # Test Case 2: Specific search
    print("\n--- Test Case 2: Specific Search (Python Developer in New York) ---")
    scraped_jobs_specific = scrape_online_jobs(
        site_names=["linkedin"], # Test with a single site
        search_term="python developer",
        location="New York, NY",
        results_wanted=1 # Keep results low
    )
    if scraped_jobs_specific is not None:
        print(f"Found {len(scraped_jobs_specific)} jobs (specific):")
        for job in scraped_jobs_specific[:1]: # Print details of the first job
            # Need import json for the test print
            import json
            print(json.dumps(job, indent=2))
    else:
        print("Job scraping failed or returned no results for specific search.")

    # Test Case 3: No results expected (highly specific unlikely term)
    print("\n--- Test Case 3: No Results Expected ---")
    scraped_jobs_no_results = scrape_online_jobs(
        search_term="Galactic Hyperloop Maintenance Engineer",
        location="Mars",
        results_wanted=1
    )
    if scraped_jobs_no_results is not None and len(scraped_jobs_no_results) == 0:
        print("Successfully confirmed no jobs found for unlikely criteria.")
    elif scraped_jobs_no_results is not None:
        print(f"Found {len(scraped_jobs_no_results)} jobs, expected 0.")
    else:
        print("Job scraping failed for 'no results' test case.")
