"""Tests for the best-effort LLM quota tracker.

Roadmap item "Now #4". Verified live this week: a Gemini free-tier key's
*daily* quota (20 requests/day, separate from the well-documented 5/min rate
limit) was exhausted by a single full crew run, with a raw 429 the only
signal it had happened — after the next scan had already failed. This module
exists to surface *something* before that point, clearly marked as an
estimate since real server-side quota state isn't queryable in advance.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_quota_state():
    """Each test gets a clean slate — the module holds process-global state."""
    import secureflow.quota as quota_mod

    quota_mod._state.clear()
    yield
    quota_mod._state.clear()


def test_snapshot_starts_at_zero():
    from secureflow.quota import snapshot

    result = snapshot("gemini")
    assert result["attempts_today"] == 0
    assert result["known_limit"] is None
    assert result["exhausted_at"] is None
    assert result["estimate"] is True


def test_record_attempt_increments_count():
    from secureflow.quota import record_attempt, snapshot

    record_attempt("gemini")
    record_attempt("gemini")
    record_attempt("gemini")

    assert snapshot("gemini")["attempts_today"] == 3


def test_providers_are_tracked_independently():
    from secureflow.quota import record_attempt, snapshot

    record_attempt("gemini")
    record_attempt("gemini")
    record_attempt("openrouter")

    assert snapshot("gemini")["attempts_today"] == 2
    assert snapshot("openrouter")["attempts_today"] == 1


def test_record_quota_exhausted_parses_real_error_shape():
    """The exact 429 body shape observed live this week."""
    from secureflow.quota import record_quota_exhausted, snapshot

    real_error = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You "
        "exceeded your current quota...', 'status': 'RESOURCE_EXHAUSTED', "
        "'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
        "'violations': [{'quotaMetric': "
        "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
        "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
        "'quotaValue': '20'}]}]}}"
    )

    record_quota_exhausted("gemini", real_error)
    result = snapshot("gemini")

    assert result["known_limit"] == 20
    assert "free_tier_requests" in result["quota_metric"]
    assert result["exhausted_at"] is not None


def test_record_quota_exhausted_without_parseable_detail_still_marks_exhausted():
    """A provider whose error body doesn't match Gemini's shape must still
    record *that* it happened, even without a specific limit number."""
    from secureflow.quota import record_quota_exhausted, snapshot

    record_quota_exhausted("openrouter", "429 Too Many Requests")
    result = snapshot("openrouter")

    assert result["exhausted_at"] is not None
    assert result["known_limit"] is None


def test_snapshot_all_covers_every_requested_provider():
    from secureflow.quota import record_attempt, snapshot_all

    record_attempt("gemini")

    result = snapshot_all(["gemini", "openrouter", "ollama"])

    assert set(result.keys()) == {"gemini", "openrouter", "ollama"}
    assert result["gemini"]["attempts_today"] == 1
    assert result["ollama"]["attempts_today"] == 0


def test_daily_bucket_resets_on_date_rollover(monkeypatch):
    import secureflow.quota as quota_mod
    from datetime import datetime, timedelta, timezone

    quota_mod.record_attempt("gemini")
    assert quota_mod.snapshot("gemini")["attempts_today"] == 1

    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    real_today_key = quota_mod._today_key
    monkeypatch.setattr(quota_mod, "_today_key", lambda: tomorrow.strftime("%Y-%m-%d"))

    assert quota_mod.snapshot("gemini")["attempts_today"] == 0, "must not carry over to a new UTC day"


# ---------------------------------------------------------------------------
# Integration: both real call paths (the crew's CrewAI wrapper, and the
# direct-litellm chat path) must actually record through this tracker.
# ---------------------------------------------------------------------------

def test_gemini_llm_wrapper_records_attempts_and_exhaustion(monkeypatch):
    import secureflow.config as config_mod
    import secureflow.quota as quota_mod

    monkeypatch.setattr(config_mod, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config_mod.time, "sleep", lambda s: None)

    llm = config_mod.get_llm_with_rate_limit_fallback(model="gemini/gemini-2.5-flash")

    from crewai import LLM as RealLLM

    call_count = {"n": 0}

    def _fake_super_call(self, *a, **k):
        call_count["n"] += 1
        raise RuntimeError('429 quota exceeded {"quotaValue": "20"}')

    monkeypatch.setattr(RealLLM, "call", _fake_super_call)

    with pytest.raises(RuntimeError):
        llm.call("hi")

    result = quota_mod.snapshot("gemini")
    assert result["attempts_today"] == call_count["n"] >= 1
    assert result["exhausted_at"] is not None
    assert result["known_limit"] == 20


def test_chat_stream_reply_records_attempts_and_exhaustion(monkeypatch):
    import litellm

    import secureflow.chat as chat_mod
    import secureflow.quota as quota_mod

    monkeypatch.setattr(chat_mod, "_candidate_models", lambda: [{"model": "gemini/gemini-2.5-flash"}])

    def _boom(**kwargs):
        raise RuntimeError("429 rate limit exceeded")

    monkeypatch.setattr(litellm, "completion", _boom)

    with pytest.raises(chat_mod.ChatError):
        list(chat_mod.stream_reply([{"role": "user", "content": "hi"}]))

    result = quota_mod.snapshot("gemini")
    assert result["attempts_today"] == 1
    assert result["exhausted_at"] is not None


def test_chat_stream_reply_does_not_record_exhaustion_for_ordinary_errors(monkeypatch):
    """A connection-refused (e.g. Ollama not running) is not quota exhaustion —
    must not be misreported as such."""
    import litellm

    import secureflow.chat as chat_mod
    import secureflow.quota as quota_mod

    monkeypatch.setattr(chat_mod, "_candidate_models", lambda: [{"model": "ollama/qwen2.5-coder"}])

    def _boom(**kwargs):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(litellm, "completion", _boom)

    with pytest.raises(chat_mod.ChatError):
        list(chat_mod.stream_reply([{"role": "user", "content": "hi"}]))

    result = quota_mod.snapshot("ollama")
    assert result["attempts_today"] == 1
    assert result["exhausted_at"] is None


# ---------------------------------------------------------------------------
# /api/providers exposes it
# ---------------------------------------------------------------------------

def test_providers_endpoint_includes_quota_snapshot(monkeypatch):
    from secureflow import server
    from secureflow import quota as quota_mod

    quota_mod.record_attempt("gemini")

    monkeypatch.setattr(server, "is_claude_cli_available", lambda: False, raising=False)
    monkeypatch.setattr("secureflow.config.is_ollama_available", lambda *a, **k: False)
    monkeypatch.setattr(server, "_is_port_open", lambda *a, **k: False)

    result = server._get_providers_dict()

    assert "quota" in result["gemini"]
    assert result["gemini"]["quota"]["attempts_today"] == 1
    assert result["gemini"]["quota"]["estimate"] is True
    # The claude/anthropic key-naming bridge must actually work.
    assert "quota" in result["claude"]
