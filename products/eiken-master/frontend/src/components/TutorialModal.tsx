'use client'

import { useEffect, useState } from 'react'

const STORAGE_KEY = 'eiken_tutorial_shown_v1'

const slides = [
  {
    emoji: '🎉',
    title: '英検マスターへようこそ！',
    body: '英検準2級・2級に合格するための学習アプリです。AIが問題を出して、あなたの弱点を分析します。',
    color: 'from-violet-500 to-purple-600',
  },
  {
    emoji: '📖',
    title: '4技能で学ぼう',
    body: 'リーディング・リスニング・ライティング・スピーキングの4技能を毎日バランスよく練習できます。',
    color: 'from-blue-500 to-indigo-600',
  },
  {
    emoji: '🃏',
    title: '単語カードで暗記',
    body: '科学的な間隔反復法（SM-2）で単語を効率よく暗記。忘れそうになる前に自動でリマインドします。',
    color: 'from-emerald-500 to-teal-600',
  },
  {
    emoji: '📊',
    title: 'AIが合格確率を計算',
    body: '毎日の学習データをもとに、AIがあなたの合格確率をリアルタイムで計算します。',
    color: 'from-amber-500 to-orange-600',
  },
  {
    emoji: '🚀',
    title: 'さあ、はじめよう！',
    body: '毎日少しずつ積み上げれば、必ず合格できます。今日の最初の問題にチャレンジしよう！',
    color: 'from-pink-500 to-rose-600',
  },
]

export default function TutorialModal() {
  const [visible, setVisible] = useState(false)
  const [slideIndex, setSlideIndex] = useState(0)
  const [dontShowAgain, setDontShowAgain] = useState(true)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const shown = localStorage.getItem(STORAGE_KEY)
      if (!shown) setVisible(true)
    }
  }, [])

  const handleClose = (force = false) => {
    if (typeof window !== 'undefined' && (dontShowAgain || force)) {
      localStorage.setItem(STORAGE_KEY, '1')
    }
    setVisible(false)
  }

  const handleNext = () => {
    if (slideIndex < slides.length - 1) {
      setSlideIndex((i) => i + 1)
    } else {
      handleClose(true)
    }
  }

  if (!visible) return null

  const slide = slides[slideIndex]
  const isLast = slideIndex === slides.length - 1

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.65)' }}>
      <div className="bg-white rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl">
        {/* Colored header */}
        <div className={`bg-gradient-to-br ${slide.color} px-8 py-10 text-center`}>
          <div className="text-7xl mb-4">{slide.emoji}</div>
          <h2 className="text-xl font-black text-white">{slide.title}</h2>
        </div>

        {/* Dots */}
        <div className="flex justify-center gap-2 pt-5">
          {slides.map((_, i) => (
            <button
              key={i}
              onClick={() => setSlideIndex(i)}
              className={`rounded-full transition-all duration-300 ${
                i === slideIndex ? 'w-6 h-2.5 bg-indigo-500' : 'w-2.5 h-2.5 bg-gray-200'
              }`}
            />
          ))}
        </div>

        {/* Body */}
        <div className="px-8 py-6 text-center">
          <p className="text-gray-600 text-base leading-relaxed">{slide.body}</p>
        </div>

        {/* Don't show again */}
        <div className="px-6 pb-2 flex items-center gap-2.5">
          <input
            type="checkbox"
            id="eiken-dont-show"
            checked={dontShowAgain}
            onChange={(e) => setDontShowAgain(e.target.checked)}
            className="w-4 h-4 rounded accent-indigo-600 cursor-pointer"
          />
          <label htmlFor="eiken-dont-show" className="text-gray-400 text-sm cursor-pointer select-none">
            次回から表示しない
          </label>
        </div>

        {/* Buttons */}
        <div className="px-6 pb-8 space-y-2.5">
          <button
            onClick={handleNext}
            className="w-full bg-indigo-600 text-white py-4 rounded-2xl font-black text-base"
          >
            {isLast ? '🚀 はじめる！' : '次へ →'}
          </button>
          {!isLast && (
            <button onClick={() => handleClose()} className="w-full text-gray-400 py-2 text-sm font-bold">
              スキップ
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
