/**
 * Chart module for Thai NLP-to-SQL Agent
 * Handles Chart.js visualization rendering
 */

import { CHART_COLORS, PIE_COLORS } from './config.js';
import { formatAxisValue } from './format.js';

// canvasId -> Chart instance, so a re-render (chart-type switch) destroys the old one.
const _charts = new Map();

/** Tear down the chart bound to a canvas, if any. */
function destroyChart(canvasId) {
    const existing = _charts.get(canvasId);
    if (existing) {
        existing.destroy();
        _charts.delete(canvasId);
    }
}

/** semantic_type of a column, from the envelope's `columns` list. */
function semanticTypeOf(columns, name) {
    const col = (columns || []).find((c) => c.name === name);
    return col ? col.semantic_type : 'number';
}

/** Numeric, non-id column names — used to pick scatter axes. */
function numericColumns(columns) {
    return (columns || [])
        .filter((c) => c.numeric && c.semantic_type !== 'id')
        .map((c) => c.name);
}

/**
 * Fold a high-cardinality category axis into "top N + other".
 * Only for single-series bar / pie, when the backend set `top_n`.
 */
function applyTopN(config, data) {
    const { top_n: topN, chart_type: type, x_col: x, y_col: y } = config;
    if (!topN || config.series_col) return data;
    if (type !== 'bar' && type !== 'pie') return data;
    if (data.length <= topN) return data;

    const sorted = [...data].sort((a, b) => (Number(b[y]) || 0) - (Number(a[y]) || 0));
    const head = sorted.slice(0, topN);
    const tailSum = sorted.slice(topN).reduce((s, r) => s + (Number(r[y]) || 0), 0);
    return [...head, { [x]: `อื่น ๆ (${sorted.length - topN})`, [y]: tailSum }];
}

/**
 * Render a chart using Chart.js. Destroys any previous chart on the same canvas.
 *
 * @param {string} canvasId
 * @param {Object} config - visualization config from the envelope
 *   (chart_type, x_col, y_col, series_col, title, x_label, y_label, top_n)
 * @param {Array<Object>} data - result rows
 * @param {Array<Object>} [columns] - envelope column metadata (for number formatting)
 */
export function renderChart(canvasId, config, data, columns) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element not found: ${canvasId}`);
        return;
    }
    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');
    const isPie = config.chart_type === 'pie';
    const isScatter = config.chart_type === 'scatter';

    const rootStyles = getComputedStyle(document.documentElement);
    const axisTextColor = rootStyles.getPropertyValue('--color-text-muted').trim();
    const gridColor = rootStyles.getPropertyValue('--color-border').trim();

    let datasets = [];
    let labels = [];

    if (isScatter) {
        // Chart.js scatter needs {x, y} points and two numeric axes.
        const nums = numericColumns(columns);
        const xCol = nums.includes(config.x_col) ? config.x_col : (nums[0] || config.x_col);
        const yCol = nums.includes(config.y_col) ? config.y_col : (nums[1] || nums[0] || config.y_col);
        config = { ...config, x_col: xCol, y_col: yCol, x_label: xCol, y_label: yCol };
        datasets.push({
            label: `${xCol} × ${yCol}`,
            data: data.map((row) => ({ x: Number(row[xCol]), y: Number(row[yCol]) })),
            backgroundColor: CHART_COLORS[0].bg,
            borderColor: CHART_COLORS[0].border,
        });
    } else if (config.series_col) {
        // Multi-series: one dataset per distinct series value.
        const seriesValues = [...new Set(data.map((r) => r[config.series_col]))].sort();
        const xValues = [...new Set(data.map((r) => r[config.x_col]))].sort((a, b) => a - b);
        labels = xValues;
        seriesValues.forEach((seriesVal, idx) => {
            const rows = data.filter((r) => r[config.series_col] === seriesVal);
            const map = {};
            rows.forEach((r) => { map[r[config.x_col]] = r[config.y_col]; });
            const color = CHART_COLORS[idx % CHART_COLORS.length];
            datasets.push({
                label: `${config.series_col}: ${seriesVal}`,
                data: xValues.map((x) => (map[x] !== undefined ? map[x] : null)),
                backgroundColor: color.bg,
                borderColor: color.border,
                borderWidth: 2,
                tension: 0.3,
                fill: false,
            });
        });
    } else {
        const rows = applyTopN(config, data);
        labels = rows.map((r) => r[config.x_col]);
        datasets.push({
            label: config.y_label || config.y_col,
            data: rows.map((r) => r[config.y_col]),
            backgroundColor: isPie ? PIE_COLORS : CHART_COLORS[0].bg,
            borderColor: isPie ? PIE_COLORS : CHART_COLORS[0].border,
            borderWidth: 1,
        });
    }

    const chartTypeMap = { bar: 'bar', column: 'bar', line: 'line', scatter: 'scatter', pie: 'pie' };
    const yType = semanticTypeOf(columns, config.y_col);
    const fmtY = (v) => formatAxisValue(v, yType);

    const chart = new Chart(ctx, {
        type: chartTypeMap[config.chart_type] || 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: isPie,
            plugins: {
                title: {
                    display: !!config.title,
                    text: config.title,
                    color: axisTextColor,
                },
                legend: {
                    position: isPie ? 'right' : 'top',
                    labels: { color: axisTextColor },
                    display: isPie || !!config.series_col,
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const base = context.dataset.label ? `${context.dataset.label}: ` : '';
                            if (isPie) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((context.parsed / total) * 100).toFixed(1);
                                return `${base}${fmtY(context.parsed)} (${pct}%)`;
                            }
                            if (isScatter) {
                                return `${base}(${fmtY(context.parsed.x)}, ${fmtY(context.parsed.y)})`;
                            }
                            return `${base}${fmtY(context.parsed.y)}`;
                        },
                    },
                },
            },
            scales: isPie ? {} : {
                x: {
                    title: { display: !!config.x_label, text: config.x_label, color: axisTextColor },
                    ticks: { color: axisTextColor },
                    grid: { color: gridColor },
                },
                y: {
                    title: { display: !!config.y_label, text: config.y_label, color: axisTextColor },
                    ticks: { color: axisTextColor, callback: (v) => fmtY(v) },
                    grid: { color: gridColor },
                },
            },
        },
    });

    _charts.set(canvasId, chart);
}
