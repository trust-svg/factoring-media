# EikenMaster フロントエンド基盤 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Next.js 15 PWA フロントエンド — 認証・オンボーディング・ホームダッシュボード・フラッシュカード UI を構築し、ブラウザから英検マスターバックエンド (FastAPI) を操作できる状態にする。

**Architecture:** Next.js 15 App Router + TypeScript + Tailwind CSS + `@ducanh2912/next-pwa`。認証は JWT を localStorage に保存し、`AuthProvider` (React Context) で全ページに配布。バックエンド API は `src/lib/api.ts` の fetch ラッパーで呼び出す。バックエンドに不足している `PUT /auth/me` エンドポイントを Task 5 で追加する。

**Tech Stack:** Next.js 15.1, TypeScript 5, Tailwind CSS 3, @ducanh2912/next-pwa 10, Jest 29, @testing-library/react 16

---

## 既存バックエンド API (参照用)

実装済みエンドポイント (port 8100):

```
POST /auth/register   → { access_token, token_type, user_id, grade }
POST /auth/login      → { access_token, token_type, user_id, grade }
GET  /auth/me         → { id, username, grade, exam_date, daily_goal_minutes }
PUT  /auth/me         → { id, username, grade, exam_date, daily_goal_minutes }  ← Task 5 で追加
GET  /flashcards/due  → Flashcard[]
POST /flashcards/     → Flashcard
POST /flashcards/{id}/review  body: { quality: 1-5 } → Flashcard
```

---

## ファイル構成

```
products/eiken-master/frontend/
├── package.json
├── next.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── jest.config.ts
├── jest.setup.ts
├── env.example
├── public/
│   ├── manifest.json
│   └── icons/
│       ├── icon-192.png  (Task 1 でプレースホルダー生成)
│       └── icon-512.png
└── src/
    ├── app/
    │   ├── globals.css
    │   ├── layout.tsx          # Root layout — AuthProvider ラップ + PWA meta
    │   ├── page.tsx            # / → auth 状態で /home or /login にリダイレクト
    │   ├── login/
    │   │   └── page.tsx        # ユーザー名 + PIN ログイン
    │   ├── onboarding/
    │   │   └── page.tsx        # 級選択 → 試験日 → /home
    │   ├── home/
    │   │   └── page.tsx        # ダッシュボード (試験まで日数 + 学習モード)
    │   └── flashcards/
    │       └── page.tsx        # SM-2 フラッシュカード UI
    ├── lib/
    │   ├── types.ts            # 共通 TypeScript 型 (User, Flashcard 等)
    │   ├── api.ts              # fetch ラッパー + エンドポイント関数
    │   └── auth.ts             # JWT localStorage ヘルパー
    └── providers/
        └── AuthProvider.tsx    # React Context: user + loading + logout
```

Plus backend additions:
```
products/eiken-master/api/app/
├── routers/auth.py             # PUT /auth/me エンドポイント追加
└── schemas/auth.py             # UpdateUserRequest スキーマ追加
```

And docker update:
```
products/eiken-master/
├── docker-compose.yml          # nextjs サービス追加
└── frontend/Dockerfile
```

---

## Task 1: Next.js 15 + PWA プロジェクト初期化

**Files:**
- Create: `products/eiken-master/frontend/package.json`
- Create: `products/eiken-master/frontend/next.config.ts`
- Create: `products/eiken-master/frontend/tsconfig.json`
- Create: `products/eiken-master/frontend/tailwind.config.ts`
- Create: `products/eiken-master/frontend/postcss.config.mjs`
- Create: `products/eiken-master/frontend/jest.config.ts`
- Create: `products/eiken-master/frontend/jest.setup.ts`
- Create: `products/eiken-master/frontend/env.example`
- Create: `products/eiken-master/frontend/public/manifest.json`
- Create: `products/eiken-master/frontend/src/app/globals.css`
- Create: `products/eiken-master/frontend/src/app/layout.tsx`
- Create: `products/eiken-master/frontend/src/app/page.tsx`
- Create: `products/eiken-master/frontend/Dockerfile`
- Modify: `products/eiken-master/docker-compose.yml`

- [ ] **Step 1: frontend/ ディレクトリを作成し package.json を作成**

```bash
mkdir -p products/eiken-master/frontend/src/app
mkdir -p products/eiken-master/frontend/public/icons
```

`products/eiken-master/frontend/package.json`:
```json
{
  "name": "eiken-master-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --port 3100",
    "build": "next build",
    "start": "next start --port 3100",
    "test": "jest",
    "test:watch": "jest --watch"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@ducanh2912/next-pwa": "^10.2.9"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "tailwindcss": "^3.4.0",
    "postcss": "^8",
    "autoprefixer": "^10",
    "jest": "^29",
    "jest-environment-jsdom": "^29",
    "@testing-library/react": "^16",
    "@testing-library/jest-dom": "^6",
    "@testing-library/user-event": "^14",
    "@jest/types": "^29"
  }
}
```

- [ ] **Step 2: next.config.ts を作成**

`products/eiken-master/frontend/next.config.ts`:
```typescript
import type { NextConfig } from 'next'
import withPWAInit from '@ducanh2912/next-pwa'

const withPWA = withPWAInit({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  skipWaiting: true,
})

const nextConfig: NextConfig = {
  output: 'standalone',
}

export default withPWA(nextConfig)
```

- [ ] **Step 3: tsconfig.json を作成**

`products/eiken-master/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    },
    "target": "ES2017"
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 4: Tailwind CSS 設定ファイルを作成**

`products/eiken-master/frontend/tailwind.config.ts`:
```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/providers/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}

export default config
```

`products/eiken-master/frontend/postcss.config.mjs`:
```javascript
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}

export default config
```

- [ ] **Step 5: Jest 設定ファイルを作成**

`products/eiken-master/frontend/jest.config.ts`:
```typescript
import type { Config } from '@jest/types'
import nextJest from 'next/jest.js'

const createJestConfig = nextJest({ dir: './' })

const config: Config.InitialOptions = {
  testEnvironment: 'jest-environment-jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
}

export default createJestConfig(config)
```

`products/eiken-master/frontend/jest.setup.ts`:
```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 6: env.example を作成**

`products/eiken-master/frontend/env.example`:
```
NEXT_PUBLIC_API_URL=http://localhost:8100
```

- [ ] **Step 7: PWA manifest.json を作成**

`products/eiken-master/frontend/public/manifest.json`:
```json
{
  "name": "英検マスター",
  "short_name": "英検マスター",
  "description": "英検準2級・2級対策 PWA アプリ",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#4338ca",
  "theme_color": "#4338ca",
  "orientation": "portrait",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

- [ ] **Step 8: プレースホルダーアイコンを生成**

```bash
cd products/eiken-master/frontend
# Python でシンプルな PNG を生成 (Pillow が使えない場合は cp で代替)
python3 -c "
import struct, zlib

def make_png(size, color):
    w = h = size
    raw = b''.join(b'\\x00' + bytes(color) * w for _ in range(h))
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')

with open('public/icons/icon-192.png', 'wb') as f:
    f.write(make_png(192, [67, 56, 202]))
with open('public/icons/icon-512.png', 'wb') as f:
    f.write(make_png(512, [67, 56, 202]))
print('Icons created')
"
```

Expected: `Icons created`

- [ ] **Step 9: App Router 基本ファイルを作成**

`products/eiken-master/frontend/src/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`products/eiken-master/frontend/src/app/layout.tsx`:
```tsx
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '英検マスター',
  description: '英検準2級・2級対策アプリ',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: '英検マスター',
  },
}

export const viewport: Viewport = {
  themeColor: '#4338ca',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  )
}
```

`products/eiken-master/frontend/src/app/page.tsx`:
```tsx
'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('eiken_token')
}

export default function RootPage() {
  const router = useRouter()
  useEffect(() => {
    router.replace(getToken() ? '/home' : '/login')
  }, [router])
  return null
}
```

- [ ] **Step 10: Dockerfile を作成**

`products/eiken-master/frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8100
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3100
ENV PORT=3100
CMD ["node", "server.js"]
```

- [ ] **Step 11: docker-compose.yml に nextjs サービスを追加**

`products/eiken-master/docker-compose.yml` の `services:` セクションの最後に追加:

```yaml
  nextjs:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: https://eiken-api.trustlink-tk.com
    container_name: eiken-nextjs
    restart: unless-stopped
    ports:
      - "127.0.0.1:3100:3100"
    environment:
      TZ: Asia/Tokyo
    depends_on:
      - api
```

- [ ] **Step 12: npm install を実行**

```bash
cd products/eiken-master/frontend
npm install
```

Expected: `added NNN packages` (エラーなし)

- [ ] **Step 13: TypeScript コンパイルチェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし (空出力 or "Found 0 errors")

- [ ] **Step 14: Commit**

```bash
git add products/eiken-master/frontend/ products/eiken-master/docker-compose.yml
git commit -m "feat(eiken): Next.js 15 + PWA セットアップ — frontend/ 初期化"
```

---

## Task 2: TypeScript 型定義 + API クライアント + テスト

**Files:**
- Create: `products/eiken-master/frontend/src/lib/types.ts`
- Create: `products/eiken-master/frontend/src/lib/api.ts`
- Create: `products/eiken-master/frontend/src/__tests__/api.test.ts`

**Context:** `src/lib/api.ts` は `NEXT_PUBLIC_API_URL` 環境変数を参照するため、テスト時は `process.env.NEXT_PUBLIC_API_URL = 'http://test-api'` でモックする。

- [ ] **Step 1: types.ts を作成**

`products/eiken-master/frontend/src/lib/types.ts`:
```typescript
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
```

- [ ] **Step 2: api.ts を作成**

`products/eiken-master/frontend/src/lib/api.ts`:
```typescript
import type {
  Flashcard,
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
    ...(init.headers as Record<string, string> | undefined),
  }
  const res = await fetch(apiUrl(path), { ...init, headers })
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
  grade: string,
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
```

- [ ] **Step 3: テストを書く (失敗することを確認)**

`products/eiken-master/frontend/src/__tests__/api.test.ts`:
```typescript
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
```

- [ ] **Step 4: テストを実行して全部 PASS を確認**

```bash
cd products/eiken-master/frontend
npx jest src/__tests__/api.test.ts --no-coverage 2>&1 | tail -10
```

Expected:
```
Tests:      3 passed, 3 total
```

- [ ] **Step 6: Commit**

```bash
git add products/eiken-master/frontend/src/lib/ products/eiken-master/frontend/src/__tests__/
git commit -m "feat(eiken): TypeScript 型定義 + API クライアント + テスト (3 passed)"
```

---

## Task 3: 認証基盤 (auth.ts + AuthProvider) + テスト

**Files:**
- Create: `products/eiken-master/frontend/src/lib/auth.ts`
- Create: `products/eiken-master/frontend/src/providers/AuthProvider.tsx`
- Create: `products/eiken-master/frontend/src/__tests__/auth.test.ts`

**Context:** `auth.ts` は localStorage の JWT を管理する pure 関数群。`AuthProvider` は React Context でアプリ全体にユーザー情報を配布し、未認証なら `/login` にリダイレクトする。

- [ ] **Step 1: auth.ts のテストを書く (失敗確認)**

`products/eiken-master/frontend/src/__tests__/auth.test.ts`:
```typescript
// Tests for src/lib/auth.ts

const TOKEN_KEY = 'eiken_token'

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: {
      _store: {} as Record<string, string>,
      getItem(k: string) { return this._store[k] ?? null },
      setItem(k: string, v: string) { this._store[k] = v },
      removeItem(k: string) { delete this._store[k] },
    },
    writable: true,
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
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/eiken-master/frontend
npx jest src/__tests__/auth.test.ts --no-coverage 2>&1 | tail -10
```

Expected: FAIL (`Cannot find module '@/lib/auth'`)

- [ ] **Step 3: auth.ts を作成**

`products/eiken-master/frontend/src/lib/auth.ts`:
```typescript
const TOKEN_KEY = 'eiken_token'

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function isTokenExpired(token: string): boolean {
  try {
    const payloadB64 = token.split('.')[1]
    const decoded = JSON.parse(atob(payloadB64)) as { exp?: number }
    if (typeof decoded.exp !== 'number') return true
    return decoded.exp * 1000 < Date.now()
  } catch {
    return true
  }
}
```

- [ ] **Step 4: テストを実行して PASS を確認**

```bash
cd products/eiken-master/frontend
npx jest src/__tests__/auth.test.ts --no-coverage 2>&1 | tail -10
```

Expected:
```
Tests:      5 passed, 5 total
```

- [ ] **Step 5: AuthProvider.tsx を作成**

`products/eiken-master/frontend/src/providers/AuthProvider.tsx`:
```tsx
'use client'

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { apiGetMe } from '@/lib/api'
import { clearToken, getToken, isTokenExpired } from '@/lib/auth'
import type { User } from '@/lib/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  logout: () => void
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const PUBLIC_PATHS = new Set(['/login', '/onboarding'])

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const token = getToken()
    if (!token || isTokenExpired(token)) {
      clearToken()
      setLoading(false)
      if (!PUBLIC_PATHS.has(pathname)) {
        router.replace('/login')
      }
      return
    }
    apiGetMe()
      .then(setUser)
      .catch(() => {
        clearToken()
        router.replace('/login')
      })
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const logout = () => {
    clearToken()
    setUser(null)
    router.replace('/login')
  }

  return (
    <AuthContext.Provider value={{ user, loading, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
```

- [ ] **Step 6: layout.tsx に AuthProvider を追加**

`products/eiken-master/frontend/src/app/layout.tsx` を以下に置き換え:
```tsx
import type { Metadata, Viewport } from 'next'
import './globals.css'
import { AuthProvider } from '@/providers/AuthProvider'

export const metadata: Metadata = {
  title: '英検マスター',
  description: '英検準2級・2級対策アプリ',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: '英検マスター',
  },
}

export const viewport: Viewport = {
  themeColor: '#4338ca',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
```

- [ ] **Step 7: TypeScript チェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし

- [ ] **Step 8: Commit**

```bash
git add products/eiken-master/frontend/src/lib/auth.ts \
        products/eiken-master/frontend/src/providers/ \
        products/eiken-master/frontend/src/app/layout.tsx \
        products/eiken-master/frontend/src/__tests__/auth.test.ts
git commit -m "feat(eiken): 認証基盤 — auth.ts + AuthProvider + テスト (5 passed)"
```

---

## Task 4: ログイン画面

**Files:**
- Create: `products/eiken-master/frontend/src/app/login/page.tsx`

**Context:** PIN入力は数字のみ (inputMode="numeric")、4桁固定。`POST /auth/login` → JWT を localStorage に保存 → `/home` にリダイレクト。

- [ ] **Step 1: ログイン画面を作成**

`products/eiken-master/frontend/src/app/login/page.tsx`:
```tsx
'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { apiLogin } from '@/lib/api'
import { saveToken } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await apiLogin(username, pin)
      saveToken(access_token)
      router.replace('/home')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ログインに失敗しました')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-indigo-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-lg p-8">
        <h1 className="text-2xl font-bold text-center text-indigo-700 mb-1">
          英検マスター
        </h1>
        <p className="text-center text-gray-400 text-sm mb-8">
          ユーザー名と PIN でログイン
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              ユーザー名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              PIN（4桁）
            </label>
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pin}
              onChange={(e) =>
                setPin(e.target.value.replace(/\D/g, '').slice(0, 4))
              }
              autoComplete="current-password"
              required
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm tracking-widest text-center focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || pin.length !== 4 || username.length === 0}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-semibold text-sm disabled:opacity-50 active:bg-indigo-700"
          >
            {loading ? 'ログイン中...' : 'ログイン'}
          </button>
        </form>
      </div>
    </main>
  )
}
```

- [ ] **Step 2: TypeScript チェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし

- [ ] **Step 3: Commit**

```bash
git add products/eiken-master/frontend/src/app/login/
git commit -m "feat(eiken): ログイン画面 — username + PIN 4桁"
```

---

## Task 5: PUT /auth/me バックエンドAPI + オンボーディング UI

**Files:**
- Modify: `products/eiken-master/api/app/routers/auth.py`
- Modify: `products/eiken-master/api/app/schemas/auth.py`
- Modify: `products/eiken-master/api/tests/test_auth_routes.py`
- Create: `products/eiken-master/frontend/src/app/onboarding/page.tsx`

**Context:** オンボーディングは 2 ステップ。Step 1: 準2級/2級を選択。Step 2: 試験日を入力。完了後 `PUT /auth/me` で保存して `/home` へ。スキップも可能。

- [ ] **Step 1: UpdateUserRequest スキーマを schemas/auth.py に追加**

`products/eiken-master/api/app/schemas/auth.py` の末尾に追加:
```python
class UpdateUserRequest(BaseModel):
    grade: Optional[str] = Field(None, pattern=r"^(pre2|2)$")
    exam_date: Optional[date] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=120)

class UserOut(BaseModel):
    id: str
    username: str
    grade: str
    exam_date: Optional[date]
    daily_goal_minutes: int
```

- [ ] **Step 2: PUT /auth/me テストを書く (失敗確認)**

`products/eiken-master/api/tests/test_auth_routes.py` にテストを追加:
```python
def test_update_me_grade(client):
    # まず register
    client.post("/auth/register", json={
        "username": "updater", "pin": "5678", "grade": "pre2"
    })
    login_res = client.post("/auth/login", json={"username": "updater", "pin": "5678"})
    token = login_res.json()["access_token"]

    res = client.put(
        "/auth/me",
        json={"grade": "2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["grade"] == "2"


def test_update_me_exam_date(client):
    client.post("/auth/register", json={
        "username": "examuser", "pin": "9999", "grade": "pre2"
    })
    login_res = client.post("/auth/login", json={"username": "examuser", "pin": "9999"})
    token = login_res.json()["access_token"]

    res = client.put(
        "/auth/me",
        json={"exam_date": "2026-10-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["exam_date"] == "2026-10-01"
```

- [ ] **Step 3: バックエンドテストを実行して失敗を確認**

```bash
cd products/eiken-master/api
DATABASE_URL=sqlite:///./test.db JWT_SECRET=test-secret .venv/bin/python -m pytest tests/test_auth_routes.py::test_update_me_grade tests/test_auth_routes.py::test_update_me_exam_date -v 2>&1 | tail -15
```

Expected: FAIL (`405 Method Not Allowed` — PUT エンドポイントがまだない)

- [ ] **Step 4: PUT /auth/me エンドポイントを auth.py に追加**

`products/eiken-master/api/app/routers/auth.py` の import 行に追加:
```python
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UpdateUserRequest, UserOut
```

そして `me()` 関数の後に追加:
```python
@router.put("/me", response_model=UserOut)
def update_me(
    body: UpdateUserRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if body.grade is not None:
        user.grade = body.grade
    if body.exam_date is not None:
        user.exam_date = body.exam_date
    if body.daily_goal_minutes is not None:
        user.daily_goal_minutes = body.daily_goal_minutes
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        username=user.username,
        grade=user.grade,
        exam_date=user.exam_date,
        daily_goal_minutes=user.daily_goal_minutes,
    )
```

- [ ] **Step 5: バックエンドテストを実行して PASS を確認**

```bash
cd products/eiken-master/api
DATABASE_URL=sqlite:///./test.db JWT_SECRET=test-secret .venv/bin/python -m pytest tests/ -v 2>&1 | tail -20
```

Expected:
```
32 passed
```
(30 既存 + 2 新規)

- [ ] **Step 6: オンボーディング UI を作成**

`products/eiken-master/frontend/src/app/onboarding/page.tsx`:
```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiUpdateMe } from '@/lib/api'
import { useAuth } from '@/providers/AuthProvider'
import type { Grade } from '@/lib/types'

type Step = 'grade' | 'exam_date'

export default function OnboardingPage() {
  const router = useRouter()
  const { setUser } = useAuth()
  const [step, setStep] = useState<Step>('grade')
  const [grade, setGrade] = useState<Grade>('pre2')
  const [examDate, setExamDate] = useState('')
  const [loading, setLoading] = useState(false)

  const handleGradeSelect = (g: Grade) => {
    setGrade(g)
    setStep('exam_date')
  }

  const handleFinish = async () => {
    setLoading(true)
    try {
      const updated = await apiUpdateMe({
        grade,
        exam_date: examDate || null,
      })
      setUser(updated)
    } catch {
      // ignore — go to home anyway
    } finally {
      setLoading(false)
      router.replace('/home')
    }
  }

  const todayStr = new Date().toISOString().split('T')[0]

  if (step === 'grade') {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 px-6">
        <h1 className="text-2xl font-bold text-indigo-700 mb-2">英検マスター</h1>
        <p className="text-gray-500 mb-8 text-center">
          目指す級を選んでください
        </p>
        <div className="flex flex-col gap-4 w-full max-w-xs">
          <button
            onClick={() => handleGradeSelect('pre2')}
            className="bg-white border-2 border-indigo-200 rounded-2xl p-6 text-center shadow-sm hover:border-indigo-500 transition-colors"
          >
            <div className="text-4xl font-bold text-indigo-600">準2級</div>
            <div className="text-sm text-gray-400 mt-1">高校入試レベル</div>
          </button>
          <button
            onClick={() => handleGradeSelect('2')}
            className="bg-white border-2 border-emerald-200 rounded-2xl p-6 text-center shadow-sm hover:border-emerald-500 transition-colors"
          >
            <div className="text-4xl font-bold text-emerald-600">2級</div>
            <div className="text-sm text-gray-400 mt-1">高校卒業レベル</div>
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 px-6">
      <h1 className="text-2xl font-bold text-indigo-700 mb-2">試験日を設定</h1>
      <p className="text-gray-500 mb-6 text-center">
        AIがスケジュールを自動で作ります
      </p>
      <input
        type="date"
        value={examDate}
        onChange={(e) => setExamDate(e.target.value)}
        min={todayStr}
        className="border border-gray-300 rounded-xl px-4 py-3 text-lg mb-6 text-center"
      />
      <button
        onClick={handleFinish}
        disabled={!examDate || loading}
        className="bg-indigo-600 text-white px-10 py-3 rounded-xl font-bold disabled:opacity-50 active:bg-indigo-700"
      >
        {loading ? '保存中...' : 'スタート！'}
      </button>
      <button
        onClick={() => router.replace('/home')}
        className="mt-4 text-sm text-gray-400 underline"
      >
        スキップ
      </button>
    </main>
  )
}
```

- [ ] **Step 7: TypeScript チェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし

- [ ] **Step 8: Commit**

```bash
git add products/eiken-master/api/app/routers/auth.py \
        products/eiken-master/api/app/schemas/auth.py \
        products/eiken-master/api/tests/test_auth_routes.py \
        products/eiken-master/frontend/src/app/onboarding/
git commit -m "feat(eiken): PUT /auth/me バックエンドAPI + オンボーディングUI (32 tests passed)"
```

---

## Task 6: ホームダッシュボード

**Files:**
- Create: `products/eiken-master/frontend/src/app/home/page.tsx`

**Context:** ログイン済みユーザーのダッシュボード。試験まで残り日数・フラッシュカードへのリンク・4技能学習モードへのリンクを表示。AuthProvider の `user` が null なら (loading 中) スピナーを表示。

- [ ] **Step 1: ホームダッシュボードを作成**

`products/eiken-master/frontend/src/app/home/page.tsx`:
```tsx
'use client'

import { useRouter } from 'next/navigation'
import { useAuth } from '@/providers/AuthProvider'
import type { Skill } from '@/lib/types'

interface StudyMode {
  skill: Skill
  label: string
  emoji: string
  bg: string
  text: string
}

const STUDY_MODES: StudyMode[] = [
  { skill: 'reading', label: 'リーディング', emoji: '📖', bg: 'bg-blue-100', text: 'text-blue-700' },
  { skill: 'listening', label: 'リスニング', emoji: '🎧', bg: 'bg-green-100', text: 'text-green-700' },
  { skill: 'writing', label: 'ライティング', emoji: '✍️', bg: 'bg-amber-100', text: 'text-amber-700' },
  { skill: 'speaking', label: 'スピーキング', emoji: '🎤', bg: 'bg-rose-100', text: 'text-rose-700' },
]

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const ms = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(ms / 86_400_000)
}

export default function HomePage() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50">
        <div className="text-indigo-400 text-sm">読み込み中...</div>
      </div>
    )
  }

  if (!user) return null

  const days = daysUntil(user.exam_date)
  const gradeLabel = user.grade === 'pre2' ? '準2級' : '2級'

  return (
    <main className="min-h-screen bg-indigo-50">
      {/* Header */}
      <header className="bg-indigo-700 text-white px-4 py-4 safe-area-top">
        <div className="max-w-lg mx-auto flex justify-between items-center">
          <div>
            <h1 className="font-bold text-lg leading-tight">英検マスター</h1>
            <p className="text-indigo-200 text-xs mt-0.5">
              {gradeLabel} · {user.username}
            </p>
          </div>
          <button
            onClick={logout}
            className="text-indigo-200 text-sm px-3 py-1 rounded-lg hover:bg-indigo-600"
          >
            ログアウト
          </button>
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-5">
        {/* Exam countdown */}
        {days !== null && (
          <div className="bg-white rounded-2xl shadow-sm p-5 text-center">
            <p className="text-gray-400 text-sm mb-1">試験まで</p>
            <p className="text-5xl font-bold text-indigo-700">
              {days}
              <span className="text-2xl font-normal ml-1">日</span>
            </p>
          </div>
        )}

        {/* Flashcard CTA */}
        <button
          onClick={() => router.push('/flashcards')}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl shadow-sm p-4 flex items-center gap-4 transition-colors"
        >
          <span className="text-4xl">🃏</span>
          <div className="text-left">
            <div className="font-bold text-base">今日の単語カード</div>
            <div className="text-indigo-200 text-sm">SM-2 間隔反復</div>
          </div>
          <span className="ml-auto text-indigo-300 text-xl">›</span>
        </button>

        {/* Study mode grid */}
        <div>
          <h2 className="font-bold text-gray-600 text-sm mb-3 px-1">
            学習モード
          </h2>
          <div className="grid grid-cols-2 gap-3">
            {STUDY_MODES.map(({ skill, label, emoji, bg, text }) => (
              <button
                key={skill}
                onClick={() => router.push(`/study/${skill}`)}
                className={`${bg} ${text} rounded-2xl p-5 text-left shadow-sm hover:opacity-80 transition-opacity`}
              >
                <div className="text-3xl mb-2">{emoji}</div>
                <div className="font-semibold text-sm">{label}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Onboarding shortcut */}
        {!user.exam_date && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-center">
            <p className="text-amber-700 text-sm mb-2">試験日が未設定です</p>
            <button
              onClick={() => router.push('/onboarding')}
              className="bg-amber-500 text-white text-sm px-4 py-1.5 rounded-lg font-semibold"
            >
              設定する
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
```

- [ ] **Step 2: TypeScript チェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし

- [ ] **Step 3: Commit**

```bash
git add products/eiken-master/frontend/src/app/home/
git commit -m "feat(eiken): ホームダッシュボード — 試験カウントダウン + 学習モード"
```

---

## Task 7: フラッシュカード UI (SM-2)

**Files:**
- Create: `products/eiken-master/frontend/src/app/flashcards/page.tsx`

**Context:** `GET /flashcards/due` でその日の復習カードを取得し、1枚ずつ表示。表 (英語) を見て裏 (意味) を思い出してから「答えを見る」ボタンを押す。quality 1-5 のボタンで採点し `POST /flashcards/{id}/review` を呼ぶ。全カード完了 or カード 0 枚のときは完了画面を表示。

- [ ] **Step 1: フラッシュカードページを作成**

`products/eiken-master/frontend/src/app/flashcards/page.tsx`:
```tsx
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetDueFlashcards, apiReviewFlashcard } from '@/lib/api'
import type { Flashcard } from '@/lib/types'

interface QualityOption {
  q: number
  label: string
  bg: string
}

const QUALITY_OPTIONS: QualityOption[] = [
  { q: 1, label: '全忘れ', bg: 'bg-red-500' },
  { q: 2, label: '誤答', bg: 'bg-orange-400' },
  { q: 3, label: 'ヒント', bg: 'bg-yellow-400 text-gray-800' },
  { q: 4, label: '正解', bg: 'bg-green-500' },
  { q: 5, label: '即答', bg: 'bg-emerald-600' },
]

export default function FlashcardsPage() {
  const router = useRouter()
  const [cards, setCards] = useState<Flashcard[]>([])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    apiGetDueFlashcards()
      .then(setCards)
      .catch((err) => console.error('Failed to load cards:', err))
      .finally(() => setLoading(false))
  }, [])

  const handleReview = async (quality: number) => {
    if (submitting) return
    setSubmitting(true)
    const card = cards[index]
    try {
      await apiReviewFlashcard(card.id, quality)
    } catch (err) {
      console.error('Review failed:', err)
    }
    if (index + 1 >= cards.length) {
      setDone(true)
    } else {
      setIndex((i) => i + 1)
      setRevealed(false)
    }
    setSubmitting(false)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50">
        <div className="text-indigo-400 text-sm">カードを読み込み中...</div>
      </div>
    )
  }

  if (done || cards.length === 0) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-indigo-50 gap-5">
        <div className="text-6xl">{cards.length === 0 ? '😴' : '🎉'}</div>
        <h2 className="text-xl font-bold text-gray-700">
          {cards.length === 0
            ? '今日の復習カードはありません！'
            : '今日の復習、完了！'}
        </h2>
        {done && (
          <p className="text-gray-400 text-sm">
            {cards.length} 枚のカードを復習しました
          </p>
        )}
        <button
          onClick={() => router.push('/home')}
          className="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold"
        >
          ホームへ
        </button>
      </main>
    )
  }

  const card = cards[index]
  const progress = ((index) / cards.length) * 100

  return (
    <main className="min-h-screen bg-indigo-50 flex flex-col">
      {/* Progress bar */}
      <div className="bg-white px-4 pt-4 pb-3 shadow-sm">
        <div className="max-w-sm mx-auto">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>フラッシュカード</span>
            <span>{index + 1} / {cards.length}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Card area */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-6">
        <div className="w-full max-w-sm space-y-4">
          {/* Front */}
          <div className="bg-white rounded-2xl shadow-sm p-8 text-center">
            <p className="text-xs text-gray-300 uppercase tracking-widest mb-3">
              英語
            </p>
            <p className="text-3xl font-bold text-gray-800">{card.front}</p>
          </div>

          {/* Back / Reveal button */}
          {revealed ? (
            <>
              <div className="bg-indigo-50 border-2 border-indigo-200 rounded-2xl p-6 text-center">
                <p className="text-xs text-indigo-300 uppercase tracking-widest mb-2">
                  意味
                </p>
                <p className="text-2xl font-bold text-indigo-700">{card.back}</p>
              </div>

              <p className="text-center text-xs text-gray-400">
                どれくらい覚えていましたか？
              </p>

              <div className="grid grid-cols-5 gap-2">
                {QUALITY_OPTIONS.map(({ q, label, bg }) => (
                  <button
                    key={q}
                    onClick={() => handleReview(q)}
                    disabled={submitting}
                    className={`${bg} text-white rounded-xl py-2.5 text-xs font-bold disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <button
              onClick={() => setRevealed(true)}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl py-4 font-bold text-lg transition-colors"
            >
              答えを見る
            </button>
          )}
        </div>
      </div>

      {/* Back nav */}
      <div className="p-4 text-center">
        <button
          onClick={() => router.push('/home')}
          className="text-sm text-gray-400 underline"
        >
          ホームに戻る
        </button>
      </div>
    </main>
  )
}
```

- [ ] **Step 2: TypeScript チェック**

```bash
cd products/eiken-master/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: エラーなし

- [ ] **Step 3: 全テスト最終確認 (backend + frontend)**

Backend:
```bash
cd products/eiken-master/api
DATABASE_URL=sqlite:///./test.db JWT_SECRET=test-secret .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `32 passed`

Frontend:
```bash
cd products/eiken-master/frontend
npx jest --no-coverage 2>&1 | tail -5
```
Expected: `8 passed` (3 api.test + 5 auth.test)

- [ ] **Step 4: Commit**

```bash
git add products/eiken-master/frontend/src/app/flashcards/
git commit -m "feat(eiken): フラッシュカード UI — SM-2 quality 採点・進捗バー"
```

- [ ] **Step 5: git push**

```bash
git push origin feature/eiken-master-phase1
```

---

## 完了後の確認事項

### ローカル動作確認 (バックエンド起動済みの場合)

1. `eiken.env` に本番 API キーを設定
2. `docker compose up api postgres -d` でバックエンド起動
3. `cd products/eiken-master/frontend && NEXT_PUBLIC_API_URL=http://localhost:8100 npm run dev`
4. ブラウザで `http://localhost:3100` にアクセス
5. 動作チェック:
   - `/` → `/login` にリダイレクトされること
   - ログイン成功 → `/home` に遷移すること
   - 試験日未設定バナーが表示されること
   - `/onboarding` で級・試験日を保存できること
   - `/flashcards` でカード 0 枚の完了画面が表示されること

### 次のプラン (Plan 3)
- 4技能学習モード (Reading / Listening / Writing / Speaking)
- ポモドーロタイマー
- AI採点 (Claude Haiku) のバックエンド追加
