import Foundation
import SwiftData

/// 連続日数・頻度のメトリクス。シングルトン的に 1 レコードのみ保持する想定。
@Model
final class Streak {
    var lastWorkoutDate: Date?
    var currentStreak: Int      // 現在の連続日数
    var longestStreak: Int      // 最長記録
    var weekFrequency: Int      // 今週のセッション数

    init(
        lastWorkoutDate: Date? = nil,
        currentStreak: Int = 0,
        longestStreak: Int = 0,
        weekFrequency: Int = 0
    ) {
        self.lastWorkoutDate = lastWorkoutDate
        self.currentStreak = currentStreak
        self.longestStreak = longestStreak
        self.weekFrequency = weekFrequency
    }
}
