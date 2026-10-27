/**
 * Configuration module for Thai NLP-to-SQL Agent
 * Contains API URL and application constants
 */

/** @type {string} Backend API base URL — the UI is served by the API itself, so
 * this must follow whatever host/port the demo server is running on (8000 for
 * the service, 8001 for demo mode). */
export const API_URL = "/api";

/**
 * Categorical palette for pie/doughnut slices and multi-series charts.
 * Muted (seaborn "deep") — reads as intentional, easy on the eyes in both themes.
 * Single-series bar/line take their colour from the `--chart-series-1` CSS token
 * instead, so they track the UI theme.
 * @type {Array<string>}
 */
export const CATEGORICAL_COLORS = [
    '#4C72B0', '#DD8452', '#55A868', '#C44E52',
    '#8172B2', '#937860', '#DA8BC3',
];
