import Foundation
#if canImport(AVFoundation)
import AVFoundation
#endif

/// MusicKit + AVAudioSession ducking でインターバル中の音楽を自動制御する。
///
/// **Phase 4 で実装予定。** 現在はスタブ。
///
/// 実装方針:
/// - `AVAudioSession.setCategory(.playback, options: .duckOthers)` で他アプリの音量を下げる
/// - インターバル残り 3 秒で ducking ON + `AVSpeechSynthesizer` で「3、2、1、スタート」
/// - セット再開で ducking OFF
/// - Apple Music の場合は `MusicKit` でプレイリスト再生 + 完全制御
/// - YouTube Music は ducking のみ（API 操作不可）
final class MusicController {
    static let shared = MusicController()
    private init() {}

    func configureAudioSession() {
        #if canImport(AVFoundation)
        // TODO: Phase 4
        // try? AVAudioSession.sharedInstance().setCategory(.playback, options: [.duckOthers, .mixWithOthers])
        #endif
    }

    func startDucking() {
        // TODO: Phase 4
    }

    func stopDucking() {
        // TODO: Phase 4
    }

    func announceCountdown(_ text: String) {
        // TODO: Phase 4 — AVSpeechSynthesizer で日本語アナウンス
    }
}
