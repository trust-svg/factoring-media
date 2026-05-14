import SwiftUI
import SwiftData
import Charts

struct ChartsView: View {
    @Query(sort: \Workout.date) private var workouts: [Workout]
    @Query(sort: \WorkoutSet.completedAt) private var allSets: [WorkoutSet]
    @Query(sort: \BodyMeasurement.date) private var measurements: [BodyMeasurement]

    @State private var selectedExerciseID: String = "bench-press"

    var body: some View {
        NavigationStack {
            List {
                Section("BIG3 推定 1RM") {
                    big3Section
                }

                Section("種目別 1RM 推移") {
                    oneRMTrendSection
                }

                Section("週次 Tonnage") {
                    if tonnagePerWeek.isEmpty {
                        Text("まだデータがありません")
                            .foregroundStyle(.secondary)
                    } else {
                        Chart(tonnagePerWeek) { item in
                            BarMark(
                                x: .value("週", item.weekStart, unit: .weekOfYear),
                                y: .value("Tonnage (kg)", item.tonnage)
                            )
                            .foregroundStyle(Color.accentColor)
                        }
                        .frame(height: 200)
                    }
                }

                Section("頻度・連続日数") {
                    LabeledContent("今週のセッション", value: "\(recentSessionCount(weeks: 1))")
                    LabeledContent("直近 4 週", value: "\(recentSessionCount(weeks: 4))")
                    LabeledContent("連続記録", value: "\(currentStreak) 日")
                }

                if !measurements.isEmpty {
                    let weightData = measurements.filter { $0.weight != nil }
                    if !weightData.isEmpty {
                        Section("体重推移") {
                            bodyWeightChart(data: weightData)
                        }
                    }

                    let fatData = measurements.filter { $0.bodyFat != nil }
                    if !fatData.isEmpty {
                        Section("体脂肪率推移") {
                            bodyFatChart(data: fatData)
                        }
                    }
                }
            }
            .navigationTitle("推移")
        }
    }

    // MARK: - BIG3

    @ViewBuilder
    private var big3Section: some View {
        if allSets.isEmpty {
            Text("まだデータがありません")
                .foregroundStyle(.secondary)
        } else {
            HStack(spacing: 0) {
                Big3Tile(label: "BENCH", exerciseID: "bench-press", sets: allSets)
                Divider().frame(height: 56)
                Big3Tile(label: "SQUAT", exerciseID: "squat", sets: allSets)
                Divider().frame(height: 56)
                Big3Tile(label: "DEAD", exerciseID: "deadlift", sets: allSets)
            }
            .listRowInsets(EdgeInsets())
        }
    }

    // MARK: - 種目別 1RM Trend

    @ViewBuilder
    private var oneRMTrendSection: some View {
        let available = exercisesWithData
        if available.isEmpty {
            Text("まだデータがありません")
                .foregroundStyle(.secondary)
        } else {
            Picker("種目", selection: $selectedExerciseID) {
                ForEach(available, id: \.id) { Text($0.name).tag($0.id) }
            }

            let trendData = oneRMTrend(for: selectedExerciseID)
            if trendData.isEmpty {
                Text("この種目のデータがありません")
                    .foregroundStyle(.secondary)
            } else {
                Chart(trendData) { point in
                    LineMark(
                        x: .value("日", point.date, unit: .day),
                        y: .value("推定 1RM (kg)", point.oneRM)
                    )
                    .foregroundStyle(Color.accentColor)
                    PointMark(
                        x: .value("日", point.date, unit: .day),
                        y: .value("推定 1RM (kg)", point.oneRM)
                    )
                    .foregroundStyle(Color.accentColor)
                }
                .frame(height: 200)
                .chartYAxisLabel("kg")
            }
        }
    }

    // MARK: - Body Composition Charts

    private func bodyWeightChart(data: [BodyMeasurement]) -> some View {
        Chart(data) { m in
            LineMark(
                x: .value("日", m.date, unit: .day),
                y: .value("体重 (kg)", m.weight!)
            )
            .foregroundStyle(.blue)
            PointMark(
                x: .value("日", m.date, unit: .day),
                y: .value("体重 (kg)", m.weight!)
            )
            .foregroundStyle(.blue)
        }
        .frame(height: 180)
        .chartYAxisLabel("kg")
    }

    private func bodyFatChart(data: [BodyMeasurement]) -> some View {
        Chart(data) { m in
            LineMark(
                x: .value("日", m.date, unit: .day),
                y: .value("体脂肪率 (%)", m.bodyFat!)
            )
            .foregroundStyle(.orange)
            PointMark(
                x: .value("日", m.date, unit: .day),
                y: .value("体脂肪率 (%)", m.bodyFat!)
            )
            .foregroundStyle(.orange)
        }
        .frame(height: 180)
        .chartYAxisLabel("%")
    }

    // MARK: - Computed

    private var exercisesWithData: [Exercise] {
        var seen: [String: Exercise] = [:]
        for set in allSets {
            if let ex = set.exercise { seen[ex.id] = ex }
        }
        return seen.values.sorted { $0.name < $1.name }
    }

    private func oneRMTrend(for exerciseID: String) -> [OneRMPoint] {
        var byDay: [Date: Double] = [:]
        let cal = Calendar.current
        for set in allSets where set.exercise?.id == exerciseID {
            let day = cal.startOfDay(for: set.completedAt)
            byDay[day] = max(byDay[day] ?? 0, set.estimatedOneRepMax)
        }
        return byDay.map { OneRMPoint(date: $0.key, oneRM: $0.value) }
            .sorted { $0.date < $1.date }
    }

    private var tonnagePerWeek: [TonnageWeek] {
        let grouped = Dictionary(grouping: workouts) { workout in
            Calendar.current.dateInterval(of: .weekOfYear, for: workout.date)?.start ?? workout.date
        }
        return grouped.map { TonnageWeek(weekStart: $0.key, tonnage: $0.value.reduce(0) { $0 + $1.totalTonnage }) }
            .sorted { $0.weekStart < $1.weekStart }
    }

    private func recentSessionCount(weeks: Int) -> Int {
        let cutoff = Date().addingTimeInterval(-TimeInterval(weeks * 7 * 86400))
        return workouts.filter { $0.date >= cutoff }.count
    }

    private var currentStreak: Int {
        let calendar = Calendar.current
        let workoutDays = Set(workouts.map { calendar.startOfDay(for: $0.date) })
        var streak = 0
        var day = calendar.startOfDay(for: .now)
        while workoutDays.contains(day) {
            streak += 1
            day = calendar.date(byAdding: .day, value: -1, to: day) ?? day
        }
        return streak
    }
}

// MARK: - Big3 Tile

private struct Big3Tile: View {
    let label: String
    let exerciseID: String
    let sets: [WorkoutSet]

    private var max1RM: Double {
        sets.filter { $0.exercise?.id == exerciseID }
            .map(\.estimatedOneRepMax)
            .max() ?? 0
    }

    var body: some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            if max1RM > 0 {
                Text("\(Int(max1RM))")
                    .font(.title2.bold().monospacedDigit())
                Text("kg")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                Text("—")
                    .font(.title2.bold())
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
    }
}

// MARK: - Supporting Types

struct TonnageWeek: Identifiable {
    var weekStart: Date
    var tonnage: Double
    var id: Date { weekStart }
}

struct OneRMPoint: Identifiable {
    var date: Date
    var oneRM: Double
    var id: Date { date }
}

#Preview {
    ChartsView()
        .modelContainer(SwiftDataContainer.shared)
}
