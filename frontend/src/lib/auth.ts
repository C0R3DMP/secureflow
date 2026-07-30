/**
 * Client-side auth helpers.
 *
 * The server enforces a shared bearer secret (MCP_SECRET) on every /api and
 * /stream route. Regular requests send it as an Authorization header; the
 * EventSource API cannot set headers, so the SSE stream carries it as a
 * ?token= query parameter instead.
 */

const STORAGE_KEY = 'secureflow.token'

/** Read the token from localStorage, falling back to a ?token= in the URL. */
export function getToken(): string {
  const fromUrl = new URLSearchParams(window.location.search).get('token')
  if (fromUrl) {
    setToken(fromUrl)
    return fromUrl
  }
  return window.localStorage.getItem(STORAGE_KEY) ?? ''
}

export function setToken(token: string): void {
  if (token) {
    window.localStorage.setItem(STORAGE_KEY, token)
  } else {
    window.localStorage.removeItem(STORAGE_KEY)
  }
}

export function hasToken(): boolean {
  return getToken().length > 0
}

/** Merge the bearer token into a fetch() init object. */
export function authHeaders(init?: RequestInit): RequestInit {
  const token = getToken()
  if (!token) return init ?? {}
  return {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  }
}

/** fetch() with the bearer token attached. */
export function authFetch(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, authHeaders(init))
}

/** Append the token as a query parameter, for EventSource URLs. */
export function withToken(url: string): string {
  const token = getToken()
  if (!token) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}token=${encodeURIComponent(token)}`
}
