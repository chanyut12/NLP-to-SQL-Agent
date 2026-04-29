"""
Slide builders for the presentation.
"""
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from scripts.presentation.config import NAVY, BLUE, STEEL, WHITE, LIGHT, GRAY, DARK, ACCENT, GREEN, ORANGE, RED
from scripts.presentation.helpers import blank_slide, bg, add_rect, add_text, add_multiline, section_header, kpi_box, table_box, flow_box


def build_all_slides(prs):
    """Generate all slides for the NLP-to-SQL presentation."""
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 1 — Title
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    
    # gradient-ish diagonal accent
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_rect(sl, 0, 7.42, 13.33, 0.08, fill=BLUE)
    add_rect(sl, 0, 0, 0.08, 7.5, fill=ACCENT)
    
    # main content
    add_text(sl, "Thai NLP-to-SQL Agent", 1, 1.4, 11, 1.4,
             size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(sl, "ระบบแปลภาษาไทยเป็น SQL อัตโนมัติ",
             1, 2.9, 11, 0.8, size=24, color=ACCENT, align=PP_ALIGN.CENTER)
    add_text(sl, "Thai Question → Safe SQL → Real Data → Visualization",
             1, 3.8, 11, 0.7, size=18, italic=True, color=RGBColor(0xBB, 0xD5, 0xFF),
             align=PP_ALIGN.CENTER)
    
    # badges
    badges = [
        ("RAG + LLM", BLUE),
        ("SQL Safety", RGBColor(0x06, 0x82, 0x5B)),
        ("Self-Correction", RGBColor(0x8B, 0x2F, 0xC9)),
        ("Multi-Provider", RGBColor(0xC4, 0x60, 0x10)),
    ]
    bx = 1.5
    for label, col in badges:
        add_rect(sl, bx, 4.9, 2.3, 0.55, fill=col)
        add_text(sl, label, bx+0.1, 4.93, 2.1, 0.45, size=14, bold=True,
                 color=WHITE, align=PP_ALIGN.CENTER)
        bx += 2.6
    
    add_text(sl, "March 2026  |  NLP Project Evaluation Report",
             1, 6.6, 11, 0.5, size=13, color=RGBColor(0x88, 0xAA, 0xCC),
             align=PP_ALIGN.CENTER)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 2 — Agenda
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "สารบัญ  /  Agenda", 0.5, 0.25, 12, 0.7,
             size=28, bold=True, color=WHITE)
    
    items = [
        ("01", "บทสรุปผู้บริหาร", "Executive Summary & KPIs"),
        ("02", "ความเข้าใจปัญหา", "Problem Definition & Data Sources"),
        ("03", "สถาปัตยกรรมและเทคนิค", "Architecture & Technical Decisions"),
        ("04", "การเลือกโมเดล", "LLM Model Selection"),
        ("05", "การวัดผล", "Evaluation & Benchmark Results"),
        ("06", "Error Analysis", "Types of Failures & Insights"),
        ("07", "ข้อจำกัด", "Limitations & Production Readiness"),
        ("08", "นวัตกรรม", "Innovation & Wow Factor"),
    ]
    
    cols = [items[:4], items[4:]]
    for ci, col in enumerate(cols):
        xl = 0.7 + ci * 6.4
        for ri, (num, th, en) in enumerate(col):
            yt = 1.2 + ri * 1.45
            add_rect(sl, xl, yt, 5.8, 1.25, fill=RGBColor(0x16, 0x1A, 0x2E), line=BLUE)
            add_rect(sl, xl, yt, 0.55, 1.25, fill=BLUE)
            add_text(sl, num, xl+0.05, yt+0.3, 0.45, 0.6,
                     size=18, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
            add_text(sl, th, xl+0.65, yt+0.1, 5.0, 0.5, size=16, bold=True, color=WHITE)
            add_text(sl, en, xl+0.65, yt+0.62, 5.0, 0.45, size=12, italic=True,
                     color=RGBColor(0x88, 0xBB, 0xDD))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 3 — Executive Summary KPIs
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "01  บทสรุปผู้บริหาร", 0.5, 0.18, 12, 0.7, size=26, bold=True, color=WHITE)
    add_text(sl, "Executive Summary", 0.5, 0.75, 12, 0.4, size=15, italic=True, color=ACCENT)
    
    kpis = [
        ("82.65%", "Overall Success Rate\n(324 / 392 queries)"),
        ("80.87%", "First-try Success\n(no retry needed)"),
        ("7",      "Self-correction wins\n(retry saved these)"),
        ("11.44s", "Median Latency (p50)"),
        ("100%",   "SQL Validity\n(all models)"),
        ("80%",    "Best EX Score\n(glm-5 on benchmark)"),
    ]
    for i, (val, lbl) in enumerate(kpis):
        col = i % 3
        row = i // 3
        kpi_box(sl, val, lbl, 0.55 + col * 4.15, 1.35 + row * 1.65, w=3.8, h=1.45,
                vcolor=ACCENT, bg_color=RGBColor(0x16, 0x1A, 0x2E))
    
    add_rect(sl, 0.55, 4.75, 12.2, 1.55, fill=RGBColor(0x0D, 0x11, 0x1E), line=BLUE)
    add_text(sl, "ระบบ Thai NLP-to-SQL Agent แปลงคำถามภาษาไทยเป็น SQL ที่ executable และ safe "
                 "พร้อม visualization อัตโนมัติ  รองรับ SQLite, MySQL, PostgreSQL "
                 "และ LLM หลายตัว ทั้ง Local (Ollama) และ Cloud (OpenAI / Google / Z.ai)",
             0.75, 4.82, 11.8, 1.35, size=14, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 4 — Problem Definition
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "02  ความเข้าใจปัญหา — 5 Pain Points", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Problem Definition", 0.5, 0.75, 12, 0.4, size=15, italic=True, color=ACCENT)
    
    problems = [
        ("#1  Language Gap",
         "ผู้ใช้ถามภาษาไทย แต่ DB ต้องใช้ SQL\n→ เข้าถึงข้อมูลไม่ได้โดยไม่มีนักพัฒนา",
         BLUE),
        ("#2  Ambiguity",
         "คำถามไทยมี synonym / intent หลากหลาย\n→ SQL ผิด intent แม้ syntax ถูก",
         RGBColor(0x1F, 0x6B, 0x9E)),
        ("#3  Dialect Mismatch",
         "SQL ต้องถูกต้องตาม dialect\n(MySQL / SQLite / PostgreSQL)\n→ รันบน engine อื่นไม่ผ่าน",
         RGBColor(0x8B, 0x2F, 0xC9)),
        ("#4  Safety Risk",
         "ระบบ execute บน DB จริง\n→ ต้องบล็อก destructive commands ทุกชนิด",
         RGBColor(0xC4, 0x60, 0x10)),
        ("#5  Usability",
         "ผลลัพธ์ต้องใช้งานได้จริง\n(execution success + chart-ready output)",
         RGBColor(0x06, 0x82, 0x5B)),
    ]
    
    for i, (title, desc, col) in enumerate(problems):
        row = i // 3
        c   = i % 3
        xl  = 0.5 + c * 4.25
        yt  = 1.3 + row * 2.4
        add_rect(sl, xl, yt, 3.95, 2.1, fill=RGBColor(0x16, 0x1A, 0x2E), line=col)
        add_rect(sl, xl, yt, 3.95, 0.42, fill=col)
        add_text(sl, title, xl+0.1, yt+0.04, 3.7, 0.36, size=14, bold=True, color=WHITE)
        add_text(sl, desc, xl+0.1, yt+0.5, 3.7, 1.5, size=12, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    add_text(sl, "System Definition:  Thai Question  →  Executable & Safe SQL  →  Table + Visualization",
             0.5, 6.05, 12.3, 0.55, size=14, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 5 — Context Preparation Pipeline
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "02  Context Preparation — 6 Steps", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "ระบบไม่โยนคำถามเข้า LLM ตรงๆ — เตรียม context 6 ขั้นตอน", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    steps = [
        ("①", "Query\nEmbedding", "multilingual-e5-small\n(query: prefix)", BLUE),
        ("②", "Example\nRetrieval", "ChromaDB\n(passage: embed)", BLUE),
        ("③", "Dialect Filter\n+ Fallback", "ถ้าไม่ครบ top-K\nfallback no filter", RGBColor(0x1F,0x6B,0x9E)),
        ("④", "SQL\nTranspile", "sqlglot\nauto-transpile dialect", RGBColor(0x1F,0x6B,0x9E)),
        ("⑤", "Schema\nExtraction", "SQLAlchemy\nFK + PK annotations", RGBColor(0x8B,0x2F,0xC9)),
        ("⑥", "Smart Schema\nFiltering", "Semantic + Thai map\n+ keyword + LLM guess", RGBColor(0xC4,0x60,0x10)),
    ]
    
    for i, (num, title, tech, col) in enumerate(steps):
        xl = 0.5 + (i % 3) * 4.2
        yt = 1.4 + (i // 3) * 2.6
        add_rect(sl, xl, yt, 3.8, 2.3, fill=RGBColor(0x16, 0x1A, 0x2E), line=col)
        add_rect(sl, xl, yt, 0.55, 2.3, fill=col)
        add_text(sl, num, xl+0.05, yt+0.7, 0.45, 0.7, size=20, bold=True, color=WHITE,
                 align=PP_ALIGN.CENTER)
        add_text(sl, title, xl+0.65, yt+0.12, 3.0, 0.75, size=15, bold=True, color=WHITE)
        add_text(sl, tech,  xl+0.65, yt+0.95, 3.0, 1.1, size=12, color=RGBColor(0xBB, 0xD5, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 6 — System Architecture
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "03  System Architecture — 7 Components", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Hybrid: RAG + LLM + SQL Safety + Self-Correction", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    comps = [
        ("①", "Example RAG", "ดึง few-shot SQL\nที่ใกล้เคียง", BLUE),
        ("②", "Schema Context\nBuilder", "schema + FK\n+ join hints", BLUE),
        ("③", "LLM SQL\nGenerator", "สร้าง SQL\nตาม dialect", RGBColor(0x1F,0x6B,0x9E)),
        ("④", "SQL Safety\nValidator", "AST-based\nread-only policy", RGBColor(0xC4,0x60,0x10)),
        ("⑤", "Execution\nLayer", "SQLAlchemy\n+ Pandas", RGBColor(0x8B,0x2F,0xC9)),
        ("⑥", "Self-Correction\nLoop", "retry max 2×\nwith error msg", RGBColor(0x06,0x82,0x5B)),
        ("⑦", "Visualization\nRecommender", "suggest chart type\n+ axes", RGBColor(0x06, 0x6B, 0x9E)),
    ]
    
    for i, (num, title, desc, col) in enumerate(comps):
        xl = 0.4 + (i % 4) * 3.2
        yt = 1.35 + (i // 4) * 2.55
        add_rect(sl, xl, yt, 2.9, 2.2, fill=RGBColor(0x16, 0x1A, 0x2E), line=col)
        add_rect(sl, xl, yt, 2.9, 0.38, fill=col)
        add_text(sl, f"{num} {title}", xl+0.1, yt+0.04, 2.7, 0.32, size=12, bold=True, color=WHITE)
        add_text(sl, desc, xl+0.1, yt+0.48, 2.7, 1.5, size=12, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    add_text(sl, "Thai Q  →  [RAG + Schema]  →  LLM  →  Safety Check  →  Execute  →  Retry?  →  Viz",
             0.4, 6.8, 12.5, 0.55, size=13, color=ACCENT, align=PP_ALIGN.CENTER)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 7 — Technical Justification
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "03  Why These Techniques?", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Technical Justification & Trade-offs", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    cards = [
        ("Dual RAG (not one store)",
         "Example RAG → SQL pattern\nSchema RAG → relevant tables\nแยก embedding space & update cycle",
         BLUE),
        ("SQL Safety (AST-based)",
         "Execute บน DB จริง → ต้องบล็อก\nDELETE/DROP/ALTER/INSERT…\nSingle-stmt + LIMIT enforcement",
         RGBColor(0xC4, 0x60, 0x10)),
        ("Self-Correction Loop",
         "Error message + full schema + FK\nส่งกลับ model → retry ≤ 2×\nช่วยกู้ column/dialect errors",
         RGBColor(0x06, 0x82, 0x5B)),
        ("Smart Schema Filtering",
         "ส่งเฉพาะ relevant tables\nลด prompt noise สำหรับ local LLM\nSemantic + Thai name mapping",
         RGBColor(0x8B, 0x2F, 0xC9)),
    ]
    
    for i, (title, body, col) in enumerate(cards):
        xl = 0.5 + (i % 2) * 6.4
        yt = 1.35 + (i // 2) * 2.55
        add_rect(sl, xl, yt, 6.1, 2.3, fill=RGBColor(0x16, 0x1A, 0x2E), line=col)
        add_rect(sl, xl, yt, 6.1, 0.42, fill=col)
        add_text(sl, title, xl+0.15, yt+0.05, 5.8, 0.36, size=14, bold=True, color=WHITE)
        add_text(sl, body, xl+0.15, yt+0.52, 5.8, 1.65, size=13, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 8 — Model Selection
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "04  LLM Model Selection", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Multi-provider support — Local & Cloud", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    table_box(
        sl,
        headers=["Provider", "Model", "Size", "Notes"],
        rows=[
            ["Ollama (Default)", "qwen2.5-coder:7b", "7B local", "รองรับไทย, ฟรี, private"],
            ["OpenAI", "gpt-4o-mini", "Cloud API", "Latency ต่ำ ~31s/25q, stable"],
            ["Google", "gemini-2.0-flash-exp", "Cloud API", "เร็ว, คุณภาพสูง"],
            ["OpenRouter", "nvidia/nemotron-120b", "120B", "Free tier, คุณภาพสูง"],
            ["Z.ai (Zhipu) ★", "glm-5", "Cloud API", "EX สูงสุด 80% — แนะนำ"],
            ["Z.ai (Zhipu)", "glm-4.7-flash", "Cloud API", "ราคาถูก, ผลปานกลาง 56%"],
        ],
        l=0.5, t=1.3, w=12.3, h=3.5,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=13
    )
    
    add_rect(sl, 0.5, 5.1, 12.3, 1.9, fill=RGBColor(0x16, 0x1A, 0x2E), line=ACCENT)
    add_text(sl, "Key Config Parameters", 0.65, 5.15, 5, 0.4, size=14, bold=True, color=ACCENT)
    params = [
        "RAG_TOP_K = 3  (few-shot examples)",
        "SCHEMA_TOP_K = 5  (tables for local LLM)",
        "MAX_RETRIES = 2  (self-correction)",
    ]
    params2 = [
        "RAG_DISTANCE_THRESHOLD = 15.0",
        "MAX_SQL_LIMIT = 500  (row cap)",
        "ENABLE_INTELLIGENT_VIZ = False  (latency control)",
    ]
    for i, p in enumerate(params):
        add_text(sl, "• " + p, 0.7, 5.6 + i*0.3, 6.0, 0.28, size=12, color=RGBColor(0xCC,0xDD,0xFF))
    for i, p in enumerate(params2):
        add_text(sl, "• " + p, 6.9, 5.6 + i*0.3, 5.8, 0.28, size=12, color=RGBColor(0xCC,0xDD,0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 9 — Operational Metrics
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "05  Operational Evaluation — query_logs.jsonl", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "394 real queries from production logs", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    kpi_data = [
        ("82.65%", "Overall\nSuccess Rate"),
        ("80.87%", "First-try\nSuccess"),
        ("7", "Retry\nSaves"),
        ("11.44s", "p50\nLatency"),
    ]
    for i, (v, l) in enumerate(kpi_data):
        kpi_box(sl, v, l, 0.5 + i * 3.1, 1.35, w=2.8, h=1.4,
                vcolor=ACCENT, bg_color=RGBColor(0x16, 0x1A, 0x2E))
    
    add_text(sl, "Dialect Distribution", 0.5, 3.0, 5.5, 0.45,
             size=14, bold=True, color=ACCENT)
    table_box(
        sl,
        headers=["Dialect", "Count", "Share"],
        rows=[
            ["MySQL",       "304", "77.6%"],
            ["SQLite",       "81", "20.7%"],
            ["PostgreSQL",    "3",  "0.8%"],
            ["Unknown",       "4",  "1.0%"],
        ],
        l=0.5, t=3.5, w=5.5, h=2.6,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=13
    )
    
    add_text(sl, "Latency Breakdown", 6.5, 3.0, 6.3, 0.45, size=14, bold=True, color=ACCENT)
    table_box(
        sl,
        headers=["Metric", "Value", "Notes"],
        rows=[
            ["Avg duration",  "16.86s", "overall mean"],
            ["p50 (median)",  "11.44s", "most users feel this"],
            ["p95",           "47.82s", "⚠ tail — needs optimization"],
        ],
        l=6.5, t=3.5, w=6.3, h=2.6,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=13
    )
    
    add_text(sl, "⚠  p95 = 47.82s — architectural optimization needed for tail latency",
             0.5, 6.3, 12.3, 0.5, size=13, color=ORANGE, align=PP_ALIGN.CENTER)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 10 — Benchmark Results
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "05  Mini Benchmark — Execution Accuracy (25 Questions)", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "classicmodels DB (SQLite) — 6 model configurations", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    table_box(
        sl,
        headers=["Model", "Provider", "RAG_K", "Retry", "SQL Valid", "Exec'able", "EX (%)"],
        rows=[
            ["gpt-4o-mini ×5", "OpenAI",     "3", "0", "100%", "100%", "48% ★stable"],
            ["qwen2.5-coder",  "Ollama",      "0", "—", "100%",  "96%", "56%"],
            ["qwen2.5-coder",  "Ollama",      "3", "2", "100%", "100%", "60%"],
            ["glm-4.7-flash",  "Z.ai",        "5", "0", "100%",  "92%", "56%"],
            ["nemotron-120b",  "OpenRouter",  "3", "2", "100%",  "92%", "64%"],
            ["glm-5 ★",        "Z.ai",        "5", "0", "100%", "100%", "80% 🏆"],
        ],
        l=0.4, t=1.35, w=12.5, h=3.1,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=12
    )
    
    add_text(sl, "EX by Query Category", 0.4, 4.65, 12.5, 0.45, size=14, bold=True, color=ACCENT)
    table_box(
        sl,
        headers=["Category", "N", "gpt-4o-mini", "qwen (RAG=3)", "nemotron", "glm-4.7", "glm-5"],
        rows=[
            ["simple",      "5",  "60%", "100%", "80%",  "60%", "100%"],
            ["aggregation", "7",  "57%",  "71%", "86%",  "71%",  "71%"],
            ["join",        "7",  "14%",  "29%", "43%",  "43%",  "86%"],
            ["complex",     "6",  "67%",  "50%", "50%",  "50%",  "67%"],
            ["TOTAL",      "25",  "48%",  "60%", "64%",  "56%",  "80%"],
        ],
        l=0.4, t=5.15, w=12.5, h=2.15,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=11
    )
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 11 — Error Analysis
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "06  Error Analysis — Why Queries Fail", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "68 failed queries out of 392  (17.35%)", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    errors = [
        ("column_error", "24", "35.3%", "เลือก column ผิด / กำกวม", ORANGE),
        ("unknown/other", "24", "35.3%", "error message ไม่ชัด", RGBColor(0x88,0x88,0x88)),
        ("table_error", "12", "17.6%", "อ้างตารางที่ไม่มีใน schema", RED),
        ("syntax_error", "5", "7.4%", "โครงสร้าง SQL ผิด", BLUE),
        ("dialect_error", "3", "4.4%", "ใช้ฟังก์ชันผิด dialect", RGBColor(0x8B,0x2F,0xC9)),
    ]
    
    for i, (etype, cnt, pct, desc, col) in enumerate(errors):
        yt = 1.4 + i * 0.98
        bar_w = float(pct.rstrip("%")) / 100 * 8.5
        add_rect(sl, 3.1, yt+0.08, bar_w, 0.65, fill=col)
        add_text(sl, etype, 0.3, yt+0.1, 2.75, 0.5, size=13, bold=True, color=col)
        add_text(sl, f"{cnt}  ({pct})", 3.2 + bar_w, yt+0.1, 1.8, 0.5,
                 size=13, bold=True, color=WHITE)
        add_text(sl, desc, 3.2 + bar_w + 2.0, yt+0.1, 5.0, 0.5,
                 size=12, italic=True, color=RGBColor(0xBB, 0xCC, 0xEE))
    
    add_rect(sl, 0.3, 6.4, 12.7, 0.85, fill=RGBColor(0x16, 0x1A, 0x2E), line=ACCENT)
    add_text(sl,
             "💡 Key Insight: column_error คือช่องว่างหลัก (35%) → target: better schema grounding ระดับ column\n"
             "   Join errors คือ differentiator ระหว่าง models — glm-5 แก้ปัญหา FK-path ได้ดีที่สุด (86% join EX)",
             0.5, 6.42, 12.3, 0.8, size=12, color=RGBColor(0xCC, 0xEE, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 12 — Benchmark Insight: Correct but Over-specified
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "05  Insight: \"Correct but Over-specified\"", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Known limitation of strict EX metric — case study: complex_006", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    add_rect(sl, 0.5, 1.3, 5.9, 2.8, fill=RGBColor(0x16, 0x1A, 0x2E), line=BLUE)
    add_text(sl, "Gold SQL  (เฉลยที่เราเขียน)", 0.65, 1.35, 5.5, 0.4, size=13, bold=True, color=BLUE)
    add_text(sl,
             "SELECT productName\nFROM products\nWHERE productCode NOT IN (\n  SELECT DISTINCT productCode\n  FROM orderdetails\n)\nLIMIT 500",
             0.65, 1.8, 5.5, 2.1, size=11, color=RGBColor(0xBB, 0xDD, 0xFF))
    
    add_rect(sl, 6.9, 1.3, 5.9, 2.8, fill=RGBColor(0x16, 0x1A, 0x2E), line=ORANGE)
    add_text(sl, "Predicted SQL  (โมเดล generate)", 7.05, 1.35, 5.5, 0.4, size=13, bold=True, color=ORANGE)
    add_text(sl,
             "SELECT p.productCode, p.productName\nFROM products AS p\nLEFT JOIN orderdetails AS od\n  ON p.productCode = od.productCode\nWHERE od.orderNumber IS NULL\nLIMIT 500",
             7.05, 1.8, 5.5, 2.1, size=11, color=RGBColor(0xFF, 0xDD, 0xBB))
    
    table_box(
        sl,
        headers=["Dimension", "Gold SQL", "Predicted SQL"],
        rows=[
            ["Business Logic",  "✅ Correct",  "✅ Correct"],
            ["SQL Technique",   "NOT IN",      "LEFT JOIN + IS NULL  (valid alt)"],
            ["Output Columns",  "1 col",       "2 cols  (productCode extra)"],
            ["EX Result",       "—",           "❌ FAIL  (column count mismatch)"],
        ],
        l=0.5, t=4.35, w=12.3, h=2.0,
        hdr_fill=NAVY, row_fill=RGBColor(0x16, 0x1A, 0x2E),
        alt_fill=RGBColor(0x0D, 0x11, 0x1E), font_size=12
    )
    
    add_rect(sl, 0.5, 6.55, 12.3, 0.75, fill=RGBColor(0x0D, 0x11, 0x1E), line=GREEN)
    add_text(sl,
             "Impact: Business EX of gpt-4o-mini likely 49–52%  |  glm-5 likely up to 84%  "
             "  (Strict EX kept for academic comparability)",
             0.65, 6.6, 12.0, 0.6, size=13, color=GREEN, align=PP_ALIGN.CENTER)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 13 — Limitations & Production Readiness
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "07  ข้อจำกัดและความพร้อมใช้งานจริง", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Limitations & Production Readiness", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    ready = [
        ("✅ Security & Safety",
         "• Block INSERT/UPDATE/DELETE/DROP/ALTER\n• Single-statement enforcement\n• LIMIT injection & row cap\n• Allowlist-only table access",
         GREEN),
        ("✅ Observability",
         "• Rich logs: 18+ fields per query\n• 8 new v2 metrics (join, aggregation…)\n• Backward-compatible JSONL format\n• Feedback & favorites loop",
         GREEN),
        ("⚠ Latency",
         "• p50 = 11.44s — acceptable\n• p95 = 47.82s — tail too high\n• RAG parallelization (asyncio.gather)\n  reduces wall time but LLM bottleneck remains",
         ORANGE),
        ("⚠ Benchmark Coverage",
         "• 25 questions, SQLite only\n• In-distribution bias\n• Strict EX underestimates business accuracy\n• Needs 100+ questions + MySQL dialect",
         ORANGE),
    ]
    
    for i, (title, body, col) in enumerate(ready):
        xl = 0.5 + (i % 2) * 6.4
        yt = 1.35 + (i // 2) * 2.6
        add_rect(sl, xl, yt, 6.1, 2.4, fill=RGBColor(0x16, 0x1A, 0x2E), line=col)
        add_rect(sl, xl, yt, 6.1, 0.4, fill=col)
        add_text(sl, title, xl+0.1, yt+0.04, 5.8, 0.36, size=13, bold=True, color=DARK)
        add_text(sl, body, xl+0.1, yt+0.5, 5.8, 1.75, size=12, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 14 — Innovation / Wow Factor
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "08  นวัตกรรม — Wow Factor", 0.5, 0.18, 12, 0.7,
             size=26, bold=True, color=WHITE)
    add_text(sl, "Innovation & Creative Engineering Contributions", 0.5, 0.75, 12, 0.4,
             size=15, italic=True, color=ACCENT)
    
    innovations = [
        ("🔀 Dual-RAG Architecture",
         "แยก Example RAG + Schema RAG อย่าง explicit\nต่างจาก single-store ที่งานอื่นทำ\nจัดการ embedding space & update cycle ได้เหมาะสมกว่า"),
        ("🌐 Thai-English Semantic Bridge",
         "mapping ชื่อ column/table ภาษาไทย ↔ อังกฤษ\nช่วย schema retrieval เมื่อผู้ใช้ถามด้วยคำไทย\nเช่น 'ลูกค้า' → customers"),
        ("🔑 FK-aware Join Hints",
         "ดึง Foreign Key ทุกตัว รวมถึง cross-name FK\nสร้าง join_hints section ใน prompt\nแก้ปัญหา salesRepEmployeeNumber → employeeNumber"),
        ("🛡️ AST-based SQL Safety",
         "ไม่ใช้ regex blacklist — parse เป็น AST จริง\nบล็อก destructive commands ระดับ statement\nInject LIMIT อัตโนมัติ"),
        ("🔄 Error-aware Self-Correction",
         "ส่ง error message + full schema + FK กลับ model\nRetry สูงสุด 2 ครั้งด้วย full context\nช่วยกู้ 7 queries ที่จะ fail"),
        ("📊 Auto Visualization Recommender",
         "วิเคราะห์ result schema → แนะนำ chart type\nกำหนด x_col, y_col, series_col อัตโนมัติ\nลด friction สำหรับ non-technical users"),
    ]
    
    for i, (title, body) in enumerate(innovations):
        xl = 0.5 + (i % 3) * 4.25
        yt = 1.35 + (i // 3) * 2.7
        add_rect(sl, xl, yt, 4.0, 2.5, fill=RGBColor(0x16, 0x1A, 0x2E), line=ACCENT)
        add_text(sl, title, xl+0.1, yt+0.1, 3.8, 0.6, size=13, bold=True, color=ACCENT)
        add_text(sl, body, xl+0.1, yt+0.75, 3.8, 1.6, size=11, color=RGBColor(0xCC, 0xDD, 0xFF))
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SLIDE 15 — Conclusions & Next Steps
    # ═══════════════════════════════════════════════════════════════════════════════
    sl = blank_slide(prs)
    bg(sl, DARK)
    add_rect(sl, 0, 0, 13.33, 0.08, fill=ACCENT)
    add_text(sl, "Conclusions & Next Steps", 0.5, 0.18, 12, 0.7,
             size=30, bold=True, color=WHITE)
    add_text(sl, "Thai NLP-to-SQL Agent — Summary", 0.5, 0.82, 12, 0.45,
             size=16, italic=True, color=ACCENT)
    
    add_rect(sl, 0.5, 1.45, 5.8, 5.2, fill=RGBColor(0x16, 0x1A, 0x2E), line=GREEN)
    add_rect(sl, 0.5, 1.45, 5.8, 0.42, fill=GREEN)
    add_text(sl, "✅ What We Achieved", 0.65, 1.48, 5.5, 0.38, size=14, bold=True, color=DARK)
    achievements = [
        "• 82.65% success rate on real production queries",
        "• glm-5 achieves 80% EX on benchmark (best-in-class)",
        "• 100% SQL validity across ALL models tested",
        "• Self-correction rescues 7 additional queries",
        "• Dual-RAG + FK-aware architecture",
        "• Full safety: AST-based, read-only, LIMIT-enforced",
        "• Rich observability: 18+ log fields per query",
        "• Multi-provider: Local Ollama + 4 Cloud APIs",
    ]
    for i, a in enumerate(achievements):
        add_text(sl, a, 0.65, 1.97 + i*0.55, 5.5, 0.52, size=12, color=RGBColor(0xCC,0xEE,0xCC))
    
    add_rect(sl, 6.8, 1.45, 6.0, 5.2, fill=RGBColor(0x16, 0x1A, 0x2E), line=ORANGE)
    add_rect(sl, 6.8, 1.45, 6.0, 0.42, fill=ORANGE)
    add_text(sl, "🚀 Next Steps", 6.95, 1.48, 5.7, 0.38, size=14, bold=True, color=DARK)
    nexts = [
        "① Expand benchmark: 100+ ข้อ, MySQL + receipt schema",
        "② Ablation study: ปิด RAG / schema filter / retry\n    วัด contribution แต่ละ component",
        "③ Semantic correctness metric\n    (ประเมินเกินกว่า pass/fail)",
        "④ Latency optimization for p95 tail (47.82s → <20s)",
        "⑤ Column-level schema grounding\n    (target: reduce column_error จาก 35%)",
        "⑥ Larger RAG examples dataset\n    (ขยายจาก 55 → 200+ examples)",
    ]
    for i, n in enumerate(nexts):
        add_text(sl, n, 6.95, 1.97 + i*0.78, 5.7, 0.72, size=11.5, color=RGBColor(0xFF,0xDD,0xBB))
    
    add_text(sl, "Thai NLP-to-SQL Agent  |  NLP Project  |  March 2026",
             0.5, 6.85, 12.3, 0.45, size=13, color=RGBColor(0x66, 0x88, 0xAA),
             align=PP_ALIGN.CENTER)
