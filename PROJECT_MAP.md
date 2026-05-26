# PROJECT_MAP — SecureFlow AI
> Generated: 2026-05-25 | Auditor: Staff SE / Tech Lead | Status: Pre-planning

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

> **ASSUMPTION recorded:** Dev Crew (architect/developer/reviewer) has the same B3 pattern in
> `dev_orchestrator.py`. It is not audited in detail here but the same fix from M1 applies.
> Confirm before M1 work begins.
