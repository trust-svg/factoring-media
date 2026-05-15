const TOKEN_KEY = 'eiken_token'

export function saveToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(TOKEN_KEY)
}

export function isTokenExpired(token: string): boolean {
  try {
    const payloadB64 = token.split('.')[1]
    const normalized = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = JSON.parse(atob(normalized)) as { exp?: number }
    if (typeof decoded.exp !== 'number') return true
    return decoded.exp * 1000 < Date.now()
  } catch {
    return true
  }
}
