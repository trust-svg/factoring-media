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
