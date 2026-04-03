"""Add page breaks before each Heading2 (main sections), skipping the first 3."""

import re

DOC_PATH = "report_unpacked/word/document.xml"

with open(DOC_PATH, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

PAGE_BREAK = '    <w:p><w:r><w:br w:type="page"/></w:r></w:p>\n\n\n    '

# Find all <w:p>...<w:pStyle w:val="Heading2"/>...</w:p> paragraphs
# We need to insert page break before each Heading2, but skip the first 2
# (those are sub-headings of the title page: "Thai NLP-to-SQL Agent" subtitle)

h2_pattern = re.compile(
    r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading2"/>)',
    re.DOTALL
)

count = [0]

def insert_page_break(m):
    count[0] += 1
    # Skip first 2 H2s (subtitle section before main content)
    if count[0] <= 2:
        return m.group(0)
    return PAGE_BREAK + m.group(0)

content = h2_pattern.sub(insert_page_break, content)

with open(DOC_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Page breaks added before {count[0] - 2} of {count[0]} Heading2 sections")
