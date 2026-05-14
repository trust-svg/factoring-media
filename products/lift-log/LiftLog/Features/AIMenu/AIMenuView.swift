import SwiftUI
import SwiftData

struct AIMenuView: View {
    private let client = ClaudeClient.shared
    @Environment(\.modelContext) private var context

    @Query(sort: \WorkoutSet.completedAt, order: .reverse) private var allSets: [WorkoutSet]
    @Query(sort: \BodyMeasurement.date, order: .reverse) private var measurements: [BodyMeasurement]
    @Query(sort: \Exercise.name) private var exercises: [Exercise]

    @State private var selectedCategory: ExerciseCategory?
    @State private var isGenerating = false
    @State private var generatedResponse: MenuResult?
    @State private var errorMessage: String?
    @State private var savedConfirmation = false

    struct MenuResult {
        let templateName: String
        let exerciseIDs: [String]
        let reasoning: String
        let tokensUsed: Int
    }

    var body: some View {
        NavigationStack {
            List {
                generationSection
                if let result = generatedResponse {
                    resultSection(result)
                    saveSection(result)
                }
                TemplateListSection(exercises: Array(exercises))
            }
            .navigationTitle("AI メニュー")
            .navigationBarTitleDisplayMode(.large)
        }
    }

    // MARK: - View Sections

    @ViewBuilder
    private var generationSection: some View {
        Section {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    FilterChip(label: "おまかせ", isSelected: selectedCategory == nil) {
                        selectedCategory = nil
                    }
                    ForEach(ExerciseCategory.allCases, id: \.self) { cat in
                        FilterChip(
                            label: cat.displayName,
                            color: cat.accentColor,
                            isSelected: selectedCategory == cat
                        ) {
                            selectedCategory = selectedCategory == cat ? nil : cat
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))

            if client.apiKey.isEmpty {
                Label("APIキーが未設定です（設定タブで入力）", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .font(.callout)
            }

            Button {
                generate()
            } label: {
                HStack {
                    Label("メニューを提案してもらう", systemImage: "sparkles")
                        .font(.headline)
                    Spacer()
                    if isGenerating { ProgressView() }
                }
            }
            .disabled(isGenerating || client.apiKey.isEmpty)

            if let err = errorMessage {
                Text(err).font(.caption).foregroundStyle(.red)
            }
        } header: {
            Text("メニュー生成")
        } footer: {
            Text("直近2週間の記録と体組成データをもとに Haiku が提案します。")
        }
    }

    @ViewBuilder
    private func resultSection(_ result: MenuResult) -> some View {
        Section("提案結果") {
            VStack(alignment: .leading, spacing: 10) {
                Text(result.templateName).font(.headline)
                Divider()
                ForEach(resolvedExercises(result.exerciseIDs), id: \Exercise.id) { ex in
                    HStack(spacing: 10) {
                        Image(systemName: ex.category.sfSymbol)
                            .foregroundStyle(ex.category.accentColor)
                            .frame(width: 24)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(ex.name).font(.body)
                            Text(ex.primaryMuscle).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                Divider()
                Text(result.reasoning).font(.callout).foregroundStyle(.secondary)
                Text("使用トークン: \(result.tokensUsed)")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .padding(.vertical, 4)
        }
    }

    @ViewBuilder
    private func saveSection(_ result: MenuResult) -> some View {
        Section {
            Button {
                saveTemplate(result)
            } label: {
                if savedConfirmation {
                    Label("保存しました", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else {
                    Label("テンプレートとして保存", systemImage: "square.and.arrow.down")
                }
            }
            .disabled(savedConfirmation)
        }
    }

    // MARK: - Actions

    private func generate() {
        isGenerating = true
        errorMessage = nil
        generatedResponse = nil
        savedConfirmation = false
        Task {
            do {
                let request = ClaudeClient.MenuRequest(
                    recentSets: Array(allSets.prefix(200)),
                    recentMeasurements: Array(measurements.prefix(10)),
                    targetCategory: selectedCategory
                )
                let resp = try await client.generateMenu(request, exercises: Array(exercises))
                generatedResponse = MenuResult(
                    templateName: resp.templateName,
                    exerciseIDs: resp.exerciseIDs,
                    reasoning: resp.reasoning,
                    tokensUsed: resp.tokensUsed
                )
            } catch {
                errorMessage = error.localizedDescription
            }
            isGenerating = false
        }
    }

    private func saveTemplate(_ result: MenuResult) {
        let t = WorkoutTemplate(
            name: result.templateName,
            isAIGenerated: true,
            exerciseIDs: result.exerciseIDs,
            notes: result.reasoning
        )
        context.insert(t)
        try? context.save()
        savedConfirmation = true
    }

    private func resolvedExercises(_ ids: [String]) -> [Exercise] {
        ids.compactMap { id in exercises.first { $0.id == id } }
    }
}

// MARK: - Template List Section (独立 View で @Query を持つ)

private struct TemplateListSection: View {
    @Query(sort: \WorkoutTemplate.createdAt, order: .reverse) private var templates: [WorkoutTemplate]
    @Environment(\.modelContext) private var context
    let exercises: [Exercise]

    var body: some View {
        if !templates.isEmpty {
            Section("保存済みテンプレート") {
                ForEach(templates, id: \.persistentModelID) { template in
                    NavigationLink {
                        TemplateDetailView(template: template, exercises: exercises)
                    } label: {
                        templateRow(template)
                    }
                }
                .onDelete(perform: deleteTemplates)
            }
        }
    }

    @ViewBuilder
    private func templateRow(_ template: WorkoutTemplate) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(template.name)
                if template.isAIGenerated {
                    Image(systemName: "sparkles")
                        .font(.caption2)
                        .foregroundStyle(Color.accentColor)
                }
            }
            Text("\(template.exerciseIDs.count) 種目")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func deleteTemplates(at offsets: IndexSet) {
        for i in offsets { context.delete(templates[i]) }
        try? context.save()
    }
}

// MARK: - Template Detail

private struct TemplateDetailView: View {
    let template: WorkoutTemplate
    let exercises: [Exercise]

    var body: some View {
        List {
            Section("種目") {
                ForEach(resolvedExercises, id: \Exercise.id) { ex in
                    HStack(spacing: 10) {
                        Image(systemName: ex.category.sfSymbol)
                            .foregroundStyle(ex.category.accentColor)
                            .frame(width: 24)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(ex.name)
                            Text(ex.primaryMuscle).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if let notes = template.notes, !notes.isEmpty {
                Section("提案理由") { Text(notes).font(.callout) }
            }
            Section("情報") {
                LabeledContent("作成日",
                    value: template.createdAt.formatted(date: .abbreviated, time: .shortened))
                if template.isAIGenerated {
                    LabeledContent("種別", value: "AI 生成")
                }
            }
        }
        .navigationTitle(template.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var resolvedExercises: [Exercise] {
        template.exerciseIDs.compactMap { id in exercises.first { $0.id == id } }
    }
}

// MARK: - Filter Chip

private struct FilterChip: View {
    let label: String
    var color: Color = .gray
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

#Preview {
    AIMenuView()
        .modelContainer(SwiftDataContainer.shared)
}
