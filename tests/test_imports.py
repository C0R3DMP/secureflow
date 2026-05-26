"""Test that all modules can be imported."""

import pytest


def test_import_secureflow():
    """Test main package import."""
    import secureflow
    assert hasattr(secureflow, "__version__")
    assert secureflow.__version__ == "0.1.0"


def test_import_config():
    """Test config module import."""
    from secureflow import config
    assert hasattr(config, "MCP_SECRET")
    assert hasattr(config, "GEMINI_API_KEY")


def test_import_cli():
    """Test CLI module import."""
    from secureflow import cli
    assert hasattr(cli, "main")


def test_import_server():
    """Test server module import."""
    from secureflow import server
    assert hasattr(server, "app")
    assert hasattr(server, "main")


def test_import_crew_agents():
    """Test crew agents module import."""
    from secureflow.crew import agents
    assert hasattr(agents, "CrewAgents")
    assert hasattr(agents, "DevAgents")
    assert hasattr(agents, "create_agents")
    assert hasattr(agents, "create_dev_agents")


def test_import_crew_tasks():
    """Test crew tasks module import."""
    from secureflow.crew import tasks
    assert hasattr(tasks, "create_security_tasks")
    assert hasattr(tasks, "create_dev_tasks")
    assert hasattr(tasks, "create_crew")
    assert hasattr(tasks, "create_dev_crew")


def test_import_crew_tools():
    """Test crew tools module import."""
    from secureflow.crew import tools
    assert hasattr(tools, "SecurityTools")
    assert hasattr(tools, "DevTools")
    assert hasattr(tools, "run_nmap_scan")
    assert hasattr(tools, "design_system")


def test_import_crew_memory():
    """Test crew memory module import."""
    from secureflow.crew import memory
    assert hasattr(memory, "SharedContext")


def test_import_crew_orchestrator():
    """Test crew orchestrator module import."""
    from secureflow.crew import orchestrator
    assert hasattr(orchestrator, "CrewOrchestrator")


def test_import_crew_dev_orchestrator():
    """Test dev orchestrator module import."""
    from secureflow.crew import dev_orchestrator
    assert hasattr(dev_orchestrator, "DevOrchestrator")


def test_all_crew_modules_importable():
    """Test that all crew modules are importable."""
    modules = [
        "secureflow.crew.agents",
        "secureflow.crew.tasks",
        "secureflow.crew.tools",
        "secureflow.crew.memory",
        "secureflow.crew.orchestrator",
        "secureflow.crew.dev_orchestrator",
    ]

    for module_name in modules:
        module = __import__(module_name, fromlist=[module_name.split(".")[-1]])
        assert module is not None, f"Failed to import {module_name}"
