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

/**
 * Display labels for the service's chart-kind keys (ADR 0015). The envelope
 * carries keys so a Consumer can dispatch on them; the demo owns the words.
 * A kind missing here is not offered by the switcher — the renderer cannot
 * draw it, so an option would lie.
 * @type {Object<string, string>}
 */
export const CHART_KIND_LABELS = {
    bar: 'Bar',
    bar_horizontal: 'Horizontal bar',
    bar_grouped: 'Grouped bar',
    bar_stacked: 'Stacked bar',
    bar_stacked_100: 'Stacked 100%',
    line: 'Line',
    area: 'Area',
    combo: 'Bar + line',
    pie: 'Doughnut',
    scatter: 'Scatter',
    heatmap: 'Heatmap',
    treemap: 'Treemap',
};
