// ScummVM-facing instrumentation, GPL-3.0-or-later.
// No RPC dispatcher is installed by this header. An owning bridge must install
// one Controller and service its pause callback before setting the agent FD.
#ifndef FDISBULL_KYRA_SCUMMVM_HOOKS_H
#define FDISBULL_KYRA_SCUMMVM_HOOKS_H
#define FORBIDDEN_SYMBOL_ALLOW_ALL
#include "common/textconsole.h"
#include "backends/platform/null/kyra_debug_core.h"
#include "kyra/kyra_v1.h"
#include "kyra/script/script.h"
#include <cstdlib>

namespace FDisBullKyraHooks {
inline FDisBullKyra::Controller *&slot() {
    static FDisBullKyra::Controller *controller = nullptr;
    return controller;
}
inline bool requested() {
    const char *fd = std::getenv("FDISBULL_SCUMMVM_FD");
    return fd && *fd;
}
inline FDisBullKyra::Controller &get() {
    if (!slot()) error("%s", "Kyra RPC controller is not installed; launch refused");
    return *slot();
}
inline void install(FDisBullKyra::Controller &controller) {
    if (slot()) error("%s", "only one Kyra controller may own this process");
    slot() = &controller;
}
inline void profile(Kyra::KyraEngine_v1 *engine) {
    if (!engine || engine->gameFlags().platform != Common::kPlatformDOS ||
            (engine->game() != Kyra::GI_KYRA1 && engine->game() != Kyra::GI_LOL) ||
            (engine->game() == Kyra::GI_KYRA1 && engine->gameFlags().lang == Common::KO_KOR))
        error("%s", "Kyra hook profile is outside the bounded DOS EMC pilot");
}
inline void loaded(Kyra::KyraEngine_v1 *engine, const Kyra::EMCData *data) {
    if (!requested()) return;
    profile(engine);
    if (!data || !data->data || !data->ordr || (data->dataSize & 1) || (data->ordrSize & 1) ||
            data->dataSize / 2 > FDisBullKyra::Controller::kWords ||
            data->ordrSize / 2 > FDisBullKyra::Controller::kWords)
        error("%s", "unsupported EMC load extents");
    std::size_t n = 0;
    while (n < sizeof(data->filename) && data->filename[n]) ++n;
    if (n == sizeof(data->filename)) error("%s", "unterminated resource name");
    get().load(data, std::string(data->filename, n),
               std::vector<std::uint16_t>(data->data, data->data + data->dataSize / 2),
               std::vector<std::uint16_t>(data->ordr, data->ordr + data->ordrSize / 2));
}
inline void unloaded(const Kyra::EMCData *data) {
    if (requested() && data) get().unload(data);
}
inline void initialized(const Kyra::EMCState *state) {
    if (requested()) get().resetContext(state);
}
inline FDisBullKyra::Id before(Kyra::KyraEngine_v1 *engine, const Kyra::EMCState *state) {
    if (!requested()) return 0;
    profile(engine);
    if (!state || !state->dataPtr || !state->ip || !state->dataPtr->data)
        error("%s", "invalid EMC execution state");
    const auto start = reinterpret_cast<std::uintptr_t>(state->dataPtr->data);
    const auto current = reinterpret_cast<std::uintptr_t>(state->ip);
    if (current < start || current - start >= state->dataPtr->dataSize || (current - start) % 2)
        error("%s", "EMC IP is outside its DATA word buffer");
    return get().before(state->dataPtr, state, (current - start) / 2,
                        state->dataPtr->data, state->dataPtr->dataSize / 2);
}
inline void after(FDisBullKyra::Id span) {
    if (span) get().after(span);
}
inline void yield() {
    // Do not enter a half-constructed engine while graphics initializes.
    if (requested() && slot()) get().yield();
}
} // namespace FDisBullKyraHooks
#endif
