import os
import time
import requests
import litellm
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MCP_SECRET = os.getenv("MCP_SECRET", "")

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

def completion_with_fallback(messages, model="gemini", temperature=0.7, max_tokens=4096):
    """Execute completion with automatic fallback routing (Gemini → Ollama)."""
    fallback_models = [
        "gemini/gemini-2.0-flash",
        "ollama/qwen2.5-coder",
    ]

    if OLLAMA_BASE_URL not in "http://localhost":
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
            last_error = e
            continue

    if last_error:
        raise RuntimeError(f"LLM providers failed. Last error: {last_error}")

def validate_mcp_secret(token: str) -> bool:
    """Validate MCP bearer token."""
    if not MCP_SECRET:
        return False
    expected = f"Bearer {MCP_SECRET}"
    return token == expected
