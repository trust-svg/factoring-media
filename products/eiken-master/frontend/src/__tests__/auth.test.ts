// Tests for src/lib/auth.ts
const TOKEN_KEY = 'eiken_token'

const mockLocalStorage = {
  _store: {} as Record<string, string>,
  getItem(k: string) { return this._store[k] ?? null },
  setItem(k: string, v: string) { this._store[k] = v },
  removeItem(k: string) { delete this._store[k] },
}

beforeEach(() => {
  mockLocalStorage._store = {}
  Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
  })
})

describe('saveToken / getToken / clearToken', () => {
  it('saveToken stores value, getToken retrieves it', async () => {
    const { saveToken, getToken } = await import('@/lib/auth')
    saveToken('my-jwt')
    expect(getToken()).toBe('my-jwt')
  })

  it('clearToken removes the value', async () => {
    const { saveToken, getToken, clearToken } = await import('@/lib/auth')
    saveToken('my-jwt')
    clearToken()
    expect(getToken()).toBeNull()
  })
})

describe('isTokenExpired', () => {
  function makeJwt(exp: number): string {
    const payload = btoa(JSON.stringify({ sub: 'u1', exp }))
    return `header.${payload}.sig`
  }

  it('returns true for expired token', async () => {
    const { isTokenExpired } = await import('@/lib/auth')
    const past = Math.floor(Date.now() / 1000) - 3600
    expect(isTokenExpired(makeJwt(past))).toBe(true)
  })

  it('returns false for valid token', async () => {
    const { isTokenExpired } = await import('@/lib/auth')
    const future = Math.floor(Date.now() / 1000) + 3600
    expect(isTokenExpired(makeJwt(future))).toBe(false)
  })

  it('returns true for malformed token', async () => {
    const { isTokenExpired } = await import('@/lib/auth')
    expect(isTokenExpired('not.a.jwt')).toBe(true)
  })
})
