from crewai import Agent, LLM
from secureflow.config import completion_with_fallback, call_opencode
from secureflow.crew.tools import run_nmap_scan, lookup_cves, assess_service
import litellm
from typing import Any, Optional

# Dev tools will be imported after they're created to avoid circular imports
# They'll be added dynamically in DevAgents methods

class OpenCodeLLM:
    """Wrapper for OpenCode HTTP API to work with CrewAI agents."""

    def __init__(self, opencode_url: str = "http://localhost:4096"):
        self.model = "opencode-http"
        self.opencode_url = opencode_url

    def generate(
        self,
        messages: list,
        stop: Optional[list] = None,
        **kwargs: Any,
    ) -> str:
        """
        CrewAI calls this method. Convert messages to prompt and send to OpenCode.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            stop: Optional stop sequences (not used for OpenCode)
            **kwargs: Additional arguments (max_tokens, temperature, etc.)

        Returns:
            Response text from OpenCode
        """
        if not messages:
            return "No messages provided"

        # Convert CrewAI message format to a single prompt
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            prompt_parts.append(f"{role}: {content}")

        prompt = "\n".join(prompt_parts)

        try:
            return call_opencode(prompt, opencode_url=self.opencode_url)
        except Exception as e:
            return f"Error calling OpenCode: {str(e)}"

class CrewAgents:
    """Define specialized security agents with fallback LLM routing."""

    @staticmethod
    def create_recon_agent():
        """Fast reconnaissance agent using Ollama."""
        # Use Ollama for reconnaissance
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
        )

    @staticmethod
    def create_analyst_agent(opencode_url: str = "http://localhost:4096"):
        """Deep analysis agent using Ollama LLM."""
        # Use Ollama for deep vulnerability analysis
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
        )

    @staticmethod
    def create_reporter_agent():
        """Reporting agent using local Ollama for documentation."""
        # Use Ollama for report generation
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
        )

class DevAgents:
    """Define specialized development agents with fallback LLM routing."""

    @staticmethod
    def create_architect_agent(opencode_url: str = "http://localhost:4096"):
        """System architecture design agent using Ollama LLM."""
        # Import here to avoid circular imports
        from secureflow.crew.tools import design_system, recommend_stack, plan_structure

        # Use Ollama for architecture design
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
        )

    @staticmethod
    def create_developer_agent():
        """Code implementation agent using Ollama for development."""
        # Import here to avoid circular imports
        from secureflow.crew.tools import write_code, create_file, test_code

        # Use Ollama for code development
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
        )

    @staticmethod
    def create_reviewer_agent():
        """Code quality review agent using local Ollama."""
        # Import here to avoid circular imports
        from secureflow.crew.tools import review_code, suggest_improvements, find_bugs

        # Use Ollama for code review
        llm = LLM(model="ollama/qwen2.5-coder:7b", base_url="http://localhost:11434")
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
            llm=llm,
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
