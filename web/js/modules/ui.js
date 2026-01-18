/**
 * UI module for Thai NLP-to-SQL Agent
 * Handles DOM manipulation, messages, and rendering
 */

import { sanitize, escapeForOnclick, formatTimestamp } from './utils.js';
import { isConnected, setCurrentTab, getCurrentTab } from './state.js';
import { fetchSchemaData, fetchHistoryData, fetchFavoritesData } from './api.js';

// DOM Elements (cached on init)
let chatHistory = null;
let schemaContainer = null;
let historyContainer = null;
let favoritesContainer = null;

/**
 * Initialize UI module with DOM element references
 */
export function initUI() {
    chatHistory = document.getElementById('chat-history');
    schemaContainer = document.getElementById('schema-container');
    historyContainer = document.getElementById('history-container');
    favoritesContainer = document.getElementById('favorites-container');
}

/**
 * Switch to a different tab
 * @param {string} tabId - Tab identifier
 */
export function switchTab(tabId) {
    setCurrentTab(tabId);

    // Update Tab UI
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${tabId}')"]`).classList.add('active');

    // Update Content UI
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');

    // Refresh Data
    if (isConnected()) {
        if (tabId === 'history') fetchHistory();
        if (tabId === 'favorites') fetchFavorites();
        if (tabId === 'schema') fetchSchema();
    }
}

/**
 * Append a message to chat history
 * @param {string} content - Message content (HTML for bot, text for user)
 * @param {boolean} isUser - Whether this is a user message
 */
export function appendMessage(content, isUser) {
    const div = document.createElement('div');
    div.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    if (isUser) {
        div.textContent = content;
    } else {
        div.innerHTML = content;
    }
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Trigger syntax highlighting for new content
    div.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
    });
}

/**
 * Show loading indicator
 * @returns {HTMLElement} The loading element
 */
export function appendLoading() {
    const div = document.createElement('div');
    div.id = 'loading-indicator';
    div.className = 'message bot-message';
    div.innerHTML = '<span class="pulse">🤖 Thinking...</span>';
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
}

/**
 * Remove loading indicator
 */
export function removeLoading() {
    const loading = document.getElementById('loading-indicator');
    if (loading) loading.remove();
}

/**
 * Render data as HTML table
 * @param {Array<Object>} data - Array of row objects
 * @returns {string} HTML table string
 */
export function renderTable(data) {
    if (!data || data.length === 0) return "";

    const headers = Object.keys(data[0]);
    let html = '<div class="table-wrapper"><table><thead><tr>';

    headers.forEach(h => html += `<th>${sanitize(h)}</th>`);
    html += "</tr></thead><tbody>";

    data.forEach(row => {
        html += "<tr>";
        headers.forEach(h => html += `<td>${sanitize(row[h])}</td>`);
        html += "</tr>";
    });

    html += "</tbody></table></div>";
    return html;
}

/**
 * Fetch and render database schema
 */
export async function fetchSchema() {
    try {
        const data = await fetchSchemaData();

        if (!data.tables || data.tables.length === 0) {
            schemaContainer.innerHTML = '<p style="text-align: center; color: #64748b;">No tables found</p>';
            return;
        }

        schemaContainer.innerHTML = data.tables.map(table => `
            <details>
                <summary>📝 ${sanitize(table.name)}</summary>
                <div class="column-list">
                    ${table.columns.map(col => `
                        <div>
                            <span>${sanitize(col.name)}</span>
                            <span class="col-type">${sanitize(col.type)}</span>
                        </div>
                    `).join('')}
                </div>
            </details>
        `).join('');
    } catch (e) {
        console.error("Schema error:", e);
    }
}

/**
 * Fetch and render query history
 */
export async function fetchHistory() {
    try {
        const data = await fetchHistoryData();

        if (!data.history || data.history.length === 0) {
            historyContainer.innerHTML = '<p style="text-align: center; color: #64748b; margin-top: 20px;">No history yet</p>';
            return;
        }

        historyContainer.innerHTML = data.history.map(item => {
            const isPos = item.feedback === 'positive';
            const isNeg = item.feedback === 'negative';
            const hasFeedbackText = item.feedback_text && item.feedback_text.trim().length > 0;

            const escapedQuestion = escapeForOnclick(item.question);
            const escapedSql = escapeForOnclick(item.sql);

            return `
            <div class="history-item" onclick="loadSQL('${escapedQuestion}', '${escapedSql}')">
                <div class="item-header">
                    <span>${formatTimestamp(item.timestamp)}</span>
                    <span style="color: ${item.status.includes('Success') ? '#22c55e' : '#ef4444'}">${item.status}</span>
                </div>
                <div class="item-question">${sanitize(item.question)}</div>
                <div class="item-sql">${sanitize(item.sql)}</div>
                ${hasFeedbackText ? `<div class="feedback-comment" title="User Feedback">💬 ${sanitize(item.feedback_text)}</div>` : ''}
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

/**
 * Fetch and render favorite queries
 */
export async function fetchFavorites() {
    try {
        const data = await fetchFavoritesData();

        if (!data.favorites || data.favorites.length === 0) {
            favoritesContainer.innerHTML = '<p style="text-align: center; color: #64748b; margin-top: 20px;">No favorites yet</p>';
            return;
        }

        favoritesContainer.innerHTML = data.favorites.map(item => `
            <div class="fav-item">
                <div class="item-header">
                    <span>Used ${item.use_count} times</span>
                </div>
                <div class="item-question">${sanitize(item.name || item.question)}</div>
                <div class="item-sql">${sanitize(item.sql)}</div>
                <div class="actions">
                    <button class="icon-btn" onclick="rerunQuery(event, '${escapeForOnclick(item.question)}', '${item.dialect}')" title="Run">
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
