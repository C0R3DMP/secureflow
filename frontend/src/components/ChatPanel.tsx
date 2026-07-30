import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { AlertCircle, MessageSquare, Send, Sparkles, Square, Trash2 } from 'lucide-react'
import { getToken } from '../lib/auth'

interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `c-${Date.now()}-${Math.random().toString(16).slice(2)}`

const SUGGESTIONS = [
  'Which finding should I remediate first, and why?',
  'Explain the most severe CVE in plain terms.',
  'Draft a remediation plan for the next 30 days.',
]

interface ChatPanelProps {
  /** Grounds the conversation in a specific scan's results. */
  target?: string
}

export function ChatPanel({ target }: ChatPanelProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const pinnedRef = useRef(true)

  useEffect(() => {
    const el = scrollRef.current
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight
  }, [turns])

  // Abort any in-flight request if the panel unmounts.
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      const question = text.trim()
      if (!question || streaming) return

      setError(null)
      setDraft('')

      const history = [...turns, { id: uid(), role: 'user' as const, content: question }]
      const replyId = uid()
      setTurns([...history, { id: replyId, role: 'assistant', content: '' }])
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const token = getToken()
        const response = await fetch('/api/chat', {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            messages: history.map(({ role, content }) => ({ role, content })),
            ...(target ? { target } : {}),
          }),
        })

        if (!response.ok) {
          const detail = await response.json().catch(() => ({}))
          throw new Error(detail.error ?? `Server returned ${response.status}`)
        }
        if (!response.body) throw new Error('Server sent no response body')

        // Parse the SSE stream incrementally, holding back partial frames.
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const frames = buffer.split('\n\n')
          buffer = frames.pop() ?? ''

          for (const frame of frames) {
            const line = frame.split('\n').find((l) => l.startsWith('data: '))
            if (!line) continue

            let event: { type: string; text?: string; message?: string }
            try {
              event = JSON.parse(line.slice(6))
            } catch {
              continue
            }

            if (event.type === 'token' && event.text) {
              setTurns((prev) =>
                prev.map((turn) =>
                  turn.id === replyId
                    ? { ...turn, content: turn.content + event.text }
                    : turn,
                ),
              )
            } else if (event.type === 'error') {
              setError(event.message ?? 'The assistant failed to reply')
            }
          }
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setError((e as Error).message)
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
        // Drop an assistant turn that never produced text.
        setTurns((prev) =>
          prev.filter((turn) => turn.id !== replyId || turn.content.length > 0),
        )
      }
    },
    [streaming, turns, target],
  )

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void send(draft)
  }

  const stop = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={() => {
          const el = scrollRef.current
          if (el) {
            pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
          }
        }}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3"
        role="log"
        aria-live="polite"
        aria-label="Conversation with the security assistant"
      >
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
            <Sparkles className="h-6 w-6 text-ink-muted" aria-hidden="true" />
            <div>
              <p className="text-sm text-secondary">Ask about this assessment</p>
              <p className="mt-1 text-xs text-muted">
                {target
                  ? `Answers are grounded in the results for ${target}.`
                  : 'Run a scan first to ground answers in real findings.'}
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => void send(suggestion)}
                  className="panel-inset px-3 py-1.5 text-left text-xs text-secondary transition-colors hover:bg-surface-3"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn) => (
            <div
              key={turn.id}
              className={
                turn.role === 'user'
                  ? 'ml-auto max-w-[85%] rounded-md rounded-br-sm bg-accent px-3 py-2'
                  : 'mr-auto max-w-[92%] rounded-md rounded-bl-sm bg-surface-2 px-3 py-2'
              }
            >
              <p className="label-caps mb-1">
                {turn.role === 'user' ? 'You' : 'Assistant'}
              </p>
              <p
                className={`whitespace-pre-wrap break-words text-[0.8125rem] leading-relaxed ${
                  turn.role === 'user' ? 'text-accent-ink' : 'text-secondary'
                }`}
              >
                {turn.content}
                {streaming && turn.role === 'assistant' && !turn.content && (
                  <span className="text-muted">Thinking…</span>
                )}
              </p>
            </div>
          ))
        )}

        {error && (
          <p
            role="alert"
            className="flex items-start gap-1.5 rounded-sm bg-severity-critical/10 px-3 py-2 text-xs text-severity-critical"
          >
            <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="whitespace-pre-wrap">{error}</span>
          </p>
        )}
      </div>

      <form onSubmit={submit} className="flex items-center gap-2 border-t border-line p-2">
        <label htmlFor="chat-input" className="sr-only">
          Message the security assistant
        </label>
        <input
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about the findings…"
          disabled={streaming}
          autoComplete="off"
          className="field py-1.5 text-[0.8125rem]"
        />
        {streaming ? (
          <button type="button" onClick={stop} className="btn btn-danger shrink-0 py-1.5">
            <Square className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">Stop generating</span>
          </button>
        ) : (
          <button
            type="submit"
            disabled={!draft.trim()}
            className="btn btn-primary shrink-0 py-1.5"
            aria-label="Send message"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
        {turns.length > 0 && !streaming && (
          <button
            type="button"
            onClick={() => {
              setTurns([])
              setError(null)
            }}
            className="icon-btn shrink-0"
            aria-label="Clear conversation"
            title="Clear conversation"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </form>
    </div>
  )
}

export { MessageSquare as ChatIcon }
