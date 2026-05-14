import Foundation

/// Claude API でメニュー提案を生成するクライアント。
///
/// **Phase 3 で実装予定。** 現在はスタブ。
///
/// 実装方針:
/// - `claude-haiku-4-5` を使用（コスト最小化）
/// - 入力: 直近 2 週間のセット記録、体重推移、部位別最終トレ日
/// - 出力: 種目リスト + セット数 + rep 範囲 + 提案理由
/// - APIキーは Keychain に保存
/// - 1 リクエストあたりのトークン数をログ
final class ClaudeClient {
    static let shared = ClaudeClient()
    private init() {}

    struct MenuRequest {
        let recentSets: [WorkoutSet]
        let recentMeasurements: [BodyMeasurement]
        let targetCategory: ExerciseCategory?
    }

    struct MenuResponse {
        let templateName: String
        let exerciseIDs: [String]
        let reasoning: String
        let tokensUsed: Int
    }

    func generateMenu(_ request: MenuRequest) async throws -> MenuResponse {
        // TODO: Phase 3
        MenuResponse(
            templateName: "",
            exerciseIDs: [],
            reasoning: "",
            tokensUsed: 0
        )
    }
}
