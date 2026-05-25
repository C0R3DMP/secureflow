# SecureFlow: AI-Powered Security & Development Crew

SecureFlow is a comprehensive AI-powered system for security assessment and application development using CrewAI's multi-agent orchestration framework.

**Status:** ✅ Production-Ready | **Version:** 0.1.0

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests Passing](https://img.shields.io/badge/tests-47%2F47%20passing-brightgreen)](https://github.com/secureflow/secureflow)
[![GitHub stars](https://img.shields.io/github/stars/secureflow/secureflow?style=social)](https://github.com/secureflow/secureflow)
## Features

### 🔒 Security Assessment Crew
- **Recon Agent** (Gemini) - Network scanning, service enumeration, CVE discovery
- **Analyst Agent** (Claude/OpenCode) - Vulnerability analysis, risk assessment, exploitation chains
- **Reporter Agent** (Ollama) - Executive reporting, remediation roadmap, CVSS scoring

### 💻 Application Development Crew
- **Architect Agent** (Claude/OpenCode) - System design, tech stack selection, project structure
- **Developer Agent** (Gemini) - Code implementation, feature building, file creation
- **Reviewer Agent** (Ollama) - Code quality review, bug detection, improvement suggestions

### 🎯 Key Capabilities
- Multi-agent collaborative workflows
- Shared context and inter-agent communication
- FastMCP server with SSE transport
- CLI interface with full command support
- Comprehensive test suite with pytest
- Production-ready deployment

## Quick Start

### Installation

```bash
# Clone or download SecureFlow
cd /home/sky/secureflow

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### First Run

```bash
# Check system status
secureflow status

# View available commands
secureflow --help
```

## Usage

### Security Assessment

```bash
# Run full security assessment on target
secureflow scan scanme.nmap.org

# The assessment will:
# 1. Run network reconnaissance (nmap, CVE lookup)
# 2. Perform vulnerability analysis
# 3. Generate executive report with remediation plan
```

### Application Development

```bash
# Build an application
secureflow build "Create a REST API for a todo application" \
  --language python \
  --output /tmp/todo-api

# The development crew will:
# 1. Design system architecture
# 2. Generate production code
# 3. Review code quality
```

### MCP Server

```bash
# Start the FastMCP server
secureflow server

# Server will listen on port 5000 with SSE transport
# Available tools:
# - run_security_crew(target)
# - run_dev_crew(task, language, output_dir)
# - run_code_review(code, language)
# - crew_status()
```

## Configuration

### Environment Variables

Create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Required variables:
- `MCP_SECRET` - Bearer token for authentication (generate: `openssl rand -hex 32`)
- `GEMINI_API_KEY` - Google Gemini API key (optional, for Recon agent)
- `OPENCODE_URL` - OpenCode server URL (default: `http://localhost:4096`)

Optional:
- `OLLAMA_BASE_URL` - Local Ollama server (default: `http://localhost:11434`)
- `TELEGRAM_BOT_TOKEN` - For Telegram notifications
- `TELEGRAM_CHAT_ID` - For Telegram notifications

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov

# Run specific test file
pytest tests/test_cli.py -v

# Run specific test
pytest tests/test_cli.py::test_cli_version -v
```

## Architecture

### Security Crew Workflow

```
Phase 1: RECONNAISSANCE
  Recon Agent (Gemini)
  - nmap scan for open ports
  - Service version detection
  - CVE lookup for each service
  └─> Writes findings to SharedContext

Phase 2: ANALYSIS
  Analyst Agent (Claude/OpenCode)
  - Reads recon findings
  - Correlates CVEs
  - Assesses risk severity
  - Identifies exploitation chains
  └─> Writes analysis to SharedContext

Phase 3: REPORTING
  Reporter Agent (Ollama)
  - Reads all findings
  - Creates executive summary
  - Plans remediation roadmap
  - Generates HTML report
  └─> Returns final report
```

### Development Crew Workflow

```
Phase 1: ARCHITECTURE
  Architect Agent (Claude/OpenCode)
  - Analyzes requirements
  - Designs system architecture
  - Recommends tech stack
  - Plans project structure
  └─> Writes design to SharedContext

Phase 2: IMPLEMENTATION
  Developer Agent (Gemini)
  - Reads architecture design
  - Generates code modules
  - Creates project files
  - Implements core features
  └─> Writes code to SharedContext

Phase 3: REVIEW
  Reviewer Agent (Ollama)
  - Reads generated code
  - Checks code quality
  - Identifies bugs
  - Suggests improvements
  └─> Returns review report
```

## Project Structure

```
secureflow/
├── secureflow/           # Main package
│   ├── cli.py           # CLI interface
│   ├── server.py        # FastMCP server
│   ├── config.py        # Configuration
│   └── crew/            # Multi-agent system
│       ├── agents.py    # Agent definitions
│       ├── tasks.py     # Task definitions
│       ├── tools.py     # Tools for agents
│       ├── orchestrator.py      # Security workflow
│       ├── dev_orchestrator.py  # Dev workflow
│       ├── memory.py    # Shared context (SQLite)
│       └── chat.py      # Inter-agent messaging
├── tests/               # Test suite
├── docs/                # Documentation
└── pyproject.toml       # Package metadata
```

## Development

### Code Style

```bash
# Format code with black
black secureflow/ tests/

# Check with flake8
flake8 secureflow/ tests/

# Type checking with mypy
mypy secureflow/

# Organize imports with isort
isort secureflow/ tests/
```

### Adding New Tools

1. Create tool function in `secureflow/crew/tools.py`:

```python
@tool("Tool Name")
def my_tool(param: str) -> str:
    """Tool description."""
    result = {"status": "success", "data": "..."}
    return json.dumps(result, indent=2)
```

2. Add to agent:

```python
from secureflow.crew.tools import my_tool

@staticmethod
def agent_with_tool():
    return Agent(
        role="Agent Role",
        tools=[my_tool],
        # ... other config
    )
```

## Deployment

### Production with systemd

```bash
# Copy to production location
sudo cp -r secureflow /opt/

# Create service file
sudo cp secureflow.service /etc/systemd/system/

# Enable and start
sudo systemctl enable secureflow
sudo systemctl start secureflow

# Check status
sudo systemctl status secureflow
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"
CMD ["secureflow", "server"]
```

## Troubleshooting

### Import Errors

```bash
# Verify environment
secureflow status

# Reinstall package
pip install -e ".[dev]" --force-reinstall
```

### Server Not Starting

```bash
# Check port availability
lsof -i :5000

# View logs
tail -f /tmp/crew_session.log
```

### Tests Failing

```bash
# Run with verbose output
pytest tests/ -vv

# Show print statements
pytest tests/ -s

# Run single test
pytest tests/test_cli.py::test_cli_version -vv
```

## Performance

- **Recon Phase**: 30-120 seconds (network dependent)
- **Analysis Phase**: 60-180 seconds (LLM response time)
- **Reporting Phase**: 30-90 seconds (report generation)
- **Total**: 2-5 minutes per security assessment

## Security

- ✅ Bearer token authentication on MCP server
- ✅ No credentials in logs or session files
- ✅ Local SQLite storage for findings
- ✅ Optional Telegram notifications
- ✅ No external data sharing by default

## Limitations

- Requires network access for NVD CVE lookups
- OpenCode server must be running for Claude-based agents
- Large codebases may timeout during analysis

## Future Improvements

- [ ] Persistent result storage
- [ ] Web UI dashboard
- [ ] Real-time progress streaming
- [ ] Scheduled assessments
- [ ] Integration with SIEM systems
- [ ] Custom tool marketplace
- [ ] Plugin system for extensions

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch
3. Add tests for new code
4. Submit pull request

## License

MIT License - see LICENSE file for details

## Support

- **Issues**: Report bugs on GitHub
- **Documentation**: See `docs/` directory
- **Examples**: Check `tests/` for usage patterns

## Citation

If you use SecureFlow in research, please cite:

```bibtex
@software{secureflow2026,
  title={SecureFlow: AI-Powered Security Assessment and Development},
  author={SecureFlow Team},
  year={2026},
  url={https://github.com/secureflow/secureflow}
}
```

---

**Built with ❤️ using CrewAI and FastMCP**

Status: ✅ Production-Ready | Version 0.1.0 | Last Updated: May 2026
