# SecureFlow

**AI-powered penetration testing framework with multi-agent collaboration**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/C0R3DMP/secureflow/actions/workflows/ci.yml/badge.svg)](https://github.com/C0R3DMP/secureflow/actions/workflows/ci.yml)
[![Tests: 253 passing](https://img.shields.io/badge/tests-253%20passing-brightgreen)](#testing)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)](#project-status)

SecureFlow is an AI-powered security assessment and application development platform. Multi-agent teams (Recon, Analyst, Reporter) collaborate via shared context to execute penetration tests. Supports Claude, Gemini, OpenRouter and Ollama as LLM providers.

## Features

### 🔒 Security Assessment Workflow
- **Recon Agent** — Network reconnaissance, port scanning, CVE discovery via nmap (falls back to a built-in socket scanner if nmap isn't installed)
- **Analyst Agent** — Vulnerability analysis, exploitability assessment, attack chain identification
- **Reporter Agent** — Executive reporting, CVSS scoring, 90-day remediation roadmap
- CVE lookup queries both **NVD** (CPE-matched) and **OSV** (package-matched), merged and deduplicated — either alone has real coverage gaps

### 💻 Development Workflow
- **Architect Agent** — System design, tech stack selection, project structure planning
- **Developer Agent** — Production code generation, feature implementation
- **Reviewer Agent** — Code quality review via real AST-based static analysis (bug detection, hardcoded secrets, injection patterns), not simulated output

### 💬 Ask AI
- Chat directly with the configured LLM about an assessment, from the dashboard
- Answers are grounded in that scan's stored findings and CVSS severity tally
- Streams token by token over SSE, with a stop control
- Runs on the same provider chain as the crew (Gemini → OpenRouter → Ollama → Claude), and scan data fed into the prompt is explicitly fenced as untrusted input

### 🖥️ Dashboard
- Live agent activity, event log with level filters, and phase progress
- Severity summary derived from real CVSS scores (NVD + OSV)
- In-app report preview (rendered in a sandboxed iframe) plus download
- Light and dark themes; keyboard shortcut `⌘K` / `Ctrl+K` to focus the target field

### 🎯 Core Capabilities
- Multi-agent collaborative workflows with shared context
- FastMCP server with SSE real-time streaming
- CLI interface (`secureflow --help`)
- Report export (HTML, PDF, JSON)
- Webhook notifications (HMAC-signed) & scheduled scans
- 253 automated tests, run in CI on every push and pull request

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/C0R3DMP/secureflow.git
cd secureflow
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your API keys (see Configuration section)
```

### 3. Run
```bash
# CLI security assessment
secureflow scan example.com

# Web dashboard
secureflow server   # Visit http://localhost:5000/ui
```

## Configuration

### Environment Variables

`cp .env.example .env` and fill in what you need — every value is optional except
that you need at least one LLM provider configured:

```bash
# Server auth — see Security section below
MCP_SECRET=                          # openssl rand -hex 32
SECUREFLOW_HOST=127.0.0.1            # loopback by default; override deliberately
SECUREFLOW_PORT=5000

# LLM providers — configure at least one (tried in this priority order)
GEMINI_API_KEY=                      # priority 1, free tier: 5 req/min
OPENROUTER_API_KEY=                  # priority 2, free models available
OLLAMA_BASE_URL=http://localhost:11434   # priority 3, local, no key needed
ANTHROPIC_API_KEY=                   # priority 4

# Optional
OPENCODE_URL=http://localhost:4096   # auto-started if the `opencode` binary is present
TELEGRAM_BOT_TOKEN=                  # for scan-complete notifications
TELEGRAM_CHAT_ID=
```

See `.env.example` for the full, commented list.

### LLM Provider Priority

SecureFlow tries providers in this order and uses the first one available:

1. **Gemini API** (5 req/min free tier) — `GEMINI_API_KEY`
2. **OpenRouter** (free models, no rate limit on the free tier) — `OPENROUTER_API_KEY`
3. **Ollama** (local, free) — run `ollama run qwen2.5-coder` first
4. **Claude API** — `ANTHROPIC_API_KEY`

Note: Claude Code CLI / Gemini CLI are not part of this fallback chain — CrewAI's
`LLM` class needs an API-compatible provider, and a locally installed CLI tool
isn't one. `pip install -e ".[dev]"` doesn't need any of these keys to run the
test suite.

## Security

SecureFlow launches network scans on demand, so an exposed instance is a remote
scanning proxy for whoever can reach it. The server is built to fail closed.

- **Authentication.** Every `/api/*`, `/stream/*` and MCP transport route requires
  a bearer token. Only the static dashboard under `/ui` is public (it does
  nothing without API access). If `MCP_SECRET` is unset, the server generates an
  ephemeral token at startup and prints it, rather than running unauthenticated.
  Set `SECUREFLOW_ALLOW_ANONYMOUS=1` to run with no auth (local development only).

  ```bash
  curl -H "Authorization: Bearer $MCP_SECRET" http://localhost:5000/api/history
  # SSE: EventSource can't set headers, so the token also works as a query param
  curl -N "http://localhost:5000/stream/example.com?token=$MCP_SECRET"
  ```

  The dashboard reads `?token=...` on first load and remembers it in `localStorage`.

- **Network exposure.** The server binds `127.0.0.1:5000` by default. Override
  deliberately with `SECUREFLOW_HOST=0.0.0.0`. If you containerize SecureFlow,
  the container's loopback is not reachable from the host, so bind
  `SECUREFLOW_HOST=0.0.0.0` *inside* the container and let Docker's own
  `-p 5000:5000` publish it — the container boundary is the real perimeter, not
  the process's bind address.

- **Target validation.** Scan targets must be a hostname, IPv4/IPv6 address,
  CIDR network, or URL. Values beginning with `-`, or containing shell/argv
  metacharacters, are rejected before reaching `nmap` — this closes an
  argument-injection path (`--script=…`, `-oN …`).

- **Prompt injection.** Service banners and page content collected during a scan
  come from the target being assessed and are treated as untrusted data when fed
  into the chat assistant's context — fenced, labelled as data, and never able
  to close its own fence early.

- **Other properties.** No credentials in logs or session files. SQLite storage
  for findings (local-only by default). HMAC-SHA256 webhook signing. HTML
  reports are escaped before rendering.

- **Scope.** Only scan systems you are authorised to test. Automated scanning of
  third-party infrastructure without permission is illegal in most jurisdictions.

## CLI Commands

| Command | Description |
|---------|-------------|
| `secureflow scan <target> [--format html\|pdf\|json]` | Run full security assessment |
| `secureflow build <task> [--language X] [--output DIR]` | Generate application code |
| `secureflow history [--limit N] [--type security\|dev]` | View past scan/build sessions |
| `secureflow schedule add <target> --cron "..."` | Schedule a recurring scan |
| `secureflow schedule list` | List scheduled scans |
| `secureflow schedule remove <job_id>` | Remove a scheduled scan |
| `secureflow server` | Start the MCP server (port 5000) |
| `secureflow server-launch [--attach]` | Launch the server in a monitored `screen` session, auto-restarting on failure |
| `secureflow status` | Check dependencies and provider health |
| `secureflow config` | Configure providers interactively |
| `secureflow tui` | Interactive TUI management interface |
| `secureflow --help` | Show all commands |

Fast recon-only scanning and standalone code review are available as MCP tools
(`run_recon`, `run_code_review`) and from the dashboard, but are not exposed as
separate CLI subcommands today.

## API

FastMCP exposes two different kinds of surface — they are not interchangeable:

**HTTP routes** — plain REST, curl-able directly:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ui` | Web dashboard |
| GET | `/stream/{target}` | SSE scan-progress stream |
| POST | `/api/chat` | Chat with the LLM about a scan (SSE token stream) |
| GET | `/api/providers` | LLM/OpenCode provider availability |
| GET | `/api/scans/{scan_id}` | Poll an in-flight scan's status |
| GET | `/api/history` | Scan history (JSON) |
| GET | `/api/schedules` | List scheduled scans |
| GET | `/api/reports/export?target=X&format=html\|pdf\|json` | Export a completed report |
| POST | `/api/settings` | Persist provider settings to `~/.secureflow/.env` |
| POST | `/api/opencode/start` \| `/api/opencode/stop` | Control a local OpenCode server |

**MCP tools** — invoked over the MCP protocol (SSE transport) by an MCP client,
not by a plain HTTP POST to a `/tools/...` path:

| Tool | Description |
|------|-------------|
| `run_security_crew` | Full assessment: recon → analysis → reporting |
| `run_security_crew_stream` | Same, with MCP progress notifications |
| `run_recon` | Recon-only, fast |
| `run_dev_crew` | Architect → developer → reviewer code generation |
| `run_code_review` | Standalone code review |
| `crew_status` | Health check / capability list |

## Architecture

### Security Assessment Workflow
```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: RECONNAISSANCE (Recon Agent)                    │
│  • nmap scan (socket-scan fallback if nmap unavailable)  │
│  • Service version detection                             │
│  • CVE lookup per service (NVD + OSV)                    │
│  └─→ Save to SharedContext: scan_results                 │
└──────────────────┬────────────────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────────────────┐
│ Phase 2: ANALYSIS (Analyst Agent)                          │
│  • Read recon findings                                     │
│  • Assess exploitability per service                       │
│  • Identify attack chains & lateral movement                │
│  • Rate: CRITICAL | HIGH | MEDIUM | LOW                     │
│  └─→ Save to SharedContext: vulnerability_analysis          │
└──────────────────┬────────────────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────────────────┐
│ Phase 3: REPORTING (Reporter Agent)                        │
│  • Executive summary (non-technical)                        │
│  • Detailed findings table                                  │
│  • 90-day remediation roadmap                                │
│  └─→ Return: report_html (rendered in-app, downloadable)     │
└──────────────────────────────────────────────────────────────┘
```

### Development Workflow
```
ARCHITECTURE → (shared context) → IMPLEMENTATION → REVIEW
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=secureflow

# Specific test
pytest tests/test_chat.py -v
```

**253 passing, 2 skipped** (PDF export only, needs the optional `export` extra —
`pip install -e ".[export]"`). Enforced in CI on every push and pull request
against `main` (Python 3.10/3.11/3.12, plus a frontend typecheck + build job).

## Project Structure

```
secureflow/
├── secureflow/
│   ├── cli.py                    # CLI interface
│   ├── server.py                 # FastMCP server + HTTP routes
│   ├── config.py                 # LLM provider config & health checks
│   ├── security.py                # Target validation, safe path joins
│   ├── analysis.py                # AST-based Python static analysis
│   ├── chat.py                    # Ask-AI chat: prompt fencing, provider fallback
│   ├── reports.py / notifications.py / scheduler.py
│   └── crew/
│       ├── agents.py             # Agent definitions
│       ├── tasks.py              # Task workflows
│       ├── tools.py              # Agent tools (nmap, CVE lookup, code analysis)
│       ├── orchestrator.py       # Security workflow
│       └── dev_orchestrator.py   # Development workflow
├── tests/                        # 253 automated tests
├── frontend/                     # React dashboard
├── server-launcher.py            # Monitored launcher (screen session, auto-restart)
├── .github/workflows/ci.yml      # CI: pytest matrix + frontend build
└── pyproject.toml                # Package metadata
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/X`)
3. Add tests for new functionality — CI runs `pytest` and the frontend build on
   every pull request
4. Submit a pull request with a description of the change and why

## Running Locally

```bash
source venv/bin/activate
python server-launcher.py   # monitored: auto-restart on failure
# or, directly:
secureflow server
```

No Dockerfile or systemd unit is currently shipped in this repository — if you
containerize or package SecureFlow yourself, remember the server binds
`127.0.0.1` by default (see the Network exposure note under Security).

## Project Status

This is an **alpha** project under active development. Recent work has focused
on closing real correctness and security gaps rather than adding surface area:
a full security review (authentication, path traversal, target-injection
fixes), replacing simulated tool output with real static analysis and CVE
lookups, and a CI pipeline that actually runs the test suite on every change.

## License

MIT License — see [LICENSE](LICENSE) file

## Support

- **Issues** — use the GitHub issue tracker
- **Docs** — this README plus inline docstrings; see `tests/` for usage patterns

---

**Built with CrewAI + FastMCP**
