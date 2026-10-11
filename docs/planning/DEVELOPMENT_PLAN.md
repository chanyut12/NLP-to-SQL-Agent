# 🚀 NLP-to-SQL Agent Development Plan

**Date:** 2026-01-22 (Updated)
**Author:** Software Architect Team
**Context:** Local Text-to-SQL Project using Qwen2.5-Coder:7b
**Project Status:** 🟢 Active Development - Q1 2026 Focus on UX & Security

---

## 📌 Current Sprint Status (2026-01-24)
- ✅ **Completed:** Frontend modularization, XSS fixes, Collapsible sidebar, **Phase 1 (API Error Handling + JSDoc)**, **Phase 2 (Event Delegation Security)**, Centralized Config, Unit Tests (Config & Safety), Responsive Design, `.env.example`
- 🚧 **In Progress:** Thai SQL Examples
- 📋 **Next Up:** Phase 3 (NLPEngine DI Refactoring), Phase 4 (CSP + Tests)

---

## 0. 🔧 Phase 0: Prerequisites (Definition of Ready)
**Goal:** Ensure stable environment and baseline before major refactoring.

### ✅ Action Items
- [x] **Environment Template:** Create `.env.example` documenting all required ENV vars (DB credentials, API keys, Model paths) matching `core/config.py`. *(Completed)*
- [ ] **Dependency Lock:** Generate `requirements.lock` (via pip-tools) to ensure reproducible builds across dev/prod environments.
- [ ] **Establish Baseline:** Run `eval/run_eval.py` on current codebase to record "Accuracy Score" and "Avg Latency". Use this to measure improvement after refactoring.

---

## 1. 🏗️ Architecture & Structure
**Current Status:** Modular Monolith using FastAPI. Good separation of concerns (DDD-inspired).
**Goal:** Improve maintainability and scalability.

### 🔍 Analysis
- **Strengths:**
  - Clear separation between `api`, `core/services`, `core/domain`, and `core/data`.
  - Use of `dependencies.py` for DI is excellent.
- **Weaknesses:**
  - `NLPEngine` class in `core/services/engine.py` is becoming a "God Class" handling RAG, Prompting, Execution, and Visualization.

### ✅ Action Items
- [ ] **Refactor NLPEngine:** Break down `NLPEngine` into smaller, focused services:
  - `PromptBuilderService`: Handle RAG assembly and template formatting.
  - `ExecutionService`: Handle DB connection and SQL execution.
  - `RetryManager`: Encapsulate the retry logic loop.
- [x] **Standardize Configuration:** Move hardcoded thresholds (e.g., `top_k=3`) from code to `core/config.py`. *(Completed: 2026-01-24)*
- [ ] **Containerization:** Create a `Dockerfile` and `docker-compose.yml` to bundle Python backend, Frontend, and Vector DB setup. *(Dockerfile & docker-compose.yml exist — need to verify completeness for production use)*

### ⚖️ Trade-off & Assessment Conditions
* **Refactoring vs. Velocity:**
    * *Condition:* หากทีมมีคนเดียวและต้องรีบส่ง Demo การ Refactor ตอนนี้อาจจะช้าไป แต่ถ้ากะใช้ยาวเกิน 3 เดือน ควรทำทันที
    * *Trade-off:* เสียเวลา dev feature ใหม่ 2-3 วันเพื่อแลกกับความง่ายในการแก้บั๊กในอนาคต (Long-term Maintainability > Short-term Velocity).
* **Dockerization:**
    * *Condition:* User ปลายทางมีความรู้ Tech แค่ไหน?
    * *Trade-off:* Docker ช่วยแก้ปัญหา "Works on my machine" ได้ 100% แต่เพิ่ม Complexity ในการ Setup ฝั่ง User ที่ต้องลง Docker Desktop (ซึ่งกิน Resource เครื่องเพิ่ม).

---

## 2. 🛡️ Security
**Current Status:** Strong SQL injection prevention via AST parsing. No Authentication.
**Goal:** Production-grade security.

### 🔍 Analysis
- **Strengths:**
  - Uses `sqlglot` for AST parsing and validation, not just Regex.
  - Forces `LIMIT` clause to prevent DoS.
- **Weaknesses:**
  - **No Authentication:** API endpoints are open.
  - **Credential Exposure:** Frontend sends DB credentials in JSON payload.

### ✅ Action Items
- [ ] **Implement Authentication:** Add API Key or JWT middleware in `api/dependencies.py`.
- [ ] **Secure Credentials:**
  - Stop sending raw DB credentials from Frontend.
  - Store connection profiles (Host/User/Pass) in Server-side Environment Variables or an Encrypted Vault.
  - Client sends only a `connection_id`.
- [ ] **Read-Only Enforcement:** Verify that the database user used by the application has **ONLY** `SELECT` permission at the database level (Defense in Depth).

### ⚖️ Trade-off & Assessment Conditions
* **Server-side Credential Storage:**
    * *Condition:* Server ของเรา Secure แค่ไหน? (มีการ Encrypt disk หรือไม่?)
    * *Trade-off:* การเก็บ Password ของ User ไว้ที่ Server เรา (แม้จะ Encrypt) ทำให้เราต้องรับผิดชอบความเสี่ยงถ้า Server โดน Hack เทียบกับแบบเดิมที่ User รับความเสี่ยงเอง (Client-side) แต่ Server-side ปลอดภัยกว่าในการส่งข้อมูลผ่าน Network.
* **Authentication:**
    * *Condition:* เป็น Internal Tool หรือ Public Service?
    * *Trade-off:* การใส่ Auth เพิ่ม Friction ในการใช้งาน (User ต้อง Login) แลกกับความสามารถในการ Audit Log ว่าใคร Query อะไรไปบ้าง (Accountability).

---

## 3. 🧠 AI Engineering & LLM Integration
**Current Status:** Advanced RAG implementation (Schema + Example RAG).
**Goal:** Higher accuracy and better context handling.

### 🔍 Analysis
- **Strengths:**
  - **Schema RAG:** Smart filtering of tables using `SchemaRAG` to save context window.
  - **Thai Localization:** Excellent dictionary mapping (`THAI_SCHEMA_MAPPINGS`).
- **Weaknesses:**
  - **Embedding Model:** Upgraded to `intfloat/multilingual-e5-small` (SOTA for Thai retrieval).

### ✅ Action Items
- [ ] **Enhance Prompt Engineering:** Implement "Chain of Thought" (CoT) explicitly in the prompt template in `engine.py` to force the model to explain its logic *before* writing SQL. *(Partially done — lightweight "Think step by step" exists but not full structured CoT)*
- [ ] **Dynamic Few-Shot Tuning:** Add a mechanism to provide "Negative Constraints" (examples of what *not* to do) based on previous error logs.
- [ ] **Embedding Optimization:** If specific technical terms are missed, consider Fine-tuning the embedding model or adding a "Glossary" layer to the RAG pipeline.

### ⚖️ Trade-off & Assessment Conditions
* **Chain of Thought (CoT):**
    * *Condition:* User รอได้นานแค่ไหน?
    * *Trade-off:* การบังคับให้ Model "Think step by step" จะเพิ่มความแม่นยำสูงมาก แต่จะเพิ่ม Latency 2-3 เท่า และเปลือง Token ขาออก (Output Token Cost/Time).
* **Fine-tuning Embeddings:**
    * *Condition:* ศัพท์ใน Database มีความเฉพาะทาง (Domain Specific) มากแค่ไหน?
    * *Trade-off:* ถ้าชื่อตารางเป็นภาษาคนทั่วไป (Customer, Order) ไม่ต้องทำ แต่ถ้าเป็นรหัสย่อ (KNA1, VBAK แบบ SAP) การทำ Fine-tune คุ้มค่า แต่ต้องแลกมาด้วย Maintenance Cost ที่ต้องทำใหม่ทุกครั้งที่ศัพทเปลี่ยนแปลง.

---

## 4. ⚡ Performance
**Current Status:** Sequential execution flow. Potential I/O bottlenecks.
**Goal:** Low latency and high throughput.

### 🔍 Analysis
- **Strengths:**
  - Schema Caching is implemented.
- **Weaknesses:**
  - `query_database` executes RAG retrieval, Prompting, and SQL execution sequentially.
  - `pd.read_sql` loads full result sets into memory.

### ✅ Action Items
- [x] **Async Parallelization:** Refactor `query_database` to use `asyncio.gather` for fetching "Example RAG" and "Schema RAG" concurrently. *(Completed — engine.py lines 293-296)*
- [ ] **Streaming Responses:** For large datasets, implement a paginated API or stream the JSON response instead of buffering the entire `df.to_dict()`.
- [ ] **Optimize Vector Search:** Ensure `chromadb` is running in a persistent server mode (not just embedded file mode) if concurrent users increase.

### ⚖️ Trade-off & Assessment Conditions
* **Async/Parallelism:**
    * *Condition:* Hardware (CPU/RAM) รองรับได้แค่ไหน?
    * *Trade-off:* การทำ Parallel แย่ง Resource กันเองในเครื่อง (Context Switch overhead) ถ้า CPU Core น้อย อาจจะช้าลงกว่าเดิม แต่ถ้าเครื่อง Server แรง จะเร็วกว่ามาก. นอกจากนี้ Code จะ Debug ยากขึ้น (Race Conditions).
* **Streaming Response:**
    * *Condition:* ข้อมูลที่ Query ส่วนใหญ่ขนาดใหญ่แค่ไหน?
    * *Trade-off:* ถ้าข้อมูล < 100 rows การทำ Streaming ไม่คุ้ม (Overhead HTTP chunking) แต่ถ้าข้อมูล > 10,000 rows การทำ Streaming คือสิ่งจำเป็นเพื่อป้องกัน Server Crash (OOM).

---

## 5. ✅ Correctness & Testing
**Current Status:** Basic unit tests present.
**Goal:** Reliability and regression prevention.

### 🔍 Analysis
- **Strengths:**
  - `eval/run_eval.py` exists for systematic accuracy testing.
- **Weaknesses:**
  - Unit tests now cover utilities, SQL safety, and config (31 tests).
  - No integration tests for the full API flow.

### ✅ Action Items
- [ ] **Integration Tests:** Add tests using `TestClient` (FastAPI) to simulate real `/query` requests with a mock LLM.
- [ ] **Golden Dataset:** Expand `thai_sql_examples.json` to include edge cases (Complex JOINs, Nested Queries) and use this as a regression test suite.
- [ ] **Error Logging:** Enhance `query_logs_sample.csv` recording to include "Reasoning" or "Error Category" for better analytics.

### ⚖️ Trade-off & Assessment Conditions
* **Strict Evaluation Pipeline:**
    * *Condition:* ต้องการความเป๊ะระดับไหน?
    * *Trade-off:* การทำ Automated Test กับ LLM ยากตรงที่ "คำตอบถูกเขียนได้หลายแบบ" (Semantic Equivalence) การเขียน Test ให้ฉลาดพอที่จะไม่ Fail แบบ False Positive ต้องใช้เวลา setup สูงมาก เทียบกับการ Manual Check สุ่มตรวจ.

---

## 6. 📉 Risk Management & Fallbacks
**Goal:** Handle failures gracefully when Local LLM or Database underperforms.

### 🔍 Risk Analysis
* **Risk:** Local LLM (Qwen-7B) hallucinating non-existent columns despite Schema RAG.
    * *Mitigation:* Implement "Schema Verification Layer" that cross-checks LLM output columns against `SchemaRAG` metadata *before* executing SQL.
* **Risk:** Complex Queries taking > 10s causing Timeout.
    * *Mitigation:* Implement client-side "Progress Updates" (via SSE/WebSocket) informing user ("Thinking...", "Checking Schema...", "Executing SQL...") to reduce perceived latency.
* **Risk:** Refactoring breaks existing functionality.
    * *Mitigation:* Apply **Strangler Fig Pattern**. Create `v2` services alongside `v1`. Switch traffic incrementally.

---

## 7. 📊 Success Metrics (KPIs)
**Goal:** Define quantifiable targets for the project.

### 🎯 Targets
1.  **Accuracy:** > 80% Execution Accuracy on `thai_sql_examples.json` (Golden Dataset).
2.  **Performance:**
    * Simple Query (Single Table): < 3 seconds.
    * Complex Query (Joins + RAG): < 8 seconds.
3.  **Security:** 100% Block rate for DROP/DELETE/UPDATE commands in regression tests.

---

## 8. 🎨 Frontend & User Experience
**Current Status:** Modular ES6 architecture with 7 modules. Collapsible sidebar implemented.
**Goal:** Modern, responsive, production-grade user interface.

### 🔍 Analysis
- **Strengths:**
  - **Modular Architecture:** Successfully refactored from 648-line God Object (`main.js`) into 7 focused modules:
    - `config.js`: Centralized configuration
    - `state.js`: Application state management
    - `utils.js`: Sanitization and formatting utilities
    - `api.js`: Backend communication
    - `feedback.js`: User feedback handling
    - `ui.js`: DOM manipulation and rendering
    - `chart.js`: Chart.js visualization
  - **Security:** XSS protection via sanitization on SQL output
  - **UX Features:** Collapsible sidebar with keyboard shortcuts (Ctrl/Cmd+B) and localStorage persistence
  - **Visualization:** Multi-series chart support with dynamic type selection
- **Weaknesses:**
  - **Limited Export Options:** Users cannot download results as CSV or export charts
  - **No Search/Filter:** History and Favorites tabs lack search functionality
  - **Loading States:** Minimal visual feedback during long queries
  - **Accessibility:** No ARIA labels, keyboard navigation incomplete

### ✅ Action Items
- [x] **Modularize Frontend:** Refactor God Object into focused modules *(Completed: 2026-01-18)*
- [x] **Collapsible Sidebar:** Implement toggle with keyboard shortcuts and state persistence *(Completed: 2026-01-22)*
- [x] **XSS Protection:** Sanitize SQL output to prevent script injection *(Completed: 2026-01-19)*
- [x] **Responsive Layout:** Implement CSS media queries and mobile-first design *(Completed — 3 breakpoints: 1023px, 767px, 479px with mobile drawer sidebar)*
  - Sidebar becomes drawer/overlay on mobile
  - Table horizontal scrolling for small screens
  - Touch-friendly button sizes (min 44px)
- [ ] **Export Features:**
  - CSV download for table results
  - PNG/SVG export for charts
  - Copy SQL query to clipboard (one-click)
- [ ] **Search & Filter:**
  - Add search input in History/Favorites tabs
  - Filter by date range, table name, or keywords
  - Sort by timestamp, relevance, or success/failure
- [ ] **Enhanced Loading States:**
  - Skeleton screens for table loading
  - Progress indicators with stages ("Analyzing...", "Executing SQL...", "Rendering...")
  - Toast notifications for success/error feedback
- [ ] **Accessibility (WCAG 2.1 AA):**
  - Add ARIA labels to all interactive elements
  - Full keyboard navigation (Tab, Arrow keys, Escape)
  - Screen reader announcements for dynamic content
  - Focus indicators and skip links
- [ ] **Theme System:**
  - Light/Dark mode toggle
  - User preference persistence
  - System preference detection (`prefers-color-scheme`)
- [ ] **Performance Optimization:**
  - Virtual scrolling for large tables (> 500 rows)
  - Lazy loading for chart libraries
  - Debounce search inputs
  - Code splitting for modules

### ⚖️ Trade-off & Assessment Conditions
* **Responsive Design:**
    * *Condition:* Target users ใช้ mobile/tablet บ่อยแค่ไหน?
    * *Trade-off:* การทำ Responsive เพิ่ม CSS complexity และต้อง Test หลาย device แต่ถ้า 30%+ ของ users ใช้ mobile การไม่ทำจะทำให้ UX แย่มาก.
* **Export Features:**
    * *Condition:* Users ต้องการเอาข้อมูลไปใช้ต่อหรือเปล่า?
    * *Trade-off:* Export เพิ่ม Dev time 1-2 วัน แต่เพิ่ม User value สูงมาก (ลด Manual Copy-Paste 100%) โดยเฉพาะในองค์กรที่ต้องทำ Report.
* **Accessibility:**
    * *Condition:* เป็น Enterprise/Government project ที่ต้อง comply กับ regulations หรือไม่?
    * *Trade-off:* A11y ใช้เวลา Dev เพิ่ม 20-30% แต่ถ้าเป็น mandatory requirement (เช่น Government contract) ต้องทำตั้งแต่แรก ถ้าไม่ใช่ สามารถเป็น Phase 2.
* **Virtual Scrolling:**
    * *Condition:* User Query ส่วนใหญ่ได้ผลลัพธ์กี่แถว?
    * *Trade-off:* ถ้าข้อมูล < 100 rows Virtual Scrolling เป็น overkill (เพิ่ม Complexity) แต่ถ้า > 1,000 rows Browser จะแฮงค์ถ้าไม่ทำ Virtual Scrolling.

---

## 9. ✅ Recently Completed (2026-01)
**Goal:** Track recent achievements and maintain momentum.

### 🎉 Achievements
- ✅ **Frontend Modularization** *(2026-01-18)*
  - Refactored 648-line `main.js` into 7 focused ES6 modules
  - Reduced coupling and improved maintainability
  - Added JSDoc annotations for window-exposed functions
- ✅ **Security Improvements** *(2026-01-19)*
  - Fixed XSS vulnerability in SQL output rendering
  - Implemented HTML sanitization for user-generated content
- ✅ **Code Quality** *(2026-01-19)*
  - Removed unused state setter functions
  - Added CI/CD workflow with automated testing
  - Documented public API with @public annotations
- ✅ **UX Enhancement** *(2026-01-22)*
  - Implemented collapsible sidebar with smooth animations
  - Added keyboard shortcut (Ctrl/Cmd+B) for toggle
  - Sidebar state persistence via localStorage
  - Fixed status badge positioning to prevent UI overlap
- ✅ **Code Quality Roadmap - Phase 1** *(2026-01-23)*
  - **API Error Handling:** Added `handleResponse()` helper function with consistent HTTP status checking
  - All 8 API functions now properly check `response.ok` before parsing JSON
  - Error messages now include backend `detail` or HTTP status for better debugging
  - **JSDoc Documentation:** Enhanced all modules with comprehensive documentation
  - Added `@throws` annotations for async functions that can fail
  - Added `@example` usage for complex functions like `renderChart()`
  - Documented detailed parameter types and data structures (e.g., config objects, QueryResponse)
- ✅ **Code Quality Roadmap - Phase 2: Security Hardening** *(2026-01-24)*
  - **Event Delegation:** Migrated all inline event handlers to centralized `handleAction()` pattern
  - Removed all 11 inline `onclick`/`onkeypress` handlers from `index.html`
  - Added `data-action` and `data-tab` attributes for declarative event routing
  - Created single document-level click listener with `e.target.closest('[data-action]')` delegation
  - Removed `exposeToWindow()` - no more global function pollution
  - Removed `escapeForOnclick()` utility - no longer needed with data attributes
  - Updated `feedback.js` function signatures (removed event parameters and `stopPropagation`)
  - **Security gains:** CSP-compatible (no `unsafe-inline`), eliminated XSS via inline handlers
- ✅ **Infrastructure Improvements** *(2026-01-24)*
  - **Centralized Configuration:** Moved all hardcoded values to `core/config.py` (SQL limits, RAG top_k, retry counts)
  - **Unit Testing:** Added 31 unit tests covering SQL Safety guards, Config validation, and Utility functions
- ✅ **Responsive Design** *(Date TBD)*
  - Added 3 CSS breakpoints (1023px, 767px, 479px) for tablet and mobile layouts
  - Sidebar becomes drawer overlay on mobile with backdrop
  - Touch-friendly button sizes (min 44px)
  - Dynamic viewport height (`100dvh`)
- ✅ **Async Performance** *(Date TBD)*
  - Implemented `asyncio.gather` for parallel Example RAG + Schema RAG retrieval in `engine.py`
- ✅ **Environment Template** *(Date TBD)*
  - Created `.env.example` with comprehensive documentation for all ENV vars

---

## 10. 🗓️ Roadmap & Prioritization
**Goal:** Define clear development phases and priorities.

### 📅 Q1 2026 (Current Quarter)
**Theme:** Stabilization & User Experience

#### High Priority (Sprint 1-2)
1. ✅ Frontend Refactoring (Completed)
2. ✅ XSS Security Fix (Completed)
3. ✅ Responsive Design (Completed)
4. 📋 Export Features (Planned)

#### Medium Priority (Sprint 3-4)
5. 📋 Search & Filter in History
6. 📋 Enhanced Loading States
7. 📋 API Authentication
8. 📋 Integration Tests

#### Low Priority (Sprint 5-6)
9. 📋 Theme System
10. 📋 Accessibility Improvements
11. 📋 Embedding Model Optimization

### 📅 Q2 2026
**Theme:** Performance & Scale

- ✅ Async Parallelization (Backend)
- Virtual Scrolling (Frontend)
- Vector Search Optimization
- ✅ Containerization (Docker) — Dockerfile & docker-compose.yml exist

### 📅 Q3 2026
**Theme:** Advanced Features

- Chain of Thought (CoT) Prompting
- Schema Verification Layer
- Advanced Analytics Dashboard
- Multi-user Support

---

## 11. 🏛️ Component Architecture
**Goal:** Comprehensive overview of system components and their responsibilities.

### 📦 Core Components

| Component | คำอธิบาย | ไฟล์หลัก | หน้าที่หลัก | ความยากง่าย | สถานะ |
|-----------|----------|----------|-------------|-------------|--------|
| **Web Frontend** | ส่วนหน้าเว็บที่ผู้ใช้เห็นและโต้ตอบ รวมถึงการแสดงกราฟและตาราง | `web/index.html`, `js/main.js`, `css/style.css` | UI, Chart.js rendering, API calls | ง่าย | ✅ เสร็จแล้ว |
| **FastAPI Server** | Backend API layer ที่รับ request จาก Frontend และส่งต่อไป Core Engine | `api/main.py`, `routes.py`, `schemas.py` | REST endpoints, request validation | ปานกลาง | ✅ เสร็จแล้ว |
| **NLPEngine (Core)** | หัวใจหลักของระบบ ประสานงานระหว่าง RAG, LLM, Validation และ Execution | `core/services/engine.py` | ประสานงานหลัก - รวม RAG + LLM + Validation | ยาก | ✅ เสร็จแล้ว |
| **RAG Store** | เก็บตัวอย่าง SQL ใน Vector DB และค้นหาตัวอย่างที่ใกล้เคียงกับคำถามผู้ใช้ | `core/data/rag_store.py` | ค้นหาตัวอย่าง SQL ที่ใกล้เคียง | ปานกลาง | ✅ เสร็จแล้ว |
| **Schema RAG** | เก็บ metadata ของ Database Schema ใน Vector DB เพื่อค้นหาตารางที่เกี่ยวข้อง | `core/data/schema_rag.py` | ค้นหาตารางที่เกี่ยวข้องกับคำถาม | ปานกลาง | ✅ เสร็จแล้ว |
| **Schema Utils** | เครื่องมือดึงโครงสร้าง Database และ filter ตารางที่ไม่เกี่ยวข้องออก | `core/domain/schema_utils.py` | ดึงและ filter database schema | ง่าย | ✅ เสร็จแล้ว |
| **SQL Safety** | ตรวจสอบ SQL ที่ LLM สร้างมาว่าปลอดภัยหรือไม่ ป้องกัน SQL Injection | `core/domain/sql_safety.py` | ป้องกัน SQL อันตราย (DROP, DELETE) | ง่าย | ✅ เสร็จแล้ว |
| **Viz Recommender** | วิเคราะห์ผลลัพธ์และแนะนำประเภทกราฟที่เหมาะสมอัตโนมัติ | `core/viz/viz_recommender.py` | แนะนำประเภทกราฟอัตโนมัติ | ปานกลาง | ✅ เสร็จแล้ว |
| **Query History** | บันทึกประวัติการถามคำถาม, feedback และ favorites | `core/services/query_history.py` | บันทึกประวัติและ feedback | ง่าย | ✅ เสร็จแล้ว |
| **Database Connection** | จัดการการเชื่อมต่อฐานข้อมูลหลายประเภท (SQLite, MySQL, PostgreSQL) | `core/data/database.py` | จัดการเชื่อมต่อฐานข้อมูล | ง่าย | ✅ เสร็จแล้ว |
| **Config** | ตั้งค่าระบบ เช่น เลือก LLM provider, กำหนด threshold ต่างๆ | `core/config.py` | Centralized settings (SQL Limits, RAG params, LLM Provider) | ง่าย | ✅ เสร็จแล้ว |

---

## 12. 📋 Task Breakdown by Feature
**Goal:** Detailed task list organized by functional area with ownership and status tracking.

### 🔧 Backend API

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| สร้าง API Endpoints | สร้าง /query, /connect, /schema, /history endpoints | `api/routes.py` | `query_endpoint()`, `connect_db()`, `get_schema()` | - | สูง | ✅ เสร็จแล้ว |
| Pydantic Models | สร้าง request/response validation models | `api/schemas.py` | `QueryRequest`, `QueryResponse`, `DatabaseConfig` | - | สูง | ✅ เสร็จแล้ว |
| Error Handling | จัดการ error responses ให้สวยงาม | `api/routes.py`, `web/js/modules/api.js` | HTTPException handlers, `handleResponse()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Rate Limiting | จำกัดจำนวน requests ต่อนาที | `api/main.py` | `slowapi.Limiter` | - | ต่ำ | ⏳ รอดำเนินการ |

### 🧠 NLP Engine

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Prompt Engineering | ออกแบบ prompt template สำหรับภาษาไทย | `core/services/engine.py` | `_create_prompt_template()`, template variable | - | สูง | ✅ เสร็จแล้ว |
| Self-Correction Loop | Retry เมื่อ SQL ผิดพลาด (สูงสุด 2 ครั้ง) | `core/services/engine.py` | `query_database()`, max_retries param | - | สูง | ✅ เสร็จแล้ว |
| SQL Cleaning | ทำความสะอาด SQL output จาก LLM | `core/services/engine.py` | `clean_sql()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Multi-LLM Support | รองรับ Ollama + OpenAI | `core/services/engine.py`, `core/config.py` | `_initialize_resources()`, `MODEL_PROVIDER` | - | ปานกลาง | ✅ เสร็จแล้ว |

### 📚 RAG System

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Example Store Setup | สร้าง ChromaDB สำหรับ SQL examples | `core/data/rag_store.py` | `ExampleStore` class, `_init_collection()` | - | สูง | ✅ เสร็จแล้ว |
| Thai SQL Examples | เพิ่มตัวอย่างคำถาม-SQL ภาษาไทย | `thai_sql_examples.json` | `examples[]` array | - | สูง | 🔄 กำลังทำ |
| Schema RAG | สร้าง Vector Store สำหรับ table metadata | `core/data/schema_rag.py` | `SchemaRAG` class, `index_schema_from_db()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Thai-English Mapping | สร้าง dictionary แปลคำไทย→English | `core/data/schema_rag.py` | `THAI_SCHEMA_MAPPINGS` dict | - | ปานกลาง | ✅ เสร็จแล้ว |

### 🔐 Security

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| SQL Validation | ตรวจสอบ SQL ก่อน execute | `core/domain/sql_safety.py` | `validate_and_sanitize_sql()` | - | สูง | ✅ เสร็จแล้ว |
| Read-Only Enforcement | บล็อก INSERT/UPDATE/DELETE/DROP | `core/domain/sql_safety.py` | `_DISALLOWED_NODE_TYPES` tuple | - | สูง | ✅ เสร็จแล้ว |
| LIMIT Enforcement | บังคับใส่ LIMIT ทุก query | `core/domain/sql_safety.py` | `_ensure_limit()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| User Authentication | ระบบ Login/Logout | `api/auth.py` (ใหม่) | (ยังไม่มี) | - | สูง | ⏳ รอดำเนินการ |

### 📊 Visualization

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Chart Type Recommender | เลือกประเภทกราฟอัตโนมัติ | `core/viz/viz_recommender.py` | `recommend_chart()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Column Detection | ตรวจจับ X/Y columns อัตโนมัติ | `core/viz/viz_recommender.py` | `_detect_metric_column()`, `_detect_dimension_column()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Chart.js Rendering | แสดงกราฟบน Frontend | `web/js/modules/chart.js` | `renderChart()`, `chartInstance` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Make a Graph Chart Look better | ทำให้หน้าตากราฟดูสวยขึ้น | `web/js/modules/chart.js` | - | - | ปานกลาง | ⏳ รอดำเนินการ |
| Export Chart as Image | ดาวน์โหลดกราฟเป็น PNG | `web/js/modules/chart.js` | (ยังไม่มี) | - | ต่ำ | ⏳ รอดำเนินการ |

### 🖥️ Frontend

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Main UI Layout | หน้าจอหลัก + chat interface | `web/index.html` | chat-container, message-input | - | สูง | ✅ เสร็จแล้ว |
| Dark Mode Styling | CSS สีเข้ม glassmorphism | `web/css/style.css` | :root variables, .glass class | - | ปานกลาง | ✅ เสร็จแล้ว |
| API Integration | เชื่อมต่อ FastAPI | `web/js/modules/api.js` | `sendMessage()`, `connectDB()`, `fetch()` | - | สูง | ✅ เสร็จแล้ว |
| Responsive Design | รองรับ Mobile/Tablet | `web/css/style.css` | @media queries (1023px, 767px, 479px) | - | ต่ำ | ✅ เสร็จแล้ว |
| Export Data (CSV) | ดาวน์โหลดผลลัพธ์เป็น CSV | `web/js/modules/ui.js` | (ยังไม่มี) | - | ปานกลาง | ⏳ รอดำเนินการ |

### 🗄️ Database Support

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| SQLite Support | รองรับ SQLite database | `core/data/database.py` | `create_engine()`, sqlite:/// | - | สูง | ✅ เสร็จแล้ว |
| MySQL Support | รองรับ MySQL database | `core/data/database.py` | mysql+pymysql:// | - | ปานกลาง | ✅ เสร็จแล้ว |
| PostgreSQL Support | รองรับ PostgreSQL | `core/data/database.py` | postgresql+psycopg2:// | - | ปานกลาง | ✅ เสร็จแล้ว |
| MS SQL Server | เพิ่มการรองรับ SQL Server | `core/data/database.py` | mssql+pyodbc:// | - | ต่ำ | ⏳ รอดำเนินการ |

### 📝 History & Feedback

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Query Logging | บันทึก log ทุก query | `core/services/query_history.py` | `QueryHistoryManager.log_query()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| User Feedback (👍/👎) | รับ feedback จากผู้ใช้ | `core/services/query_history.py` | `update_feedback()` | - | ปานกลาง | ✅ เสร็จแล้ว |
| Favorites System | บันทึก query ที่ชอบ | `core/services/query_history.py` | `add_favorite()`, `get_favorites()` | - | ปานกลาง | ✅ เสร็จแล้ว |

### 🧪 Testing

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Unit Tests | เขียน test สำหรับแต่ละ module | `tests/` | `test_sql_safety.py`, `test_config.py`, `test_common.py` | - | สูง | ✅ เสร็จแล้ว |
| Integration Tests | ทดสอบ end-to-end flow | `tests/` | test_integration.py | - | ปานกลาง | ⏳ รอดำเนินการ |

### 📄 Documentation

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| README.md | คู่มือติดตั้งและใช้งาน | `README.md` | Installation, Usage sections | - | สูง | ✅ เสร็จแล้ว |
| PRODUCT_SPEC.md | เอกสารสถาปัตยกรรมระบบ | `PRODUCT_SPEC.md` | Architecture, Components sections | - | ปานกลาง | ✅ เสร็จแล้ว |
| TUNING_GUIDE.md | คู่มือปรับแต่ง LLM | `TUNING_GUIDE.md` | Techniques, Evaluation sections | - | ปานกลาง | ✅ เสร็จแล้ว |

### 🚀 Advanced Features (อนาคต)

| งาน | รายละเอียด | ไฟล์ | Function / Variable | ผู้รับผิดชอบ | ความสำคัญ | สถานะ |
|-----|-----------|------|-------------------|-------------|----------|--------|
| Fine-tuning (LoRA) | Fine-tune โมเดลสำหรับภาษาไทย | `training/` (ใหม่) | (ยังไม่มี) | - | ต่ำ | ⏳ รอดำเนินการ |
| Multi-turn Conversation | จำบริบทการสนทนาก่อนหน้า | `core/services/engine.py` | ConversationMemory class | - | ต่ำ | ⏳ รอดำเนินการ |
| Query Caching | Cache ผลลัพธ์ query ที่ใช้บ่อย | `core/services/engine.py` | @lru_cache decorator | - | ต่ำ | ⏳ รอดำเนินการ |
| Scheduled Reports | สร้างรายงานอัตโนมัติ | (ใหม่) | APScheduler integration | - | ต่ำ | ⏳ รอดำเนินการ |

---

## 13. 📅 Development Timeline
**Goal:** Track project milestones and major achievements chronologically.

| วันที่ | งานที่ทำ | Commit หลัก | หมายเหตุ |
|--------|---------|------------|----------|
| **29 ธ.ค. 2025** | เริ่มต้นโปรเจกต์ | `Initial setup` | เริ่มต้น project structure |
| **30 ธ.ค. 2025** | Core Features | `feat(rag): persistent RAG storage`<br>`feat(safety): SQL guardrails`<br>`feat(schema): smart filtering`<br>`feat(viz): auto chart recommendation` | เพิ่ม RAG, Security, Viz |
| **31 ธ.ค. 2025** | History & Multi-LLM | `feat(history): query history manager`<br>`feat(llm): dual provider Ollama+OpenAI`<br>`docs: tuning guide` | เพิ่ม History, รองรับ OpenAI |
| **3 ม.ค. 2026** | Cleanup | `chore: update gitignore` | ทำความสะอาด codebase |
| **4 ม.ค. 2026** | Major Refactor | `refactor: migrate Streamlit → FastAPI`<br>`feat: modern web frontend`<br>`feat(tools): MySQL→SQLite converter` | เปลี่ยนจาก Streamlit เป็น FastAPI + Web |
| **5 ม.ค. 2026** | Cleanup | `chore: remove legacy .streamlit` | ลบ config เก่า |
| **9 ม.ค. 2026** | Polish & Docs | `feat(rag): MySQL examples`<br>`feat(prompt): dialect cheat sheet`<br>`feat(feedback): text feedback modal`<br>`docs: update all documentation` | เพิ่ม examples, ปรับปรุง prompt |
| **11 ม.ค. 2026** | Schema RAG | `feat(schema): Smart Schema Retrieval`<br>`feat(rag): distance threshold filtering`<br>`docs: update architecture docs` | เพิ่ม Schema RAG, ปรับแต่ง RAG |

**📊 สรุป:** ทำงานมา **8 วัน** (ประมาณ 1-2 สัปดาห์)

---

## 14. 📊 Progress Summary
**Goal:** Quantitative tracking of completion rates across all feature categories.

| หมวดหมู่ | เสร็จแล้ว | กำลังทำ | รอดำเนินการ | รวม | % เสร็จสิ้น |
|---------|----------|---------|-------------|-----|-------------|
| 🔧 Backend API | 3 | 0 | 1 | 4 | **75%** |
| 🧠 NLP Engine | 4 | 0 | 0 | 4 | **100%** ✅ |
| 📚 RAG System | 3 | 1 | 0 | 4 | **75%** |
| 🔐 Security | 3 | 0 | 1 | 4 | **75%** |
| 📊 Visualization | 3 | 0 | 2 | 5 | **60%** |
| 🖥️ Frontend | 4 | 0 | 1 | 5 | **80%** |
| 🗄️ Database Support | 3 | 0 | 1 | 4 | **75%** |
| 📝 History & Feedback | 3 | 0 | 0 | 3 | **100%** ✅ |
| 🧪 Testing | 1 | 0 | 1 | 2 | **50%** |
| 📄 Documentation | 3 | 0 | 0 | 3 | **100%** ✅ |
| 🚀 Advanced Features | 0 | 0 | 4 | 4 | **0%** |
| **รวมทั้งหมด** | **30** | **1** | **11** | **42** | **71%** |

### 📈 Key Insights
- ✅ **Core functionality complete:** NLP Engine, History & Feedback, Documentation at 100%
- 🎯 **Recent Wins:** Centralized Config, Unit Tests, Responsive Design, API Error Handling completed
- 🎯 **High completion areas:** Frontend at 80%, Backend API/Database/Security/RAG at 75%
- ⚠️ **Needs attention:** Integration Testing at 50%, Advanced Features at 0%
- 🚧 **Active development:** Thai SQL Examples currently in progress
- 📋 **Remaining work:** 11 tasks pending, primarily in Advanced Features and Visualization

---

## 15. 🎯 Prioritized Code Quality Roadmap
**Goal:** Actionable plan based on CodeFlow Report analysis (2026-01-23).
**Context:** Code review identified technical debt and security improvements needed.

### 📋 CodeFlow Report Findings Summary

**Report Status:**
- ✅ **4 False Positives:** SQL injection claims and eval() warnings were incorrect
- ✅ **XSS Fixed:** Already addressed in commit `2593328`
- ⚠️ **6 Valid Issues:** Require attention across security, architecture, and quality

**Overall Assessment:** Codebase is in good condition with recent security improvements. Priority focus on architecture and frontend hardening.

---

### ✅ Phase 1: Critical Quick Wins *(Completed: 2026-01-23)*
**Timeline:** 3-4 hours
**Strategy:** High value, low effort improvements that build foundation for future work

#### 1.1 Add API Error Handling ⚡
- **Effort:** 1-2 hours
- **Impact:** HIGH - Better error messages for users, easier debugging
- **Priority:** CRITICAL
- **Files:** `web/js/modules/api.js`
- **Issue:** 4 of 8 API functions lack HTTP status checks
  - `sendQuery()` (line 61-72) - ❌ No error checking
  - `fetchSchemaData()` (line 12-14) - ❌ No error checking
  - `fetchHistoryData()` (line 22-24) - ❌ No error checking
  - `fetchFavoritesData()` (line 31-34) - ❌ No error checking

**Action Plan:**
```javascript
// Create helper function
async function handleResponse(response) {
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// Apply to all API functions
export async function fetchSchemaData() {
    const res = await fetch(`${API_URL}/schema`);
    return handleResponse(res);
}
```

**Success Criteria:**
- [x] All API functions check `response.ok` before parsing *(Completed: 2026-01-23)*
- [x] Consistent error message format via `handleResponse()` helper *(Completed: 2026-01-23)*
- [x] User-friendly error displays in UI (throws Error with `detail` or HTTP status) *(Completed: 2026-01-23)*

---

#### 1.2 Complete JSDoc Documentation 📝
- **Effort:** 2 hours
- **Impact:** MEDIUM - Better developer experience, easier maintenance
- **Priority:** HIGH
- **Files:** `web/js/modules/*.js`, `web/js/main.js`
- **Status:** Partially complete (commit `56f4d3f` added basic JSDoc)

**Remaining Work:**
- [x] Document callback parameters *(Completed: 2026-01-23)*
- [x] Add `@throws` annotations for functions that can throw errors *(Completed: 2026-01-23)*
- [x] Add usage examples for complex functions (e.g., `renderChart()`) *(Completed: 2026-01-23)*
- [x] Document data structure formats (e.g., QueryResponse shape, viz config) *(Completed: 2026-01-23)*

**Example:**
```javascript
/**
 * Renders a chart using Chart.js
 * @param {Object} vizConfig - Visualization configuration
 * @param {string} vizConfig.chart_type - Chart type (bar, line, pie, etc.)
 * @param {string} vizConfig.x_column - Column name for X-axis
 * @param {string} vizConfig.y_column - Column name for Y-axis
 * @param {Array<Object>} data - Array of data objects
 * @throws {Error} If chart_type is not supported
 * @example
 * renderChart({ chart_type: 'bar', x_column: 'name', y_column: 'sales' }, data);
 */
```

---

### ✅ Phase 2: Security Hardening *(Completed: 2026-01-24)*
**Timeline:** 6-8 hours
**Strategy:** Eliminate XSS attack surface and enable Content Security Policy

#### 2.1 Migrate Inline Event Handlers to Event Delegation 🔒
- **Effort:** 6-8 hours
- **Impact:** HIGH - Eliminates XSS risk, enables CSP compliance
- **Priority:** HIGH
- **Files:** `web/js/modules/ui.js`, `web/index.html`

**Current Risk:**
- Inline `onclick` handlers with dynamic user content
- Uses `escapeForOnclick()` but still risky for CSP
- Found in: `ui.js` lines 168, 177-191, 220-226

**Refactoring Approach:**
```javascript
// BEFORE (Current - Risky):
historyContainer.innerHTML = `
    <div class="history-item" onclick="loadSQL('${escapedQuestion}', '${escapedSql}')">
        <button onclick="sendFeedback(event, '${item.log_id}', 'positive')">👍</button>
    </div>
`;

// AFTER (Event Delegation - Safe):
historyContainer.innerHTML = `
    <div class="history-item" data-question="${sanitize(item.question)}" data-sql="${sanitize(item.sql)}">
        <button data-action="loadSQL">Load</button>
        <button data-action="sendFeedback" data-log-id="${item.log_id}" data-type="positive">👍</button>
    </div>
`;

// Single event listener with delegation
historyContainer.addEventListener('click', (e) => {
    const action = e.target.dataset.action;
    if (action === 'loadSQL') {
        const item = e.target.closest('[data-question]');
        loadSQL(item.dataset.question, item.dataset.sql);
    } else if (action === 'sendFeedback') {
        sendFeedback(e, e.target.dataset.logId, e.target.dataset.type);
    }
});
```

**Action Items:**
- [x] Replace all `onclick="${...}"` with data attributes in `ui.js` *(Completed: 2026-01-24)*
- [x] Remove `escapeForOnclick()` function (no longer needed) *(Completed: 2026-01-24)*
- [x] Add single event listeners with delegation pattern *(Completed: 2026-01-24)*
- [x] Test all interactive elements (history, favorites, feedback buttons) *(Completed: 2026-01-24)*
- [x] Update `index.html` to remove inline handlers *(Completed: 2026-01-24)*
- [x] Update `feedback.js` - remove event parameters from `sendFeedback()` and `showFeedbackModal()` *(Completed: 2026-01-24)*
- [x] Update `main.js` - centralized `handleAction()` with switch/case routing *(Completed: 2026-01-24)*

**Benefits:**
- ✅ CSP compatible (no `unsafe-inline` needed)
- ✅ Eliminates escaping complexity
- ✅ Better performance (fewer event listeners)
- ✅ More maintainable code

---

### 🟢 Phase 3: Architecture Improvement
**Timeline:** 4-6 hours
**Strategy:** Reduce coupling in backend for better testability

#### 3.1 Refactor NLPEngine for Dependency Injection ⚙️
- **Effort:** 4-6 hours
- **Impact:** HIGH - Better testability, cleaner architecture, easier to maintain
- **Priority:** HIGH
- **File:** `core/services/engine.py`

**Current Issue:**
- `NLPEngine` directly creates dependencies (violates Dependency Inversion Principle)
- Tight coupling to 6+ core modules
- Difficult to test in isolation
- Hard to swap implementations

**Current Anti-Pattern:**
```python
# core/services/engine.py (Current)
class NLPEngine:
    def __init__(self):
        self.example_store = create_example_store()  # ← Creates dependency
        self.schema_rag = create_schema_rag()
        self.viz_service = create_viz_service()
        # ... more direct instantiations
```

**Recommended Refactoring:**
```python
# core/services/engine.py (Refactored)
class NLPEngine:
    def __init__(
        self,
        example_store: ExampleStore,
        schema_rag: SchemaRAG,
        viz_service: VizService,
        llm_client: LLMClient
    ):
        self.example_store = example_store
        self.schema_rag = schema_rag
        self.viz_service = viz_service
        self.llm_client = llm_client

# core/api/dependencies.py (Factory)
def get_nlp_engine() -> NLPEngine:
    return NLPEngine(
        example_store=create_example_store(),
        schema_rag=create_schema_rag(),
        viz_service=create_viz_service(),
        llm_client=create_llm_client()
    )
```

**Action Items:**
- [ ] Create interfaces/protocols for `ExampleStore`, `SchemaRAG`, `VizService`
- [ ] Update `NLPEngine.__init__()` to accept dependencies
- [ ] Update `core/api/dependencies.py` factory function
- [ ] Update all tests to inject mock dependencies
- [ ] Update `routes.py` to use new factory

**Benefits:**
- ✅ Easy to test (inject mocks)
- ✅ Easy to swap implementations (e.g., different RAG stores)
- ✅ Follows SOLID principles (Dependency Inversion)
- ✅ Clearer dependencies (explicit in constructor)

---

### 🔵 Phase 4: Future Enhancements
**Timeline:** 10-14 hours
**Strategy:** Long-term quality improvements (optional)

#### 4.1 Add Integration Tests 🧪
- **Effort:** 8-12 hours
- **Impact:** MEDIUM - Catch bugs earlier, prevent regressions
- **Priority:** MEDIUM
- **Status:** Currently 0% test coverage on frontend

**Test Framework Setup:**
```json
// package.json (new file needed)
{
  "devDependencies": {
    "vitest": "^1.0.0",
    "happy-dom": "^12.0.0"
  },
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui"
  }
}
```

**Test Coverage Goals:**
- [ ] API module: All fetch functions
- [ ] UI module: Message rendering, table rendering
- [ ] Chart module: Chart creation and updates
- [ ] State module: State mutations
- [ ] Critical user flows: Connection → Query → Visualization

**Example Test:**
```javascript
// tests/api.test.js
import { describe, it, expect, vi } from 'vitest';
import { sendQuery } from '../web/js/modules/api.js';

describe('API Module', () => {
  it('should handle successful query', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ sql: 'SELECT * FROM users' })
      })
    );

    const result = await sendQuery('show all users', 'sqlite');
    expect(result.sql).toBe('SELECT * FROM users');
  });
});
```

---

#### 4.2 Add Content Security Policy Headers 🛡️
- **Effort:** 2 hours
- **Impact:** MEDIUM - Defense-in-depth security
- **Priority:** LOW
- **Dependencies:** **MUST complete Phase 2 (Event Delegation) first**

**Implementation:**
```html
<!-- web/index.html -->
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self';
               script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
               style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
               font-src 'self' https://fonts.gstatic.com;
               img-src 'self' data:;
               connect-src 'self' http://localhost:8000;">
```

**Action Items:**
- [ ] Complete Phase 2 first (remove all inline event handlers)
- [ ] Add CSP meta tag to `index.html`
- [ ] Test all functionality with CSP enabled
- [ ] Configure FastAPI to send CSP headers
- [ ] Monitor CSP violations in browser console

**Note:** Cannot implement until inline handlers are removed (Phase 2).

---

## 16. 🗺️ Recommended Execution Sequence

### **Option A: Security-First Approach** (Recommended) ← Current Path
```
Week 1: ✅ Phase 1 (Quick Wins) → ✅ Phase 2 (Security)
Week 2: Phase 3 (Architecture) → Phase 4 (Optional)
Total: 13-18 hours core work + 10-14 hours optional
```

**Best for:** Production-ready codebase, compliance requirements

---

### **Option B: Quick Wins Only**
```
Focus: Just Phase 1 (3-4 hours)
Best for: Time-constrained, need immediate improvements
Result: Better error handling + complete documentation
```

**Best for:** MVP demos, rapid iterations

---

### **Option C: Frontend-Focused Sprint**
```
Day 1-2: Phase 1 (#1.1, #1.2) - 3-4 hours
Day 3-4: Phase 2 (#2.1) - 6-8 hours
Day 5: Phase 4 (#4.2) - 2 hours
Total: 11-14 hours, full frontend hardening
```

**Best for:** Frontend-heavy teams, CSP compliance needed

---

## 17. 📝 Next Actions

### Immediate (This Week)
1. ✅ **Code Review Completed** - Validated CodeFlow report findings *(2026-01-23)*
2. ✅ **Phase 1 Completed** - API error handling + JSDoc documentation *(2026-01-23)*
   - Added `handleResponse()` helper with HTTP status checking
   - Enhanced JSDoc with `@throws`, `@example`, detailed parameter types
   - All 8 API functions now have consistent error handling
3. ✅ **Phase 2 Completed** - Security hardening (Event Delegation) *(2026-01-24)*
   - Migrated all inline handlers to `data-action` attributes
   - Centralized event routing via `handleAction()` in `main.js`
   - Removed `escapeForOnclick()` and `exposeToWindow()`
   - CSP-ready: no more `unsafe-inline` requirement
4. 🎯 **Next: Phase 3** - Architecture refactoring (DI in NLPEngine)

### Short-term (Next 2 Weeks)
5. ⚙️ **Phase 3** - Refactor NLPEngine for Dependency Injection
6. 🛡️ **Phase 4.2** - Add Content Security Policy headers (now unblocked by Phase 2)

### Long-term (Q1 2026)
7. 🧪 **Phase 4.1** - Testing infrastructure (Vitest + integration tests)
8. 📊 **Measure Impact** - Track bug reduction, development velocity

---

## 18. 🏗️ Phase 3 Detailed Plan: NLPEngine Refactoring (DI + God Class Breakdown)

**Goal:** Break `NLPEngine` God Class into focused, testable services using Dependency Injection.
**Status:** 📋 Planned
**Timeline:** 6-8 hours
**Dependencies:** Phase 1 & 2 completed ✅ (no blocker)

### 🔍 Problem Analysis

`core/services/engine.py` (411 lines) is a **God Class** that handles too many responsibilities:

| Responsibility | Lines | Concern |
|---|---|---|
| LLM provider selection + initialization | 42-97 | Infrastructure |
| Prompt template creation | 108-184 | Prompt Engineering |
| Schema caching + indexing | 211-253 | Data Layer |
| Parallel RAG retrieval | 259-296 | RAG |
| LLM chain execution | 301-317 | Infrastructure |
| SQL validation + execution | 325-346 | Data Layer |
| Retry/correction loop | 348-409 | Error Recovery |
| Visualization recommendation | 343-344 | Visualization |

**Consequences:** Difficult to test (must mock 6+ modules), difficult to debug (must read 400+ lines), difficult to extend (must touch large file).

### ✅ Target Architecture

```
core/services/
├── engine.py              # NLPEngine — lightweight orchestrator (~80-100 lines)
├── llm_client.py          # LLMClient — provider selection + LLM invocation (~80 lines)
├── prompt_builder.py      # PromptBuilder — prompt template + RAG assembly (~100 lines)
├── sql_executor.py        # SQLExecutor — schema caching + SQL execution (~100 lines)
└── retry_manager.py       # RetryManager — retry loop + correction prompt (~80 lines)
```

### 📦 New Components

#### 1. `core/services/llm_client.py` — LLM Client Wrapper

**Extracted from:** `engine.py:42-97`
**Responsibility:** Provider selection, LLM initialization, invocation

```python
class LLMClient:
    """Wrapper around LangChain LLM with provider selection."""

    def __init__(self, provider: str = None):
        self._llm = self._create_llm(provider or settings.MODEL_PROVIDER)

    def _create_llm(self, provider: str):
        """Initialize LLM based on provider (ollama/openai/google/zhipu/openrouter)."""
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            return ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0,
                              api_key=settings.OPENAI_API_KEY)
        elif provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            if not settings.GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            return ChatGoogleGenerativeAI(model=settings.GOOGLE_MODEL, temperature=0,
                                          google_api_key=settings.GOOGLE_API_KEY,
                                          convert_system_message_to_human=True)
        elif provider == "zhipu":
            from langchain_openai import ChatOpenAI
            if not settings.ZHIPU_API_KEY:
                raise ValueError("ZHIPU_API_KEY not found in environment variables")
            return ChatOpenAI(model=settings.ZHIPU_MODEL, temperature=0,
                              api_key=settings.ZHIPU_API_KEY,
                              base_url="https://api.z.ai/api/coding/paas/v4")
        elif provider == "openrouter":
            from langchain_openai import ChatOpenAI
            if not settings.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY not found in environment variables")
            return ChatOpenAI(model=settings.OPENROUTER_MODEL, temperature=0,
                              api_key=settings.OPENROUTER_API_KEY,
                              base_url="https://openrouter.ai/api/v1")
        else:
            from langchain_ollama import ChatOllama
            return ChatOllama(model=settings.OLLAMA_MODEL, temperature=0,
                              base_url=settings.OLLAMA_BASE_URL)

    async def ainvoke(self, prompt: str) -> str:
        """Invoke LLM and return text response."""
        result = await self._llm.ainvoke(prompt)
        return result.content if hasattr(result, 'content') else str(result)

    def get_raw_llm(self):
        """Expose raw LangChain LLM for LCEL chain composition."""
        return self._llm
```

**Testing:** Mock by injecting a fake `LLMClient` that returns predetermined SQL.

---

#### 2. `core/services/prompt_builder.py` — Prompt Builder

**Extracted from:** `engine.py:108-184` + RAG formatting logic
**Responsibility:** Prompt template, RAG example retrieval, prompt variable assembly

```python
class PromptBuilder:
    """Builds prompts with RAG examples and schema context."""

    def __init__(self, example_store: ExampleStore, template: PromptTemplate = None):
        self._example_store = example_store
        self._template = template or self._default_template()

    @staticmethod
    def _default_template() -> PromptTemplate:
        """Create the default Thai NLP-to-SQL prompt template."""
        template = """You are an expert SQL analyst..."""  # Current template text
        return PromptTemplate.from_template(template)

    async def build_prompt_parts(
        self, question: str, dialect: str, schema_text: str, max_limit: int
    ) -> tuple:
        """
        Get RAG examples and format prompt variables.
        Returns: (prompt_vars_dict, rag_examples_count)
        """
        dynamic_examples, rag_count = await (
            self._example_store.async_format_examples_for_prompt_with_count(
                question,
                top_k=settings.RAG_TOP_K,
                dialect=dialect,
                threshold=settings.RAG_DISTANCE_THRESHOLD
            )
        )
        prompt_vars = {
            "dynamic_examples": dynamic_examples,
            "schema": schema_text,
            "dialect": dialect,
            "max_limit": max_limit,
        }
        return prompt_vars, rag_count

    def create_chain(self, llm):
        """Compose the LCEL chain: prompt | llm | StrOutputParser."""
        from langchain_core.output_parsers import StrOutputParser
        return self._template | llm | StrOutputParser()
```

**Testing:** Mock `ExampleStore` to verify prompt variable construction.

---

#### 3. `core/services/sql_executor.py` — SQL Executor

**Extracted from:** `engine.py:211-346`
**Responsibility:** Schema caching, Schema RAG indexing, SQL validation, SQL execution

```python
class SQLExecutor:
    """Handles schema caching, SQL validation, and database execution."""

    def __init__(self, example_store: ExampleStore):
        self._example_store = example_store
        self._current_engine: Engine = None
        self._schema_cache: dict = None
        self._schema_text_cache: str = None
        self._join_hints_cache: str = None
        self._all_tables_cache: list = None
        self._full_schema_text_cache: str = None
        self._schema_rag: SchemaRAG = None

    async def get_raw_schema(self, engine: Engine) -> dict:
        """Get database schema with caching. Re-fetches on engine change."""
        ...

    async def get_schema_text(self, engine: Engine, question: str,
                               llm=None) -> str:
        """Get filtered schema text for prompt (Ollama: smart filter, Cloud: full)."""
        ...

    async def get_all_tables(self, engine: Engine) -> list:
        """Get cached table list."""
        ...

    async def execute_sql(self, sql: str, engine: Engine, dialect: str,
                           max_limit: int, allowed_tables: list) -> tuple:
        """
        Validate and execute SQL query.
        Returns: (sanitized_sql, dataframe, error_message)
        """
        safe_sql_obj = validate_and_sanitize_sql(
            sql, dialect=dialect, max_limit=max_limit, allowed_tables=allowed_tables
        )
        df = await asyncio.to_thread(pd.read_sql, safe_sql_obj.sql, engine)
        return safe_sql_obj.sql, df, None

    def get_full_schema_text(self) -> str:
        """Get or lazily compute full schema text (for retry correction)."""
        ...
```

**Testing:** Mock `validate_and_sanitize_sql` and `pd.read_sql` to test caching behavior.

---

#### 4. `core/services/retry_manager.py` — Retry Manager

**Extracted from:** `engine.py:325-409`
**Responsibility:** Self-correction retry loop, error-type detection, correction prompt

```python
class RetryManager:
    """Manages the self-correction retry loop for failed SQL queries."""

    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client

    async def run_with_retries(
        self,
        sql: str,
        execute_fn,
        raw_schema: dict,
        full_schema_text_fn,
        dialect: str,
        max_retries: int
    ) -> tuple:
        """
        Execute SQL with retry loop.
        execute_fn: async callable(sql) -> (sql, df, error)
        full_schema_text_fn: callable() -> str (lazy)
        Returns: (sql, df_or_None, error_or_None, attempt_count)
        """
        full_schema_text = None

        for attempt in range(max_retries + 1):
            try:
                result_sql, df, error = await execute_fn(sql)
                if error is None:
                    return result_sql, df, None, attempt
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries:
                    if full_schema_text is None:
                        full_schema_text = full_schema_text_fn()
                    sql = await self._correct_sql(
                        sql, error_msg, full_schema_text, dialect
                    )
                else:
                    return sql, None, error_msg, attempt
        return sql, None, "Max retries exceeded", max_retries

    async def _correct_sql(self, failed_sql: str, error_msg: str,
                            schema_text: str, dialect: str) -> str:
        """Ask LLM to correct failed SQL based on error context."""
        is_table_error = any(p in error_msg.lower() for p in [
            "no such table", "table not found", "doesn't exist"
        ])
        is_column_error = any(p in error_msg.lower() for p in [
            "unknown column", "no such column", "column not found"
        ])

        if is_table_error or is_column_error:
            error_type = "table" if is_table_error else "column"
            correction_prompt = f"""The SQL query failed because it referenced a wrong {error_type}.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {failed_sql}

### Database Schema (with Foreign Key relationships):
{schema_text}

IMPORTANT: Check the [FK -> ...] annotations above.
Rewrite the query using ONLY the tables and columns listed above.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""
        else:
            correction_prompt = f"""The following SQL query failed with an error.

Target dialect: {dialect}
Error: {error_msg}
Failed SQL: {failed_sql}

### Database Schema (for reference):
{schema_text}

Please analyze the error and provide a corrected SQL query.
Return ONLY the corrected SQL query without any explanation or markdown.
Corrected SQL:"""

        corrected = await self._llm_client.ainvoke(correction_prompt)
        return corrected
```

**Testing:** Mock `LLMClient.ainvoke` to return predetermined corrections. Verify retry count and error handling.

---

#### 5. `core/services/engine.py` — Refactored Orchestrator

**Before:** 411 lines (God Class)
**After:** ~80-100 lines (Thin Orchestrator)

```python
class NLPEngine:
    """
    Main orchestrator for Thai NLP-to-SQL processing.
    Coordinates LLM, RAG, SQL execution, and visualization.
    """

    def __init__(
        self,
        llm_client: LLMClient = None,
        prompt_builder: PromptBuilder = None,
        sql_executor: SQLExecutor = None,
        retry_manager: RetryManager = None,
        viz_service: VizService = None,
        example_store: ExampleStore = None,
    ):
        # Dependency Injection: accept all dependencies or create defaults
        self._example_store = example_store or create_example_store()
        self._llm_client = llm_client or LLMClient()
        self._prompt_builder = prompt_builder or PromptBuilder(self._example_store)
        self._sql_executor = sql_executor or SQLExecutor(self._example_store)
        self._retry_manager = retry_manager or RetryManager(self._llm_client)
        self._viz_service = viz_service or create_viz_service(
            llm=self._llm_client.get_raw_llm(),
            enable_intelligent=settings.ENABLE_INTELLIGENT_VIZ
        )

    async def query_database(
        self,
        question: str,
        engine: Engine,
        dialect: str = "sqlite",
        max_limit: int = None,
        max_retries: int = None,
        preferred_chart_type: str = None
    ):
        """
        Main entry point: generate SQL and execute against DB.
        Returns: (sql, data_dict, error, retry_count, viz_config, rag_count)
        """
        if max_limit is None:
            max_limit = settings.MAX_SQL_LIMIT
        if max_retries is None:
            max_retries = settings.MAX_RETRIES

        # 1. Get schema (with caching)
        raw_schema = await self._sql_executor.get_raw_schema(engine)

        # 2. Get schema text for prompt
        schema_text = await self._sql_executor.get_schema_text(
            engine, question, self._llm_client.get_raw_llm()
        )

        # 3. Build prompt with RAG examples
        prompt_vars, rag_count = await self._prompt_builder.build_prompt_parts(
            question, dialect, schema_text, max_limit
        )

        # 4. Generate SQL via LLM
        chain = self._prompt_builder.create_chain(self._llm_client.get_raw_llm())
        chain_with_vars = chain.partial(**prompt_vars)
        try:
            response = await chain_with_vars.ainvoke({"question": question})
            sql = clean_sql_response(response, dialect)
        except Exception as e:
            return None, None, f"LLM Generation Failed: {str(e)}", 0, None, 0

        # 5. Execute with retries
        all_tables = await self._sql_executor.get_all_tables(engine)

        async def execute_fn(s):
            return await self._sql_executor.execute_sql(
                s, engine, dialect, max_limit, all_tables
            )

        sql, df, error, retry_count = await self._retry_manager.run_with_retries(
            sql, execute_fn, raw_schema,
            lambda: self._sql_executor.get_full_schema_text(),
            dialect, max_retries
        )

        # 6. Visualization + return
        if error or df is None:
            return sql, None, error, retry_count, None, rag_count

        result_data = df.to_dict(orient='records')
        viz_config = self._viz_service.recommend(df, question, preferred_chart_type)

        return sql, result_data, None, retry_count, viz_config, rag_count
```

### 📁 File Change Summary

| File | Change | Risk |
|------|--------|------|
| `core/services/llm_client.py` | **NEW** — LLM provider wrapper | Low |
| `core/services/prompt_builder.py` | **NEW** — Prompt + RAG assembly | Low |
| `core/services/sql_executor.py` | **NEW** — Schema caching + SQL execution | Medium |
| `core/services/retry_manager.py` | **NEW** — Retry loop + correction | Medium |
| `core/services/engine.py` | **REWRITE** — Thin orchestrator (~80 lines) | High |
| `api/dependencies.py` | **UPDATE** — Factory with DI | Low |
| `tests/unit/test_engine_di.py` | **NEW** — Tests for new services | None |

### 🛡️ Backward Compatibility

- `NLPEngine.query_database()` **signature unchanged** — same return type, same parameters
- `api/routes.py` **no changes needed** — calls `engine.query_database()` as before
- `NLPEngine()` **no-arg constructor still works** — creates default dependencies internally
- All downstream code (frontend, routes, dependencies) **unaffected**

### 📋 Execution Steps (Ordered)

| Step | Action | Effort | Test Gate |
|------|--------|--------|-----------|
| 1 | Create `llm_client.py` — move provider selection | 1 hr | Import succeeds, LLM initializes |
| 2 | Create `prompt_builder.py` — move template + RAG | 1 hr | Prompt variables generated correctly |
| 3 | Create `sql_executor.py` — move schema caching + execution | 1.5 hrs | Schema caching works, SQL executes |
| 4 | Create `retry_manager.py` — move retry loop | 1 hr | Retry logic works with mock LLM |
| 5 | Rewrite `engine.py` — thin orchestrator with DI | 1 hr | All existing tests pass |
| 6 | Update `api/dependencies.py` — factory with DI | 0.5 hr | Server starts, `/query` works |
| 7 | Run `pytest tests/ -v` — verify no regressions | 0.5 hr | All 31+ tests pass |
| 8 | Add `tests/unit/test_engine_di.py` — new service tests | 1.5 hrs | New tests pass |

**Total estimated effort: 8 hours**

### ✅ Success Criteria

- [ ] `NLPEngine` is under 100 lines (from 411)
- [ ] Each new service file has a single clear responsibility
- [ ] All dependencies are injectable via constructor
- [ ] All existing unit tests pass without modification
- [ ] `api/routes.py` requires no changes
- [ ] New unit tests cover each service with mocked dependencies
- [ ] Server starts and `/query` endpoint works end-to-end

### ⚖️ Trade-off & Assessment Conditions

* **Refactoring vs. Feature Development:**
    * *Condition:* ถ้าต้องส่ง Demo ภายใน 1 สัปดาห์ ให้เลื่อน Phase 3 ออกไปก่อน
    * *Trade-off:* เสียเวลา 8 ชม. แลกกับ maintainability ระยะยาว — bug fix เร็วขึ้น, เพิ่ม feature ง่ายขึ้น, test เขียนง่ายขึ้น
* **Strangler Fig Pattern:**
    * *Strategy:* สร้าง services ใหม่ทีละตัว, ย้าย logic ทีละส่วน, รัน test ทุก step — ไม่ต้อง rewrite ทีเดียวทั้งหมด