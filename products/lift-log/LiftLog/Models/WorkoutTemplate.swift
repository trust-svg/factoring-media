import Foundation
import SwiftData

/// AI 提案 (Phase 3) または手動作成のテンプレート。
/// exerciseIDs は `Exercise.id` の配列で順序付き。
@Model
final class WorkoutTemplate {
    var id: UUID
    var name: String
    var isAIGenerated: Bool
    var exerciseIDs: [String]
    var notes: String?
    var createdAt: Date
    var lastUsedAt: Date?

    init(
        id: UUID = UUID(),
        name: String,
        isAIGenerated: Bool = false,
        exerciseIDs: [String] = [],
        notes: String? = nil,
        createdAt: Date = .now,
        lastUsedAt: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.isAIGenerated = isAIGenerated
        self.exerciseIDs = exerciseIDs
        self.notes = notes
        self.createdAt = createdAt
        self.lastUsedAt = lastUsedAt
    }
}
