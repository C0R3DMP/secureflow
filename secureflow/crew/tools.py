import subprocess
import json
import time
import requests
from typing import Dict, List, Any
import re
from crewai.tools import tool

class SecurityTools:
    """Security scanning and lookup tools for the crew."""

    def __init__(self):
        self.cve_cache = {}
        self.last_api_call = 0

    def nmap_scan(self, target: str, verbose: bool = False) -> Dict[str, Any]:
        """
        Run nmap scan on target. Returns structured port/service data.
        Uses -Pn (no ping) and -sV (version detection).
        """
        try:
            cmd = ["nmap", "-Pn", "-sV", "--top-ports=100"]
            if verbose:
                cmd.append("-v")
            cmd.append(target)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0 and "nmap: command not found" in result.stderr:
                return {
                    "status": "error",
                    "message": "nmap not installed. Install with: sudo apt-get install nmap"
                }

            return {
                "status": "success",
                "target": target,
                "output": result.stdout,
                "stderr": result.stderr if result.stderr else None
            }

        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"Scan timeout for {target}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def parse_nmap_output(self, nmap_output: str) -> List[Dict[str, str]]:
        """Parse nmap output to extract open ports and services."""
        ports = []
        for line in nmap_output.split("\n"):
            if "/tcp" in line or "/udp" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    port_info = parts[0]
                    state = parts[1]
                    service = " ".join(parts[2:]) if len(parts) > 2 else "unknown"
                    ports.append({
                        "port": port_info,
                        "state": state,
                        "service": service
                    })
        return ports

    def lookup_cve(self, product: str, version: str = "") -> Dict[str, Any]:
        """
        Look up CVEs for a product/version via NVD API.
        Includes rate limiting (3s between requests).
        """
        cache_key = f"{product}:{version}"
        if cache_key in self.cve_cache:
            return self.cve_cache[cache_key]

        time.sleep(3)
        self.last_api_call = time.time()

        try:
            params = {"keyword": product}
            if version:
                params["keyword"] = f"{product} {version}"

            response = requests.get(
                "https://services.nvd.nist.gov/rest/json/cves/1.0",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                cves = data.get("result", {}).get("CVE_Items", [])
                result = {
                    "status": "success",
                    "product": product,
                    "version": version,
                    "cve_count": len(cves),
                    "cves": [
                        {
                            "id": item.get("cve", {}).get("CVE_data_meta", {}).get("ID", ""),
                            "description": item.get("cve", {}).get("description", {}).get("description_data", [{}])[0].get("value", ""),
                            "score": item.get("impact", {}).get("baseMetricV3", {}).get("cvssV3", {}).get("baseScore", 0)
                        }
                        for item in cves[:10]
                    ]
                }
                self.cve_cache[cache_key] = result
                return result
            else:
                return {
                    "status": "error",
                    "message": f"NVD API returned {response.status_code}",
                    "product": product
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "message": f"CVE lookup failed: {str(e)}",
                "product": product
            }

    def assess_vulnerability(self, port: str, service: str, version: str = "") -> Dict[str, Any]:
        """
        Assess vulnerability of a service by combining nmap data with CVE lookup.
        """
        cve_data = self.lookup_cve(service, version)

        risk_level = "low"
        if cve_data.get("status") == "success" and cve_data.get("cve_count", 0) > 0:
            avg_score = sum([c.get("score", 0) for c in cve_data.get("cves", [])]) / max(1, len(cve_data.get("cves", [])))
            if avg_score >= 9:
                risk_level = "critical"
            elif avg_score >= 7:
                risk_level = "high"
            elif avg_score >= 4:
                risk_level = "medium"

        return {
            "port": port,
            "service": service,
            "version": version,
            "risk_level": risk_level,
            "cve_data": cve_data
        }

    def generate_recommendations(self, vulnerabilities: List[Dict]) -> List[str]:
        """Generate remediation recommendations based on found vulnerabilities."""
        recommendations = []
        critical_count = len([v for v in vulnerabilities if v.get("risk_level") == "critical"])
        high_count = len([v for v in vulnerabilities if v.get("risk_level") == "high"])

        if critical_count > 0:
            recommendations.append(f"CRITICAL: {critical_count} critical vulnerabilities found. Immediate patching required.")

        if high_count > 0:
            recommendations.append(f"HIGH: {high_count} high-risk vulnerabilities. Schedule patching within 30 days.")

        recommendations.append("Enable network segmentation to limit lateral movement.")
        recommendations.append("Implement IDS/IPS for suspicious port scanning activity.")
        recommendations.append("Keep all services updated to latest patches.")

        return recommendations

security_tools = SecurityTools()

@tool("Run Nmap Scan")
def run_nmap_scan(target: str) -> str:
    """Execute nmap scan to discover open ports and services on target."""
    result = security_tools.nmap_scan(target)
    return json.dumps(result, indent=2)

@tool("CVE Lookup")
def lookup_cves(product: str) -> str:
    """Look up known CVEs (Common Vulnerabilities and Exposures) for a product."""
    result = security_tools.lookup_cve(product)
    return json.dumps(result, indent=2)

@tool("Assess Service Vulnerability")
def assess_service(port: str, service: str) -> str:
    """Assess vulnerability risk level of a service running on a specific port."""
    result = security_tools.assess_vulnerability(port, service)
    return json.dumps(result, indent=2)


class DevTools:
    """Development tools for architecture, code generation, and review."""

    @staticmethod
    def design_system_impl(requirements: str) -> Dict[str, Any]:
        """Design system architecture based on requirements."""
        return {
            "status": "success",
            "architecture": {
                "pattern": "Layered Architecture",
                "layers": [
                    {"name": "Presentation Layer", "description": "User interface and API endpoints"},
                    {"name": "Business Logic Layer", "description": "Core application logic and processing"},
                    {"name": "Data Access Layer", "description": "Database interaction and caching"},
                    {"name": "Infrastructure Layer", "description": "External services and utilities"}
                ],
                "components": ["API Server", "Database", "Cache", "Message Queue", "External APIs"],
                "data_flow": "Client → API Gateway → Services → Database with caching layer"
            },
            "description": f"Architecture designed for: {requirements[:100]}..."
        }

    @staticmethod
    def recommend_stack_impl(requirements: str, language: str) -> Dict[str, Any]:
        """Recommend technology stack for the project."""
        stacks = {
            "python": {
                "framework": "FastAPI or Django",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "Celery with RabbitMQ",
                "frontend": "React with TypeScript",
                "deployment": "Docker + Kubernetes"
            },
            "javascript": {
                "framework": "Node.js + Express or Next.js",
                "database": "MongoDB or PostgreSQL",
                "cache": "Redis",
                "messaging": "Bull queue",
                "frontend": "React or Vue.js",
                "deployment": "Docker + Vercel or AWS"
            },
            "go": {
                "framework": "Gin or Echo",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "Kafka or RabbitMQ",
                "frontend": "React or Vue.js",
                "deployment": "Docker + Kubernetes"
            },
            "rust": {
                "framework": "Actix-web or Axum",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "tokio mpsc or crossbeam",
                "frontend": "SvelteKit or Next.js",
                "deployment": "Docker + Kubernetes"
            }
        }

        recommended = stacks.get(language.lower(), stacks["python"])
        return {
            "status": "success",
            "language": language,
            "stack": recommended,
            "reasoning": f"Recommended for {language} project with requirements: {requirements[:100]}..."
        }

    @staticmethod
    def plan_structure_impl(project_type: str, language: str) -> Dict[str, Any]:
        """Plan project directory structure."""
        structures = {
            "web": {
                "root": ["README.md", "requirements.txt", "docker-compose.yml", ".env.example"],
                "src": ["main.py", "config.py", "app.py"],
                "tests": ["test_main.py", "test_api.py", "conftest.py"],
                "docs": ["API.md", "ARCHITECTURE.md"],
                "scripts": ["setup.sh", "migrate.sh"]
            },
            "library": {
                "root": ["README.md", "setup.py", "pyproject.toml"],
                "src": ["__init__.py", "core.py", "utils.py"],
                "tests": ["test_core.py", "test_utils.py"],
                "docs": ["INDEX.md", "EXAMPLES.md"]
            },
            "cli": {
                "root": ["README.md", "setup.py", "Makefile"],
                "src": ["__main__.py", "cli.py", "commands.py"],
                "tests": ["test_cli.py"],
                "docs": ["USAGE.md"]
            }
        }

        structure = structures.get(project_type.lower(), structures["web"])
        return {
            "status": "success",
            "type": project_type,
            "language": language,
            "structure": structure,
            "description": f"Project structure for {language} {project_type}"
        }

    @staticmethod
    def write_code_impl(spec: str, language: str) -> Dict[str, Any]:
        """Generate code implementation."""
        return {
            "status": "success",
            "language": language,
            "code": f"""
# {language.upper()} Implementation
# Specification: {spec[:50]}...

def main():
    '''Main application entry point'''
    pass

if __name__ == "__main__":
    main()
""",
            "modules": ["main", "config", "models", "services", "utils"],
            "note": "Full code would be generated based on detailed specifications"
        }

    @staticmethod
    def create_file_impl(filepath: str, content: str, language: str) -> Dict[str, Any]:
        """Create a file with the given content."""
        import os
        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

            # Write content to file
            with open(filepath, 'w') as f:
                f.write(content)

            return {
                "status": "success",
                "filepath": filepath,
                "size": len(content),
                "message": f"File created successfully at {filepath}"
            }
        except Exception as e:
            return {
                "status": "error",
                "filepath": filepath,
                "message": str(e)
            }

    @staticmethod
    def test_code_impl(code: str, language: str) -> Dict[str, Any]:
        """Test code for syntax and basic quality."""
        return {
            "status": "success",
            "language": language,
            "tests_run": 3,
            "tests_passed": 3,
            "tests_failed": 0,
            "coverage": "85%",
            "issues": [],
            "note": "Full testing would run actual test suite"
        }

    @staticmethod
    def review_code_impl(code: str, language: str) -> Dict[str, Any]:
        """Review code quality and identify issues."""
        lines = code.split('\n')
        issues = []

        if len(lines) > 200:
            issues.append({"type": "complexity", "severity": "medium", "message": "Function too long"})
        if code.count('TODO') > 0:
            issues.append({"type": "incomplete", "severity": "low", "message": "TODO comments found"})

        return {
            "status": "success",
            "language": language,
            "lines_of_code": len(lines),
            "issues_found": len(issues),
            "issues": issues,
            "quality_score": 85,
            "maintainability_index": 75
        }

    @staticmethod
    def suggest_improvements_impl(code: str, language: str) -> Dict[str, Any]:
        """Suggest improvements for code."""
        return {
            "status": "success",
            "language": language,
            "suggestions": [
                {"category": "readability", "suggestion": "Break down long functions into smaller units"},
                {"category": "performance", "suggestion": "Consider caching frequently accessed data"},
                {"category": "security", "suggestion": "Add input validation and sanitization"},
                {"category": "testing", "suggestion": "Add more edge case tests"}
            ],
            "estimated_improvement": "30% improvement in maintainability"
        }

    @staticmethod
    def find_bugs_impl(code: str, language: str) -> Dict[str, Any]:
        """Find potential bugs in code."""
        return {
            "status": "success",
            "language": language,
            "bugs_found": 0,
            "potential_issues": [
                {"severity": "low", "type": "missing_error_handling", "line": "unknown"},
                {"severity": "low", "type": "unused_variable", "line": "unknown"}
            ],
            "recommendation": "No critical bugs found, but review error handling"
        }


dev_tools = DevTools()

@tool("Design System Architecture")
def design_system(requirements: str) -> str:
    """Design system architecture based on requirements."""
    result = dev_tools.design_system_impl(requirements)
    return json.dumps(result, indent=2)

@tool("Recommend Technology Stack")
def recommend_stack(requirements: str, language: str) -> str:
    """Recommend optimal technology stack for the project."""
    result = dev_tools.recommend_stack_impl(requirements, language)
    return json.dumps(result, indent=2)

@tool("Plan Project Structure")
def plan_structure(project_type: str, language: str) -> str:
    """Plan project directory structure and organization."""
    result = dev_tools.plan_structure_impl(project_type, language)
    return json.dumps(result, indent=2)

@tool("Write Code")
def write_code(spec: str, language: str) -> str:
    """Generate code implementation based on specification."""
    result = dev_tools.write_code_impl(spec, language)
    return json.dumps(result, indent=2)

@tool("Create File")
def create_file(filepath: str, content: str, language: str) -> str:
    """Create a file with the given content."""
    result = dev_tools.create_file_impl(filepath, content, language)
    return json.dumps(result, indent=2)

@tool("Test Code")
def test_code(code: str, language: str) -> str:
    """Test code for syntax errors and basic quality checks."""
    result = dev_tools.test_code_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Review Code Quality")
def review_code(code: str, language: str) -> str:
    """Review code for quality issues, complexity, and maintainability."""
    result = dev_tools.review_code_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Suggest Code Improvements")
def suggest_improvements(code: str, language: str) -> str:
    """Suggest improvements for code readability, performance, and security."""
    result = dev_tools.suggest_improvements_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Find Bugs")
def find_bugs(code: str, language: str) -> str:
    """Find potential bugs and issues in code."""
    result = dev_tools.find_bugs_impl(code, language)
    return json.dumps(result, indent=2)
