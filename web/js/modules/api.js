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
 * Connect to database
 * @param {Object} config - Database configuration
 * @param {string} config.db_type - Database type (sqlite, mysql, postgresql)
 * @param {string} [config.host] - Database host
 * @param {number} [config.port] - Database port
 * @param {string} [config.username] - Database username
 * @param {string} [config.password] - Database password
 * @param {string} [config.database] - Database name
 * @param {string} [config.file_path] - SQLite file path
 * @returns {Promise<Object>} Connection result with status and dialect
 * @throws {Error} If connection fails or server returns non-ok status
 */
export async function connectDatabase(config) {
    const res = await fetch(`${API_URL}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config })
    });
    return handleResponse(res);
}

/**
 * Send NLP query to generate and execute SQL
 * @param {string} question - User question in natural language
 * @param {string} dialect - Database dialect (sqlite, mysql, postgresql)
 * @param {string|null} [preferredChartType=null] - Optional chart type (bar, line, pie, scatter)
 * @returns {Promise<Object>} Query result containing sql, data, viz_config, and log_id
 * @throws {Error} If query fails or server returns non-ok status
 */
export async function sendQuery(question, dialect, preferredChartType = null) {
    const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question,
            dialect,
            preferred_chart_type: preferredChartType
        })
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
