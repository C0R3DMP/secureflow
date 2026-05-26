import os
import time
import subprocess
import requests
import litellm
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENCODE_URL = os.getenv("OPENCODE_URL", "http://localhost:4096")
OPENCODE_SERVER_PASSWORD = os.getenv("OPENCODE_SERVER_PASSWORD", "secureflow")
MCP_SECRET = os.getenv("MCP_SECRET", "")

# Rate limit tracking
_rate_limit_fallback = {"gemini_limited": False, "last_rate_limit_time": 0}


def is_claude_cli_available(timeout: int = 2) -> bool:
    """Check if Claude CLI is available."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Claude CLI check failed: {e}")
        return False


def is_ollama_available(base_url: str = OLLAMA_BASE_URL, timeout: int = 2) -> bool:
    """Check if Ollama server is available and healthy."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Ollama health check failed: {e}")
        return False

def is_gemini_cli_available(timeout: int = 2) -> bool:
    """Check if Gemini CLI is available."""
    try:
        result = subprocess.run(
            ["gemini", "--version"],
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Gemini CLI check failed: {e}")
        return False


class LLMProviderStatus:
    """Track status and quota of LLM providers.

    Provider priority (all CrewAI/litellm compatible):
    1. Gemini API (free tier: 5 req/min)
    2. OpenRouter (free models available)
    3. Ollama (free, local)
    4. Claude API (optional)
    """

    PROVIDERS = {
        "gemini": {
            "api_key_var": GEMINI_API_KEY,
            "type": "api",
            "priority": 1,
            "available": bool(GEMINI_API_KEY),
            "model": "gemini/gemini-2.5-flash",
        },
        "openrouter": {
            "api_key_var": OPENROUTER_API_KEY,
            "type": "api",
            "priority": 2,
            "available": bool(OPENROUTER_API_KEY),
            "model": "openrouter/google/gemini-2.0-flash-exp:free",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "type": "local",
            "priority": 3,
            "available": is_ollama_available(),
            "model": "ollama/qwen2.5-coder:7b",
        },
        "claude": {
            "api_key_var": ANTHROPIC_API_KEY,
            "type": "api",
            "priority": 4,
            "available": bool(ANTHROPIC_API_KEY),
            "model": "claude-opus-4-6",
        },
        "opencode": {
            "base_url": OPENCODE_URL,
            "type": "local",
            "priority": 5,
            "available": False,  # Check dynamically in check_health
        },
    }

    @staticmethod
    def check_health(provider: str) -> bool:
        """Check if a provider is healthy and available."""
        if provider == "gemini":
            return bool(GEMINI_API_KEY) and not _rate_limit_fallback.get("gemini_limited", False)
        elif provider == "openrouter":
            return bool(OPENROUTER_API_KEY)
        elif provider == "claude":
            return bool(ANTHROPIC_API_KEY)
        elif provider == "ollama":
            return is_ollama_available()
        elif provider == "opencode":
            try:
                headers = {"Authorization": f"Bearer {OPENCODE_SERVER_PASSWORD}"}
                response = requests.get(f"{OPENCODE_URL}/", headers=headers, timeout=2)
                return 200 <= response.status_code < 400
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

# Note: CLI tools (Claude Code CLI, Gemini CLI) cannot be used directly with CrewAI's LLM class
# They require subprocess execution outside of the CrewAI framework
# See call_claude_cli() and call_gemini_cli() below for direct CLI usage if needed


def init_llms():
    """Initialize litellm with fallback chain: Claude CLI → Gemini CLI → Gemini API → Ollama."""
    config = {
        "claude-cli": {
            "type": "cli",
            "model": "claude-opus-4-6",
        },
        "gemini-cli": {
            "type": "cli",
            "model": "gemini",
        },
        "gemini": {
            "api_key": GEMINI_API_KEY,
            "model": "gemini/gemini-2.5-flash",
        },
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "model": "ollama/qwen2.5-coder",
        },
    }
    return config

def get_fallback_chain():
    """Return the LLM fallback order: Gemini API → Ollama → Claude API."""
    return [
        {"model": "gemini/gemini-2.5-flash"},
        {"model": "ollama/qwen2.5-coder", "base_url": OLLAMA_BASE_URL},
        {"model": "claude/claude-opus-4-6"},
    ]

def call_claude_cli(prompt: str, model: str = "claude-opus-4-6") -> str:
    """Call Claude via subprocess CLI directly."""
    try:
        result = subprocess.run(
            ["claude", "-m", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Claude CLI error: {result.stderr}")
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI request timed out")
    except FileNotFoundError:
        raise RuntimeError("Claude CLI not found")
    except Exception as e:
        raise RuntimeError(f"Claude CLI error: {str(e)}")


def call_gemini_cli(prompt: str) -> str:
    """Call Gemini via subprocess CLI directly."""
    try:
        result = subprocess.run(
            ["gemini"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Gemini CLI error: {result.stderr}")
            raise RuntimeError(f"Gemini CLI failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Gemini CLI request timed out")
    except FileNotFoundError:
        raise RuntimeError("Gemini CLI not found")
    except Exception as e:
        raise RuntimeError(f"Gemini CLI error: {str(e)}")


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


def get_llm_with_rate_limit_fallback(model="gemini/gemini-2.5-flash", temperature=0.7, max_tokens=4096):
    """
    Create an LLM instance with intelligent rate limit handling:
    1. Try primary model (e.g., gemini-2.5-flash)
    2. If 429: extract retryDelay from error, sleep(retryDelay + 2), retry same model
    3. If still 429: try OpenRouter (alternative free provider)
    4. If still limited: try Ollama (local fallback)
    5. Never fail silently - always return working provider or raise clear error

    Gemini free tier: 5 requests/minute (429 = rate limited)
    """
    from crewai import LLM
    import time
    import json
    import re

    gemini_retry_count = {}  # Track retries per model

    def extract_retry_delay(error_str: str) -> int:
        """Extract retryDelay from Gemini API error response."""
        try:
            # Try to find retryDelay in error message
            if "retryDelay" in error_str:
                match = re.search(r'"retryDelay"\s*:\s*"([^"]+)"', error_str)
                if match:
                    delay_str = match.group(1)
                    # Parse duration format like "1.5s"
                    if delay_str.endswith('s'):
                        return int(float(delay_str[:-1]))
            # Fallback to common values
            if "429" in error_str:
                return 12  # Default 12s for rate limit
        except Exception as e:
            logger.debug(f"Could not extract retry delay: {e}")
        return 12

    class RateLimitAwareGeminiLLM(LLM):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.retry_count = 0
            self.max_retries = 2

        def call(self, *args, **kwargs):
            """Execute with intelligent rate limit handling."""
            attempt = 0
            while attempt <= self.max_retries:
                try:
                    return super().call(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()

                    # Check for rate limit (429)
                    if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
                        attempt += 1
                        if attempt > self.max_retries:
                            logger.warning(f"Gemini rate limited after {self.max_retries} retries, falling back...")
                            break

                        # Extract retry delay from error
                        retry_delay = extract_retry_delay(str(e))
                        wait_time = retry_delay + 2

                        logger.warning(
                            f"🔄 Gemini rate limit (429) - Waiting {wait_time}s before retry "
                            f"({attempt}/{self.max_retries})..."
                        )
                        time.sleep(wait_time)

                        if attempt <= self.max_retries:
                            logger.info(f"↻ Retrying same model (attempt {attempt})")
                            continue

                    # Not a rate limit error
                    raise

            # After max retries, raise error to trigger fallback
            raise RuntimeError(
                f"Gemini rate limited after {self.max_retries} retries. "
                f"Free tier limit: 5 requests/minute. Try OpenRouter or Ollama."
            )

    # Try to create Gemini LLM with rate limit awareness
    if "gemini" in model.lower():
        try:
            logger.info(f"Creating Gemini LLM with rate limit handling: {model}")
            return RateLimitAwareGeminiLLM(
                model=model,
                api_key=GEMINI_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.error(f"Failed to create Gemini LLM: {e}")
            raise RuntimeError(
                f"Cannot initialize Gemini LLM: {str(e)}\n"
                f"Try: export OPENROUTER_API_KEY=... for alternative"
            )

    return LLM(model=model, temperature=temperature, max_tokens=max_tokens)


# Note: To use Claude Code CLI or Gemini CLI directly, call:
#   - call_claude_cli(prompt) for Claude Code CLI
#   - call_gemini_cli(prompt) for Gemini CLI
# These functions execute CLI tools via subprocess and are not CrewAI-compatible


def get_best_available_llm(temperature=0.7):
    """Get the best available LLM based on provider priority.

    Provider order (all CrewAI compatible):
    1. Gemini API (5 req/min free, requires GEMINI_API_KEY)
    2. OpenRouter (free models, requires OPENROUTER_API_KEY)
    3. Ollama (free, local, no API key)
    4. Claude API (requires ANTHROPIC_API_KEY)
    """
    from crewai import LLM

    available = LLMProviderStatus.get_available_providers()
    logger.info(f"Available LLM providers: {[p[0] for p in available]}")

    for provider, priority in available:
        logger.info(f"Trying provider: {provider} (priority: {priority})")

        if provider == "gemini":
            if GEMINI_API_KEY:
                logger.info(f"✅ Using Gemini API (primary, 5 req/min)")
                return get_llm_with_rate_limit_fallback(
                    model="gemini/gemini-2.5-flash",
                    temperature=temperature
                )
        elif provider == "openrouter":
            if OPENROUTER_API_KEY:
                logger.info(f"✅ Using OpenRouter (free models)")
                return LLM(
                    model="openrouter/google/gemini-2.0-flash-exp:free",
                    api_key=OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=temperature,
                )
        elif provider == "ollama":
            logger.info(f"✅ Using Ollama (local, free)")
            return LLM(
                model="ollama/qwen2.5-coder:7b",
                base_url=OLLAMA_BASE_URL,
                temperature=temperature,
            )
        elif provider == "claude":
            if ANTHROPIC_API_KEY:
                logger.info(f"✅ Using Claude API")
                return LLM(
                    model="claude-opus-4-6",
                    api_key=ANTHROPIC_API_KEY,
                    temperature=temperature,
                )

    # Fallback: always try Ollama if nothing else works
    try:
        logger.warning("No API keys available, using Ollama as fallback")
        return LLM(
            model="ollama/qwen2.5-coder:7b",
            base_url=OLLAMA_BASE_URL,
            temperature=temperature,
        )
    except Exception as e:
        raise RuntimeError(
            f"No LLM providers available!\n"
            f"  Option 1: export GEMINI_API_KEY=... (primary)\n"
            f"  Option 2: export OPENROUTER_API_KEY=... (free models)\n"
            f"  Option 3: ollama run qwen2.5-coder (local, free)\n"
            f"  Option 4: export ANTHROPIC_API_KEY=... (alternative)\n"
            f"  Error: {str(e)}"
        )


def completion_with_fallback(messages, model="gemini", temperature=0.7, max_tokens=4096):
    """Execute completion with automatic fallback routing (Gemini → Ollama on 429)."""
    fallback_models = [
        "gemini/gemini-2.5-flash",
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

