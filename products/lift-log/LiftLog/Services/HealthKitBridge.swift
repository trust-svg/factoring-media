import Foundation

/// HealthKit を介した TANITA 体組成データ読み込みとワークアウト書き込み。
///
/// **Phase 2 で実装予定。** 現在はスタブ。
///
/// 実装方針:
/// - 起動時に `HKHealthStore.requestAuthorization` を呼ぶ
/// - 読み取り: `bodyMass`, `bodyFatPercentage`, `leanBodyMass`, `basalEnergyBurned`, `height`
/// - 書き込み: `HKWorkout` (functionalStrengthTraining)
/// - バックグラウンド配信 `HKObserverQuery` で TANITA の新規データを自動取り込み
final class HealthKitBridge {
    static let shared = HealthKitBridge()
    private init() {}

    /// 権限要求。Info.plist に以下を追加する必要あり:
    /// - `NSHealthShareUsageDescription`
    /// - `NSHealthUpdateUsageDescription`
    func requestAuthorization() async throws {
        // TODO: Phase 2
    }

    /// TANITA 体組成データを `BodyMeasurement` として返す。
    func fetchBodyMeasurements(since: Date) async throws -> [BodyMeasurement] {
        // TODO: Phase 2
        []
    }

    /// ワークアウト完了時に HealthKit へ書き込む。
    func saveWorkout(_ workout: Workout) async throws {
        // TODO: Phase 2
    }
}
