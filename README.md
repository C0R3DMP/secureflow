# SecureFlow

**AI-powered penetration testing framework with multi-agent collaboration**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 221 passing](https://img.shields.io/badge/tests-221%20passing-brightgreen)](#testing)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)](https://github.com/secureflow/secureflow)

SecureFlow is a complete AI-powered security assessment and application development platform. Multi-agent teams (Recon, Analyst, Reporter) collaborate via shared context to execute comprehensive penetration tests. Supports Claude, Gemini, and Ollama LLMs.

## Features

### 🔒 Security Assessment Workflow
- **Recon Agent** (Gemini API/Ollama) — Network reconnaissance, port scanning, CVE discovery via nmap
- **Analyst Agent** (Gemini API/Ollama) — Vulnerability analysis, exploitability assessment, attack chain identification
- **Reporter Agent** (Gemini API/Ollama) — Executive reporting, CVSS scoring, 90-day remediation roadmap

### 💻 Development Workflow
- **Architect Agent** — System design, tech stack selection, project structure planning
- **Developer Agent** — Production code generation, feature implementation, project scaffolding
- **Reviewer Agent** — Code quality review, bug detection, security assessment

### 🎯 Core Capabilities
- Multi-agent collaborative workflows with shared context
- FastMCP server with SSE real-time streaming
- Web dashboard with live scan monitoring
- CLI interface with full command support
- Report export (HTML, PDF, JSON)
- Webhook notifications & scheduled scans
- 221 automated tests, comprehensive coverage

### 🖥️ Dashboard
- Live agent activity, event log with level filters, and phase progress
- Severity summary derived from real CVSS scores returned by NVD
- In-app report preview (rendered in a sandboxed frame) plus download
- Light and dark themes; keyboard shortcut `⌘K` / `Ctrl+K` to focus the target field

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/secureflow/secureflow.git
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

Create `.env` file with:

```bash
# Required
ANTHROPIC_API_KEY=sk-...          # Optional, uses Claude CLI if not set
GEMINI_API_KEY=...                # Optional, uses Gemini CLI if not set

# Optional
OLLAMA_BASE_URL=http://localhost:11434
MCP_SECRET=<32-char bearer token>  # For server auth (generate: openssl rand -hex 32)
TELEGRAM_BOT_TOKEN=...            # For Telegram notifications
TELEGRAM_CHAT_ID=...              # For Telegram notifications
```

### LLM Provider Priority

SecureFlow tries providers in this order (first available is used):

1. **Gemini API** (5 req/min) — Requires `GEMINI_API_KEY`
2. **OpenRouter** (free models) — Requires `OPENROUTER_API_KEY` — Recommended for high volume
3. **Ollama** (local, free) — Requires running `ollama run qwen2.5-coder`
4. **Claude API** — Requires `ANTHROPIC_API_KEY`

**Recommendation:** Use OpenRouter for free models with no rate limits on free tier

## Security

SecureFlow launches network scans on demand, so an exposed instance is a remote
scanning proxy for whoever can reach it. The server is built to fail closed.

### Authentication

Every `/api/*`, `/stream/*` and MCP transport route requires a bearer token. Only
the static dashboard under `/ui` is public (it is inert without API access).

```bash
# Recommended: set a stable token
MCP_SECRET=$(openssl rand -hex 32)
```

If `MCP_SECRET` is unset, the server **generates an ephemeral token at startup and
prints it** rather than running unauthenticated. To deliberately run with no auth
(local development only), set `SECUREFLOW_ALLOW_ANONYMOUS=1`.

Pass the token as a header, or — for the SSE stream, since `EventSource` cannot
set headers — as a query parameter:

```bash
curl -H "Authorization: Bearer $MCP_SECRET" http://localhost:5000/api/history
curl -N "http://localhost:5000/stream/example.com?token=$MCP_SECRET"
```

The dashboard reads the token from `?token=...` on first load and remembers it in
`localStorage`.

### Network exposure

The server binds `127.0.0.1:5000` by default. Override deliberately:

```bash
SECUREFLOW_HOST=0.0.0.0 SECUREFLOW_PORT=5000 secureflow server
```

### Target validation

Scan targets must be a hostname, IPv4/IPv6 address, CIDR network, or URL. Values
that begin with `-` or contain shell/argv metacharacters are rejected before
reaching `nmap`, closing an argument-injection path (`--script=…`, `-oN …`).

### Scope

Only scan systems you are authorised to test. Automated scanning of third-party
infrastructure without permission is illegal in most jurisdictions.

## CLI Commands

| Command | Description |
|---------|-------------|
| `secureflow scan <target>` | Run full security assessment |
| `secureflow recon <target>` | Fast reconnaissance only |
| `secureflow build <task>` | Generate application code |
| `secureflow review <file>` | Code quality review |
| `secureflow schedule add` | Schedule recurring scan |
| `secureflow schedule list` | Show scheduled scans |
| `secureflow schedule remove <id>` | Delete scheduled scan |
| `secureflow history` | View past scans |
| `secureflow server` | Start MCP server (port 5000) |
| `secureflow status` | Check system health |
| `secureflow --help` | Show all commands |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/run_security_crew` | Async security assessment (returns `scan_id`) |
| POST | `/tools/run_recon` | Fast reconnaissance (async) |
| POST | `/tools/run_dev_crew` | Code generation (async) |
| POST | `/tools/run_code_review` | Code review analysis (async) |
| GET | `/api/scans/{scan_id}` | Poll scan status |
| GET | `/api/history` | Scan history (JSON) |
| GET | `/api/reports/export?target=X&format=html` | Export report (html/pdf/json) |
| GET | `/ui` | Web dashboard |
| GET | `/stream/{target}` | SSE progress stream |

## Architecture

### Security Assessment Workflow
```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: RECONNAISSANCE (Recon Agent)                   │
│  • nmap scan (top 1000 ports)                           │
│  • Service version detection                            │
│  • CVE lookup per service                               │
│  └─→ Save to SharedContext: recon_scan_results          │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│ Phase 2: ANALYSIS (Analyst Agent)                       │
│  • Read recon findings                                  │
│  • Assess exploitability per service                    │
│  • Identify attack chains & lateral movement            │
│  • Rate: CRITICAL | HIGH | MEDIUM | LOW                │
│  └─→ Save to SharedContext: vulnerability_analysis     │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│ Phase 3: REPORTING (Reporter Agent)                     │
│  • Executive summary (non-technical)                    │
│  • Detailed findings table                              │
│  • 90-day remediation roadmap                           │
│  • Technical appendix & CVSS scores                     │
│  └─→ Return: final_report (HTML/PDF/JSON)              │
└─────────────────────────────────────────────────────────┘
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
pytest tests/test_cli.py::test_scan -v
```

Status: **114/114 tests passing** ✅

## Project Structure

```
secureflow/
├── secureflow/
│   ├── cli.py                    # CLI interface
│   ├── server.py                 # FastMCP server
│   ├── config.py                 # LLM config & provider detection
│   ├── server-launcher.py        # Robust server management
│   └── crew/
│       ├── agents.py             # 6 agent definitions
│       ├── tasks.py              # Task workflows
│       ├── tools.py              # Agent tools (nmap, CVE lookup, etc.)
│       ├── orchestrator.py       # Security workflow
│       └── dev_orchestrator.py   # Development workflow
├── tests/                        # 114 automated tests
├── frontend/                     # React dashboard
└── pyproject.toml               # Package metadata
```

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
python server-launcher.py  # Auto-restart on failure
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
docker run -p 5000:5000 -e ANTHROPIC_API_KEY=$KEY secureflow
```

## Security

- ✅ Bearer token authentication (MCP server)
- ✅ No credentials in logs or session files
- ✅ SQLite storage for findings (local-only by default)
- ✅ HMAC-SHA256 webhook signing
- ✅ XSS protection in HTML reports

## Completed Milestones

- [x] **M7** — CrewAI 1.14.5 upgrade, XSS fixes, Gemini 2.5-flash
- [x] **M8** — Concurrent scans, async tools, status polling
- [x] **M9** — Report export (HTML/PDF/JSON)
- [x] **M10** — Webhook notifications with HMAC signing
- [x] **M11** — Scheduled scans with cron & SQLite persistence
- [x] **M12** — Claude/Gemini CLI support, detailed agent prompts, robust server launcher

## License

MIT License — see [LICENSE](LICENSE) file

## Support

- **Issues** — GitHub issues tracker
- **Docs** — See `docs/` directory
- **Examples** — Check `tests/` for patterns

---

**Built with CrewAI + FastMCP** | Version 0.1.0 | ✅ Production-Ready
