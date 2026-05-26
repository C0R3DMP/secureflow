import os
import time
import requests
import litellm
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENCODE_URL = os.getenv("OPENCODE_URL", "http://localhost:4096")
MCP_SECRET = os.getenv("MCP_SECRET", "")

# Rate limit tracking
_rate_limit_fallback = {"gemini_limited": False, "last_rate_limit_time": 0}


def is_ollama_available(base_url: str = OLLAMA_BASE_URL, timeout: int = 2) -> bool:
    """Check if Ollama server is available and healthy."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Ollama health check failed: {e}")
        return False


class LLMProviderStatus:
    """Track status and quota of LLM providers."""

    PROVIDERS = {
        "claude": {
            "api_key_var": ANTHROPIC_API_KEY,
            "type": "api",
            "priority": 1,
            "available": bool(ANTHROPIC_API_KEY),
        },
        "gemini": {
            "api_key_var": GEMINI_API_KEY,
            "type": "api",
            "priority": 2,
            "available": bool(GEMINI_API_KEY),
        },
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "type": "local",
            "priority": 3,
            "available": is_ollama_available(),
        },
        "opencode": {
            "base_url": OPENCODE_URL,
            "type": "local",
            "priority": 4,
            "available": False,  # Check dynamically in check_health
        },
    }

    @staticmethod
    def check_health(provider: str) -> bool:
        """Check if a provider is healthy and available."""
        if provider == "claude":
            return bool(ANTHROPIC_API_KEY)
        elif provider == "gemini":
            return bool(GEMINI_API_KEY) and not _rate_limit_fallback.get("gemini_limited", False)
        elif provider == "ollama":
            return is_ollama_available()
        elif provider == "opencode":
            try:
                response = requests.get(f"{OPENCODE_URL}/session", timeout=2)
                return response.status_code < 500
            except:
                return False
        return False

    @staticmethod
    def get_available_providers() -> list:
        """Get list of available providers sorted by priority."""
        available = []
        for provider, info in LLMProviderStatus.PROVIDERS.items():
            if LLMProviderStatus.check_health(provider):
                available.append((provider, info["priority"]))
        return sorted(available, key=lambda x: x[1])

def init_llms():
    """Initialize litellm with fallback chain: Gemini → Ollama local (OpenCode for Analyst)."""
    config = {
        "gemini": {
            "api_key": GEMINI_API_KEY,
            "model": "gemini/gemini-2.0-flash",
        },
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "model": "ollama/qwen2.5-coder",
        },
    }
    return config

def get_fallback_chain():
    """Return the LLM fallback order: Gemini → Ollama (Claude via CLI)."""
    return [
        {"model": "gemini/gemini-2.0-flash"},
        {"model": "ollama/qwen2.5-coder", "base_url": OLLAMA_BASE_URL},
    ]

def call_opencode(prompt: str, opencode_url: str = "http://localhost:4096", max_retries: int = 60) -> str:
    """
    Call OpenCode via HTTP API.
    Requires: opencode serve --port 4096 running.

    Flow:
    1. POST /session → get session_id
    2. POST /session/{id}/message → send prompt
    3. Poll GET /session/{id} → wait for completion
    4. Return response text
    """
    try:
        headers = {"Content-Type": "application/json"}

        # Step 1: Create session
        session_resp = requests.post(
            f"{opencode_url}/session",
            json={},
            headers=headers,
            timeout=10,
        )
        session_resp.raise_for_status()
        session_id = session_resp.json().get("id")
        if not session_id:
            raise RuntimeError("No session ID returned from OpenCode")

        # Step 2: Send message (prompt)
        msg_resp = requests.post(
            f"{opencode_url}/session/{session_id}/message",
            json={"content": prompt},
            headers=headers,
            timeout=10,
        )
        msg_resp.raise_for_status()

        # Step 3: Poll for completion
        retries = 0
        while retries < max_retries:
            status_resp = requests.get(
                f"{opencode_url}/session/{session_id}",
                headers=headers,
                timeout=10,
            )
            status_resp.raise_for_status()
            session_data = status_resp.json()

            if session_data.get("status") == "complete":
                # Extract last message content
                messages = session_data.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    return last_msg.get("content", "")
                return "No response content"

            if session_data.get("status") == "error":
                raise RuntimeError(f"OpenCode error: {session_data.get('error', 'Unknown error')}")

            # Wait before retry
            time.sleep(0.5)
            retries += 1

        raise RuntimeError(f"OpenCode request timed out after {max_retries} retries (30s)")

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot connect to OpenCode. Start with: opencode serve --port 4096"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenCode request timed out")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"OpenCode API error: {e.response.status_code} {e.response.text}")
    except Exception as e:
        raise RuntimeError(f"OpenCode error: {str(e)}")


def get_llm_with_rate_limit_fallback(model="gemini/gemini-2.0-flash", temperature=0.7, max_tokens=4096):
    """
    Create an LLM instance with intelligent fallback strategy:
    1. Try primary model (e.g., gemini-2.0-flash)
    2. If 429, try gemini-1.5-flash instead
    3. If still limited, check Ollama availability
    4. If all limited, wait and notify user of retry time
    Never fails silently.
    """
    from crewai import LLM
    import time

    gemini_limited_key = "gemini_limited"

    # Check if we've already detected Gemini is limited
    if _rate_limit_fallback.get(gemini_limited_key) and "gemini" in model.lower():
        logger.info("Gemini previously rate limited, trying fallback models...")

        # Try gemini-1.5-flash as first fallback
        try:
            logger.info("Attempting gemini-1.5-flash as fallback...")
            return LLM(
                model="gemini/gemini-1.5-flash",
                api_key=GEMINI_API_KEY,
                temperature=temperature
            )
        except Exception as e:
            logger.warning(f"gemini-1.5-flash failed: {e}")

        # Try Ollama if available
        if is_ollama_available():
            logger.info("Using Ollama as fallback (Gemini limited)")
            return LLM(
                model="ollama/qwen2.5-coder:7b",
                base_url=OLLAMA_BASE_URL,
                temperature=temperature
            )
        else:
            logger.error("All LLM providers exhausted. Gemini limited, Ollama unavailable.")
            raise RuntimeError(
                "Rate limit hit on Gemini and no fallback available. "
                "Ollama server not responding. Please try again in 1 minute or check Ollama status."
            )

    # Try to create Gemini LLM with intelligent error handling
    if "gemini" in model.lower():
        class IntelligentFallbackLLM(LLM):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fallback_tried = False

            def call(self, *args, **kwargs):
                try:
                    return super().call(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()

                    # Check for rate limit / quota errors
                    if any(x in error_str for x in ["429", "rate limit", "quota", "too many requests"]):
                        logger.warning(f"Gemini rate limit detected: {error_str}")
                        _rate_limit_fallback[gemini_limited_key] = True

                        if not self.fallback_tried:
                            self.fallback_tried = True
                            # Try gemini-1.5-flash first
                            try:
                                logger.info("Switching to gemini-1.5-flash...")
                                fallback_llm = LLM(
                                    model="gemini/gemini-1.5-flash",
                                    api_key=GEMINI_API_KEY,
                                    temperature=self.temperature
                                )
                                return fallback_llm.call(*args, **kwargs)
                            except Exception as e2:
                                logger.warning(f"gemini-1.5-flash also failed: {e2}")

                        # Try Ollama
                        if is_ollama_available():
                            logger.info("Switching to Ollama (gemini rate limited)...")
                            fallback_llm = LLM(
                                model="ollama/qwen2.5-coder:7b",
                                base_url=OLLAMA_BASE_URL,
                                temperature=self.temperature
                            )
                            return fallback_llm.call(*args, **kwargs)
                        else:
                            logger.error("Rate limited on Gemini, Ollama unavailable. Waiting before retry...")
                            time.sleep(2)
                            raise RuntimeError(
                                "Rate limited on all providers. "
                                "Gemini quota exhausted, Ollama not responding. "
                                "Please wait 1-2 minutes and retry."
                            )

                    # Not a rate limit error - propagate
                    raise

        try:
            return IntelligentFallbackLLM(
                model=model,
                api_key=GEMINI_API_KEY,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Failed to create Gemini LLM: {e}")

            # Try fallback models on initialization failure
            try:
                logger.info("Attempting gemini-1.5-flash on init failure...")
                return LLM(
                    model="gemini/gemini-1.5-flash",
                    api_key=GEMINI_API_KEY,
                    temperature=temperature
                )
            except Exception:
                if is_ollama_available():
                    logger.info("Using Ollama on Gemini init failure")
                    return LLM(
                        model="ollama/qwen2.5-coder:7b",
                        base_url=OLLAMA_BASE_URL,
                        temperature=temperature
                    )
                raise RuntimeError(
                    "Cannot initialize Gemini, gemini-1.5-flash failed, and Ollama not available."
                )

    return LLM(model=model, temperature=temperature)


def completion_with_fallback(messages, model="gemini", temperature=0.7, max_tokens=4096):
    """Execute completion with automatic fallback routing (Gemini → Ollama on 429)."""
    fallback_models = [
        "gemini/gemini-2.0-flash",
        "ollama/qwen2.5-coder",
    ]

    litellm.api_base_for_ollama = OLLAMA_BASE_URL

    last_error = None
    for model_name in fallback_models:
        try:
            if "ollama" in model_name:
                response = litellm.completion(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_base=OLLAMA_BASE_URL,
                    timeout=30,
                )
            else:
                response = litellm.completion(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30,
                )
            return response
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                logger.info("Gemini rate limit (429) detected, switching to Ollama")
                _rate_limit_fallback["gemini_limited"] = True
            last_error = e
            continue

    if last_error:
        raise RuntimeError(f"LLM providers failed. Last error: {last_error}")

