"""Pytest configuration and fixtures."""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load test environment
test_env_path = Path(__file__).parent.parent / ".env.example"
if test_env_path.exists():
    load_dotenv(test_env_path)


@pytest.fixture
def test_data_dir():
    """Return path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture
def sample_code():
    """Sample Python code for testing."""
    return '''
def hello_world():
    """Print hello world."""
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
'''


@pytest.fixture
def sample_target():
    """Sample security target for testing."""
    return "localhost"


@pytest.fixture
def sample_task():
    """Sample development task."""
    return "Create a simple REST API with user authentication"
