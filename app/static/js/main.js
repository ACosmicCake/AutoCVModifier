// cv_tailor_project/app/static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const cvTailorForm = document.getElementById('cvTailorForm');
    const tailorResultDiv = document.getElementById('tailorResult');
    const pdfDownloadLinkDiv = document.getElementById('pdfDownloadLink');

    // CV Analysis constants removed
    // const cvAnalysisForm = document.getElementById('cvAnalysisForm');
    // const analysisResultPre = document.querySelector('#analysisResultDisplay pre');

    const jobScrapeForm = document.getElementById('jobScrapeForm');
    const jobResultsDiv = document.getElementById('jobResults');
    const loadingIndicator = document.getElementById('loadingIndicator');

    function showLoading(message = 'Processing...') {
        loadingIndicator.querySelector('p').textContent = message;
        loadingIndicator.classList.remove('hidden');
    }

    function hideLoading() {
        loadingIndicator.classList.add('hidden');
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

    // --- CV Tailoring ---
    if (cvTailorForm) {
        cvTailorForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading('Tailoring CV and generating PDF...');
            tailorResultDiv.innerHTML = '';
            pdfDownloadLinkDiv.innerHTML = '';

            const formData = new FormData(cvTailorForm);

            try {
                const response = await fetch('/api/tailor-cv', {
                    method: 'POST',
                    body: formData,
                });

                const result = await response.json(); // Always try to parse JSON
                hideLoading();

                if (response.ok) {
                    tailorResultDiv.innerHTML = `<p class="text-green-600">Success: ${escapeHtml(result.message || 'CV Tailored!')}</p>`;

                    if (result.tailored_cv_json) {
                        const formattedJson = JSON.stringify(result.tailored_cv_json, null, 2);
                        tailorResultDiv.innerHTML += `<h4 class="font-semibold mt-2">Tailored CV (JSON Preview):</h4><pre>${escapeHtml(formattedJson)}</pre>`;
                    }

                    if (result.pdf_download_url) {
                        pdfDownloadLinkDiv.innerHTML = `<a href="${escapeHtml(result.pdf_download_url)}" target="_blank" class="inline-block mt-3 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline">Download Tailored CV (PDF)</a>`;
                    } else if (result.error_pdf) {
                         pdfDownloadLinkDiv.innerHTML = `<p class="text-orange-500 mt-2">Note: ${escapeHtml(result.error_pdf)}</p>`;
                    } else {
                         pdfDownloadLinkDiv.innerHTML = `<p class="text-orange-500 mt-2">PDF download link not available. JSON preview above.</p>`;
                    }
                } else {
                    tailorResultDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(result.error || 'Failed to tailor CV.')}</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('CV Tailoring Error:', error);
                tailorResultDiv.innerHTML = `<p class="text-red-600">An unexpected error occurred. Check console.</p>`;
            }
        });
    }

    // --- CV Analysis --- Block Removed

    // --- Job Scraping ---
    if (jobScrapeForm) {
        jobScrapeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading('Scraping jobs...');
            jobResultsDiv.innerHTML = '<p>Scraping jobs, please wait...</p>';

            const params = new URLSearchParams({
                search_term: document.getElementById('searchTerm').value,
                location: document.getElementById('location').value,
                site_names: document.getElementById('siteNames').value,
                results_wanted: document.getElementById('resultsWanted').value || 5
            });

            try {
                const response = await fetch(`/api/scrape-jobs?${params.toString()}`);
                const result = await response.json(); // Always try to parse JSON
                hideLoading();

                if (response.ok && result.jobs) {
                    if (result.jobs.length > 0) {
                        let html = '<h3 class="text-xl font-semibold mb-3">Scraped Jobs:</h3><div class="space-y-4">';
                        result.jobs.forEach(job => {
                            html += `
                                <div class="p-4 border rounded-md shadow-sm bg-gray-50 job-card">
                                    <h4 class="text-lg font-bold text-blue-600">${escapeHtml(job.title || 'N/A')} ${job.is_remote ? '<span class="text-xs bg-green-200 text-green-800 p-1 rounded ml-2">Remote</span>': ''}</h4>
                                    <p class="text-sm text-gray-700">${escapeHtml(job.company || 'N/A')} - ${escapeHtml(job.location || 'N/A')}</p>
                                    <p class="text-xs text-gray-500">Source: ${escapeHtml(job.site || 'N/A')} | Posted: ${escapeHtml(job.date_posted || job.job_posted_date || 'N/A')}</p>
                                    ${job.job_url ? `<a href="${escapeHtml(job.job_url)}" target="_blank" class="text-blue-500 hover:underline text-sm">View Job</a>` : ''}
                                    ${job.description ? `<details class="mt-2 text-sm">
                                        <summary class="cursor-pointer text-gray-600 hover:text-gray-800">Description</summary>
                                        <p class="mt-1 text-gray-600 leading-relaxed">${escapeHtml(job.description.substring(0,300))}...</p> <!-- Show snippet -->
                                    </details>` : '<p class="mt-2 text-sm text-gray-500">No description available.</p>'}
                                </div>`;
                        });
                        html += '</div>';
                        jobResultsDiv.innerHTML = html;
                    } else {
                        jobResultsDiv.innerHTML = '<p>No jobs found for your criteria.</p>';
                    }
                } else {
                    jobResultsDiv.innerHTML = `<p class="text-red-600">Error: ${escapeHtml(result.error || 'Failed to scrape jobs.')}</p>`;
                }
            } catch (error) {
                hideLoading();
                console.error('Job Scraping Error:', error);
                jobResultsDiv.innerHTML = '<p class="text-red-600">An unexpected error occurred while scraping jobs. Check console.</p>';
            }
        });
    }
});
