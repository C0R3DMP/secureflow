"""Test crew agents."""

import pytest
from crewai import Agent


def test_create_agents():
    """Test creating security agents."""
    from secureflow.crew.agents import create_agents

    agents = create_agents()

    assert isinstance(agents, dict)
    assert "recon" in agents
    assert "analyst" in agents
    assert "reporter" in agents

    for agent in agents.values():
        assert isinstance(agent, Agent)


def test_create_dev_agents():
    """Test creating development agents."""
    from secureflow.crew.agents import create_dev_agents

    agents = create_dev_agents()

    assert isinstance(agents, dict)
    assert "architect" in agents
    assert "developer" in agents
    assert "reviewer" in agents

    for agent in agents.values():
        assert isinstance(agent, Agent)


def test_recon_agent_properties():
    """Test recon agent has correct properties."""
    from secureflow.crew.agents import CrewAgents

    agent = CrewAgents.create_recon_agent()

    assert agent.role == "Security Reconnaissance Specialist"
    assert "network" in agent.goal.lower()
    assert len(agent.tools) > 0


def test_analyst_agent_properties():
    """Test analyst agent has correct properties."""
    from secureflow.crew.agents import CrewAgents

    agent = CrewAgents.create_analyst_agent()

    assert agent.role == "Vulnerability Analysis Expert"
    assert "vulnerab" in agent.goal.lower()
    assert len(agent.tools) > 0


def test_reporter_agent_properties():
    """Test reporter agent has correct properties."""
    from secureflow.crew.agents import CrewAgents

    agent = CrewAgents.create_reporter_agent()

    assert agent.role == "Security Report Specialist"
    assert "report" in agent.goal.lower()


def test_architect_agent_properties():
    """Test architect agent has correct properties."""
    from secureflow.crew.agents import DevAgents

    agent = DevAgents.create_architect_agent()

    assert agent.role == "Software Architect"
    assert "architecture" in agent.goal.lower()
    assert len(agent.tools) > 0


def test_developer_agent_properties():
    """Test developer agent has correct properties."""
    from secureflow.crew.agents import DevAgents

    agent = DevAgents.create_developer_agent()

    assert agent.role == "Senior Software Developer"
    assert "code" in agent.goal.lower()
    assert len(agent.tools) > 0


def test_reviewer_agent_properties():
    """Test reviewer agent has correct properties."""
    from secureflow.crew.agents import DevAgents

    agent = DevAgents.create_reviewer_agent()

    assert agent.role == "Code Quality Reviewer"
    assert "review" in agent.goal.lower()
    assert len(agent.tools) > 0
