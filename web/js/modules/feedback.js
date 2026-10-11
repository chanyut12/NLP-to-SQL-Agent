/**
 * Feedback module for Thai NLP-to-SQL Agent
 * Handles feedback modal and feedback submission
 */

import { getFeedbackLogId, setFeedbackLogId } from './state.js';
import { updateFeedback } from './api.js';
import { fetchHistory } from './ui.js';

/**
 * Show feedback modal for text input.
 * Called via event delegation from main.js handleAction().
 * @param {string} logId - Query log ID
 */
export function showFeedbackModal(logId) {
    setFeedbackLogId(logId);
    const modal = document.getElementById('feedback-modal');
    const textarea = document.getElementById('feedback-text-input');
    textarea.value = '';
    hideFeedbackError();
    modal.style.display = 'flex';
    textarea.focus();
}

function showFeedbackError(message) {
    const errorEl = document.getElementById('feedback-error');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

function hideFeedbackError() {
    const errorEl = document.getElementById('feedback-error');
    errorEl.style.display = 'none';
    errorEl.textContent = '';
}

/**
 * Close feedback modal
 */
export function closeFeedbackModal() {
    const modal = document.getElementById('feedback-modal');
    modal.style.display = 'none';
    setFeedbackLogId(null);
}

/**
 * Submit feedback with text from modal.
 * Reads text from modal textarea and sends as comment feedback.
 * @throws {Error} If updateFeedback() fails (caught internally, shows alert)
 */
export async function submitFeedbackWithText() {
    const textarea = document.getElementById('feedback-text-input');
    const feedbackText = textarea.value.trim();
    const logId = getFeedbackLogId();

    if (!logId) return;

    try {
        await updateFeedback(logId, 'comment', feedbackText);
        closeFeedbackModal();
        fetchHistory(); // Refresh to show new comment
    } catch (e) {
        console.error("Feedback error", e);
        showFeedbackError("บันทึก Feedback ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง");
    }
}

/**
 * Send quick feedback (thumbs up/down).
 * Called via event delegation from main.js handleAction().
 * @param {string} logId - Query log ID
 * @param {string} feedback - Feedback type ('positive' or 'negative')
 * @throws {Error} If updateFeedback() fails (caught internally, logged to console)
 */
export async function sendFeedback(logId, feedback) {
    try {
        await updateFeedback(logId, feedback, null);
        fetchHistory(); // Refresh to show result
    } catch (e) {
        console.error("Feedback error", e);
    }
}
