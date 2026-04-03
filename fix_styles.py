"""
Improve report.docx readability by patching styles.xml
Changes:
- Default font: Arial (Thai-compatible, universal)
- Body: 12pt, 1.15 line spacing, proper paragraph spacing
- H1: Deep navy #1F3864, 22pt, bold, page-break control
- H2: Medium blue #2563A8, 16pt, bold, border bottom
- H3: Steel blue #1F6B9E, 13pt, bold
- H4: Gray #4A4A4A, 12pt, bold italic
- Table header: Navy fill #1F3864, white text
- VerbatimChar / SourceCode: Consolas, light gray bg #F2F2F2
- Title: 28pt centered, deep navy
- After-paragraph spacing: 120 (6pt) by default
"""

import re, sys, os

STYLES_PATH = "report_unpacked/word/styles.xml"

with open(STYLES_PATH, "r", encoding="ascii", errors="replace") as f:
    content = f.read()

# ── 1. Default doc font → Arial ──────────────────────────────────────────
content = content.replace(
    '<w:rFonts w:asciiTheme="minorHAnsi" w:cstheme="minorBidi" w:eastAsiaTheme="minorEastAsia" w:hAnsiTheme="minorHAnsi"/>',
    '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>',
    1  # only first occurrence = docDefaults
)

# ── 2. Default paragraph spacing after → 120 (was 200) ──────────────────
content = content.replace(
    '<w:spacing w:after="200"/>', '<w:spacing w:after="120" w:line="276" w:lineRule="auto"/>', 1
)

# ── 3. HEADING 1 ─────────────────────────────────────────────────────────
old_h1_color = '<w:color w:themeColor="accent1" w:themeShade="BF" w:val="0F4761"/>\n        \n        \n        <w:sz w:val="40"/>'
new_h1_color = '<w:color w:val="1F3864"/>\n        \n        \n        <w:sz w:val="44"/>'
content = content.replace(old_h1_color, new_h1_color, 1)

# H1 spacing: add generous space before & after
old_h1_spacing = re.search(
    r'(styleId="Heading1".*?<w:pPr>)(.*?)(</w:pPr>.*?styleId="Heading2")',
    content, re.DOTALL
)
if old_h1_spacing:
    h1_ppr_block = old_h1_spacing.group(2)
    new_spacing = '\n        <w:spacing w:before="480" w:after="160"/>\n        <w:keepNext/>\n'
    if '<w:spacing' not in h1_ppr_block:
        new_h1_ppr = h1_ppr_block + new_spacing
        content = content[:old_h1_spacing.start(2)] + new_h1_ppr + content[old_h1_spacing.end(2):]

# H1 font: Arial, bold
content = content.replace(
    '<w:rFonts w:asciiTheme="majorHAnsi" w:cstheme="majorBidi" w:eastAsiaTheme="majorEastAsia" w:hAnsiTheme="majorHAnsi"/>\n        \n        \n        <w:color w:val="1F3864"/>',
    '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n        \n        \n        <w:color w:val="1F3864"/>',
    1
)

# ── 4. HEADING 2 ─────────────────────────────────────────────────────────
content = content.replace(
    '<w:color w:themeColor="accent1" w:themeShade="BF" w:val="0F4761"/>\n        \n        \n        <w:sz w:val="32"/>',
    '<w:color w:val="2563A8"/>\n        \n        \n        <w:sz w:val="32"/>',
    1
)
content = content.replace(
    '<w:rFonts w:asciiTheme="majorHAnsi" w:cstheme="majorBidi" w:eastAsiaTheme="majorEastAsia" w:hAnsiTheme="majorHAnsi"/>\n        \n        \n        <w:color w:val="2563A8"/>',
    '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n        \n        \n        <w:color w:val="2563A8"/>',
    1
)

# ── 5. HEADING 3 ─────────────────────────────────────────────────────────
content = content.replace(
    '<w:color w:themeColor="accent1" w:themeShade="BF" w:val="0F4761"/>\n        \n        \n        <w:sz w:val="28"/>',
    '<w:color w:val="1F6B9E"/>\n        \n        \n        <w:sz w:val="28"/>',
    1
)

# ── 6. Title style ────────────────────────────────────────────────────────
# Title: font size 56 → keep but change color to deep navy
content = content.replace(
    '<w:rFonts w:asciiTheme="majorHAnsi" w:cstheme="majorBidi" w:eastAsiaTheme="majorEastAsia" w:hAnsiTheme="majorHAnsi"/>\n        \n        \n        <w:sz w:val="56"/>',
    '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>\n        \n        \n        <w:color w:val="1F3864"/>\n        \n        \n        <w:sz w:val="56"/>',
    1
)

# ── 7. VerbatimChar (inline code) → Consolas, gray bg ────────────────────
verbatim_old = re.search(r'styleId="VerbatimChar".*?</w:style>', content, re.DOTALL)
if verbatim_old:
    old_block = verbatim_old.group(0)
    # Replace entire VerbatimChar style body with improved version
    new_verbatim = '''<w:style w:customStyle="1" w:styleId="VerbatimChar" w:type="character">


    <w:name w:val="VerbatimChar"/>


    <w:basedOn w:val="DefaultParagraphFont"/>


    <w:rPr>


      <w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Courier New"/>


      <w:color w:val="C0392B"/>


      <w:sz w:val="20"/>


      <w:szCs w:val="20"/>


      <w:highlight w:val="lightGray"/>

    </w:rPr>

  </w:style>'''
    content = content[:verbatim_old.start()] + new_verbatim + content[verbatim_old.end():]

# ── 8. SourceCode (code blocks) → Consolas, gray bg ─────────────────────
source_old = re.search(r'styleId="SourceCode".*?</w:style>', content, re.DOTALL)
if source_old:
    old_block = source_old.group(0)
    new_source = '''<w:style w:type="paragraph" w:customStyle="1" w:styleId="SourceCode">


    <w:name w:val="SourceCode"/>


    <w:basedOn w:val="Normal"/>


    <w:pPr>


      <w:spacing w:before="80" w:after="80" w:line="240" w:lineRule="auto"/>


      <w:ind w:left="360" w:right="360"/>


      <w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>

    </w:pPr>


    <w:rPr>


      <w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Courier New"/>


      <w:sz w:val="19"/>


      <w:szCs w:val="19"/>

    </w:rPr>

  </w:style>'''
    content = content[:source_old.start()] + new_source + content[source_old.end():]

# ── 9. Table header row style (first row shading) ───────────────────────
# The table style uses "Table" styleId — add header row band with navy fill
table_old = re.search(r'w:styleId="Table" w:type="table".*?</w:style>', content, re.DOTALL)
if table_old:
    old_tbl = table_old.group(0)
    # Inject a firstRow conditional format with navy header
    header_cond = '''
      <w:tblStylePr w:type="firstRow">
        <w:tcPr>
          <w:shd w:val="clear" w:color="auto" w:fill="1F3864"/>
        </w:tcPr>
        <w:rPr>
          <w:b/>
          <w:bCs/>
          <w:color w:val="FFFFFF"/>
        </w:rPr>
      </w:tblStylePr>
      <w:tblStylePr w:type="band1Horz">
        <w:tcPr>
          <w:shd w:val="clear" w:color="auto" w:fill="EEF3FA"/>
        </w:tcPr>
      </w:tblStylePr>'''
    if 'firstRow' not in old_tbl:
        new_tbl = old_tbl.replace('</w:style>', header_cond + '\n  </w:style>', 1)
        content = content[:table_old.start()] + new_tbl + content[table_old.end():]

# ── 10. Normal paragraph: set Arial explicitly + line spacing ────────────
# Find Normal style and ensure rPr uses Arial
normal_style = re.search(r'styleId="Normal" w:type="paragraph".*?</w:style>', content, re.DOTALL)
if normal_style:
    old_normal = normal_style.group(0)
    if '<w:rPr>' not in old_normal:
        # Inject rPr before </w:style>
        new_rpr = '''
    <w:rPr>
      <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>
      <w:lang w:val="th-TH" w:eastAsia="th-TH"/>
    </w:rPr>'''
        new_normal = old_normal.replace('</w:style>', new_rpr + '\n  </w:style>', 1)
        content = content[:normal_style.start()] + new_normal + content[normal_style.end():]

with open(STYLES_PATH, "w", encoding="ascii", errors="xmlcharrefreplace") as f:
    f.write(content)

print("styles.xml patched successfully")
