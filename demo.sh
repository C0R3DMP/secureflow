#!/bin/bash
# SecureFlow Demo Script
# Demonstrates CLI capabilities with colored output

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Activate virtual environment
source venv/bin/activate

echo -e "${CYAN}${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║         SecureFlow AI Demo - Version 0.1.0                 ║${NC}"
echo -e "${CYAN}${BOLD}║   Security Assessment & Application Development Crew       ║${NC}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}${BOLD}DEMO 1: System Status Check${NC}"
echo -e "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Running: ${CYAN}secureflow status${NC}"
echo ""

secureflow status

echo ""
echo -e "${GREEN}✅ Status check complete!${NC}"
echo ""

echo -e "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}${BOLD}DEMO 2: Security Scan (localhost)${NC}"
echo -e "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Target: ${CYAN}127.0.0.1 (localhost)${NC}"
echo -e "${YELLOW}Duration: 2-5 minutes${NC}"
echo -e "${YELLOW}Phases:${NC}"
echo -e "  1️⃣  ${CYAN}Reconnaissance${NC} - Network scanning and CVE lookup"
echo -e "  2️⃣  ${CYAN}Analysis${NC} - Vulnerability assessment and risk scoring"
echo -e "  3️⃣  ${CYAN}Reporting${NC} - Executive summary and remediation plan"
echo ""
echo -e "${YELLOW}Running: ${CYAN}secureflow scan 127.0.0.1${NC}"
echo ""

secureflow scan 127.0.0.1

echo ""
echo -e "${GREEN}✅ Security scan complete!${NC}"
echo ""

echo -e "${CYAN}${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                   DEMO COMPLETED SUCCESSFULLY              ║${NC}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}📚 Other Available Commands:${NC}"
echo ""
echo -e "  ${CYAN}secureflow build${NC} <task>        - Build an application"
echo -e "    Example: ${CYAN}secureflow build \"REST API for todos\"${NC}"
echo ""
echo -e "  ${CYAN}secureflow server${NC}               - Start MCP server"
echo -e "    Listens on: ${CYAN}http://0.0.0.0:5000/sse${NC}"
echo ""
echo -e "  ${CYAN}secureflow --help${NC}               - Show all commands"
echo ""
echo -e "📖 Documentation: ${CYAN}README.md${NC}"
echo -e "🧪 Tests: ${CYAN}pytest tests/ -v${NC}"
echo -e "📝 Version: ${CYAN}secureflow --version${NC}"
echo ""
