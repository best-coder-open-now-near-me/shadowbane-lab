#include "navigation_channel.h"
#include <Windows.h>
#include <strsafe.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <vector>

using namespace wonderbane::extension;
using namespace wonderbane::extension::navigation;

namespace {
int failures = 0;
void Check(const bool ok, const char* name) {
    if (!ok) { std::cerr << name << "\n"; ++failures; }
}
std::vector<unsigned char> ReadHex(const char* path) {
    std::ifstream input(path);
    std::vector<unsigned char> result;
    std::string value;
    while (input >> value) {
        result.push_back(static_cast<unsigned char>(std::stoul(value, nullptr, 16)));
    }
    return result;
}
void PutHeader(std::vector<unsigned char>& data, FrameHeader header) {
    header.checksum = 0U;
    std::memcpy(data.data(), &header, sizeof(header));
    header.checksum = FrameChecksum(data.data(), data.size());
    std::memcpy(data.data(), &header, sizeof(header));
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    auto golden = ReadHex(argv[1]);
    if (golden.size() < sizeof(FrameHeader) + sizeof(Line)) return 3;
    FrameHeader original{};
    std::memcpy(&original, golden.data(), sizeof(original));
    const auto valid = [&](const auto& bytes, std::uint64_t now = 200U) {
        return ValidateFrame(bytes.data(), bytes.size(), 2U, 42U, 123456U, now);
    };
    Check(valid(golden) == FrameError::none, "Python-generated frame must validate in C++");
    Check(original.line_count == 1U && original.session_id == 17U,
          "shared golden schema layout");
    Line line{};
    std::memcpy(&line, golden.data() + sizeof(FrameHeader), sizeof(line));
    Check(line.start[0] == 3.0F && line.start[1] == 5.0F && line.start[2] == -4.0F,
          "golden LT/altitude/-LG layout");
    Check(valid(golden, 5000U) == FrameError::lease, "expired producer");
    Check(ValidateFrame(golden.data(), golden.size(), 4U, 42U, 123456U, 200U)
          == FrameError::sequence, "changed sequence");
    Check(ValidateFrame(golden.data(), golden.size(), 2U, 43U, 123456U, 200U)
          == FrameError::identity, "wrong pid");
    Check(ValidateFrame(golden.data(), golden.size(), 2U, 42U, 123457U, 200U)
          == FrameError::identity, "reused pid");
    for (const std::size_t offset : {48U, 128U, 160U}) {
        auto changed = golden; changed[offset] ^= 1U;
        Check(valid(changed) == FrameError::checksum, "CRC covers header, lines and capture");
    }
    auto changed = golden;
    auto header = original;
    header.live_zone_id += 1U; PutHeader(changed, header);
    Check(valid(changed) == FrameError::zone, "wrong current zone");
    header = original; header.line_count = 16385U; PutHeader(changed, header);
    Check(valid(changed) == FrameError::capacity, "oversized line array");
    header = original; header.flags |= kFrozen; header.lease_ms = 9000U;
    PutHeader(changed, header);
    Check(valid(changed, 9001U) == FrameError::none, "frozen sample with fresh lease");
    header.flags &= ~kFrozen; PutHeader(changed, header);
    Check(valid(changed, 9001U) == FrameError::stale, "live stale sample");
    changed = golden;
    line.start[1] = std::numeric_limits<float>::quiet_NaN();
    std::memcpy(changed.data() + sizeof(FrameHeader), &line, sizeof(line));
    PutHeader(changed, original);
    Check(valid(changed) == FrameError::coordinates, "nonfinite geometry");

    FILETIME creation{}, exit{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)) return 4;
    ProcessIdentity identity{GetCurrentProcessId(),
        (static_cast<std::uint64_t>(creation.dwHighDateTime) << 32U) | creation.dwLowDateTime};
    Check(StartNavigationChannel(identity) == ERROR_SUCCESS, "start real channel");
    Check(StartNavigationChannel(identity) == ERROR_ALREADY_INITIALIZED, "duplicate start");
    wchar_t name[160]{};
    (void)StringCchPrintfW(name, 160U, L"Local\\WonderBaneNavigation-%lu-%llu",
                         identity.process_id, identity.creation_filetime_utc);
    HANDLE mapping = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, name);
    void* address = mapping ? MapViewOfFile(mapping, FILE_MAP_READ | FILE_MAP_WRITE, 0U, 0U, kMappingBytes) : nullptr;
    if (address == nullptr) { StopNavigationChannel(); return 5; }
    auto buffer = std::make_unique<NavigationFrameBuffer>();
    Check(!ReadNavigationFrame(buffer.get()), "empty channel hidden");
    changed = golden; header = original;
    header.process_id = identity.process_id;
    header.process_creation = identity.creation_filetime_utc;
    header.sampled_ms = header.lease_ms = GetTickCount64();
    PutHeader(changed, header);
    std::memcpy(address, changed.data(), changed.size());
    Check(ReadNavigationFrame(buffer.get()), "read valid real channel");
    Check(ReadNavigationFrame(buffer.get()), "reuse validated frame without reparsing");
    header.session_id += 1U; PutHeader(changed, header);
    std::memcpy(address, changed.data(), changed.size());
    Check(ReadNavigationFrame(buffer.get()) && buffer->header.session_id == header.session_id,
          "new producer may restart sequence but must replace old session");
    auto* sequence = reinterpret_cast<volatile LONG*>(static_cast<unsigned char*>(address) + 12U);
    InterlockedExchange(sequence, 3);
    Check(!ReadNavigationFrame(buffer.get()), "torn update hides cached geometry");
    std::memcpy(address, changed.data(), changed.size());
    Check(ReadNavigationFrame(buffer.get()), "recover next complete frame");
    header.sequence = 4U; header.live_zone_id += 1U; PutHeader(changed, header);
    std::memcpy(address, changed.data(), changed.size());
    Check(!ReadNavigationFrame(buffer.get()), "zone change invalidates cached geometry");
    StopNavigationChannel();
    Check(!ReadNavigationFrame(buffer.get()), "stop invalidates reader");
    UnmapViewOfFile(address); CloseHandle(mapping);
    Check(StartNavigationChannel(identity) == ERROR_SUCCESS, "restart after cleanup");
    StopNavigationChannel();
    return failures ? 1 : 0;
}
