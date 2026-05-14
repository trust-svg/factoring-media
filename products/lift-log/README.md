# LiftLog

Hiro 個人専用の筋トレ管理 iOS / watchOS アプリ。

## 概要

毎日のワークアウト記録、TANITA 体組成データの連携、Apple Watch でのスタンドアロン記録、Claude API による AI メニュー提案、インターバル中の音楽自動演出までを一本にまとめた個人向けアプリ。

- 個人専用（AppStore 公開予定なし）
- 実機 Sideload / 開発者証明書での個人配信を想定
- 既存 Workspace の Claude API キーを Phase 3 で流用

## 技術スタック

| 機能 | 技術 |
|---|---|
| UI / 状態管理 | SwiftUI + Observable + SwiftData |
| 永続化 | SwiftData (local only) ※ Apple Developer Program 非加入のため CloudKit 不使用 |
| iPhone ↔ Watch 同期 | WatchConnectivity (`WCSession`) のみ |
| グラフ | Swift Charts |
| タイマー | `Timer.publish` + `WKHapticType` + Local Live Activities (Phase 7) |
| TANITA 体組成 | HealthKit (`bodyMass`, `bodyFatPercentage`, `leanBodyMass`, `basalEnergyBurned`) |
| Apple Music 制御 | MusicKit |
| 他アプリ音量 ducking | `AVAudioSession.duckOthers` |
| 音声アナウンス | `AVSpeechSynthesizer`（日本語）|
| AI 提案 | Claude API (`claude-haiku-4-5`) |
| Watch 心拍数 | `HKWorkoutSession` + `HKLiveWorkoutBuilder` |

## フェーズ計画

- **Phase 1**（2–3 週）コア記録 + インターバルタイマー + 基本グラフ ← **現在**
- **Phase 2**（1 週）HealthKit 連携 + 体組成グラフ + Estimated 1RM
- **Phase 3**（1 週）Claude API メニュー提案
- **Phase 4**（3–5 日）MusicKit + ducking 自動演出
- **Phase 5**（1–2 週）Apple Watch v1（補助役）
- **Phase 6**（2–3 週）Apple Watch v2（スタンドアロン）
- **Phase 7**（1 週）Live Activities / ウィジェット / Siri

詳細は [/Users/Mac_air/.claude/plans/encapsulated-twirling-boot.md](../../../.claude/plans/encapsulated-twirling-boot.md) を参照。

## 動作要件

- macOS 14.5+ / Xcode 16+ （実機: Xcode 26.5 で動作確認）
- iOS 17.0+ / watchOS 10.0+
- Apple Silicon Mac 推奨（iOS シミュレーター高速）
- **Apple Developer Program 非加入**：無料 Apple ID で実機 Sideload（7 日署名・週1再ビルド運用）

## セットアップ

### 1. Xcode インストール
AppStore から Xcode を入手し、初回起動でライセンス同意・追加コンポーネントのインストールを完了させる。

### 2. Xcode プロジェクト作成
```
File > New > Project > iOS > App
Product Name: LiftLog
Team: <個人 Apple ID>
Interface: SwiftUI
Storage: SwiftData
Include Tests: ✅
Bundle Identifier: com.trustlink.LiftLog
```
プロジェクトの保存先は本ディレクトリ (`products/lift-log/`) を選ぶ。

### 3. 既存ファイルをプロジェクトに取り込む
Xcode の Project Navigator にドラッグ&ドロップで以下を追加:
- `LiftLog/Models/`
- `LiftLog/DataLayer/`
- `LiftLog/Features/`
- `LiftLog/Services/`
- `LiftLog/Resources/ExercisePresets.json`（Add to Bundle Resources にチェック）

Xcode が自動生成する `LiftLogApp.swift` と `ContentView.swift` は、本リポジトリの `LiftLog/App/LiftLogApp.swift` / `RootView.swift` で置き換える。

### 4. Capability 設定
Phase 1 では特に不要。Phase 2 以降:
- **HealthKit**（Phase 2）
- **Background Modes: Audio**（Phase 4）
- **WatchConnectivity**（Phase 5、watchOS ターゲット追加時に自動）

※ CloudKit は使わない（Apple Developer Program 非加入のため）

### 5. ビルド
シミュレーター（iPhone 15 Pro 等）を選択して ⌘R。

## ディレクトリ

```
products/lift-log/
├── README.md
├── CLAUDE.md                     # プロダクト固有 Claude 指示
├── .gitignore
├── .env.example
├── LiftLog.xcodeproj/            # Xcode 生成後に作られる
├── LiftLog/                      # iOS ターゲット
│   ├── App/
│   ├── Features/{WorkoutLogger,Timer,Charts,History,Settings,AIMenu}/
│   ├── Services/                 # HealthKit / Claude / Music
│   ├── Models/                   # SwiftData @Model
│   ├── DataLayer/
│   └── Resources/
│       └── ExercisePresets.json  # 50 種目
├── LiftLogWatch/                 # watchOS ターゲット（Phase 5）
└── Shared/                       # 両ターゲット共通
```

## 開発状況

- [x] プラン承認（2026-05-13）
- [x] スケルトン作成
- [ ] Xcode プロジェクト初期化
- [ ] Phase 1 実装
