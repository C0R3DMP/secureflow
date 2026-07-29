import { useState, useCallback } from 'react'
import { authHeaders } from '../lib/auth'

export function useAPI<T>(
  url: string,
  options?: RequestInit,
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fetch_ = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(url, authHeaders(options))
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const json = (await response.json()) as T
      setData(json)
      return json
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e))
      setError(err)
      throw err
    } finally {
      setLoading(false)
    }
  }, [url, options])

  return { data, loading, error, fetch: fetch_ }
}
