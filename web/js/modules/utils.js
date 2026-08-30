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

/**
 * Build a user-facing error message: a plain-language Thai explanation with
 * a suggested next step, followed by the raw technical detail as smaller
 * muted text (kept for debugging/support, not hidden — just de-emphasized).
 * @param {string} friendlyMessage - Plain-language explanation + next step
 * @param {Error} err - The caught error
 * @returns {string} HTML string safe to pass to appendMessage
 */
export function formatError(friendlyMessage, err) {
    return `❌ ${friendlyMessage}<br><small class="text-muted">${sanitize(err.message)}</small>`;
}
