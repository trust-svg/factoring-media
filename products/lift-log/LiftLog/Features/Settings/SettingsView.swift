import SwiftUI
import SwiftData

struct SettingsView: View {
    @Environment(HealthKitBridge.self) private var bridge
    @Environment(\.modelContext) private var context

    private let claude = ClaudeClient.shared

    @State private var isSyncing = false
    @State private var syncError: String?
    @State private var apiKeyInput: String = ""
    @State private var showAPIKey = false
    @State private var apiKeySaved = false
    @State private var isAPIKeySet = false

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
                            if isSyncing { ProgressView() }
                        }
                    }
                    .disabled(isSyncing)

                    if let last = bridge.lastSyncDate {
                        LabeledContent("最終同期",
                            value: last.formatted(date: .abbreviated, time: .shortened))
                    }
                    if let err = syncError {
                        Text(err).font(.caption).foregroundStyle(.red)
                    }
                }

                Section {
                    apiKeyRow
                } header: {
                    Text("Claude API")
                } footer: {
                    Text("Anthropic の API キー（sk-ant-...）。Keychain に保存されます。")
                }

                Section("連携 (準備中)") {
                    Label("Apple Music", systemImage: "music.note")
                        .foregroundStyle(.secondary)
                }

                Section("情報") {
                    LabeledContent("バージョン", value: "0.3.0 (Phase 3)")
                    LabeledContent("開発", value: "Hiro 個人専用")
                    if claude.totalTokensUsed > 0 {
                        LabeledContent("累計トークン", value: claude.totalTokensUsed.formatted())
                    }
                }
            }
            .navigationTitle("設定")
            .onAppear {
                apiKeyInput = claude.apiKey
                isAPIKeySet = !claude.apiKey.isEmpty
            }
        }
    }

    @ViewBuilder
    private var apiKeyRow: some View {
        if !isAPIKeySet {
            HStack {
                if showAPIKey {
                    TextField("sk-ant-...", text: $apiKeyInput)
                        .font(.system(.body, design: .monospaced))
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                } else {
                    SecureField("sk-ant-...", text: $apiKeyInput)
                        .font(.system(.body, design: .monospaced))
                }
                Button {
                    showAPIKey.toggle()
                } label: {
                    Image(systemName: showAPIKey ? "eye.slash" : "eye")
                        .foregroundStyle(.secondary)
                }
            }

            Button {
                claude.saveAPIKey(apiKeyInput)
                isAPIKeySet = !apiKeyInput.isEmpty
                apiKeySaved = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) { apiKeySaved = false }
            } label: {
                Label(
                    apiKeySaved ? "保存しました ✓" : "保存",
                    systemImage: apiKeySaved ? "checkmark.circle.fill" : "key.fill"
                )
                .foregroundStyle(apiKeySaved ? .green : .accentColor)
            }
            .disabled(apiKeyInput.isEmpty)
        } else {
            HStack {
                Label("設定済み", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Spacer()
                Button("削除", role: .destructive) {
                    claude.saveAPIKey("")
                    apiKeyInput = ""
                    isAPIKeySet = false
                }
                .font(.callout)
            }
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
