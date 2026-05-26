import { X, Check } from 'lucide-react'
import { useState } from 'react'

interface SettingsModalProps {
  onClose: () => void
}

export function SettingsModal({ onClose }: SettingsModalProps) {
  const [claudeKey, setClaudeKey] = useState('')
  const [geminiKey, setGeminiKey] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [tested, setTested] = useState<Record<string, boolean>>({})

  const handleTest = async (provider: string) => {
    // Simulate test
    setTested((prev) => ({ ...prev, [provider]: true }))
    setTimeout(
      () => setTested((prev) => ({ ...prev, [provider]: false })),
      2000,
    )
  }

  const handleSave = () => {
    const settings = {
      claudeKey,
      geminiKey,
      ollamaUrl,
    }
    localStorage.setItem('secureflow-settings', JSON.stringify(settings))
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-card border border-border rounded-lg shadow-lg max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <h2 className="text-lg font-bold text-foreground">⚙️ Provider Settings</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-card transition-colors"
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
            <label className="text-sm font-semibold text-foreground block mb-2">
              🤖 Claude (Anthropic)
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={claudeKey}
                onChange={(e) => setClaudeKey(e.target.value)}
                placeholder="ANTHROPIC_API_KEY"
                className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                onClick={() => handleTest('claude')}
                className="px-3 py-2 bg-accent hover:bg-accent/90 text-accent-foreground rounded-md text-sm font-semibold transition-colors"
              >
                {tested.claude ? <Check className="h-4 w-4" /> : 'Test'}
              </button>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Status: {claudeKey ? '✅ Configured' : '❌ Not configured'}
            </p>
          </div>

          {/* Gemini */}
          <div>
            <label className="text-sm font-semibold text-foreground block mb-2">
              ✨ Gemini (Google)
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="GEMINI_API_KEY"
                className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                onClick={() => handleTest('gemini')}
                className="px-3 py-2 bg-accent hover:bg-accent/90 text-accent-foreground rounded-md text-sm font-semibold transition-colors"
              >
                {tested.gemini ? <Check className="h-4 w-4" /> : 'Test'}
              </button>
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
                className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <button
                onClick={() => handleTest('ollama')}
                className="px-3 py-2 bg-accent hover:bg-accent/90 text-accent-foreground rounded-md text-sm font-semibold transition-colors"
              >
                {tested.ollama ? <Check className="h-4 w-4" /> : 'Test'}
              </button>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Status: ✅ Running (simulated)
            </p>
          </div>

          <div className="bg-card/50 rounded border border-border p-3">
            <p className="text-xs text-muted-foreground">
              <strong>Note:</strong> Settings are stored in browser storage only.
              These API keys are not transmitted to the server.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 p-6 border-t border-border">
          <button
            onClick={handleSave}
            className="flex-1 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md font-semibold transition-colors"
          >
            💾 Save Settings
          </button>
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-card border border-border hover:bg-card/80 rounded-md font-semibold transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
