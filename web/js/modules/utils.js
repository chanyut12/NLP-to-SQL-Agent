/**
 * Utility functions for Thai NLP-to-SQL Agent
 * Contains sanitization and helper functions
 */

/**
 * Sanitize text to prevent XSS attacks
 * @param {any} text - Text to sanitize
 * @returns {string} Sanitized HTML-safe string
 */
export function sanitize(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/**
 * Format timestamp to locale string
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Formatted date string
 */
export function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString();
}
