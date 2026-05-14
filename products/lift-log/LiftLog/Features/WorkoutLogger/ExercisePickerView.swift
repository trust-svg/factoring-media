import SwiftUI
import SwiftData

struct ExercisePickerView: View {
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \Exercise.name) private var exercises: [Exercise]
    @State private var selectedCategory: ExerciseCategory?
    @State private var searchText: String = ""

    let onSelect: (Exercise) -> Void

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // カテゴリフィルター
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        CategoryChip(label: "すべて", color: .gray,
                                     isSelected: selectedCategory == nil) {
                            selectedCategory = nil
                        }
                        ForEach(ExerciseCategory.allCases, id: \.self) { cat in
                            CategoryChip(label: cat.displayName, color: cat.accentColor,
                                         isSelected: selectedCategory == cat) {
                                selectedCategory = selectedCategory == cat ? nil : cat
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                }
                .background(Color(.systemGroupedBackground))

                Divider()

                List(filteredExercises) { exercise in
                    Button {
                        onSelect(exercise)
                        dismiss()
                    } label: {
                        ExerciseRow(exercise: exercise)
                    }
                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                }
                .listStyle(.plain)
            }
            .searchable(text: $searchText, prompt: "種目を検索")
            .navigationTitle("種目を選ぶ")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("キャンセル") { dismiss() }
                }
            }
        }
    }

    private var filteredExercises: [Exercise] {
        var list = exercises
        if let cat = selectedCategory { list = list.filter { $0.category == cat } }
        if !searchText.isEmpty {
            list = list.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
        return list
    }
}

// MARK: - Exercise Row

private struct ExerciseRow: View {
    let exercise: Exercise

    var body: some View {
        HStack(spacing: 12) {
            ExerciseIcon(exercise: exercise)

            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Text(exercise.primaryMuscle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Text(exercise.category.displayName)
                .font(.caption2.weight(.medium))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(exercise.category.accentColor.opacity(0.15))
                .foregroundStyle(exercise.category.accentColor)
                .clipShape(Capsule())
        }
        .contentShape(Rectangle())
    }
}

// MARK: - Exercise Icon (SF Symbol or AsyncImage)

private struct ExerciseIcon: View {
    let exercise: Exercise

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10)
                .fill(exercise.category.accentColor.opacity(0.12))
                .frame(width: 48, height: 48)

            if let urlString = exercise.imageURL, let url = URL(string: urlString) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable()
                            .scaledToFit()
                            .frame(width: 36, height: 36)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    default:
                        fallbackIcon
                    }
                }
            } else {
                fallbackIcon
            }
        }
    }

    private var fallbackIcon: some View {
        Image(systemName: exercise.category.sfSymbol)
            .font(.system(size: 22, weight: .medium))
            .foregroundStyle(exercise.category.accentColor)
            .symbolRenderingMode(.hierarchical)
    }
}

// MARK: - Category Chip

private struct CategoryChip: View {
    let label: String
    let color: Color
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline.weight(isSelected ? .semibold : .regular))
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(isSelected ? color : color.opacity(0.1))
                .foregroundStyle(isSelected ? .white : color)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}
