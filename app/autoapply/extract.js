// app/autoapply/extract.js
// Runs inside a page/frame. Tags every fillable control and button with a data-aa-* id and
// returns a description of them plus page-level signals (CAPTCHA, login wall, confirmation).
(prefix) => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').replace(/\s*\*\s*$/, ' *').trim();
    const textOf = (el) => (el ? clean(el.innerText || el.textContent || '') : '');

    const isShown = (el) => {
        if (!el || !el.getClientRects) return false;
        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') return false;
        return el.getClientRects().length > 0;
    };
    // Custom-styled radios, checkboxes and file inputs are often hidden behind a visible label/button.
    const isUsable = (el) => {
        if (isShown(el)) return true;
        if (['radio', 'checkbox', 'file'].includes(el.type)) {
            if (el.labels && [...el.labels].some(isShown)) return true;
            const parent = el.closest('label, [class*="upload"], [class*="file"], [class*="dropzone"], .field, div');
            return parent ? isShown(parent) : false;
        }
        return false;
    };

    const SEARCH_RE = /\bsearch\b|keyword/i;
    const isSearchBox = (el) => el.type === 'search' || el.getAttribute('role') === 'searchbox' ||
        SEARCH_RE.test(el.name || '') || SEARCH_RE.test(el.placeholder || '') || SEARCH_RE.test(el.getAttribute('aria-label') || '');

    const labelledBy = (el) => {
        const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
        return clean(ids.map(id => textOf(document.getElementById(id))).join(' '));
    };

    // Text of a <label> without the text of the control(s) it wraps.
    const labelText = (label) => {
        const copy = label.cloneNode(true);
        copy.querySelectorAll('input, select, textarea, button, [role="listbox"]').forEach(n => n.remove());
        return textOf(copy);
    };

    // Nearest heading-like text before the control inside its field container.
    const nearbyText = (el) => {
        let node = el;
        for (let depth = 0; depth < 4 && node && node !== document.body; depth++) {
            let sib = node.previousElementSibling;
            while (sib) {
                const t = textOf(sib);
                if (t && t.length < 300 && !sib.querySelector('input, select, textarea')) return t;
                sib = sib.previousElementSibling;
            }
            node = node.parentElement;
        }
        return '';
    };

    const labelFor = (el) => {
        const viaAria = labelledBy(el);
        if (viaAria) return viaAria;
        if (el.labels && el.labels.length) {
            const t = clean([...el.labels].map(labelText).join(' '));
            if (t) return t;
        }
        return clean(el.getAttribute('aria-label') || '') || nearbyText(el) ||
            clean(el.placeholder || '') || clean(el.title || '') || clean(el.name || '');
    };

    const groupLabel = (inputs) => {
        const first = inputs[0];
        const fieldset = first.closest('fieldset');
        if (fieldset) {
            const legend = fieldset.querySelector('legend');
            if (legend && textOf(legend)) return textOf(legend);
        }
        const group = first.closest('[role="radiogroup"], [role="group"]');
        if (group) {
            const t = labelledBy(group) || clean(group.getAttribute('aria-label') || '');
            if (t) return t;
        }
        // Smallest ancestor holding the whole group: use its text minus the option labels.
        let container = first.parentElement;
        while (container && !inputs.every(i => container.contains(i))) container = container.parentElement;
        for (let depth = 0; container && depth < 3; depth++, container = container.parentElement) {
            const optionTexts = new Set(inputs.map(optionLabel));
            const lines = (container.innerText || '').split('\n').map(clean).filter(l => l && !optionTexts.has(l));
            if (lines.length) return lines[0];
        }
        return clean(first.name || '');
    };

    const optionLabel = (input) => {
        if (input.labels && input.labels.length) return labelText(input.labels[0]);
        return clean(input.getAttribute('aria-label') || input.value || '');
    };

    const isRequired = (el, label) => el.required || el.getAttribute('aria-required') === 'true' ||
        /\*\s*$/.test(label) || /\(required\)/i.test(label);

    // The counter lives on the window so elements that appear later (next form page) get fresh ids.
    const tag = (el, attr) => {
        let id = el.getAttribute(attr);
        if (!id) {
            window.__aaCounter = (window.__aaCounter || 0) + 1;
            id = `${prefix}${{ 'data-aa-id': 'f', 'data-aa-group': 'g', 'data-aa-btn': 'b' }[attr]}${window.__aaCounter}`;
            el.setAttribute(attr, id);
        }
        return id;
    };

    const fields = [];
    const seenGroups = new Set();
    const controls = document.querySelectorAll('input, select, textarea, [role="combobox"]:not(input)');

    for (const el of controls) {
        const type = (el.type || '').toLowerCase();
        if (['hidden', 'submit', 'button', 'reset', 'image', 'password'].includes(type)) continue;
        if (el.disabled || el.readOnly && type !== 'file') continue;
        if (el.closest('[aria-hidden="true"]') && type !== 'file') continue;
        if ((el.name || '').startsWith('g-recaptcha') || (el.name || '').includes('captcha')) continue;
        if (isSearchBox(el) || !isUsable(el)) continue;

        if (type === 'radio' || (type === 'checkbox' && el.name)) {
            const scope = el.form || document;
            const group = [...scope.querySelectorAll(`input[type="${type}"]`)].filter(i => i.name === el.name && isUsable(i));
            if (type === 'radio' || group.length > 1) {
                if (seenGroups.has(type + el.name)) continue;
                seenGroups.add(type + el.name);
                const label = groupLabel(group);
                group.forEach(i => tag(i, 'data-aa-id'));
                fields.push({
                    id: tag(el, 'data-aa-group'),
                    kind: type === 'radio' ? 'radio' : 'checkbox_group',
                    label,
                    required: group.some(i => i.required) || isRequired(el, label),
                    options: group.map(i => ({ id: i.getAttribute('data-aa-id'), label: optionLabel(i), value: i.value })),
                    value: group.filter(i => i.checked).map(optionLabel),
                });
                continue;
            }
        }

        const label = labelFor(el);
        const field = { id: tag(el, 'data-aa-id'), label, required: isRequired(el, label), name: el.name || '' };

        if (el.tagName === 'SELECT') {
            field.kind = el.multiple ? 'multiselect' : 'select';
            field.options = [...el.options]
                .filter(o => !o.disabled && !(o.value === '' && /select|choose|--|please/i.test(o.text)))
                .map(o => ({ value: o.value, label: clean(o.text) }));
            field.value = el.selectedIndex >= 0 && el.value !== '' ? clean(el.options[el.selectedIndex].text) : '';
        } else if (type === 'checkbox') {
            field.kind = 'checkbox';
            field.value = el.checked;
        } else if (type === 'file') {
            field.kind = 'file';
            field.accept = el.accept || '';
            field.value = el.files && el.files.length ? el.files[0].name : '';
        } else if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list' ||
                   /select__input|autocomplete/i.test(el.className || '')) {
            field.kind = 'combobox';
            field.value = clean(el.value || '');
            // react-select style widgets show the chosen value in a sibling element.
            const container = el.closest('[class*="select__control"], [class*="container"]');
            const chosen = container && container.querySelector('[class*="single-value"], [class*="singleValue"]');
            if (chosen) field.value = textOf(chosen);
        } else if (el.tagName === 'TEXTAREA') {
            field.kind = 'textarea';
            field.value = el.value || '';
        } else {
            field.kind = ['email', 'tel', 'url', 'number', 'date'].includes(type) ? type : 'text';
            field.value = el.value || '';
            if (el.maxLength > 0) field.maxlength = el.maxLength;
        }
        if (el.placeholder) field.placeholder = clean(el.placeholder);
        fields.push(field);
    }

    const buttons = [];
    const buttonEls = document.querySelectorAll('button, input[type="submit"], input[type="button"], a, [role="button"]');
    for (const el of buttonEls) {
        if (buttons.length >= 120) break;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true' || !isShown(el)) continue;
        const text = clean(el.innerText || el.value || el.getAttribute('aria-label') || el.title || '');
        if (!text || text.length > 80) continue;
        buttons.push({ id: tag(el, 'data-aa-btn'), text, tag: el.tagName.toLowerCase(), type: el.type || '', href: el.getAttribute('href') || '' });
    }

    const bodyText = (document.body && document.body.innerText || '').slice(0, 20000);
    const captchaFrames = [...document.querySelectorAll('iframe')].filter(f =>
        /recaptcha|hcaptcha|turnstile|challenges\.cloudflare|arkoselabs|funcaptcha/i.test(f.src || '') && isShown(f));
    const errors = [...document.querySelectorAll('[aria-invalid="true"], [role="alert"], .error, .field-error, [class*="error-message"], [class*="errorMessage"]')]
        .filter(isShown).map(textOf).filter(t => t && t.length < 200).slice(0, 15);
    const invalidIds = [...document.querySelectorAll('[aria-invalid="true"][data-aa-id]')].map(e => e.getAttribute('data-aa-id'));

    return {
        url: location.href,
        title: document.title,
        fields,
        buttons,
        signals: {
            password: [...document.querySelectorAll('input[type="password"]')].some(isShown),
            captcha: captchaFrames.length > 0 || /verify (that )?you are (a )?human|are you a robot|complete the security check/i.test(bodyText.slice(0, 3000)),
            confirmation: /thank you for (applying|your application|submitting)|application (has been |was )?(submitted|received|sent)|we('ve| have) received your application|successfully applied|you('ve| have) applied/i.test(bodyText),
            errors,
            invalidIds,
        },
        text: bodyText.slice(0, 4000),
    };
}
