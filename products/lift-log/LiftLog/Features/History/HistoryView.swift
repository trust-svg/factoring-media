import SwiftUI
import SwiftData

struct HistoryView: View {
    @Query(sort: \Workout.date, order: .reverse) private var workouts: [Workout]
    @State private var viewMode: ViewMode = .calendar

    enum ViewMode: String, CaseIterable {
        case list     = "リスト"
        case calendar = "カレンダー"
    }

    var body: some View {
        NavigationStack {
            Group {
                if workouts.isEmpty {
                    ContentUnavailableView(
                        "履歴はまだありません",
                        systemImage: "calendar.badge.plus",
                        description: Text("最初のワークアウトを記録すると、ここに表示されます。")
                    )
                } else {
                    switch viewMode {
                    case .list:     WorkoutListView(workouts: workouts)
                    case .calendar: WorkoutCalendarView(workouts: workouts)
                    }
                }
            }
            .navigationTitle("履歴")
            .navigationDestination(for: Workout.self) { workout in
                WorkoutDetailView(workout: workout)
            }
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Picker("表示", selection: $viewMode) {
                        ForEach(ViewMode.allCases, id: \.self) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 180)
                }
            }
        }
    }
}

// MARK: - List Mode

private struct WorkoutListView: View {
    let workouts: [Workout]

    var body: some View {
        List {
            ForEach(workouts) { workout in
                NavigationLink(value: workout) {
                    WorkoutRow(workout: workout)
                }
            }
        }
    }
}

private struct WorkoutRow: View {
    let workout: Workout

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(workout.date.formatted(date: .abbreviated, time: .shortened))
                .font(.headline)
            HStack(spacing: 12) {
                Label("\(workout.sets.count) セット", systemImage: "list.bullet")
                Label("\(Int(workout.totalTonnage)) kg", systemImage: "scalemass")
                if workout.durationSec > 0 {
                    Label(formatDuration(workout.durationSec), systemImage: "clock")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    private func formatDuration(_ sec: Int) -> String {
        let h = sec / 3600; let m = (sec % 3600) / 60
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }
}

// MARK: - Calendar Mode

private struct WorkoutCalendarView: View {
    let workouts: [Workout]
    @State private var displayedMonth = Date()
    @State private var selectedDate: Date? = Calendar.current.startOfDay(for: Date())

    private let cal = Calendar.current
    private let weekdays = ["日", "月", "火", "水", "木", "金", "土"]

    private var workoutsByDate: [Date: [Workout]] {
        Dictionary(grouping: workouts) { cal.startOfDay(for: $0.date) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Month navigation header
            HStack {
                Button { shiftMonth(by: -1) } label: {
                    Image(systemName: "chevron.left")
                        .font(.title3.weight(.semibold))
                }
                Spacer()
                Text(monthTitle(displayedMonth))
                    .font(.headline)
                Spacer()
                Button { shiftMonth(by: 1) } label: {
                    Image(systemName: "chevron.right")
                        .font(.title3.weight(.semibold))
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 10)

            // Weekday labels
            HStack(spacing: 0) {
                ForEach(weekdays, id: \.self) { day in
                    Text(day)
                        .font(.caption)
                        .foregroundStyle(day == "日" ? .red : day == "土" ? .blue : .secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 4)

            // Day grid
            let days = monthDays(for: displayedMonth)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 0), count: 7), spacing: 2) {
                ForEach(days.indices, id: \.self) { i in
                    if let date = days[i] {
                        CalendarDayCell(
                            date: date,
                            workouts: workoutsByDate[date] ?? [],
                            isSelected: selectedDate.map { cal.isDate($0, inSameDayAs: date) } ?? false,
                            isToday: cal.isDateInToday(date),
                            onTap: { selectedDate = date }
                        )
                    } else {
                        Color.clear.frame(height: 50)
                    }
                }
            }
            .padding(.horizontal, 8)

            Divider().padding(.top, 8)

            // Selected day detail
            selectedDayContent
        }
    }

    @ViewBuilder
    private var selectedDayContent: some View {
        if let date = selectedDate {
            let dayWorkouts = workoutsByDate[date] ?? []
            if dayWorkouts.isEmpty {
                VStack {
                    Spacer()
                    Text(date.formatted(date: .abbreviated, time: .omitted))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text("ワークアウトなし")
                        .foregroundStyle(.tertiary)
                    Spacer()
                }
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(date.formatted(date: .abbreviated, time: .omitted))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                        ForEach(dayWorkouts) { workout in
                            NavigationLink(value: workout) {
                                WorkoutSummaryCard(workout: workout)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(16)
                }
            }
        } else {
            Color.clear.frame(height: 80)
        }
    }

    private func shiftMonth(by n: Int) {
        displayedMonth = cal.date(byAdding: .month, value: n, to: displayedMonth) ?? displayedMonth
        selectedDate = nil
    }

    private func monthTitle(_ date: Date) -> String {
        date.formatted(.dateTime.year().month(.wide))
    }

    private func monthDays(for date: Date) -> [Date?] {
        guard let range = cal.range(of: .day, in: .month, for: date),
              let first = cal.date(from: cal.dateComponents([.year, .month], from: date))
        else { return [] }
        let offset = (cal.component(.weekday, from: first) - cal.firstWeekday + 7) % 7
        var days: [Date?] = Array(repeating: nil, count: offset)
        for n in range { days.append(cal.date(byAdding: .day, value: n - 1, to: first)) }
        while days.count % 7 != 0 { days.append(nil) }
        return days
    }
}

private struct CalendarDayCell: View {
    let date: Date
    let workouts: [Workout]
    let isSelected: Bool
    let isToday: Bool
    let onTap: () -> Void

    private var categories: [ExerciseCategory] {
        Array(Set(workouts.flatMap { $0.sets }.compactMap { $0.exercise?.category }))
    }

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 3) {
                Text("\(Calendar.current.component(.day, from: date))")
                    .font(.system(size: 14, weight: isToday || isSelected ? .bold : .regular))
                    .foregroundStyle(
                        isSelected ? Color.white
                        : isToday  ? Color.accentColor
                        : Color.primary
                    )
                    .frame(width: 30, height: 30)
                    .background(
                        Circle().fill(isSelected ? Color.accentColor : Color.clear)
                    )

                HStack(spacing: 2) {
                    ForEach(categories.prefix(3), id: \.rawValue) { cat in
                        Circle()
                            .fill(cat.accentColor)
                            .frame(width: 5, height: 5)
                    }
                }
                .frame(height: 6)
            }
            .frame(height: 50)
        }
        .buttonStyle(.plain)
    }
}

private struct WorkoutSummaryCard: View {
    let workout: Workout

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(workout.date.formatted(date: .omitted, time: .shortened))
                    .font(.subheadline.weight(.medium))
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }

            HStack(spacing: 0) {
                statCell(value: formatDuration(workout.durationSec), label: "時間")
                Divider().frame(height: 32)
                statCell(value: "\(workout.sets.count)", label: "セット")
                Divider().frame(height: 32)
                statCell(value: "\(Int(workout.totalTonnage))kg", label: "ボリューム")
            }
        }
        .padding(14)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private func statCell(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.headline.monospacedDigit())
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func formatDuration(_ sec: Int) -> String {
        guard sec > 0 else { return "-" }
        let h = sec / 3600; let m = (sec % 3600) / 60
        return h > 0 ? "\(h)h\(m)m" : "\(m)m"
    }
}

// MARK: - Detail View

struct WorkoutDetailView: View {
    @Bindable var workout: Workout

    var body: some View {
        List {
            Section("サマリー") {
                LabeledContent("日時", value: workout.date.formatted(date: .abbreviated, time: .shortened))
                LabeledContent("セット数", value: "\(workout.sets.count)")
                LabeledContent("総挙上重量", value: "\(Int(workout.totalTonnage)) kg")
                if !workout.workedCategories.isEmpty {
                    LabeledContent("部位",
                        value: workout.workedCategories.map(\.displayName).joined(separator: ", "))
                }
            }

            Section("セット") {
                ForEach(workout.sets.sorted(by: { $0.completedAt < $1.completedAt })) { set in
                    HStack {
                        Text(set.exercise?.name ?? "(不明)")
                        Spacer()
                        Text("\(formatWeight(set.weight)) kg × \(set.reps)")
                            .monospacedDigit()
                    }
                }
            }
        }
        .navigationTitle(workout.date.formatted(date: .abbreviated, time: .omitted))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func formatWeight(_ w: Double) -> String {
        w.truncatingRemainder(dividingBy: 1) == 0
            ? String(format: "%.0f", w)
            : String(format: "%.1f", w)
    }
}

