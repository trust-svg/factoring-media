import type {
  Flashcard,
  Grade,
  TokenResponse,
  UpdateUserRequest,
  User,
} from './types'

function apiUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8100'
  return `${base}${path}`
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('eiken_token')
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  let res: Response
  try {
    res = await fetch(apiUrl(path), { ...init, headers })
  } catch {
    throw new Error('ネットワークエラー: サーバーに接続できません')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// Auth
export const apiLogin = (username: string, pin: string) =>
  request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, pin }),
  })

export const apiRegister = (
  username: string,
  pin: string,
  grade: Grade,
  exam_date?: string,
  daily_goal_minutes = 30,
) =>
  request<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, pin, grade, exam_date, daily_goal_minutes }),
  })

export const apiGetMe = () => request<User>('/auth/me')

export const apiUpdateMe = (data: UpdateUserRequest) =>
  request<User>('/auth/me', {
    method: 'PUT',
    body: JSON.stringify(data),
  })

// Flashcards
export const apiGetDueFlashcards = () =>
  request<Flashcard[]>('/flashcards/due')

export const apiCreateFlashcard = (front: string, back: string) =>
  request<Flashcard>('/flashcards/', {
    method: 'POST',
    body: JSON.stringify({ front, back }),
  })

export const apiReviewFlashcard = (cardId: string, quality: number) =>
  request<Flashcard>(`/flashcards/${cardId}/review`, {
    method: 'POST',
    body: JSON.stringify({ quality }),
  })
