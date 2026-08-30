/**
 * Chart module for Thai NLP-to-SQL Agent
 * Handles Chart.js visualization rendering
 */

import { CHART_COLORS, PIE_COLORS } from './config.js';

/**
 * Render a chart using Chart.js
 * Supports single-series and multi-series modes with automatic layout.
 *
 * @param {string} canvasId - Canvas element ID to render into
 * @param {Object} config - Visualization configuration from backend
 * @param {string} config.chart_type - Chart type: 'bar', 'column', 'line', 'scatter', or 'pie'
 * @param {string} config.x_col - Column name for X-axis labels
 * @param {string} config.y_col - Column name for Y-axis values
 * @param {string} [config.series_col] - Column name for multi-series grouping
 * @param {Array<Object>} data - Array of data row objects from query result
 * @throws {Error} If Chart.js is not loaded (Chart global undefined)
 * @example
 * renderChart('chart-abc123', {
 *   chart_type: 'bar',
 *   x_col: 'department',
 *   y_col: 'total_sales',
 *   series_col: 'year'
 * }, queryData);
 */
export function renderChart(canvasId, config, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`Canvas element not found: ${canvasId}`);
        return;
    }

    const ctx = canvas.getContext('2d');
    const isPie = config.chart_type === 'pie';

    // Read theme tokens so axis/legend text and gridlines track the active light/dark theme
    const rootStyles = getComputedStyle(document.documentElement);
    const axisTextColor = rootStyles.getPropertyValue('--color-text-muted').trim();
    const gridColor = rootStyles.getPropertyValue('--color-border').trim();

    let datasets = [];
    let labels = [];

    // Check if multi-series mode
    if (config.series_col && config.chart_type !== 'pie' && config.chart_type !== 'scatter') {
        // Multi-series mode: Group data by series_col
        const seriesValues = [...new Set(data.map(row => row[config.series_col]))].sort();
        const xValues = [...new Set(data.map(row => row[config.x_col]))].sort((a, b) => a - b);
        labels = xValues;

        seriesValues.forEach((seriesVal, idx) => {
            const seriesData = data.filter(row => row[config.series_col] === seriesVal);
            const colorIdx = idx % CHART_COLORS.length;

            // Create a map for quick lookup
            const dataMap = {};
            seriesData.forEach(row => {
                dataMap[row[config.x_col]] = row[config.y_col];
            });

            // Build values array aligned with labels
            const values = xValues.map(x => dataMap[x] !== undefined ? dataMap[x] : null);

            datasets.push({
                label: `${config.series_col}: ${seriesVal}`,
                data: values,
                backgroundColor: CHART_COLORS[colorIdx].bg,
                borderColor: CHART_COLORS[colorIdx].border,
                borderWidth: 2,
                tension: 0.3,  // Smooth lines
                fill: false
            });
        });

    } else {
        // Single-series mode (original behavior)
        labels = data.map(row => row[config.x_col]);
        const values = data.map(row => row[config.y_col]);

        const bgColors = isPie ? PIE_COLORS : CHART_COLORS[0].bg;
        const borderColors = isPie ? PIE_COLORS : CHART_COLORS[0].border;

        datasets.push({
            label: config.y_col,
            data: values,
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: 1
        });
    }

    // Map chart type to Chart.js type
    const chartTypeMap = {
        'bar': 'bar',
        'column': 'bar',
        'line': 'line',
        'scatter': 'scatter',
        'pie': 'pie'
    };

    new Chart(ctx, {
        type: chartTypeMap[config.chart_type] || 'bar',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: isPie,  // Pie needs aspect ratio to fit properly
            plugins: {
                legend: {
                    position: isPie ? 'right' : 'top',
                    labels: { color: axisTextColor }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y;
                            }

                            // Calculate % for Pie
                            if (config.chart_type === 'pie') {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const value = context.parsed;
                                const percent = ((value / total) * 100).toFixed(1) + "%";
                                label += ` (${percent})`;
                            }
                            return label;
                        }
                    }
                }
            },
            scales: config.chart_type !== 'pie' ? {
                x: {
                    ticks: { color: axisTextColor },
                    grid: { color: gridColor }
                },
                y: {
                    ticks: { color: axisTextColor },
                    grid: { color: gridColor }
                }
            } : {}
        }
    });
}
