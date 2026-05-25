from crewai import Task
from secureflow.crew.agents import create_agents, create_dev_agents

def create_security_tasks(target: str):
    """Create security assessment tasks for the crew."""
    agents = create_agents()

    recon_task = Task(
        description=f"""
        Conduct comprehensive network reconnaissance on {target}.

        1. Execute nmap scan to identify open ports and running services
        2. Look up known CVEs for each discovered service
        3. Document initial attack surface and service versions

        Provide structured output with:
        - Open ports and services
        - Service versions detected
        - Known vulnerabilities per service
        - Quick risk assessment (low/medium/high)
        """,
        expected_output="Detailed reconnaissance report with ports, services, and CVE findings",
        agent=agents["recon"],
    )

    analysis_task = Task(
        description=f"""
        Perform deep vulnerability analysis on {target} based on reconnaissance findings.

        1. Analyze each discovered service for exploitability
        2. Correlate CVEs and identify common exploitation chains
        3. Assess business impact and risk severity (CVSS-based)
        4. Identify services that could lead to lateral movement
        5. Prioritize vulnerabilities by severity and exploitability

        Provide structured analysis with:
        - Top 5 critical vulnerabilities
        - Exploitation prerequisites
        - Potential impact (data theft, RCE, DoS, etc.)
        - Lateral movement risks
        - Exposure severity (internal vs internet-facing)
        """,
        expected_output="Risk assessment and vulnerability prioritization analysis",
        agent=agents["analyst"],
        context=[recon_task],
    )

    reporting_task = Task(
        description=f"""
        Create an executive-ready security assessment report for {target}.

        Based on reconnaissance and analysis findings:

        1. Write executive summary (1 page, non-technical)
        2. Create detailed findings section with CVSS scores
        3. Develop remediation roadmap with:
           - Immediate actions (critical vulnerabilities)
           - 30-day remediation plan
           - 90-day hardening plan
        4. Include risk metrics and KPIs
        5. Suggest security controls to implement

        Format as professional HTML report suitable for board review.
        """,
        expected_output="Professional HTML security report with executive summary and remediation roadmap",
        agent=agents["reporter"],
        context=[recon_task, analysis_task],
    )

    return {
        "recon": recon_task,
        "analysis": analysis_task,
        "reporting": reporting_task,
    }

def create_recon_tasks(target: str):
    """Create lightweight recon-only tasks."""
    agents = create_agents()

    recon_task = Task(
        description=f"""
        Quick network reconnaissance on {target}.

        1. Run nmap scan with top 100 ports
        2. Identify major services and versions
        3. Check for obvious CVEs
        """,
        expected_output="Recon findings with open ports and services",
        agent=agents["recon"],
    )

    return {"recon": recon_task}

def create_crew(target: str):
    """Factory function to create a full security crew."""
    from crewai import Crew
    agents = create_agents()
    tasks = create_security_tasks(target)

    crew = Crew(
        agents=[agents["recon"], agents["analyst"], agents["reporter"]],
        tasks=[tasks["recon"], tasks["analysis"], tasks["reporting"]],
        verbose=True,
    )

    return crew

def create_recon_crew(target: str):
    """Factory function to create a lightweight recon-only crew."""
    from crewai import Crew
    agents = create_agents()
    tasks = create_recon_tasks(target)

    crew = Crew(
        agents=[agents["recon"]],
        tasks=[tasks["recon"]],
        verbose=True,
    )

    return crew


def create_dev_tasks(task: str, language: str, output_dir: str):
    """Create development workflow tasks for the crew."""
    agents = create_dev_agents()

    architecture_task = Task(
        description=f"""
        Design system architecture for: {task}

        Using technology: {language}

        1. Analyze requirements and identify key components
        2. Design system architecture with proper layers
        3. Choose appropriate technology stack and frameworks
        4. Plan project directory structure and organization
        5. Document design decisions and rationale

        Provide structured design with:
        - Architecture diagram (text-based)
        - Technology stack recommendations
        - Project folder structure
        - Data flow description
        - Component dependencies
        """,
        expected_output="Complete architecture specification with tech stack and project structure",
        agent=agents["architect"],
    )

    implementation_task = Task(
        description=f"""
        Implement the {language} application based on the architecture.

        Requirements: {task}
        Output directory: {output_dir}

        1. Review the architecture design from the architect
        2. Write core application modules and services
        3. Create project files and directory structure
        4. Implement key features from requirements
        5. Add configuration and setup files
        6. Create test stubs and documentation

        Generate complete, production-ready code with:
        - All necessary source files
        - Configuration management
        - Initialization and setup code
        - Basic test structure
        - README and documentation
        """,
        expected_output="Complete application code and all necessary project files",
        agent=agents["developer"],
        context=[architecture_task],
    )

    review_task = Task(
        description=f"""
        Review the generated {language} code for quality and best practices.

        Focus areas:
        1. Code style and consistency
        2. Potential bugs and edge cases
        3. Performance and scalability
        4. Security considerations
        5. Testing coverage
        6. Documentation quality

        Provide comprehensive review with:
        - Quality assessment (score out of 100)
        - List of issues found (by severity)
        - Specific suggestions for improvement
        - Refactoring recommendations
        - Best practices not followed
        - Performance optimization ideas
        """,
        expected_output="Detailed code review report with findings and improvement recommendations",
        agent=agents["reviewer"],
        context=[architecture_task, implementation_task],
    )

    return {
        "architecture": architecture_task,
        "implementation": implementation_task,
        "review": review_task,
    }


def create_code_review_tasks(code: str, language: str):
    """Create code review tasks for existing code."""
    agents = create_dev_agents()

    review_task = Task(
        description=f"""
        Review the following {language} code for quality and issues:

        Code to review:
        {code[:500]}...

        Focus on:
        1. Code style and naming conventions
        2. Potential bugs and logical errors
        3. Security vulnerabilities
        4. Performance concerns
        5. Maintainability and readability
        6. Test coverage assessment

        Provide:
        - Quality score
        - List of issues (organized by severity)
        - Specific improvement suggestions
        - Best practices violations
        """,
        expected_output="Comprehensive code review with issues and recommendations",
        agent=agents["reviewer"],
    )

    return {"review": review_task}


def create_dev_crew(task: str, language: str, output_dir: str):
    """Factory function to create a full development crew."""
    from crewai import Crew
    agents = create_dev_agents()
    tasks = create_dev_tasks(task, language, output_dir)

    crew = Crew(
        agents=[agents["architect"], agents["developer"], agents["reviewer"]],
        tasks=[tasks["architecture"], tasks["implementation"], tasks["review"]],
        verbose=True,
    )

    return crew


def create_code_review_crew(code: str, language: str):
    """Factory function to create a code review crew."""
    from crewai import Crew
    agents = create_dev_agents()
    tasks = create_code_review_tasks(code, language)

    crew = Crew(
        agents=[agents["reviewer"]],
        tasks=[tasks["review"]],
        verbose=True,
    )

    return crew
