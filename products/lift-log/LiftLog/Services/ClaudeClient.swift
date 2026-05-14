import Foundation
import Security

final class ClaudeClient {
    static let shared = ClaudeClient()

    var apiKey: String = ""
    var totalTokensUsed: Int = 0

    private let keychainAccount = "com.trustlink.LiftLog.anthropicAPIKey"
    private let apiURL = URL(string: "https://api.anthropic.com/v1/messages")!
    private let model = "claude-haiku-4-5-20251001"

    private init() {
        apiKey = loadFromKeychain() ?? loadFromBundle() ?? ""
    }

    // MARK: - API Key

    func saveAPIKey(_ key: String) {
        apiKey = key.trimmingCharacters(in: .whitespaces)
        saveToKeychain(apiKey)
    }

    // MARK: - Menu Generation

    struct MenuRequest {
        let recentSets: [WorkoutSet]       // 直近2週間
        let recentMeasurements: [BodyMeasurement]
        let targetCategory: ExerciseCategory?
    }

    struct MenuResponse {
        let templateName: String
        let exerciseIDs: [String]
        let reasoning: String
        let tokensUsed: Int
    }

    enum ClaudeError: LocalizedError {
        case missingAPIKey
        case networkError
        case apiError(Int, String)
        case parseError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:   return "APIキーが未設定です。設定タブで入力してください。"
            case .networkError:   return "ネットワークエラーが発生しました。"
            case .apiError(let c, let m): return "API エラー (\(c)): \(m)"
            case .parseError(let m): return "レスポンス解析失敗: \(m)"
            }
        }
    }

    func generateMenu(_ request: MenuRequest, exercises: [Exercise]) async throws -> MenuResponse {
        guard !apiKey.isEmpty else { throw ClaudeError.missingAPIKey }

        let prompt = buildPrompt(request: request, exercises: exercises)

        var urlRequest = URLRequest(url: apiURL)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        urlRequest.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        urlRequest.httpBody = try JSONEncoder().encode(AnthropicRequest(
            model: model,
            maxTokens: 1024,
            messages: [.init(role: "user", content: prompt)]
        ))

        let (data, response) = try await URLSession.shared.data(for: urlRequest)
        guard let http = response as? HTTPURLResponse else { throw ClaudeError.networkError }
        guard http.statusCode == 200 else {
            throw ClaudeError.apiError(http.statusCode,
                String(data: data, encoding: .utf8) ?? "unknown")
        }

        let decoded = try JSONDecoder().decode(AnthropicResponse.self, from: data)
        let text = decoded.content.first?.text ?? ""
        let tokens = decoded.usage.inputTokens + decoded.usage.outputTokens
        totalTokensUsed += tokens
        print("[ClaudeClient] tokens: \(tokens) (total: \(totalTokensUsed))")

        return try parseMenuResponse(text: text, tokensUsed: tokens)
    }

    // MARK: - Prompt

    private func buildPrompt(request: MenuRequest, exercises: [Exercise]) -> String {
        let cal = Calendar.current
        let twoWeeksAgo = Date().addingTimeInterval(-14 * 86400)
        let recentSets = request.recentSets.filter { $0.completedAt >= twoWeeksAgo }

        // Workout history grouped by day
        let byDay = Dictionary(grouping: recentSets) {
            cal.startOfDay(for: $0.completedAt)
        }
        let historyText = byDay.sorted { $0.key > $1.key }.map { (day, sets) in
            let dateStr = day.formatted(date: .abbreviated, time: .omitted)
            let lines = sets.map { "  - \($0.exercise?.name ?? "?") \(Int($0.weight))kg×\($0.reps)" }
            return "\(dateStr)\n" + lines.joined(separator: "\n")
        }.joined(separator: "\n\n")

        // Category rest days
        let restText = ExerciseCategory.allCases.map { cat in
            let lastDate = recentSets
                .filter { $0.exercise?.category == cat }
                .map(\.completedAt)
                .max()
            if let last = lastDate {
                let days = cal.dateComponents([.day], from: last, to: .now).day ?? 0
                return "\(cat.displayName): \(days)日前"
            } else {
                return "\(cat.displayName): 記録なし"
            }
        }.joined(separator: "\n")

        // Recent measurements
        let measureText: String
        if request.recentMeasurements.isEmpty {
            measureText = "データなし"
        } else {
            measureText = request.recentMeasurements.prefix(3).map { m in
                var parts: [String] = [m.date.formatted(date: .abbreviated, time: .omitted)]
                if let w = m.weight  { parts.append("体重 \(String(format: "%.1f", w))kg") }
                if let f = m.bodyFat { parts.append("体脂肪 \(String(format: "%.1f", f))%") }
                return parts.joined(separator: " / ")
            }.joined(separator: "\n")
        }

        // Available exercises grouped by category
        let exerciseText = ExerciseCategory.allCases.map { cat in
            let list = exercises.filter { $0.category == cat }
                .map { "  \($0.id): \($0.name)" }
                .joined(separator: "\n")
            return "\(cat.displayName)\n\(list)"
        }.joined(separator: "\n\n")

        let targetLine = request.targetCategory.map {
            "\n希望部位: \($0.displayName)を中心に組んでください。"
        } ?? ""

        return """
あなたは個人トレーニングコーチです。以下のデータをもとに今日のワークアウトメニューを提案してください。\(targetLine)

## 直近2週間のトレーニング履歴
\(historyText.isEmpty ? "記録なし" : historyText)

## 部位別 最終トレーニング日
\(restText)

## 最近の体組成
\(measureText)

## 出力形式（JSONのみ・他テキスト不要）
```json
{
  "templateName": "メニュー名（例: 胸・三頭 パワー系）",
  "exerciseIDs": ["bench-press", "incline-dumbbell-press"],
  "reasoning": "提案理由（2〜3文・日本語）"
}
```

## 利用可能な種目（ID: 名前）
\(exerciseText)
"""
    }

    // MARK: - Parse

    private func parseMenuResponse(text: String, tokensUsed: Int) throws -> MenuResponse {
        // JSON を抽出（Markdown コードブロックを考慮）
        let jsonString: String
        if let range = text.range(of: #"\{[\s\S]*?\}"#, options: .regularExpression) {
            jsonString = String(text[range])
        } else {
            throw ClaudeError.parseError("JSON not found in response")
        }

        struct Parsed: Decodable {
            let templateName: String
            let exerciseIDs: [String]
            let reasoning: String
        }

        do {
            let parsed = try JSONDecoder().decode(Parsed.self, from: Data(jsonString.utf8))
            return MenuResponse(
                templateName: parsed.templateName,
                exerciseIDs: parsed.exerciseIDs,
                reasoning: parsed.reasoning,
                tokensUsed: tokensUsed
            )
        } catch {
            throw ClaudeError.parseError(error.localizedDescription)
        }
    }

    // MARK: - Keychain

    private func saveToKeychain(_ value: String) {
        let data = Data(value.utf8)
        let attrs: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrAccount: keychainAccount,
            kSecValueData: data,
        ]
        SecItemDelete([kSecClass: kSecClassGenericPassword,
                       kSecAttrAccount: keychainAccount] as CFDictionary)
        SecItemAdd(attrs as CFDictionary, nil)
    }

    private func loadFromKeychain() -> String? {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrAccount: keychainAccount,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func loadFromBundle() -> String? {
        Bundle.main.object(forInfoDictionaryKey: "CLAUDE_API_KEY") as? String
    }
}

// MARK: - Codable Models

private struct AnthropicRequest: Encodable {
    let model: String
    let maxTokens: Int
    let messages: [Message]

    struct Message: Encodable {
        let role: String
        let content: String
    }

    enum CodingKeys: String, CodingKey {
        case model
        case maxTokens = "max_tokens"
        case messages
    }
}

private struct AnthropicResponse: Decodable {
    let content: [ContentBlock]
    let usage: Usage

    struct ContentBlock: Decodable {
        let text: String
    }

    struct Usage: Decodable {
        let inputTokens: Int
        let outputTokens: Int

        enum CodingKeys: String, CodingKey {
            case inputTokens = "input_tokens"
            case outputTokens = "output_tokens"
        }
    }
}
