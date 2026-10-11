/**
 * Chart module for Thai NLP-to-SQL Agent
 * Handles Chart.js visualization rendering
 */

import { CATEGORICAL_COLORS } from './config.js';
import { formatAxisValue } from './format.js';

// canvasId -> Chart instance, so a re-render (chart-type switch) destroys the old one.
const _charts = new Map();

// Category axis goes horizontal past this many bars (long Thai labels read better).
const HORIZONTAL_BAR_THRESHOLD = 8;

let _defaultsApplied = false;
function applyChartDefaults() {
    if (_defaultsApplied || typeof Chart === 'undefined' || !Chart.defaults) return;
    Chart.defaults.font.family = "'Anuphan', system-ui, sans-serif";
    _defaultsApplied = true;
}

/**
 * Resolve a CSS color expression (including `var(...)` and `color-mix(...)`) to a
 * concrete `rgb()/rgba()` string via a hidden probe. `getPropertyValue` alone
 * returns custom properties unresolved, and Chart.js draws to a canvas that may
 * not understand `color-mix()`.
 */
function resolveColor(expr) {
    const probe = document.createElement('span');
    probe.style.cssText = `color:${expr};position:absolute;left:-9999px`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
}

/** Tear down the chart bound to a canvas, if any. */
function destroyChart(canvasId) {
    const tracked = _charts.get(canvasId);
    if (tracked) {
        tracked.destroy();
        _charts.delete(canvasId);
    }
    // Belt-and-suspenders: if a previous `new Chart()` threw part-way through
    // init, Chart.js may still hold an instance on this canvas that we never
    // recorded. Reusing the canvas would then throw "Canvas is already in use".
    const orphan = (typeof Chart !== 'undefined' && Chart.getChart)
        ? Chart.getChart(canvasId)
        : null;
    if (orphan) orphan.destroy();
}

/** Re-measure a chart after its container was hidden and shown again. */
export function resizeChart(canvasId) {
    const chart = _charts.get(canvasId);
    if (chart) chart.resize();
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
    applyChartDefaults();
    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');
    if (!ctx) {
        console.error(`Could not get a 2d context for ${canvasId}`);
        return;
    }
    const isPie = config.chart_type === 'pie';
    const isScatter = config.chart_type === 'scatter';
    const isLine = config.chart_type === 'line';

    const tick = resolveColor('var(--color-text-muted)');
    const grid = resolveColor('var(--chart-grid)');
    const series1 = resolveColor('var(--chart-series-1)');
    const fill1 = resolveColor('var(--chart-fill-1)');
    const surface = resolveColor('var(--color-surface)');
    const surfaceAlt = resolveColor('var(--color-surface-alt)');
    const textColor = resolveColor('var(--color-text)');

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
            backgroundColor: series1,
            borderColor: series1,
            pointRadius: 4,
            pointHoverRadius: 6,
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
            const color = CATEGORICAL_COLORS[idx % CATEGORICAL_COLORS.length];
            datasets.push({
                label: `${config.series_col}: ${seriesVal}`,
                data: xValues.map((x) => (map[x] !== undefined ? map[x] : null)),
                backgroundColor: color,
                borderColor: color,
                borderWidth: 2,
                borderRadius: isLine ? 0 : 6,
                maxBarThickness: 48,
                tension: 0.35,
                pointRadius: xValues.length <= 30 ? 3 : 0,
                pointHoverRadius: 6,
                fill: false,
            });
        });
    } else {
        const rows = applyTopN(config, data);
        labels = rows.map((r) => r[config.x_col]);
        const values = rows.map((r) => r[config.y_col]);
        if (isPie) {
            datasets.push({
                data: values,
                backgroundColor: CATEGORICAL_COLORS,
                borderColor: surface,
                borderWidth: 2,
            });
        } else if (isLine) {
            datasets.push({
                label: config.y_label || config.y_col,
                data: values,
                borderColor: series1,
                backgroundColor: fill1,
                borderWidth: 2.5,
                tension: 0.35,
                pointRadius: values.length <= 30 ? 3 : 0,
                pointHoverRadius: 6,
                pointBackgroundColor: series1,
                fill: true,
            });
        } else {
            datasets.push({
                label: config.y_label || config.y_col,
                data: values,
                backgroundColor: series1,
                borderRadius: 6,
                borderWidth: 0,
                maxBarThickness: 48,
            });
        }
    }

    const horizontal = config.chart_type === 'bar'
        && !config.series_col
        && labels.length > HORIZONTAL_BAR_THRESHOLD;
    const chartType = isPie ? 'doughnut' : (isScatter ? 'scatter' : (isLine ? 'line' : 'bar'));

    const yType = semanticTypeOf(columns, config.y_col);
    const fmtVal = (v) => formatAxisValue(v, yType);

    const catAxis = () => {
        const a = { grid: { display: false }, border: { display: false }, ticks: { color: tick } };
        if (config.x_label) a.title = { display: true, text: config.x_label, color: tick };
        return a;
    };
    const valAxis = () => {
        const a = {
            grid: { color: grid },
            border: { display: false },
            ticks: { color: tick, callback: (v) => fmtVal(v) },
        };
        if (config.y_label) a.title = { display: true, text: config.y_label, color: tick };
        return a;
    };

    let scales = {};
    if (isScatter) {
        const axis = (label) => ({
            grid: { color: grid },
            border: { display: false },
            ticks: { color: tick },
            ...(label ? { title: { display: true, text: label, color: tick } } : {}),
        });
        scales = { x: axis(config.x_label), y: axis(config.y_label) };
    } else if (!isPie) {
        scales = horizontal ? { x: valAxis(), y: catAxis() } : { x: catAxis(), y: valAxis() };
    }

    const spec = {
        type: chartType,
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: isPie,
            indexAxis: horizontal ? 'y' : 'x',
            ...(isPie ? { cutout: '55%' } : {}),
            layout: { padding: 4 },
            plugins: {
                legend: {
                    display: isPie || !!config.series_col,
                    position: isPie ? 'right' : 'top',
                    labels: { color: textColor, usePointStyle: true, boxWidth: 8, padding: 14 },
                },
                tooltip: {
                    usePointStyle: true,
                    padding: 10,
                    cornerRadius: 8,
                    backgroundColor: surfaceAlt || 'rgba(0, 0, 0, 0.8)',
                    titleColor: textColor,
                    bodyColor: textColor,
                    borderColor: grid,
                    borderWidth: 1,
                    callbacks: {
                        label(context) {
                            const base = context.dataset.label ? `${context.dataset.label}: ` : '';
                            if (isPie) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((context.parsed / total) * 100).toFixed(1);
                                return `${base}${fmtVal(context.parsed)} (${pct}%)`;
                            }
                            if (isScatter) {
                                return `${base}(${fmtVal(context.parsed.x)}, ${fmtVal(context.parsed.y)})`;
                            }
                            return `${base}${fmtVal(horizontal ? context.parsed.x : context.parsed.y)}`;
                        },
                    },
                },
            },
            scales,
        },
    };

    try {
        _charts.set(canvasId, new Chart(ctx, spec));
    } catch (e) {
        // Leave the canvas clean so the next chart-type switch can retry.
        destroyChart(canvasId);
        console.error('Chart render failed:', e);
    }
}
