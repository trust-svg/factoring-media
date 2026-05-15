export type Grade = 'pre2' | '2'
export type Skill = 'reading' | 'listening' | 'writing' | 'speaking'

export interface User {
  id: string
  username: string
  grade: Grade
  exam_date: string | null
  daily_goal_minutes: number
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  grade: Grade
}

export interface Flashcard {
  id: string
  user_id: string
  front: string
  back: string
  source: 'builtin' | 'mined' | 'user'
  ease_factor: number
  interval_days: number
  repetitions: number
  due_date: string
  created_at: string
}

export interface UpdateUserRequest {
  grade?: Grade
  exam_date?: string | null
  daily_goal_minutes?: number
}
