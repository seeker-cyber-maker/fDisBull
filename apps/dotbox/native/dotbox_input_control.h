// SPDX-License-Identifier: GPL-2.0-or-later
// Emulation-thread ownership policy for the DotBox DOSBox-X overlay.
#ifndef DOSBOX_DOTBOX_INPUT_CONTROL_H
#define DOSBOX_DOTBOX_INPUT_CONTROL_H

#include <cstdint>
#include <limits>
#include <string>

namespace dosbox_agent {

struct AgentInputControlState {
    bool host = false;
    std::uint64_t generation = 0;
};

// All reads and writes belong to the emulation thread. Checking the generation
// when a queued command executes prevents a pre-handoff input from firing later.
class DotBoxInputControl {
public:
    AgentInputControlState State() const { return state_; }
    void Reset() { state_ = AgentInputControlState(); }

    bool CanInject(bool has_generation, std::uint64_t generation,
                   std::string* error) const
    {
        if (state_.host) {
            if (error) *error = "Input is owned by the host";
            return false;
        }
        if (has_generation && generation != state_.generation) {
            if (error) *error = "Input control generation changed";
            return false;
        }
        return true;
    }

    template<class Cleanup>
    bool Transfer(bool host, std::uint64_t expected_generation, bool visible,
                  Cleanup cleanup, std::string* error)
    {
        if (expected_generation != state_.generation) {
            if (error) *error = "Input control generation changed";
            return false;
        }
        if (host && !visible) {
            if (error) *error = "Host input requires a visible agent window";
            return false;
        }
        if (state_.generation == (std::numeric_limits<std::uint64_t>::max)()) {
            if (error) *error = "Input control generation exhausted";
            return false;
        }
        cleanup();
        state_.host = host;
        ++state_.generation;
        return true;
    }

    // Restore keeps the live owner, but consumes its generation before any
    // cleanup or serializer effects. Failure must never revive an old lease.
    template<class Cleanup>
    bool FenceRestore(std::uint64_t expected_generation, Cleanup cleanup,
                      std::string* error)
    {
        if (expected_generation != state_.generation) {
            if (error) *error = "Input control generation changed";
            return false;
        }
        if (state_.generation == (std::numeric_limits<std::uint64_t>::max)()) {
            if (error) *error = "Input control generation exhausted";
            return false;
        }
        ++state_.generation;
        cleanup();
        return true;
    }

private:
    AgentInputControlState state_;
};

AgentInputControlState AGENT_GetInputControlState();
bool AGENT_ChangeInputControl(bool host, std::uint64_t expected_generation,
                             std::string* error);
bool AGENT_FenceStateRestore(std::uint64_t expected_generation,
                            std::string* error);
bool AGENT_CanInjectInput(bool has_generation, std::uint64_t generation,
                          std::string* error);
void AGENT_ResetInputControl();

} // namespace dosbox_agent
#endif
