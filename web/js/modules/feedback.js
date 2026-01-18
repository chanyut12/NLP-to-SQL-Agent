/**
 * Feedback module for Thai NLP-to-SQL Agent
 * Handles feedback modal and feedback submission
 */

import { getFeedbackLogId, setFeedbackLogId } from './state.js';
import { updateFeedback } from './api.js';
import { fetchHistory } from './ui.js';

/**
 * Show feedback modal for text input
 * @param {Event} e - Click event
 * @param {string} logId - Query log ID
 */
export function showFeedbackModal(e, logId) {
    e.stopPropagation();
    setFeedbackLogId(logId);
    const modal = document.getElementById('feedback-modal');
    const textarea = document.getElementById('feedback-text-input');
    textarea.value = '';
    modal.style.display = 'flex';
    textarea.focus();
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
 * Submit feedback with text from modal
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
        alert("Failed to save feedback");
    }
}

/**
 * Send quick feedback (thumbs up/down)
 * @param {Event} e - Click event
 * @param {string} logId - Query log ID
 * @param {string} feedback - Feedback type (positive/negative)
 */
export async function sendFeedback(e, logId, feedback) {
    e.stopPropagation();
    try {
        await updateFeedback(logId, feedback, null);
        fetchHistory(); // Refresh to show result
    } catch (e) {
        console.error("Feedback error", e);
    }
}
