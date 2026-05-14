import Foundation
import Observation
#if canImport(UIKit)
import UIKit
#endif

/// インターバルタイマーの状態を管理する。
///
/// Phase 4 で `MusicController.startDucking()` / アナウンス連動を組み込む予定。
/// 現状は単純なカウントダウン + 完了時の触覚通知のみ。
@Observable
@MainActor
final class IntervalTimerController {
    private(set) var remainingSec: Int = 90
    private(set) var isRunning: Bool = false
    private(set) var isPaused: Bool = false

    private var timer: Timer?
    private var endDate: Date?

    func start(seconds: Int) {
        stop()
        remainingSec = seconds
        scheduleTimer(from: seconds)
    }

    func pause() {
        guard isRunning else { return }
        isRunning = false
        isPaused = true
        timer?.invalidate()
        timer = nil
        endDate = nil
    }

    func resume() {
        guard isPaused, remainingSec > 0 else { return }
        isPaused = false
        scheduleTimer(from: remainingSec)
    }

    /// 稼働中・一時停止中どちらでも ±秒調整できる
    func adjust(by delta: Int) {
        let newValue = max(1, remainingSec + delta)
        remainingSec = newValue
        if isRunning {
            endDate = Date().addingTimeInterval(TimeInterval(newValue))
        }
    }

    func stop() {
        isRunning = false
        isPaused = false
        timer?.invalidate()
        timer = nil
        endDate = nil
    }

    func reset(to seconds: Int) {
        stop()
        remainingSec = seconds
    }

    private func scheduleTimer(from seconds: Int) {
        endDate = Date().addingTimeInterval(TimeInterval(seconds))
        isRunning = true
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.tick() }
        }
    }

    private func tick() {
        guard let end = endDate else { return }
        let remaining = Int(end.timeIntervalSinceNow.rounded(.up))
        remainingSec = max(0, remaining)
        if remainingSec <= 0 {
            stop()
            triggerCompletion()
        }
    }

    private func triggerCompletion() {
        #if canImport(UIKit)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif
    }
}
