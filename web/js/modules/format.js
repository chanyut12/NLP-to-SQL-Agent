/**
 * Value formatting driven by the envelope's `semantic_type` (see docs/API.md).
 * Pure functions — no DOM.
 */

const NF0 = new Intl.NumberFormat('th-TH');
const NF2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 });

/**
 * Format one cell for display.
 * @param {*} value
 * @param {string} semanticType - count|number|percent|gpa|date|id|category|name|text
 * @returns {string}
 */
export function formatValue(value, semanticType) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    switch (semanticType) {
        case 'count':   return Number.isFinite(n) ? NF0.format(n) : String(value);
        case 'number':  return Number.isFinite(n) ? NF2.format(n) : String(value);
        case 'percent': return Number.isFinite(n) ? `${n.toFixed(1)}%` : String(value);
        case 'gpa':     return Number.isFinite(n) ? n.toFixed(2) : String(value);
        case 'date':    return String(value).slice(0, 10);
        case 'id':      return String(value);            // never a thousands separator
        default:        return String(value);
    }
}

/** A numeric column that isn't an identifier — right-align it. */
export function isRightAligned(col) {
    return !!col.numeric && col.semantic_type !== 'id';
}

/** `attendance_rate_percent` -> `attendance rate percent`. */
export function humanizeHeader(name) {
    return String(name).replace(/_/g, ' ');
}

/** Axis / tooltip number formatter for charts. */
export function formatAxisValue(value, semanticType) {
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    if (semanticType === 'percent') return `${NF2.format(n)}%`;
    return NF2.format(n);
}

export function toCSV(rows) {
    if (!rows || !rows.length) return '';
    const headers = Object.keys(rows[0]);
    const esc = (v) => {
        if (v === null || v === undefined) return '';
        const s = String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return [headers.join(','), ...rows.map((r) => headers.map((h) => esc(r[h])).join(','))].join('\n');
}

export function toMarkdown(rows) {
    if (!rows || !rows.length) return '';
    const headers = Object.keys(rows[0]);
    const esc = (v) => (v === null || v === undefined ? '' : String(v).replace(/\|/g, '\\|'));
    const row = (cells) => `| ${cells.join(' | ')} |`;
    return [
        row(headers),
        row(headers.map(() => '---')),
        ...rows.map((r) => row(headers.map((h) => esc(r[h])))),
    ].join('\n');
}
