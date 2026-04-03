"""Precise line-by-line style patching for report_unpacked/word/styles.xml"""

STYLES_PATH = "report_unpacked/word/styles.xml"

with open(STYLES_PATH, "r", encoding="ascii", errors="replace") as f:
    lines = f.readlines()

# Track which heading section we're in
current_heading = None
h1_rpr_count = 0
h2_rpr_count = 0
h3_rpr_count = 0

# State flags
in_heading1 = False
in_heading2 = False
in_heading3 = False
in_h1char = False
in_h2char = False
in_h3char = False
in_verbatim_char = False
in_source_code = False
in_table_style = False

changed_h1_color = False
changed_h2_color = False
changed_h3_color = False
changed_h1_font = False
changed_h2_font = False
changed_h1char_color = False
changed_h2char_color = False
changed_h1_sz = False
changed_h2_sz = False

new_lines = []
for i, line in enumerate(lines):
    # Track heading sections
    if 'w:styleId="Heading1"' in line and 'Char' not in line:
        in_heading1 = True; in_heading2 = False; in_heading3 = False
    elif 'w:styleId="Heading2"' in line and 'Char' not in line:
        in_heading1 = False; in_heading2 = True; in_heading3 = False
    elif 'w:styleId="Heading3"' in line and 'Char' not in line:
        in_heading1 = False; in_heading2 = False; in_heading3 = True
    elif 'w:styleId="Heading1Char"' in line:
        in_heading1 = False; in_h1char = True; in_h2char = False; in_h3char = False
    elif 'w:styleId="Heading2Char"' in line:
        in_h1char = False; in_h2char = True; in_h3char = False
    elif 'w:styleId="Heading3Char"' in line:
        in_h2char = False; in_h3char = True
    elif 'w:styleId="VerbatimChar"' in line:
        in_verbatim_char = True
        in_heading1 = False; in_heading2 = False; in_heading3 = False
        in_h1char = False; in_h2char = False; in_h3char = False
    elif 'w:styleId="SourceCode"' in line:
        in_source_code = True
        in_verbatim_char = False
    elif 'w:styleId="' in line:
        in_heading1 = False; in_heading2 = False; in_heading3 = False
        in_h1char = False; in_h2char = False; in_h3char = False
        in_verbatim_char = False; in_source_code = False

    modified = line

    # ── H1: color, font, size ────────────────────────────────────────────
    if in_heading1 and 'w:themeColor="accent1"' in line and 'val="0F4761"' in line and not changed_h1_color:
        modified = '      <w:color w:val="1F3864"/>\n'
        changed_h1_color = True

    elif in_heading1 and 'w:asciiTheme="majorHAnsi"' in line and not changed_h1_font:
        modified = '      <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n'
        changed_h1_font = True

    elif in_heading1 and '<w:sz w:val="40"/>' in line and not changed_h1_sz:
        modified = '      <w:sz w:val="44"/>\n'
        changed_h1_sz = True

    # ── H2: color, font ──────────────────────────────────────────────────
    elif in_heading2 and 'w:themeColor="accent1"' in line and 'val="0F4761"' in line and not changed_h2_color:
        modified = '      <w:color w:val="2563A8"/>\n'
        changed_h2_color = True

    elif in_heading2 and 'w:asciiTheme="majorHAnsi"' in line and not changed_h2_font:
        modified = '      <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n'
        changed_h2_font = True

    elif in_heading2 and '<w:sz w:val="32"/>' in line and not changed_h2_sz:
        modified = '      <w:sz w:val="32"/>\n'
        changed_h2_sz = True

    # ── H3: color ────────────────────────────────────────────────────────
    elif in_heading3 and 'w:themeColor="accent1"' in line and 'val="0F4761"' in line and not changed_h3_color:
        modified = '      <w:color w:val="1F6B9E"/>\n'
        changed_h3_color = True

    # ── H1Char: color, font ──────────────────────────────────────────────
    elif in_h1char and 'w:themeColor="accent1"' in line and 'val="0F4761"' in line and not changed_h1char_color:
        modified = '      <w:color w:val="1F3864"/>\n'
        changed_h1char_color = True

    elif in_h1char and 'w:asciiTheme="majorHAnsi"' in line:
        modified = '      <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n'

    # ── H2Char: color, font ──────────────────────────────────────────────
    elif in_h2char and 'w:themeColor="accent1"' in line and 'val="0F4761"' in line and not changed_h2char_color:
        modified = '      <w:color w:val="2563A8"/>\n'
        changed_h2char_color = True

    elif in_h2char and 'w:asciiTheme="majorHAnsi"' in line:
        modified = '      <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n'

    # ── VerbatimChar: Consolas + red color for inline code ───────────────
    elif in_verbatim_char and 'w:asciiTheme=' in line:
        modified = '      <w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Courier New"/>\n'

    elif in_verbatim_char and '<w:sz w:val=' in line:
        modified = '      <w:sz w:val="20"/>\n'

    # ── SourceCode block: Consolas ────────────────────────────────────────
    elif in_source_code and 'w:asciiTheme=' in line:
        modified = '      <w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Courier New"/>\n'

    new_lines.append(modified)

with open(STYLES_PATH, "w", encoding="ascii", errors="xmlcharrefreplace") as f:
    f.writelines(new_lines)

print(f"Done. H1 color changed: {changed_h1_color}, H2: {changed_h2_color}, H3: {changed_h3_color}")
print(f"H1 font changed: {changed_h1_font}, H2: {changed_h2_font}")
print(f"H1 size changed: {changed_h1_sz}")
