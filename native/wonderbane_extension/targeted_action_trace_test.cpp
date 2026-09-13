#include "targeted_action_trace.cpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <thread>

namespace we = wonderbane::extension;
namespace {
bool fail_install = false;
std::atomic<std::uint64_t> epoch{7};
std::atomic<unsigned> calls{0};
HANDLE entered = nullptr, released = nullptr;
void __fastcall Original(void*, void*, void*) {
    ++calls;
    if (entered) { SetEvent(entered); WaitForSingleObject(released, INFINITE); }
}
int failures = 0;
void Check(bool value, const char* text) { if (!value) { ++failures; std::cerr << text << '\n'; } }
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
bool ReadNativeMovementLifetime(NativeScene& out) noexcept {
    out = {}; out.epoch = epoch.load(); out.identity = {1901199, 53}; return out.epoch != 0;
}
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {
    return scene.epoch != 0 && scene.epoch == epoch.load();
}
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot, std::uint32_t expected, std::uint32_t replacement) noexcept {
    const auto previous = InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),
        static_cast<LONG>(replacement), static_cast<LONG>(expected));
    if (static_cast<std::uint32_t>(previous) != expected) { return ERROR_INVALID_DATA; }
    if (fail_install) { fail_install = false; return ERROR_ACCESS_DENIED; }
    return ERROR_SUCCESS;
}
}
int main(int argc, char** argv) {
    if (argc > 2 && std::strcmp(argv[1], "reader") == 0) {
        wchar_t name[160]{};
        StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.TargetedAction.v2.%lu.123456789",
            static_cast<unsigned long>(std::strtoul(argv[2], nullptr, 10)));
        const auto handle = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
        if (!handle) { return 2; }
        const auto* view = static_cast<const we::Storage*>(MapViewOfFile(handle, FILE_MAP_READ, 0, 0, sizeof(we::Storage)));
        const bool valid = view && view->write_sequence == 257 && view->overwritten == 1
            && view->records[0].committed_sequence == 257
            && view->records[0].fields[0] == 2392387 && view->records[0].fields[2] == 1901199;
        if (view) { UnmapViewOfFile(view); }
        CloseHandle(handle);
        return valid ? 0 : 3;
    }
    const bool rollback = argc > 1 && std::strcmp(argv[1], "rollback") == 0;
    we::ProcessIdentity identity{GetCurrentProcessId(), 123456789};
    // Executable fixture for the reviewed x86 virtual-call ABI. The return PC
    // matches the production guard; this runs TracedDeserialize, not Observe.
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1161000,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!image) { return 4; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    auto& slot = *reinterpret_cast<std::uint32_t*>(image + we::slot_rva);
    slot = reinterpret_cast<std::uint32_t>(&Original);
    constexpr unsigned char decoder_code[]{
        0x55, 0x8b, 0xec, 0x8b, 0x4d, 0x08, 0x8b, 0x01,
        0xff, 0x75, 0x0c, 0xff, 0x50, 0x1c, 0x5d, 0xc2, 0x08, 0x00};
    auto* decoder_address = image + we::decoder_return_rva - 14;
    std::memcpy(decoder_address, decoder_code, sizeof(decoder_code));
    DWORD protection = 0;
    if (!VirtualProtect(decoder_address, sizeof(decoder_code), PAGE_EXECUTE_READ, &protection)
        || !FlushInstructionCache(GetCurrentProcess(), decoder_address, sizeof(decoder_code))) { return 5; }
    using Decoder = void(__stdcall*)(void*, void*);
    const auto decode = reinterpret_cast<Decoder>(decoder_address);
    const auto target = reinterpret_cast<we::Deserialize>(&Original);
    fail_install = rollback;
    Check(we::StartBound(identity, base, &slot, target)
        == static_cast<DWORD>(rollback ? ERROR_ACCESS_DENIED : ERROR_SUCCESS), "start result");
    if (rollback) {
        Check(slot == reinterpret_cast<std::uint32_t>(&Original), "rollback restores slot");
        we::TracedDeserialize(nullptr, nullptr, nullptr);
        Check(calls == 1 && we::storage == nullptr, "late rollback callback preserves call-through");
        we::StopTargetedActionTrace();
        return failures;
    }
    std::array<std::uint32_t, 48> message{};
    message[0] = static_cast<std::uint32_t>(base) + static_cast<std::uint32_t>(we::message_vtable_rva);
    message[32] = 2392387; message[33] = 53;
    message[34] = 1901199; message[35] = 53;
    for (unsigned i = 36; i < 48; ++i) { message[i] = 0xdeadbeef; }
    message[36] = 0; message[40] = 0;
    std::uint32_t stream = static_cast<std::uint32_t>(base) + static_cast<std::uint32_t>(we::socket_vtable_rva);
    const auto caller = base + we::decoder_return_rva;
    we::Observe(message.data(), &stream, caller + 1);
    Check(we::storage->write_sequence == 0, "exclude other callers");
    ++stream; we::Observe(message.data(), &stream, caller); --stream;
    Check(we::storage->write_sequence == 0, "exclude replay/non-socket streams");
    decode(message.data(), &stream);
    Check(calls == 1, "native-style decoder calls original once");
    const auto& record = we::storage->records[0];
    Check(record.committed_sequence == 1 && record.fields[0] == 2392387
        && record.fields[2] == 1901199, "retain original participant keys");
    Check(record.fields[5] == 0 && record.fields[7] == 0 && record.fields[9] == 0
        && record.fields[11] == 0,
        "absent payloads never expose stale bytes");
    Check(record.fields[12] == 7 && record.fields[13] == 0
        && record.fields[14] == 1901199 && record.fields[15] == 53,
        "native decode carries existing watch identity");
    for (unsigned i = 0; i < 256; ++i) { we::Observe(message.data(), &stream, caller); }
    Check(we::storage->write_sequence == 257 && we::storage->overwritten == 1, "bounded ring accounting");
    wchar_t executable[MAX_PATH]{}, command[2 * MAX_PATH]{};
    GetModuleFileNameW(nullptr, executable, MAX_PATH);
    StringCchPrintfW(command, 2 * MAX_PATH, L"\"%s\" reader %lu", executable, GetCurrentProcessId());
    STARTUPINFOW startup{}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION child{};
    const bool launched = CreateProcessW(executable, command, nullptr, nullptr, FALSE,
        CREATE_NO_WINDOW, nullptr, nullptr, &startup, &child) != FALSE;
    Check(launched, "independent reader process starts");
    if (launched) {
        Check(WaitForSingleObject(child.hProcess, 5000) == WAIT_OBJECT_0, "independent reader finishes");
        DWORD status = 1; GetExitCodeProcess(child.hProcess, &status);
        Check(status == 0, "real interprocess publication layout and payload");
        CloseHandle(child.hThread); CloseHandle(child.hProcess);
    }
    auto* retained = static_cast<const we::Storage*>(MapViewOfFile(we::mapping, FILE_MAP_READ, 0, 0, sizeof(we::Storage)));
    Check(retained != nullptr, "reader view");
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    released = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::thread crossing([&] { decode(message.data(), &stream); });
    Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "decode held across epoch change");
    epoch = 8;
    SetEvent(released); crossing.join();
    const auto& crossed = we::storage->records[1];
    Check(crossed.committed_sequence == 258 && crossed.fields[12] == 0
        && crossed.fields[13] == 0 && crossed.fields[14] == 0 && crossed.fields[15] == 0,
        "old decode cannot inherit replacement watch");
    ResetEvent(entered); ResetEvent(released);
    std::thread callback([&] { decode(message.data(), &stream); });
    Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "callback reached original");
    we::StopTargetedActionTrace();
    Check(slot == reinterpret_cast<std::uint32_t>(&Original) && we::storage == nullptr, "production stop closes publication");
    Check(we::StartBound(identity, base, &slot, target) == ERROR_ALREADY_INITIALIZED, "no replacement generation");
    SetEvent(released); callback.join();
    we::StopTargetedActionTrace();
    Check(calls == 3, "held callback completes exactly once");
    if (retained) {
        Check(retained->stopped == 1 && retained->write_sequence == 258, "closed reader cannot receive late publication");
        UnmapViewOfFile(retained);
    }
    CloseHandle(entered); CloseHandle(released);
    VirtualFree(image, 0, MEM_RELEASE);
    return failures;
}
