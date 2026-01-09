const API_URL = "http://localhost:8000/api";

// DOM Elements
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const dbTypeSelect = document.getElementById('db-type');
const statusBadge = document.getElementById('connection-status');
const connectBtn = document.getElementById('connect-btn');

// State
let isConnected = false;
let currentTab = 'connection';
// Visualization State
let currentVizConfig = null;
let currentVizData = null;
let currentChartId = null;

// --- Tab Switching Logic ---
function switchTab(tabId) {
    currentTab = tabId;

    // Update Tab UI
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${tabId}')"]`).classList.add('active');

    // Update Content UI
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');

    // Refresh Data
    if (isConnected) {
        if (tabId === 'history') fetchHistory();
        if (tabId === 'favorites') fetchFavorites();
        if (tabId === 'schema') fetchSchema();
    }
}

// --- Data Fetching ---
async function fetchSchema() {
    try {
        const res = await fetch(`${API_URL}/schema`);
        const data = await res.json();
        const container = document.getElementById('schema-container');

        if (!data.tables || data.tables.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #64748b;">No tables found</p>';
            return;
        }

        container.innerHTML = data.tables.map(table => `
            <details>
                <summary>📝 ${table.name}</summary>
                <div class="column-list">
                    ${table.columns.map(col => `
                        <div>
                            <span>${col.name}</span>
                            <span class="col-type">${col.type}</span>
                        </div>
                    `).join('')}
                </div>
            </details>
        `).join('');
    } catch (e) {
        console.error("Schema error:", e);
    }
}

async function fetchHistory() {
    try {
        const res = await fetch(`${API_URL}/history?limit=20`);
        const data = await res.json();
        const container = document.getElementById('history-container');

        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #64748b; margin-top: 20px;">No history yet</p>';
            return;
        }

        container.innerHTML = data.history.map(item => {
            const isPos = item.feedback === 'positive';
            const isNeg = item.feedback === 'negative';
            const hasFeedbackText = item.feedback_text && item.feedback_text.trim().length > 0;

            // Escape quotes for onclick handlers
            const escapedQuestion = item.question.replace(/'/g, "\\'").replace(/"/g, "&quot;");
            const escapedSql = item.sql.replace(/'/g, "\\'").replace(/"/g, "&quot;");

            return `
            <div class="history-item" onclick="loadSQL('${escapedQuestion}', '${escapedSql}')">
                <div class="item-header">
                    <span>${new Date(item.timestamp).toLocaleString()}</span>
                    <span style="color: ${item.status.includes('Success') ? '#22c55e' : '#ef4444'}">${item.status}</span>
                </div>
                <div class="item-question">${item.question}</div>
                <div class="item-sql">${item.sql}</div>
                ${hasFeedbackText ? `<div class="feedback-comment" title="User Feedback">💬 ${item.feedback_text}</div>` : ''}
                <div class="actions">
                    <button class="icon-btn" onclick="sendFeedback(event, '${item.log_id}', 'positive')" 
                        style="${isPos ? 'color: #22c55e; font-weight: bold;' : ''}" title="Good Response">
                        👍
                    </button>
                    <button class="icon-btn" onclick="sendFeedback(event, '${item.log_id}', 'negative')" 
                        style="${isNeg ? 'color: #ef4444; font-weight: bold;' : ''}" title="Bad Response">
                        👎
                    </button>
                    <button class="icon-btn" onclick="showFeedbackModal(event, '${item.log_id}')" title="Add Comment">
                        💬
                    </button>
                    <button class="icon-btn" onclick="saveFavoriteFromHistory(event, '${item.log_id}', '${escapedQuestion}', '${escapedSql}', '${item.dialect}')" title="Save as Favorite">
                        ⭐
                    </button>
                    <button class="icon-btn" onclick="rerunQuery(event, '${escapedQuestion}', '${item.dialect}')" title="Re-run">
                        🔄
                    </button>
                </div>
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error("History error:", e);
    }
}

async function fetchFavorites() {
    try {
        const res = await fetch(`${API_URL}/favorites`);
        const data = await res.json();
        const container = document.getElementById('favorites-container');

        if (!data.favorites || data.favorites.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #64748b; margin-top: 20px;">No favorites yet</p>';
            return;
        }

        container.innerHTML = data.favorites.map(item => `
            <div class="fav-item">
                <div class="item-header">
                    <span>Used ${item.use_count} times</span>
                </div>
                <div class="item-question">${item.name || item.question}</div>
                <div class="item-sql">${item.sql}</div>
                <div class="actions">
                    <button class="icon-btn" onclick="rerunQuery(event, '${item.question}', '${item.dialect}')" title="Run">
                        ▶️
                    </button>
                    <button class="icon-btn delete" onclick="deleteFavorite(event, '${item.favorite_id}')" title="Delete">
                        🗑️
                    </button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Favorites error:", e);
    }
}

// --- Interaction Logic ---
let currentFeedbackLogId = null;

// Show feedback modal for text input
function showFeedbackModal(e, logId) {
    e.stopPropagation();
    currentFeedbackLogId = logId;
    const modal = document.getElementById('feedback-modal');
    const textarea = document.getElementById('feedback-text-input');
    textarea.value = '';
    modal.style.display = 'flex';
    textarea.focus();
}

// Close feedback modal
function closeFeedbackModal() {
    const modal = document.getElementById('feedback-modal');
    modal.style.display = 'none';
    currentFeedbackLogId = null;
}

// Submit feedback with text from modal
async function submitFeedbackWithText() {
    const textarea = document.getElementById('feedback-text-input');
    const feedbackText = textarea.value.trim();

    if (!currentFeedbackLogId) return;

    try {
        // Default to neutral feedback type when just adding comment
        await fetch(`${API_URL}/history/${currentFeedbackLogId}/feedback`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                feedback: 'comment',  // New type for text-only feedback
                feedback_text: feedbackText
            })
        });
        closeFeedbackModal();
        fetchHistory(); // Refresh to show new comment
    } catch (e) {
        console.error("Feedback error", e);
        alert("Failed to save feedback");
    }
}

async function sendFeedback(e, logId, feedback, feedbackText = null) {
    e.stopPropagation();
    try {
        await fetch(`${API_URL}/history/${logId}/feedback`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feedback, feedback_text: feedbackText })
        });
        fetchHistory(); // Refresh to show result
    } catch (e) {
        console.error("Feedback error", e);
    }
}

async function saveFavoriteFromHistory(e, logId, question, sql, dialect) {
    e.stopPropagation(); // Prevent item click
    try {
        await fetch(`${API_URL}/favorites`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, sql, dialect, log_id: logId })
        });
        switchTab('favorites'); // Switch to fav tab to show it
    } catch (e) {
        alert("Failed to save favorite: " + e.message);
    }
}

async function deleteFavorite(e, favId) {
    e.stopPropagation();
    if (!confirm("Remove this favorite?")) return;

    try {
        await fetch(`${API_URL}/favorites/${favId}`, { method: 'DELETE' });
        fetchFavorites(); // Refresh
    } catch (e) {
        alert("Failed to delete: " + e.message);
    }
}

function loadSQL(question, sql) {
    userInput.value = question; // Pre-fill question
}

function rerunQuery(e, question, dialect) {
    e.stopPropagation();
    userInput.value = question;
    dbTypeSelect.value = dialect === 'sqlite' ? 'SQLite' : (dialect === 'mysql' ? 'MySQL' : 'PostgreSQL');
    sendMessage();
}


// --- Existing Logic (Updated) ---
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

// Chart Type Selector
document.getElementById('chart-type-selector').addEventListener('change', (e) => {
    if (currentVizConfig && currentVizData && currentChartId) {
        let type = e.target.value;
        let p_config = { ...currentVizConfig };

        if (type === 'auto') {
            // If auto, we rely on the ORIGINAL (which might have been user overridden in prompt, but here means "system default")
            // Wait, currentVizConfig IS the system calculation (unless we muted it).
            // Actually, 'currentVizConfig' holds the LAST rendered state.
            // We need `data.visualization` from the response. But we didn't store the *original* response globally, only `currentVizConfig`.
            // Minor limitation: "Auto" here just means "What was sent by backend".
            // If backend sent "pie" because of prompt, Auto = Pie.
            // If backend sent "bar" because of heuristic, Auto = Bar.
            // This is correct behavior.
            type = p_config.chart_type;
        } else {
            p_config.chart_type = type;
        }

        renderChart(currentChartId, p_config, currentVizData);
    }
});

function handleKeyPress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
}

function appendMessage(content, isUser) {
    const div = document.createElement('div');
    div.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    div.innerHTML = content;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Trigger syntax highlighting for new content
    div.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
    });
}

function appendLoading() {
    const div = document.createElement('div');
    div.id = 'loading-indicator';
    div.className = 'message bot-message';
    div.innerHTML = '<span class="pulse">🤖 Thinking...</span>';
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
}

function removeLoading() {
    const loading = document.getElementById('loading-indicator');
    if (loading) loading.remove();
}

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
        const res = await fetch(`${API_URL}/connect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config })
        });

        const data = await res.json();
        if (res.ok) {
            isConnected = true;
            statusBadge.className = "status-badge connected";
            statusBadge.textContent = "Connected";
            appendMessage(`✅ Connected to ${type} successfully!`, false);

            // Auto fetch schema
            fetchSchema();
            // Switch to history or schema to show usefulness
            // switchTab('schema'); 
        } else {
            throw new Error(data.detail);
        }
    } catch (e) {
        appendMessage(`❌ Connection failed: ${e.message}`, false);
        statusBadge.className = "status-badge disconnected";
        statusBadge.textContent = "Error";
    } finally {
        connectBtn.textContent = "Connect Database";
        connectBtn.disabled = false;
    }
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    if (!isConnected) {
        appendMessage("⚠️ Please connect to a database first.", false);
        return;
    }

    appendMessage(text, true);
    userInput.value = '';

    appendLoading();

    // Hide chart selector while loading
    document.getElementById('chart-type-selector').style.display = 'none';

    try {
        // Get selected chart type from dropdown
        const chartSelector = document.getElementById('chart-type-selector');
        const preferredChartType = chartSelector.value !== 'auto' ? chartSelector.value : null;

        const res = await fetch(`${API_URL}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: text,
                dialect: dbTypeSelect.value.toLowerCase(),
                preferred_chart_type: preferredChartType
            })
        });

        const data = await res.json();
        removeLoading();

        if (data.error) {
            appendMessage(`❌ Error: ${data.error}<br><pre><code class="language-sql">${data.sql}</code></pre>`, false);
        } else {
            let html = `<strong>Generated SQL:</strong><pre><code class="language-sql">${data.sql}</code></pre>`;

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
                html += `<div class="chart-container" style="position: relative; height:300px; width:100%"><canvas id="${chartId}"></canvas></div>`;

                // Update Globals for switching
                currentVizConfig = data.visualization;
                currentVizData = data.data;
                currentChartId = chartId;

                // Show Selector
                const selector = document.getElementById('chart-type-selector');
                selector.style.display = 'inline-block';
                // Reset to Auto by default or currently recommended?
                // User wants "Auto" to be default conceptual, but dropdown should reflect reality?
                // Actually user said: "set default to system thought"
                // So we set value to 'auto'? No, 'auto' implies "whatever system thinks".
                // Let's set it to 'auto' visually, but render the 'system recommended'.
                selector.value = 'auto';

            } else {
                document.getElementById('chart-type-selector').style.display = 'none';
                currentVizConfig = null;
                currentVizData = null;
                currentChartId = null;
            }

            appendMessage(html, false);

            if (chartId && data.visualization) {
                renderChart(chartId, data.visualization, data.data);
            }

            // Refresh history if open
            if (currentTab === 'history') fetchHistory();
        }

    } catch (e) {
        removeLoading();
        appendMessage(`❌ Network Error: ${e.message}`, false);
    }
}

function renderTable(data) {
    if (!data || data.length === 0) return "";

    const headers = Object.keys(data[0]);
    let html = "<table><thead><tr>";

    headers.forEach(h => html += `<th>${h}</th>`);
    html += "</tr></thead><tbody>";

    data.forEach(row => {
        html += "<tr>";
        headers.forEach(h => html += `<td>${row[h]}</td>`);
        html += "</tr>";
    });

    html += "</tbody></table>";
    return html;
}

function renderChart(canvasId, config, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');

    // Destroy existing chart if any (needs tracking, but for now we generate unique IDs so it's fine)
    // Actually, distinct IDs mean we don't need to destroy, but memory leak caution.
    // For now, simple render.

    // Prepare Data
    const labels = data.map(row => row[config.x_col]);
    const values = data.map(row => row[config.y_col]);

    // Colors
    const isPie = config.chart_type === 'pie';
    const bgColors = isPie ? [
        '#60a5fa', '#34d399', '#f472b6', '#a78bfa', '#fbbf24', '#f87171', '#818cf8', '#fb7185'
    ] : 'rgba(96, 165, 250, 0.5)';

    const borderColors = isPie ? bgColors : '#60a5fa';

    new Chart(ctx, {
        type: config.chart_type === 'bar' || config.chart_type === 'column' ? 'bar' :
            config.chart_type === 'line' ? 'line' :
                config.chart_type === 'scatter' ? 'scatter' :
                    config.chart_type === 'pie' ? 'pie' : 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: config.y_col,
                data: values,
                backgroundColor: bgColors,
                borderColor: borderColors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#94a3b8' }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y;
                            }

                            // Calculate % for Pie
                            if (config.chart_type === 'pie') {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const value = context.parsed;
                                const percent = ((value / total) * 100).toFixed(1) + "%";
                                label += ` (${percent})`;
                            }
                            return label;
                        }
                    }
                }
            },
            scales: config.chart_type !== 'pie' ? {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                y: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                }
            } : {
                x: { display: false },
                y: { display: false }
            }
        }
    });
}

connectBtn.onclick = connectDB;
