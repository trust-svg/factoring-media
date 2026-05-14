import Foundation
import SwiftUI
import SwiftData

enum ExerciseCategory: String, Codable, CaseIterable, Hashable {
    case chest, back, legs, shoulders, arms, core

    var displayName: String {
        switch self {
        case .chest:     return "胸"
        case .back:      return "背中"
        case .legs:      return "脚"
        case .shoulders: return "肩"
        case .arms:      return "腕"
        case .core:      return "体幹"
        }
    }

    var sfSymbol: String {
        switch self {
        case .chest:     return "figure.strengthtraining.traditional"
        case .back:      return "figure.rowing"
        case .legs:      return "figure.run"
        case .shoulders: return "figure.yoga"
        case .arms:      return "figure.boxing"
        case .core:      return "figure.core.training"
        }
    }

    var accentColor: Color {
        switch self {
        case .chest:     return .red
        case .back:      return .blue
        case .legs:      return .green
        case .shoulders: return .orange
        case .arms:      return .purple
        case .core:      return .yellow
        }
    }
}

@Model
final class Exercise {
    @Attribute(.unique) var id: String
    var name: String
    var categoryRaw: String
    var primaryMuscle: String
    var isCompound: Bool
    var defaultRestSec: Int
    var isCustom: Bool
    var createdAt: Date
    var imageURL: String?  // 種目イラストURL（nil → カテゴリ SF Symbol にフォールバック）

    var category: ExerciseCategory {
        get { ExerciseCategory(rawValue: categoryRaw) ?? .chest }
        set { categoryRaw = newValue.rawValue }
    }

    init(
        id: String,
        name: String,
        category: ExerciseCategory,
        primaryMuscle: String,
        isCompound: Bool,
        defaultRestSec: Int = 90,
        isCustom: Bool = false,
        createdAt: Date = .now,
        imageURL: String? = nil
    ) {
        self.id = id
        self.name = name
        self.categoryRaw = category.rawValue
        self.primaryMuscle = primaryMuscle
        self.isCompound = isCompound
        self.defaultRestSec = defaultRestSec
        self.isCustom = isCustom
        self.createdAt = createdAt
        self.imageURL = imageURL
    }
}
