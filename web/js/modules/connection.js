/**
 * Connection panel for the standalone demo (ADR 0013).
 *
 * The service answers against one fixed Datasource (ADR 0011) — except in demo
 * mode, where the page is served by the same process it talks to and can point
 * that process at another database without a restart. The routes this module
 * calls exist only while the demo UI is mounted; when they are missing the panel
 * removes itself, so a deployment without them never shows a dead form.
 */

import { connectDemoDatabase, fetchDemoState } from './api.js';
import { appendMessage, fetchSchema, renderDatasourceStatus, switchTab } from './ui.js';
import { formatError, sanitize } from './utils.js';
import { getCurrentTab, resetSession } from './state.js';
import { refreshProfileEntry } from './wizard.js';

// SQLAlchemy's DSN carries the driver; these are the ones the project ships.
const DRIVERS = { postgresql: 'psycopg2', mysql: 'pymysql' };
const DEFAULT_PORTS = { postgresql: '5432', mysql: '3306' };

let typeSelect = null;
let statusBadge = null;
let connectButton = null;
let profileSelect = null;
let dsnPreview = null;

/**
 * Wire the panel, then show the Datasource the demo is running against.
 */
export async function initConnectionPanel() {
    typeSelect = document.getElementById('db-type');
    statusBadge = document.getElementById('connection-status');
    connectButton = document.getElementById('connect-btn');
    profileSelect = document.getElementById('profile-select');
    dsnPreview = document.getElementById('dsn-preview');
    if (!typeSelect) return;

    typeSelect.addEventListener('change', () => {
        renderTypeFields();
        updateDsnPreview();
    });
    document.querySelectorAll('#tab-connection input').forEach((input) => {
        input.addEventListener('input', updateDsnPreview);
    });

    try {
        renderState(await fetchDemoState());
    } catch (e) {
        // No /api/demo/* here: the UI is a plain static mount.
        removePanel();
    }
}

/**
 * Build the DSN the server will open, from the form.
 * @param {{hidePassword?: boolean}} [options] - Mask the password (for display)
 * @returns {string} SQLAlchemy DSN
 */
function buildDatabaseUrl({ hidePassword = false } = {}) {
    const type = typeSelect.value;

    if (type === 'sqlite') {
        const file = document.getElementById('db-path').value.trim();
        return `sqlite:///${file}`;
    }

    const user = document.getElementById('db-user').value.trim();
    const password = document.getElementById('db-pass').value;
    const host = document.getElementById('db-host').value.trim() || 'localhost';
    const port = document.getElementById('db-port').value.trim();
    const database = document.getElementById('db-name').value.trim();

    // encodeURIComponent keeps '@', ':' and '/' inside credentials from being
    // read as DSN separators.
    const credentials = user
        ? `${encodeURIComponent(user)}${password ? `:${hidePassword ? '***' : encodeURIComponent(password)}` : ''}@`
        : '';
    const authority = `${host}${port ? `:${port}` : ''}`;
    return `${type}+${DRIVERS[type]}://${credentials}${authority}/${database}`;
}

/** Show the SQLite or the host/port fields for the selected type. */
function renderTypeFields() {
    const isSqlite = typeSelect.value === 'sqlite';
    document.getElementById('sqlite-config').style.display = isSqlite ? 'flex' : 'none';
    document.getElementById('sql-config').style.display = isSqlite ? 'none' : 'flex';

    // Follow the dialect's default port unless the user typed their own.
    const portInput = document.getElementById('db-port');
    if (!portInput.value || Object.values(DEFAULT_PORTS).includes(portInput.value)) {
        portInput.value = DEFAULT_PORTS[typeSelect.value] || '';
    }
}

/** Keep the DSN preview in step with the form (password masked). */
function updateDsnPreview() {
    if (dsnPreview) {
        dsnPreview.textContent = `Connection URL: ${buildDatabaseUrl({ hidePassword: true })}`;
    }
}

/** Fill the profile select and the status badge from /api/demo/state. */
function renderState(state) {
    profileSelect.innerHTML = state.profiles
        .map((name) => `<option value="${sanitize(name)}">${sanitize(name)}</option>`)
        .join('');
    profileSelect.value = state.profile;
    setStatus(
        state.datasource ? `🟢 ต่ออยู่: ${state.datasource}` : '🔴 ยังไม่ได้ตั้ง Datasource',
        Boolean(state.datasource),
    );
    updateDsnPreview();
    refreshProfileEntry(state);
}

/** @param {boolean} ok - success (green) or failure (red) styling */
function setStatus(text, ok) {
    if (!statusBadge) return;
    statusBadge.textContent = text;
    statusBadge.className = `status-badge ${ok ? 'connected' : 'disconnected'}`;
}

function setBusy(busy) {
    if (!connectButton) return;
    connectButton.disabled = busy;
    connectButton.textContent = busy ? 'Connecting…' : 'Connect Database';
}

/**
 * Connect the demo to the form's Datasource and refresh everything that
 * depended on the old one.
 */
export async function connectFromForm() {
    setBusy(true);
    setStatus('⏳ กำลังเชื่อมต่อ…', false);
    try {
        const result = await connectDemoDatabase(buildDatabaseUrl(), profileSelect.value);

        setStatus(`🟢 ต่ออยู่: ${result.datasource}`, true);
        appendMessage(
            `✅ เชื่อมต่อสำเร็จ: <code>${sanitize(result.datasource)}</code> — พบ ${result.tables.length} ตาราง` +
            '<br>เริ่มบทสนทนาใหม่แล้ว เพราะ schema เปลี่ยน',
            false,
        );

        // Prior Turns describe the previous Datasource; replaying them against
        // the new schema would mislead the agent.
        resetSession();
        const resetButton = document.getElementById('reset-session-btn');
        if (resetButton) resetButton.style.display = 'none';

        await renderDatasourceStatus();
        fetchSchema();
        refreshProfileEntry();
    } catch (e) {
        setStatus('🔴 เชื่อมต่อไม่สำเร็จ', false);
        appendMessage(
            formatError('เชื่อมต่อฐานข้อมูลไม่สำเร็จ กรุณาตรวจสอบ Connection URL, ผู้ใช้ และรหัสผ่านอีกครั้ง', e),
            false,
        );
    } finally {
        setBusy(false);
    }
}

/** Remove the tab where the demo routes are not served (auto/service). */
function removePanel() {
    document.getElementById('tab-btn-connection')?.remove();
    document.getElementById('tab-connection')?.remove();
    // The wizard lives in the demo routes too; leave no dead entry point behind.
    document.getElementById('profile-wizard-modal')?.remove();
    if (getCurrentTab() === 'connection') switchTab('schema');
}
