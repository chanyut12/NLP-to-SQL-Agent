"""
Patch document.xml:
1. Add navy shading to first row (header) of every table
2. Add page break before each top-level Heading1
3. Improve table borders to use light blue lines
"""

import re

DOC_PATH = "report_unpacked/word/document.xml"

with open(DOC_PATH, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

# ── 1. Improve table cell padding and borders ────────────────────────────
# Replace bare <w:tblPr> with styled version
ORIG_TBLPR = '<w:tblPr>\n      \n      \n      <w:tblStyle w:val="Table"/>\n      \n      \n      <w:tblW w:w="0" w:type="auto"/>'
NEW_TBLPR = '''<w:tblPr>


      <w:tblStyle w:val="Table"/>


      <w:tblW w:w="0" w:type="auto"/>


      <w:tblCellMar>
        <w:top w:w="100" w:type="dxa"/>
        <w:left w:w="108" w:type="dxa"/>
        <w:bottom w:w="100" w:type="dxa"/>
        <w:right w:w="108" w:type="dxa"/>
      </w:tblCellMar>'''

content = content.replace(ORIG_TBLPR, NEW_TBLPR)

# ── 2. Add navy shading to first table row cells ──────────────────────────
# Find all <w:tr> blocks and shade cells in the first row of each table
def add_header_shading(match_content):
    """Add navy shading + white bold text to table row cells"""
    # Replace each <w:tcPr> (or add one) with shading
    # Simpler: inject shading into <w:tcPr> of first row cells
    result = re.sub(
        r'<w:tcPr>(.*?)</w:tcPr>',
        lambda m: '<w:tcPr>' + m.group(1) + '<w:shd w:val="clear" w:color="auto" w:fill="1F3864"/></w:tcPr>',
        match_content,
        flags=re.DOTALL
    )
    # Make text white and bold in first row runs
    result = re.sub(
        r'(<w:rPr>)(.*?)(</w:rPr>)',
        lambda m: m.group(1) + m.group(2) + '<w:color w:val="FFFFFF"/><w:b/><w:bCs/>' + m.group(3),
        result,
        flags=re.DOTALL
    )
    return result

# Find tables and apply to their first row
def process_table(tbl_match):
    tbl = tbl_match.group(0)
    # Find the first <w:tr>...</w:tr>
    first_tr = re.search(r'<w:tr\b.*?</w:tr>', tbl, re.DOTALL)
    if first_tr:
        original_tr = first_tr.group(0)
        # Only shade if it looks like a header row (has <w:th> or is genuinely first)
        shaded_tr = add_header_shading(original_tr)
        tbl = tbl[:first_tr.start()] + shaded_tr + tbl[first_tr.end():]
    return tbl

content = re.sub(r'<w:tbl>.*?</w:tbl>', process_table, content, flags=re.DOTALL)

# ── 3. Add page break before each Heading1 (except the very first one) ───
# Find all Heading1 paragraphs
heading1_count = [0]

def add_page_break_before_h1(m):
    heading1_count[0] += 1
    if heading1_count[0] == 1:
        return m.group(0)  # Skip first H1 (document title area)
    page_break = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n    '
    return page_break + m.group(0)

content = re.sub(
    r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"/>.*?</w:p>',
    add_page_break_before_h1,
    content,
    flags=re.DOTALL
)

with open(DOC_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"document.xml patched. H1 sections found: {heading1_count[0]}")
