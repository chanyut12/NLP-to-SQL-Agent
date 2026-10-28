/**
 * Chart module for Thai NLP-to-SQL Agent
 *
 * ECharts adapter for the service's visualization config: it maps the envelope's
 * `visualization` block onto an ECharts option, with every colour derived from
 * the page's CSS variables so light and dark both work without hard-coded
 * colours (ADR 0015).
 *
 * Chart kinds are keys: bar, bar_horizontal, bar_grouped, bar_stacked,
 * bar_stacked_100, line, area, combo, pie, scatter. The config also states the
 * intended series form and the sort order it assumes; the kind wins when both
 * are present.
 */

import { CATEGORICAL_COLORS } from './config.js';
import { formatAxisValue } from './format.js';

// chartId -> { instance, config, data, columns }, so a theme switch or a
// chart-type switch can rebuild on the same host without leaking instances.
const _charts = new Map();

// Axis labels longer than this are truncated; the tooltip carries the full text.
const MAX_LABEL_CHARS = 16;

// Value labels stop once a chart would carry more marks than this — they collide.
const MAX_VALUE_LABELS = 30;

const FONT = "'Anuphan', system-ui, sans-serif";

// Bar-family kinds whose key already names the form.
const SERIES_FORM_OF_KIND = {
    bar_grouped: 'grouped',
    bar_stacked: 'stacked',
    bar_stacked_100: 'stacked_100',
};

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
 * Only for single-series bars / pie, when the backend set `top_n`.
 */
function applyTopN(config, data) {
    const { top_n: topN, chart_type: type, x_col: x, y_col: y } = config;
    if (!topN || config.series_col) return data;
    if (!['bar', 'bar_horizontal', 'pie'].includes(type)) return data;
    if (data.length <= topN) return data;

    const sorted = [...data].sort((a, b) => (Number(b[y]) || 0) - (Number(a[y]) || 0));
    const head = sorted.slice(0, topN);
    const tailSum = sorted.slice(topN).reduce((s, r) => s + (Number(r[y]) || 0), 0);
    return [...head, { [x]: `อื่น ๆ (${sorted.length - topN})`, [y]: tailSum }];
}

/** Order rows the way the recommendation says it assumes (config.sort). */
function sortRows(rows, sort, xCol, yCol) {
    if (sort === 'value_desc') {
        return [...rows].sort((a, b) => (Number(b[yCol]) || 0) - (Number(a[yCol]) || 0));
    }
    if (sort === 'x_asc') {
        return [...rows].sort((a, b) => {
            const x = a[xCol];
            const y = b[xCol];
            if (typeof x === 'number' && typeof y === 'number') return x - y;
            return String(x).localeCompare(String(y), 'th');
        });
    }
    return rows;
}

/** Bar data carrying the theme's value ramp; the maximum takes the accent. */
function rampedBars(values, t) {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const maxIdx = values.indexOf(max);
    return values.map((v, i) => ({
        value: v,
        itemStyle: {
            // A lone measure gets intensity, not decoration: the ramp is item
            // opacity over the theme's series colour (ADR 0015).
            color: max > min && i === maxIdx ? t.accent : t.series,
            opacity: max === min ? 0.75 : 0.45 + 0.55 * ((v - min) / (max - min)),
        },
    }));
}

/**
 * Render a chart with ECharts into a sized host element, destroying any previous
 * instance on that host.
 *
 * @param {string} chartId - id of the host element the renderer fills
 * @param {Object} config - visualization config from the envelope
 *   (chart_type, x_col, y_col, series_col, y2_col, chart_form, sort, title,
 *    x_label, y_label, top_n)
 * @param {Array<Object>} data - result rows
 * @param {Array<Object>} [columns] - envelope column metadata (for number formatting)
 */
export function renderChart(chartId, config, data, columns) {
    const host = document.getElementById(chartId);
    if (!host) {
        // The card left the DOM (chat cleared, history rendered away). Forget the
        // entry so a theme switch does not keep re-rendering a chart nobody sees.
        _charts.delete(chartId);
        return;
    }
    if (typeof echarts === 'undefined') {
        console.error('ECharts is not loaded; chart not rendered.');
        return;
    }
    bindWindowResize();
    destroyChart(chartId);

    const t = readTheme();
    const kind = config.chart_type;
    // The kind names the form when it is a bar-family key; a plain bar key may
    // carry one instead (a Consumer can pick "stacked" with chart_type bar).
    // Forms are a bar concept — a line with a series role stays a line.
    const form = SERIES_FORM_OF_KIND[kind]
        || (kind === 'bar' ? config.chart_form : null)
        || null;
    const isCombo = kind === 'combo';
    const isScatter = kind === 'scatter';
    const isPie = kind === 'pie';
    const isLineish = kind === 'line' || kind === 'area';
    const isHorizontal = kind === 'bar_horizontal';

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
    const fmtPercent = (v) => `${Number(v).toFixed(0)}%`;
    // A 100% stack is normalized to shares of each x.
    const fmtStack = form === 'stacked_100' ? fmtPercent : fmtVal;

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

    let y2Formatter = null;

    if (isPie) {
        const rows = sortRows(applyTopN(config, data), config.sort, xCol, yCol);
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
        // Cartesian: the bar family, line/area, or the combo's dual axis.
        const seriesCol = isCombo ? null : config.series_col;
        const labels = [];
        const series = [];
        let showLabels = false;

        if (isCombo) {
            const rows = sortRows(data, config.sort, xCol, yCol);
            const y2Col = config.y2_col;
            const fmtY2 = (v) => formatAxisValue(v, semanticTypeOf(columns, y2Col));
            y2Formatter = fmtY2;
            labels.push(...rows.map((r) => r[xCol]));
            const values = rows.map((r) => Number(r[yCol]) || 0);
            const rates = rows.map((r) => (r[y2Col] === null || r[y2Col] === undefined
                ? null : Number(r[y2Col])));
            showLabels = values.length <= MAX_VALUE_LABELS;

            series.push({
                name: yLabel || yCol,
                type: 'bar',
                yAxisIndex: 0,
                data: rampedBars(values, t),
                barMaxWidth: 40,
                label: {
                    show: showLabels,
                    position: 'top',
                    color: t.muted,
                    fontFamily: FONT,
                    fontSize: 11,
                    formatter: (p) => fmtVal(p.value),
                },
            });
            series.push({
                name: String(y2Col || '').replace(/_/g, ' '),
                type: 'line',
                yAxisIndex: 1,
                data: rates,
                smooth: 0.3,
                symbol: 'circle',
                symbolSize: 7,
                showSymbol: true,
                lineStyle: { color: t.accent, width: 2.5 },
                itemStyle: { color: t.accent },
            });
            option.legend = {
                type: 'scroll',
                top: 0,
                icon: 'circle',
                itemWidth: 8,
                itemHeight: 8,
                textStyle: { color: t.muted, fontFamily: FONT },
            };
        } else if (seriesCol) {
            const seriesValues = [...new Set(data.map((r) => r[seriesCol]))];
            const xValues = [...new Set(data.map((r) => r[xCol]))];
            if (config.sort === 'x_asc') {
                xValues.sort((a, b) => (typeof a === 'number' && typeof b === 'number')
                    ? a - b
                    : String(a).localeCompare(String(b), 'th'));
            }
            labels.push(...xValues);
            const marks = xValues.length * seriesValues.length;
            // Stacked segments cannot carry readable labels; grouped bars can.
            showLabels = !isLineish && !form && marks <= MAX_VALUE_LABELS;

            const totals = new Map();
            if (form === 'stacked_100') {
                xValues.forEach((v) => {
                    const total = data
                        .filter((r) => r[xCol] === v)
                        .reduce((sum, r) => sum + (Number(r[yCol]) || 0), 0);
                    totals.set(v, total);
                });
            }

            seriesValues.forEach((seriesVal, idx) => {
                const colour = CATEGORICAL_COLORS[idx % CATEGORICAL_COLORS.length];
                const map = new Map(
                    data.filter((r) => r[seriesCol] === seriesVal)
                        .map((r) => [r[xCol], Number(r[yCol]) || 0]));
                const values = xValues.map((v) => {
                    if (!map.has(v)) return null;
                    const raw = map.get(v);
                    if (form !== 'stacked_100') return raw;
                    const total = totals.get(v) || 0;
                    return total ? (raw / total) * 100 : 0;
                });
                series.push({
                    name: `${seriesCol}: ${seriesVal}`,
                    type: isLineish ? 'line' : 'bar',
                    data: values,
                    // Only the stacked forms share a stack; grouped bars sit side by side.
                    stack: form === 'stacked' || form === 'stacked_100' ? 'total' : undefined,
                    itemStyle: { color: colour, borderRadius: isLineish || form ? 0 : 6 },
                    lineStyle: { color: colour, width: 2.5 },
                    barMaxWidth: 42,
                    smooth: isLineish ? 0.3 : false,
                    symbol: 'circle',
                    symbolSize: 6,
                    showSymbol: isLineish && xValues.length <= 30,
                    areaStyle: kind === 'area' ? { color: colour, opacity: 0.18 } : undefined,
                    // ECharts 5.6 drops an *inherited* line/area style when it
                    // re-enters emphasis on every hover move, leaving the line
                    // and fill blank. Restating them here keeps the chart drawn.
                    emphasis: isLineish ? {
                        itemStyle: { color: colour },
                        lineStyle: { color: colour, width: 2.5 },
                        areaStyle: kind === 'area' ? { color: colour, opacity: 0.18 } : undefined,
                    } : undefined,
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
            // Single series. Bars take the order the recommendation states (the
            // default is biggest first) and a value ramp with the maximum
            // highlighted; lines keep the SQL's order unless told otherwise.
            const rows = sortRows(applyTopN(config, data), config.sort, xCol, yCol);
            labels.push(...rows.map((r) => r[xCol]));
            const values = rows.map((r) => Number(r[yCol]) || 0);
            showLabels = !isLineish && values.length <= MAX_VALUE_LABELS;

            series.push({
                name: yLabel || yCol,
                type: isLineish ? 'line' : 'bar',
                data: isLineish ? values : rampedBars(values, t),
                itemStyle: isLineish ? { color: t.series } : { borderRadius: 6 },
                lineStyle: { color: t.series, width: 2.5 },
                barMaxWidth: 48,
                smooth: isLineish ? 0.3 : false,
                symbol: 'circle',
                symbolSize: 6,
                showSymbol: isLineish && values.length <= 30,
                areaStyle: kind === 'area' ? { color: t.fill } : undefined,
                // Same 5.6 emphasis reset as the multi-series branch above.
                emphasis: isLineish ? {
                    itemStyle: { color: t.series },
                    lineStyle: { color: t.series, width: 2.5 },
                    areaStyle: kind === 'area' ? { color: t.fill } : undefined,
                } : undefined,
            });
        }

        const horizontal = isHorizontal && !seriesCol && !form;
        const rotate = !horizontal && labels.length > 8 ? 30 : 0;

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
            axisLabel: { color: t.muted, fontFamily: FONT, formatter: fmtStack },
            splitLine: { lineStyle: { color: t.grid } },
        };

        const valueLabel = {
            show: showLabels,
            position: horizontal ? 'right' : 'top',
            color: t.muted,
            fontFamily: FONT,
            fontSize: 11,
            formatter: (p) => fmtStack(p.value),
        };
        series.forEach((s) => { if (!s.label) s.label = valueLabel; });

        option.tooltip = {
            ...tooltipBase,
            trigger: 'axis',
            axisPointer: { type: kind === 'bar' || isCombo || form ? 'shadow' : 'line' },
            valueFormatter: (v) => (v === null || v === undefined ? '-' : fmtStack(v)),
        };
        option.grid = {
            left: 8,
            right: isCombo ? 44 : 20,
            top: option.legend ? 30 : 24,
            bottom: 4,
            containLabel: true,
        };
        option.xAxis = horizontal ? valueAxis : categoryAxis;
        option.yAxis = isCombo
            ? [valueAxis, {
                type: 'value',
                position: 'right',
                axisLine: { show: false },
                axisTick: { show: false },
                axisLabel: {
                    color: t.muted,
                    fontFamily: FONT,
                    formatter: (v) => (y2Formatter ? y2Formatter(v) : v),
                },
                splitLine: { show: false },
            }]
            : (horizontal ? categoryAxis : valueAxis);
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
