import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Settings as SettingsIcon, X } from 'lucide-react'
import { authFetch } from '../lib/auth'

interface SettingsModalProps {
  onClose: () => void
}

type SaveState = { kind: 'idle' | 'saving' } | { kind: 'ok' | 'error'; message: string }

const GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']

const OPENROUTER_MODELS = [
  'google/gemini-2.0-flash-exp:free',
  'meta-llama/llama-3.1-8b-instruct:free',
  'mistralai/mistral-7b-instruct:free',
]

/**
 * Provider credentials.
 *
 * API keys are POSTed to the server, which merges them into ~/.secureflow/.env
 * with 0600 permissions. They are deliberately NOT mirrored into localStorage —
 * that put long-lived provider secrets somewhere any injected script could read
 * them, for no benefit, since the server is the store of record.
 */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const [claudeKey, setClaudeKey] = useState('')
  const [claudeMode, setClaudeMode] = useState<'api' | 'cli'>('api')
  const [claudeCli, setClaudeCli] = useState<{ available: boolean; version?: string } | null>(null)
  const [geminiKey, setGeminiKey] = useState('')
  const [geminiModel, setGeminiModel] = useState(GEMINI_MODELS[0])
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [openrouterModel, setOpenrouterModel] = useState(OPENROUTER_MODELS[0])
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [save, setSave] = useState<SaveState>({ kind: 'idle' })

  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    // Non-secret preferences only.
    const stored = window.localStorage.getItem('secureflow.preferences')
    if (stored) {
      try {
        const prefs = JSON.parse(stored)
        if (prefs.claudeMode) setClaudeMode(prefs.claudeMode)
        if (prefs.geminiModel) setGeminiModel(prefs.geminiModel)
        if (prefs.openrouterModel) setOpenrouterModel(prefs.openrouterModel)
        if (prefs.ollamaUrl) setOllamaUrl(prefs.ollamaUrl)
      } catch {
        /* ignore malformed preferences */
      }
    }

    authFetch('/api/claude-cli-status')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setClaudeCli(d ? { available: d.available, version: d.version } : null))
      .catch(() => setClaudeCli({ available: false }))
  }, [])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSave({ kind: 'saving' })

    // Send only the fields the operator actually filled in — the server merges
    // rather than overwrites, so blank fields leave existing keys untouched.
    const payload: Record<string, string> = {
      claudeMode,
      geminiModel,
      openrouterModel,
      ollamaUrl,
    }
    if (claudeKey.trim()) payload.claudeKey = claudeKey.trim()
    if (geminiKey.trim()) payload.geminiKey = geminiKey.trim()
    if (openrouterKey.trim()) payload.openrouterKey = openrouterKey.trim()

    window.localStorage.setItem(
      'secureflow.preferences',
      JSON.stringify({ claudeMode, geminiModel, openrouterModel, ollamaUrl }),
    )

    try {
      const response = await authFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        setSave({ kind: 'error', message: data.message ?? `Server returned ${response.status}` })
        return
      }

      // Clear the secret fields once they are stored server-side.
      setClaudeKey('')
      setGeminiKey('')
      setOpenrouterKey('')
      setSave({
        kind: 'ok',
        message: `Saved: ${(data.updated ?? []).join(', ') || 'preferences'}`,
      })
    } catch {
      setSave({ kind: 'error', message: 'Could not reach the server' })
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-overlay/80 p-4 pt-12 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        className="panel w-full max-w-lg shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-header sticky top-0 z-10 rounded-t-[0.625rem] bg-surface-1">
          <h2 id="settings-title" className="panel-title">
            <SettingsIcon className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            Provider settings
          </h2>
          <button ref={closeRef} type="button" onClick={onClose} className="icon-btn" aria-label="Close settings">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-5 p-5">
          <p className="text-xs text-muted">
            Keys are stored on the server in{' '}
            <code className="text-ink-secondary">~/.secureflow/.env</code> (owner-only).
            Leave a field blank to keep the key already configured.
          </p>

          {/* Gemini — highest priority provider */}
          <Section title="Gemini" hint="Priority 1 · free tier is 5 requests/minute">
            <Field
              id="gemini-key"
              label="API key"
              type="password"
              value={geminiKey}
              onChange={setGeminiKey}
              placeholder="GEMINI_API_KEY"
            />
            <Select
              id="gemini-model"
              label="Model"
              value={geminiModel}
              onChange={setGeminiModel}
              options={GEMINI_MODELS}
            />
          </Section>

          {/* OpenRouter */}
          <Section title="OpenRouter" hint="Priority 2 · free models available">
            <Field
              id="openrouter-key"
              label="API key"
              type="password"
              value={openrouterKey}
              onChange={setOpenrouterKey}
              placeholder="OPENROUTER_API_KEY"
            />
            <Select
              id="openrouter-model"
              label="Model"
              value={openrouterModel}
              onChange={setOpenrouterModel}
              options={OPENROUTER_MODELS}
            />
          </Section>

          {/* Ollama */}
          <Section title="Ollama" hint="Priority 3 · local, no key required">
            <Field
              id="ollama-url"
              label="Base URL"
              type="text"
              value={ollamaUrl}
              onChange={setOllamaUrl}
              placeholder="http://localhost:11434"
            />
          </Section>

          {/* Claude */}
          <Section title="Claude" hint="Priority 4">
            <fieldset>
              <legend className="label-caps mb-1.5">Mode</legend>
              <div className="flex gap-4">
                {(['api', 'cli'] as const).map((mode) => (
                  <label key={mode} className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="claude-mode"
                      value={mode}
                      checked={claudeMode === mode}
                      onChange={() => setClaudeMode(mode)}
                      className="accent-[hsl(var(--accent))]"
                    />
                    <span>{mode === 'api' ? 'API key' : 'Local CLI'}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {claudeMode === 'api' ? (
              <Field
                id="claude-key"
                label="API key"
                type="password"
                value={claudeKey}
                onChange={setClaudeKey}
                placeholder="ANTHROPIC_API_KEY"
              />
            ) : (
              <p className="flex items-center gap-1.5 text-xs">
                {claudeCli === null ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-muted" aria-hidden="true" />
                    <span className="text-muted">Checking for the Claude CLI…</span>
                  </>
                ) : claudeCli.available ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-severity-none" aria-hidden="true" />
                    <span className="text-secondary">
                      CLI detected{claudeCli.version ? ` — ${claudeCli.version}` : ''}
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-3.5 w-3.5 text-severity-medium" aria-hidden="true" />
                    <span className="text-secondary">
                      CLI not found on PATH. Note it is not usable as a CrewAI provider.
                    </span>
                  </>
                )}
              </p>
            )}
          </Section>
        </div>

        <div className="flex items-center gap-3 border-t border-line px-5 py-4">
          <div className="min-w-0 flex-1" aria-live="polite">
            {save.kind === 'ok' && (
              <p className="flex items-center gap-1.5 text-xs text-severity-none">
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{save.message}</span>
              </p>
            )}
            {save.kind === 'error' && (
              <p role="alert" className="flex items-center gap-1.5 text-xs text-severity-critical">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{save.message}</span>
              </p>
            )}
          </div>

          <button type="button" onClick={onClose} className="btn btn-secondary">
            Close
          </button>
          <button type="submit" className="btn btn-primary" disabled={save.kind === 'saving'}>
            {save.kind === 'saving' && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            Save
          </button>
        </div>
      </form>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-[0.6875rem] text-muted">{hint}</span>
      </div>
      {children}
    </section>
  )
}

function Field({
  id,
  label,
  type,
  value,
  onChange,
  placeholder,
}: {
  id: string
  label: string
  type: 'text' | 'password'
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="label-caps mb-1.5 block">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        autoComplete="off"
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="field"
      />
    </div>
  )
}

function Select({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}) {
  return (
    <div>
      <label htmlFor={id} className="label-caps mb-1.5 block">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="field"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}
