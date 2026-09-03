import Foundation

/// Shared API models and configuration for the menu-bar client.
enum APIConfig {
    /// Matches docker-compose / start.sh default (`127.0.0.1:9000`).
    static let baseURL = URL(string: "http://127.0.0.1:9000")!
    static let requestTimeout: TimeInterval = 5
}

struct Stats: Codable, Equatable, Sendable {
    let applied: Int
    let interviewing: Int
    let active: Int
    let total: Int
    let submittedThisWeek: Int

    enum CodingKeys: String, CodingKey {
        case applied
        case interviewing
        case active
        case total
        case submittedThisWeek = "submitted_this_week"
    }

    /// Compact menu-bar title when the API is reachable.
    var menuBarTitle: String {
        "💼 \(applied) Applied"
    }
}

struct ApplicationPayload: Codable, Equatable, Sendable {
    var company: String
    var role: String
    var url: String?
    var status: String
    var notes: String?
    var source: String?
    var workMode: String?

    init(
        company: String,
        role: String,
        url: String? = nil,
        status: String = "applied",
        notes: String? = nil,
        source: String? = nil,
        workMode: String? = nil
    ) {
        self.company = company
        self.role = role
        self.url = url
        self.status = status
        self.notes = notes
        self.source = source
        self.workMode = workMode
    }

    enum CodingKeys: String, CodingKey {
        case company
        case role
        case url
        case status
        case notes
        case source
        case workMode = "work_mode"
    }
}

struct ApplicationResponse: Codable, Equatable, Sendable {
    let id: Int
    let company: String
    let role: String
    let url: String?
    let status: String
    let notes: String?
    let source: String
    let workMode: String
    let location: String?

    enum CodingKeys: String, CodingKey {
        case id
        case company
        case role
        case url
        case status
        case notes
        case source
        case workMode = "work_mode"
        case location
    }
}

enum APIError: LocalizedError, Equatable {
    case unreachable
    case invalidResponse
    case server(statusCode: Int, detail: String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .unreachable:
            return "Backend unreachable. Is Docker Compose running?"
        case .invalidResponse:
            return "Unexpected response from the API."
        case let .server(statusCode, detail):
            return "API error (\(statusCode)): \(detail)"
        case let .decoding(message):
            return "Failed to decode response: \(message)"
        }
    }
}
