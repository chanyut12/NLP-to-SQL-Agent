/**
 * Profile wizard (demo only, ADR 0014).
 *
 * Four screens turn the connected Datasource into an ordinary
 * `profiles/<name>/` profile: name, Thai terms, example questions with drafted
 * SQL and live rows, and business rules. The endpoints called here exist only
 * while the demo UI is mounted; when they are missing the connection panel
 * removes itself and this module has no entry point left.
 */

import {
    connectDemoDatabase, draftProfileExample, fetchDemoState, saveDemoProfile,
} from './api.js';
import { appendMessage } from './ui.js';
import { sanitize } from './utils.js';

const NAME_RE = /^[a-z0-9_-]{1,64}$/;
const NUDGE_KEY = 'profileNudgeDismissedFor';
const SAMPLE_DB = 'local_database.db';

let demoState = null;
let step = 1;
let lastDraft = null;       // { ok, question, sql, rows, row_count, category }
let pendingOverwrite = false;
let saved = null;           // { profile, coverage }
let drafting = false;

const draft = {
    name: '',
    mappings: [],           // { term, fragments: string[] }
    examples: [],           // { question, sql }
    rules: '',
    ambiguities: '',
};

/**
 * Wire the wizard's delegated actions and show/hide its entry points.
 * Called once from main.js after the connection panel is initialised.
 */
export function initProfileWizard() {
    document.addEventListener('click', handleWizardClick);
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if (getModal()?.style.display === 'flex') closeProfileWizard();
    });
    refreshProfileEntry();
}

/**
 * Show the create-profile button when a Datasource is connected, and the
 * first-run nudge when that Datasource has no profile of its own yet.
 * @param {Object|null} state - /api/demo/state result, when the caller has it
 */
export async function refreshProfileEntry(state = null) {
    if (state) demoState = state;
    else {
        try {
            demoState = await fetchDemoState();
        } catch {
            return;  // no demo routes: the connection panel removes itself
        }
    }

    const button = document.getElementById('open-wizard-btn');
    if (!button) return;
    button.hidden = !demoState.datasource;

    const nudge = document.getElementById('profile-nudge');
    if (nudge) nudge.hidden = !shouldNudge();
}

/**
 * The nudge appears when the demo answers from the bundled sample profile
 * while pointed at some other database — i.e. the connected Datasource has no
 * profile describing it. A deliberately chosen profile (sts, or one the user
 * created) is treated as a match.
 */
function shouldNudge() {
    if (!demoState || !demoState.datasource) return false;
    if (demoState.profile !== 'demo') return false;
    if (demoState.datasource.includes(SAMPLE_DB)) return false;
    return localStorage.getItem(NUDGE_KEY) !== demoState.datasource;
}

/* ---------- actions ---------- */

const ACTIONS = {
    openProfileWizard,
    closeProfileWizard,
    dismissProfileNudge,
    addWizardMapping: () => addMapping(),
    removeWizardMapping: (target) => removeMapping(Number(target.dataset.index)),
    draftWizardExample: () => draftExample(),
    retryWizardSql: () => draftExample(value('wizard-sql')),
    acceptWizardExample: () => acceptExample(),
    skipWizardExample: () => skipExample(),
    removeWizardExample: (target) => removeExample(Number(target.dataset.index)),
    wizardBack: () => setStep(step - 1),
    wizardNext: () => nextStep(),
    saveWizardProfile: () => saveProfile(false),
    overwriteWizardProfile: () => saveProfile(true),
    switchWizardProfile: () => switchToSavedProfile(),
};

function handleWizardClick(e) {
    const target = e.target.closest('[data-action]');
    if (!target) return;
    const handler = ACTIONS[target.dataset.action];
    if (!handler) return;
    e.preventDefault();
    handler(target);
}

function getModal() {
    return document.getElementById('profile-wizard-modal');
}

function openProfileWizard() {
    const modal = getModal();
    if (!modal) return;
    if (saved) resetWizard();
    renderMappings();
    renderExamples();
    modal.style.display = 'flex';
    document.getElementById('wizard-datasource').textContent = demoState?.datasource
        ? `ฐานข้อมูลที่ต่ออยู่: ${demoState.datasource}`
        : '';
    setStep(step);
    document.getElementById('wizard-name').focus();
}

function closeProfileWizard() {
    const modal = getModal();
    if (modal) modal.style.display = 'none';
    setError('');
}

function dismissProfileNudge() {
    if (demoState?.datasource) localStorage.setItem(NUDGE_KEY, demoState.datasource);
    const nudge = document.getElementById('profile-nudge');
    if (nudge) nudge.hidden = true;
}

/* ---------- steps ---------- */

function setStep(next) {
    captureStep(step);
    step = next;
    const numeric = Number.isInteger(step);

    document.querySelectorAll('#profile-wizard-modal .wizard-screen').forEach((screen) => {
        screen.classList.toggle('active', screen.dataset.screen === String(step));
    });
    document.querySelectorAll('#wizard-steps .wizard-step-dot').forEach((dot) => {
        dot.classList.toggle('active', dot.dataset.step === String(step));
    });

    if (step === 1 && draft.name) value('wizard-name', draft.name);
    if (step === 4) {
        value('wizard-rules', draft.rules);
        value('wizard-ambiguities', draft.ambiguities);
    }

    document.getElementById('wizard-back').hidden = !numeric || step === 1;
    document.getElementById('wizard-next').hidden = !numeric || step === 4;
    document.getElementById('wizard-save').hidden = step !== 4;
    document.getElementById('wizard-overwrite').hidden = !(step === 4 && pendingOverwrite);
    setError('');
}

function captureStep(current) {
    if (current === 1) draft.name = value('wizard-name').trim();
    if (current === 4) {
        draft.rules = value('wizard-rules');
        draft.ambiguities = value('wizard-ambiguities');
    }
}

function nextStep() {
    captureStep(step);
    if (step === 1 && !NAME_RE.test(draft.name)) {
        setError('ชื่อ profile ใช้ได้เฉพาะ a-z, 0-9, - และ _ (ไม่เกิน 64 ตัว)');
        return;
    }
    setStep(step + 1);
}

/* ---------- screen 2: Thai terms ---------- */

function addMapping() {
    const term = value('wizard-term').trim();
    const fragments = value('wizard-fragments')
        .split(',')
        .map((fragment) => fragment.trim())
        .filter(Boolean);

    if (!term || !fragments.length) {
        setError('ใส่คำศัพท์ไทยและชื่อตาราง/คอลัมน์อย่างน้อยหนึ่งชื่อ');
        return;
    }
    draft.mappings.push({ term, fragments });
    value('wizard-term', '');
    value('wizard-fragments', '');
    setError('');
    renderMappings();
    document.getElementById('wizard-term').focus();
}

function removeMapping(index) {
    draft.mappings.splice(index, 1);
    renderMappings();
}

function renderMappings() {
    const host = document.getElementById('wizard-mappings');
    if (!host) return;
    if (!draft.mappings.length) {
        host.innerHTML = '<p class="field-hint">ยังไม่มีคำศัพท์ — ข้ามขั้นนี้ได้</p>';
        return;
    }
    host.innerHTML = draft.mappings.map((mapping, index) => `
        <div class="wizard-item">
            <span><strong>${sanitize(mapping.term)}</strong> → ${sanitize(mapping.fragments.join(', '))}</span>
            <button type="button" class="link-btn" data-action="removeWizardMapping"
                data-index="${index}">ลบ</button>
        </div>
    `).join('');
}

/* ---------- screen 3: examples ---------- */

async function draftExample(sql = null) {
    if (drafting) return;
    const question = value('wizard-question').trim();
    if (!question) {
        setError('ใส่คำถามตัวอย่างก่อน');
        return;
    }

    drafting = true;
    setError('');
    setDraftStatus('⏳ กำลังร่าง SQL และรันกับฐานข้อมูล…');
    setAcceptEnabled(false);

    try {
        const result = await draftProfileExample(question, sql);
        if (result.status === 'ok') {
            lastDraft = {
                ok: true,
                question,
                sql: result.sql,
                rows: result.rows || [],
                row_count: result.row_count,
                category: result.category,
            };
            showDraft();
            setDraftStatus(
                `✅ รันได้ ${Number(result.row_count).toLocaleString('th-TH')} แถว`
                + (result.category ? ` · หมวด ${result.category}` : '')
            );
        } else {
            lastDraft = { ok: false, question, sql: result.sql || sql || '' };
            showDraft();
            setDraftStatus('❌ ร่างไม่สำเร็จ — แก้ SQL ด้านล่างแล้วลองรันใหม่ได้');
            setError(result.error || 'ร่าง SQL ไม่สำเร็จ');
        }
    } catch (e) {
        lastDraft = { ok: false, question, sql: sql || '' };
        showDraft();
        setDraftStatus('❌ ติดต่อ service ไม่ได้');
        setError(e.message);
    } finally {
        drafting = false;
    }
}

function showDraft() {
    document.getElementById('wizard-draft').hidden = false;
    value('wizard-sql', lastDraft.sql || '');
    const rows = document.getElementById('wizard-rows');
    if (lastDraft.ok) {
        rows.innerHTML = rowsTable(lastDraft.rows);
        setAcceptEnabled(true);
    } else {
        rows.innerHTML = '';
        setAcceptEnabled(false);
    }
}

function setAcceptEnabled(enabled) {
    const button = document.getElementById('wizard-accept');
    if (button) button.disabled = !enabled;
}

function acceptExample() {
    if (!lastDraft || !lastDraft.ok) return;
    const sql = value('wizard-sql').trim();
    if (!sql) {
        setError('SQL ว่าง — ร่างหรือแก้ก่อนยอมรับ');
        return;
    }
    if (sql !== lastDraft.sql.trim()) {
        setError('SQL ถูกแก้หลังจากรัน — กด "ลองรัน SQL ที่แก้" ก่อนยอมรับ');
        return;
    }
    draft.examples.push({ question: lastDraft.question, sql });
    clearDraft();
    renderExamples();
    setDraftStatus(`✅ เพิ่มแล้ว ${draft.examples.length} ตัวอย่าง — ตั้งคำถามถัดไปได้เลย`);
}

function skipExample() {
    clearDraft();
    setDraftStatus('');
    document.getElementById('wizard-question').focus();
}

function clearDraft() {
    lastDraft = null;
    document.getElementById('wizard-draft').hidden = true;
    value('wizard-question', '');
    value('wizard-sql', '');
    document.getElementById('wizard-rows').innerHTML = '';
    setError('');
}

function removeExample(index) {
    draft.examples.splice(index, 1);
    renderExamples();
}

function renderExamples() {
    const host = document.getElementById('wizard-examples');
    if (!host) return;
    if (!draft.examples.length) {
        host.innerHTML = '<p class="field-hint">ยังไม่มีตัวอย่างที่ยอมรับ — บันทึกโดยไม่มีตัวอย่างก็ได้</p>';
        return;
    }
    host.innerHTML = draft.examples.map((example, index) => `
        <div class="wizard-item">
            <span><strong>${sanitize(example.question)}</strong><br><code>${sanitize(example.sql)}</code></span>
            <button type="button" class="link-btn" data-action="removeWizardExample"
                data-index="${index}">ลบ</button>
        </div>
    `).join('');
}

function rowsTable(rows) {
    if (!rows || !rows.length) {
        return '<p class="field-hint" style="padding:8px">ไม่มีแถวข้อมูล</p>';
    }
    const columns = Object.keys(rows[0]);
    const head = columns.map((column) => `<th>${sanitize(column)}</th>`).join('');
    const body = rows.slice(0, 5).map((row) => (
        `<tr>${columns.map((column) => `<td>${sanitize(row[column] ?? '—')}</td>`).join('')}</tr>`
    )).join('');
    const note = rows.length > 5
        ? `<p class="field-hint" style="padding:6px 8px">แสดง 5 จาก ${rows.length} แถว</p>`
        : '';
    return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${note}`;
}

/* ---------- screen 4: save ---------- */

function buildHints() {
    const parts = [];
    if (draft.rules.trim()) parts.push(`## กฎทางธุรกิจ\n${draft.rules.trim()}`);
    if (draft.ambiguities.trim()) {
        parts.push(`## ความกำกวมที่ควรถามกลับ\n${draft.ambiguities.trim()}`);
    }
    return parts.join('\n\n');
}

function mappingObject() {
    const mappings = {};
    for (const mapping of draft.mappings) mappings[mapping.term] = mapping.fragments;
    return mappings;
}

async function saveProfile(overwrite = false) {
    captureStep(step);
    if (!NAME_RE.test(draft.name)) {
        setStep(1);
        setError('ชื่อ profile ใช้ได้เฉพาะ a-z, 0-9, - และ _ (ไม่เกิน 64 ตัว)');
        return;
    }

    setError('');
    setSaving(true);
    try {
        const result = await saveDemoProfile({
            name: draft.name,
            hints: buildHints(),
            schema_mappings: mappingObject(),
            examples: draft.examples.map(({ question, sql }) => ({ question, sql })),
            overwrite,
        });
        saved = result;
        pendingOverwrite = false;
        renderDone(result);
        setStep('done');

        // The new profile is selectable immediately: remember it for the panel.
        if (demoState) demoState.profiles = [...new Set([...(demoState.profiles || []), result.profile])];
        const select = document.getElementById('profile-select');
        if (select && ![...select.options].some((option) => option.value === result.profile)) {
            select.add(new Option(result.profile, result.profile));
        }
    } catch (e) {
        const conflict = /อยู่แล้ว/.test(e.message);
        pendingOverwrite = conflict;
        setError(conflict ? `${e.message} — กด "ยืนยันเขียนทับ" เพื่อแทนที่` : e.message);
        document.getElementById('wizard-overwrite').hidden = !conflict;
    } finally {
        setSaving(false);
    }
}

function setSaving(busy) {
    const button = document.getElementById('wizard-save');
    if (!button) return;
    button.disabled = busy;
    button.textContent = busy ? 'กำลังบันทึก…' : 'บันทึก Profile';
}

function renderDone(result) {
    const coverage = result.coverage || {};
    document.getElementById('wizard-result').innerHTML = `
        <h4>✅ บันทึก profile “${sanitize(result.profile)}” แล้ว</h4>
        <ul class="wizard-coverage">
            <li>กฎทางธุรกิจ: ${coverage.hints ? 'มี' : '<span class="missing">ยังไม่มี</span>'}</li>
            <li>ตัวอย่างคำถาม: ${coverage.examples || 0}</li>
            <li>คำศัพท์ไทย: ${coverage.schema_mappings || 0}</li>
        </ul>
        <p class="field-hint">ไฟล์อยู่ที่ <code>profiles/${sanitize(result.profile)}/</code> — ตรวจและ commit
            ได้ตามปกติ (ไม่ถูก commit ให้อัตโนมัติ)</p>
        <div class="wizard-inline">
            <button type="button" class="primary-btn" data-action="switchWizardProfile">ใช้ profile นี้เลย</button>
            <span class="field-hint" id="wizard-switch-note"></span>
        </div>`;
}

async function switchToSavedProfile() {
    if (!saved) return;
    const note = document.getElementById('wizard-switch-note');
    if (note) note.textContent = '⏳ กำลังสลับ…';
    try {
        const result = await connectDemoDatabase(null, saved.profile);
        demoState = {
            ...(demoState || {}),
            datasource: result.datasource,
            profile: result.profile,
            profiles: [...new Set([...(demoState?.profiles || []), result.profile])],
        };

        const select = document.getElementById('profile-select');
        if (select) select.value = result.profile;
        const badge = document.getElementById('connection-status');
        if (badge) {
            badge.textContent = `🟢 ต่ออยู่: ${result.datasource} · profile ${result.profile}`;
            badge.className = 'status-badge connected';
        }
        if (note) note.textContent = `✅ กำลังใช้ ${result.profile} อยู่`;
        appendMessage(
            `🧭 ใช้ profile <strong>${sanitize(result.profile)}</strong> แล้ว — `
            + 'ถามคำถามกับฐานข้อมูลนี้ได้เลย (ไม่ต้อง restart)',
            false,
        );
        refreshProfileEntry(demoState);
    } catch (e) {
        if (note) note.textContent = '';
        setError(e.message);
    }
}

function resetWizard() {
    saved = null;
    pendingOverwrite = false;
    lastDraft = null;
    step = 1;
    Object.assign(draft, {
        name: '', mappings: [], examples: [], rules: '', ambiguities: '',
    });
    value('wizard-name', '');
    value('wizard-rules', '');
    value('wizard-ambiguities', '');
    value('wizard-term', '');
    value('wizard-fragments', '');
    value('wizard-question', '');
    value('wizard-sql', '');
    document.getElementById('wizard-draft').hidden = true;
    document.getElementById('wizard-rows').innerHTML = '';
    document.getElementById('wizard-result').innerHTML = '';
    setDraftStatus('');
    setError('');
    renderMappings();
    renderExamples();
}

/* ---------- small helpers ---------- */

function value(id, next = undefined) {
    const element = document.getElementById(id);
    if (!element) return '';
    if (next !== undefined) {
        element.value = next;
        return next;
    }
    return element.value;
}

function setError(message) {
    const element = document.getElementById('wizard-error');
    if (!element) return;
    element.textContent = message || '';
    element.hidden = !message;
}

function setDraftStatus(message) {
    const element = document.getElementById('wizard-draft-status');
    if (element) element.textContent = message || '';
}
