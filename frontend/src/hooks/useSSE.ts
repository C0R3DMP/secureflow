import { useEffect } from 'react'
import type { StreamEvent } from '../types'
import { withToken } from '../lib/auth'

export function useSSE(
  target: string | null,
  onEvent: (event: StreamEvent) => void,
  onError: (error: Error) => void,
) {
  useEffect(() => {
    if (!target) return

    // EventSource cannot set an Authorization header, so the bearer token
    // travels as a query parameter on this route only.
    const eventSource = new EventSource(
      withToken(`/stream/${encodeURIComponent(target)}`),
    )

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as StreamEvent
        onEvent(data)
      } catch (e) {
        onError(new Error(`Failed to parse SSE message: ${e}`))
      }
    }

    const handleError = () => {
      eventSource.close()
      onError(new Error('Connection to server lost'))
    }

    eventSource.addEventListener('message', handleMessage)
    eventSource.addEventListener('error', handleError)

    return () => {
      eventSource.removeEventListener('message', handleMessage)
      eventSource.removeEventListener('error', handleError)
      eventSource.close()
    }
  }, [target, onEvent, onError])
}
