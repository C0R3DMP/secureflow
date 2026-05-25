"""Test crew tools."""

import pytest
import json


def test_security_tools_instantiation():
    """Test that SecurityTools can be instantiated."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    assert tools is not None


def test_dev_tools_instantiation():
    """Test that DevTools can be instantiated."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    assert tools is not None


def test_design_system_tool():
    """Test design_system tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.design_system_impl("Build a web application")
    assert isinstance(result, dict)
    assert "architecture" in result
    assert result["status"] == "success"


def test_recommend_stack_tool():
    """Test recommend_stack tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.recommend_stack_impl("Build a web application", "python")
    assert isinstance(result, dict)
    assert "stack" in result
    assert result["status"] == "success"


def test_plan_structure_tool():
    """Test plan_structure tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.plan_structure_impl("web", "python")
    assert isinstance(result, dict)
    assert "structure" in result
    assert result["status"] == "success"


def test_write_code_tool():
    """Test write_code tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.write_code_impl("Calculate fibonacci", "python")
    assert isinstance(result, dict)
    assert "code" in result
    assert result["status"] == "success"


def test_review_code_tool():
    """Test review_code tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "def hello(): print('world')"
    result = tools.review_code_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert "quality_score" in result


def test_find_bugs_tool():
    """Test find_bugs tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "def test(): pass"
    result = tools.find_bugs_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"


def test_suggest_improvements_tool():
    """Test suggest_improvements tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "x=1+2"
    result = tools.suggest_improvements_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert "suggestions" in result
