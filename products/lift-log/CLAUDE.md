# CLAUDE.md — LiftLog (products/lift-log)

このファイルは LiftLog プロダクト固有の指示書。Workspace 全体の `CLAUDE.md` を上書き・補完する。

## プロダクト概要

- Hiro 個人専用の筋トレ管理 iOS / watchOS アプリ
- 言語: **Swift 6.0+**（Workspace 全体は Python / TypeScript 中心だが、ここだけ Swift）
- フレームワーク: SwiftUI + SwiftData + HealthKit + MusicKit
- Bundle Identifier: `com.trustlink.LiftLog`
- AppStore 公開なし。個人デバイス Sideload / TestFlight 個人限定配布

## やること（責務）

- iOS / watchOS の SwiftUI 実装
- SwiftData モデル定義とマイグレーション
- HealthKit / MusicKit / Claude API クライアント実装
- Phase 計画に沿った段階実装

## やってはいけないこと（非責務）

- **AppStore 申請関連の作業はしない**（個人専用のため）
- **他プロダクトのコード参照・流用は明示確認の上で**（products/clients/ は強制的に隔離）
- **`Info.plist` や `.xcodeproj` を手で編集しない**（Xcode の GUI で操作）
- **`LiftLog.xcodeproj/project.pbxproj` を直接編集しない**（Xcode が壊れる）

## コード規約

- Swift 6 strict concurrency 対応（actor / @MainActor / Sendable を意識）
- SwiftUI View は 1 ファイル 1 View を原則、共通部品は `Shared/` に
- SwiftData `@Model` は `Models/` 配下、リレーション定義は `@Relationship` で明示
- 命名: 型は PascalCase、プロパティは camelCase、ファイル名は型名と一致

## フェーズ進捗管理

現在: **Phase 3（AI メニュー提案）実装中**

| Phase | 状態 |
|---|---|
| Phase 1 | ✅ complete |
| Phase 2 | ✅ complete |
| Phase 3 | ✅ complete |
| Phase 4 | ⚪ pending |
| Phase 5 | ⚪ pending |
| Phase 6 | ⚪ pending |
| Phase 7 | ⚪ pending |

各 Phase 完了時は本ファイルの状態を更新する。

## 検証ルール（重要）

Workspace 共通の「完了報告前のスモーク確認」が適用される。Swift では:

- **コード変更後は必ず Xcode でビルドして警告ゼロを確認**
- ビルドできない環境（Xcode 未インストール状態）では「ビルド未確認」と明記
- SwiftData モデル変更時はシミュレーターをリセットして起動確認（マイグレーション壊れの早期検知）
- 実機配信前にシミュレーターで golden path（記録 → タイマー → 履歴 → グラフ）を一周

## 環境変数

`.env` は Xcode プロジェクトに直接埋め込まない。Phase 3 で Claude API を実装する際は:
- 開発時: `xcconfig` 経由で `CLAUDE_API_KEY` を Info.plist に埋め込み
- 配信時: Keychain に保存して読み出し（個人アプリでも秘密情報は Keychain）

## 既知の落とし穴

- **CloudKit は使わない（Apple Developer Program 非加入のため）**: `SwiftDataContainer` で `cloudKitDatabase: .none` を明示。将来加入時の再有効化フックはコメントで残してある。`@Model` の relationship は `inverse` を必ず明示（SwiftData 単体でも必須）
- **同期は WatchConnectivity (WCSession) のみ**: iPhone がリーチャブルでない瞬間に Watch でセット保存しても、`transferUserInfo` のキューに積まれて後で配送される。**ライブミラー用の `sendMessage` は reachable 必須**なので、フォールバック UI（「iPhone と接続できません」表示）を必ず用意する
- **マージは last-write-wins by `updatedAt`**: 全エンティティに `id: UUID` と `updatedAt: Date` を持たせ、受信側で冪等 upsert する。`updatedAt` は `Date()` で素直に取り、Watch / iPhone の時計ズレは Apple の自動同期に任せる（独自の単調増加クロックは作らない）
- **HealthKit**: 過去データの自動取得不可（書き込み時刻以降のみ）。TANITA は HealthKit ON 後の測定だけ流れる
- **MusicKit**: シミュレーターでは再生できない。実機必須
- **watchOS standalone**: CloudKit が無いので「Watch だけで完結 → 後で iPhone に同期」は WCSession のキューイング機構が頼り。`transferUserInfo` のドキュメントを守って **一度の payload を 65KB 以下** に抑える（セット1件なら問題なし、複数件まとめ送信時に注意）
- **Local Live Activities のみ**: Push 経由の更新ができない（Apple Developer Program 必須）。インターバルタイマーは Local Activity で `ActivityKit` を直接 update する設計にする

## デプロイ / 配信

- **方針: Apple Developer Program 非加入を継続**（2026-05-14 確定）
- 開発時: Xcode から実機へ直接ビルド（**無料 Apple ID で 7 日署名**）
  - 7 日経つと起動できなくなるので、**週1で Xcode 接続→Run の再署名運用** が必要
  - カレンダー登録 or d-manager の定期リマインドで運用化を検討（Phase 1 完了後）
- TestFlight 配信: 不可。Sideload のみ
- Push Notification / CloudKit / リモート Live Activities: 不可（コードベースで参照しない）
- 将来 Apple Developer Program 加入時: CloudKit 解禁 → SwiftData マイグレーションスクリプト（local store → CloudKit container）を別途設計

## 関連リソース

- 設計プラン: `/Users/Mac_air/.claude/plans/encapsulated-twirling-boot.md`
- HealthPlanet API (Phase 2+): https://www.healthplanet.jp/apis/api.html
- MusicKit: https://developer.apple.com/documentation/musickit
- Claude API: 既存 `ANTHROPIC_API_KEY` を流用
