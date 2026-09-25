#include "combat_fence.h"
#include <fstream>
#include <iostream>
#include <string>
using namespace wonderbane::extension::combat::fence;
bool Decode(const std::string& text, Binding& b) {
    if (text.size() != 2 * sizeof(b)) { return false; }
    auto* bytes = reinterpret_cast<unsigned char*>(&b);
    auto digit = [](char c) { return c >= '0' && c <= '9' ? c - '0'
        : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1; };
    for (std::size_t i = 0; i < sizeof(b); ++i) {
        const int a = digit(text[2*i]), z = digit(text[2*i+1]);
        if (a < 0 || z < 0) { return false; }
        bytes[i] = static_cast<unsigned char>(a * 16 + z);
    }
    return true;
}
int main(int argc, char** argv) {
    if (argc != 2) { return 1; }
    if (std::string(argv[1]) == "--consumer") {
        std::cout << GetCurrentProcessId() << ' ' << Creation(GetCurrentProcess()) << std::endl;
        std::string text; Binding b{}; Ticket ticket;
        if (!std::getline(std::cin, text) || !Decode(text, b)) { return 2; }
        std::cout << (ticket.Open(b) ? "open" : "rejected") << std::endl;
        while (std::getline(std::cin, text)) {
            if (text == "enter") { std::cout << static_cast<int>(ticket.TryEnter(b)) << std::endl; }
            else if (text == "inspect") {
                State state{}; const auto result = ticket.Inspect(state);
                std::cout << static_cast<int>(result) << ' ' << static_cast<int>(state) << std::endl;
            } else if (text == "wrong-generation") {
                auto current = b; ++current.movement_generation;
                std::cout << static_cast<int>(ticket.TryEnter(current)) << std::endl;
            } else { return 3; }
        }
        return 0;
    }
    std::ifstream file(argv[1]); std::string text; Binding b{};
    if (!std::getline(file, text) || !Decode(text, b) || !Valid(b)) { return 4; }
    if (b.client_pid != 1234 || b.producer_pid != 5678 || b.client_creation != 0x1020304050607080ULL
        || b.revision != 19 || b.local_key[0] != 91 || b.target_key[0] != 92
        || b.request[0] != 1 || b.operation[31] != 5) { return 5; }
    auto changed = b; changed.state = State::entered;
    if (!Same(b, changed) || Revoked(State::entered) != State::entered_revoked
        || Revoked(State::pending) != State::revoked) { return 6; }
    changed.scene++; if (Same(b, changed)) { return 7; }
    changed = b; changed.padding[79] = 1; if (Valid(changed)) { return 8; }
    changed = b; changed.target_key[1] = 30; if (Valid(changed)) { return 9; }
    changed = b; changed.state = static_cast<State>(5); if (Valid(changed)) { return 10; }
    changed = b; changed.producer_creation = 0; if (Valid(changed)) { return 11; }
    Ticket ticket; if (ticket.Open(b)) { return 12; } // fixture is not this process lifetime
    return 0;
}
