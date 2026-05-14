import SwiftUI
import SwiftData

struct WorkoutLoggerView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \Workout.date, order: .reverse) private var workouts: [Workout]
    @State private var activeWorkoutID: PersistentIdentifier?

    private var activeWorkout: Workout? {
        guard let id = activeWorkoutID else { return nil }
        return workouts.first { $0.persistentModelID == id }
    }

    var body: some View {
        NavigationStack {
            Group {
                if let workout = activeWorkout {
                    ActiveWorkoutView(workout: workout, onFinish: finishWorkout)
                } else {
                    StartWorkoutPlaceholderView(onStart: startNewWorkout)
                }
            }
            .navigationTitle("今日のトレ")
            .toolbar {
                if activeWorkout != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("完了", role: .destructive) {
                            finishWorkout()
                        }
                    }
                }
            }
        }
    }

    private func startNewWorkout() {
        let workout = Workout()
        context.insert(workout)
        try? context.save()
        activeWorkoutID = workout.persistentModelID
    }

    private func finishWorkout() {
        guard let workout = activeWorkout else { return }
        workout.durationSec = Int(Date().timeIntervalSince(workout.date))
        try? context.save()
        activeWorkoutID = nil
    }
}

private struct StartWorkoutPlaceholderView: View {
    let onStart: () -> Void

    var body: some View {
        VStack(spacing: 28) {
            Spacer()
            Image(systemName: "dumbbell.fill")
                .font(.system(size: 72))
                .foregroundStyle(.tint)
            Text("ワークアウトを始めよう")
                .font(.title2.bold())
            Text("「開始」を押すと記録セッションがスタートします")
                .foregroundStyle(.secondary)
                .font(.callout)
            Button(action: onStart) {
                Text("新しいセッションを開始")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            .padding(.horizontal, 24)
            Spacer()
        }
    }
}

private struct ActiveWorkoutView: View {
    @Bindable var workout: Workout
    let onFinish: () -> Void

    @Environment(\.modelContext) private var context
    @State private var showExercisePicker = false
    @State private var showTimer = false

    var body: some View {
        List {
            Section {
                LabeledContent("開始時刻", value: workout.date.formatted(date: .omitted, time: .shortened))
                LabeledContent("総挙上重量", value: "\(Int(workout.totalTonnage)) kg")
                LabeledContent("セット数", value: "\(workout.sets.count)")
            }

            Section("セット") {
                if workout.sets.isEmpty {
                    Text("まだセットがありません")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(workout.sets.sorted(by: { $0.completedAt < $1.completedAt })) { set in
                        SetRow(set: set)
                    }
                    .onDelete(perform: deleteSet)
                }
            }

            Section {
                Button {
                    showExercisePicker = true
                } label: {
                    Label("セットを追加", systemImage: "plus.circle.fill")
                }
                Button {
                    showTimer = true
                } label: {
                    Label("インターバルタイマー", systemImage: "timer")
                }
            }
        }
        .sheet(isPresented: $showExercisePicker) {
            ExercisePickerView { exercise in
                addSet(for: exercise)
            }
        }
        .sheet(isPresented: $showTimer) {
            IntervalTimerView()
        }
    }

    private func addSet(for exercise: Exercise) {
        let set = WorkoutSet(
            exercise: exercise,
            reps: 10,
            weight: 20,
            restSec: exercise.defaultRestSec
        )
        set.workout = workout
        context.insert(set)
        workout.sets.append(set)
        try? context.save()
    }

    private func deleteSet(at offsets: IndexSet) {
        let sorted = workout.sets.sorted(by: { $0.completedAt < $1.completedAt })
        for index in offsets {
            context.delete(sorted[index])
        }
        try? context.save()
    }
}

private struct SetRow: View {
    @Bindable var set: WorkoutSet
    @State private var showWeightPicker = false
    @State private var showRepsPicker = false

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(set.exercise?.name ?? "(種目なし)")
                    .font(.headline)
                    .lineLimit(1)
            }

            Spacer()

            HStack(spacing: 8) {
                // 重量タップ → ホイールピッカー
                Button { showWeightPicker = true } label: {
                    VStack(spacing: 2) {
                        Text(weightLabel(set.weight))
                            .font(.title3.bold())
                            .monospacedDigit()
                        Text("kg")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .frame(minWidth: 56)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 10)
                    .background(.thinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)

                Text("×")
                    .foregroundStyle(.secondary)
                    .font(.subheadline)

                // 回数タップ → ホイールピッカー
                Button { showRepsPicker = true } label: {
                    VStack(spacing: 2) {
                        Text("\(set.reps)")
                            .font(.title3.bold())
                            .monospacedDigit()
                        Text("回")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .frame(minWidth: 44)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 10)
                    .background(.thinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)

                if set.isPR {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.yellow)
                        .font(.subheadline)
                }
            }
        }
        .padding(.vertical, 4)
        .sheet(isPresented: $showWeightPicker) {
            WeightPickerSheet(weight: $set.weight)
                .presentationDetents([.height(280)])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showRepsPicker) {
            RepsPickerSheet(reps: $set.reps)
                .presentationDetents([.height(280)])
                .presentationDragIndicator(.visible)
        }
    }

    private func weightLabel(_ w: Double) -> String {
        w.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(w))" : String(format: "%.1f", w)
    }
}

private struct WeightPickerSheet: View {
    @Binding var weight: Double
    @Environment(\.dismiss) private var dismiss

    @State private var intPart: Int
    @State private var fracPart: Int // 0 = .0, 1 = .5

    init(weight: Binding<Double>) {
        _weight = weight
        let w = weight.wrappedValue
        _intPart = State(initialValue: max(0, Int(w)))
        _fracPart = State(initialValue: w.truncatingRemainder(dividingBy: 1) >= 0.4 ? 1 : 0)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Text("重量")
                    .font(.headline)
                Spacer()
                Button("完了") {
                    weight = Double(intPart) + (fracPart == 1 ? 0.5 : 0.0)
                    dismiss()
                }
                .fontWeight(.semibold)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 8)

            HStack(spacing: 0) {
                Picker("整数", selection: $intPart) {
                    ForEach(0...300, id: \.self) { Text("\($0)").tag($0) }
                }
                .pickerStyle(.wheel)
                .frame(maxWidth: .infinity)

                Text(".")
                    .font(.title2.bold())
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 2)

                Picker("小数", selection: $fracPart) {
                    Text("0").tag(0)
                    Text("5").tag(1)
                }
                .pickerStyle(.wheel)
                .frame(width: 80)

                Text("kg")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 8)
                    .padding(.trailing, 16)
            }
            .frame(height: 180)
        }
    }
}

private struct RepsPickerSheet: View {
    @Binding var reps: Int
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Text("回数")
                    .font(.headline)
                Spacer()
                Button("完了") { dismiss() }
                    .fontWeight(.semibold)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 8)

            Picker("回数", selection: $reps) {
                ForEach(1...100, id: \.self) { Text("\($0) 回").tag($0) }
            }
            .pickerStyle(.wheel)
            .frame(height: 180)
        }
    }
}

#Preview {
    WorkoutLoggerView()
        .modelContainer(SwiftDataContainer.shared)
}
