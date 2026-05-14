import SwiftUI
import SwiftData

@main
struct LiftLogApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
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
