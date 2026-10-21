// app/static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const $ = (id) => document.getElementById(id);

    // --- Elements ---
    const cvTailorForm = $('cvTailorForm');
    const cvFileInput = $('cvFile');
    const cvDropZone = $('cvDropZone');
    const cvFileLabel = $('cvFileLabel');
    const cvTextInput = $('cvText');
    const jobDescriptionInput = $('jobDescription');
    const linkedJobIdInput = $('linkedJobId');
    const linkedJobChip = $('linkedJobChip');
    const modelSelect = $('model');
    const customModelInput = $('customModel');
    const includeSummaryInput = $('includeSummary');
    const tailorBtn = $('tailorBtn');

    const resultEmpty = $('resultEmpty');
    const resultPanel = $('resultPanel');
    const tailorResultDiv = $('tailorResult');
    const downloadPdfBtn = $('downloadPdfBtn');
    const downloadJsonBtn = $('downloadJsonBtn');
    const previewPdfBtn = $('previewPdfBtn');
    const pdfPreview = $('pdfPreview');
    const pdfFrame = $('pdfFrame');
    const editJsonBtn = $('editJsonBtn');
    const jsonEditor = $('jsonEditor');
    const jsonEditorText = $('jsonEditorText');
    const rerenderBtn = $('rerenderBtn');
    const resetJsonBtn = $('resetJsonBtn');

    const generateCoverLetterBtn = $('generateCoverLetterBtn');
    const copyCoverLetterBtn = $('copyCoverLetterBtn');
    const coverLetterResultDiv = $('coverLetterResult');
    const qaForm = $('qaForm');
    const qaBtn = $('qaBtn');
    const qaResultDiv = $('qaResult');

    const jobScrapeForm = $('jobScrapeForm');
    const scrapeBtn = $('scrapeBtn');
    const jobResultsDiv = $('jobResults');
    const jobPagination = $('jobPagination');
    const jobCount = $('jobCount');
    const filterKeywordInput = $('filterKeyword');
    const filterLocationInput = $('filterLocation');
    const filterSourceSelect = $('filterSource');
    const filterAppliedStatusSelect = $('filterAppliedStatus');
    const clearFiltersButton = $('clearFiltersButton');
    const selectAllCheckbox = $('selectAllJobsCheckbox');

    const batchBar = $('batchBar');
    const batchGenerateCVsButton = $('batchGenerateCVsButton');
    const batchCvHelpText = $('batchCvHelpText');
    const clearSelectionBtn = $('clearSelectionBtn');
    const batchCvResultsDiv = $('batchCvResults');

    // --- State ---
    let cvMode = 'file';
    let tailored = null; // { cv, originalCv, jobDescription, jobId, pdfUrl, jsonUrl }
    let allJobs = [];
    let shownCount = 0;
    const JOBS_PER_PAGE = 10;
    const selectedJobIds = new Set();
    let batchRunning = false;

    // --- Utilities ---
    function escapeHtml(unsafe) {
        if (unsafe === null || typeof unsafe === 'undefined') return '';
        return unsafe.toString()
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    const storage = {
        get(key, fallback = null) {
            try { const v = localStorage.getItem(`cvtailor.${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
        },
        set(key, value) {
            try { localStorage.setItem(`cvtailor.${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ }
        },
    };

    function toast(message, type = 'info', timeout = 5000) {
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        $('toasts').appendChild(el);
        setTimeout(() => el.remove(), timeout);
    }

    function setLoading(button, loading, loadingText) {
        if (!button) return;
        if (loading) {
            button.dataset.originalHtml = button.innerHTML;
            button.disabled = true;
            button.classList.add('is-loading');
            button.innerHTML = `<span class="spinner"></span><span>${escapeHtml(loadingText || 'Working...')}</span>`;
        } else {
            button.disabled = false;
            button.classList.remove('is-loading');
            if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
        }
    }

    async function api(url, options = {}) {
        let response;
        try {
            response = await fetch(url, options);
        } catch (e) {
            throw new Error('Could not reach the server. Is it still running?');
        }
        let data = {};
        try { data = await response.json(); } catch { /* non-JSON response */ }
        return { ok: response.ok, status: response.status, data };
    }

    function debounce(fn, wait = 300) {
        let t;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
    }

    function formatDate(value) {
        if (!value) return '';
        const d = new Date(String(value).replace(' ', 'T'));
        return isNaN(d) ? String(value) : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    }

    // --- Models & provider status ---
    function selectedModel() {
        return modelSelect.value === '__custom__' ? customModelInput.value.trim() : modelSelect.value;
    }

    async function loadModels() {
        const { ok, data } = await api('/api/models');
        if (!ok) { toast('Could not load the model list.', 'error'); return; }

        const providers = data.providers || {};
        $('providerStatus').innerHTML = [
            ['Gemini', providers.google],
            ['OpenRouter', providers.openrouter],
        ].map(([name, on]) => `<span class="badge ${on ? 'badge-green' : 'badge-red'}" title="${on ? 'API key configured' : 'No API key in .env'}">${name}: ${on ? 'ready' : 'no key'}</span>`).join('');

        const groups = { google: 'Google Gemini (direct)', openrouter: 'OpenRouter' };
        modelSelect.innerHTML = Object.entries(groups).map(([provider, label]) => {
            const options = (data.models || []).filter(m => m.provider === provider).map(m =>
                `<option value="${escapeHtml(m.id)}" ${m.available ? '' : 'disabled'}>${escapeHtml(m.label)}${m.available ? '' : ' (no API key)'}</option>`
            ).join('');
            return options ? `<optgroup label="${escapeHtml(label)}">${options}</optgroup>` : '';
        }).join('') + '<option value="__custom__">Custom model id...</option>';

        const saved = storage.get('model');
        const savedCustom = storage.get('customModel', '');
        const optionExists = (v) => [...modelSelect.options].some(o => o.value === v && !o.disabled);
        if (saved && optionExists(saved)) modelSelect.value = saved;
        else if (optionExists(data.default)) modelSelect.value = data.default;
        else {
            const firstAvailable = [...modelSelect.options].find(o => !o.disabled);
            if (firstAvailable) modelSelect.value = firstAvailable.value;
        }
        customModelInput.value = savedCustom;
        customModelInput.classList.toggle('hidden', modelSelect.value !== '__custom__');

        if (!providers.google && !providers.openrouter) {
            toast('No API keys configured. Add GOOGLE_API_KEY or OPENROUTER_API_KEY to .env and restart.', 'error', 10000);
        }
    }

    modelSelect.addEventListener('change', () => {
        customModelInput.classList.toggle('hidden', modelSelect.value !== '__custom__');
        storage.set('model', modelSelect.value);
        if (modelSelect.value === '__custom__') customModelInput.focus();
    });
    customModelInput.addEventListener('change', () => storage.set('customModel', customModelInput.value.trim()));
    includeSummaryInput.checked = !!storage.get('includeSummary', false);
    includeSummaryInput.addEventListener('change', () => storage.set('includeSummary', includeSummaryInput.checked));

    // --- CV input (file or pasted text) ---
    document.querySelectorAll('[data-cv-mode]').forEach(tab => {
        tab.addEventListener('click', () => {
            cvMode = tab.dataset.cvMode;
            document.querySelectorAll('[data-cv-mode]').forEach(t => t.classList.toggle('active', t === tab));
            $('cvFilePanel').classList.toggle('hidden', cvMode !== 'file');
            $('cvTextPanel').classList.toggle('hidden', cvMode !== 'text');
            updateBatchBar();
        });
    });

    function updateFileLabel() {
        const file = cvFileInput.files && cvFileInput.files[0];
        cvDropZone.classList.toggle('has-file', !!file);
        cvFileLabel.innerHTML = file
            ? `<strong>${escapeHtml(file.name)}</strong> <span class="text-gray-500">(${Math.ceil(file.size / 1024)} KB) - click to change</span>`
            : 'Drop your CV here or <span class="text-blue-600 font-semibold">browse</span> (PDF, DOCX, TXT, JSON)';
        updateBatchBar();
    }

    cvFileInput.addEventListener('change', updateFileLabel);
    ['dragenter', 'dragover'].forEach(evt => cvDropZone.addEventListener(evt, (e) => { e.preventDefault(); cvDropZone.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach(evt => cvDropZone.addEventListener(evt, (e) => { e.preventDefault(); cvDropZone.classList.remove('dragover'); }));
    cvDropZone.addEventListener('drop', (e) => {
        if (e.dataTransfer && e.dataTransfer.files.length) {
            cvFileInput.files = e.dataTransfer.files;
            updateFileLabel();
        }
    });
    cvTextInput.addEventListener('input', debounce(updateBatchBar, 200));

    function hasCv() {
        return cvMode === 'file' ? !!(cvFileInput.files && cvFileInput.files[0]) : cvTextInput.value.trim().length > 0;
    }

    function appendCv(formData) {
        if (cvMode === 'file') formData.append('cv_file', cvFileInput.files[0]);
        else formData.append('cv_text', cvTextInput.value.trim());
    }

    // --- Linking a saved job to the tailoring form ---
    function linkJob(job) {
        jobDescriptionInput.value = job.description || '';
        linkedJobIdInput.value = job.id;
        linkedJobChip.innerHTML = `<span class="truncate">For: ${escapeHtml(job.title)}${job.company ? ' @ ' + escapeHtml(job.company) : ''}</span><button type="button" title="Unlink job" aria-label="Unlink job">&times;</button>`;
        linkedJobChip.classList.remove('hidden');
        linkedJobChip.querySelector('button').addEventListener('click', unlinkJob);
        $('cv-tailoring').scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (!job.description) toast('This job has no saved description. Paste one in.', 'info');
    }

    function unlinkJob() {
        linkedJobIdInput.value = '';
        linkedJobChip.classList.add('hidden');
    }

    jobDescriptionInput.addEventListener('input', () => {
        // Editing the description by hand still keeps the link, so the CV is saved against that job.
        if (!jobDescriptionInput.value.trim()) unlinkJob();
    });

    // --- CV Tailoring ---
    function showResult(result, jobDescription, jobId) {
        tailored = {
            cv: result.tailored_cv_json,
            originalCv: result.tailored_cv_json,
            jobDescription,
            jobId,
            pdfUrl: result.pdf_download_url,
            jsonUrl: result.json_download_url,
        };
        resultEmpty.classList.add('hidden');
        resultPanel.classList.remove('hidden');
        updateResultLinks();
        jsonEditorText.value = JSON.stringify(tailored.cv, null, 2);
        coverLetterResultDiv.innerHTML = '';
        copyCoverLetterBtn.classList.add('hidden');
        qaResultDiv.innerHTML = '';
        if (window.innerWidth < 1024) $('result-section').scrollIntoView({ behavior: 'smooth' });
    }

    function updateResultLinks() {
        const hasPdf = !!tailored.pdfUrl;
        downloadPdfBtn.classList.toggle('hidden', !hasPdf);
        previewPdfBtn.classList.toggle('hidden', !hasPdf);
        if (hasPdf) downloadPdfBtn.href = tailored.pdfUrl;
        downloadJsonBtn.classList.toggle('hidden', !tailored.jsonUrl);
        if (tailored.jsonUrl) downloadJsonBtn.href = tailored.jsonUrl;
        $('autoApplyResultBtn').classList.toggle('hidden', !(hasPdf && tailored.jobId));
        if (!pdfPreview.classList.contains('hidden') && hasPdf) pdfFrame.src = `${tailored.pdfUrl}?inline=1`;
    }

    cvTailorForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!hasCv()) { toast(cvMode === 'file' ? 'Please choose your CV file.' : 'Please paste your CV text.', 'error'); return; }
        const jobDescription = jobDescriptionInput.value.trim();
        if (!jobDescription) { toast('Please paste a job description or pick a job below.', 'error'); return; }
        const model = selectedModel();
        if (!model) { toast('Please choose a model.', 'error'); return; }

        const formData = new FormData();
        appendCv(formData);
        formData.append('job_description', jobDescription);
        formData.append('model', model);
        formData.append('include_summary', includeSummaryInput.checked ? 'true' : 'false');
        const jobId = linkedJobIdInput.value;
        if (jobId) formData.append('job_id', jobId);

        setLoading(tailorBtn, true, 'Tailoring your CV...');
        try {
            const { ok, data } = await api('/api/tailor-cv', { method: 'POST', body: formData });
            if (data.tailored_cv_json) {
                showResult(data, jobDescription, jobId || null);
                const cls = ok ? 'text-green-700' : 'text-yellow-700';
                const title = data.job_title ? ` <span class="text-gray-500">(${escapeHtml(data.job_title)})</span>` : '';
                tailorResultDiv.innerHTML = `<p class="${cls} font-semibold">${escapeHtml(data.message || 'CV tailored!')}${title}</p>` +
                    (data.error_pdf ? `<p class="text-sm text-yellow-700">${escapeHtml(data.error_pdf)}</p>` : '');
                toast(ok ? 'Your tailored CV is ready.' : (data.error_pdf || data.message), ok ? 'success' : 'error');
                if (jobId) fetchAndDisplayJobs();
            } else {
                toast(data.error || 'Failed to tailor CV.', 'error', 9000);
            }
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(tailorBtn, false);
        }
    });

    previewPdfBtn.addEventListener('click', () => {
        const opening = pdfPreview.classList.contains('hidden');
        pdfPreview.classList.toggle('hidden', !opening);
        previewPdfBtn.textContent = opening ? 'Hide preview' : 'Preview';
        if (opening && tailored && tailored.pdfUrl) pdfFrame.src = `${tailored.pdfUrl}?inline=1`;
    });

    editJsonBtn.addEventListener('click', () => {
        const opening = jsonEditor.classList.contains('hidden');
        jsonEditor.classList.toggle('hidden', !opening);
        editJsonBtn.textContent = opening ? 'Close editor' : 'Edit content';
    });

    resetJsonBtn.addEventListener('click', () => {
        if (tailored) jsonEditorText.value = JSON.stringify(tailored.originalCv, null, 2);
    });

    rerenderBtn.addEventListener('click', async () => {
        if (!tailored) return;
        let cv;
        try {
            cv = JSON.parse(jsonEditorText.value);
        } catch (err) {
            toast(`The JSON is not valid: ${err.message}`, 'error', 8000);
            return;
        }
        setLoading(rerenderBtn, true, 'Rendering...');
        try {
            const { ok, data } = await api('/api/render-pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cv_json: cv, job_id: tailored.jobId }),
            });
            if (!ok) { toast(data.error || 'Failed to render PDF.', 'error'); return; }
            tailored.cv = data.tailored_cv_json;
            tailored.pdfUrl = data.pdf_download_url;
            tailored.jsonUrl = data.json_download_url;
            updateResultLinks();
            toast('PDF re-rendered with your edits.', 'success');
            if (tailored.jobId) fetchAndDisplayJobs();
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(rerenderBtn, false);
        }
    });

    // --- Follow-ups ---
    generateCoverLetterBtn.addEventListener('click', async () => {
        if (!tailored) { toast('Please tailor a CV first.', 'error'); return; }
        setLoading(generateCoverLetterBtn, true, 'Writing...');
        coverLetterResultDiv.innerHTML = '';
        try {
            const { ok, data } = await api('/api/generate-cover-letter', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cv_json: tailored.cv, job_description: tailored.jobDescription, model: selectedModel() }),
            });
            if (ok) {
                coverLetterResultDiv.innerHTML = `<pre class="output" id="coverLetterText">${escapeHtml(data.cover_letter)}</pre>`;
                copyCoverLetterBtn.classList.remove('hidden');
            } else {
                coverLetterResultDiv.innerHTML = `<p class="text-red-600 text-sm">${escapeHtml(data.error || 'Failed to generate cover letter.')}</p>`;
            }
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(generateCoverLetterBtn, false);
        }
    });

    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            toast('Copied to clipboard.', 'success', 2000);
        } catch {
            toast('Could not copy automatically. Select the text and copy it manually.', 'error');
        }
    }

    copyCoverLetterBtn.addEventListener('click', () => {
        const el = $('coverLetterText');
        if (el) copyText(el.textContent);
    });

    qaForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!tailored) { toast('Please tailor a CV first.', 'error'); return; }
        const questions = $('applicationQuestion').value.split(/\r?\n/).map(q => q.trim()).filter(Boolean);
        if (questions.length === 0) { toast('Please enter at least one question.', 'error'); return; }

        setLoading(qaBtn, true, `Answering ${questions.length}...`);
        qaResultDiv.innerHTML = '';
        try {
            const { ok, data } = await api('/api/answer-question', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cv_json: tailored.cv, job_description: tailored.jobDescription, question: questions, model: selectedModel() }),
            });
            if (!ok) {
                qaResultDiv.innerHTML = `<p class="text-red-600 text-sm">${escapeHtml(data.error || 'Failed to get answers.')}</p>`;
                return;
            }
            qaResultDiv.innerHTML = (data.answers || []).map((item, i) => `
                <div>
                    <div class="flex items-start justify-between gap-2 mb-1">
                        <p class="text-sm font-semibold">${i + 1}. ${escapeHtml(item.question)}</p>
                        <button type="button" class="btn btn-gray btn-xs copy-answer" data-index="${i}">Copy</button>
                    </div>
                    <pre class="output ${item.ok ? '' : 'text-red-600'}">${escapeHtml(item.answer)}</pre>
                </div>`).join('');
            qaResultDiv.querySelectorAll('.copy-answer').forEach(btn => {
                btn.addEventListener('click', () => copyText(data.answers[Number(btn.dataset.index)].answer));
            });
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(qaBtn, false);
        }
    });

    // --- Jobs list ---
    function currentFilters() {
        return {
            keyword: filterKeywordInput.value.trim(),
            location: filterLocationInput.value.trim(),
            source: filterSourceSelect.value,
            applied_status: filterAppliedStatusSelect.value,
        };
    }

    async function fetchAndDisplayJobs() {
        const params = new URLSearchParams();
        Object.entries(currentFilters()).forEach(([key, value]) => {
            if (value && !(key === 'applied_status' && value === 'all')) params.append(key, value);
        });
        try {
            const { ok, data } = await api(`/api/jobs?${params.toString()}`);
            if (!ok) {
                jobResultsDiv.innerHTML = `<p class="text-red-600">${escapeHtml(data.error || 'Failed to fetch jobs.')}</p>`;
                return;
            }
            updateSourceOptions(data.sources || []);
            allJobs = data.jobs || [];
            // Drop selections that are no longer visible.
            const visibleIds = new Set(allJobs.map(j => String(j.id)));
            [...selectedJobIds].forEach(id => { if (!visibleIds.has(id)) selectedJobIds.delete(id); });
            shownCount = Math.max(JOBS_PER_PAGE, Math.min(shownCount, allJobs.length));
            renderJobs();
        } catch (err) {
            jobResultsDiv.innerHTML = `<p class="text-red-600">${escapeHtml(err.message)}</p>`;
        }
    }

    function updateSourceOptions(sources) {
        const current = filterSourceSelect.value;
        filterSourceSelect.innerHTML = '<option value="">All sources</option>' +
            sources.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
        if (current && !sources.includes(current)) {
            filterSourceSelect.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(current)}">${escapeHtml(current)}</option>`);
        }
        filterSourceSelect.value = current;
    }

    const APPLICATION_BADGES = {
        queued: ['badge-blue', 'Auto-apply queued'],
        running: ['badge-blue', 'Applying...'],
        needs_attention: ['badge-yellow', 'Apply: needs you'],
        ready_for_review: ['badge-purple', 'Review & submit'],
        submitted: ['badge-green', 'Application sent'],
        failed: ['badge-red', 'Auto-apply failed'],
        cancelled: ['', 'Auto-apply cancelled'],
    };
    const ACTIVE_APPLICATION = ['queued', 'running', 'needs_attention', 'ready_for_review'];

    function applicationBadge(job) {
        if (!job.application) return '';
        const [cls, text] = APPLICATION_BADGES[job.application.status] || ['', job.application.status];
        return `<a href="#application-${job.application.id}" class="badge ${cls}" data-action="show-application">${text}</a>`;
    }

    function jobCardHtml(job) {
        const id = String(job.id);
        const isApplied = job.applied === 1 || job.applied === true;
        const selected = selectedJobIds.has(id);
        const applyActive = job.application && ACTIVE_APPLICATION.includes(job.application.status);
        return `
            <div class="job-card ${selected ? 'is-selected' : ''} ${isApplied ? 'is-applied' : ''}" data-job-id="${escapeHtml(id)}">
                <div class="flex items-start gap-3">
                    <input type="checkbox" class="job-select-checkbox mt-1 h-4 w-4" value="${escapeHtml(id)}" ${selected ? 'checked' : ''} aria-label="Select job">
                    <div class="flex-grow min-w-0">
                        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                            <div class="min-w-0">
                                <h4 class="font-semibold text-blue-700 truncate">
                                    ${job.url ? `<a href="${escapeHtml(job.url)}" target="_blank" rel="noopener" class="hover:underline">${escapeHtml(job.title || 'Untitled role')}</a>` : escapeHtml(job.title || 'Untitled role')}
                                </h4>
                                <p class="text-sm text-gray-700">${escapeHtml(job.company || 'Unknown company')}${job.location ? ' &middot; ' + escapeHtml(job.location) : ''}</p>
                                <div class="flex flex-wrap items-center gap-2 mt-1">
                                    <span class="badge badge-blue">${escapeHtml(job.source || 'unknown')}</span>
                                    <span class="text-xs text-gray-500">Saved ${escapeHtml(formatDate(job.date_scraped))}</span>
                                    ${isApplied ? '<span class="badge badge-yellow">Applied</span>' : ''}
                                    ${job.cv_filename ? '<span class="badge badge-green">CV ready</span>' : ''}
                                    ${applicationBadge(job)}
                                </div>
                            </div>
                            <div class="flex flex-wrap gap-1 sm:justify-end flex-shrink-0">
                                <button type="button" class="btn btn-blue btn-xs" data-action="tailor">Tailor CV</button>
                                ${job.cv_filename ? `<a class="btn btn-green btn-xs" href="/api/download-cv/${encodeURIComponent(job.cv_filename)}" target="_blank" rel="noopener">Download CV</a>` : ''}
                                ${job.cv_filename && !applyActive ? `<button type="button" class="btn btn-purple btn-xs" data-action="auto-apply" title="Fill this job's application form automatically">Auto apply</button>` : ''}
                                <button type="button" class="btn ${isApplied ? 'btn-yellow' : 'btn-gray'} btn-xs" data-action="toggle-applied">${isApplied ? 'Mark unapplied' : 'Mark applied'}</button>
                                <button type="button" class="btn btn-red-outline btn-xs" data-action="delete" title="Delete job">Delete</button>
                            </div>
                        </div>
                        <details class="mt-2 text-sm">
                            <summary class="cursor-pointer text-gray-600 hover:text-gray-800">Description</summary>
                            <div class="description mt-1 text-gray-700 leading-relaxed">${escapeHtml(job.description || 'No description available.')}</div>
                        </details>
                    </div>
                </div>
            </div>`;
    }

    function renderJobs() {
        if (allJobs.length === 0) {
            const filtered = Object.values(currentFilters()).some(v => v && v !== 'all');
            jobResultsDiv.innerHTML = `<p class="text-gray-500 text-sm">${filtered ? 'No saved jobs match these filters.' : 'No saved jobs yet. Scrape some above to get started.'}</p>`;
            jobPagination.innerHTML = '';
            jobCount.textContent = '';
            updateBatchBar();
            return;
        }
        const visible = allJobs.slice(0, shownCount);
        jobResultsDiv.innerHTML = visible.map(jobCardHtml).join('');
        jobCount.textContent = `Showing ${visible.length} of ${allJobs.length}`;
        jobPagination.innerHTML = shownCount < allJobs.length
            ? `<button type="button" id="loadMoreJobsBtn" class="btn btn-gray btn-sm">Show ${Math.min(JOBS_PER_PAGE, allJobs.length - shownCount)} more</button>`
            : '';
        const loadMore = $('loadMoreJobsBtn');
        if (loadMore) loadMore.addEventListener('click', () => { shownCount += JOBS_PER_PAGE; renderJobs(); });
        updateBatchBar();
    }

    function jobById(id) {
        return allJobs.find(j => String(j.id) === String(id));
    }

    // Event delegation: one listener for every job card.
    jobResultsDiv.addEventListener('change', (e) => {
        if (!e.target.classList.contains('job-select-checkbox')) return;
        const id = e.target.value;
        if (e.target.checked) selectedJobIds.add(id); else selectedJobIds.delete(id);
        e.target.closest('.job-card').classList.toggle('is-selected', e.target.checked);
        updateBatchBar();
    });

    jobResultsDiv.addEventListener('click', async (e) => {
        const button = e.target.closest('[data-action]');
        if (!button) return;
        const card = button.closest('.job-card');
        const job = jobById(card.dataset.jobId);
        if (!job) return;

        if (button.dataset.action === 'tailor') {
            linkJob(job);
        } else if (button.dataset.action === 'auto-apply') {
            e.preventDefault();
            if (window.AutoApply) window.AutoApply.applyToJobs([job.id], button);
        } else if (button.dataset.action === 'show-application') {
            e.preventDefault();
            if (window.AutoApply) window.AutoApply.showApplication(job.application.id);
        } else if (button.dataset.action === 'toggle-applied') {
            button.disabled = true;
            const { ok, data } = await api(`/api/jobs/${job.id}/toggle-applied`, { method: 'POST' }).catch(err => ({ ok: false, data: { error: err.message } }));
            if (ok) {
                job.applied = data.new_status;
                if (filterAppliedStatusSelect.value !== 'all') fetchAndDisplayJobs();
                else card.outerHTML = jobCardHtml(job);
            } else {
                toast(data.error || 'Could not update status.', 'error');
                button.disabled = false;
            }
        } else if (button.dataset.action === 'delete') {
            if (!confirm(`Delete "${job.title}" from your saved jobs?`)) return;
            const { ok, data } = await api(`/api/jobs/${job.id}`, { method: 'DELETE' }).catch(err => ({ ok: false, data: { error: err.message } }));
            if (ok) {
                selectedJobIds.delete(String(job.id));
                if (linkedJobIdInput.value === String(job.id)) unlinkJob();
                allJobs = allJobs.filter(j => j !== job);
                renderJobs();
                toast('Job deleted.', 'info', 2500);
            } else {
                toast(data.error || 'Could not delete job.', 'error');
            }
        }
    });

    selectAllCheckbox.addEventListener('change', () => {
        allJobs.slice(0, shownCount).forEach(job => {
            if (selectAllCheckbox.checked) selectedJobIds.add(String(job.id)); else selectedJobIds.delete(String(job.id));
        });
        renderJobs();
    });

    clearSelectionBtn.addEventListener('click', () => {
        selectedJobIds.clear();
        selectAllCheckbox.checked = false;
        renderJobs();
    });

    const debouncedFetch = debounce(fetchAndDisplayJobs, 300);
    [filterKeywordInput, filterLocationInput].forEach(input => input.addEventListener('input', debouncedFetch));
    [filterSourceSelect, filterAppliedStatusSelect].forEach(select => select.addEventListener('change', fetchAndDisplayJobs));
    clearFiltersButton.addEventListener('click', () => {
        filterKeywordInput.value = '';
        filterLocationInput.value = '';
        filterSourceSelect.value = '';
        filterAppliedStatusSelect.value = 'all';
        fetchAndDisplayJobs();
    });

    // --- Job scraping ---
    const scrapeFields = ['searchTerm', 'location', 'resultsWanted', 'hoursOld'];
    const savedScrape = storage.get('scrape', {});
    scrapeFields.forEach(id => { if (savedScrape[id] !== undefined) $(id).value = savedScrape[id]; });
    if (Array.isArray(savedScrape.sites)) {
        document.querySelectorAll('.site-cb').forEach(cb => { cb.checked = savedScrape.sites.includes(cb.value); });
    }
    if (savedScrape.isRemote !== undefined) $('isRemote').checked = !!savedScrape.isRemote;
    if (savedScrape.easyApplyOnly !== undefined) $('easyApplyOnly').checked = !!savedScrape.easyApplyOnly;
    if (savedScrape.jobType !== undefined) $('jobType').value = savedScrape.jobType;

    jobScrapeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const sites = [...document.querySelectorAll('.site-cb:checked')].map(cb => cb.value);
        if (sites.length === 0) { toast('Pick at least one site to scrape.', 'error'); return; }

        const values = Object.fromEntries(scrapeFields.map(id => [id, $(id).value]));
        storage.set('scrape', { ...values, sites, isRemote: $('isRemote').checked,
                                easyApplyOnly: $('easyApplyOnly').checked, jobType: $('jobType').value });

        const params = new URLSearchParams({
            search_term: values.searchTerm,
            location: values.location,
            site_names: sites.join(','),
            results_wanted: values.resultsWanted || 5,
        });
        if (values.hoursOld) params.append('hours_old', values.hoursOld);
        if ($('isRemote').checked) params.append('is_remote', 'true');
        if ($('easyApplyOnly').checked) params.append('easy_apply', 'true');
        if ($('jobType').value) params.append('job_type', $('jobType').value);

        setLoading(scrapeBtn, true, 'Scraping...');
        try {
            const { ok, data } = await api(`/api/scrape-jobs?${params.toString()}`);
            if (ok) {
                const n = (data.jobs || []).length;
                const skipped = data.skipped_by_rules ? ` ${data.skipped_by_rules} skipped by your job rules.` : '';
                toast((n ? `Saved ${n} new job${n === 1 ? '' : 's'}.` : 'No new jobs found (they may already be in your list).') + skipped, n ? 'success' : 'info');
                await fetchAndDisplayJobs();
            } else {
                toast(data.error || 'Failed to scrape jobs.', 'error', 9000);
            }
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(scrapeBtn, false);
        }
    });

    // --- Batch CV generation ---
    function updateBatchBar() {
        const count = selectedJobIds.size;
        batchBar.classList.toggle('hidden', count === 0 && !batchRunning);
        document.body.classList.toggle('has-batch-bar', count > 0 || batchRunning);
        if (batchRunning) return;
        const cvReady = hasCv();
        batchGenerateCVsButton.disabled = !(cvReady && count > 0);
        batchGenerateCVsButton.textContent = `Generate ${count} tailored CV${count === 1 ? '' : 's'}`;
        batchCvHelpText.textContent = cvReady
            ? `${count} job${count === 1 ? '' : 's'} selected.`
            : `${count} job${count === 1 ? '' : 's'} selected. Add your CV in step 1 to generate tailored CVs.`;
        const visible = allJobs.slice(0, shownCount);
        selectAllCheckbox.checked = visible.length > 0 && visible.every(j => selectedJobIds.has(String(j.id)));

        const applicable = selectedApplicableJobIds();
        batchAutoApplyBtn.classList.toggle('hidden', applicable.length === 0);
        batchAutoApplyBtn.textContent = `Auto apply to ${applicable.length} job${applicable.length === 1 ? '' : 's'} with CVs`;

        const needCv = selectedApplicableJobIds(false).filter(id => !jobById(id).cv_filename);
        tailorAndApplyBtn.classList.toggle('hidden', !(cvReady && needCv.length));
        tailorAndApplyBtn.textContent = `Tailor & apply to ${applicable.length + needCv.length}`;
    }

    // Selected jobs without an application in progress (by default only those that already have a CV).
    function selectedApplicableJobIds(requireCv = true) {
        return [...selectedJobIds].map(jobById).filter(job => job && (!requireCv || job.cv_filename) &&
            !(job.application && ACTIVE_APPLICATION.includes(job.application.status))).map(job => job.id);
    }

    const tailorAndApplyBtn = $('tailorAndApplyBtn');
    tailorAndApplyBtn.addEventListener('click', () => {
        if (window.AutoApply) window.AutoApply.tailorAndApply(selectedApplicableJobIds(false), tailorAndApplyBtn);
    });

    const batchAutoApplyBtn = $('batchAutoApplyBtn');
    batchAutoApplyBtn.addEventListener('click', () => {
        const ids = selectedApplicableJobIds();
        if (ids.length && window.AutoApply) window.AutoApply.applyToJobs(ids, batchAutoApplyBtn);
    });

    batchGenerateCVsButton.addEventListener('click', async () => {
        if (!hasCv()) { toast('Please add your CV in step 1 first.', 'error'); return; }
        const ids = [...selectedJobIds];
        if (ids.length === 0) return;
        const model = selectedModel();
        if (!model) { toast('Please choose a model.', 'error'); return; }

        const formData = new FormData();
        appendCv(formData);
        ids.forEach(id => formData.append('job_ids[]', id));
        formData.append('model', model);
        formData.append('include_summary', includeSummaryInput.checked ? 'true' : 'false');

        batchRunning = true;
        batchCvResultsDiv.innerHTML = '';
        setLoading(batchGenerateCVsButton, true, `Generating ${ids.length} CV${ids.length === 1 ? '' : 's'}...`);
        batchCvHelpText.textContent = 'This can take a few minutes. You can keep browsing.';
        try {
            const { ok, data } = await api('/api/batch-generate-cvs', { method: 'POST', body: formData });
            if (!ok || !data.results) {
                toast(data.error || 'Batch generation failed.', 'error', 9000);
                return;
            }
            const successes = data.results.filter(r => r.status === 'success');
            const failures = data.results.filter(r => r.status !== 'success');
            batchCvResultsDiv.innerHTML = `
                <div class="border rounded-lg p-4 bg-gray-50">
                    <h4 class="font-semibold mb-2">Batch results: ${successes.length} succeeded${failures.length ? `, ${failures.length} failed` : ''}</h4>
                    <ul class="text-sm space-y-1">
                        ${data.results.map(r => `<li>
                            <span class="badge ${r.status === 'success' ? 'badge-green' : 'badge-red'}">${r.status === 'success' ? 'OK' : 'Error'}</span>
                            ${escapeHtml(r.job_title_summary || 'Job ' + r.job_id)}
                            ${r.pdf_url ? ` &middot; <a class="text-blue-600 hover:underline" href="${escapeHtml(r.pdf_url)}" target="_blank" rel="noopener">PDF</a>` : ''}
                            ${r.message ? ` <span class="text-red-600">${escapeHtml(r.message)}</span>` : ''}
                        </li>`).join('')}
                    </ul>
                </div>`;
            toast(`Generated ${successes.length} of ${data.results.length} CVs.`, failures.length ? 'info' : 'success');
            successes.forEach(r => selectedJobIds.delete(String(r.job_id)));
            await fetchAndDisplayJobs();
            successes.forEach(r => {
                const card = jobResultsDiv.querySelector(`.job-card[data-job-id="${CSS.escape(String(r.job_id))}"]`);
                if (card) { card.classList.add('flash'); setTimeout(() => card.classList.remove('flash'), 2500); }
            });
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            batchRunning = false;
            setLoading(batchGenerateCVsButton, false);
            updateBatchBar();
        }
    });

    $('autoApplyResultBtn').addEventListener('click', (e) => {
        if (tailored && tailored.jobId && window.AutoApply) window.AutoApply.applyToJobs([Number(tailored.jobId)], e.currentTarget);
    });

    // Shared helpers for autoapply.js
    window.CVTailor = {
        api, toast, escapeHtml, setLoading, debounce, selectedModel, hasCv, jobById,
        getTailoredCv: () => (tailored ? tailored.cv : null),
        refreshJobs: fetchAndDisplayJobs,
        jobs: () => allJobs,
        // Form data for /api/batch-generate-cvs with the CV from step 1 and the current options.
        cvFormData: () => {
            const formData = new FormData();
            appendCv(formData);
            formData.append('model', selectedModel());
            formData.append('include_summary', includeSummaryInput.checked ? 'true' : 'false');
            return formData;
        },
    };

    // --- Initial Load ---
    loadModels();
    fetchAndDisplayJobs();
    updateBatchBar();
});
