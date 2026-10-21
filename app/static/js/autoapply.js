// app/static/js/autoapply.js
document.addEventListener('DOMContentLoaded', () => {
    const { api, toast, escapeHtml, setLoading } = window.CVTailor;
    const $ = (id) => document.getElementById(id);

    const profileForm = $('profileForm');
    const profilePanel = $('profilePanel');
    const profileStatus = $('profileStatus');
    const savedAnswers = $('savedAnswers');
    const applicationsList = $('applicationsList');
    const autoSubmitToggle = $('autoSubmitToggle');

    const DECLINE = "I don't wish to answer";
    const EEO_FIELDS = [
        ['gender', 'Gender', ['Male', 'Female', 'Non-binary']],
        ['race_ethnicity', 'Race / ethnicity', ['American Indian or Alaska Native', 'Asian', 'Black or African American',
            'Native Hawaiian or Other Pacific Islander', 'White', 'Two or More Races']],
        ['hispanic_latino', 'Hispanic or Latino?', ['Yes', 'No']],
        ['veteran_status', 'Veteran status', ['I am not a protected veteran', 'I identify as one or more of the classifications of protected veteran']],
        ['disability_status', 'Disability', ['No, I do not have a disability', 'Yes, I have a disability (or previously had one)']],
    ];
    $('eeoFields').innerHTML = EEO_FIELDS.map(([name, label, options]) => `
        <div><label class="label" for="pf_${name}">${escapeHtml(label)}</label>
            <select class="input" id="pf_${name}" name="${name}">
                <option>${escapeHtml(DECLINE)}</option>
                ${options.map(o => `<option>${escapeHtml(o)}</option>`).join('')}
            </select></div>`).join('');

    // --- Profile ---
    let missingFields = [];

    function addAnswerRow(question = '', answer = '') {
        const row = document.createElement('div');
        row.className = 'grid md:grid-cols-5 gap-2 items-start saved-answer';
        row.innerHTML = `
            <input class="input md:col-span-2 text-sm" placeholder="Question, e.g. Why do you want to work here?" value="${escapeHtml(question)}">
            <textarea class="input md:col-span-3 text-sm" rows="2" placeholder="Your answer">${escapeHtml(answer)}</textarea>
            <button type="button" class="text-xs text-red-600 hover:underline md:col-span-5 justify-self-end">Remove</button>`;
        row.querySelector('button').addEventListener('click', () => row.remove());
        savedAnswers.appendChild(row);
    }

    function fillProfileForm(profile) {
        for (const [key, value] of Object.entries(profile)) {
            const el = profileForm.elements[key];
            if (!el || key === 'custom_answers') continue;
            if (el.type === 'checkbox') el.checked = !!value;
            else if (el.tagName === 'SELECT' && value && ![...el.options].some(o => o.value === value)) {
                el.insertAdjacentHTML('beforeend', `<option>${escapeHtml(value)}</option>`);
                el.value = value;
            } else el.value = value ?? '';
        }
        savedAnswers.innerHTML = '';
        (profile.custom_answers || []).forEach(a => addAnswerRow(a.question, a.answer));
    }

    function readProfileForm() {
        const profile = {};
        [...profileForm.elements].forEach(el => {
            if (!el.name) return;
            profile[el.name] = el.type === 'checkbox' ? el.checked : el.value.trim();
        });
        profile.custom_answers = [...savedAnswers.querySelectorAll('.saved-answer')].map(row => ({
            question: row.querySelector('input').value.trim(),
            answer: row.querySelector('textarea').value.trim(),
        })).filter(a => a.question && a.answer);
        return profile;
    }

    function showProfileStatus(missing) {
        missingFields = missing || [];
        profileStatus.className = `badge ${missingFields.length ? 'badge-red' : 'badge-green'}`;
        profileStatus.textContent = missingFields.length
            ? `Missing: ${missingFields.map(m => m.replace(/_/g, ' ')).join(', ')}`
            : 'Complete';
    }

    async function loadProfile() {
        const { ok, data } = await api('/api/profile');
        if (!ok) return;
        fillProfileForm(data.profile);
        showProfileStatus(data.missing);
    }

    profileForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const button = $('saveProfileBtn');
        setLoading(button, true, 'Saving...');
        try {
            const { ok, data } = await api('/api/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile: readProfileForm() }),
            });
            if (!ok) { toast(data.error || 'Could not save the profile.', 'error'); return; }
            fillProfileForm(data.profile);
            showProfileStatus(data.missing);
            toast(data.missing.length ? 'Profile saved. Some required details are still missing.' : 'Profile saved.', data.missing.length ? 'info' : 'success');
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setLoading(button, false);
        }
    });

    $('addAnswerBtn').addEventListener('click', () => addAnswerRow());

    $('profileFromCvBtn').addEventListener('click', async () => {
        const cv = window.CVTailor.getTailoredCv();
        const jobWithCv = window.CVTailor.jobs().find(j => j.cv_filename);
        if (!cv && !jobWithCv) { toast('Tailor a CV first, then try again.', 'error'); return; }
        const { ok, data } = await api('/api/profile/from-cv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cv ? { cv_json: cv } : { job_id: jobWithCv.id }),
        });
        if (!ok) { toast(data.error || 'Could not read the CV.', 'error'); return; }
        let filled = 0;
        for (const [key, value] of Object.entries(data.suggestions || {})) {
            const el = profileForm.elements[key];
            if (el && !el.value.trim()) { el.value = value; filled++; }
        }
        toast(filled ? `Filled ${filled} blank field(s) from your CV. Check them and press Save.` : 'Nothing new to fill from the CV.', 'info');
    });

    // --- Settings ---
    try { autoSubmitToggle.checked = JSON.parse(localStorage.getItem('cvtailor.autoSubmit') || 'false'); } catch { /* storage unavailable */ }
    const updateAutoSubmitWarning = () => $('autoSubmitWarning').classList.toggle('hidden', !autoSubmitToggle.checked);
    updateAutoSubmitWarning();
    autoSubmitToggle.addEventListener('change', () => {
        try { localStorage.setItem('cvtailor.autoSubmit', JSON.stringify(autoSubmitToggle.checked)); } catch { /* ignore */ }
        updateAutoSubmitWarning();
    });

    $('openBrowserBtn').addEventListener('click', async () => {
        const { ok, data } = await api('/api/autoapply/browser', { method: 'POST' });
        toast(ok ? 'A Chrome window is opening. Sign in to any job sites you use; it will remember you.' : (data.error || 'Could not open the browser.'), ok ? 'info' : 'error', 7000);
        schedulePoll(1000);
    });

    // --- Applying ---
    async function applyToJobs(jobIds, button) {
        if (missingFields.length) {
            profilePanel.open = true;
            profilePanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            toast('Complete your applicant profile first (marked with *), then save it.', 'error', 7000);
            return;
        }
        const body = { model: window.CVTailor.selectedModel(), auto_submit: autoSubmitToggle.checked };
        const single = jobIds.length === 1;
        if (button) setLoading(button, true, 'Queuing...');
        try {
            const { ok, data } = await api(single ? '/api/apply' : '/api/apply/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(single ? { ...body, job_id: jobIds[0] } : { ...body, job_ids: jobIds }),
            });
            if (!ok) {
                toast(data.error || 'Could not start auto-apply.', 'error', 8000);
                if (/profile/i.test(data.error || '')) { profilePanel.open = true; profilePanel.scrollIntoView({ behavior: 'smooth' }); }
                return;
            }
            if (single) {
                toast('Auto-apply started. A Chrome window will open the application.', 'success');
                openIds.add(data.application.id);
            } else {
                const queued = data.results.filter(r => r.status === 'queued');
                const skipped = data.results.filter(r => r.status !== 'queued');
                toast(`Queued ${queued.length} application(s).${skipped.length ? ` Skipped ${skipped.length}: ${skipped[0].message}` : ''}`,
                      skipped.length ? 'info' : 'success', 7000);
            }
            $('auto-apply').scrollIntoView({ behavior: 'smooth', block: 'start' });
            await refreshApplications();
            window.CVTailor.refreshJobs();
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            if (button) setLoading(button, false);
        }
    }

    // --- Applications list ---
    const STATUS = {
        queued: ['badge-blue', 'Queued', true],
        running: ['badge-blue', 'Filling form', true],
        needs_attention: ['badge-yellow', 'Needs you', true],
        ready_for_review: ['badge-purple', 'Ready for your review', false],
        submitted: ['badge-green', 'Submitted', false],
        failed: ['badge-red', 'Failed', false],
        cancelled: ['', 'Cancelled', false],
    };
    const ACTIONS = {
        queued: [['cancel', 'Cancel', 'btn-gray']],
        running: [['cancel', 'Cancel', 'btn-gray']],
        needs_attention: [['continue', 'Continue', 'btn-blue'], ['mark_submitted', 'I submitted it', 'btn-green'], ['cancel', 'Cancel', 'btn-gray']],
        ready_for_review: [['submit', 'Submit now', 'btn-purple'], ['mark_submitted', 'I submitted it', 'btn-green'], ['cancel', 'Discard', 'btn-gray']],
        failed: [['retry', 'Retry', 'btn-blue'], ['mark_submitted', 'I applied manually', 'btn-gray']],
        cancelled: [['retry', 'Retry', 'btn-blue']],
        submitted: [],
    };
    const openIds = new Set();
    const lastSeen = new Map(); // id -> "status|updated_at"
    let pollTimer = null;

    function timeAgo(value) {
        const d = new Date(String(value).replace(' ', 'T'));
        if (isNaN(d)) return '';
        const s = Math.round((Date.now() - d) / 1000);
        if (s < 60) return 'just now';
        if (s < 3600) return `${Math.floor(s / 60)} min ago`;
        if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
        return d.toLocaleDateString();
    }

    function summaryHtml(app) {
        const [cls, label, live] = STATUS[app.status] || ['', app.status, false];
        const title = app.job_title ? `${escapeHtml(app.job_title)}${app.job_company ? ' &middot; ' + escapeHtml(app.job_company) : ''}` : escapeHtml(app.url);
        const actions = (ACTIONS[app.status] || []).map(([action, text, btn]) =>
            `<button type="button" class="btn ${btn} btn-xs" data-app-action="${action}" data-app-id="${app.id}">${text}</button>`).join('');
        return `
            <summary class="px-4 py-3 cursor-pointer">
                <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                    <div class="min-w-0">
                        <div class="flex items-center gap-2">
                            ${live ? '<span class="dot live"></span>' : ''}
                            <span class="badge ${cls}">${label}</span>
                            <span class="font-semibold truncate">${title}</span>
                            ${app.auto_submit ? '<span class="badge" title="Submits automatically when the form is complete">auto-submit</span>' : ''}
                        </div>
                        <p class="text-sm text-gray-700 mt-1">${escapeHtml(app.message || '')}</p>
                        <p class="text-xs text-gray-500">#${app.id} &middot; updated ${escapeHtml(timeAgo(app.updated_at))}</p>
                    </div>
                    <div class="flex flex-wrap gap-1 flex-shrink-0">${actions}</div>
                </div>
            </summary>
            <div class="app-body px-4 pb-4"></div>`;
    }

    function bodyHtml(app) {
        const fields = app.fields || [];
        const rows = fields.map(f => {
            const problem = ['missing', 'error'].includes(f.status);
            const cls = problem ? 'problem' : (f.confidence === 'low' ? 'low' : '');
            const statusText = { filled: 'filled', kept: 'already filled', skipped: 'left blank', missing: 'needs you', error: 'failed' }[f.status] || f.status;
            return `<tr class="${cls}">
                <td>${escapeHtml((f.label || '(unlabelled)').replace(/\s*\*\s*$/, ''))}${f.required ? ' <span class="text-red-600">*</span>' : ''}</td>
                <td class="whitespace-pre-wrap">${escapeHtml(f.value || '')}${f.detail ? `<div class="text-red-600">${escapeHtml(f.detail)}</div>` : ''}</td>
                <td>${escapeHtml(f.source || '')}${f.confidence === 'low' ? ' <span class="badge badge-yellow">check</span>' : ''}</td>
                <td>${escapeHtml(statusText)}</td></tr>`;
        }).join('');
        const log = (app.log || []).map(l => `<div class="${l.level === 'warning' ? 'warning' : ''}">${escapeHtml(l.t)} ${escapeHtml(l.msg)}</div>`).join('');
        return `
            <div class="grid lg:grid-cols-3 gap-4">
                <div class="lg:col-span-2">
                    <h5 class="text-sm font-semibold mb-1">What was filled</h5>
                    ${rows ? `<div class="overflow-x-auto"><table class="fields-table">
                        <thead><tr><th>Question</th><th>Answer</th><th>Source</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>
                        <p class="text-xs text-gray-500 mt-1">Yellow rows are AI answers worth double-checking; red rows need your input.</p>`
                      : '<p class="text-sm text-gray-500">No fields filled yet.</p>'}
                </div>
                <div>
                    <h5 class="text-sm font-semibold mb-1">Activity</h5>
                    <div class="app-log">${log || 'Waiting...'}</div>
                    ${app.screenshot ? `<a href="/api/applications/${app.id}/screenshot?v=${encodeURIComponent(app.updated_at)}" target="_blank" rel="noopener">
                        <img src="/api/applications/${app.id}/screenshot?v=${encodeURIComponent(app.updated_at)}" alt="Latest screenshot of the form" class="mt-2 rounded border max-h-64 w-full object-cover object-top"></a>` : ''}
                    <p class="text-xs text-gray-500 mt-2 break-all">URL: <a class="text-blue-600 hover:underline" href="${escapeHtml(app.url)}" target="_blank" rel="noopener">${escapeHtml(app.url)}</a></p>
                </div>
            </div>`;
    }

    async function loadBody(el, appId) {
        const { ok, data } = await api(`/api/applications/${appId}`);
        if (!ok) return;
        const body = el.querySelector('.app-body');
        const log = body.querySelector('.app-log');
        const stickToBottom = !log || log.scrollTop + log.clientHeight >= log.scrollHeight - 10;
        body.innerHTML = bodyHtml(data.application);
        const newLog = body.querySelector('.app-log');
        if (newLog && stickToBottom) newLog.scrollTop = newLog.scrollHeight;
    }

    async function refreshApplications() {
        let result;
        try { result = await api('/api/applications'); } catch { return false; }
        if (!result.ok) return false;
        const { applications, worker } = result.data;

        $('workerStatus').textContent = worker.browser_open ? 'Browser open' : '';
        $('applicationsCount').textContent = applications.length ? `${applications.length} recent` : '';
        if (!applications.length) {
            applicationsList.innerHTML = '<p class="text-sm text-gray-500">No applications yet. Use "Auto apply" on a job that has a tailored CV.</p>';
            return false;
        }
        if (!applicationsList.querySelector('.application')) applicationsList.innerHTML = '';

        let jobsChanged = false;
        const keep = new Set();
        applications.forEach((app, index) => {
            keep.add(String(app.id));
            const signature = `${app.status}|${app.updated_at}`;
            let el = $(`application-${app.id}`);
            if (!el) {
                el = document.createElement('details');
                el.id = `application-${app.id}`;
                el.addEventListener('toggle', () => {
                    if (el.open) { openIds.add(app.id); loadBody(el, app.id); } else openIds.delete(app.id);
                });
            }
            if (applicationsList.children[index] !== el) applicationsList.insertBefore(el, applicationsList.children[index] || null);
            if (lastSeen.get(app.id) !== signature) {
                const previous = lastSeen.get(app.id);
                if (previous && previous.split('|')[0] !== app.status) {
                    jobsChanged = true;
                    if (app.status === 'needs_attention') toast(`Auto-apply needs you: ${app.message}`, 'info', 9000);
                    if (app.status === 'ready_for_review') toast(`Ready for your review: ${app.job_title || 'application'}`, 'success');
                    if (app.status === 'submitted') toast(`Application submitted: ${app.job_title || ''}`, 'success');
                    if (app.status === 'failed') toast(`Auto-apply failed: ${app.message}`, 'error', 8000);
                }
                lastSeen.set(app.id, signature);
                const wasOpen = el.open || openIds.has(app.id);
                el.className = `application ${app.status === 'needs_attention' ? 'is-attention' : ''} ${app.status === 'ready_for_review' ? 'is-review' : ''}`;
                el.innerHTML = summaryHtml(app);
                el.open = wasOpen;
                if (wasOpen) loadBody(el, app.id);
            }
        });
        [...applicationsList.querySelectorAll('.application')].forEach(el => {
            if (!keep.has(el.id.replace('application-', ''))) el.remove();
        });
        if (jobsChanged) window.CVTailor.refreshJobs();
        return applications.some(a => STATUS[a.status] && STATUS[a.status][2]) || worker.awaiting_review.length > 0;
    }

    function schedulePoll(delay) {
        clearTimeout(pollTimer);
        pollTimer = setTimeout(async () => {
            const active = await refreshApplications();
            schedulePoll(active ? 2000 : 15000);
        }, delay);
    }

    applicationsList.addEventListener('click', async (e) => {
        const button = e.target.closest('[data-app-action]');
        if (!button) return;
        e.preventDefault(); // don't toggle the <details>
        const { appAction: action, appId } = button.dataset;
        if (action === 'cancel' && !confirm('Stop this application? The browser tab will be closed.')) return;
        button.disabled = true;
        const { ok, data } = await api(`/api/applications/${appId}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
        }).catch(err => ({ ok: false, data: { error: err.message } }));
        if (!ok) {
            toast(data.error || 'That action failed.', 'error');
            button.disabled = false;
            return;
        }
        if (action === 'retry') openIds.add(data.application.id);
        toast({ continue: 'Continuing...', submit: 'Submitting...', mark_submitted: 'Marked as submitted.', cancel: 'Cancelling...', retry: 'Queued again.' }[action], 'info', 2500);
        schedulePoll(300);
    });

    function showApplication(appId) {
        const el = $(`application-${appId}`);
        if (!el) { $('auto-apply').scrollIntoView({ behavior: 'smooth' }); return; }
        el.open = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    window.AutoApply = { applyToJobs, showApplication };

    loadProfile();
    refreshApplications().then(active => schedulePoll(active ? 2000 : 15000));
});
