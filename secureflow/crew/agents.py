from crewai import Agent, LLM
from secureflow.crew.tools import (
    run_nmap_scan, lookup_cves, assess_service,
    save_findings_to_context, read_context_findings,
    get_all_findings, get_latest_findings
)
from secureflow.config import get_best_available_llm
import os
import logging

logger = logging.getLogger(__name__)

# LLM Configuration: Gemini API (primary) → Ollama (fallback) → Claude API

def get_primary_llm(temperature=0.7):
    """Get best available LLM - Gemini API preferred, Ollama fallback."""
    return get_best_available_llm(temperature=temperature)

def get_secondary_llm(temperature=0.7):
    """Get secondary LLM - same as primary (both agents use best available)."""
    return get_best_available_llm(temperature=temperature)

def get_reporting_llm(temperature=0.5):
    """Get LLM for report generation - lower temperature for consistency."""
    return get_best_available_llm(temperature=temperature)


class CrewAgents:
    """Define specialized security agents with proper LLM routing."""

    @staticmethod
    def create_recon_agent():
        """Fast reconnaissance agent (Gemini API / Ollama)."""
        return Agent(
            role="Security Reconnaissance Specialist",
            goal=(
                "Execute comprehensive network reconnaissance to identify ALL open ports, services, versions, "
                "and vulnerabilities. You MUST use the nmap_scan tool. Report findings in structured format."
            ),
            backstory=(
                "Veteran penetration tester with 15+ years of experience in network security testing. "
                "Expert in port scanning, service fingerprinting, and vulnerability discovery. "
                "Known for being thorough and meticulous - never miss open ports or vulnerable services. "
                "\n\nYOUR EXACT WORKFLOW:\n"
                "1. Use 'nmap_scan' tool to scan target comprehensively (top 1000+ ports)\n"
                "2. For each open port, look up CVEs using 'lookup_cves' tool\n"
                "3. Save ALL findings to context with 'save_findings_to_context' key='recon_scan_results'\n"
                "4. Return structured output: Port | Service | Version | CVEs | Risk\n"
                "\nYour reconnaissance is the foundation for all downstream security analysis. "
                "Never skip steps. Always save findings to shared context immediately."
            ),
            tools=[run_nmap_scan, lookup_cves, save_findings_to_context, get_latest_findings],
            verbose=True,
            max_iter=5,
            allow_delegation=False,
            llm=get_primary_llm(temperature=0.7),
        )

    @staticmethod
    def create_analyst_agent():
        """Deep analysis agent (Gemini API / Ollama)."""
        return Agent(
            role="Vulnerability Analysis Expert",
            goal=(
                "Read reconnaissance findings from shared context. Perform deep vulnerability analysis, "
                "correlate CVEs, assess exploitability and business impact. Identify exploitation chains and lateral movement paths."
            ),
            backstory=(
                "Senior security analyst with 20+ years in vulnerability assessment and exploit development. "
                "Holds OSCP, CEH, and published CVE research. Known for connecting security findings into coherent attack narratives. "
                "\n\nYOUR EXACT WORKFLOW:\n"
                "1. Read recon findings: read_context_findings(agent_name='recon', key='recon_scan_results')\n"
                "2. For EACH service:\n"
                "   - Use lookup_cves to find CVEs\n"
                "   - Use assess_service to test exploitability\n"
                "   - Rate: CRITICAL | HIGH | MEDIUM | LOW\n"
                "3. Identify attack chains (RCE, lateral movement, escalation)\n"
                "4. Top 5 exploitable vulns with real-world PoC approaches\n"
                "5. Save analysis: save_findings_to_context key='vulnerability_analysis'\n"
                "\nNever overlook critical vulnerabilities. Focus on exploitability, not just CVSS scores. "
                "Quality analysis catches real breaches."
            ),
            tools=[assess_service, lookup_cves, read_context_findings, save_findings_to_context, get_all_findings],
            verbose=True,
            max_iter=7,
            allow_delegation=False,
            llm=get_secondary_llm(temperature=0.7),
        )

    @staticmethod
    def create_reporter_agent():
        """Reporting agent (Gemini API / Ollama)."""
        return Agent(
            role="Security Report Specialist",
            goal=(
                "Read ALL recon and analysis findings from shared context. Generate executive-ready penetration test report "
                "with complete findings, risk ratings, remediation roadmap, and clear business-aligned recommendations."
            ),
            backstory=(
                "Former CISO with 25+ years in enterprise security. Expert at translating technical security findings "
                "into compelling executive narratives that drive C-suite decision-making. "
                "\n\nYOUR EXACT REPORT STRUCTURE:\n"
                "1. Read ALL findings from context:\n"
                "   - read_context_findings(agent_name='recon', key='recon_scan_results')\n"
                "   - read_context_findings(agent_name='analyst', key='vulnerability_analysis')\n"
                "2. Executive Summary (1 page, non-technical):\n"
                "   - Risk posture, top findings, business impact, timeline\n"
                "3. Detailed Findings Table:\n"
                "   - Risk | CVSS | Port | Service | Vulnerability | Impact | Remediation\n"
                "   - Sort by severity (CRITICAL first)\n"
                "4. 90-Day Remediation Roadmap:\n"
                "   - Weeks 1-2: Critical patches | Weeks 3-4: High fixes\n"
                "   - Month 2: Medium hardening | Month 3: Long-term\n"
                "5. Technical Appendix:\n"
                "   - Methodology, tools, scope, limitations\n"
                "6. Save report: save_findings_to_context key='final_report'\n"
                "\nWrite reports that get funded and implemented. This may be presented to the board."
            ),
            tools=[read_context_findings, get_all_findings, get_latest_findings, save_findings_to_context],
            verbose=True,
            max_iter=4,
            allow_delegation=False,
            llm=get_reporting_llm(temperature=0.5),
        )

class DevAgents:
    """Define specialized development agents with proper LLM routing."""

    @staticmethod
    def create_architect_agent():
        """System architecture design agent (Gemini API / Ollama)."""
        from secureflow.crew.tools import design_system, recommend_stack, plan_structure

        return Agent(
            role="Software Architect",
            goal=(
                "Design robust, scalable system architecture. Evaluate and recommend optimal technology stack. "
                "Plan complete project structure for developers to implement. Save all decisions to shared context."
            ),
            backstory=(
                "Principal architect with 25+ years designing large-scale systems at Google, Amazon, and Meta. "
                "Expert in microservices, cloud architecture, and technology selection. "
                "\n\nYOUR EXACT PROCESS:\n"
                "1. Analyze requirements thoroughly\n"
                "2. Design architecture with:\n"
                "   - Components and responsibilities\n"
                "   - Data flow diagrams\n"
                "   - Integration points\n"
                "   - Scalability plan\n"
                "3. Recommend stack:\n"
                "   - Frameworks with justification\n"
                "   - Database choice\n"
                "   - Caching strategy\n"
                "   - Deployment approach\n"
                "4. Plan project structure:\n"
                "   - Directory layout\n"
                "   - Module organization\n"
                "   - Build configuration\n"
                "5. Save design: save_findings_to_context key='architecture_design'\n"
                "\nYour design determines quality. Be thorough and opinionated."
            ),
            tools=[design_system, recommend_stack, plan_structure, save_findings_to_context, get_latest_findings],
            verbose=True,
            max_iter=6,
            allow_delegation=False,
            llm=get_primary_llm(temperature=0.7),
        )

    @staticmethod
    def create_developer_agent():
        """Code implementation agent (Gemini API / Ollama)."""
        from secureflow.crew.tools import write_code, create_file, test_code

        return Agent(
            role="Senior Software Developer",
            goal=(
                "Read architecture design from shared context. Implement production-ready code with strong testing, "
                "clean structure, and comprehensive documentation. Save all code to shared context."
            ),
            backstory=(
                "Fullstack engineer with 18+ years building production systems at major tech companies. "
                "Expert in Python, JavaScript, databases, and cloud deployment. "
                "\n\nYOUR EXACT WORKFLOW:\n"
                "1. Read architecture: read_context_findings(agent_name='architect', key='architecture_design')\n"
                "2. Implement production-quality code for:\n"
                "   - Core modules\n"
                "   - Business logic\n"
                "   - API endpoints\n"
                "   - Database models\n"
                "   - Configuration\n"
                "3. Create all files:\n"
                "   - Organized source code\n"
                "   - Config files (setup.py, package.json)\n"
                "   - Init scripts, test stubs, docs\n"
                "4. Follow best practices:\n"
                "   - Error handling\n"
                "   - Logging and observability\n"
                "   - Security and performance\n"
                "5. Save code: save_findings_to_context key='implementation_code'\n"
                "\nWrite code you'll support for 5+ years in production. Quality is paramount."
            ),
            tools=[write_code, create_file, test_code, read_context_findings, save_findings_to_context, get_all_findings],
            verbose=True,
            max_iter=8,
            allow_delegation=False,
            llm=get_secondary_llm(temperature=0.7),
        )

    @staticmethod
    def create_reviewer_agent():
        """Code quality review agent (Gemini API / Ollama)."""
        from secureflow.crew.tools import review_code, suggest_improvements, find_bugs

        return Agent(
            role="Code Quality Reviewer",
            goal=(
                "Read architecture and implementation code from shared context. Perform comprehensive code review, "
                "identify bugs and security issues, suggest improvements. Ensure code meets production standards."
            ),
            backstory=(
                "Principal engineer with 20+ years in code quality and security review. "
                "Former tech lead at security-critical companies. "
                "\n\nYOUR EXACT REVIEW PROCESS:\n"
                "1. Read architecture & code from context:\n"
                "   - read_context_findings(agent_name='architect', key='architecture_design')\n"
                "   - read_context_findings(agent_name='developer', key='implementation_code')\n"
                "2. Review for quality:\n"
                "   - Code clarity and maintainability\n"
                "   - Bugs and logical errors\n"
                "   - Security (OWASP top 10)\n"
                "   - Performance\n"
                "   - Test coverage\n"
                "   - Documentation\n"
                "3. Rate issues:\n"
                "   - CRITICAL: Security, data loss, system failure\n"
                "   - HIGH: Major bugs, architecture violations\n"
                "   - MEDIUM: Performance, maintainability\n"
                "   - LOW: Style, minor improvements\n"
                "4. Provide specific code recommendations\n"
                "5. Save review: save_findings_to_context key='code_review'\n"
                "\nQuality gates are in your hands. Find real problems before production."
            ),
            tools=[review_code, suggest_improvements, find_bugs, read_context_findings, get_all_findings, get_latest_findings],
            verbose=True,
            max_iter=5,
            allow_delegation=False,
            llm=get_reporting_llm(temperature=0.5),
        )


def create_agents():
    """Factory function to create all three security agents."""
    return {
        "recon": CrewAgents.create_recon_agent(),
        "analyst": CrewAgents.create_analyst_agent(),
        "reporter": CrewAgents.create_reporter_agent(),
    }


def create_dev_agents():
    """Factory function to create all three development agents."""
    return {
        "architect": DevAgents.create_architect_agent(),
        "developer": DevAgents.create_developer_agent(),
        "reviewer": DevAgents.create_reviewer_agent(),
    }
