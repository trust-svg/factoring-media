import SwiftUI
import SwiftData

struct SettingsView: View {
    @Environment(HealthKitBridge.self) private var bridge
    @Environment(\.modelContext) private var context

    @State private var isSyncing = false
    @State private var syncError: String?

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

                Section("HealthKit / TANITA") {
                    if !bridge.isAuthorized {
                        Button {
                            Task { try await bridge.requestAuthorization() }
                        } label: {
                            Label("権限を許可", systemImage: "heart.fill")
                                .foregroundStyle(.red)
                        }
                    } else {
                        Label("権限あり", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }

                    Button {
                        syncNow()
                    } label: {
                        HStack {
                            Label("今すぐ同期", systemImage: "arrow.triangle.2.circlepath")
                            Spacer()
                            if isSyncing {
                                ProgressView()
                            }
                        }
                    }
                    .disabled(isSyncing)

                    if let last = bridge.lastSyncDate {
                        LabeledContent("最終同期",
                            value: last.formatted(date: .abbreviated, time: .shortened))
                    }

                    if let err = syncError {
                        Text(err)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }

                Section("連携 (準備中)") {
                    Label("Apple Music", systemImage: "music.note")
                        .foregroundStyle(.secondary)
                    Label("AI メニュー提案", systemImage: "sparkles")
                        .foregroundStyle(.secondary)
                }

                Section("情報") {
                    LabeledContent("バージョン", value: "0.2.0 (Phase 2)")
                    LabeledContent("開発", value: "Hiro 個人専用")
                }
            }
            .navigationTitle("設定")
        }
    }

    private func syncNow() {
        isSyncing = true
        syncError = nil
        Task {
            do {
                if !bridge.isAuthorized { try await bridge.requestAuthorization() }
                try await bridge.sync(into: context)
            } catch {
                syncError = error.localizedDescription
            }
            isSyncing = false
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
        .environment(HealthKitBridge.shared)
}
