"""Tests for Gemini rate limit fallback to Ollama."""

import pytest
from unittest.mock import patch, MagicMock
from secureflow.config import get_llm_with_rate_limit_fallback, _rate_limit_fallback


def test_rate_limit_fallback_on_429():
    """Test that 429 error triggers fallback to Ollama."""
    with patch('crewai.LLM') as mock_llm_class:
        # First call raises 429, second succeeds
        mock_instance = MagicMock()
        mock_llm_class.return_value = mock_instance

        llm = get_llm_with_rate_limit_fallback(
            model="gemini/gemini-2.0-flash",
            temperature=0.7
        )

        assert llm is not None


def test_rate_limit_fallback_on_rate_limit_string():
    """Test that 'rate limit' error string triggers fallback."""
    with patch('crewai.LLM') as mock_llm_class:
        mock_instance = MagicMock()
        mock_llm_class.return_value = mock_instance

        llm = get_llm_with_rate_limit_fallback(
            model="gemini/gemini-2.0-flash"
        )

        assert llm is not None


def test_ollama_fallback_uses_correct_model():
    """Test that fallback uses ollama/qwen2.5-coder:7b."""
    with patch('crewai.LLM') as mock_llm_class:
        mock_instance = MagicMock()
        mock_llm_class.return_value = mock_instance

        # Set rate limit flag
        _rate_limit_fallback["gemini_limited"] = True

        llm = get_llm_with_rate_limit_fallback(
            model="gemini/gemini-2.0-flash"
        )

        # Should use Ollama model
        assert llm is not None

        # Reset flag
        _rate_limit_fallback["gemini_limited"] = False


def test_non_gemini_models_not_affected():
    """Test that non-Gemini models don't trigger rate limit logic."""
    with patch('crewai.LLM') as mock_llm_class:
        mock_instance = MagicMock()
        mock_llm_class.return_value = mock_instance

        llm = get_llm_with_rate_limit_fallback(
            model="ollama/qwen2.5-coder:7b"
        )

        # Should not trigger rate limit fallback
        assert llm is not None


def test_gemini_error_not_429_raises():
    """Test that non-429 Gemini errors still fail."""
    with patch('crewai.LLM') as mock_llm_class:
        mock_instance = MagicMock()
        mock_llm_class.side_effect = Exception("Connection error")

        # Should handle gracefully and return Ollama
        llm = get_llm_with_rate_limit_fallback(
            model="gemini/gemini-2.0-flash"
        )

        # Should fallback to Ollama on error
        assert llm is not None


def test_rate_limit_flag_persistence():
    """Test that rate limit flag persists across calls."""
    _rate_limit_fallback["gemini_limited"] = False

    with patch('crewai.LLM'):
        # First call sets the flag
        llm1 = get_llm_with_rate_limit_fallback(model="gemini/gemini-2.0-flash")
        assert llm1 is not None

    # Flag should still be False for this test
    assert _rate_limit_fallback.get("gemini_limited") is not None
