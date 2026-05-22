import type {
  AudioResponse,
  DailyPlan,
  ErrorData,
  ExplainJaResponse,
  Flashcard,
  Grade,
  PraiseResponse,
  ProgressData,
  Question,
  Session,
  Skill,
  SpeakingScore,
  TokenResponse,
  UpdateUserRequest,
  User,
  VocabClustersResponse,
  VocabHintResponse,
  WritingScore,
} from './types'
import { getToken } from './auth'

function apiUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8100'
  return `${base}${path}`
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

// Analytics
export const apiGetProgress = () => request<ProgressData>('/analytics/progress')

export const apiGetErrors = () => request<ErrorData>('/analytics/errors')

// Question generation
export const apiGenerateQuestion = (skill: Skill) =>
  request<Question>(`/questions/generate?skill=${skill}`, { method: 'POST' })

export const apiPraise = (data: {
  skill: Skill
  is_passing: boolean
  score_pct: number
  streak: number
}) =>
  request<PraiseResponse>('/ai/praise', {
    method: 'POST',
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

export const apiGenerateFlashcardExample = (cardId: string) =>
  request<{ example: string; example_ja: string | null }>(`/flashcards/${cardId}/generate-example`, {
    method: 'POST',
  })

// Questions
export const apiGetQuestions = (skill: Skill, count = 5) =>
  request<Question[]>(`/questions?skill=${skill}&count=${count}`)

// Sessions
export const apiStartSession = (skill: Skill) =>
  request<Session>('/sessions/start', {
    method: 'POST',
    body: JSON.stringify({ skill }),
  })

export const apiEndSession = (
  sessionId: string,
  data: {
    duration_seconds: number
    questions_attempted: number
    correct_count: number
    pomodoro_completed?: boolean
  }
) =>
  request<Session>(`/sessions/${sessionId}/end`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const apiRecordAttempt = (
  sessionId: string,
  data: {
    question_id: string
    skill: Skill
    user_answer?: string
    is_correct: boolean
    time_spent_seconds?: number
  }
) =>
  request<{ id: string }>(`/sessions/${sessionId}/attempt`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const apiScoreWriting = (data: {
  session_id: string
  question_id: string
  answer_text: string
}) =>
  request<WritingScore>('/ai/score-writing', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const apiGenerateAudio = (text: string) =>
  request<AudioResponse>('/ai/generate-audio', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })

export const apiExplainJa = (data: {
  question: string
  choices: string[]
  answer_index: number
  explanation: string
  passage?: string
}) =>
  request<ExplainJaResponse>('/ai/explain-ja', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const apiVocabHint = (word: string) =>
  request<VocabHintResponse>('/ai/vocab-hint', {
    method: 'POST',
    body: JSON.stringify({ word }),
  })

export const apiSeedVocab = (grade: Grade) =>
  request<{ created: number }>(`/flashcards/seed-vocab?grade=${grade}`, { method: 'POST' })

export const apiGetTodayPlan = () => request<DailyPlan>('/schedule/today')

export const apiGetVocabClusters = (grade?: string) =>
  request<VocabClustersResponse>(
    `/vocabulary/clusters${grade ? `?grade=${grade}` : ''}`,
  )

// Push notifications
export const apiGetVapidPublicKey = () =>
  request<{ public_key: string }>('/push/vapid-public-key')

export const apiPushSubscribe = (sub: { endpoint: string; p256dh: string; auth: string }) =>
  request<{ id: string }>('/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(sub),
  })

export const apiPushUnsubscribe = (sub: { endpoint: string; p256dh: string; auth: string }) =>
  request<{ ok: boolean }>('/push/unsubscribe', {
    method: 'DELETE',
    body: JSON.stringify(sub),
  })

export const apiPushTest = () =>
  request<{ sent: number; removed_stale: number }>('/push/test', { method: 'POST' })

export const apiNotifyDailyComplete = () =>
  request<{ ok: boolean }>('/sessions/notify-complete', { method: 'POST' })

export async function apiScoreSpeaking(
  sessionId: string,
  questionId: string,
  topic: string,
  speakingPoints: string[],
  audioBlob: Blob
): Promise<SpeakingScore> {
  const token = getToken()
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.webm')
  form.append('session_id', sessionId)
  form.append('question_id', questionId)
  form.append('topic', topic)
  speakingPoints.forEach(p => form.append('speaking_points', p))
  let res: Response
  try {
    res = await fetch(apiUrl('/ai/score-speaking'), {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
  } catch {
    throw new Error('ネットワークエラー: サーバーに接続できません')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<SpeakingScore>
}
