// Experimental native debugger control core. No game data or engine emulation.
// This sidecar is intended for GPL-3.0-or-later ScummVM integration.
#ifndef FDISBULL_KYRA_DEBUG_CORE_H
#define FDISBULL_KYRA_DEBUG_CORE_H
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef FDISBULL_KYRA_NO_EXCEPTIONS
#include "common/textconsole.h"
#endif

namespace FDisBullKyra {
using Id = std::uint64_t;
struct Position {
    Id resource = 0, generation = 0, word = 0, context = 0, span = 0, parent = 0;
};
struct Instruction {
    unsigned opcode = 0;
    int parameter = 0;
    unsigned words = 1;
};
struct Resource {
    Id id = 0, generation = 0;
    std::string name;
    std::vector<std::uint16_t> data, ordr;
};
struct Event {
    bool before = true;
    Position position;
    Instruction instruction;
};
struct Stop {
    std::string reason, phase;
    Position position;
    Id entered = 0, completed = 0, revision = 0;
    std::vector<Id> completedSpans;
};
struct Breakpoint { Id id, resource, generation, word; };

class Controller {
public:
    using Clock = std::chrono::steady_clock;
    using PauseHandler = std::function<void(const Stop &, Controller &)>;
    static constexpr std::size_t kWords = 262144;
    static constexpr std::size_t kTotalWords = 8 * 1024 * 1024;

    explicit Controller(PauseHandler handler, std::size_t traceCapacity = 2048)
        : _handler(std::move(handler)), _capacity(traceCapacity) {
        require(bool(_handler), "a real pause/controller handler is required");
        require(traceCapacity >= 2 && traceCapacity <= 2048, "invalid trace capacity");
    }

    Id load(const void *key, std::string name, std::vector<std::uint16_t> data,
            std::vector<std::uint16_t> ordr) {
        require(key != nullptr, "null resource key");
        require(!name.empty() && name.size() <= 255, "invalid advisory resource name");
        require(!data.empty() && data.size() <= kWords && ordr.size() <= kWords,
                "resource word budget exceeded");
        auto existing = _keys.find(key);
        Id rid = existing == _keys.end() ? 0 : existing->second;
        for (const auto &frame : _active)
            require(frame.position.resource != rid, "cannot replace an active resource");
        require(rid || _resources.size() < 256, "loaded resource count exceeded");
        std::size_t words = data.size() + ordr.size();
        for (const auto &item : _resources)
            if (item.first != rid) words += item.second.data.size() + item.second.ordr.size();
        require(words <= kTotalWords, "aggregate resource word budget exceeded");
        Id generation = rid ? _resources.at(rid).generation + 1 : 1;
        if (!rid) rid = ++_nextResource;
        _resources[rid] = {rid, generation, std::move(name), std::move(data), std::move(ordr)};
        _keys[key] = rid;
        invalidateBreakpoints(rid);
        ++_revision;
        return rid;
    }

    void unload(const void *key) {
        auto item = _keys.find(key);
        if (item == _keys.end()) return;
        Id rid = item->second;
        for (const auto &frame : _active)
            require(frame.position.resource != rid, "cannot unload an active resource");
        _resources.erase(rid);
        _keys.erase(item);
        invalidateBreakpoints(rid);
        ++_revision;
    }

    void resetContext(const void *key) {
        require(key != nullptr, "null execution context");
        for (const auto &frame : _active)
            require(_contexts.find(key) == _contexts.end() ||
                    frame.position.context != _contexts.at(key), "cannot reset active context");
        require(_contexts.count(key) || _contexts.size() < 4096, "context count exceeded");
        _contexts[key] = ++_nextContext;
    }

    static Instruction decode(const Resource &resource, Id offset) {
        require(offset < resource.data.size(), "instruction outside DATA");
        std::uint16_t word = resource.data[offset];
        Instruction out;
        out.opcode = (word >> 8) & 31;
        if (word & 0x8000) {
            out.opcode = 0; out.parameter = word & 0x7fff;
        } else if (word & 0x4000) {
            out.parameter = (word & 255) >= 128 ? int(word & 255) - 256 : int(word & 255);
        } else if (word & 0x2000) {
            require(offset + 1 < resource.data.size(), "truncated long operand");
            unsigned param = resource.data[offset + 1];
            out.parameter = param >= 32768 ? int(param) - 65536 : int(param);
            out.words = 2;
        }
        require(out.opcode < 19, "unsupported EMC core opcode");
        return out;
    }

    std::vector<std::uint8_t> read(Id rid, Id generation, bool data,
                                 std::size_t offset, std::size_t length) const {
        const Resource &resource = get(rid, generation);
        const auto &words = data ? resource.data : resource.ordr;
        require(length <= 4096 && offset <= words.size() * 2 &&
                length <= words.size() * 2 - offset, "resource read exceeds bounds");
        std::vector<std::uint8_t> result;
        result.reserve(length);
        for (std::size_t i = offset; i < offset + length; ++i)
            result.push_back(std::uint8_t(i % 2 ? words[i / 2] & 255 : words[i / 2] >> 8));
        return result;
    }

    Id addBreakpoint(Id rid, Id generation, Id word, const std::vector<std::uint8_t> &expected) {
        const auto &resource = get(rid, generation);
        Instruction instruction = decode(resource, word);
        require(expected == read(rid, generation, true, word * 2, instruction.words * 2),
                "breakpoint instruction guard mismatch");
        require(_breakpoints.size() < 4096, "breakpoint count exceeded");
        Id id = ++_nextBreakpoint;
        _breakpoints[id] = {id, rid, generation, word};
        return id;
    }
    bool removeBreakpoint(Id id) { return _breakpoints.erase(id) != 0; }
    void breakOnSyscall(unsigned id, bool enabled = true) {
        require(id <= 255, "syscall ID outside byte range");
        if (enabled) _syscalls.insert(id); else _syscalls.erase(id);
    }

    // The handler owns the stopped engine thread. It may inspect and explicitly
    // resume. Returning without a resume is a refusal, never silent execution.
    void resume(Id completedBudget, unsigned hostMs) {
        require(!_running, "execution is already running");
        require(completedBudget > 0 && completedBudget <= 1000000, "invalid dispatch budget");
        require(hostMs > 0 && hostMs <= 600000, "invalid host-time budget");
        _budget = completedBudget;
        _enteredBase = _entered; _completedBase = _completed;
        _completedSpans.clear();
        _deadline = Clock::now() + std::chrono::milliseconds(hostMs);
        _pause = false; _running = true;
    }
    void requestPause() { _pause = true; }

    Id before(const void *resourceKey, const void *contextKey, Id word,
              const std::uint16_t *liveWords, std::size_t liveCount) {
        require(_active.size() < 128, "nested EMC dispatch depth exceeded");
        auto item = _keys.find(resourceKey);
        require(item != _keys.end(), "execution uses an unregistered resource");
        if (!_contexts.count(contextKey)) resetContext(contextKey);
        const Resource &resource = _resources.at(item->second);
        Event event;
        event.position = {resource.id, resource.generation, word, _contexts.at(contextKey),
                          ++_nextSpan, _active.empty() ? 0 : _active.back().position.span};
        event.instruction = decode(resource, word);
        require(liveWords != nullptr && liveCount == resource.data.size(),
                "live DATA extent differs from load snapshot");
        for (unsigned i = 0; i < event.instruction.words; ++i)
            require(liveWords[word + i] == resource.data[word + i],
                    "live instruction differs from load snapshot");
        _active.push_back(event);
        gate("emc_before", event.position, &event.instruction);
        ++_entered;
        record(event);
        return event.position.span;
    }

    void after(Id span) {
        require(!_active.empty() && _active.back().position.span == span,
                "completion does not match the innermost dispatch");
        Event event = _active.back();
        _active.pop_back();
        event.before = false;
        ++_completed;
        if (_completedSpans.size() == 2048) _completedSpans.erase(_completedSpans.begin());
        _completedSpans.push_back(span);
        record(event);
        gate("emc_after", event.position, nullptr);
    }

    // Must also be called from the null backend's delay/event-poll paths. This
    // checks host budgets while native media/TIM callbacks are inside an opcode.
    void yield() {
        gate("backend_yield", _active.empty() ? Position{} : _active.back().position, nullptr);
    }

    const std::map<Id, Resource> &resources() const { return _resources; }
    const std::deque<Event> &events() const { return _trace; }
    Id dropped() const { return _dropped; }
    const Stop &lastStop() const { return _lastStop; }
    bool running() const { return _running; }
    void clearTrace() { _trace.clear(); _dropped = 0; }

private:
    static void require(bool good, const char *message) {
        if (!good) {
#ifdef FDISBULL_KYRA_NO_EXCEPTIONS
            error("%s", message);
#else
            throw std::runtime_error(message);
#endif
        }
    }
    const Resource &get(Id rid, Id generation) const {
        auto item = _resources.find(rid);
        require(item != _resources.end() && item->second.generation == generation,
                "stale resource identity or generation");
        return item->second;
    }
    void invalidateBreakpoints(Id rid) {
        for (auto i = _breakpoints.begin(); i != _breakpoints.end(); )
            if (i->second.resource == rid) i = _breakpoints.erase(i); else ++i;
    }
    void record(const Event &event) {
        if (_trace.size() == _capacity) { _trace.pop_front(); ++_dropped; }
        _trace.push_back(event);
        ++_revision;
    }
    void gate(const char *phase, const Position &position, const Instruction *instruction) {
        std::string reason;
        if (!_running) reason = "entry";
        else if (_pause) reason = "pause";
        else if (_completed - _completedBase >= _budget) reason = "budget";
        else if (Clock::now() >= _deadline) reason = "host_timeout";
        else if (instruction) {
            for (const auto &item : _breakpoints) {
                const auto &bp = item.second;
                if (bp.resource == position.resource && bp.generation == position.generation &&
                        bp.word == position.word) { reason = "breakpoint"; break; }
            }
            if (reason.empty() && instruction->opcode == 14 &&
                    _syscalls.count(unsigned(instruction->parameter) & 255)) reason = "syscall";
        }
        if (reason.empty()) return;
        _running = false;
        _lastStop = {reason, phase, position, _entered - _enteredBase,
                     _completed - _completedBase, ++_revision, _completedSpans};
        _handler(_lastStop, *this);
        require(_running, "controller returned without an explicit bounded resume");
    }

    PauseHandler _handler;
    std::size_t _capacity;
    std::map<const void *, Id> _keys, _contexts;
    std::map<Id, Resource> _resources;
    std::map<Id, Breakpoint> _breakpoints;
    std::set<unsigned> _syscalls;
    std::vector<Event> _active;
    std::deque<Event> _trace;
    Stop _lastStop;
    std::vector<Id> _completedSpans;
    Id _nextResource = 0, _nextContext = 0, _nextSpan = 0, _nextBreakpoint = 0;
    Id _revision = 0, _entered = 0, _completed = 0, _enteredBase = 0, _completedBase = 0;
    Id _budget = 0, _dropped = 0;
    bool _running = false;
    std::atomic<bool> _pause{false};
    Clock::time_point _deadline;
};
} // namespace FDisBullKyra
#endif
