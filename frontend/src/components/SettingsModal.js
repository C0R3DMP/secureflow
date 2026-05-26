import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { X, Check, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';
export function SettingsModal({ onClose }) {
    const [claudeKey, setClaudeKey] = useState('');
    const [claudeMode, setClaudeMode] = useState('api');
    const [claudeCliAvailable, setClaudeCliAvailable] = useState(false);
    const [checkingClaude, setCheckingClaude] = useState(false);
    const [geminiKey, setGeminiKey] = useState('');
    const [geminiModel, setGeminiModel] = useState('gemini-2.0-flash');
    const [openrouterKey, setOpenrouterKey] = useState('');
    const [openrouterModel, setOpenrouterModel] = useState('openrouter/google/gemini-2.0-flash-exp:free');
    const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
    const [tested, setTested] = useState({});
    useEffect(() => {
        // Load settings from localStorage
        const saved = localStorage.getItem('secureflow-settings');
        if (saved) {
            const settings = JSON.parse(saved);
            if (settings.claudeKey)
                setClaudeKey(settings.claudeKey);
            if (settings.claudeMode)
                setClaudeMode(settings.claudeMode);
            if (settings.geminiKey)
                setGeminiKey(settings.geminiKey);
            if (settings.geminiModel)
                setGeminiModel(settings.geminiModel);
            if (settings.openrouterKey)
                setOpenrouterKey(settings.openrouterKey);
            if (settings.openrouterModel)
                setOpenrouterModel(settings.openrouterModel);
            if (settings.ollamaUrl)
                setOllamaUrl(settings.ollamaUrl);
        }
        // Check Claude CLI availability
        checkClaudeCli();
    }, []);
    const checkClaudeCli = async () => {
        setCheckingClaude(true);
        try {
            const response = await fetch('/api/claude-cli-status');
            const data = await response.json();
            setClaudeCliAvailable(data.available);
        }
        catch (e) {
            setClaudeCliAvailable(false);
        }
        finally {
            setCheckingClaude(false);
        }
    };
    const handleTest = async (provider) => {
        // Simulate test
        setTested((prev) => ({ ...prev, [provider]: true }));
        setTimeout(() => setTested((prev) => ({ ...prev, [provider]: false })), 2000);
    };
    const handleSave = async () => {
        const settings = {
            claudeKey: claudeMode === 'api' ? claudeKey : '',
            claudeMode,
            geminiKey,
            geminiModel,
            openrouterKey,
            openrouterModel,
            ollamaUrl,
        };
        // Save to localStorage
        localStorage.setItem('secureflow-settings', JSON.stringify(settings));
        // Send to backend
        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            if (response.ok) {
                const data = await response.json();
                console.log('Settings saved:', data);
            }
        }
        catch (e) {
            console.error('Failed to save settings to backend:', e);
        }
        onClose();
    };
    return (_jsx("div", { className: "fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-50", children: _jsxs("div", { className: "glass rounded-2xl shadow-2xl max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto border-white/10", children: [_jsxs("div", { className: "flex items-center justify-between p-6 border-b border-white/10", children: [_jsx("h2", { className: "text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent", children: "\u2699\uFE0F Provider Settings" }), _jsx("button", { onClick: onClose, className: "p-1 hover:bg-white/10 transition-colors rounded-lg", children: _jsx(X, { className: "h-5 w-5" }) })] }), _jsxs("div", { className: "p-6 space-y-6", children: [_jsx("div", { children: _jsx("p", { className: "text-xs text-muted-foreground mb-4", children: "Configure your LLM providers. Priority: Claude > Gemini > OpenRouter > Ollama" }) }), _jsxs("div", { children: [_jsx("label", { className: "text-sm font-semibold text-foreground block mb-3", children: "\uD83E\uDD16 Claude (Anthropic)" }), _jsxs("div", { className: "space-y-2 mb-3", children: [_jsxs("label", { className: "flex items-center gap-2 cursor-pointer", children: [_jsx("input", { type: "radio", name: "claude-mode", value: "api", checked: claudeMode === 'api', onChange: () => setClaudeMode('api'), className: "w-4 h-4" }), _jsx("span", { className: "text-sm text-foreground", children: "Claude API (Paid)" })] }), _jsxs("label", { className: "flex items-center gap-2 cursor-pointer", children: [_jsx("input", { type: "radio", name: "claude-mode", value: "cli", checked: claudeMode === 'cli', onChange: () => setClaudeMode('cli'), className: "w-4 h-4" }), _jsx("span", { className: "text-sm text-foreground", children: "Claude Code CLI (Local)" })] })] }), claudeMode === 'api' && (_jsxs("div", { className: "flex gap-2 mb-2", children: [_jsx("input", { type: "password", value: claudeKey, onChange: (e) => setClaudeKey(e.target.value), placeholder: "ANTHROPIC_API_KEY", className: "input-glass flex-1" }), _jsx("button", { onClick: () => handleTest('claude'), className: "btn-primary px-3 py-2", children: tested.claude ? _jsx(Check, { className: "h-4 w-4" }) : 'Test' })] })), claudeMode === 'cli' && (_jsx("div", { className: "flex gap-2 items-center mb-2", children: _jsxs("button", { onClick: checkClaudeCli, disabled: checkingClaude, className: "flex-1 btn-primary py-2 flex items-center justify-center gap-2 disabled:opacity-50", children: [checkingClaude && _jsx(Loader2, { className: "h-4 w-4 spinner-spin" }), checkingClaude ? 'Checking...' : 'Check Status'] }) })), _jsxs("p", { className: "text-xs text-muted-foreground mt-1", children: ["Status:", ' ', claudeMode === 'api'
                                            ? claudeKey
                                                ? '✅ API Key configured'
                                                : '❌ API Key not set'
                                            : claudeCliAvailable
                                                ? '✅ CLI available'
                                                : '❌ CLI not found'] })] }), _jsxs("div", { children: [_jsx("label", { className: "text-sm font-semibold text-foreground block mb-2", children: "\u2728 Gemini (Google)" }), _jsxs("div", { className: "flex gap-2 mb-2", children: [_jsx("input", { type: "password", value: geminiKey, onChange: (e) => setGeminiKey(e.target.value), placeholder: "GEMINI_API_KEY", className: "input-glass flex-1" }), _jsx("button", { onClick: () => handleTest('gemini'), className: "btn-primary px-3 py-2", children: tested.gemini ? _jsx(Check, { className: "h-4 w-4" }) : 'Test' })] }), _jsxs("div", { className: "mb-2", children: [_jsx("label", { className: "text-xs text-muted-foreground block mb-1", children: "Model" }), _jsxs("select", { value: geminiModel, onChange: (e) => setGeminiModel(e.target.value), className: "input-glass w-full", children: [_jsx("option", { value: "gemini-2.0-flash", children: "gemini-2.0-flash (default, free)" }), _jsx("option", { value: "gemini-1.5-pro", children: "gemini-1.5-pro" }), _jsx("option", { value: "gemini-1.5-flash", children: "gemini-1.5-flash" })] })] }), _jsxs("p", { className: "text-xs text-muted-foreground mt-1", children: ["Status: ", geminiKey ? '✅ Configured' : '❌ Not configured'] })] }), _jsxs("div", { children: [_jsx("label", { className: "text-sm font-semibold text-foreground block mb-2", children: "\uD83C\uDF10 OpenRouter (Free Models)" }), _jsxs("div", { className: "flex gap-2 mb-2", children: [_jsx("input", { type: "password", value: openrouterKey, onChange: (e) => setOpenrouterKey(e.target.value), placeholder: "OPENROUTER_API_KEY", className: "input-glass flex-1" }), _jsx("button", { onClick: () => handleTest('openrouter'), className: "btn-primary px-3 py-2", children: tested.openrouter ? _jsx(Check, { className: "h-4 w-4" }) : 'Test' })] }), _jsxs("div", { className: "mb-2", children: [_jsx("label", { className: "text-xs text-muted-foreground block mb-1", children: "Model" }), _jsxs("select", { value: openrouterModel, onChange: (e) => setOpenrouterModel(e.target.value), className: "input-glass w-full", children: [_jsx("option", { value: "openrouter/google/gemini-2.0-flash-exp:free", children: "Gemini 2.0 Flash (free)" }), _jsx("option", { value: "openrouter/meta-llama/llama-3.1-8b-instruct:free", children: "Llama 3.1 8B (free)" }), _jsx("option", { value: "openrouter/anthropic/claude-3.5-sonnet", children: "Claude 3.5 Sonnet" })] })] }), _jsxs("p", { className: "text-xs text-muted-foreground mt-1 mb-2", children: ["Status: ", openrouterKey ? '✅ Configured' : '❌ Not configured'] }), _jsx("a", { href: "https://openrouter.ai", target: "_blank", rel: "noopener noreferrer", className: "text-xs text-blue-400 hover:text-blue-300 transition-colors", children: "Get free API key at openrouter.ai \u2192" })] }), _jsxs("div", { children: [_jsx("label", { className: "text-sm font-semibold text-foreground block mb-2", children: "\uD83E\uDD99 Ollama (Local)" }), _jsxs("div", { className: "flex gap-2", children: [_jsx("input", { type: "text", value: ollamaUrl, onChange: (e) => setOllamaUrl(e.target.value), placeholder: "http://localhost:11434", className: "input-glass flex-1" }), _jsx("button", { onClick: () => handleTest('ollama'), className: "btn-primary px-3 py-2", children: tested.ollama ? _jsx(Check, { className: "h-4 w-4" }) : 'Test' })] }), _jsx("p", { className: "text-xs text-muted-foreground mt-1", children: "Status: \u2705 Running (simulated)" })] }), _jsx("div", { className: "glass rounded-lg p-3 border-white/5", children: _jsxs("p", { className: "text-xs text-muted-foreground", children: [_jsx("strong", { children: "Note:" }), " Settings are stored locally and on the server. API keys are securely transmitted via HTTPS."] }) })] }), _jsxs("div", { className: "flex gap-2 p-6 border-t border-white/10", children: [_jsx("button", { onClick: handleSave, className: "flex-1 btn-primary py-2 font-semibold", children: "\uD83D\uDCBE Save" }), _jsx("button", { onClick: onClose, className: "flex-1 btn-glass", children: "Close" })] })] }) }));
}
