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

export interface Question {
  id: string
  grade: Grade
  skill: Skill
  source: string
  content: ReadingContent | ListeningContent | WritingContent | SpeakingContent
  audio_text: string | null
  difficulty: number
}

export interface ReadingContent {
  passage?: string
  question: string
  choices: string[]
  answer: number
  explanation: string
}

export interface ListeningContent {
  question: string
  choices: string[]
  answer: number
  explanation: string
}

export interface WritingContent {
  prompt: string
  min_words: number
  example_response?: string
}

export interface SpeakingContent {
  topic: string
  speaking_points: string[]
  time_limit_seconds: number
}

export interface Session {
  id: string
  skill: Skill
  started_at: string
  ended_at?: string | null
  duration_seconds: number | null
  accuracy_rate: number | null
  questions_attempted: number
  pomodoro_completed: boolean
}

export interface CriterionScore {
  score: number
  max: number
  comment: string
}

export interface WritingScore {
  score: number
  max_score: number
  feedback: string
  criteria: Record<string, CriterionScore>
  is_passing: boolean
}

export interface SpeakingScore extends WritingScore {
  transcript: string
}

export interface AudioResponse {
  audio_base64: string
  duration_hint_seconds: number | null
}

export interface SkillBreakdown {
  reading: number | null
  listening: number | null
  writing: number | null
  speaking: number | null
}

export interface ProgressData {
  pass_probability: number | null
  skill_breakdown: SkillBreakdown
  streak: number
  trend: 'up' | 'flat' | 'down'
  days_remaining: number | null
  total_sessions: number
  grade: string
  advice: string | null
  praise: string | null
  recent_dates: string[]
}

export interface PraiseResponse {
  praise: string
}
