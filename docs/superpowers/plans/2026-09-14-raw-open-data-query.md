# Raw Open Data Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe raw-data query scope covering all downloaded Taipower resources while preserving the curated database as the default.

**Architecture:** A catalog database records manifest metadata and bounded schema previews. A focused service lazily reads rows from approved CSV, JSON, XML, and ZIP paths; FastAPI exposes public reads and an authenticated rebuild operation.

**Tech Stack:** Python 3.11, SQLite, FastAPI, standard-library CSV/JSON/XML/ZIP parsers, vanilla JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-14-raw-open-data-query-design.md`

## Global Constraints

- Keep `power.db` and its trusted views unchanged.
- Keep `trusted` as the default query scope.
- Do not copy raw payloads into the catalog database.
- Limit public row responses to 200 rows.
- Require the existing admin session and CSRF protection for catalog rebuilds.

---

### Task 1: Raw resource catalog and readers

**Files:**
- Create: `src/serving/raw_data.py`
- Create: `tests/test_raw_data.py`

**Interfaces:**
- Produces: `RawDataService.rebuild()`, `status()`, `list_resources()`, `read_rows()`, and `query()`.
- Consumes: `data/raw/manifest.json`, `data/raw/files`, and `data/raw/inbox`.

- [ ] **Step 1: Write failing catalog and reader tests**
- [ ] **Step 2: Run `pytest tests/test_raw_data.py -q` and confirm the module is missing**
- [ ] **Step 3: Implement manifest cataloging, safe path resolution, format readers, and raw query responses**
- [ ] **Step 4: Run `pytest tests/test_raw_data.py -q` and confirm all tests pass**

### Task 2: FastAPI integration and access control

**Files:**
- Modify: `src/serving/app.py`
- Modify: `src/serving/query_log.py`
- Test: `tests/test_raw_data.py`

**Interfaces:**
- Consumes: `RawDataService` methods from Task 1.
- Produces: `/api/raw/status`, `/api/raw/resources`, `/api/raw/resources/{resource_id}/rows`, `/api/raw/rebuild`, and `query_scope` on `/api/query`.

- [ ] **Step 1: Add failing public-read, raw-routing, and protected-rebuild API tests**
- [ ] **Step 2: Run the focused tests and confirm the routes or request field are absent**
- [ ] **Step 3: Wire the service into application state and add bounded endpoints**
- [ ] **Step 4: Include query scope in diagnostic logs and run the focused tests**

### Task 3: Public interface and operating instructions

**Files:**
- Modify: `src/serving/static/index.html`
- Modify: `src/serving/static/app.js`
- Modify: `PUBLIC_OFFLINE_SERVING.md`
- Test: `tests/test_serving.py`

**Interfaces:**
- Consumes: `query_scope` accepted by Task 2.
- Produces: a query-scope selector and documented inbox/rebuild workflow.

- [ ] **Step 1: Add frontend contract assertions for the selector and request field**
- [ ] **Step 2: Run the focused frontend contract test and confirm it fails**
- [ ] **Step 3: Add the selector, send `query_scope`, and document rebuild/promotion behavior**
- [ ] **Step 4: Run focused tests, then the complete test suite**
