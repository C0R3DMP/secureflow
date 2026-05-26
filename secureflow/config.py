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
    """Track status and quota of LLM providers."""

    PROVIDERS = {
        "claude-cli": {
            "type": "cli",
            "priority": 1,
            "available": is_claude_cli_available(),
        },
        "gemini-cli": {
            "type": "cli",
            "priority": 2,
            "available": is_gemini_cli_available(),
        },
        "claude": {
            "api_key_var": ANTHROPIC_API_KEY,
            "type": "api",
            "priority": 3,
            "available": bool(ANTHROPIC_API_KEY),
        },
        "gemini": {
            "api_key_var": GEMINI_API_KEY,
            "type": "api",
            "priority": 4,
            "available": bool(GEMINI_API_KEY),
        },
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "type": "local",
            "priority": 5,
            "available": is_ollama_available(),
        },
        "opencode": {
            "base_url": OPENCODE_URL,
            "type": "local",
            "priority": 6,
            "available": False,  # Check dynamically in check_health
        },
    }

    @staticmethod
    def check_health(provider: str) -> bool:
        """Check if a provider is healthy and available."""
        if provider == "claude-cli":
            return is_claude_cli_available()
        elif provider == "gemini-cli":
            return is_gemini_cli_available()
        elif provider == "claude":
            return bool(ANTHROPIC_API_KEY)
        elif provider == "gemini":
            return bool(GEMINI_API_KEY) and not _rate_limit_fallback.get("gemini_limited", False)
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

class CLILLMWrapper:
    """Wrapper to make CLI tools compatible with CrewAI LLM interface."""

    def __init__(self, cli_type: str = "claude", model: str = "claude-opus-4-6"):
        self.cli_type = cli_type
        self.model = model
        self.temperature = 0.7
        self.max_tokens = 4096

    def call(self, prompt: str, **kwargs) -> str:
        """Execute CLI command and return response."""
        if self.cli_type == "claude":
            return call_claude_cli(prompt, self.model)
        elif self.cli_type == "gemini":
            return call_gemini_cli(prompt)
        else:
            raise ValueError(f"Unknown CLI type: {self.cli_type}")


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
    """Return the LLM fallback order: Claude CLI → Gemini CLI → Gemini API → Ollama."""
    return [
        {"model": "claude-cli", "type": "cli"},
        {"model": "gemini-cli", "type": "cli"},
        {"model": "gemini/gemini-2.5-flash"},
        {"model": "ollama/qwen2.5-coder", "base_url": OLLAMA_BASE_URL},
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
                model="gemini/gemini-2.5-flash-lite",
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
                                    model="gemini/gemini-2.5-flash-lite",
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
                    model="gemini/gemini-2.5-flash-lite",
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


def get_claude_cli_llm(temperature=0.7):
    """Get Claude CLI wrapper as CrewAI-compatible LLM."""
    from crewai import LLM
    # Use litellm with claude model via openai-compatible endpoint if available
    # For now, return a basic LLM that will fall back
    if is_claude_cli_available():
        logger.info("Using Claude CLI as primary provider")
        try:
            # Try using litellm's claude model support
            return LLM(
                model="claude-opus-4-6",
                api_key=ANTHROPIC_API_KEY or "dummy",
                temperature=temperature,
                provider="claude",
            )
        except:
            # Fallback to wrapper
            logger.info("Claude API not available, using CLI wrapper")
            llm = CLILLMWrapper("claude", "claude-opus-4-6")
            llm.temperature = temperature
            return llm
    return None


def get_gemini_cli_llm(temperature=0.7):
    """Get Gemini CLI wrapper as CrewAI-compatible LLM."""
    from crewai import LLM
    if is_gemini_cli_available():
        logger.info("Using Gemini CLI as secondary provider")
        try:
            return LLM(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY or "dummy",
                temperature=temperature,
            )
        except:
            # Fallback to wrapper
            logger.info("Gemini API not available, using CLI wrapper")
            llm = CLILLMWrapper("gemini")
            llm.temperature = temperature
            return llm
    return None


def get_best_available_llm(temperature=0.7):
    """Get the best available LLM based on provider priority."""
    from crewai import LLM

    available = LLMProviderStatus.get_available_providers()
    logger.info(f"Available LLM providers: {[p[0] for p in available]}")

    for provider, priority in available:
        logger.info(f"Trying provider: {provider} (priority: {priority})")

        if provider == "claude-cli":
            llm = get_claude_cli_llm(temperature)
            if llm:
                logger.info(f"Using {provider}")
                return llm
        elif provider == "gemini-cli":
            llm = get_gemini_cli_llm(temperature)
            if llm:
                logger.info(f"Using {provider}")
                return llm
        elif provider == "claude":
            if ANTHROPIC_API_KEY:
                logger.info(f"Using {provider}")
                return LLM(
                    model="claude-opus-4-6",
                    api_key=ANTHROPIC_API_KEY,
                    temperature=temperature,
                )
        elif provider == "gemini":
            if GEMINI_API_KEY:
                logger.info(f"Using {provider}")
                return get_llm_with_rate_limit_fallback(
                    model="gemini/gemini-2.5-flash",
                    temperature=temperature
                )
        elif provider == "ollama":
            logger.info(f"Using {provider}")
            return LLM(
                model="ollama/qwen2.5-coder:7b",
                base_url=OLLAMA_BASE_URL,
                temperature=temperature,
            )

    raise RuntimeError("No LLM providers available! Check config and CLI tools.")


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

