import { formatTime } from '@/components/PomodoroTimer'

describe('formatTime', () => {
  it('formats 0 as 00:00', () => {
    expect(formatTime(0)).toBe('00:00')
  })

  it('formats 65 as 01:05', () => {
    expect(formatTime(65)).toBe('01:05')
  })

  it('formats 1500 as 25:00', () => {
    expect(formatTime(1500)).toBe('25:00')
  })

  it('formats 599 as 09:59', () => {
    expect(formatTime(599)).toBe('09:59')
  })
})
