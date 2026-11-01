import Foundation

func parse(_ value: String) -> String? { PublicIPProvider.parseIPv4(Data(value.utf8)) }
precondition(parse("203.0.113.7\n") == "203.0.113.7")
precondition(parse(" 0.0.0.0 ") == "0.0.0.0")
precondition(parse("255.255.255.255") == "255.255.255.255")
for invalid in ["", "1.2.3", "1.2.3.4.5", "256.1.2.3", "-1.2.3.4", "+1.2.3.4", "01.2.3.4", "1..3.4", "1.2.3.4 extra", "1.2.3.4\n5.6.7.8", "::1", "１.2.3.4"] {
    precondition(parse(invalid) == nil, "Accepted invalid fixture")
}
precondition(PublicIPProvider.parseIPv4(Data([0xff])) == nil)
precondition(PublicIPProvider.serviceURL.scheme == "https")
print("Public IPv4 parser checks passed")
