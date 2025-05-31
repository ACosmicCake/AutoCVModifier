// app/static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const cvTailorForm = document.getElementById('cvTailorForm');
    const cvFileInput = document.getElementById('cvFile');
    const tailorResultDiv = document.getElementById('tailorResult');
    const pdfDownloadLinkDiv = document.getElementById('pdfDownloadLinkDiv'); // ID updated
    const autoApplyButton = document.getElementById('autoApplyButton'); // Added

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
            // console.warn("Batch CV button or help text element not found.");
            return;
        }
        // Ensure CV file input and job results div exist for checks
        // If these critical elements are missing, disable button and show help.
        if (!cvFileInput || !jobResultsDiv) {
            // console.warn("CV file input or job results div not found for batch button state update.");
            batchGenerateCVsButton.disabled = true;
            batchGenerateCVsButton.classList.add('hidden'); // Explicitly hide
            batchCvHelpText.classList.remove('hidden');
            return;
        }

        const cvFileSelected = cvFileInput.files && cvFileInput.files.length > 0;
        const selectedJobsCount = jobResultsDiv.querySelectorAll('.job-select-checkbox:checked').length;

        if (cvFileSelected && selectedJobsCount > 0) {
            batchGenerateCVsButton.disabled = false;
            batchGenerateCVsButton.classList.remove('hidden'); // Show button
            batchCvHelpText.classList.add('hidden');    // Hide help text
        } else {
            batchGenerateCVsButton.disabled = true;
            batchGenerateCVsButton.classList.add('hidden'); // Hide button
            batchCvHelpText.classList.remove('hidden');   // Show help text
        }
    }

    // --- CV Tailoring ---
    if (cvTailorForm) {
        cvTailorForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading('Tailoring CV and generating PDF...');
            if (tailorResultDiv) tailorResultDiv.innerHTML = '';
            // Clear only dynamic content (links/messages) from pdfDownloadLinkDiv, not the button itself
            if (pdfDownloadLinkDiv) {
                const existingLink = pdfDownloadLinkDiv.querySelector('a');
                if (existingLink) existingLink.remove();
                const existingMessages = pdfDownloadLinkDiv.querySelectorAll('p');
                existingMessages.forEach(msg => msg.remove());
            }
            if (autoApplyButton) autoApplyButton.style.display = 'none'; // Hide button at start
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

                    // Always clear previous dynamic content (links or messages) before adding new ones
                    if (pdfDownloadLinkDiv) {
                        const existingLink = pdfDownloadLinkDiv.querySelector('a');
                        if (existingLink) existingLink.remove();
                        const existingErrorMessages = pdfDownloadLinkDiv.querySelectorAll('p');
                        existingErrorMessages.forEach(p => p.remove());
                    }

                    if (result.pdf_download_url && pdfDownloadLinkDiv) {
                        const downloadLink = document.createElement('a');
                        downloadLink.href = escapeHtml(result.pdf_download_url);
                        downloadLink.target = '_blank';
                        downloadLink.className = 'inline-block mt-3 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline';
                        downloadLink.textContent = 'Download Tailored CV (PDF)';
                        pdfDownloadLinkDiv.prepend(downloadLink); // Prepend to appear before the button

                        if (autoApplyButton) {
                            autoApplyButton.style.display = 'inline-block'; // Show button
                            if (result.pdf_filename) {
                                autoApplyButton.dataset.pdfFilename = result.pdf_filename; // Store filename
                            } else {
                                delete autoApplyButton.dataset.pdfFilename; // Clear if not present
                            }
                        }
                    } else if (result.error_pdf && pdfDownloadLinkDiv) {
                        const errorMsg = document.createElement('p');
                        errorMsg.className = "text-orange-500 mt-2";
                        errorMsg.textContent = `Note: ${escapeHtml(result.error_pdf)}`;
                        pdfDownloadLinkDiv.appendChild(errorMsg); // Append the message
                        if (autoApplyButton) autoApplyButton.style.display = 'none'; // Hide on error
                    } else if (pdfDownloadLinkDiv) { // Case for no PDF link and no specific PDF error
                        const noticeMsg = document.createElement('p');
                        noticeMsg.className = "text-orange-500 mt-2";
                        noticeMsg.textContent = `PDF download link not available. JSON preview above.`;
                        pdfDownloadLinkDiv.appendChild(noticeMsg); // Append the message
                        if (autoApplyButton) autoApplyButton.style.display = 'none'; // Hide if no PDF
                    }
                } else { // Response not ok
                    if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(result.error || 'Failed to tailor CV.')}</p>`;
                    // Ensure pdfDownloadLinkDiv is also cleared of old links/messages and button hidden
                    if (pdfDownloadLinkDiv) {
                        const existingLink = pdfDownloadLinkDiv.querySelector('a');
                        if (existingLink) existingLink.remove();
                        const existingErrorMessages = pdfDownloadLinkDiv.querySelectorAll('p');
                        existingErrorMessages.forEach(p => p.remove());
                    }
                    if (autoApplyButton) autoApplyButton.style.display = 'none'; // Hide on error
                }
            } catch (error) {
                hideLoading();
                console.error('CV Tailoring Error:', error);
                if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-red-600">An unexpected error occurred. Check console.</p>`;
                if (autoApplyButton) autoApplyButton.style.display = 'none'; // Hide on error
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

            html += `
                <div class="p-4 border rounded-md shadow-sm bg-gray-50 job-card" data-job-id-card="${escapeHtml(jobId)}">
                    <div class="flex items-start">
                        <input type="checkbox" class="job-select-checkbox mt-1 mr-3 h-5 w-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500" value="${escapeHtml(jobId)}" data-job-description="${escapeHtml(description)}" data-job-title="${escapeHtml(job.title || 'N/A')}">
                        <div class="flex-grow">
                            <div class="flex justify-between items-center">
                                <h4 class="text-lg font-bold text-blue-600">${escapeHtml(job.title || 'N/A')}</h4>
                                <button class="text-xs py-1 px-2 rounded border toggle-applied-btn ${isApplied ? 'bg-yellow-500 text-white' : 'bg-gray-200 hover:bg-gray-300'}" data-job-id="${escapeHtml(jobId)}">${isApplied ? 'Mark Unapplied' : 'Mark Applied'}</button>
                            </div>
                            <p class="text-sm text-gray-700">${escapeHtml(company)} - ${escapeHtml(location)}</p>
                            <p class="text-xs text-gray-500">Source: ${escapeHtml(source)} | Scraped: ${escapeHtml(formatted_date_scraped)} | DB ID: ${jobId}</p>
                            <p class="text-xs text-gray-500 job-applied-status">Status: ${isApplied ? 'Applied' : 'Not Applied'}</p>
                            ${job_url ? `<a href="${escapeHtml(job_url)}" target="_blank" class="text-blue-500 hover:underline text-sm mr-2">View Original Job</a>` : ''}
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

    // --- AutoApply Button Event Listener ---
    if (autoApplyButton) {
        autoApplyButton.addEventListener('click', async () => {
            if (!jobResultsDiv) {
                console.error("jobResultsDiv not found. Cannot proceed with AutoApply.");
                alert("An error occurred. Job results area not found.");
                return;
            }
            const selectedCheckboxes = jobResultsDiv.querySelectorAll('.job-select-checkbox:checked');

            if (selectedCheckboxes.length !== 1) {
                alert('Please select exactly one job from the list to AutoApply.');
                return;
            }

            const jobId = selectedCheckboxes[0].value;
            // Clear previous messages in tailorResultDiv before showing new ones
            if (tailorResultDiv) tailorResultDiv.innerHTML = '';

            let requestBody = {};
            // Attempt to get tailored_cv JSON
            if (tailorResultDiv) {
                const preElement = tailorResultDiv.querySelector('pre');
                if (preElement && preElement.textContent) {
                    try {
                        const tailoredCvJson = JSON.parse(preElement.textContent);
                        requestBody = { tailored_cv: tailoredCvJson };
                    } catch (parseError) {
                        console.warn('Failed to parse tailored CV JSON from <pre> tag:', parseError);
                        // Send empty object as per requirement if parsing fails
                        requestBody = {};
                    }
                } else {
                    console.warn('Tailored CV JSON <pre> tag not found in tailorResultDiv. Sending empty object for AutoApply.');
                    requestBody = {};
                }
            } else {
                // Should not happen if tailorResultDiv is essential for other messages too
                console.warn('tailorResultDiv itself not found. Sending empty object for AutoApply.');
                requestBody = {};
            }

            // Attempt to get pdf_filename from button's data attribute
            if (autoApplyButton && autoApplyButton.dataset.pdfFilename) {
                requestBody.pdf_filename = autoApplyButton.dataset.pdfFilename;
            } else {
                console.warn('PDF filename not found on autoApplyButton dataset. Will send request without it.');
                // requestBody.pdf_filename = null; // Or omit, backend should handle absence
            }

            showLoading('Attempting AutoApply...');

            try {
                // The endpoint /api/auto-apply/<job_id> exists from previous step,
                // but full auto-application logic is pending server-side.
                const response = await fetch(`/api/auto-apply/${jobId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });

                hideLoading();
                // For now, we expect this to fail or not be fully implemented.
                if (response.ok) {
                    const result = await response.json();
                    if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-green-600">AutoApply successful (mocked): ${escapeHtml(result.message || 'Application submitted.')}</p>`;
                } else {
                    // Handle non-OK responses (like 404, 500, etc.)
                     if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-orange-500">AutoApply feature is under development. Endpoint returned status: ${response.status}.</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('AutoApply Error:', error);
                if (tailorResultDiv) tailorResultDiv.innerHTML = `<p class="text-red-600">AutoApply feature is under development. Endpoint not ready or network error.</p>`;
            }
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

            // Clear single CV tailoring dynamic content (links/messages) from pdfDownloadLinkDiv
            if (pdfDownloadLinkDiv) {
                const existingLink = pdfDownloadLinkDiv.querySelector('a');
                if (existingLink) existingLink.remove();
                const existingMessages = pdfDownloadLinkDiv.querySelectorAll('p');
                existingMessages.forEach(msg => msg.remove());
            }
            // Also ensure autoApplyButton is hidden when starting batch generation,
            // as it's tied to the single CV generation flow.
            if (autoApplyButton) autoApplyButton.style.display = 'none';


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

                if (response.ok && resultsData.results) {
                    let html = '<h3 class="text-xl font-semibold mb-3">Batch CV Generation Results:</h3><div class="space-y-3">';
                    resultsData.results.forEach(res => {
                        html += `<div class="p-3 border rounded-md ${res.status === 'success' ? 'bg-green-50' : 'bg-red-50'}">`;
                        html += `<p class="font-semibold">${escapeHtml(res.job_title_summary || 'Job')}: <span class="${res.status === 'success' ? 'text-green-700' : 'text-red-700'}">${escapeHtml(res.status)}</span></p>`;
                        if (res.status === 'success' && res.pdf_url) {
                            html += `<a href="${escapeHtml(res.pdf_url)}" target="_blank" class="text-blue-500 hover:underline">Download PDF</a>`;
                        } else if (res.message) {
                            html += `<p class="text-sm text-red-600">${escapeHtml(res.message)}</p>`;
                        }
                        html += `</div>`;
                    });
                    html += '</div>';
                    if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = html;
                } else {
                     if (batchCvResultsDiv) batchCvResultsDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(resultsData.error || 'Failed to generate batch CVs.')}</p>`;
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
