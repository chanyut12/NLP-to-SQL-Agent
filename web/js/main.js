/**
 * Main entry point for Thai NLP-to-SQL Agent
 *
 * This file imports all modules and sets up the application.
 * Uses event delegation via data-action attributes instead of inline handlers.
 */

// Module imports
import { API_URL } from './modules/config.js';
import {
    isConnected, setConnected, getCurrentTab,
    getVizConfig, getVizData, getChartId,
    setVizState, clearVizState
} from './modules/state.js';
import { sanitize, formatError } from './modules/utils.js';
import { connectDatabase, sendQuery, saveFavorite, deleteFavoriteById } from './modules/api.js';
import {
    initUI, switchTab, appendMessage, appendLoading, removeLoading,
    renderTable, fetchSchema, fetchHistory, fetchFavorites
} from './modules/ui.js';
import {
    showFeedbackModal, closeFeedbackModal, submitFeedbackWithText, sendFeedback
} from './modules/feedback.js';
import { renderChart } from './modules/chart.js';

// DOM Elements
let userInput = null;
let dbTypeSelect = null;
let statusBadge = null;
let connectBtn = null;
let chartSelector = null;
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
    dbTypeSelect = document.getElementById('db-type');
    statusBadge = document.getElementById('connection-status');
    connectBtn = document.getElementById('connect-btn');
    chartSelector = document.getElementById('chart-type-selector');
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
}

/**
 * Set up all event listeners using event delegation
 */
function setupEventListeners() {
    // Database type selector
    const DEFAULT_PORTS = { MySQL: '3306', PostgreSQL: '5432' };
    dbTypeSelect.addEventListener('change', (e) => {
        const type = e.target.value;
        const sqliteConfig = document.getElementById('sqlite-config');
        const sqlConfig = document.getElementById('sql-config');

        if (type === 'SQLite') {
            sqliteConfig.style.display = 'flex';
            sqlConfig.style.display = 'none';
        } else {
            sqliteConfig.style.display = 'none';
            sqlConfig.style.display = 'flex';

            // Refresh the port to this dialect's default, unless the user
            // already typed something other than one of the known defaults.
            const portInput = document.getElementById('db-port');
            const knownDefaults = Object.values(DEFAULT_PORTS);
            if (!portInput.value || knownDefaults.includes(portInput.value)) {
                portInput.value = DEFAULT_PORTS[type] || '';
            }
        }
    });

    // Chart type selector
    chartSelector.addEventListener('change', (e) => {
        const vizConfig = getVizConfig();
        const vizData = getVizData();
        const chartId = getChartId();

        if (vizConfig && vizData && chartId) {
            let type = e.target.value;
            let pConfig = { ...vizConfig };

            if (type === 'auto') {
                type = pConfig.chart_type;
            } else {
                pConfig.chart_type = type;
            }

            renderChart(chartId, pConfig, vizData);
        }
    });

    // Connect button
    connectBtn.addEventListener('click', connectDB);

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
            rerunQuery(target.dataset.question, target.dataset.dialect);
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
function rerunQuery(question, dialect) {
    userInput.value = question;
    dbTypeSelect.value = dialect === 'sqlite' ? 'SQLite' : (dialect === 'mysql' ? 'MySQL' : 'PostgreSQL');
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
 * Connect to database
 */
async function connectDB() {
    const type = dbTypeSelect.value;
    const config = {
        db_type: type,
        database: "",
        host: "localhost",
        port: "",
        user: "",
        password: ""
    };

    if (type === 'SQLite') {
        config.database = document.getElementById('db-path').value;
    } else {
        config.host = document.getElementById('db-host').value;
        config.port = document.getElementById('db-port').value;
        config.user = document.getElementById('db-user').value;
        config.password = document.getElementById('db-pass').value;
        config.database = document.getElementById('db-name').value;
    }

    connectBtn.textContent = "Connecting...";
    connectBtn.disabled = true;

    try {
        await connectDatabase(config);
        setConnected(true);
        statusBadge.className = "status-badge connected";
        statusBadge.textContent = "Connected";
        appendMessage(`✅ Connected to ${type} successfully!`, false);

        // Auto fetch schema
        fetchSchema();
    } catch (e) {
        appendMessage(formatError("เชื่อมต่อฐานข้อมูลไม่สำเร็จ กรุณาตรวจสอบ Host, Port, Username และ Password อีกครั้ง", e), false);
        statusBadge.className = "status-badge disconnected";
        statusBadge.textContent = "Error";
    } finally {
        connectBtn.textContent = "Connect Database";
        connectBtn.disabled = false;
    }
}

/**
 * Send message/query to backend
 */
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    if (!isConnected()) {
        appendMessage("⚠️ Please connect to a database first.", false);
        return;
    }

    appendMessage(text, true);
    userInput.value = '';

    appendLoading();

    // Hide chart selector while loading
    chartSelector.style.display = 'none';

    try {
        // Get selected chart type from dropdown
        const preferredChartType = chartSelector.value !== 'auto' ? chartSelector.value : null;

        const data = await sendQuery(
            text,
            dbTypeSelect.value.toLowerCase(),
            preferredChartType
        );

        removeLoading();

        if (data.error) {
            appendMessage(`❌ Error: ${sanitize(data.error)}<br><pre><code class="language-sql">${sanitize(data.sql)}</code></pre>`, false);
        } else {
            let html = `<strong>Generated SQL:</strong><pre><code class="language-sql">${sanitize(data.sql)}</code></pre>`;

            if (data.data && data.data.length > 0) {
                html += renderTable(data.data);
            } else {
                html += "<br><em>No results found or empty set.</em>";
            }

            if (data.retry_count > 0) {
                html += `<br><small class="text-warning">Self-corrected after ${data.retry_count} retries</small>`;
            }

            // Visualization
            let chartId = null;
            if (data.visualization && data.visualization.chart_type !== 'none' && data.visualization.chart_type !== 'table') {
                chartId = 'chart-' + Math.random().toString(36).substr(2, 9);
                html += `<div class="chart-container"><canvas id="${chartId}"></canvas></div>`;

                // Update visualization state
                setVizState(data.visualization, data.data, chartId);

                // Show selector
                chartSelector.style.display = 'inline-block';
                chartSelector.value = 'auto';
            } else {
                chartSelector.style.display = 'none';
                clearVizState();
            }

            appendMessage(html, false);

            if (chartId && data.visualization) {
                renderChart(chartId, data.visualization, data.data);
            }

            // Refresh history if open
            if (getCurrentTab() === 'history') fetchHistory();
        }

    } catch (e) {
        removeLoading();
        appendMessage(formatError("ไม่สามารถติดต่อเซิร์ฟเวอร์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่อีกครั้ง", e), false);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
