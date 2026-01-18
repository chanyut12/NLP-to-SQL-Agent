/**
 * Main entry point for Thai NLP-to-SQL Agent
 *
 * This file imports all modules and sets up the application.
 * Functions are exposed to window object for HTML onclick handlers.
 */

// Module imports
import { API_URL } from './modules/config.js';
import {
    isConnected, setConnected, getCurrentTab,
    getVizConfig, getVizData, getChartId,
    setVizState, clearVizState
} from './modules/state.js';
import { sanitize } from './modules/utils.js';
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

    // Initialize UI module
    initUI();

    // Set up event listeners
    setupEventListeners();

    // Expose functions to window for HTML onclick handlers
    exposeToWindow();
}

/**
 * Set up all event listeners
 */
function setupEventListeners() {
    // Database type selector
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
    connectBtn.onclick = connectDB;
}

/**
 * Expose functions to window object for HTML onclick handlers
 */
function exposeToWindow() {
    window.switchTab = switchTab;
    window.sendMessage = sendMessage;
    window.handleKeyPress = handleKeyPress;
    window.loadSQL = loadSQL;
    window.rerunQuery = rerunQuery;
    window.sendFeedback = sendFeedback;
    window.showFeedbackModal = showFeedbackModal;
    window.closeFeedbackModal = closeFeedbackModal;
    window.submitFeedbackWithText = submitFeedbackWithText;
    window.saveFavoriteFromHistory = saveFavoriteFromHistory;
    window.deleteFavorite = deleteFavorite;
}

/**
 * Handle Enter key press in input field.
 * Exposed to window for HTML onkeypress handler.
 * @public
 * @param {KeyboardEvent} e - Keyboard event
 */
function handleKeyPress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
}

/**
 * Load SQL into input field from history.
 * Exposed to window for HTML onclick handler.
 * @public
 * @param {string} question - Question to load
 * @param {string} _sql - SQL (unused, kept for API compatibility)
 */
function loadSQL(question, _sql) {
    userInput.value = question;
}

/**
 * Re-run a query from history or favorites.
 * Exposed to window for HTML onclick handler.
 * @public
 * @param {Event} e - Click event
 * @param {string} question - Question to re-run
 * @param {string} dialect - Database dialect
 */
function rerunQuery(e, question, dialect) {
    e.stopPropagation();
    userInput.value = question;
    dbTypeSelect.value = dialect === 'sqlite' ? 'SQLite' : (dialect === 'mysql' ? 'MySQL' : 'PostgreSQL');
    sendMessage();
}

/**
 * Save a query as favorite from history.
 * Exposed to window for HTML onclick handler.
 * @public
 * @param {Event} e - Click event
 * @param {string} logId - Query log ID
 * @param {string} question - Question text
 * @param {string} sql - SQL query
 * @param {string} dialect - Database dialect
 */
async function saveFavoriteFromHistory(e, logId, question, sql, dialect) {
    e.stopPropagation();
    try {
        await saveFavorite(question, sql, dialect, logId);
        switchTab('favorites');
    } catch (err) {
        alert("Failed to save favorite: " + err.message);
    }
}

/**
 * Delete a favorite query.
 * Exposed to window for HTML onclick handler.
 * @public
 * @param {Event} e - Click event
 * @param {string} favId - Favorite ID
 */
async function deleteFavorite(e, favId) {
    e.stopPropagation();
    if (!confirm("Remove this favorite?")) return;

    try {
        await deleteFavoriteById(favId);
        fetchFavorites();
    } catch (err) {
        alert("Failed to delete: " + err.message);
    }
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
        appendMessage(`❌ Connection failed: ${e.message}`, false);
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
                html += `<br><small style="color: #fbbf24">Self-corrected after ${data.retry_count} retries</small>`;
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
        appendMessage(`❌ Network Error: ${e.message}`, false);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
