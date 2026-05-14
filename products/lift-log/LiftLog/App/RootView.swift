import SwiftUI
import SwiftData

struct RootView: View {
    var body: some View {
        TabView {
            WorkoutLoggerView()
                .tabItem { Label("記録", systemImage: "dumbbell.fill") }

            HistoryView()
                .tabItem { Label("履歴", systemImage: "clock.fill") }

            ChartsView()
                .tabItem { Label("推移", systemImage: "chart.line.uptrend.xyaxis") }

            SettingsView()
                .tabItem { Label("設定", systemImage: "gearshape.fill") }
        }
    }
}

#Preview {
    RootView()
        .modelContainer(SwiftDataContainer.shared)
}
