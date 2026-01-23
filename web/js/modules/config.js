/**
 * Configuration module for Thai NLP-to-SQL Agent
 * Contains API URL and application constants
 */

/** @type {string} Backend API base URL */
export const API_URL = "http://localhost:8000/api";

/**
 * Chart color palette for multi-series charts
 * @type {Array<{bg: string, border: string}>}
 */
export const CHART_COLORS = [
    { bg: 'rgba(96, 165, 250, 0.7)', border: '#60a5fa' },   // Blue
    { bg: 'rgba(239, 68, 68, 0.7)', border: '#ef4444' },    // Red
    { bg: 'rgba(34, 197, 94, 0.7)', border: '#22c55e' },    // Green
    { bg: 'rgba(168, 85, 247, 0.7)', border: '#a855f7' },   // Purple
    { bg: 'rgba(251, 191, 36, 0.7)', border: '#fbbf24' },   // Yellow
    { bg: 'rgba(236, 72, 153, 0.7)', border: '#ec4899' },   // Pink
    { bg: 'rgba(20, 184, 166, 0.7)', border: '#14b8a6' },   // Teal
    { bg: 'rgba(249, 115, 22, 0.7)', border: '#f97316' },   // Orange
];

/**
 * Pie chart color palette
 * @type {Array<string>}
 */
export const PIE_COLORS = [
    '#60a5fa', '#34d399', '#f472b6', '#a78bfa',
    '#fbbf24', '#f87171', '#818cf8', '#fb7185'
];
