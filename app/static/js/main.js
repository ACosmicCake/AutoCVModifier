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
                html += `<button onclick="console.log('Auto Apply for job ID ${escapeHtml(jobId)} clicked. CV: ${escapeHtml(cvFilename)}')" class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded text-xs mt-2">Auto Apply Job</button>`;
            }

            html += `       </div> 
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
                const jobId = event.target.dataset.jobId;
                if (!jobId) return;

                showLoading('Updating status...');

                try {
                    const response = await fetch(`/api/jobs/${jobId}/toggle-applied`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });
                    const result = await response.json();
                    hideLoading();

                    if (response.ok && result.new_status !== undefined) {
                        // Dynamically update the specific job card's UI
                        const card = event.target.closest('.job-card');
                        if (card) {
                            const statusTextElement = card.querySelector('.job-applied-status');
                            const toggleButton = event.target; // or card.querySelector('.toggle-applied-btn')

                            const newAppliedStatusBool = result.new_status === 1 || result.new_status === true;

                            if (statusTextElement) {
                                statusTextElement.textContent = `Status: ${newAppliedStatusBool ? 'Applied' : 'Not Applied'}`;
                            }
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
        updateBatchButtonState(); // Update batch button state after rendering jobs and attaching listeners
    }

    // --- Fetch and Display Jobs (Filtered or All) ---
    async function fetchAndDisplayJobs(queryParams = {}) {
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
                                    autoApplyBtn.className = 'bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded text-xs mt-2';
                                    autoApplyBtn.addEventListener('click', () => {
                                        console.log(`Auto Apply clicked for job ID ${result.job_id}, CV: ${escapeHtml(result.pdf_url)}`);
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

    // --- Initial Load ---
    if (jobResultsDiv) { // Basic check, specific elements for filters/batch are checked inside their setup.
        fetchAndDisplayJobs();
    } else {
        console.warn("jobResultsDiv not found on page load. Initial job fetch skipped.");
    }
    updateBatchButtonState(); // Initial state for the batch button
});
