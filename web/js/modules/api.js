/**
 * API module for Thai NLP-to-SQL Agent
 * Handles all HTTP requests to the backend
 */

import { API_URL } from './config.js';

/**
 * Fetch database schema
 * @returns {Promise<Object>} Schema data with tables array
 */
export async function fetchSchemaData() {
    const res = await fetch(`${API_URL}/schema`);
    return res.json();
}

/**
 * Fetch query history
 * @param {number} limit - Maximum number of items
 * @returns {Promise<Object>} History data
 */
export async function fetchHistoryData(limit = 20) {
    const res = await fetch(`${API_URL}/history?limit=${limit}`);
    return res.json();
}

/**
 * Fetch favorite queries
 * @returns {Promise<Object>} Favorites data
 */
export async function fetchFavoritesData() {
    const res = await fetch(`${API_URL}/favorites`);
    return res.json();
}

/**
 * Connect to database
 * @param {Object} config - Database configuration
 * @returns {Promise<Object>} Connection result
 */
export async function connectDatabase(config) {
    const res = await fetch(`${API_URL}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config })
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail);
    }
    return data;
}

/**
 * Send NLP query
 * @param {string} question - User question
 * @param {string} dialect - Database dialect
 * @param {string|null} preferredChartType - Optional chart type preference
 * @returns {Promise<Object>} Query result with SQL, data, and visualization
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
    return res.json();
}

/**
 * Update feedback for a query
 * @param {string} logId - Query log ID
 * @param {string} feedback - Feedback type (positive/negative/comment)
 * @param {string|null} feedbackText - Optional feedback text
 * @returns {Promise<Response>} Fetch response
 */
export async function updateFeedback(logId, feedback, feedbackText = null) {
    return fetch(`${API_URL}/history/${logId}/feedback`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback, feedback_text: feedbackText })
    });
}

/**
 * Save query as favorite
 * @param {string} question - Query question
 * @param {string} sql - SQL query
 * @param {string} dialect - Database dialect
 * @param {string} logId - Original log ID
 * @returns {Promise<Response>} Fetch response
 */
export async function saveFavorite(question, sql, dialect, logId) {
    return fetch(`${API_URL}/favorites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, sql, dialect, log_id: logId })
    });
}

/**
 * Delete a favorite query
 * @param {string} favId - Favorite ID
 * @returns {Promise<Response>} Fetch response
 */
export async function deleteFavoriteById(favId) {
    return fetch(`${API_URL}/favorites/${favId}`, { method: 'DELETE' });
}
