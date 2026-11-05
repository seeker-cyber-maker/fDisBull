// Authored native transport driver, NOT ScummVM and NOT a Z-machine emulator.
// Calls the same C++ bridge hooks with scripted events. No opcode is executed.
#include "experimental/scummvm/zcode/agent.h"
#include <fstream>
#include <iterator>
#include <thread>

int main(int argc, char **argv) {
    std::string directory;
    for (int i=1; i<argc; ++i) {
        const std::string arg(argv[i]);
        if (arg.find("--path=")==0) directory=arg.substr(7);
    }
    std::ifstream file(directory+"/story.z3",std::ios::binary);
    if (!file) return 40;
    std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
    if (bytes.size()<1024) return 41;
    const size_t declared=(size_t(bytes[26])<<8|bytes[27])*2;
    const auto mode=bytes[100];
    if (mode==1) bytes[800]^=1; // Source drift must fail complete readback.
    auto &a=FDisBullZCode::agent();
    a.loaded(bytes.data(),declared);
    if (!a.enabled()) return 42;
    auto first=a.before(1024);
    a.character('A',0);
    bytes[80]=7; // Authored mutation, not instruction semantics.
    a.after(first,1025);
    auto second=a.before(1025);
    if (mode==2) {
        // Scripted nested dispatch tests count versus outer-call completion.
        auto nested=a.before(1050);
        a.character('N',0);
        a.after(nested,1051);
    }
    a.after(second,1026);
    if (mode==3) {
        for (int i=0;i<2200;++i) { auto id=a.before(1030); a.after(id,1030); }
    }
    if (mode==4) {
        // A CPU callback that never yields requires the parent's hard deadline.
        for (;;) std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    if (mode==5) {
        for (int i=0;i<100;++i) {
            auto id=a.before(1030);
            std::this_thread::sleep_for(std::chrono::milliseconds(4));
            a.after(id,1030);
        }
    }
    for (int i=0;i<3;++i) {
        auto id=a.before(1040);
        std::string command=a.input("line",32,0);
        a.character('[',0);
        for (unsigned char c:command) a.character(c,0);
        a.character(']',0); a.character('\n',0);
        a.character('S',1); // Separate status window, not narrative.
        a.after(id,1041);
    }
    a.exited(1041);
}
