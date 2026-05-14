import SwiftUI

struct IntervalTimerView: View {
    @State private var controller = IntervalTimerController()
    @State private var presetSeconds: Int = 90

    private var isActive: Bool { controller.isRunning || controller.isPaused }

    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                Spacer()

                // タイマー表示 + ±10秒ボタン
                VStack(spacing: 12) {
                    Text(timeString(controller.remainingSec))
                        .font(.system(size: 96, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(controller.remainingSec <= 5 && controller.isRunning ? .red : .primary)
                        .contentTransition(.numericText())

                    HStack(spacing: 24) {
                        Button("-10") { controller.adjust(by: -10) }
                            .buttonStyle(.bordered)
                            .controlSize(.regular)
                            .disabled(!isActive)

                        Button("+10") { controller.adjust(by: 10) }
                            .buttonStyle(.bordered)
                            .controlSize(.regular)
                            .disabled(!isActive)
                    }
                }

                Picker("プリセット", selection: $presetSeconds) {
                    Text("60s").tag(60)
                    Text("90s").tag(90)
                    Text("2分").tag(120)
                    Text("3分").tag(180)
                    Text("4分").tag(240)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .disabled(isActive)

                // メインボタン
                HStack(spacing: 16) {
                    if !isActive {
                        Button("開始") {
                            controller.start(seconds: presetSeconds)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                    } else if controller.isRunning {
                        Button("一時停止") {
                            controller.pause()
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.orange)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                    } else {
                        Button("再開") {
                            controller.resume()
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                    }

                    if isActive {
                        Button("リセット") {
                            controller.reset(to: presetSeconds)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }
                }
                .padding(.horizontal)
                .animation(.easeInOut(duration: 0.15), value: controller.isRunning)
                .animation(.easeInOut(duration: 0.15), value: controller.isPaused)

                Spacer()
            }
            .padding()
            .navigationTitle("インターバル")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                controller.reset(to: presetSeconds)
            }
            .onChange(of: presetSeconds) { _, newValue in
                if !isActive {
                    controller.reset(to: newValue)
                }
            }
        }
    }

    private func timeString(_ sec: Int) -> String {
        String(format: "%02d:%02d", sec / 60, sec % 60)
    }
}

#Preview {
    IntervalTimerView()
}
