import SwiftUI
import SwiftData
import Charts

struct ChartsView: View {
    @Query(sort: \Workout.date) private var workouts: [Workout]

    var body: some View {
        NavigationStack {
            List {
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
                        .frame(height: 220)
                    }
                }

                Section("頻度（直近 4 週）") {
                    LabeledContent("セッション数", value: "\(recentSessionCount(weeks: 4))")
                    LabeledContent("今週", value: "\(recentSessionCount(weeks: 1))")
                }

                Section("連続日数") {
                    LabeledContent("現在", value: "\(currentStreak) 日")
                }
            }
            .navigationTitle("推移")
        }
    }

    private var tonnagePerWeek: [TonnageWeek] {
        let grouped = Dictionary(grouping: workouts) { workout in
            Calendar.current.dateInterval(of: .weekOfYear, for: workout.date)?.start ?? workout.date
        }
        return grouped.map { (weekStart, weekWorkouts) in
            TonnageWeek(
                weekStart: weekStart,
                tonnage: weekWorkouts.reduce(0) { $0 + $1.totalTonnage }
            )
        }
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

struct TonnageWeek: Identifiable {
    var weekStart: Date
    var tonnage: Double
    var id: Date { weekStart }
}

#Preview {
    ChartsView()
        .modelContainer(SwiftDataContainer.shared)
}
