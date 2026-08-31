/**
 * Result card: a full-width panel below the chat bubble that shows one query's
 * output — a summary bar, a formatted table, and (when the service suggests one)
 * a chart, switchable by tab. Built from the /api/query envelope.
 */

import { appendMessage } from './ui.js';
import { renderChart } from './chart.js';
import {
    formatValue, isRightAligned, humanizeHeader, toCSV, toMarkdown,
} from './format.js';

let _seq = 0;

/**
 * Render one successful query result into the chat.
 * @param {Object} env - the /api/query response envelope (status === "ok")
 */
export function renderResult(env) {
    // 1. The generated SQL stays in a chat bubble.
    let sqlHtml = `<strong>Generated SQL:</strong><pre><code class="language-sql">${escapeHtml(env.sql)}</code></pre>`;
    if (env.retry_count > 0) {
        sqlHtml += `<br><small class="text-warning">แก้เองอัตโนมัติ ${env.retry_count} ครั้ง</small>`;
    }
    appendMessage(sqlHtml, false);

    // 2. The result card.
    const chatHistory = document.getElementById('chat-history');
    const card = document.createElement('div');
    card.className = 'result-card';
    const place = () => {
        chatHistory.appendChild(card);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    };

    const rows = env.rows || [];
    if (rows.length === 0) {
        card.innerHTML = '<p class="empty-state">ไม่พบข้อมูล (ผลลัพธ์ว่าง)</p>';
        return place();
    }

    card.appendChild(buildSummaryBar(env));

    if (env.summary && env.summary.single_value) {
        card.appendChild(buildBigNumber(env));
        return place();
    }

    const viz = env.visualization;
    const hasChart = viz && viz.chart_type !== 'none' && viz.chart_type !== 'table';

    const tablePane = document.createElement('div');
    tablePane.className = 'result-pane result-pane-table';
    tablePane.appendChild(buildTable(rows, env.columns));

    if (!hasChart) {
        card.appendChild(tablePane);
        return place();
    }

    const chartId = `chart-${++_seq}`;
    const chartPane = document.createElement('div');
    chartPane.className = 'result-pane result-pane-chart';
    chartPane.innerHTML = `<div class="chart-container"><canvas id="${chartId}"></canvas></div>`;

    if (viz.title) {
        const h4 = document.createElement('h4');
        h4.className = 'result-title';
        h4.textContent = viz.title;
        card.appendChild(h4);
    }
    card.appendChild(buildTabs(card, viz, chartId, rows, env.columns));
    if (viz.reason) {
        const reason = document.createElement('div');
        reason.className = 'result-reason';
        reason.textContent = `ℹ️ ${viz.reason}`;
        card.appendChild(reason);
    }
    card.appendChild(chartPane);
    card.appendChild(tablePane);

    tablePane.hidden = true;  // default view: chart
    place();
    renderChart(chartId, viz, rows, env.columns);
}

/* ---------- pieces ---------- */

function buildSummaryBar(env) {
    const bar = document.createElement('div');
    bar.className = 'result-summary';

    const parts = [`${env.row_count.toLocaleString('th-TH')} แถว`];
    const single = env.summary && env.summary.single_value;
    const aggs = (env.summary && env.summary.numeric_aggregates) || {};
    if (!single) {
        for (const [name, stats] of Object.entries(aggs)) {
            if (stats.sum !== undefined) parts.push(`Σ ${humanizeHeader(name)} ${stats.sum.toLocaleString('th-TH')}`);
            if (stats.mean !== undefined) parts.push(`เฉลี่ย ${stats.mean.toLocaleString('th-TH', { maximumFractionDigits: 2 })}`);
            break; // one column's worth is enough for a summary line
        }
    }
    if (env.truncated) parts.push('⚠️ แสดง 500 แถวแรก (ปรับคำถามให้แคบลง)');

    const text = document.createElement('span');
    text.className = 'result-summary-text';
    text.textContent = parts.join('  ·  ');
    bar.appendChild(text);

    const actions = document.createElement('div');
    actions.className = 'result-actions';
    actions.appendChild(copyButton('📋 CSV', () => toCSV(env.rows)));
    actions.appendChild(copyButton('📋 MD', () => toMarkdown(env.rows)));
    bar.appendChild(actions);

    return bar;
}

function buildBigNumber(env) {
    const box = document.createElement('div');
    box.className = 'result-bignum';
    const col = env.columns[0];
    const value = env.rows[0][col.name];
    box.innerHTML = `
        <span class="bignum-value">${escapeHtml(formatValue(value, col.semantic_type))}</span>
        <span class="bignum-label">${escapeHtml(humanizeHeader(col.name))}</span>`;
    return box;
}

function buildTabs(card, viz, chartId, rows, columns) {
    const tabs = document.createElement('div');
    tabs.className = 'result-tabs';

    const show = (pane) => {
        card.querySelector('.result-pane-chart').hidden = pane !== 'chart';
        card.querySelector('.result-pane-table').hidden = pane !== 'table';
        tabs.querySelectorAll('.result-tab').forEach((b) => {
            b.classList.toggle('active', b.dataset.pane === pane);
        });
    };

    ['chart', 'table'].forEach((pane) => {
        const btn = document.createElement('button');
        btn.className = `result-tab${pane === 'chart' ? ' active' : ''}`;
        btn.dataset.pane = pane;
        btn.textContent = pane === 'chart' ? 'กราฟ' : 'ตาราง';
        btn.addEventListener('click', () => show(pane));
        tabs.appendChild(btn);
    });

    const select = document.createElement('select');
    select.className = 'result-chart-type';
    const types = { bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie', scatter: 'Scatter' };
    const offered = new Set(['bar', 'line', 'pie', 'scatter', viz.chart_type]);
    for (const [value, label] of Object.entries(types)) {
        if (!offered.has(value)) continue;
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        if (value === viz.chart_type) opt.selected = true;
        select.appendChild(opt);
    }
    select.addEventListener('change', () => {
        renderChart(chartId, { ...viz, chart_type: select.value }, rows, columns);
        show('chart');
    });
    tabs.appendChild(select);

    tabs.appendChild(pngButton(chartId, viz.title));
    return tabs;
}

function buildTable(rows, columns) {
    const cols = columns && columns.length
        ? columns
        : Object.keys(rows[0]).map((name) => ({ name, numeric: false, semantic_type: 'text' }));

    const scroll = document.createElement('div');
    scroll.className = 'result-table-scroll';

    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');

    let sortState = { name: null, dir: 1 };
    const tbody = document.createElement('tbody');

    const paint = () => {
        tbody.replaceChildren();
        const view = [...rows];
        if (sortState.name) {
            const st = cols.find((c) => c.name === sortState.name);
            const numeric = st && st.numeric;
            view.sort((a, b) => {
                const x = a[sortState.name];
                const y = b[sortState.name];
                if (x === null || x === undefined) return 1;
                if (y === null || y === undefined) return -1;
                const cmp = numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y), 'th');
                return cmp * sortState.dir;
            });
        }
        for (const r of view) {
            const tr = document.createElement('tr');
            for (const c of cols) {
                const td = document.createElement('td');
                td.textContent = formatValue(r[c.name], c.semantic_type);
                if (isRightAligned(c)) td.className = 'num';
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
    };

    for (const c of cols) {
        const th = document.createElement('th');
        th.textContent = humanizeHeader(c.name);
        if (isRightAligned(c)) th.className = 'num';
        th.classList.add('sortable');
        th.addEventListener('click', () => {
            sortState = sortState.name === c.name
                ? { name: c.name, dir: -sortState.dir }
                : { name: c.name, dir: 1 };
            headRow.querySelectorAll('th').forEach((h) => h.removeAttribute('data-sort'));
            th.dataset.sort = sortState.dir === 1 ? 'asc' : 'desc';
            paint();
        });
        headRow.appendChild(th);
    }

    thead.appendChild(headRow);
    table.appendChild(thead);
    table.appendChild(tbody);
    scroll.appendChild(table);
    paint();
    return scroll;
}

/* ---------- small controls ---------- */

function copyButton(label, getText) {
    const btn = document.createElement('button');
    btn.className = 'result-mini-btn';
    btn.textContent = label;
    btn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(getText());
            const original = btn.textContent;
            btn.textContent = '✓ คัดลอกแล้ว';
            setTimeout(() => { btn.textContent = original; }, 1500);
        } catch {
            btn.textContent = '✗ คัดลอกไม่ได้';
        }
    });
    return btn;
}

function pngButton(chartId, title) {
    const btn = document.createElement('button');
    btn.className = 'result-mini-btn';
    btn.textContent = '⬇ PNG';
    btn.addEventListener('click', () => {
        const canvas = document.getElementById(chartId);
        if (!canvas) return;
        const a = document.createElement('a');
        a.href = canvas.toDataURL('image/png');
        a.download = `${(title || 'chart').slice(0, 40)}.png`;
        a.click();
    });
    return btn;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text === null || text === undefined ? '' : String(text);
    return div.innerHTML;
}
