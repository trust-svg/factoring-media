import Foundation
import SwiftData

@Model
final class WorkoutSet {
    var id: UUID
    var exercise: Exercise?
    var reps: Int
    var weight: Double      // kg
    var rpe: Int?           // 1–10 (Rate of Perceived Exertion)
    var restSec: Int
    var completedAt: Date
    var updatedAt: Date
    var isPR: Bool
    var workout: Workout?

    /// Epley formula: 1RM ≈ weight × (1 + reps / 30)
    var estimatedOneRepMax: Double {
        guard reps > 0 else { return 0 }
        return weight * (1.0 + Double(reps) / 30.0)
    }

    /// Tonnage (kg-volume) = weight × reps
    var tonnage: Double {
        weight * Double(reps)
    }

    init(
        id: UUID = UUID(),
        exercise: Exercise? = nil,
        reps: Int,
        weight: Double,
        rpe: Int? = nil,
        restSec: Int = 90,
        completedAt: Date = .now,
        updatedAt: Date = .now,
        isPR: Bool = false
    ) {
        self.id = id
        self.exercise = exercise
        self.reps = reps
        self.weight = weight
        self.rpe = rpe
        self.restSec = restSec
        self.completedAt = completedAt
        self.updatedAt = updatedAt
        self.isPR = isPR
    }
}
