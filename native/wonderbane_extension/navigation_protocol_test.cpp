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
    if (argc != 3) return 2;
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
    const auto evidence = [&](const auto& bytes, std::uint64_t now = 5000U) {
        return ValidateEvidenceFrame(bytes.data(), bytes.size(), 2U, 42U, 123456U, now);
    };
    Check(evidence(golden) == FrameError::none, "expired capture remains structurally valid");
    auto bad_capture = golden; bad_capture.back() ^= 1U;
    Check(evidence(bad_capture) == FrameError::checksum, "stale evidence still requires CRC");
    const auto control_bytes = ReadHex(argv[2]);
    if (control_bytes.size() != sizeof(ControlFrame)) return 6;
    ControlFrame controls{};
    std::memcpy(&controls, control_bytes.data(), sizeof(controls));
    Check(ValidateControls(controls, 2U, original), "Python-generated panel controls validate in C++");
    auto bad_controls = controls; bad_controls.sequence = 3U;
    Check(!ValidateControls(bad_controls, 3U, original), "torn panel controls rejected");
    bad_controls = controls; bad_controls.process_creation += 1U;
    Check(!ValidateControls(bad_controls, 2U, original), "controls cannot target a reused pid");
    bad_controls = controls; bad_controls.flags ^= 1U;
    Check(!ValidateControls(bad_controls, 2U, original), "controls require complete checksum");
    auto changed = golden;
    auto header = original;
    header.live_zone_id += 1U; PutHeader(changed, header);
    Check(valid(changed) == FrameError::zone, "wrong current zone");
    Check(evidence(changed) == FrameError::none, "changed zone remains projected evidence only");
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
    Check(ReadNavigationEvidence(buffer.get()) && !buffer->live_placement,
          "zone change retains capture but never world placement");
    Check((buffer->presentation.flags & kEnabled) == 0U,
          "persistent capture requires a panel with a hide control");
    const auto publish_controls = [&]() {
        controls.checksum = 0U;
        controls.checksum = FrameChecksum(&controls, sizeof(controls));
        std::memcpy(static_cast<unsigned char*>(address) + kMaximumFrameBytes,
                    &controls, sizeof(controls));
    };
    controls.process_id = identity.process_id;
    controls.process_creation = identity.creation_filetime_utc;
    controls.session_id = header.session_id;
    controls.layer_mask = kTrailLayer;
    publish_controls();
    Check(ReadNavigationEvidence(buffer.get()) && !buffer->live_placement
        && (buffer->presentation.flags & kEnabled) != 0U
        && buffer->presentation.layer_mask == kTrailLayer,
        "panel controls a captured map without renewing world placement");
    controls.sequence += 2U; controls.flags = 0U; publish_controls();
    Check(ReadNavigationEvidence(buffer.get()) && (buffer->presentation.flags & kEnabled) == 0U,
          "hide applies immediately after the producer exits");
    controls.sequence += 2U; controls.flags = 1U; publish_controls();
    header.sequence += 2U; header.live_zone_id = header.zone_id;
    header.flags |= kFrozen;
    header.sampled_ms = header.lease_ms = GetTickCount64() - 5000U;
    PutHeader(changed, header); std::memcpy(address, changed.data(), changed.size());
    Check(!ReadNavigationFrame(buffer.get()), "expired capture cannot authorize live rendering");
    Check(ReadNavigationEvidence(buffer.get()) && !buffer->live_placement
        && (buffer->presentation.flags & kEnabled) != 0U,
        "completed run's capture remains visible without a producer");
    controls.session_id += 1U; controls.sequence += 2U; publish_controls();
    Check(ReadNavigationEvidence(buffer.get()) && (buffer->presentation.flags & kEnabled) == 0U,
          "another session cannot reveal or control stale capture");
    header.sequence += 2U; PutHeader(changed, header); changed.back() ^= 1U;
    std::memcpy(address, changed.data(), changed.size());
    Check(!ReadNavigationEvidence(buffer.get()), "corrupt historical evidence is hidden");
    StopNavigationChannel();
    Check(!ReadNavigationFrame(buffer.get()), "stop invalidates reader");
    Check(!ReadNavigationEvidence(buffer.get()), "stop invalidates historical evidence reader");
    UnmapViewOfFile(address); CloseHandle(mapping);
    Check(StartNavigationChannel(identity) == ERROR_SUCCESS, "restart after cleanup");
    StopNavigationChannel();
    return failures ? 1 : 0;
}
