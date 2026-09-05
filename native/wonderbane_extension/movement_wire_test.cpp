#include "movement_wire.h"
#include <fstream>
#include <string>
#include <iostream>
using namespace wonderbane::extension::movement;
namespace w = wonderbane::extension::movement::wire;
template<class T> bool Load(std::ifstream& file, T& value) {
    std::string text; if (!std::getline(file, text) || text.size() != 2 * sizeof(T)) { return false; }
    auto* bytes = reinterpret_cast<unsigned char*>(&value);
    const auto digit = [](char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1; };
    for (std::size_t i = 0; i < sizeof(T); ++i) {
        const int a = digit(text[2*i]), b = digit(text[2*i+1]); if (a < 0 || b < 0) { return false; }
        bytes[i] = static_cast<unsigned char>(a * 16 + b);
    }
    return true;
}
int main(int argc, char** argv) {
    if (argc != 2) { return 1; }
    std::ifstream file(argv[1]); w::Command command{}; w::Receipt receipt{}; w::Status status{};
    if (!Load(file, command) || !Load(file, receipt) || !Load(file, status)) { return 2; }
    Grant expected{}; Settings settings{};
    if (!w::Valid(w::Verb::acquire, command) || !w::Decode(command.expected, expected)
        || !w::Decode(command.settings, settings)) { return 3; }
    if (expected.generation != 0x1020304050607080ULL || expected.scene != 0x2030405060708090ULL
        || expected.owner != Owner::automation || expected.token.worker[94] != 'w'
        || expected.token.operation[94] != 'o' || command.requested.worker[94] != 'n'
        || command.requested.operation[94] != 'p' || command.window != 0xf1234567
        || command.host.process != 1234 || command.host.generation != 27
        || command.host.creation != 0x1122334455667788ULL || command.request[0] != 0x12
        || command.request[15] != 0xf0 || command.revision != 0x3456789012345678ULL
        || command.destination.x != 1.25F || command.destination.y != -20.5F || command.destination.z != 4096.0F
        || !settings.enabled || !settings.controller || !settings.invert_camera_y || settings.keys[0] != 0x49) { return 4; }
    const auto encoded_grant = w::Encode(expected); const auto encoded_settings = w::Encode(settings);
    if (std::memcmp(&encoded_grant, &command.expected, sizeof(encoded_grant))
        || std::memcmp(&encoded_settings, &command.settings, sizeof(encoded_settings))) { return 5; }
    w::Receipt native_receipt{}; native_receipt.grant = command.expected; native_receipt.request = command.request;
    native_receipt.host = command.host; native_receipt.window = command.window; native_receipt.revision = command.revision;
    native_receipt.settings = command.settings; native_receipt.outcome = static_cast<unsigned>(Result::stale); native_receipt.flags = 7;
    if (std::memcmp(&native_receipt, &receipt, sizeof(receipt))) { return 6; }
    w::Status native_status{}; native_status.sequence = 12; native_status.process = 4321; native_status.flags = 7;
    native_status.creation = 0x2233445566778899ULL; native_status.window = command.window;
    native_status.grant = command.expected; native_status.settings = command.settings;
    native_status.revision = command.revision; native_status.tick = 987654321;
    if (std::memcmp(&native_status, &status, sizeof(status))) { return 7; }
    auto invalid = command; invalid.reserved[55] = 1; if (w::Valid(w::Verb::acquire, invalid)) { return 8; }
    invalid = command; invalid.expected.token.worker[95] = 'x'; if (w::Valid(w::Verb::acquire, invalid)) { return 9; }
    invalid = command; invalid.request = {}; if (w::Valid(w::Verb::acquire, invalid)) { return 10; }
    invalid = command; invalid.host.generation = 0; if (w::Valid(w::Verb::acquire, invalid)) { return 11; }
    invalid = command; invalid.window = 0x100000000ULL; if (w::Valid(w::Verb::acquire, invalid)) { return 12; }
    invalid = command; invalid.settings.button = 2; if (w::Valid(w::Verb::acquire, invalid)) { return 13; }
    invalid = command; invalid.expected.owner = 2; if (w::Valid(w::Verb::acquire, invalid)) { return 14; }
    invalid = command; invalid.requested = {}; invalid.destination.x = NAN;
    if (w::Valid(w::Verb::destination, invalid)) { return 15; }
    std::cout << "native/Python command, receipt, status and settings fixture verified\n";
    return 0;
}
