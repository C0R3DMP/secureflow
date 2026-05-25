from crewai import Agent, LLM
from secureflow.crew.tools import run_nmap_scan, lookup_cves, assess_service
import os

# LLM Configuration with fallback chain: Claude → Gemini → Ollama

def get_claude_llm():
    """Claude agent with fallback to Gemini then Ollama."""
    return LLM(
        model="anthropic/claude-sonnet-4-20250514",
        temperature=0.7,
        api_key=os.getenv("ANTHROPIC_API_KEY", "")
    )

def get_gemini_llm():
    """Gemini agent for fast reconnaissance."""
    return LLM(
        model="gemini/gemini-2.0-flash",
        api_key=os.getenv("GEMINI_API_KEY", "")
    )

def get_ollama_reporter():
    """Ollama for report generation and analysis."""
    return LLM(
        model="ollama/qwen2.5-coder:7b",
        base_url="http://localhost:11434"
    )

def get_ollama_deepseek():
    """Ollama deepseek-r1 for exploitation analysis."""
    return LLM(
        model="ollama/deepseek-r1",
        base_url="http://localhost:11434"
    )

class CrewAgents:
    """Define specialized security agents with proper LLM routing."""

    @staticmethod
    def create_recon_agent():
        """Fast reconnaissance agent using Gemini."""
        return Agent(
            role="Security Reconnaissance Specialist",
            goal="Discover network topology, open ports, running services, and preliminary vulnerability surface",
            backstory=(
                "Expert in network mapping and service enumeration. Uses aggressive but safe "
                "scanning techniques to build complete target profiles. Fast thinker who prioritizes "
                "speed and breadth over depth."
            ),
            tools=[run_nmap_scan, lookup_cves],
            verbose=True,
            max_iter=5,
            allow_delegation=False,
            llm=get_gemini_llm(),
        )

    @staticmethod
    def create_analyst_agent():
        """Deep analysis agent using Claude."""
        return Agent(
            role="Vulnerability Analysis Expert",
            goal="Analyze discovered vulnerabilities, correlate CVEs, assess risk, and identify exploitation paths",
            backstory=(
                "Senior security researcher with 15+ years of experience. Known for deep technical "
                "analysis and connecting disparate findings into coherent threat narratives. Methodical "
                "and thorough, never misses critical details."
            ),
            tools=[assess_service, lookup_cves],
            verbose=True,
            max_iter=7,
            allow_delegation=False,
            llm=get_claude_llm(),
        )

    @staticmethod
    def create_reporter_agent():
        """Reporting agent using Ollama for documentation."""
        return Agent(
            role="Security Report Specialist",
            goal="Create comprehensive, executive-friendly security reports with clear remediation roadmaps",
            backstory=(
                "Former CISO who bridges the gap between technical security and business needs. "
                "Excels at translating complex findings into actionable, prioritized remediation "
                "strategies that stakeholders understand and support."
            ),
            tools=[],
            verbose=True,
            max_iter=4,
            allow_delegation=False,
            llm=get_ollama_reporter(),
        )

class DevAgents:
    """Define specialized development agents with proper LLM routing."""

    @staticmethod
    def create_architect_agent():
        """System architecture design agent using Claude."""
        from secureflow.crew.tools import design_system, recommend_stack, plan_structure

        return Agent(
            role="Software Architect",
            goal="Design robust system architecture, choose optimal technology stack, and plan scalable project structure",
            backstory=(
                "Principal architect with 20+ years of experience designing large-scale systems. "
                "Expert in pattern recognition, technology evaluation, and translating requirements "
                "into elegant architectural designs that teams can build upon."
            ),
            tools=[design_system, recommend_stack, plan_structure],
            verbose=True,
            max_iter=6,
            allow_delegation=False,
            llm=get_claude_llm(),
        )

    @staticmethod
    def create_developer_agent():
        """Code implementation agent using Gemini."""
        from secureflow.crew.tools import write_code, create_file, test_code

        return Agent(
            role="Senior Software Developer",
            goal="Write production-quality code, implement features, and create well-structured project files",
            backstory=(
                "Fullstack developer with 15+ years of experience building scalable applications. "
                "Known for writing clean, maintainable code, strong testing practices, and mentoring "
                "junior developers. Stays current with best practices and modern frameworks."
            ),
            tools=[write_code, create_file, test_code],
            verbose=True,
            max_iter=8,
            allow_delegation=False,
            llm=get_gemini_llm(),
        )

    @staticmethod
    def create_reviewer_agent():
        """Code quality review agent using Ollama."""
        from secureflow.crew.tools import review_code, suggest_improvements, find_bugs

        return Agent(
            role="Code Quality Reviewer",
            goal="Review code for quality, identify bugs, and suggest improvements for maintainability",
            backstory=(
                "Senior engineer and code review expert with deep knowledge of software design principles. "
                "Excels at identifying subtle bugs, security issues, and architectural problems. "
                "Provides constructive feedback that improves team quality and developer growth."
            ),
            tools=[review_code, suggest_improvements, find_bugs],
            verbose=True,
            max_iter=5,
            allow_delegation=False,
            llm=get_ollama_reporter(),
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
