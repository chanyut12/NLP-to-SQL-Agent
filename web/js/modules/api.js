/**
 * API module for Thai NLP-to-SQL Agent
 * Handles all HTTP requests to the backend
 */

import { API_URL } from './config.js';

/**
 * Handle fetch response - checks HTTP status and parses JSON
 * @param {Response} response - Fetch Response object
 * @returns {Promise<Object>} Parsed JSON response
 * @throws {Error} If response status is not ok (4xx/5xx)
 */
async function handleResponse(response) {
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Datasource health — { status, datasource: bool }
 */
export async function fetchHealth() {
    const res = await fetch(`${API_URL}/health`);
    return handleResponse(res);
}

/**
 * Demo-mode Datasource state — { datasource, profile, profiles }.
 *
 * Only mounted while the demo UI is served (ADR 0013); a 404 means this
 * deployment has no connection panel and the caller should hide it.
 */
export async function fetchDemoState() {
    const res = await fetch(`${API_URL}/demo/state`);
    return handleResponse(res);
}

/**
 * Switch the running demo to another Datasource (APP_MODE=demo only).
 * @param {string} databaseUrl - SQLAlchemy DSN, e.g. sqlite:///./local_database.db
 * @param {string} profile - Domain profile name under profiles/
 * @returns {Promise<Object>} { datasource, profile, tables }
 */
export async function connectDemoDatabase(databaseUrl, profile) {
    const res = await fetch(`${API_URL}/demo/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ database_url: databaseUrl, profile }),
    });
    return handleResponse(res);
}

/**
 * Fetch database schema
 * @returns {Promise<Object>} Schema data with tables array
 * @throws {Error} If server returns non-ok status
 */
export async function fetchSchemaData() {
    const res = await fetch(`${API_URL}/schema`);
    return handleResponse(res);
}

/**
 * Fetch query history
 * @param {number} [limit=20] - Maximum number of items to retrieve
 * @returns {Promise<Object>} History data with history array
 * @throws {Error} If server returns non-ok status
 */
export async function fetchHistoryData(limit = 20) {
    const res = await fetch(`${API_URL}/history?limit=${limit}`);
    return handleResponse(res);
}

/**
 * Fetch favorite queries
 * @returns {Promise<Object>} Favorites data with favorites array
 * @throws {Error} If server returns non-ok status
 */
export async function fetchFavoritesData() {
    const res = await fetch(`${API_URL}/favorites`);
    return handleResponse(res);
}

/**
 * Send a question. The service picks the dialect from its own datasource.
 * @param {string} question - User question in natural language
 * @param {string|null} [preferredChartType=null] - Optional chart type (bar, line, pie, scatter)
 * @param {Array|null} [history=null] - Prior Turns for a conversational session (ADR 0006)
 * @returns {Promise<Object>} The response envelope (status, answer_type, sql, rows, visualization, error, ...)
 */
export async function sendQuery(question, preferredChartType = null, history = null) {
    // ALWAYS include history — an empty array selects agent mode (the PRESENCE
    // of the field dispatches, not its contents). Omitting it on the first
    // Turn silently fell back to the legacy one-shot pipeline, so clarify/
    // refuse never worked on question one (found in the frontend review).
    const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question,
            preferred_chart_type: preferredChartType,
            history: history ?? [],
        }),
    });
    return handleResponse(res);
}

/**
 * Update feedback for a query
 * @param {string} logId - Query log ID
 * @param {string} feedback - Feedback type (positive, negative, or comment)
 * @param {string|null} [feedbackText=null] - Optional feedback text comment
 * @returns {Promise<Object>} Updated feedback result
 * @throws {Error} If server returns non-ok status
 */
export async function updateFeedback(logId, feedback, feedbackText = null) {
    const res = await fetch(`${API_URL}/history/${logId}/feedback`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback, feedback_text: feedbackText })
    });
    return handleResponse(res);
}

/**
 * Save query as favorite
 * @param {string} question - Query question text
 * @param {string} sql - SQL query string
 * @param {string} dialect - Database dialect
 * @param {string} logId - Original query log ID
 * @returns {Promise<Object>} Saved favorite result
 * @throws {Error} If server returns non-ok status
 */
export async function saveFavorite(question, sql, dialect, logId) {
    const res = await fetch(`${API_URL}/favorites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, sql, dialect, log_id: logId })
    });
    return handleResponse(res);
}

/**
 * Delete a favorite query
 * @param {string} favId - Favorite ID to delete
 * @returns {Promise<Object>} Deletion result
 * @throws {Error} If server returns non-ok status
 */
export async function deleteFavoriteById(favId) {
    const res = await fetch(`${API_URL}/favorites/${favId}`, { method: 'DELETE' });
    return handleResponse(res);
}
