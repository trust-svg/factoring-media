'use client'

import { useEffect, useState } from 'react'

const STORAGE_KEY = 'eiken_install_banner_dismissed'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export default function InstallBanner() {
  const [show, setShow] = useState(false)
  const [isIos, setIsIos] = useState(false)
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (localStorage.getItem(STORAGE_KEY)) return
    // Already installed as PWA
    if (window.matchMedia('(display-mode: standalone)').matches) return

    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !(window.navigator as unknown as { standalone?: boolean }).standalone
    if (ios) {
      setIsIos(true)
      setShow(true)
      return
    }

    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
      setShow(true)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1')
    setShow(false)
  }

  const install = async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt()
      const { outcome } = await deferredPrompt.userChoice
      if (outcome === 'accepted') localStorage.setItem(STORAGE_KEY, '1')
    }
    setShow(false)
  }

  if (!show) return null

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 max-w-sm mx-auto">
      <div className="bg-indigo-700 text-white rounded-2xl p-4 shadow-2xl flex items-start gap-3">
        <span className="text-2xl shrink-0">📱</span>
        <div className="flex-1 min-w-0">
          <p className="font-black text-sm">ホーム画面に追加</p>
          {isIos ? (
            <p className="text-indigo-200 text-xs mt-0.5 leading-relaxed">
              Safariの <span className="font-bold">共有ボタン</span> → <span className="font-bold">ホーム画面に追加</span> でアプリとして使えます
            </p>
          ) : (
            <p className="text-indigo-200 text-xs mt-0.5">アプリとしてインストールして快適に学習</p>
          )}
        </div>
        <div className="flex flex-col gap-1.5 shrink-0">
          {!isIos && (
            <button
              onClick={install}
              className="bg-white text-indigo-700 text-xs font-black px-3 py-1.5 rounded-xl"
            >
              追加
            </button>
          )}
          <button
            onClick={dismiss}
            className="text-indigo-300 text-xs font-bold px-2 py-1 rounded-xl hover:text-white"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}
