import Foundation
import SwiftData

enum MeasurementSource: String, Codable, Hashable {
    case healthKit
    case healthPlanet
    case manual
}

/// TANITA / HealthKit 由来の体組成データ。Phase 2 で HealthKit 経由の取り込みを実装する。
@Model
final class BodyMeasurement {
    var id: UUID
    var date: Date
    var weight: Double?         // kg
    var bodyFat: Double?        // %
    var muscleMass: Double?     // kg (lean body mass)
    var bmr: Double?            // kcal (basal metabolic rate)
    var height: Double?         // cm
    var sourceRaw: String

    var source: MeasurementSource {
        get { MeasurementSource(rawValue: sourceRaw) ?? .manual }
        set { sourceRaw = newValue.rawValue }
    }

    init(
        id: UUID = UUID(),
        date: Date = .now,
        weight: Double? = nil,
        bodyFat: Double? = nil,
        muscleMass: Double? = nil,
        bmr: Double? = nil,
        height: Double? = nil,
        source: MeasurementSource = .manual
    ) {
        self.id = id
        self.date = date
        self.weight = weight
        self.bodyFat = bodyFat
        self.muscleMass = muscleMass
        self.bmr = bmr
        self.height = height
        self.sourceRaw = source.rawValue
    }
}
