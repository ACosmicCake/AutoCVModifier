# app/job_scraper.py
import logging
import math
import traceback

import requests  # For catching specific network exceptions like ReadTimeout

try:
    from jobspy import scrape_jobs as jobspy_scrape  # provided by the `python-jobspy` package
except ImportError:  # keep the rest of the app usable if the scraper isn't installed
    jobspy_scrape = None

logger = logging.getLogger(__name__)

SUPPORTED_JOBSPY_SITES = {"indeed", "linkedin", "zip_recruiter", "glassdoor", "google", "bayt", "naukri"}


def _clean_value(value):
    """Converts pandas/numpy values (NaN, Timestamps, numpy scalars) into JSON-friendly Python values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "isoformat"):  # date, datetime, pandas Timestamp
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            return str(value)
    if hasattr(value, "item"):  # numpy scalar
        try:
            return _clean_value(value.item())
        except (TypeError, ValueError):
            return str(value)
    return value


def scrape_online_jobs(
    site_names: list[str] | None = None,
    search_term: str = "software engineer",
    location: str = "USA",
    results_wanted: int = 5,
    country_indeed: str = 'USA',
    linkedin_fetch_description: bool = True,
    offset: int = 0,
    hours_old: int | None = None,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool = False,
) -> list[dict] | None:
    """
    Scrapes jobs from the given sites using JobSpy.

    Returns a list of job dicts (possibly empty), or None if the scraper failed.
    `offset` skips that many results per site, so repeated calls can page through listings.
    """
    if jobspy_scrape is None:
        logger.error("JobSpy is not installed. Run: pip install python-jobspy")
        return None

    site_names = site_names or ["indeed", "linkedin"]
    processed_site_names = []
    for name in site_names:
        cleaned_name = str(name).strip().lower()
        if cleaned_name in SUPPORTED_JOBSPY_SITES:
            if cleaned_name not in processed_site_names:
                processed_site_names.append(cleaned_name)
        else:
            logger.warning("Unsupported site name '%s' ignored.", name)

    if not processed_site_names:
        logger.error("No valid site names remaining after validation.")
        return []

    logger.info("Scraping %s for '%s' in '%s' (results_wanted=%s, offset=%s)",
                processed_site_names, search_term, location, results_wanted, offset)

    kwargs = dict(
        site_name=processed_site_names,
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        country_indeed=country_indeed,
        linkedin_fetch_description=linkedin_fetch_description,
        offset=offset,
        is_remote=is_remote,
        verbose=0,
    )
    if hours_old:
        kwargs["hours_old"] = hours_old
    if job_type:
        kwargs["job_type"] = job_type
    if easy_apply:
        kwargs["easy_apply"] = True  # LinkedIn/Indeed: only jobs you can apply to on the board itself
    if "google" in processed_site_names:
        kwargs["google_search_term"] = f"{search_term} jobs near {location}"

    try:
        jobs_df = jobspy_scrape(**kwargs)
    except requests.exceptions.ReadTimeout as rte:
        logger.error("Timeout while scraping jobs (the site may be slow or blocking requests): %s", rte)
        return None
    except Exception as e:
        logger.error("Unexpected error while scraping jobs with JobSpy: %s\n%s", e, traceback.format_exc())
        return None

    if jobs_df is None:
        return None
    if jobs_df.empty:
        logger.info("No jobs found matching the criteria.")
        return []

    records = jobs_df.to_dict(orient='records')
    return [{key: _clean_value(value) for key, value in record.items()} for record in records]
