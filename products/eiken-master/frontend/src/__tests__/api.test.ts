// Tests for src/lib/api.ts
import { apiLogin, apiGetDueFlashcards, apiReviewFlashcard, apiGetQuestions, apiStartSession, apiScoreWriting, apiEndSession, apiRecordAttempt } from '@/lib/api'

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

describe('apiGetQuestions', () => {
  it('fetches questions with skill and count params', async () => {
    const mockQ = [{ id: 'q1', skill: 'reading', grade: 'pre2' }]
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockQ,
    } as Response)
    const result = await apiGetQuestions('reading', 3)
    expect(result).toEqual(mockQ)
    expect(mockFetch.mock.calls[0][0]).toContain('skill=reading&count=3')
  })
})

describe('apiStartSession', () => {
  it('posts skill and returns session', async () => {
    const mockSession = { id: 's1', skill: 'writing', questions_attempted: 0 }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSession,
    } as Response)
    const result = await apiStartSession('writing')
    expect(result).toEqual(mockSession)
    const call = mockFetch.mock.calls[0]
    expect(JSON.parse(call[1].body)).toEqual({ skill: 'writing' })
  })
})

describe('apiScoreWriting', () => {
  it('posts answer and returns score', async () => {
    const mockScore = { score: 7, max_score: 10, is_passing: true, feedback: 'ok', criteria: {} }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockScore,
    } as Response)
    const result = await apiScoreWriting({ session_id: 's1', question_id: 'q1', answer_text: 'My essay.' })
    expect(result.is_passing).toBe(true)
    expect(result.score).toBe(7)
  })
})

describe('apiEndSession', () => {
  it('posts end data and returns session', async () => {
    const mockSession = { id: 's1', skill: 'writing', questions_attempted: 3 }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSession,
    } as Response)
    const result = await apiEndSession('s1', {
      duration_seconds: 300,
      questions_attempted: 3,
      correct_count: 2,
    })
    expect(result).toEqual(mockSession)
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/sessions/s1/end')
    expect(JSON.parse(call[1].body).correct_count).toBe(2)
  })
})

describe('apiRecordAttempt', () => {
  it('posts attempt data and returns id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'att1' }),
    } as Response)
    const result = await apiRecordAttempt('s1', {
      question_id: 'q1',
      skill: 'reading',
      is_correct: true,
    })
    expect(result.id).toBe('att1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/sessions/s1/attempt')
  })
})
