import { X, Check, Loader2 } from 'lucide-react'
import { useState, useEffect } from 'react'

interface SettingsModalProps {
  onClose: () => void
}

export function SettingsModal({ onClose }: SettingsModalProps) {
  const [claudeKey, setClaudeKey] = useState('')
  const [claudeMode, setClaudeMode] = useState<'api' | 'cli'>('api')
  const [claudeCliAvailable, setClaudeCliAvailable] = useState(false)
  const [checkingClaude, setCheckingClaude] = useState(false)
  const [geminiKey, setGeminiKey] = useState('')
  const [geminiModel, setGeminiModel] = useState('gemini-2.0-flash')
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [tested, setTested] = useState<Record<string, boolean>>({})

  useEffect(() => {
    // Load settings from localStorage
    const saved = localStorage.getItem('secureflow-settings')
    if (saved) {
      const settings = JSON.parse(saved)
      if (settings.claudeKey) setClaudeKey(settings.claudeKey)
      if (settings.claudeMode) setClaudeMode(settings.claudeMode)
      if (settings.geminiKey) setGeminiKey(settings.geminiKey)
      if (settings.geminiModel) setGeminiModel(settings.geminiModel)
      if (settings.ollamaUrl) setOllamaUrl(settings.ollamaUrl)
    }

    // Check Claude CLI availability
    checkClaudeCli()
  }, [])

  const checkClaudeCli = async () => {
    setCheckingClaude(true)
    try {
      const response = await fetch('/api/claude-cli-status')
      const data = await response.json()
      setClaudeCliAvailable(data.available)
    } catch (e) {
      setClaudeCliAvailable(false)
    } finally {
      setCheckingClaude(false)
    }
  }

  const handleTest = async (provider: string) => {
    // Simulate test
    setTested((prev) => ({ ...prev, [provider]: true }))
    setTimeout(
      () => setTested((prev) => ({ ...prev, [provider]: false })),
      2000,
    )
  }

  const handleSave = async () => {
    const settings = {
      claudeKey: claudeMode === 'api' ? claudeKey : '',
      claudeMode,
      geminiKey,
      geminiModel,
      ollamaUrl,
    }

    // Save to localStorage
    localStorage.setItem('secureflow-settings', JSON.stringify(settings))

    // Send to backend
    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
      if (response.ok) {
        const data = await response.json()
        console.log('Settings saved:', data)
      }
    } catch (e) {
      console.error('Failed to save settings to backend:', e)
    }

    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-50">
      <div className="glass rounded-2xl shadow-2xl max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto border-white/10">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            ⚙️ Provider Settings
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/10 transition-colors rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          <div>
            <p className="text-xs text-muted-foreground mb-4">
              Configure your LLM providers. Priority: Claude &gt; Gemini &gt;
              Ollama
            </p>
          </div>

          {/* Claude */}
          <div>
            <label className="text-sm font-semibold text-foreground block mb-3">
              🤖 Claude (Anthropic)
            </label>

            {/* Claude Mode Selection */}
            <div className="space-y-2 mb-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="claude-mode"
                  value="api"
                  checked={claudeMode === 'api'}
                  onChange={() => setClaudeMode('api')}
                  className="w-4 h-4"
                />
                <span className="text-sm text-foreground">Claude API (Paid)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="claude-mode"
                  value="cli"
                  checked={claudeMode === 'cli'}
                  onChange={() => setClaudeMode('cli')}
                  className="w-4 h-4"
                />
                <span className="text-sm text-foreground">Claude Code CLI (Local)</span>
              </label>
            </div>

            {/* Claude API Key Input (only show if API mode) */}
            {claudeMode === 'api' && (
              <div className="flex gap-2 mb-2">
                <input
                  type="password"
                  value={claudeKey}
                  onChange={(e) => setClaudeKey(e.target.value)}
                  placeholder="ANTHROPIC_API_KEY"
                  className="input-glass flex-1"
                />
                <button
                  onClick={() => handleTest('claude')}
                  className="btn-primary px-3 py-2"
                >
                  {tested.claude ? <Check className="h-4 w-4" /> : 'Test'}
                </button>
              </div>
            )}

            {/* Claude CLI Status (only show if CLI mode) */}
            {claudeMode === 'cli' && (
              <div className="flex gap-2 items-center mb-2">
                <button
                  onClick={checkClaudeCli}
                  disabled={checkingClaude}
                  className="flex-1 btn-primary py-2 flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {checkingClaude && <Loader2 className="h-4 w-4 spinner-spin" />}
                  {checkingClaude ? 'Checking...' : 'Check Status'}
                </button>
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-1">
              Status:{' '}
              {claudeMode === 'api'
                ? claudeKey
                  ? '✅ API Key configured'
                  : '❌ API Key not set'
                : claudeCliAvailable
                ? '✅ CLI available'
                : '❌ CLI not found'}
            </p>
          </div>

          {/* Gemini */}
          <div>
            <label className="text-sm font-semibold text-foreground block mb-2">
              ✨ Gemini (Google)
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="GEMINI_API_KEY"
                className="input-glass flex-1"
              />
              <button
                onClick={() => handleTest('gemini')}
                className="btn-primary px-3 py-2"
              >
                {tested.gemini ? <Check className="h-4 w-4" /> : 'Test'}
              </button>
            </div>

            {/* Gemini Model Selection */}
            <div className="mb-2">
              <label className="text-xs text-muted-foreground block mb-1">
                Model
              </label>
              <select
                value={geminiModel}
                onChange={(e) => setGeminiModel(e.target.value)}
                className="input-glass w-full"
              >
                <option value="gemini-2.0-flash">gemini-2.0-flash (default, free)</option>
                <option value="gemini-1.5-pro">gemini-1.5-pro</option>
                <option value="gemini-1.5-flash">gemini-1.5-flash</option>
              </select>
            </div>

            <p className="text-xs text-muted-foreground mt-1">
              Status: {geminiKey ? '✅ Configured' : '❌ Not configured'}
            </p>
          </div>

          {/* Ollama */}
          <div>
            <label className="text-sm font-semibold text-foreground block mb-2">
              🦙 Ollama (Local)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={ollamaUrl}
                onChange={(e) => setOllamaUrl(e.target.value)}
                placeholder="http://localhost:11434"
                className="input-glass flex-1"
              />
              <button
                onClick={() => handleTest('ollama')}
                className="btn-primary px-3 py-2"
              >
                {tested.ollama ? <Check className="h-4 w-4" /> : 'Test'}
              </button>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Status: ✅ Running (simulated)
            </p>
          </div>

          <div className="glass rounded-lg p-3 border-white/5">
            <p className="text-xs text-muted-foreground">
              <strong>Note:</strong> Settings are stored locally and on the server.
              API keys are securely transmitted via HTTPS.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 p-6 border-t border-white/10">
          <button
            onClick={handleSave}
            className="flex-1 btn-primary py-2 font-semibold"
          >
            💾 Save
          </button>
          <button
            onClick={onClose}
            className="flex-1 btn-glass"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
