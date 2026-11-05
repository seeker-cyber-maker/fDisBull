// Authored control-kernel tests. This executable is not ScummVM or a game VM.
#include "experimental/scummvm/kyra-scaffold/debug_core.h"
#include <cassert>
#include <iostream>
#include <thread>
using namespace FDisBullKyra;

template<typename F> static void refuses(F call) {
    bool refused = false;
    try { call(); } catch (const std::runtime_error &) { refused = true; }
    assert(refused);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    std::string test = argv[1];
    int owner = 0, context = 0, childContext = 0;
    std::vector<std::uint16_t> words{0x4101, 0x4e04, 0x4801};
    std::vector<Stop> stops;
    Controller ctrl([&](const Stop &stop, Controller &c) {
        stops.push_back(stop);
        c.resume(100, 1000);
    }, 4);
    Id resource = ctrl.load(&owner, "AUTHORED.EMC", words, {0});
    auto begin = [&](Id at) { return ctrl.before(&owner, &context, at, words.data(), words.size()); };
    auto perform = [&](Id at) { Id span = begin(at); ctrl.after(span); };

    if (test == "canonical-bytes") {
        assert(ctrl.read(resource, 1, true, 0, 6) ==
               (std::vector<std::uint8_t>{0x41, 1, 0x4e, 4, 0x48, 1}));
        assert(ctrl.read(resource, 1, false, 0, 2) == (std::vector<std::uint8_t>{0, 0}));
        refuses([&] { ctrl.read(resource, 1, true, 5, 2); });
    } else if (test == "before-after") {
        perform(0);
        assert(stops.size() == 1 && stops[0].reason == "entry");
        assert(ctrl.events().size() == 2);
        assert(ctrl.events()[0].before && !ctrl.events()[1].before);
        assert(ctrl.events()[0].position.span == ctrl.events()[1].position.span);
    } else if (test == "no-owner-resume") {
        Controller absent([](const Stop &, Controller &) {});
        absent.load(&owner, "AUTHORED.EMC", words, {0});
        refuses([&] { absent.before(&owner, &context, 0, words.data(), words.size()); });
    } else if (test == "breakpoint") {
        auto point = ctrl.addBreakpoint(resource, 1, 1, {0x4e, 4});
        perform(0); perform(1);
        assert(stops.back().reason == "breakpoint" && stops.back().position.word == 1);
        assert(ctrl.removeBreakpoint(point));
        assert(!ctrl.removeBreakpoint(point));
        refuses([&] { ctrl.addBreakpoint(resource, 1, 1, {0x4e, 3}); });
    } else if (test == "stale-generation") {
        auto point = ctrl.addBreakpoint(resource, 1, 1, {0x4e, 4});
        assert(ctrl.load(&owner, "AUTHORED.EMC", words, {0}) == resource);
        refuses([&] { ctrl.read(resource, 1, true, 0, 2); });
        assert(!ctrl.removeBreakpoint(point));
        assert(ctrl.read(resource, 2, true, 0, 2).size() == 2);
        ctrl.unload(&owner);
        refuses([&] { ctrl.read(resource, 2, true, 0, 2); });
        assert(ctrl.load(&owner, "AUTHORED.EMC", words, {0}) != resource);
    } else if (test == "live-word-guard") {
        words[0] = 0x4102;
        refuses([&] { begin(0); });
        assert(ctrl.events().empty());
    } else if (test == "long-operand") {
        std::vector<std::uint16_t> longWords{0x2e00, 4};
        ctrl.load(&owner, "AUTHORED.EMC", longWords, {0});
        longWords[1] = 5;
        refuses([&] { ctrl.before(&owner, &context, 0, longWords.data(), longWords.size()); });
        ctrl.load(&owner, "AUTHORED.EMC", {0x2e00}, {0});
        refuses([&] { ctrl.before(&owner, &context, 0, longWords.data(), 1); });
    } else if (test == "nested-completion") {
        std::vector<Stop> observed;
        Controller nested([&](const Stop &s, Controller &c) {
            observed.push_back(s); c.resume(1, 1000);
        });
        nested.load(&owner, "AUTHORED.EMC", words, {0});
        Id parent = nested.before(&owner, &context, 0, words.data(), words.size());
        Id child = nested.before(&owner, &childContext, 1, words.data(), words.size());
        nested.after(child);
        assert(observed.back().reason == "budget" && observed.back().completed == 1);
        assert(observed.back().completedSpans == std::vector<Id>{child});
        assert(observed.back().position.parent == parent);
        nested.after(parent);
        assert(observed.back().completedSpans == std::vector<Id>{parent});
    } else if (test == "syscall-break") {
        ctrl.breakOnSyscall(4);
        perform(0); perform(1);
        assert(stops.back().reason == "syscall");
        ctrl.breakOnSyscall(4, false);
        refuses([&] { ctrl.breakOnSyscall(256); });
    } else if (test == "pause-yield") {
        ctrl.yield();
        ctrl.requestPause();
        ctrl.yield();
        assert(stops.back().reason == "pause" && stops.back().phase == "backend_yield");
        assert(stops.back().completed == 0);
    } else if (test == "host-budget-yield") {
        std::vector<Stop> timedStops;
        Controller timed([&](const Stop &s, Controller &c) { timedStops.push_back(s); c.resume(1, 1); });
        timed.yield();
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        timed.yield();
        assert(timedStops.back().reason == "host_timeout");
        assert(timedStops.back().completed == 0);
    } else if (test == "trace-drop-count") {
        perform(0); perform(1);
        assert(ctrl.events().size() == 4 && ctrl.dropped() == 0);
        perform(2);
        assert(ctrl.events().size() == 4 && ctrl.dropped() == 2);
        ctrl.clearTrace();
        assert(ctrl.events().empty() && ctrl.dropped() == 0);
    } else if (test == "active-resource-and-stack") {
        Id span = begin(0);
        refuses([&] { ctrl.unload(&owner); });
        refuses([&] { ctrl.load(&owner, "AUTHORED.EMC", words, {0}); });
        refuses([&] { ctrl.resetContext(&context); });
        refuses([&] { ctrl.after(span + 1); });
        ctrl.after(span);
    } else if (test == "bounds-and-invalid-decode") {
        refuses([&] { ctrl.load(nullptr, "A", words, {0}); });
        refuses([&] { ctrl.load(&owner, "A", {}, {0}); });
        refuses([&] { ctrl.load(&owner, "A", std::vector<std::uint16_t>(Controller::kWords + 1), {}); });
        refuses([&] { ctrl.resume(0, 1); });
        refuses([&] { ctrl.resume(1, 0); });
        ctrl.load(&owner, "A", {0x1f00}, {0});
        refuses([&] { ctrl.before(&owner, &context, 0, words.data(), 1); });
    } else {
        std::cerr << "Unknown authored case\n";
        return 2;
    }
    std::cout << "PASS " << test << " (control kernel only)\n";
}
