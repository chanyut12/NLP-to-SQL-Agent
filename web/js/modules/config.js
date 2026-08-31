/**
 * Configuration module for Thai NLP-to-SQL Agent
 * Contains API URL and application constants
 */

/** @type {boolean} Whether the frontend is running on localhost */
const isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(window.location.hostname);

/** @type {string} Backend API base URL */
export const API_URL = isLocal
    ? "http://localhost:8000/api"
    : "/api"; // served same-origin by the FastAPI app

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
