// Tests for src/lib/api.ts
import { apiLogin, apiGetDueFlashcards, apiReviewFlashcard } from '@/lib/api'

// Set env before module evaluation
process.env.NEXT_PUBLIC_API_URL = 'http://test-api'

const mockFetch = jest.fn()
global.fetch = mockFetch

const mockGetItem = jest.fn(() => null as string | null)
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: mockGetItem,
    setItem: jest.fn(),
    removeItem: jest.fn(),
  },
  writable: true,
})

beforeEach(() => {
  mockFetch.mockReset()
  mockGetItem.mockReset()
  mockGetItem.mockReturnValue(null)
})

describe('apiLogin', () => {
  it('POST /auth/login with username and pin', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'tok', token_type: 'bearer', user_id: 'u1', grade: 'pre2' }),
    })

    const result = await apiLogin('taro', '1234')

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'taro', pin: '1234' }),
      }),
    )
    expect(result.access_token).toBe('tok')
  })

  it('throws Error with detail message on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Invalid credentials' }),
    })

    await expect(apiLogin('taro', '0000')).rejects.toThrow('Invalid credentials')
  })
})

describe('apiGetDueFlashcards', () => {
  it('GET /flashcards/due with Authorization header when token exists', async () => {
    mockGetItem.mockReturnValue('my-token')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })

    await apiGetDueFlashcards()

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/flashcards/due',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer my-token',
        }),
      }),
    )
  })
})

describe('apiReviewFlashcard', () => {
  it('POST /flashcards/{id}/review with quality', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'c1', front: 'test', back: '試験' }),
    })

    await apiReviewFlashcard('c1', 4)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/flashcards/c1/review',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ quality: 4 }),
      }),
    )
  })
})
