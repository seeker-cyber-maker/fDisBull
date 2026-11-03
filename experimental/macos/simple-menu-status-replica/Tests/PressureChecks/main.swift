import Foundation
func check(_ value: MemoryMood.Pressure?, _ expected: MemoryMood) {
    precondition(MemoryMood.from(pressure: value) == expected)
}
check(nil, .unknown)
check(.normal, .relaxed)
check(.warning, .concerned)
check(.critical, .stressed)
check(.normal, .relaxed) // recovery after critical
precondition(MemoryMood.estimated(total: 100, free: 5, inactive: 25, purgeable: 0) == .relaxed)
precondition(MemoryMood.estimated(total: 100, free: 5, inactive: 10, purgeable: 0) == .concerned)
precondition(MemoryMood.estimated(total: 100, free: 5, inactive: 5, purgeable: 0) == .stressed)
precondition(MemoryMood.estimated(total: 0, free: 0, inactive: 0, purgeable: 0) == .unknown)
print("Memory pressure and startup estimate checks passed")
