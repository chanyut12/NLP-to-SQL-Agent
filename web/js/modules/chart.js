/**
 * Chart module for Thai NLP-to-SQL Agent
 *
 * ECharts adapter for the service's visualization config: it maps the envelope's
 * `visualization` block onto an ECharts option, with every colour derived from
 * the page's CSS variables so light and dark both work without hard-coded
 * colours (ADR 0015).
 */

import { CATEGORICAL_COLORS } from './config.js';
import { formatAxisValue } from './format.js';

// chartId -> { instance, config, data, columns }, so a theme switch or a
// chart-type switch can rebuild on the same host without leaking instances.
const _charts = new Map();

// Category axis goes horizontal past this many bars (long Thai labels read better).
const HORIZONTAL_BAR_THRESHOLD = 8;

// Axis labels longer than this are truncated; the tooltip carries the full text.
const MAX_LABEL_CHARS = 16;

// Value labels stop once a chart would carry more marks than this — they collide.
const MAX_VALUE_LABELS = 30;

const FONT = "'Anuphan', system-ui, sans-serif";

let _resizeBound = false;
function bindWindowResize() {
    if (_resizeBound) return;
    window.addEventListener('resize', () => {
        _charts.forEach((entry) => entry.instance.resize());
    });
    _resizeBound = true;
}

/**
 * Resolve a CSS color expression (including `var(...)` and `color-mix(...)`) to a
 * concrete `rgb()/rgba()` string via a hidden probe. `getPropertyValue` alone
 * returns custom properties unresolved, and the canvas backend may not
 * understand `color-mix()`.
 */
function resolveColor(expr) {
    const probe = document.createElement('span');
    probe.style.cssText = `color:${expr};position:absolute;left:-9999px`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
}

/** Re-read every themed token at render time, so a theme switch re-colours. */
function readTheme() {
    return {
        text: resolveColor('var(--color-text)'),
        muted: resolveColor('var(--color-text-muted)'),
        grid: resolveColor('var(--chart-grid)'),
        border: resolveColor('var(--color-border)'),
        series: resolveColor('var(--chart-series-1)'),
        fill: resolveColor('var(--chart-fill-1)'),
        surface: resolveColor('var(--color-surface)'),
        surfaceAlt: resolveColor('var(--color-surface-alt)'),
        accent: resolveColor('var(--color-accent)'),
    };
}

/** Truncate a long Thai category label; hover still shows the full text. */
function truncateLabel(value) {
    const text = String(value === null || value === undefined ? '' : value);
    return text.length > MAX_LABEL_CHARS ? `${text.slice(0, MAX_LABEL_CHARS - 1)}…` : text;
}

/** Tear down the chart bound to a host element, if any. */
function destroyChart(chartId) {
    const tracked = _charts.get(chartId);
    if (tracked) {
        tracked.instance.dispose();
        _charts.delete(chartId);
    }
    // Belt-and-suspenders: if a previous init threw part-way through, ECharts
    // may still hold an instance on this host that we never recorded.
    const host = document.getElementById(chartId);
    const orphan = (typeof echarts !== 'undefined' && host) ? echarts.getInstanceByDom(host) : null;
    if (orphan) orphan.dispose();
}

/** Re-measure a chart after its container was hidden and shown again. */
export function resizeChart(chartId) {
    const entry = _charts.get(chartId);
    if (entry) entry.instance.resize();
}

/** Rebuild every live chart — called on a theme switch, which changes the tokens. */
export function refreshCharts() {
    // Snapshot the entries first: renderChart deletes and re-adds its key, and
    // Map.forEach would visit re-added entries again (endless re-render loop).
    [..._charts.entries()].forEach(([chartId, entry]) => {
        renderChart(chartId, entry.config, entry.data, entry.columns);
    });
}

/** PNG data URL of a rendered chart, for the result card's download button. */
export function chartPng(chartId) {
    const entry = _charts.get(chartId);
    if (!entry) return null;
    return entry.instance.getDataURL({
        type: 'png',
        pixelRatio: 2,
        backgroundColor: readTheme().surface,
    });
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
 * Render a chart with ECharts into a sized host element, destroying any previous
 * instance on that host.
 *
 * @param {string} chartId - id of the host element the renderer fills
 * @param {Object} config - visualization config from the envelope
 *   (chart_type, x_col, y_col, series_col, title, x_label, y_label, top_n)
 * @param {Array<Object>} data - result rows
 * @param {Array<Object>} [columns] - envelope column metadata (for number formatting)
 */
export function renderChart(chartId, config, data, columns) {
    const host = document.getElementById(chartId);
    if (!host) {
        console.error(`Chart host not found: ${chartId}`);
        return;
    }
    if (typeof echarts === 'undefined') {
        console.error('ECharts is not loaded; chart not rendered.');
        return;
    }
    bindWindowResize();
    destroyChart(chartId);

    const t = readTheme();
    const kind = config.chart_type;                 // bar | line | area | pie | scatter
    const isScatter = kind === 'scatter';
    const isPie = kind === 'pie';
    const isLineish = kind === 'line' || kind === 'area';

    let xCol = config.x_col;
    let yCol = config.y_col;
    let xLabel = config.x_label;
    let yLabel = config.y_label;

    if (isScatter) {
        // Scatter needs two numeric axes; fall back to the numeric columns present.
        const nums = numericColumns(columns);
        xCol = nums.includes(xCol) ? xCol : (nums[0] || xCol);
        yCol = nums.includes(yCol) ? yCol : (nums[1] || nums[0] || yCol);
        xLabel = xLabel || xCol;
        yLabel = yLabel || yCol;
    }

    const yType = semanticTypeOf(columns, yCol);
    const fmtVal = (v) => formatAxisValue(v, yType);
    const fmtX = (v) => formatAxisValue(v, semanticTypeOf(columns, xCol));

    const tooltipBase = {
        backgroundColor: t.surfaceAlt,
        borderColor: t.grid,
        borderWidth: 1,
        textStyle: { color: t.text, fontFamily: FONT },
        extraCssText: 'border-radius:8px;box-shadow:0 2px 8px rgba(0, 0, 0, 0.12)',
    };

    const option = {
        textStyle: { fontFamily: FONT },
        animationDuration: 300,
        color: CATEGORICAL_COLORS,
    };

    if (isPie) {
        const rows = applyTopN(config, data);
        option.tooltip = {
            ...tooltipBase,
            trigger: 'item',
            formatter: (p) => `${p.name}: ${fmtVal(p.value)} (${p.percent}%)`,
        };
        option.legend = {
            type: 'scroll',
            orient: 'vertical',
            right: 8,
            top: 'middle',
            icon: 'circle',
            itemWidth: 8,
            itemHeight: 8,
            textStyle: { color: t.muted, fontFamily: FONT },
        };
        option.series = [{
            type: 'pie',
            radius: ['45%', '70%'],
            center: ['38%', '52%'],
            data: rows.map((r) => ({ name: String(r[xCol]), value: Number(r[yCol]) || 0 })),
            itemStyle: { borderColor: t.surface, borderWidth: 2 },
            label: {
                color: t.muted,
                fontFamily: FONT,
                formatter: '{b}\n{d}%',
            },
            labelLayout: { hideOverlap: true },
            labelLine: { lineStyle: { color: t.grid } },
            emphasis: { scale: true, scaleSize: 6 },
        }];
    } else if (isScatter) {
        const points = data.map((r) => [Number(r[xCol]), Number(r[yCol])]);
        option.tooltip = {
            ...tooltipBase,
            trigger: 'item',
            formatter: (p) => `(${fmtX(p.value[0])}, ${fmtVal(p.value[1])})`,
        };
        option.grid = { left: 8, right: 20, top: 24, bottom: 4, containLabel: true };
        const axis = (name, fmt) => ({
            type: 'value',
            name,
            nameTextStyle: { color: t.muted, fontFamily: FONT },
            axisLine: { lineStyle: { color: t.border } },
            axisTick: { show: false },
            axisLabel: { color: t.muted, fontFamily: FONT, formatter: fmt },
            splitLine: { lineStyle: { color: t.grid } },
        });
        option.xAxis = axis(xLabel, fmtX);
        option.yAxis = axis(yLabel, fmtVal);
        option.series = [{
            type: 'scatter',
            data: points,
            symbolSize: 9,
            itemStyle: { color: t.series, opacity: 0.85 },
            emphasis: { itemStyle: { color: t.accent } },
        }];
    } else {
        // Cartesian: single- or multi-series bar / line / area.
        const seriesCol = config.series_col;
        const labels = [];
        const series = [];
        let showLabels = false;

        if (seriesCol) {
            const seriesValues = [...new Set(data.map((r) => r[seriesCol]))].sort();
            const xValues = [...new Set(data.map((r) => r[xCol]))];
            // A numeric x (years, months) reads better ascending; anything else
            // keeps the row order the recommendation's SQL already chose.
            if (xValues.every((v) => typeof v === 'number')) xValues.sort((a, b) => a - b);
            labels.push(...xValues);
            const marks = xValues.length * seriesValues.length;
            showLabels = !isLineish && marks <= MAX_VALUE_LABELS;
            seriesValues.forEach((seriesVal, idx) => {
                const colour = CATEGORICAL_COLORS[idx % CATEGORICAL_COLORS.length];
                const map = new Map(
                    data.filter((r) => r[seriesCol] === seriesVal).map((r) => [r[xCol], r[yCol]]));
                series.push({
                    name: `${seriesCol}: ${seriesVal}`,
                    type: isLineish ? 'line' : 'bar',
                    data: xValues.map((v) => (map.has(v) ? Number(map.get(v)) : null)),
                    itemStyle: { color: colour, borderRadius: isLineish ? 0 : 6 },
                    lineStyle: { color: colour, width: 2.5 },
                    barMaxWidth: 42,
                    smooth: isLineish ? 0.3 : false,
                    symbol: 'circle',
                    symbolSize: 6,
                    showSymbol: isLineish && xValues.length <= 30,
                    areaStyle: kind === 'area' ? { color: colour, opacity: 0.18 } : undefined,
                });
            });
            option.legend = {
                type: 'scroll',
                top: 0,
                icon: 'circle',
                itemWidth: 8,
                itemHeight: 8,
                textStyle: { color: t.muted, fontFamily: FONT },
            };
        } else {
            // Single series. Bars sort by value (biggest first) and take a value
            // ramp with the maximum highlighted; lines keep the SQL's order.
            let rows = applyTopN(config, data);
            if (!isLineish) {
                rows = [...rows].sort((a, b) => (Number(b[yCol]) || 0) - (Number(a[yCol]) || 0));
            }
            labels.push(...rows.map((r) => r[xCol]));
            const values = rows.map((r) => Number(r[yCol]) || 0);
            showLabels = !isLineish && values.length <= MAX_VALUE_LABELS;

            let barData = values;
            if (!isLineish) {
                const min = Math.min(...values);
                const max = Math.max(...values);
                const maxIdx = values.indexOf(max);
                barData = values.map((v, i) => ({
                    value: v,
                    itemStyle: {
                        // A lone measure gets intensity, not decoration: the ramp
                        // is item opacity over the theme's series colour, and the
                        // maximum carries the accent (ADR 0015).
                        color: max > min && i === maxIdx ? t.accent : t.series,
                        opacity: max === min ? 0.75 : 0.45 + 0.55 * ((v - min) / (max - min)),
                    },
                }));
            }
            series.push({
                name: config.y_label || yCol,
                type: isLineish ? 'line' : 'bar',
                data: barData,
                itemStyle: isLineish ? { color: t.series } : { borderRadius: 6 },
                lineStyle: { color: t.series, width: 2.5 },
                barMaxWidth: 48,
                smooth: isLineish ? 0.3 : false,
                symbol: 'circle',
                symbolSize: 6,
                showSymbol: isLineish && values.length <= 30,
                areaStyle: kind === 'area' ? { color: t.fill } : undefined,
            });
        }

        const horizontal = kind === 'bar' && !seriesCol && labels.length > HORIZONTAL_BAR_THRESHOLD;
        const rotate = !horizontal && kind === 'bar' && labels.length > 8 ? 30 : 0;

        const categoryAxis = {
            type: 'category',
            data: labels,
            axisLine: { lineStyle: { color: t.border } },
            axisTick: { show: false },
            axisLabel: {
                color: t.muted,
                fontFamily: FONT,
                interval: 0,
                rotate,
                formatter: truncateLabel,
            },
            splitLine: { show: false },
            ...(horizontal ? { inverse: true } : {}),
        };
        const valueAxis = {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: t.muted, fontFamily: FONT, formatter: fmtVal },
            splitLine: { lineStyle: { color: t.grid } },
        };

        const valueLabel = {
            show: showLabels,
            position: horizontal ? 'right' : 'top',
            color: t.muted,
            fontFamily: FONT,
            fontSize: 11,
            formatter: (p) => fmtVal(p.value),
        };
        series.forEach((s) => { s.label = valueLabel; });

        option.tooltip = {
            ...tooltipBase,
            trigger: 'axis',
            axisPointer: { type: kind === 'bar' ? 'shadow' : 'line' },
            valueFormatter: (v) => (v === null || v === undefined ? '-' : fmtVal(v)),
        };
        option.grid = { left: 8, right: 20, top: option.legend ? 30 : 24, bottom: 4, containLabel: true };
        option.xAxis = horizontal ? valueAxis : categoryAxis;
        option.yAxis = horizontal ? categoryAxis : valueAxis;
        option.series = series;
    }

    try {
        const instance = echarts.init(host, null, { renderer: 'canvas' });
        instance.setOption(option);
        _charts.set(chartId, {
            instance,
            // Keep the effective config (the scatter axis fix-ups included) so a
            // theme switch rebuilds exactly what is on screen.
            config: { ...config, x_col: xCol, y_col: yCol, x_label: xLabel, y_label: yLabel },
            data,
            columns,
        });
    } catch (e) {
        // Leave the host clean so the next chart-type switch can retry.
        destroyChart(chartId);
        console.error('Chart render failed:', e);
    }
}
