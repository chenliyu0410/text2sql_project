# Public Offline Serving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish PowerQuery TW from this Windows computer through a stable HTTPS URL, with anonymous offline queries and shared authenticated access to data management and paid online mode configuration.

**Architecture:** Run a dedicated PowerQuery worker on loopback port 8766 with `OPENAI_API_KEY` removed at startup and a persistent shared strong administrator credential. Publish only that worker through Tailscale Funnel HTTPS port 8443 so the existing LH Funnel on HTTPS 443 remains untouched; an administrator may later provide an API key through the memory-only runtime settings UI.

**Tech Stack:** Windows PowerShell 5.1+, PowerQuery TW console entry point, Uvicorn, Tailscale Funnel

**Spec:** `PUBLIC_OFFLINE_SERVING.md`

## Global Constraints

- Keep both application workers bound to loopback; never bind Uvicorn to `0.0.0.0`.
- Preserve the LH project mapping on public HTTPS 443 and local port 8000.
- Public PowerQuery traffic uses HTTPS 8443 and local port 8766.
- The public worker must not inherit `OPENAI_API_KEY`.
- Public visitors may query anonymously; data management and paid runtime configuration require the shared administrator credential.
- Runtime logs remain local and are excluded from version control.
- Automated tests are not run because the requested change is limited to deployment configuration and the project workflow requires explicit permission before test execution.

---

### Task 1: Public offline service controller

**Files:**
- Create: `scripts/public_offline_service.ps1`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `.venv/Scripts/powerquery.exe`, `data/processed/power.db`, and the installed Tailscale CLI.
- Produces: `start`, `stop`, and `status` modes; a PID file; metadata; and local log files.

- [ ] **Step 1: Add fail-closed startup checks**

Require the executable, database, Tailscale, an unused local port, and an offline health response.

- [ ] **Step 2: Isolate the public process environment**

Clear `OPENAI_API_KEY`, generate an ephemeral administrator password, and allow administrator origins only from loopback.

- [ ] **Step 3: Publish the dedicated worker**

Run the worker on `127.0.0.1:8766`, wait for offline health, and configure `tailscale funnel --bg --https=8443 8766`.

- [ ] **Step 4: Add safe stop and status operations**

Turn off only HTTPS 8443 and stop only the PID whose executable matches the project console entry point.

### Task 2: Operator entry points and documentation

**Files:**
- Create: `公開離線啟動.bat`
- Create: `停止公開服務.bat`
- Create: `開機自動啟動-公開離線.bat`
- Create: `顯示公開管理密碼.bat`
- Create: `PUBLIC_OFFLINE_SERVING.md`

**Interfaces:**
- Consumes: the controller modes from Task 1.
- Produces: double-click launch and stop commands, an optional login-startup target, and recovery instructions.

- [ ] **Step 1: Add the interactive launch wrapper**

Invoke `-Mode start`, display the resulting public URL, and direct failures to the launcher log.

- [ ] **Step 2: Add stop and login-startup wrappers**

Expose a deliberate stop action and a non-interactive hidden startup target without installing it automatically.

- [ ] **Step 3: Document operation and diagnostics**

Describe the network mapping, offline boundary, log locations, startup shortcut procedure, and the correct diagnostic files to share.

### Task 3: Deploy the public endpoint

**Files:**
- Runtime output only: `.powerquery-public/`
- Runtime output only: `logs/`

**Interfaces:**
- Consumes: Task 1 controller and current Tailscale login.
- Produces: a running offline worker and public HTTPS URL.

- [ ] **Step 1: Start the public service**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\public_offline_service.ps1 -Mode start
```

Expected output contains `公開離線服務已啟動` and an HTTPS URL using port 8443.

- [ ] **Step 2: Record the operator commands**

Use `公開離線啟動.bat` for later starts and `停止公開服務.bat` to remove only the PowerQuery public endpoint.

Execution choice: inline execution, approved by the user on 2026-09-14.
