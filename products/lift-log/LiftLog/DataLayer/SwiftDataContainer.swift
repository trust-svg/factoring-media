import Foundation
import SwiftData

/// SwiftData の `ModelContainer` を一元管理する。
///
/// **方針: local-only**（2026-05-14 確定）。Apple Developer Program 非加入のため CloudKit は使わない。
/// iPhone ↔ Watch 同期は Phase 5 で WatchConnectivity (`WCSession`) を実装する。
///
/// **将来 Developer Program に加入する場合の解禁手順**（参考）:
/// 1. Xcode の Signing & Capabilities で iCloud > CloudKit を有効化
/// 2. CloudKit container `iCloud.com.trustlink.LiftLog` を追加
/// 3. ModelConfiguration を以下に変更:
///    ```
///    ModelConfiguration(
///        "LiftLog",
///        schema: schema,
///        cloudKitDatabase: .private("iCloud.com.trustlink.LiftLog")
///    )
///    ```
/// 4. 既存 local store からのマイグレーションスクリプトを別途実装
@MainActor
enum SwiftDataContainer {
    static let shared: ModelContainer = {
        let schema = Schema([
            Workout.self,
            WorkoutSet.self,
            Exercise.self,
            BodyMeasurement.self,
            WorkoutTemplate.self,
            Streak.self
        ])
        let config = ModelConfiguration(
            "LiftLog",
            schema: schema,
            isStoredInMemoryOnly: false
        )
        do {
            return try ModelContainer(for: schema, configurations: [config])
        } catch {
            fatalError("[LiftLog] Failed to initialize ModelContainer: \(error)")
        }
    }()

    /// プリセット種目 50 件をシード。既にデータがあれば skip。
    /// アプリ起動時に 1 度だけ呼ぶ。
    static func seedPresetsIfNeeded(context: ModelContext) {
        let descriptor = FetchDescriptor<Exercise>(
            predicate: #Predicate { !$0.isCustom }
        )
        let existing = (try? context.fetch(descriptor)) ?? []
        guard existing.isEmpty else { return }

        guard let url = Bundle.main.url(forResource: "ExercisePresets", withExtension: "json"),
              let data = try? Data(contentsOf: url) else {
            print("[LiftLog] ExercisePresets.json not found in bundle")
            return
        }

        struct PresetExercise: Decodable {
            let id: String
            let name: String
            let category: String
            let primaryMuscle: String
            let isCompound: Bool
            let defaultRestSec: Int
        }

        let decoder = JSONDecoder()
        guard let presets = try? decoder.decode([PresetExercise].self, from: data) else {
            print("[LiftLog] Failed to decode ExercisePresets.json")
            return
        }

        for preset in presets {
            guard let category = ExerciseCategory(rawValue: preset.category.lowercased()) else {
                print("[LiftLog] Unknown category: \(preset.category)")
                continue
            }
            let exercise = Exercise(
                id: preset.id,
                name: preset.name,
                category: category,
                primaryMuscle: preset.primaryMuscle,
                isCompound: preset.isCompound,
                defaultRestSec: preset.defaultRestSec,
                isCustom: false
            )
            context.insert(exercise)
        }

        do {
            try context.save()
            print("[LiftLog] Seeded \(presets.count) preset exercises")
        } catch {
            print("[LiftLog] Failed to save seeded presets: \(error)")
        }
    }
}
