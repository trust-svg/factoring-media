'use client'

export type MascotScene =
  | 'idle'       // char_01: ホーム待機・通常
  | 'correct'    // char_02: 正解・ガッツポーズ
  | 'explain'    // char_03: 説明・教える
  | 'thinking'   // char_04: 考え中・AIロード中
  | 'cheer'      // char_05: 励まし・不正解後の応援
  | 'tired'      // char_06: ポモドーロ休憩
  | 'surprise'   // char_07: 驚き（合格確率ジャンプ）
  | 'celebrate'  // char_08: セッション完了・祝福

const SCENE_MAP: Record<MascotScene, string> = {
  idle:      '/characters/char_01.png',
  correct:   '/characters/char_02.png',
  explain:   '/characters/char_03.png',
  thinking:  '/characters/char_04.png',
  cheer:     '/characters/char_05.png',
  tired:     '/characters/char_06.png',
  surprise:  '/characters/char_07.png',
  celebrate: '/characters/char_08.png',
}

interface MascotProps {
  scene: MascotScene
  size?: number
  className?: string
}

export default function Mascot({ scene, size = 120, className = '' }: MascotProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={SCENE_MAP[scene]}
      alt=""
      width={size}
      height={size}
      className={`select-none pointer-events-none ${className}`}
      style={{ objectFit: 'contain', animation: 'float 4s ease-in-out infinite' }}
    />
  )
}
