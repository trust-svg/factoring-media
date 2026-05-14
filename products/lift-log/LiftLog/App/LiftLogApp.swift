import SwiftUI
import SwiftData

@main
struct LiftLogApp: App {
    private let hkBridge = HealthKitBridge.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(hkBridge)
                .task {
                    await MainActor.run {
                        SwiftDataContainer.seedPresetsIfNeeded(
                            context: SwiftDataContainer.shared.mainContext
                        )
                    }
                }
        }
        .modelContainer(SwiftDataContainer.shared)
    }
}
