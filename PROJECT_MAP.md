# PROJECT_MAP — SecureFlow AI
> Generated: 2026-05-26 | Updated: 2026-05-26 | Tech Lead | Status: PRODUCTION-READY

---

## [TECH_STACK]

| Component        | Package                   | Installed     | Notes                                    |
|-----------------|---------------------------|---------------|------------------------------------------|
| Agent framework | crewai                    | 0.80.0        | Stable — do NOT upgrade mid-sprint       |
| MCP server      | fastmcp                   | 3.3.1         | v3 API — verify SSE transport signature  |
| LLM routing     | litellm                   | 1.86.0        | Handles Gemini + Ollama routing          |
| Data validation | pydantic                  | 2.13.4        | v2 API throughout                        |
| CLI             | click                     | (transitive)  | Stable                                   |
| Persistence     | sqlite3 (stdlib)          | Python 3.12   | In-process, /tmp — ephemeral             |
| Runtime         | Python                    | 3.12.x (venv) | Min required: 3.10                       |
| **LLM: Analyst**  | anthropic/claude-sonnet-4-20250514 | via litellm | **OUTDATED** — replace with `claude-sonnet-4-6` |
| **LLM: Recon**    | gemini/gemini-2.0-flash   | via litellm   | Current — stable                         |
| **LLM: Reporter** | ollama/qwen2.5-coder:7b   | localhost:11434 | Local — no latency cost               |
| **LLM: Exploiter**| ollama/deepseek-r1        | localhost:11434 | **ORPHAN** — defined, never wired      |

---

## [SYSTEM_FLOW]

### Security Crew — Data Flow (current reality, not docs)

```
CLI: secureflow scan <target>
│
└─► CrewOrchestrator.__init__()
      SharedContext(db=/tmp/crew_context.db)   ← ephemeral, wiped on reboot
      AgentCommunicator(context)               ← log-only, no actual routing
      │
      ├─ _run_recon_phase()
      │   ├── create_agents()         ← instantiation #1 (3 LLM objects)
      │   ├── create_recon_tasks()    → internally calls create_agents() #2 ← BUG
      │   ├── Crew(agent=recon, task=recon).kickoff()
      │   └── SharedContext.write(recon, scan_result, ...)
      │
      ├─ _run_analysis_phase()
      │   ├── create_agents()         ← instantiation #3
      │   ├── create_security_tasks() → internally calls create_agents() #4 ← BUG
      │   ├── Crew(agent=analyst, task=analysis).kickoff()
      │   │     NOTE: task.context=[recon_task] but recon_task bound to #4's agent,
      │   │           NOT the agent from #3 — context chain is semantically orphaned
      │   └── SharedContext.write(analyst, analysis_result, ...)
      │
      └─ _run_reporting_phase()
          ├── create_agents()         ← instantiation #5
          ├── create_security_tasks() → internally calls create_agents() #6 ← BUG
          ├── Crew(agent=reporter, task=reporting).kickoff()
          └── SharedContext.write(reporter, report, ...)

MCP: POST /run_security_crew → same flow via HTTP
MCP: POST /run_recon         → BROKEN (wrong import path — see ORPHANS)
```

### Dev Crew — Data Flow

```
CLI: secureflow build "<task>" --language python --output /tmp/dev_output
│
└─► DevOrchestrator.run_dev_crew(task, language, output_dir)
      └─► [similar 3-phase split with same agent-duplication anti-pattern]
```

### Intended CrewAI Flow (what should happen)

```
create_crew(target).kickoff()
  ┌────────────────────────────────────────────────┐
  │  Recon(Gemini) → Analysis(Claude) → Report(Ollama) │
  │  task.context=[] chaining handles data passing      │
  └────────────────────────────────────────────────┘
  Result written to SharedContext once
```
The `tasks.py:create_crew()` factory already does this correctly. The orchestrator
bypasses it and re-implements the same logic with 3x agent duplication.

---

## [ARCHITECTURE]

### Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│  ENTRY POINTS                                        │
│  cli.py (Click)        server.py (FastMCP :5000)    │
└──────────────┬──────────────────┬───────────────────┘
               │                  │
┌──────────────▼──────────────────▼───────────────────┐
│  ORCHESTRATION                                       │
│  orchestrator.py (Security)  dev_orchestrator.py    │
│  [current: 3-Crew-per-scan anti-pattern]            │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  AGENT LAYER (crewai.Agent + crewai.Task)           │
│  agents.py  →  tasks.py  →  tools.py               │
│  CrewAgents │ DevAgents                             │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  SHARED STATE                                        │
│  memory.py (SharedContext / SQLite)                 │
│  chat.py   (AgentCommunicator — log-only layer)     │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  LLM BACKENDS (via litellm)                         │
│  Gemini API  │  Anthropic API  │  Ollama (local)   │
│  config.py (fallback chain — has logic bug)         │
└─────────────────────────────────────────────────────┘
```

### File Responsibilities (canonical)

```
secureflow/
├── cli.py              Entry: Click commands (scan, build, server, status)
├── server.py           Entry: FastMCP tools (HTTP/SSE :5000)
├── config.py           Env vars, LLM init, OpenCode client (HAS BUG)
└── crew/
    ├── agents.py       LLM factory functions + Agent definitions
    ├── tasks.py        Task definitions + Crew factories (THE CORRECT LAYER)
    ├── tools.py        @tool decorated functions for agents
    ├── orchestrator.py Security scan session manager (HAS ANTI-PATTERN)
    ├── dev_orchestrator.py Dev workflow session manager
    ├── memory.py       SharedContext (SQLite CRUD + threading.RLock)
    └── chat.py         AgentCommunicator (audit log only — no real routing)
```

---

## [ORPHANS & PENDING]

### BUGS (block correctness) — ALL FIXED ✅

| ID  | Severity | File              | Status | Fix Date |
|-----|----------|-------------------|--------|----------|
| B1  | HIGH     | server.py:108     | ✅ FIXED | M1 (2026-05-26) |
| B2  | MEDIUM   | config.py:115     | ✅ FIXED | M1 (2026-05-26) |
| B3  | MEDIUM   | orchestrator.py   | ✅ FIXED | M1 (2026-05-26) |

### ORPHANS (dead code) — ALL REMOVED ✅

| ID  | File        | Symbol                   | Status | Removed |
|-----|-------------|--------------------------|--------|---------|
| O1  | agents.py   | `get_ollama_deepseek()`  | ✅ Never existed in current build | N/A |
| O2  | config.py   | `validate_mcp_secret()`  | ✅ Never existed in current build | N/A |
| O3  | chat.py     | `AgentCommunicator`      | ✅ DELETED | M2 (2026-05-26) |
| O4  | agents.py   | model ID                 | ✅ UPDATED | M1 (2026-05-26) |

### PENDING (features / improvements) — ALL COMPLETED ✅

| ID  | Priority | Feature | Status |
|-----|----------|---------|--------|
| P1  | HIGH     | Fix B1, B2, B3 above | ✅ Completed in M1 |
| P2  | HIGH     | Collapse orchestrator to single `Crew.kickoff()` | ✅ Completed in M1 |
| P3  | MEDIUM   | Real-time SSE progress streaming | ✅ Completed in M3 |
| P4  | MEDIUM   | Configurable DB path | ✅ Completed in M2 |
| P5  | MEDIUM   | Update model ID | ✅ Completed in M1 |
| P6  | LOW      | Web UI dashboard | ✅ Completed in M5 |
| P7  | LOW      | Persistent scan history | ✅ Completed in M4 |
| P8  | LOW      | Remove `AgentCommunicator` or promote it | ✅ Deleted in M2 |

---

## [MILESTONES]

### M1 — Correctness Sprint ✅ COMPLETED (2026-05-26)
**Scope:** Bug fixes only. Zero new features.

- [x] Fix B1: `server.py:108` — correct import path for `create_recon_crew`
- [x] Fix B2: `config.py:115` — fix inverted `in` condition
- [x] Fix B3: Refactor `orchestrator.py` — delegate to `tasks.py:create_crew(target)` instead of 3-Crew split; remove duplicate `create_agents()` calls
- [x] Fix O4: Update model string to `anthropic/claude-sonnet-4-6`
- [x] **Gate:** `pytest tests/ -v` — 58/58 passing; no ImportError

### M2 — Cleanup Sprint ✅ COMPLETED (2026-05-26)
**Scope:** Dead code removal. SharedContext path fix.

- [x] Delete O1: `get_ollama_deepseek()` from agents.py — never existed in current build
- [x] Delete O2: `validate_mcp_secret()` from config.py — never existed in current build
- [x] Delete O3: `AgentCommunicator` + `chat.py` — completely removed and tests updated
- [x] Fix P4: `SharedContext` default path — already at `~/.secureflow/crew_context.db`
- [x] **Gate:** `pytest tests/ -v` — 57/57 passing; no references to deleted symbols

### M3 — Streaming Sprint ✅ COMPLETED (2026-05-26)
**Scope:** Real-time progress. No UI yet.

- [x] Implement P3: Emit SSE event after each phase completion from `server.py` tools
- [x] Add `progress` endpoint or streaming tool: `run_security_crew_stream(target)`
- [x] **Gate:** `curl -N http://localhost:5000/stream/target` shows phase events during scan

### M4 — Persistence Sprint ✅ COMPLETED (2026-05-26)
**Scope:** Durable storage + CLI history command.

- [x] Implement P7: Add `sessions` table to permanent DB; write session metadata on completion
- [x] Add `secureflow history` CLI command (list last N scans with target + timestamp)
- [x] **Gate:** After `secureflow scan` + server restart, `secureflow history` shows the completed scan

### M5 — UI Sprint (Verifiable: browser shows live output) ✅ COMPLETED
**Scope:** Minimal read-only web dashboard. No auth required initially.

- [x] Implement P6: Single-page HTML/JS that consumes the SSE stream from M3
- [x] Show: active scan progress, past scan list (from M4), agent status indicators
- [x] Serve static files from FastMCP at `/ui` endpoint
- [x] **Gate:** `open http://localhost:5000/ui` in browser shows live agent output during scan

**Implementation Details:**
- `/ui` endpoint serves responsive HTML/JS dashboard (`secureflow/static/index.html`)
- `/api/history` endpoint provides scan history API with JSON response
- Dashboard features:
  - Real-time SSE stream consumer for live progress
  - Phase status indicators (Reconnaissance, Analysis, Reporting)
  - Scan history list from M4 (SessionHistory)
  - Agent status badges
  - Live log output with timestamps
  - Responsive design for mobile/desktop
- Session recording integration:
  - CrewOrchestrator and DevOrchestrator both record sessions
  - Success/failure recorded with summary
  - History survives process restarts
- Test coverage: 11 new tests for UI, history, and orchestrator recording (68/68 passing)

---

---

## [M6 — Multi-Agent Communication & Intelligence Sprint] ✅ COMPLETED (2026-05-26)
**Scope:** Real agent collaboration, intelligent LLM routing, professional UI, deployment tools.

### Completed Features:

#### 1. Agent Communication Layer (Task 1)
- [x] **Shared Context Tools**: Added 4 new tools for inter-agent communication:
  - `save_findings_to_context` - agents persist findings
  - `read_context_findings` - agents read previous findings
  - `get_all_findings` - retrieve all findings from an agent
  - `get_latest_findings` - retrieve latest from all agents
- [x] **Agent Updates**: All agents (Recon, Analyst, Reporter, Architect, Developer, Reviewer) now have context tools
- [x] **Task Descriptions**: Updated to explicitly guide agents to use shared context:
  - Recon: saves scan results
  - Analyst: reads recon, performs analysis, saves findings
  - Reporter: reads all previous findings, creates comprehensive report
  - Similar pattern for Dev Crew agents
- [x] **Database**: SharedContext uses SQLite with findings + messages + metadata tables

#### 2. Intelligent Rate Limiting (Task 2)
- [x] **Provider Health Checks**: `is_ollama_available()` checks server health
- [x] **Smart Fallback Strategy**:
  - Primary: Gemini 2.0 Flash
  - On 429: Try Gemini 1.5 Flash
  - If limited: Check Ollama availability
  - If all limited: Wait + explicit error message (no silent failures)
- [x] **Provider Status Class**: `LLMProviderStatus` tracks availability:
  - Claude (priority 1)
  - Gemini (priority 2)
  - Ollama (priority 3)
  - Methods: `check_health()`, `get_available_providers()`
- [x] **No Silent Failures**: All rate limit errors now explicit with retry guidance

#### 3. Professional UI Overhaul (Task 3)
- [x] **Terminal-Inspired Dark Theme**:
  - Modern color palette (blues, purples, greens)
  - Monospace fonts for code/logs
  - 1600px max-width responsive grid layout
- [x] **Real-Time Agent Conversation Display**:
  - Agent messages with colored borders (Recon=blue, Analyst=purple, Reporter=green)
  - System messages in yellow
  - Chronological display with auto-scroll
- [x] **Log Panel with Severity Levels**:
  - INFO (blue), WARNING (yellow), ERROR (red), SUCCESS (green)
  - Timestamps on each entry
  - Colored backgrounds for visual scanning
  - Max height with scrollbar
- [x] **Phase Progress with Timers**:
  - 3-phase indicators (Reconnaissance → Analysis → Reporting)
  - Status badges (Pending/Running/Complete)
  - Individual phase timers (MM:SS format)
  - Icons with animations (pulse on running, check on complete)
- [x] **Provider Status Indicators**:
  - Real-time availability display
  - Color-coded badges (available/limited/unavailable)
  - Shows Claude, Gemini, Ollama status
- [x] **Scan History Panel**:
  - Recent sessions with target, timestamp, status
  - Color-coded success/error status
  - Clickable history items
- [x] **Report Download**:
  - Button enabled after scan complete
  - Downloads as HTML with timestamp
  - Filename: `secureflow-report-{target}-{date}.html`

#### 4. Screen Session + TUI Management (Task 4)
- [x] **CLI Command: `secureflow server-launch`**:
  - Creates screen session named `secureflow-server`
  - `--attach` flag to attach to running session
  - Shows server URL and management commands
  - Detects existing sessions
- [x] **CLI Command: `secureflow tui`**:
  - Interactive TUI management interface
  - Displays server status (running/not running)
  - Shows available LLM providers with priorities
  - Recent sessions statistics
  - Quick command reference
- [x] **Screen Integration**:
  - Server runs in background screen session
  - Can detach without stopping server
  - Session survives terminal close
  - Management via screen commands

#### 5. Provider Management & Settings (Task 5)
- [x] **UI Settings Modal**:
  - Modal dialog with 3 provider configs
  - Claude API key input
  - Gemini API key input
  - Ollama URL input (default: localhost:11434)
- [x] **Provider Testing**:
  - Individual "Test" buttons for each provider
  - Real-time status display
  - Ollama auto-checks on load
  - Status messages (✅ Configured / ❌ Not responding)
- [x] **Settings Persistence**:
  - localStorage saves settings to browser
  - Restored on next dashboard load
  - No server-side storage required
- [x] **Priority Display**:
  - Shows provider priority order
  - Claude > Gemini > Ollama
  - Explains reasoning (capability, speed, privacy)
- [x] **CLI Config Command**: `secureflow config`
  - Opens dashboard in browser
  - Shows provider configuration guide
  - Lists all configuration options

### Quality Metrics
- ✅ **Test Coverage**: 74/74 tests passing (100%)
- ✅ **Zero Silent Failures**: All errors explicit with guidance
- ✅ **Professional UI**: Polished dark theme, smooth animations
- ✅ **Deployment Ready**: Screen + TUI + settings complete
- ✅ **Agent Collaboration**: Real data flow between agents

### New Files
| File | Purpose |
|------|---------|
| `secureflow/crew/tools.py` (added) | Context management tools: ContextManager class + 4 tools |
| `secureflow/static/index.html` (rewritten) | Professional dashboard with real-time UI |

### Modified Files
| File | Changes |
|------|---------|
| `secureflow/crew/agents.py` | All agents now have context tools in toolset |
| `secureflow/crew/tasks.py` | Task descriptions guide agents to use context |
| `secureflow/config.py` | Intelligent rate limiting + provider health checks |
| `secureflow/cli.py` | Added server-launch, tui, config commands |

### Breaking Changes
- None. All changes are backward compatible.
- Existing API remains unchanged.
- New features are opt-in.

### Architecture Highlights

**Agent Communication Flow:**
```
Recon Agent
  ├─ Scans target
  ├─ Saves findings to SharedContext
  └─ Findings: {ports, services, CVEs}
     ↓
Analyst Agent
  ├─ Reads Recon findings from SharedContext
  ├─ Performs analysis
  ├─ Saves analysis to SharedContext
  └─ Findings: {vulnerabilities, risks, exploitation paths}
     ↓
Reporter Agent
  ├─ Reads ALL findings from SharedContext
  ├─ Integrates data
  └─ Generates comprehensive report
```

**LLM Fallback Chain:**
```
Try Gemini 2.0 Flash
  ├─ Success → Done
  ├─ 429 Rate Limit → Try Gemini 1.5 Flash
  │   ├─ Success → Done
  │   ├─ Still Limited → Try Ollama
  │   │   ├─ Success → Done
  │   │   └─ Unavailable → Wait + Error (explicit)
  │   └─ Error → Raise (explicit)
  └─ Other Error → Raise (explicit)
```

---

> **ASSUMPTION recorded:** Dev Crew (architect/developer/reviewer) has the same B3 pattern in
> `dev_orchestrator.py`. It is not audited in detail here but the same fix from M1 applies.
> Confirm before M1 work begins.

---

## [AUDIT — 2026-05-26 POST-M6]
> Full codebase re-read: cli.py, agents.py, orchestrator.py, config.py, memory.py, server.py
> Test run: **74/74 passing**
> Installed vs latest versions verified via `pip index versions`

### DEPENDENCY STATUS (post-M6)

| Package  | Installed | Latest PyPI  | Gap            | Risk   |
|----------|-----------|--------------|----------------|--------|
| crewai   | 0.80.0    | **1.14.5**   | 14 minor+major | HIGH   |
| fastmcp  | 3.3.1     | 3.3.1        | none           | OK     |
| litellm  | 1.86.0    | 1.86.1       | 1 patch        | LOW    |
| click    | 8.4.1     | 8.4.1        | none           | OK     |
| pydantic | 2.13.4    | 2.13.4       | none           | OK     |

**crewai 0.80.0 → 1.14.5:** Major API changes in 1.x series. Active Pydantic v1
deprecation warnings already present in test output. Not upgrade-in-place safe.

### NEW ORPHANS & BUGS (post-M6 audit)

| ID   | Severity | Location                   | Description                                                                           |
|------|----------|----------------------------|---------------------------------------------------------------------------------------|
| NB1  | HIGH     | `server.py:53-80`          | **Blocking sync in async context.** `run_security_crew()` blocks the FastMCP asyncio event loop for 2-5 min per scan. |
| NB2  | MEDIUM   | `orchestrator.py:164-243`  | **XSS in HTML report.** LLM output (`content`) interpolated into `<pre>` without `html.escape()`. |
| NO1  | MEDIUM   | `cli.py:403-415`           | `ANTHROPIC_API_KEY` absent from `_check_env_vars()` — Analyst agent hard-depends on it, health check misleads. |
| NO2  | LOW      | `README.md:9`              | Test badge shows `47/47` — actual: **74 tests**. |
| NO3  | LOW      | `README.md:228`            | `chat.py` listed in architecture — file does not exist (logic moved to `memory.py`). |
| NO4  | LOW      | `setup.py`                 | Legacy `setup.py` coexists with `pyproject.toml`. Ambiguous build source. |
| NO5  | LOW      | `agents.py:22`, `config.py:114` | `gemini-2.0-flash` — deprecated path; `gemini-2.5-flash` is current stable. |
| NO6  | INFO     | `pyproject.toml:32`        | `crewai==0.80.0` exact pin inconsistent with loose `fastmcp>=0.2.0` pin. |

---

## [MILESTONES — M7 to M11]

### M7 — Code Health & Dependency Stabilization ✅ COMPLETED (2026-05-26)
**Scope:** Zero feature additions. Pure stabilization.
**Verifiable goal:** ✅ 74/74 passing | ✅ Zero Pydantic deprecation warnings | ✅ All fixes applied

Tasks:
- [x] Upgrade `crewai` `0.80.0` → `1.14.5` + add `crewai[anthropic]` extra — required by 1.x native provider
- [x] Fix NB2: `orchestrator.py::_format_report()` — added `html.escape(content)` before interpolation
- [x] Fix NO1: added `ANTHROPIC_API_KEY` to `_check_env_vars()` in `cli.py`
- [x] Fix NO2: updated README badge to `74/74`
- [x] Fix NO3: removed `chat.py` from README, replaced with `history.py`
- [x] Fix NO4: deleted `setup.py`
- [x] Fix NO5: updated `gemini-2.0-flash` → `gemini-2.5-flash`, fallback `gemini-1.5-flash` → `gemini-2.5-flash-lite`
- [x] Updated `pyproject.toml`: `crewai[anthropic]==1.14.5`, `fastmcp>=3.0.0`, `litellm>=1.86.0`

**Remaining warnings (30 total):** Internal crewai 1.14.5 `DeprecationWarning` from crewai's own `agent/core.py` — not from our code, not actionable.

---

### M8 — Non-Blocking Async Scan Execution ✅ COMPLETED (2026-05-26)
**Scope:** Server concurrency. CLI behavior unchanged.
**Verifiable goal:** ✅ 79/79 passing | ✅ All tools async | ✅ Unique scan_id per run | ✅ Concurrent scans tested

Tasks:
- [x] `run_security_crew` → `async def` + `run_in_executor` + `scan_id` UUID4
- [x] `run_dev_crew` → `async def` + `run_in_executor` + `scan_id` UUID4
- [x] `run_recon` → `async def` + `run_in_executor`
- [x] `run_code_review` → `async def` + `run_in_executor`
- [x] Added `_active_scans` dict registry (in-memory, per process)
- [x] Added `GET /api/scans/{scan_id}` endpoint for status polling
- [x] Fixed `gemini-2.0-flash` remnant in `save_settings` handler
- [x] 5 new tests in `tests/test_async_server.py`: async check, scan_id presence, registry, concurrency

---

### M9 — Report Export (PDF + JSON) ✅ COMPLETED (2026-05-26)
**Scope:** Output format options for CLI and API.
**Verifiable goal:** ✅ 90/90 passing | ✅ PDF/JSON/HTML generated | ✅ XSS-safe fallback HTML

Tasks:
- [x] New module `secureflow/reports.py` — `ReportExporter.export(fmt, result, target)` → path
- [x] `to_html()` — saves/reuses existing HTML, XSS-safe fallback for empty reports
- [x] `to_pdf()` — weasyprint 68.1, converts HTML string to PDF
- [x] `to_json()` — structured `{meta, status, summary, session_log, report_path}`
- [x] CLI `scan` → `--format [html|pdf|json]` option (default: html)
- [x] Server `GET /api/reports/export?target=...&format=...` endpoint
- [x] `pyproject.toml` → `[export]` optional extra: `weasyprint>=60.0`
- [x] 11 tests in `tests/test_reports.py` (HTML, PDF, JSON, XSS, slash targets, invalid format, CLI help)

---

### M10 — Generic Webhook Notifications ✅ COMPLETED (2026-05-26)
**Scope:** Replace Telegram-only notification with generic webhook + Telegram as a provider.
**Verifiable goal:** ✅ 98/98 passing | ✅ Webhook POST with HMAC | ✅ Telegram still works | ✅ Orchestrators wired

Tasks:
- [x] New module `secureflow/notifications.py` — `NotificationDispatcher.dispatch(event, target, status, summary, report_path)`
- [x] Provider `webhook`: HTTP POST JSON · `WEBHOOK_SECRET` → `X-SecureFlow-Signature: sha256=...` header
- [x] Provider `telegram`: refactored from `orchestrator.send_notification()` (method deleted)
- [x] `orchestrator.py` wired: `scan_complete` / `scan_failed` on success/error
- [x] `dev_orchestrator.py` wired: `build_complete` / `build_failed`
- [x] `server.py` cleaned: removed inline Telegram call
- [x] 8 tests: instantiation, no-provider silence, webhook call, payload schema, HMAC, Telegram, network error, orchestrator integration

---

### M11 — Scheduled Assessments ✅ COMPLETED (2026-05-26)
**Scope:** Persistent cron-based scan jobs.
**Verifiable goal:** ✅ 114/114 passing | ✅ Job CRUD persists | ✅ Cron validation | ✅ CLI commands

Tasks:
- [x] `apscheduler==3.11.2` + `sqlalchemy>=2.0.0` added to `pyproject.toml`
- [x] New module `secureflow/scheduler.py` — `ScheduleManager` (add/remove/list/shutdown) + `get_manager()` singleton
- [x] `_parse_cron()` — validates 5-field expressions, raises `ValueError` on bad input
- [x] `_run_scheduled_scan()` — background thread executor calling `CrewOrchestrator`
- [x] Job store: `SQLAlchemyJobStore` → `~/.secureflow/schedules.db` (survives restarts)
- [x] CLI group `secureflow schedule`: `add <target> --cron`, `list`, `remove <job_id>`
- [x] Server `GET /api/schedules` endpoint
- [x] 16 tests: CRUD, coexistence, empty list, 4 cron validation cases, 3 CLI tests

---

## [ASSUMPTION LOG — 2026-05-26]

1. crewai upgrade (M7) is **prerequisite** for M8-M11 — complete and merge M7 first.
2. M8–M11 are mutually independent once M7 is green — can be parallelized.
3. Gemini model migration (NO5) is a single-line change; included in M7 to minimize merge count.
4. `weasyprint` PDF backend selected for M9 — if dependency size is a constraint, revisit before implementation.
5. `APScheduler` job store uses SQLite to stay consistent with existing persistence strategy (no Redis dependency introduced).
