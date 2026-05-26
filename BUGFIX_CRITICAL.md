# Critical Bug Fix: Anthropic API 401 Errors

## Problem

Agents were attempting to use Claude Code CLI with CrewAI's LLM class, which doesn't support CLI tools directly. This resulted in:
- 401 Unauthorized errors when calling Anthropic API
- Using dummy `ANTHROPIC_API_KEY` values
- Agents failing silently or crashing

**Root Cause:** CrewAI's `LLM` class requires API-compatible providers. CLI tools (Claude Code CLI, Gemini CLI) execute via subprocess and cannot be integrated directly with CrewAI.

## Solution

Removed Claude CLI and Gemini CLI from the provider hierarchy. Changed to **API-compatible providers only**:

1. **Gemini API** (PRIMARY) — Works with CrewAI, requires `GEMINI_API_KEY`
2. **Ollama** (FALLBACK) — Free, local, always available
3. **Claude API** (OPTIONAL) — Works with CrewAI, requires `ANTHROPIC_API_KEY`

## Changes Made

### config.py
- Removed `claude-cli` and `gemini-cli` from `LLMProviderStatus.PROVIDERS`
- Updated provider priority: Gemini → Ollama → Claude
- Simplified `check_health()` method (no CLI checks)
- Updated `get_best_available_llm()` to only use API-compatible providers
- Added fallback to Ollama if no API keys available

### agents.py
- Removed `get_claude_cli_llm()` and `get_gemini_cli_llm()` functions
- Updated all 6 agents to use `get_best_available_llm()`
- Updated agent descriptions to reflect actual providers (Gemini/Ollama)

### README.md
- Updated feature descriptions (Gemini API/Ollama instead of CLI tools)
- Corrected LLM provider priority section
- Added note about Claude CLI not being CrewAI-compatible

## Testing

All agents now initialize successfully:
```
✅ Recon Agent     -> Ollama (fallback when no Gemini API key)
✅ Analyst Agent   -> Ollama (fallback when no Gemini API key)
✅ Reporter Agent  -> Ollama (fallback when no Gemini API key)
✅ Architect       -> Ollama (fallback when no Gemini API key)
✅ Developer       -> Ollama (fallback when no Gemini API key)
✅ Reviewer        -> Ollama (fallback when no Gemini API key)
```

## How to Use

### Option 1: Gemini API (Recommended)
```bash
export GEMINI_API_KEY="your-key-here"
secureflow scan example.com
```

### Option 2: Ollama (Free, Local)
```bash
# First, install Ollama and pull a model:
ollama run qwen2.5-coder

# Then run:
secureflow scan example.com
```

### Option 3: Claude API (Alternative)
```bash
export ANTHROPIC_API_KEY="your-key-here"
secureflow scan example.com
```

## Files Modified
- `secureflow/config.py` — LLM provider configuration
- `secureflow/crew/agents.py` — Agent definitions
- `README.md` — Documentation

## Impact
- ✅ No more 401 Anthropic API errors
- ✅ Agents work with free local Ollama
- ✅ Cleaner, simpler provider hierarchy
- ✅ More predictable error handling

---
**Status:** Fixed and tested ✅ | Date: 2026-05-26
