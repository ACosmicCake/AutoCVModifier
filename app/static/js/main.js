// app/static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const cvTailorForm = document.getElementById('cvTailorForm');
    const cvFileInput = document.getElementById('cvFile');
    const tailorResultDiv = document.getElementById('tailorResult');
    const pdfDownloadLinkDiv = document.getElementById('pdfDownloadLink');

    const jobScrapeForm = document.getElementById('jobScrapeForm');
    const jobResultsDiv = document.getElementById('jobResults');
    const loadingIndicator = document.getElementById('loadingIndicator');

    // Filter controls
    const filterKeywordInput = document.getElementById('filterKeyword');
    const filterLocationInput = document.getElementById('filterLocation');
    const filterSourceSelect = document.getElementById('filterSource');
    const filterAppliedStatusSelect = document.getElementById('filterAppliedStatus'); // Added
    const filterJobsButton = document.getElementById('filterJobsButton');
    const clearFiltersButton = document.getElementById('clearFiltersButton');

    // Batch CV Generation
    const batchGenerateCVsButton = document.getElementById('batchGenerateCVsButton');
    const batchCvResultsDiv = document.getElementById('batchCvResults');
    const batchCvHelpText = document.getElementById('batchCvHelpText');


    function showLoading(message = 'Processing...') {
        if (loadingIndicator) {
            loadingIndicator.querySelector('p').textContent = message;
            loadingIndicator.classList.remove('hidden');
        }
    }

    function hideLoading() {
        if (loadingIndicator) {
            loadingIndicator.classList.add('hidden');
        }
    }

    function escapeHtml(unsafe) {
        if (unsafe === null || typeof unsafe === 'undefined') return '';
        return unsafe
            .toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // --- Update Batch Generate Button State ---
    function updateBatchButtonState() {
        // Ensure button and help text elements exist before proceeding
        if (!batchGenerateCVsButton || !batchCvHelpText) {
            return;
        }
        if (!cvFileInput || !jobResultsDiv) {
            batchGenerateCVsButton.disabled = true;
            batchGenerateCVsButton.classList.add('hidden');
            batchCvHelpText.textContent = "Upload a CV and ensure job listings are loaded to enable batch generation.";
            batchCvHelpText.classList.remove('hidden');
            return;
        }

        const cvFileSelected = cvFileInput.files && cvFileInput.files.length > 0;
        const selectedJobsCount = jobResultsDiv.querySelectorAll('.job-select-checkbox:checked').length;

        if (cvFileSelected && selectedJobsCount > 0) {
            batchGenerateCVsButton.disabled = false;
            batchGenerateCVsButton.classList.remove('hidden');
            batchCvHelpText.classList.add('hidden');
            batchCvHelpText.textContent = "Select your base CV and one or more jobs to generate tailored CVs."; // Default help text
        } else {
            batchGenerateCVsButton.disabled = true;
            batchGenerateCVsButton.classList.add('hidden');
            batchCvHelpText.classList.remove('hidden');
            if (!cvFileSelected && selectedJobsCount === 0) {
                batchCvHelpText.textContent = "Please upload your base CV and select at least one job from the list below.";
            } else if (!cvFileSelected) {
                batchCvHelpText.textContent = "Please upload your base CV.";
            } else { // selectedJobsCount === 0
                batchCvHelpText.textContent = "Please select at least one job from the list below.";
            }
        }
    }

    // --- CV Tailoring ---
    if (cvTailorForm) {
        cvTailorForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading('Tailoring CV and generating PDF...');
            if (tailorResultDiv) tailorResultDiv.innerHTML = '';
            if (pdfDownloadLinkDiv) pdfDownloadLinkDiv.innerHTML = '';
            if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = ''; // Clear batch results too

            const formData = new FormData(cvTailorForm);

            try {
                const response = await fetch('/api/tailor-cv', {
                    method: 'POST',
                    body: formData,
                });

                const result = await response.json();
                hideLoading();

                if (response.ok) {
                    if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-green-600">Success: ${escapeHtml(result.message || 'CV Tailored!')}</p>`;
                    if (result.tailored_cv_json && tailorResultDiv) {
                        const formattedJson = JSON.stringify(result.tailored_cv_json, null, 2);
                        tailorResultDiv.innerHTML += `<h4 class="font-semibold mt-2">Tailored CV (JSON Preview):</h4><pre class="whitespace-pre-wrap text-xs">${escapeHtml(formattedJson)}</pre>`;
                    }
                    if (result.pdf_download_url && pdfDownloadLinkDiv) {
                        pdfDownloadLinkDiv.innerHTML = `<a href="${escapeHtml(result.pdf_download_url)}" target="_blank" class="inline-block mt-3 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline">Download Tailored CV (PDF)</a>`;
                    } else if (result.error_pdf && pdfDownloadLinkDiv) {
                         pdfDownloadLinkDiv.innerHTML = `<p class="text-orange-500 mt-2">Note: ${escapeHtml(result.error_pdf)}</p>`;
                    } else if (pdfDownloadLinkDiv) {
                         pdfDownloadLinkDiv.innerHTML = `<p class="text-orange-500 mt-2">PDF download link not available. JSON preview above.</p>`;
                    }
                } else {
                    if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(result.error || 'Failed to tailor CV.')}</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('CV Tailoring Error:', error);
                if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-red-600">An unexpected error occurred. Check console.</p>`;
            }
        });
    }
    if (cvFileInput) {
        cvFileInput.addEventListener('change', updateBatchButtonState);
    }


    // --- Job Display Function ---
    function displayJobs(jobsArray) {
        if (!jobResultsDiv) return;
        if (!jobsArray || jobsArray.length === 0) {
            jobResultsDiv.innerHTML = '<p>No jobs found matching your criteria.</p>';
            updateBatchButtonState(); // Update button state even if no jobs
            return;
        }

        let html = `<div class="flex justify-between items-center mb-3">
                        <h3 class="text-xl font-semibold">Job Listings:</h3>
                        <label class="text-sm"><input type="checkbox" id="selectAllJobsCheckbox" class="mr-1"> Select All</label>
                    </div>
                    <div class="space-y-4">`;
        jobsArray.forEach(job => {
            const description = job.description || 'No description available.'; // Keep it simple for data attribute
            const company = job.company || 'N/A';
            const location = job.location || 'N/A';
            const job_url = job.url;
            const source = job.source;
            const date_scraped_obj = new Date(job.date_scraped);
            const formatted_date_scraped = date_scraped_obj.toLocaleDateString() + ' ' + date_scraped_obj.toLocaleTimeString();
            // Use job.id from database as the unique value for checkbox
            const jobId = job.id;
            const isApplied = job.applied === 1 || job.applied === true;
            const cvFilename = job.cv_filename; // New field
            // const generatedCvId = job.generated_cv_id; // New field, might be used later

            html += `
                <div class="p-4 border rounded-md shadow-sm bg-gray-50 job-card" data-job-id="${escapeHtml(jobId)}">
                    <div class="flex items-start">
                        <input type="checkbox" class="job-select-checkbox mt-1 mr-3 h-5 w-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500" 
                               value="${escapeHtml(jobId)}" 
                               data-job-id="${escapeHtml(jobId)}" 
                               data-job-description="${escapeHtml(description)}" 
                               data-job-title="${escapeHtml(job.title || 'N/A')}">
                        <div class="flex-grow">
                            <div class="flex justify-between items-center">
                                <h4 class="text-lg font-bold text-blue-600">${escapeHtml(job.title || 'N/A')}</h4>
                                <button class="text-xs py-1 px-2 rounded border toggle-applied-btn ${isApplied ? 'bg-yellow-500 text-white' : 'bg-gray-200 hover:bg-gray-300'}" data-job-id="${escapeHtml(jobId)}">${isApplied ? 'Mark Unapplied' : 'Mark Applied'}</button>
                            </div>
                            <p class="text-sm text-gray-700">${escapeHtml(company)} - ${escapeHtml(location)}</p>
                            <p class="text-xs text-gray-500">Source: ${escapeHtml(source)} | Scraped: ${escapeHtml(formatted_date_scraped)} | DB ID: ${jobId}</p>
                            <p class="text-xs text-gray-500 job-applied-status">Status: ${isApplied ? 'Applied' : 'Not Applied'}</p>
                            ${job_url ? `<a href="${escapeHtml(job_url)}" target="_blank" class="text-blue-500 hover:underline text-sm mr-2">View Original Job</a>` : ''}
                            
                            <div class="mt-2 job-actions">`; // Container for action buttons
            
            if (cvFilename) {
                html += `<button onclick="window.open('/api/download-cv/${escapeHtml(cvFilename)}', '_blank')" class="bg-green-500 hover:bg-green-700 text-white font-bold py-1 px-2 rounded text-xs mt-2 mr-2">Download CV</button>`;
                html += `<button class="auto-apply-btn bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded text-xs mt-2" data-job-id="${escapeHtml(jobId)}" data-job-url="${escapeHtml(job_url)}" data-cv-filename="${escapeHtml(cvFilename)}">Auto Apply Job</button>`;
            }
            html += `       </div>
                            <div class="auto-apply-status text-xs mt-1 text-gray-600"></div> <!-- Ensure this was part of the previous change, if not, it's added now -->
                            <details class="mt-2 text-sm">
                                <summary class="cursor-pointer text-gray-600 hover:text-gray-800">Full Description (for reference)</summary>
                                <p class="mt-1 text-gray-600 leading-relaxed whitespace-pre-line">${escapeHtml(description)}</p>
                            </details>
                        </div>
                    </div>
                </div>`;
        });
        html += '</div>';
        jobResultsDiv.innerHTML = html;

        // Add event listeners for newly created checkboxes
        const jobCheckboxes = jobResultsDiv.querySelectorAll('.job-select-checkbox');
        jobCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', updateBatchButtonState);
        });

        const selectAllCheckbox = document.getElementById('selectAllJobsCheckbox');
        if(selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                jobCheckboxes.forEach(cb => cb.checked = e.target.checked); // Apply to current list of checkboxes
                updateBatchButtonState();
            });
        }

        // Add event listeners for toggle applied buttons
        const toggleButtons = jobResultsDiv.querySelectorAll('.toggle-applied-btn');
        toggleButtons.forEach(button => {
            button.addEventListener('click', async (event) => {
                const currentJobId = event.target.dataset.jobId; // Renamed to avoid conflict in wider scope if jobId was used
                if (!currentJobId) return;

                showLoading('Updating status...');

                try {
                    const response = await fetch(`/api/jobs/${currentJobId}/toggle-applied`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });
                    const result = await response.json();
                    hideLoading();

                    if (response.ok && result.new_status !== undefined) {
                        const card = event.target.closest('.job-card');
                        if (card) {
                            const statusTextElement = card.querySelector('.job-applied-status');
                            const toggleButton = event.target; 
                            const newAppliedStatusBool = result.new_status === 1 || result.new_status === true;
                            if (statusTextElement) statusTextElement.textContent = `Status: ${newAppliedStatusBool ? 'Applied' : 'Not Applied'}`;
                            if (toggleButton) {
                                toggleButton.textContent = newAppliedStatusBool ? 'Mark Unapplied' : 'Mark Applied';
                                if (newAppliedStatusBool) {
                                    toggleButton.classList.add('bg-yellow-500', 'text-white');
                                    toggleButton.classList.remove('bg-gray-200', 'hover:bg-gray-300');
                                } else {
                                    toggleButton.classList.remove('bg-yellow-500', 'text-white');
                                    toggleButton.classList.add('bg-gray-200', 'hover:bg-gray-300');
                                }
                            }
                        }
                    } else {
                        alert(`Error updating status: ${result.error || 'Unknown error'}`);
                    }
                } catch (error) {
                    hideLoading();
                    console.error('Toggle Applied Status Error:', error);
                    alert('An unexpected error occurred while updating status.');
                }
            });
        });

        // Add event listeners for Auto Apply Job buttons (for jobs loaded directly in displayJobs)
        const autoApplyButtons = jobResultsDiv.querySelectorAll('.auto-apply-btn');
        autoApplyButtons.forEach(button => {
            button.addEventListener('click', async (event) => {
                const clickedButton = event.currentTarget; 
                const originalButtonText = clickedButton.textContent;
                clickedButton.disabled = true;
                clickedButton.textContent = 'Applying...';

                const jobCard = clickedButton.closest('.job-card');
                let statusDiv = null;
                if (jobCard) {
                    statusDiv = jobCard.querySelector('.auto-apply-status');
                    if (statusDiv) {
                        statusDiv.innerHTML = ''; 
                        statusDiv.className = 'auto-apply-status text-xs mt-1 text-gray-600'; 
                    }
                }

                const jobUrl = clickedButton.dataset.jobUrl;
                const cvFilename = clickedButton.dataset.cvFilename;

                if (!jobUrl || !cvFilename) {
                    alert('Missing job URL or CV filename for auto-apply. Check button data attributes.');
                    console.error("AutoApply Error: jobUrl or cvFilename missing from button dataset.", clickedButton.dataset);
                    if (statusDiv) {
                        statusDiv.textContent = 'Error: Missing job URL or CV filename.';
                        statusDiv.className = 'auto-apply-status text-xs mt-1 text-red-600';
                    }
                    clickedButton.disabled = false;
                    clickedButton.textContent = originalButtonText;
                    return;
                }

                const userProfileFileInput = document.getElementById('userProfileFile');
                let profile_json_path = "User_profile.json"; // Default
                if (userProfileFileInput && userProfileFileInput.files && userProfileFileInput.files.length > 0) {
                    profile_json_path = userProfileFileInput.files[0].name;
                } else {
                    alert("User Profile JSON not selected. Using default 'User_profile.json'. Ensure this file is correctly placed for AI access if this default is intended.");
                    // Optionally update statusDiv here too if desired, e.g., "Using default profile."
                }

                showLoading('Starting AutoApply process...');

                try {
                    const response = await fetch('/api/auto-apply', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            job_url: jobUrl,
                            cv_json_path: cvFilename, // Using filename as identifier for JSON CV
                            cv_pdf_path: cvFilename,  // Using filename as identifier for PDF CV
                            profile_json_path: profile_json_path // Use determined path
                        })
                    });

                    // Try to parse JSON regardless of response.ok to get error details from body
                    const resultData = await response.json(); 

                    if (response.ok) {
                        console.log('AutoApply Response:', resultData);
                        // alert('AutoApply process initiated: ' + (resultData.message || 'Request successful. Check server logs.')); // Alert kept for now
                        if (statusDiv) {
                            statusDiv.textContent = `Initiated: ${resultData.message || 'Server confirmed.'}`;
                            statusDiv.className = 'auto-apply-status text-xs mt-1 text-green-600';
                        }
                    } else {
                        console.error('AutoApply Error Data:', resultData);
                        // alert('AutoApply failed: ' + (resultData.error || 'Unknown server error. Check console.')); // Alert kept for now
                        if (statusDiv) {
                            statusDiv.textContent = `Failed: ${resultData.error || 'Unknown server error.'}`;
                            statusDiv.className = 'auto-apply-status text-xs mt-1 text-red-600';
                        }
                    }
                } catch (error) { 
                    console.error('Fetch Error for AutoApply:', error);
                    // alert('AutoApply request failed: ' + error.message); // Alert kept for now
                    if (statusDiv) {
                        statusDiv.textContent = `Request Error: ${error.message}`;
                        statusDiv.className = 'auto-apply-status text-xs mt-1 text-red-600';
                    }
                } finally {
                    hideLoading();
                    clickedButton.disabled = false;
                    clickedButton.textContent = originalButtonText;
                }
            });
        });
        
        updateBatchButtonState(); 
    }

    // --- Store current jobs data globally for access in batch CV update ---
    let currentJobsData = []; 

    // --- Fetch and Display Jobs (Filtered or All) ---
    async function fetchAndDisplayJobs(queryParams = {}) {
        currentJobsData = []; 
        showLoading('Fetching jobs from database...');
        if (jobResultsDiv) jobResultsDiv.innerHTML = '<p>Loading jobs...</p>';

        const params = new URLSearchParams();
        if (queryParams.keyword) params.append('keyword', queryParams.keyword);
        if (queryParams.location) params.append('location', queryParams.location);
        if (queryParams.source) params.append('source', queryParams.source);
        if (queryParams.applied_status && queryParams.applied_status !== 'all') {
            params.append('applied_status', queryParams.applied_status);
        }

        try {
            const response = await fetch(`/api/jobs?${params.toString()}`);
            const result = await response.json();
            hideLoading();

            if (response.ok && result.jobs) {
                currentJobsData = result.jobs; // Populate currentJobsData
                displayJobs(result.jobs);
            } else {
                if (jobResultsDiv) jobResultsDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(result.error || 'Failed to fetch jobs.')}</p>`;
                updateBatchButtonState(); // Still update button state on error
            }
        } catch (error) {
            hideLoading();
            console.error('Fetch Jobs Error:', error);
            if (jobResultsDiv) jobResultsDiv.innerHTML = '<p class="text-red-600">An unexpected error occurred while fetching jobs. Check console.</p>';
            updateBatchButtonState(); // Still update button state on error
        }
    }

    // --- Event Listener for Filter Button ---
    if (filterJobsButton) {
        filterJobsButton.addEventListener('click', () => {
            const filters = {
                keyword: filterKeywordInput ? filterKeywordInput.value.trim() : '',
                location: filterLocationInput ? filterLocationInput.value.trim() : '',
                source: filterSourceSelect ? filterSourceSelect.value : '',
                applied_status: filterAppliedStatusSelect ? filterAppliedStatusSelect.value : 'all'
            };
            fetchAndDisplayJobs(filters);
        });
    }

    // --- Event Listener for Clear Filters Button ---
    if (clearFiltersButton) {
        clearFiltersButton.addEventListener('click', () => {
            if(filterKeywordInput) filterKeywordInput.value = '';
            if(filterLocationInput) filterLocationInput.value = '';
            if(filterSourceSelect) filterSourceSelect.value = '';
            if(filterAppliedStatusSelect) filterAppliedStatusSelect.value = 'all'; // Reset new filter
            fetchAndDisplayJobs(); // Fetch all jobs
        });
    }

    // --- Job Scraping Form Submission ---
    if (jobScrapeForm) {
        jobScrapeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading('Scraping jobs...');
            if (jobResultsDiv) jobResultsDiv.innerHTML = '<p>Scraping jobs, please wait...</p>';
             if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = ''; // Clear previous batch results

            const scrapeParams = new URLSearchParams({
                search_term: document.getElementById('searchTerm').value,
                location: document.getElementById('location').value,
                site_names: document.getElementById('siteNames').value,
                results_wanted: document.getElementById('resultsWanted').value || 5
            });

            try {
                const response = await fetch(`/api/scrape-jobs?${scrapeParams.toString()}`);
                const result = await response.json();
                hideLoading();

                if (response.ok) {
                    let message = "Jobs scraped successfully!";
                    if (result.jobs && result.jobs.length > 0) {
                         message += ` Found ${result.jobs.length} new potential listings. Refreshing job list from database.`;
                    } else {
                        message += " No new listings found from this scrape. Refreshing job list from database.";
                    }
                    // Temporarily show message in jobResultsDiv before it's overwritten by fetchAndDisplayJobs
                    if (jobResultsDiv) jobResultsDiv.innerHTML = `<p>${escapeHtml(message)}</p>`;

                    const currentFilters = {
                        keyword: filterKeywordInput ? filterKeywordInput.value.trim() : '',
                        location: filterLocationInput ? filterLocationInput.value.trim() : '',
                        source: filterSourceSelect ? filterSourceSelect.value : '',
                        applied_status: filterAppliedStatusSelect ? filterAppliedStatusSelect.value : 'all'
                    };
                    fetchAndDisplayJobs(currentFilters);

                } else {
                    if (jobResultsDiv) jobResultsDiv.innerHTML = `<p class="text-red-600">Error scraping: ${escapeHtml(result.error || 'Failed to scrape jobs.')}</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('Job Scraping Error:', error);
                if (jobResultsDiv) jobResultsDiv.innerHTML = '<p class="text-red-600">An unexpected error occurred while scraping jobs. Check console.</p>';
            }
        });
    }

    // --- Batch CV Generation Event Listener ---
    if (batchGenerateCVsButton) {
        batchGenerateCVsButton.addEventListener('click', async () => {
            if (!cvFileInput || !cvFileInput.files[0]) {
                alert('Please select a CV file first.');
                return;
            }
            const selectedCheckboxes = jobResultsDiv.querySelectorAll('.job-select-checkbox:checked');
            if (selectedCheckboxes.length === 0) {
                alert('Please select at least one job.');
                return;
            }

            showLoading(`Generating ${selectedCheckboxes.length} CV(s)...`);
            if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = '';
            if (tailorResultDiv) tailorResultDiv.innerHTML = ''; // Clear single tailor results
            if (pdfDownloadLinkDiv) pdfDownloadLinkDiv.innerHTML = '';


            const formData = new FormData();
            formData.append('cv_file', cvFileInput.files[0]);

            selectedCheckboxes.forEach(checkbox => {
                // Send job_id and job_description. Backend will use description.
                // ID is useful if backend needs to fetch more details, though here description is primary.
                formData.append('job_ids[]', checkbox.value);
                formData.append('job_descriptions[]', checkbox.dataset.jobDescription);
                formData.append('job_titles[]', checkbox.dataset.jobTitle); // For summary in results
            });

            try {
                const response = await fetch('/api/batch-generate-cvs', {
                    method: 'POST',
                    body: formData,
                });
                const resultsData = await response.json();
                hideLoading();

                if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = ''; // Clear previous summary
                const errorMessages = [];
                let successes = 0;

                if (response.ok && resultsData.results) {
                    resultsData.results.forEach(result => {
                        if (result.status === 'success') {
                            successes++;
                            const jobCard = document.querySelector(`.job-card[data-job-id='${result.job_id}']`);
                            if (jobCard) {
                                const actionsDiv = jobCard.querySelector('.job-actions');
                                if (actionsDiv) {
                                    actionsDiv.innerHTML = ''; // Clear existing buttons

                                    const downloadBtn = document.createElement('a');
                                    downloadBtn.href = escapeHtml(result.pdf_url);
                                    downloadBtn.textContent = 'Download CV';
                                    downloadBtn.className = 'bg-green-500 hover:bg-green-700 text-white font-bold py-1 px-2 rounded text-xs mt-2 mr-2';
                                    downloadBtn.target = '_blank';
                                    actionsDiv.appendChild(downloadBtn);

                                    const autoApplyBtn = document.createElement('button');
                                    autoApplyBtn.textContent = 'Auto Apply Job';
                                    autoApplyBtn.className = 'auto-apply-btn bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded text-xs mt-2';
                                    
                                    // Set data attributes for the new auto-apply button
                                    autoApplyBtn.dataset.jobId = result.job_id;
                                    const pdfUrlPartsBatch = result.pdf_url.split('/');
                                    const newCvFilenameBatch = pdfUrlPartsBatch[pdfUrlPartsBatch.length -1];
                                    autoApplyBtn.dataset.cvFilename = newCvFilenameBatch;
                                    
                                    const currentJobBatch = currentJobsData.find(job => job.id === parseInt(result.job_id));
                                    if (currentJobBatch && currentJobBatch.url) {
                                        autoApplyBtn.dataset.jobUrl = currentJobBatch.url;
                                    } else {
                                        console.error(`Could not find job URL for job ID ${result.job_id} in currentJobsData for batch-generated button.`);
                                        autoApplyBtn.dataset.jobUrl = ""; // Fallback
                                    }

                                    // Add event listener for this dynamically created button (batch context)
                                    autoApplyBtn.addEventListener('click', async (event) => {
                                        const clickedButtonBatch = event.currentTarget;
                                        const originalButtonTextBatch = clickedButtonBatch.textContent;
                                        clickedButtonBatch.disabled = true;
                                        clickedButtonBatch.textContent = 'Applying...';

                                        const jobCardBatch = clickedButtonBatch.closest('.job-card');
                                        let statusDivBatch = null;
                                        if (jobCardBatch) {
                                            statusDivBatch = jobCardBatch.querySelector('.auto-apply-status');
                                            if (statusDivBatch) {
                                                statusDivBatch.innerHTML = ''; 
                                                statusDivBatch.className = 'auto-apply-status text-xs mt-1 text-gray-600'; 
                                            }
                                        }

                                        const jobUrlBatch = clickedButtonBatch.dataset.jobUrl;
                                        const cvFilenameForAutoApplyBatch = clickedButtonBatch.dataset.cvFilename;
                                        
                                        if (!jobUrlBatch || !cvFilenameForAutoApplyBatch) {
                                            alert('Missing job URL or CV filename for auto-apply (batch).');
                                            if (statusDivBatch) {
                                                statusDivBatch.textContent = 'Error: Missing job URL or CV filename.';
                                                statusDivBatch.className = 'auto-apply-status text-xs mt-1 text-red-600';
                                            }
                                            clickedButtonBatch.disabled = false;
                                            clickedButtonBatch.textContent = originalButtonTextBatch;
                                            return;
                                        }

                                        const userProfileFileInputBatch = document.getElementById('userProfileFile');
                                        let profile_json_path_batch = "User_profile.json"; 
                                        if (userProfileFileInputBatch && userProfileFileInputBatch.files && userProfileFileInputBatch.files.length > 0) {
                                            profile_json_path_batch = userProfileFileInputBatch.files[0].name;
                                        } else {
                                            alert("User Profile JSON not selected. Using default 'User_profile.json' for batch auto-apply.");
                                        }

                                        showLoading('Starting AutoApply process (batch)...');
                                        try {
                                            const fetchResponse = await fetch('/api/auto-apply', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({
                                                    job_url: jobUrlBatch,
                                                    cv_json_path: cvFilenameForAutoApplyBatch,
                                                    cv_pdf_path: cvFilenameForAutoApplyBatch,
                                                    profile_json_path: profile_json_path_batch 
                                                })
                                            });
                                            const responseData = await fetchResponse.json();
                                            if (fetchResponse.ok) {
                                                console.log('AutoApply Response (batch):', responseData);
                                                // alert('AutoApply (batch) initiated: ' + (responseData.message || 'OK'));
                                                if (statusDivBatch) {
                                                    statusDivBatch.textContent = `Initiated: ${responseData.message || 'OK'}`;
                                                    statusDivBatch.className = 'auto-apply-status text-xs mt-1 text-green-600';
                                                }
                                            } else {
                                                console.error('AutoApply Error (batch):', responseData);
                                                // alert('AutoApply (batch) failed: ' + (responseData.error || 'Error'));
                                                if (statusDivBatch) {
                                                    statusDivBatch.textContent = `Failed: ${responseData.error || 'Error'}`;
                                                    statusDivBatch.className = 'auto-apply-status text-xs mt-1 text-red-600';
                                                }
                                            }
                                        } catch (fetchError) {
                                            console.error('Fetch Error for AutoApply (batch):', fetchError);
                                            // alert('AutoApply (batch) request failed: ' + fetchError.message);
                                            if (statusDivBatch) {
                                                statusDivBatch.textContent = `Request Error: ${fetchError.message}`;
                                                statusDivBatch.className = 'auto-apply-status text-xs mt-1 text-red-600';
                                            }
                                        } finally {
                                            hideLoading();
                                            clickedButtonBatch.disabled = false;
                                            clickedButtonBatch.textContent = originalButtonTextBatch;
                                        }
                                    });
                                    actionsDiv.appendChild(autoApplyBtn);

                                    jobCard.classList.add('bg-green-100');
                                    setTimeout(() => jobCard.classList.remove('bg-green-100'), 3000);
                                } else {
                                    console.warn(`Actions div not found for job card ID: ${result.job_id}`);
                                    // Optionally add this to a different kind of error/warning list if needed
                                }
                            } else {
                                console.warn(`Job card not found for ID: ${result.job_id}`);
                                // This case might happen if the job list was refreshed or changed during batch processing.
                                // Add to errorMessages or a separate warnings list if necessary.
                                errorMessages.push(`<li>Successfully generated CV for Job ID ${result.job_id} (title: ${escapeHtml(result.job_title_summary || 'N/A')}) but could not find its card to update. PDF: <a href="${escapeHtml(result.pdf_url)}" target="_blank" class="text-blue-500 hover:underline">Download Here</a></li>`);
                            }
                        } else { // result.status === 'error'
                            errorMessages.push(`<li>${escapeHtml(result.job_title_summary || 'Unknown Job')}: ${escapeHtml(result.message)} (Job ID: ${result.job_id || 'N/A'})</li>`);
                        }
                    });

                    if (errorMessages.length > 0 && batchCvResultsDiv) {
                        const errorTitle = document.createElement('h4');
                        errorTitle.className = 'text-lg font-semibold text-red-700 mb-2';
                        errorTitle.textContent = 'CV Generation Issues:';
                        batchCvResultsDiv.appendChild(errorTitle);
                        
                        const errorList = document.createElement('ul');
                        errorList.className = 'list-disc list-inside text-red-600';
                        errorList.innerHTML = errorMessages.join('');
                        batchCvResultsDiv.appendChild(errorList);
                    }
                    
                    if (successes > 0 && errorMessages.length === 0 && batchCvResultsDiv) {
                         batchCvResultsDiv.innerHTML = `<p class="text-green-600">Batch CV generation completed successfully for ${successes} job(s). Job cards have been updated.</p>`;
                    } else if (successes > 0 && errorMessages.length > 0 && batchCvResultsDiv) {
                        // If there were also successes, add a small note about them if not already clear
                        const successMessage = document.createElement('p');
                        successMessage.className = 'text-green-600 mt-2';
                        successMessage.textContent = `${successes} CV(s) generated successfully and job cards updated. See issues above.`;
                        batchCvResultsDiv.appendChild(successMessage);
                    }


                } else { // Response not ok or resultsData.results not present
                     if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(resultsData.error || 'Failed to process batch CVs response.')}</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('Batch CV Generation Error:', error);
                if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = '<p class="text-red-600">An unexpected error occurred. Check console.</p>';
            }
        });
    }

    // --- User Profile Form ---
    const userProfileForm = document.getElementById('userProfileForm');
    const generateProfileButton = document.getElementById('generateProfileButton');

    if (generateProfileButton && userProfileForm) {
        generateProfileButton.addEventListener('click', () => {
            const userProfileData = {};

            // Populate with values from the form fields
            userProfileData.CurrentLocation = document.getElementById('currentLocation').value;
            userProfileData.CurrentCompany = document.getElementById('currentCompany').value;
            userProfileData.LinkedInURL = document.getElementById('linkedinUrl').value;
            userProfileData.TwitterURL = document.getElementById('twitterUrl').value;
            userProfileData.GitHubURL = document.getElementById('githubUrl').value;
            userProfileData.PortfolioURL = document.getElementById('portfolioUrl').value;
            userProfileData.OtherWebsiteURL = document.getElementById('otherWebsiteUrl').value;

            // NYC Intern Qualifications
            userProfileData.NYCInternQualifications = {};
            const commuteYes = document.getElementById('commuteYes').checked;
            const commuteNo = document.getElementById('commuteNo').checked;
            if (commuteYes) {
                userProfileData.NYCInternQualifications.CommuteToFlatiron = true;
            } else if (commuteNo) {
                userProfileData.NYCInternQualifications.CommuteToFlatiron = false;
            } else {
                userProfileData.NYCInternQualifications.CommuteToFlatiron = null;
            }

            const commitYes = document.getElementById('commitYes').checked;
            const commitNo = document.getElementById('commitNo').checked;
            if (commitYes) {
                userProfileData.NYCInternQualifications.CommitToInternshipDuration = true;
            } else if (commitNo) {
                userProfileData.NYCInternQualifications.CommitToInternshipDuration = false;
            } else {
                userProfileData.NYCInternQualifications.CommitToInternshipDuration = null;
            }

            // Convert to JSON string
            const jsonString = JSON.stringify(userProfileData, null, 2);

            // Trigger download
            const blob = new Blob([jsonString], { type: 'application/json' });
            const href = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = href;
            link.download = 'User_profile.json';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(href);
        });
    }

    // --- Initial Load ---
    // Populate currentJobsData when jobs are fetched
    if (jobResultsDiv) { 
        fetchAndDisplayJobs().then(() => {
            // This is a bit of a placeholder; displayJobs itself populates currentJobsData.
            // No specific action needed here unless there's post-fetch logic for currentJobsData.
        });
    } else {
        console.warn("jobResultsDiv not found on page load. Initial job fetch skipped.");
    }
    updateBatchButtonState(); // Initial state for the batch button
});
