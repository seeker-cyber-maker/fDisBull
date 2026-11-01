import Foundation

/// An explicit lookup through ipify (https://www.ipify.org/). The service sees
/// the request's public address. Creating this provider makes no request;
/// the dashboard starts its first request when Network Info becomes visible.
public final class PublicIPProvider {
    public static let serviceName = "ipify"
    public static let serviceURL = URL(string: "https://api.ipify.org?format=text")!

    public enum LookupError: Error, Equatable {
        case network
        case unexpectedResponse
        case invalidAddress
    }

    public init() {}

    /// Strictly parse one IPv4 address, allowing surrounding whitespace only.
    public static func parseIPv4(_ data: Data) -> String? {
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        let address = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let parts = address.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return nil }
        for part in parts {
            guard (1...3).contains(part.utf8.count),
                  part.utf8.allSatisfy({ (48...57).contains($0) }),
                  !(part.count > 1 && part.first == "0"),
                  let value = UInt8(part) else { return nil }
            _ = value
        }
        return address
    }

    /// Explicitly starts a request. Each completion is either a new address or
    /// an error; this provider never caches an earlier success or logs it.
    public func fetch(completion: @escaping (Result<String, LookupError>) -> Void) {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 5
        configuration.timeoutIntervalForResource = 10
        let session = URLSession(configuration: configuration)
        var request = URLRequest(url: Self.serviceURL)
        request.timeoutInterval = 5
        request.cachePolicy = .reloadIgnoringLocalCacheData
        session.dataTask(with: request) { data, response, error in
            defer { session.finishTasksAndInvalidate() }
            guard error == nil else { completion(.failure(.network)); return }
            guard let response = response as? HTTPURLResponse, response.statusCode == 200,
                  let data = data, data.count <= 64 else {
                completion(.failure(.unexpectedResponse)); return
            }
            guard let address = Self.parseIPv4(data) else {
                completion(.failure(.invalidAddress)); return
            }
            completion(.success(address))
        }.resume()
    }
}
