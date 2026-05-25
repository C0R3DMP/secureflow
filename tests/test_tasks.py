"""Test crew tasks."""

import pytest
from crewai import Task


def test_create_security_tasks():
    """Test creating security assessment tasks."""
    from secureflow.crew.tasks import create_security_tasks

    target = "localhost"
    tasks = create_security_tasks(target)

    assert isinstance(tasks, dict)
    assert "recon" in tasks
    assert "analysis" in tasks
    assert "reporting" in tasks

    for task in tasks.values():
        assert isinstance(task, Task)
        assert target in task.description


def test_create_dev_tasks():
    """Test creating development tasks."""
    from secureflow.crew.tasks import create_dev_tasks

    task = "Build a REST API"
    language = "python"
    output_dir = "/tmp/test"
    tasks = create_dev_tasks(task, language, output_dir)

    assert isinstance(tasks, dict)
    assert "architecture" in tasks
    assert "implementation" in tasks
    assert "review" in tasks

    for t in tasks.values():
        assert isinstance(t, Task)


def test_create_crew():
    """Test creating a security crew."""
    from secureflow.crew.tasks import create_crew
    from crewai import Crew

    target = "localhost"
    crew = create_crew(target)

    assert isinstance(crew, Crew)
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3


def test_create_dev_crew():
    """Test creating a development crew."""
    from secureflow.crew.tasks import create_dev_crew
    from crewai import Crew

    task = "Build a REST API"
    language = "python"
    output_dir = "/tmp/test"
    crew = create_dev_crew(task, language, output_dir)

    assert isinstance(crew, Crew)
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3


def test_create_code_review_crew():
    """Test creating a code review crew."""
    from secureflow.crew.tasks import create_code_review_crew
    from crewai import Crew

    code = "print('hello')"
    language = "python"
    crew = create_code_review_crew(code, language)

    assert isinstance(crew, Crew)
    assert len(crew.agents) >= 1
    assert len(crew.tasks) >= 1
