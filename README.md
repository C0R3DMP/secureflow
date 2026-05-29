# SecureFlow

**AI-powered penetration testing framework with multi-agent collaboration**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 151/151](https://img.shields.io/badge/tests-151%2F151%20passing-brightgreen)](#testing)
[![Status: Production](https://img.shields.io/badge/status-production--ready-success)](https://github.com/secureflow/secureflow)

SecureFlow is a complete AI-powered security assessment and application development platform. Multi-agent teams (Recon, Analyst, Reporter) collaborate via shared context to execute comprehensive penetration tests. Supports Claude, Gemini, and Ollama LLMs.

## Features

### 🔒 Security Assessment Workflow
- **Security Reconnaissance Specialist** (Gemini API/Ollama) — Network port scanning, DNS enumeration, web fingerprinting, TLS inspection, security-header auditing, sensitive-path probing, and CVE discovery
- **Vulnerability Analysis Expert** (Gemini API/Ollama) — Vulnerability analysis, exploitability assessment, attack chain identification
- **Security Report Specialist** (Gemini API/Ollama) — Executive reporting, CVSS scoring, 90-day remediation roadmap

### 🧰 Reconnaissance Toolkit

The recon agent uses a suite of built-in tools. The web/DNS/TLS tools are **pure-Python** (no external binaries required) so they work on any deployment, with `nmap` used automatically when present:

| Tool | Purpose |
|------|---------|
| **Nmap Scan** | Port & service discovery (`nmap -sV`, socket fallback with banner grabbing) |
| **DNS Enumeration** | A / AAAA / MX / NS / TXT / CNAME / SOA records (dnspython) |
| **HTTP Fingerprint** | Server banner, page title, and technology detection (CMS, frameworks, languages) |
| **Security Header Audit** | Detects missing HSTS, CSP, X-Frame-Options, X-Content-Type-Options, etc. |
| **Sensitive Path Probe** | Checks for exposed `/.git`, `/.env`, backups, admin panels, actuator endpoints |
| **TLS Certificate Inspection** | Cert subject/issuer/expiry, negotiated protocol & cipher, self-signed / weak-protocol warnings |
| **CVE Lookup** | Known vulnerabilities per service/product (NVD API) |

### 💻 Development Workflow
- **Software Architect** — System design, tech stack selection, project structure planning
- **Senior Software Developer** — Production code generation, feature implementation, project scaffolding
- **Code Quality Reviewer** — Code quality review, bug detection, security assessment

### 🎯 Core Capabilities
- Multi-agent collaborative workflows with shared context (SQLite-backed, thread-safe)
- FastMCP server with SSE real-time streaming
- React web dashboard with live scan monitoring
- CLI interface with full command support
- Report export (HTML, PDF, JSON)
- Webhook notifications (HMAC-SHA256 signed) & scheduled scans
- 151 automated tests, comprehensive coverage

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/secureflow/secureflow.git
cd secureflow
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Build the Dashboard
```bash
cd frontend && npm install && npm run build && cd ..
```

### 3. Configure
```bash
cp .env.example .env
# Edit .env with your API keys (see Configuration section)
```

### 4. Run
```bash
# CLI security assessment
secureflow scan example.com

# Web dashboard
secureflow server   # Visit http://localhost:5000/ui
```

## Configuration

### Environment Variables

Create `.env` file with:

```bash
# Authentication (strongly recommended for production)
MCP_SECRET=<32-char bearer token>  # Generate: openssl rand -hex 32

# LLM Providers — configure at least ONE
GEMINI_API_KEY=...                 # Option 1: Gemini API (5 req/min free)
OPENROUTER_API_KEY=...             # Option 2: OpenRouter (free models)
ANTHROPIC_API_KEY=sk-...           # Option 3: Claude API
OLLAMA_BASE_URL=http://localhost:11434  # Option 4: Local Ollama

# Optional notifications
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
WEBHOOK_URL=https://your.server/hook
WEBHOOK_SECRET=<hmac-signing-secret>

# OpenCode integration (optional)
OPENCODE_URL=http://localhost:4096
OPENCODE_SERVER_PASSWORD=<password>
```

### LLM Provider Priority

SecureFlow tries providers in this order (first available is used):

1. **Gemini API** (5 req/min) — Requires `GEMINI_API_KEY`
2. **OpenRouter** (free models) — Requires `OPENROUTER_API_KEY` — Recommended for high volume
3. **Ollama** (local, free) — Requires running `ollama run qwen2.5-coder`
4. **Claude API** — Requires `ANTHROPIC_API_KEY`

## CLI Commands

| Command | Description |
|---------|-------------|
| `secureflow scan <target>` | Run full security assessment |
| `secureflow scan <target> --format pdf` | Export report as PDF |
| `secureflow build <task>` | Generate application code |
| `secureflow schedule add <target> --cron "0 3 * * *"` | Schedule recurring scan |
| `secureflow schedule list` | Show scheduled scans |
| `secureflow schedule remove <id>` | Delete scheduled scan |
| `secureflow history` | View past scans |
| `secureflow server` | Start MCP server (port 5000) |
| `secureflow server-launch` | Start server in a screen session |
| `secureflow status` | Check system health |
| `secureflow tui` | Interactive management interface |

## API Endpoints

All `/api/*` and `/stream/*` endpoints require `Authorization: Bearer <MCP_SECRET>` when `MCP_SECRET` is set.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/run_security_crew` | Full security assessment (MCP tool) |
| POST | `/tools/run_recon` | Fast reconnaissance (MCP tool) |
| POST | `/tools/run_dev_crew` | Code generation (MCP tool) |
| POST | `/tools/run_code_review` | Code review analysis (MCP tool) |
| GET | `/api/scans/{scan_id}` | Poll scan status |
| GET | `/api/history` | Scan history (JSON) |
| GET | `/api/providers` | LLM provider availability |
| GET | `/api/schedules` | List scheduled scans |
| GET | `/api/reports/export?target=X&format=html` | Export report (html/pdf/json) |
| POST | `/api/settings` | Update provider settings |
| GET | `/stream/{target}` | SSE progress stream (auth required) |
| GET | `/ui` | React web dashboard |

## Architecture

### Security Assessment Workflow
```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: RECONNAISSANCE (Security Reconnaissance Spec.) │
│  • nmap scan (top 50 ports, socket+banner fallback)     │
│  • DNS enumeration (A/MX/NS/TXT/...)                     │
│  • HTTP fingerprint + security-header audit             │
│  • Sensitive-path probe (/.git, /.env, backups)         │
│  • TLS certificate inspection                           │
│  • CVE lookup per service (NVD API)                     │
│  └─→ Save to SharedContext: recon_scan_results          │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│ Phase 2: ANALYSIS (Vulnerability Analysis Expert)       │
│  • Read recon findings from shared context              │
│  • Assess exploitability per service                    │
│  • Identify attack chains & lateral movement            │
│  • Rate: CRITICAL | HIGH | MEDIUM | LOW                 │
│  └─→ Save to SharedContext: vulnerability_analysis      │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│ Phase 3: REPORTING (Security Report Specialist)         │
│  • Executive summary (non-technical)                    │
│  • Detailed findings table with CVSS scores             │
│  • 90-day remediation roadmap                           │
│  • Technical appendix & methodology                     │
│  └─→ Return: final_report (HTML/PDF/JSON)               │
└─────────────────────────────────────────────────────────┘
```

### Development Workflow
```
Software Architect → (shared context) → Senior Software Developer → Code Quality Reviewer
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=secureflow

# Specific module
pytest tests/test_cli.py -v
```

Status: **151/151 tests passing** ✅

## Project Structure

```
secureflow/
├── secureflow/
│   ├── cli.py                    # CLI interface
│   ├── server.py                 # FastMCP server + HTTP API
│   ├── config.py                 # LLM config & provider detection
│   ├── reports.py                # HTML/PDF/JSON report export
│   ├── notifications.py          # Webhook & Telegram dispatcher
│   ├── scheduler.py              # APScheduler cron manager
│   └── crew/
│       ├── agents.py             # 6 specialist agent definitions
│       ├── tasks.py              # Task & crew factories
│       ├── tools.py              # Agent tools (nmap, DNS, HTTP/TLS recon, CVE, file ops)
│       ├── memory.py             # Thread-safe SQLite shared context
│       ├── history.py            # Thread-safe session history
│       ├── orchestrator.py       # Security workflow orchestrator
│       └── dev_orchestrator.py   # Development workflow orchestrator
├── frontend/                     # React + Vite dashboard (TypeScript)
│   └── src/
│       ├── App.tsx
│       ├── components/           # Dashboard, LogViewer, SettingsModal…
│       └── hooks/                # useAPI, useSSE
├── secureflow/static/dist/       # Compiled React build (served by server)
├── tests/                        # 151 automated tests
└── pyproject.toml               # Package metadata
```

## Security

### Authentication
Set `MCP_SECRET` in `.env` to enable bearer token auth on all API endpoints:
```bash
MCP_SECRET=$(openssl rand -hex 32)
```
All `/api/*` and `/stream/*` routes return `401 Unauthorized` when the token is missing or invalid. Token comparison uses `hmac.compare_digest()` to prevent timing attacks.

### Hardening applied
- ✅ Bearer token auth enforced on all HTTP API routes
- ✅ Timing-safe token comparison (`hmac.compare_digest`)
- ✅ Path traversal protection in static file serving (`resolve()` + containment check)
- ✅ Newline injection prevention in `.env` file writes
- ✅ nmap target argument validation (regex allowlist)
- ✅ File write operations restricted to `/tmp/` and `~/.secureflow/`
- ✅ HMAC-SHA256 webhook signing for outbound notifications
- ✅ HTML escaping in fallback report template
- ✅ Telegram Markdown special-character escaping
- ✅ `output_dir` restricted to `/tmp/` in dev crew API

### Concurrency & Stability
- ✅ `SharedContext` and `SessionHistory` protected by `RLock`
- ✅ CVE lookup cache protected by `threading.Lock`
- ✅ Logger handler accumulation fixed (handlers only added once per logger)
- ✅ OpenCode subprocess uses `DEVNULL` (no pipe buffer deadlock)
- ✅ `_active_scans` capped at 500 entries (bounded memory)
- ✅ `ScheduleManager` registers `atexit` shutdown handler

## Completed Milestones

- [x] **M7** — CrewAI 1.14.5 upgrade, XSS fixes, Gemini 2.5-flash
- [x] **M8** — Concurrent scans, async tools, status polling
- [x] **M9** — Report export (HTML/PDF/JSON), `--format` CLI option
- [x] **M10** — Webhook notifications with HMAC signing
- [x] **M11** — Scheduled scans with cron & SQLite persistence
- [x] **M12** — Claude/Gemini CLI support, detailed agent prompts, robust server launcher
- [x] **M13** — Security hardening (auth enforcement, path traversal, injection fixes, thread safety)
- [x] **M14** — Expanded recon toolkit (DNS enum, HTTP fingerprint, security-header audit, sensitive-path probe, TLS inspection) — stress-tested under high concurrency

## Contributing

SecureFlow welcomes contributions:

1. Fork repository
2. Create feature branch (`git checkout -b feature/X`)
3. Add tests for new functionality
4. Submit pull request with description

## Deployment

### Local Development
```bash
source venv/bin/activate
secureflow server
```

### Production (systemd)
```bash
sudo cp secureflow.service /etc/systemd/system/
sudo systemctl enable --now secureflow
sudo systemctl status secureflow
```

### Docker
```bash
docker build -t secureflow .
docker run -p 5000:5000 \
  -e MCP_SECRET=$(openssl rand -hex 32) \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  secureflow
```

## License

MIT License — see [LICENSE](LICENSE) file

## Support

- **Issues** — GitHub issues tracker
- **Docs** — See `docs/` directory
- **Examples** — Check `tests/` for patterns

---

**Built with CrewAI + FastMCP** | Version 0.1.0 | ✅ Production-Ready
