/**
 * Main entry point for Thai NLP-to-SQL Agent
 *
 * This file imports all modules and sets up the application.
 * Uses event delegation via data-action attributes instead of inline handlers.
 */

// Module imports
import { getCurrentTab, getSessionTurns, addSessionTurn, resetSession } from './modules/state.js';
import { sanitize, formatError } from './modules/utils.js';
import { sendQuery, saveFavorite, deleteFavoriteById } from './modules/api.js';
import {
    initUI, switchTab, appendMessage, appendLoading, removeLoading,
    fetchSchema, fetchHistory, fetchFavorites, renderDatasourceStatus
} from './modules/ui.js';
import {
    showFeedbackModal, closeFeedbackModal, submitFeedbackWithText, sendFeedback
} from './modules/feedback.js';
import { renderAnswer } from './modules/result.js';
import { refreshCharts } from './modules/chart.js';
import { initConnectionPanel, connectFromForm } from './modules/connection.js';

// DOM Elements
let userInput = null;
let sidebar = null;
let openSidebarBtn = null;
let sidebarBackdrop = null;
let themeIcon = null;

const MOBILE_QUERY = '(max-width: 767px)';
const isMobileViewport = () => window.matchMedia(MOBILE_QUERY).matches;

/**
 * Initialize application when DOM is ready
 */
function init() {
    // Cache DOM elements
    userInput = document.getElementById('user-input');
    sidebar = document.getElementById('sidebar');
    openSidebarBtn = document.getElementById('open-sidebar-btn');
    sidebarBackdrop = document.getElementById('sidebar-backdrop');
    themeIcon = document.getElementById('theme-icon');

    // Initialize UI module
    initUI();

    // Set up event listeners
    setupEventListeners();

    // Restore sidebar state from localStorage
    restoreSidebarState();

    // Sync theme toggle icon with the theme applied pre-paint (see index.html inline script)
    restoreThemeState();

    // Show datasource status, load the schema, and wire the demo's
    // connection panel (which hides itself when its routes are absent).
    renderDatasourceStatus();
    fetchSchema();
    initConnectionPanel();
}

/**
 * Set up all event listeners using event delegation
 */
function setupEventListeners() {
    // User input - Enter key to send
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl+B or Cmd+B to toggle sidebar
        if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
            e.preventDefault();
            toggleSidebar();
        }
    });

    // Global click event delegation for all data-action elements
    document.addEventListener('click', handleAction);

    // Arrow-key navigation between sidebar tabs (ARIA tablist pattern)
    document.querySelector('.tabs').addEventListener('keydown', handleTabKeydown);

    // Keep responsive layout in sync across viewport changes
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
}

/**
 * Move focus (and switch to) the next/previous tab on arrow keys, per the
 * ARIA APG tablist keyboard pattern.
 * @param {KeyboardEvent} e
 */
function handleTabKeydown(e) {
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const currentIndex = tabs.indexOf(document.activeElement);
    if (currentIndex === -1) return;

    let newIndex;
    if (e.key === 'ArrowRight') newIndex = (currentIndex + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') newIndex = 0;
    else if (e.key === 'End') newIndex = tabs.length - 1;
    else return;

    e.preventDefault();
    tabs[newIndex].focus();
    switchTab(tabs[newIndex].dataset.tab);
}

/**
 * Global event delegation handler.
 * Routes clicks on elements with data-action attributes to appropriate functions.
 * @param {MouseEvent} e - Click event
 */
function handleAction(e) {
    const target = e.target.closest('[data-action]');
    if (!target) return;

    const action = target.dataset.action;

    switch (action) {
        case 'toggleSidebar':
            toggleSidebar();
            break;
        case 'toggleTheme':
            toggleTheme();
            break;
        case 'closeConfirmModal':
            closeConfirmModal();
            break;
        case 'confirmModalAccept':
            confirmModalAccept();
            break;
        case 'switchTab':
            switchTab(target.dataset.tab);
            if (isMobileViewport() && !sidebar.classList.contains('collapsed')) {
                toggleSidebar();
            }
            break;
        case 'sendMessage':
            sendMessage();
            break;
        case 'connectDatabase':
            connectFromForm();
            break;
        case 'resetSession':
            resetConversation();
            break;
        case 'closeFeedbackModal':
            closeFeedbackModal();
            break;
        case 'submitFeedbackWithText':
            submitFeedbackWithText();
            break;
        case 'loadSQL':
            loadSQL(target.dataset.question, target.dataset.sql);
            break;
        case 'sendFeedback':
            sendFeedback(target.dataset.logId, target.dataset.type);
            break;
        case 'showFeedbackModal':
            showFeedbackModal(target.dataset.logId);
            break;
        case 'saveFavorite':
            saveFavoriteFromHistory(target.dataset.logId, target.dataset.question, target.dataset.sql, target.dataset.dialect);
            break;
        case 'rerunQuery':
            rerunQuery(target.dataset.question);
            break;
        case 'deleteFavorite':
            deleteFavorite(target.dataset.favId);
            break;
    }
}

/**
 * Load SQL into input field from history
 * @param {string} question - Question to load
 * @param {string} _sql - SQL (unused, kept for compatibility)
 */
function loadSQL(question, _sql) {
    userInput.value = question;
}

/**
 * Re-run a query from history or favorites
 * @param {string} question - Question to re-run
 * @param {string} dialect - Database dialect
 */
function rerunQuery(question) {
    userInput.value = question;
    sendMessage();
}

/**
 * Save a query as favorite from history
 * @param {string} logId - Query log ID
 * @param {string} question - Question text
 * @param {string} sql - SQL query
 * @param {string} dialect - Database dialect
 */
async function saveFavoriteFromHistory(logId, question, sql, dialect) {
    try {
        await saveFavorite(question, sql, dialect, logId);
        switchTab('favorites');
    } catch (err) {
        appendMessage(formatError("บันทึกรายการโปรดไม่สำเร็จ กรุณาลองใหม่อีกครั้ง", err), false);
    }
}

/**
 * Delete a favorite query (after user confirms via the in-app confirm modal).
 * @param {string} favId - Favorite ID
 */
function deleteFavorite(favId) {
    showConfirmModal("ต้องการลบรายการโปรดนี้หรือไม่? การลบไม่สามารถย้อนกลับได้", async () => {
        try {
            await deleteFavoriteById(favId);
            fetchFavorites();
        } catch (err) {
            appendMessage(formatError("ลบรายการโปรดไม่สำเร็จ กรุณาลองใหม่อีกครั้ง", err), false);
        }
    });
}

/**
 * Show the generic confirm modal (replaces native confirm()) and stash the
 * action to run if the user accepts.
 * @param {string} message - Confirmation prompt text
 * @param {() => void} onConfirm - Callback to run if the user confirms
 */
let pendingConfirmAction = null;
function showConfirmModal(message, onConfirm) {
    document.getElementById('confirm-modal-message').textContent = message;
    pendingConfirmAction = onConfirm;
    document.getElementById('confirm-modal').style.display = 'flex';
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
    pendingConfirmAction = null;
}

function confirmModalAccept() {
    const action = pendingConfirmAction;
    closeConfirmModal();
    if (action) action();
}

/**
 * Apply collapsed visual state without persisting (used by resize handler).
 */
function applySidebarCollapsed(collapsed) {
    if (collapsed) {
        sidebar.classList.add('collapsed');
        openSidebarBtn.style.display = 'flex';
        sidebarBackdrop?.classList.remove('active');
    } else {
        sidebar.classList.remove('collapsed');
        openSidebarBtn.style.display = 'none';
        if (isMobileViewport()) {
            sidebarBackdrop?.classList.add('active');
        } else {
            sidebarBackdrop?.classList.remove('active');
        }
    }
}

/**
 * Sync the theme toggle icon with the theme already applied pre-paint
 * (see the inline script in index.html that reads localStorage before first render).
 */
function restoreThemeState() {
    const isDark = document.documentElement.dataset.theme === 'dark';
    themeIcon.textContent = isDark ? '☀️' : '🌙';
}

/**
 * Toggle between light and dark theme, persisting the choice.
 */
function toggleTheme() {
    const isDark = document.documentElement.dataset.theme === 'dark';
    if (isDark) {
        delete document.documentElement.dataset.theme;
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
    }
    themeIcon.textContent = isDark ? '🌙' : '☀️';
    refreshCharts();  // charts derive their colours from the theme tokens
}

/**
 * Toggle sidebar visibility
 */
function toggleSidebar() {
    const isCollapsed = sidebar.classList.contains('collapsed');
    applySidebarCollapsed(!isCollapsed);
    localStorage.setItem('sidebarCollapsed', String(!isCollapsed));
}

/**
 * Restore sidebar state from localStorage. On mobile, default to collapsed
 * when no user preference has been stored yet.
 */
function restoreSidebarState() {
    const stored = localStorage.getItem('sidebarCollapsed');
    const isCollapsed = stored === null ? isMobileViewport() : stored === 'true';
    applySidebarCollapsed(isCollapsed);
}

/**
 * Keep layout sane across viewport resizes (e.g. orientation change,
 * dragging window across breakpoints, devtools toggling).
 */
let resizeTimer = null;
function handleResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (!isMobileViewport()) {
            sidebarBackdrop?.classList.remove('active');
        } else if (!sidebar.classList.contains('collapsed')) {
            sidebarBackdrop?.classList.add('active');
        }
    }, 120);
}

/**
 * Send message/query to backend
 */
// One Turn at a time: an agent question takes ~10s (p95 ~17s), and a second
// submit mid-flight would interleave Turns of the same session.
let inFlight = false;

function setSendDisabled(disabled) {
    const sendBtn = document.querySelector('[data-action="sendMessage"]');
    if (sendBtn) {
        sendBtn.disabled = disabled;
        sendBtn.textContent = disabled ? 'กำลังค้นหา…' : 'Send 🚀';
    }
    if (userInput) userInput.disabled = disabled;
}

async function sendMessage() {
    if (inFlight) return;
    const text = userInput.value.trim();
    if (!text) return;

    inFlight = true;
    setSendDisabled(true);
    appendMessage(text, true);
    userInput.value = '';

    appendLoading();

    try {
        // Conversational session (ADR 0006): replay completed Turns so the
        // service can resolve pronouns like "ห้องนั้น" against prior context.
        const data = await sendQuery(text, null, getSessionTurns());

        removeLoading();

        if (data.error) {
            // Error envelopes carry no SQL (answer_type stays "result" by
            // default but sql is null) — only render the SQL when it exists.
            const sqlPart = data.sql
                ? `<br><pre><code class="language-sql">${sanitize(data.sql)}</code></pre>`
                : '';
            appendMessage(`❌ Error: ${sanitize(data.error.message)}${sqlPart}`, false);
        } else {
            renderAnswer(data);
            // Record this Turn for the next request — including refusals, so
            // the agent knows the prior topic was declined.
            addSessionTurn({
                question: text,
                answer_type: data.answer_type || 'result',
                sql: (data.answer_type || 'result') === 'result' ? data.sql : null,
                row_count: data.row_count || 0,
            });
            toggleResetBtn(false);
            // Refresh history if open
            if (getCurrentTab() === 'history') fetchHistory();
        }

    } catch (e) {
        removeLoading();
        appendMessage(formatError("ไม่สามารถติดต่อเซิร์ฟเวอร์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่อีกครั้ง", e), false);
    } finally {
        inFlight = false;
        setSendDisabled(false);
        userInput.focus();
    }
}

function toggleResetBtn(hidden) {
    const btn = document.getElementById('reset-session-btn');
    if (btn) btn.style.display = hidden ? 'none' : 'inline-flex';
}

/**
 * Start a new session: drop the replayed Turns so the next question is
 * interpreted standalone (topic switch), keeping the chat transcript.
 */
function resetConversation() {
    resetSession();
    toggleResetBtn(true);
    appendMessage('🔄 เริ่มบทสนทนาใหม่แล้ว — คำถามถัดไปจะไม่อ้างบริบทเดิม', false);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
