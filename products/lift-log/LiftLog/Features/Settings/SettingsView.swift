import SwiftUI

struct SettingsView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("一般") {
                    NavigationLink {
                        ExerciseMasterPlaceholder()
                    } label: {
                        Label("種目マスター", systemImage: "list.bullet.rectangle")
                    }
                    NavigationLink {
                        TimerSettingsPlaceholder()
                    } label: {
                        Label("タイマー", systemImage: "timer")
                    }
                }

                Section("連携 (Phase 2+)") {
                    Label("HealthKit / TANITA", systemImage: "heart.fill")
                        .foregroundStyle(.secondary)
                    Label("Apple Music", systemImage: "music.note")
                        .foregroundStyle(.secondary)
                    Label("AI メニュー提案", systemImage: "sparkles")
                        .foregroundStyle(.secondary)
                }

                Section("情報") {
                    LabeledContent("バージョン", value: "0.1.0 (Phase 1)")
                    LabeledContent("開発", value: "Hiro 個人専用")
                }
            }
            .navigationTitle("設定")
        }
    }
}

private struct ExerciseMasterPlaceholder: View {
    var body: some View {
        ContentUnavailableView(
            "種目マスター編集",
            systemImage: "wrench.and.screwdriver",
            description: Text("Phase 7 で実装予定。現在はプリセット 50 種目を利用中。")
        )
    }
}

private struct TimerSettingsPlaceholder: View {
    var body: some View {
        ContentUnavailableView(
            "タイマー設定",
            systemImage: "wrench.and.screwdriver",
            description: Text("プリセット秒数や音声アナウンスの設定は Phase 4 で実装予定。")
        )
    }
}

#Preview {
    SettingsView()
}
