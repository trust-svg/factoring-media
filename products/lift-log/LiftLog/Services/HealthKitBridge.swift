import Foundation
import HealthKit
import Observation
import SwiftData

@Observable
@MainActor
final class HealthKitBridge {
    static let shared = HealthKitBridge()
    var isAuthorized = false
    var lastSyncDate: Date?

    private let store = HKHealthStore()
    private init() {}

    private var readTypes: Set<HKObjectType> {
        [
            HKQuantityType(.bodyMass),
            HKQuantityType(.bodyFatPercentage),
            HKQuantityType(.leanBodyMass),
            HKQuantityType(.basalEnergyBurned),
            HKQuantityType(.height),
        ]
    }

    private var writeTypes: Set<HKSampleType> {
        [
            HKObjectType.workoutType(),
            HKQuantityType(.activeEnergyBurned),
        ]
    }

    // MARK: - Public API

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        try await store.requestAuthorization(toShare: writeTypes, read: readTypes)
        isAuthorized = true
    }

    /// HealthKit から体組成データを取得し SwiftData context へ upsert する。
    func sync(into context: ModelContext) async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let since = lastSyncDate ?? Calendar.current.date(byAdding: .year, value: -1, to: .now)!
        let incoming = try await fetchBodyMeasurements(since: since)

        // Fetch existing records so we can upsert by date
        let existingFD = FetchDescriptor<BodyMeasurement>(sortBy: [SortDescriptor(\.date)])
        let existing = (try? context.fetch(existingFD)) ?? []
        let existingByDay: [Date: BodyMeasurement] = Dictionary(
            uniqueKeysWithValues: existing.map { (Calendar.current.startOfDay(for: $0.date), $0) }
        )

        for m in incoming {
            let key = Calendar.current.startOfDay(for: m.date)
            if let current = existingByDay[key] {
                if let v = m.weight     { current.weight     = v }
                if let v = m.bodyFat    { current.bodyFat    = v }
                if let v = m.muscleMass { current.muscleMass = v }
                if let v = m.bmr        { current.bmr        = v }
                if let v = m.height     { current.height     = v }
            } else {
                context.insert(m)
            }
        }

        lastSyncDate = .now
        try context.save()
    }

    /// ワークアウト完了時に HealthKit へ書き込む。
    func saveWorkout(_ workout: Workout) async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let start = workout.date
        let end = start.addingTimeInterval(TimeInterval(max(1, workout.durationSec)))

        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining

        let builder = HKWorkoutBuilder(healthStore: store, configuration: config, device: .local())
        try await builder.beginCollection(at: start)

        let kcal = Double(workout.sets.count) * 5.0
        let energySample = HKQuantitySample(
            type: HKQuantityType(.activeEnergyBurned),
            quantity: HKQuantity(unit: .kilocalorie(), doubleValue: kcal),
            start: start,
            end: end
        )
        try await builder.addSamples([energySample])
        try await builder.endCollection(at: end)
        _ = try await builder.finishWorkout()
    }

    // MARK: - Private

    private func fetchBodyMeasurements(since startDate: Date) async throws -> [BodyMeasurement] {
        async let w  = fetchQuantity(.bodyMass,          since: startDate, unit: .gramUnit(with: .kilo))
        async let bf = fetchQuantity(.bodyFatPercentage, since: startDate, unit: .percent())
        async let lm = fetchQuantity(.leanBodyMass,      since: startDate, unit: .gramUnit(with: .kilo))
        async let b  = fetchQuantity(.basalEnergyBurned, since: startDate, unit: .kilocalorie())
        async let h  = fetchQuantity(.height,            since: startDate, unit: .meterUnit(with: .centi))
        let (weights, fats, masses, bmrs, heights) = try await (w, bf, lm, b, h)
        return mergeByDay(weights: weights, fats: fats, masses: masses, bmrs: bmrs, heights: heights)
    }

    private func fetchQuantity(
        _ identifier: HKQuantityTypeIdentifier,
        since startDate: Date,
        unit: HKUnit
    ) async throws -> [(date: Date, value: Double)] {
        let qType = HKQuantityType(identifier)
        let predicate = HKQuery.predicateForSamples(
            withStart: startDate, end: nil, options: .strictStartDate
        )
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: qType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [sort]
            ) { _, samples, error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    let results = (samples as? [HKQuantitySample] ?? []).map {
                        (date: $0.startDate, value: $0.quantity.doubleValue(for: unit))
                    }
                    continuation.resume(returning: results)
                }
            }
            store.execute(query)
        }
    }

    private func mergeByDay(
        weights: [(date: Date, value: Double)],
        fats:    [(date: Date, value: Double)],
        masses:  [(date: Date, value: Double)],
        bmrs:    [(date: Date, value: Double)],
        heights: [(date: Date, value: Double)]
    ) -> [BodyMeasurement] {
        let cal = Calendar.current
        var byDay: [Date: BodyMeasurement] = [:]

        func upsert(_ date: Date, _ block: (BodyMeasurement) -> Void) {
            let key = cal.startOfDay(for: date)
            let m = byDay[key] ?? BodyMeasurement(date: key, source: .healthKit)
            block(m)
            byDay[key] = m
        }

        for (d, v) in weights  { upsert(d) { $0.weight     = v } }
        for (d, v) in fats     { upsert(d) { $0.bodyFat    = v } }
        for (d, v) in masses   { upsert(d) { $0.muscleMass = v } }
        for (d, v) in bmrs     { upsert(d) { $0.bmr        = v } }
        for (d, v) in heights  { upsert(d) { $0.height     = v } }

        return byDay.values.sorted { $0.date < $1.date }
    }
}
