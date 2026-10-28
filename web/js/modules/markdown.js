/**
 * Minimal, dependency-free Markdown for chat prose (the agent's Thai summary,
 * clarifications and refusals). Covers what an answer actually uses: paragraphs,
 * headings, bullet/numbered lists, bold/italic/strikethrough, inline code,
 * fenced code blocks, blockquotes and links. Everything is escaped first, so
 * the result is safe to hand to `appendMessage` as HTML.
 *
 * Block output is joined without newlines: the chat bubble keeps
 * `white-space: pre-wrap` for plain-text messages, and stray newlines between
 * tags would be rendered as blank lines there.
 */

import { sanitize } from './utils.js';

/**
 * Render one line of inline Markdown. Code spans are pulled out first so their
 * contents are not treated as emphasis.
 * @param {string} text - raw (unescaped) inline Markdown
 * @returns {string} HTML
 */
function inline(text) {
    const codes = [];
    let s = text.replace(/`([^`]+)`/g, (_, code) => {
        codes.push(code);
        return `\u0000${codes.length - 1}\u0000`;
    });

    s = sanitize(s)
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
        .replace(/~~([^~]+)~~/g, '<del>$1</del>')
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${sanitize(codes[Number(i)])}</code>`);
}

/**
 * Render a Markdown string to HTML.
 * @param {string} text
 * @returns {string} HTML (empty string for null/undefined)
 */
export function renderMarkdown(text) {
    if (text === null || text === undefined) return '';
    const lines = String(text).replace(/\r\n?/g, '\n').trim().split('\n');
    const out = [];
    let para = [];

    const flush = () => {
        if (para.length) {
            out.push(`<p>${inline(para.join(' '))}</p>`);
            para = [];
        }
    };

    for (let i = 0; i < lines.length;) {
        const line = lines[i];

        // Fenced code block: ```lang ... ```
        const fence = line.match(/^\s*```\s*([\w+#.-]*)\s*$/);
        if (fence) {
            flush();
            const body = [];
            i++;
            while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
            i++; // closing fence
            const cls = fence[1] ? ` class="language-${sanitize(fence[1])}"` : '';
            out.push(`<pre><code${cls}>${sanitize(body.join('\n'))}</code></pre>`);
            continue;
        }

        if (!line.trim()) { flush(); i++; continue; }

        // Headings render two levels down: a chat bubble is not a document page.
        const heading = line.match(/^\s*(#{1,6})\s+(.*)$/);
        if (heading) {
            flush();
            const level = Math.min(heading[1].length + 2, 6);
            out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
            i++;
            continue;
        }

        if (/^\s*(?:-{3,}|\*{3,})\s*$/.test(line)) { flush(); out.push('<hr>'); i++; continue; }

        if (/^\s*[-*+]\s+/.test(line)) {
            flush();
            const items = [];
            while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                items.push(`<li>${inline(lines[i].replace(/^\s*[-*+]\s+/, ''))}</li>`);
                i++;
            }
            out.push(`<ul>${items.join('')}</ul>`);
            continue;
        }

        if (/^\s*\d+[.)]\s+/.test(line)) {
            flush();
            const items = [];
            while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
                items.push(`<li>${inline(lines[i].replace(/^\s*\d+[.)]\s+/, ''))}</li>`);
                i++;
            }
            out.push(`<ol>${items.join('')}</ol>`);
            continue;
        }

        if (/^\s*>\s?/.test(line)) {
            flush();
            const quoted = [];
            while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
                quoted.push(lines[i++].replace(/^\s*>\s?/, ''));
            }
            out.push(`<blockquote>${inline(quoted.join(' '))}</blockquote>`);
            continue;
        }

        para.push(line.trim());
        i++;
    }

    flush();
    return out.join('');
}
