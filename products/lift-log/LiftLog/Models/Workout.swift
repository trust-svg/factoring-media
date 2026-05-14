import Foundation
import SwiftData

@Model
final class Workout {
    var id: UUID
    var date: Date
    var durationSec: Int
    var notes: String?
    var updatedAt: Date

    @Relationship(deleteRule: .cascade, inverse: \WorkoutSet.workout)
    var sets: [WorkoutSet]

    /// セッション内全セットの総挙上重量 (kg)
    var totalTonnage: Double {
        sets.reduce(0) { $0 + $1.tonnage }
    }

    /// 動かした部位の一覧（重複排除済み）
    var workedCategories: [ExerciseCategory] {
        let cats = sets.compactMap { $0.exercise?.category }
        return Array(Set(cats)).sorted { $0.rawValue < $1.rawValue }
    }

    init(
        id: UUID = UUID(),
        date: Date = .now,
        durationSec: Int = 0,
        notes: String? = nil,
        updatedAt: Date = .now,
        sets: [WorkoutSet] = []
    ) {
        self.id = id
        self.date = date
        self.durationSec = durationSec
        self.notes = notes
        self.updatedAt = updatedAt
        self.sets = sets
    }
}
