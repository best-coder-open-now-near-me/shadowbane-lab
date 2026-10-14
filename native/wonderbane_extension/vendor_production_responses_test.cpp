#include "vendor_production_responses.cpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <thread>
namespace p = wonderbane::extension::vendor_production;
namespace {
std::atomic<std::uint64_t> epoch{7};
unsigned decoded = 0, processed = 0, destroyed = 0, serialized = 0, replacements = 0, fail_at = 0;
HANDLE entered = nullptr, released = nullptr;
bool hold_decode = false;
int failures = 0;
void Check(bool value, const char* message) { if (!value) { ++failures; std::cerr << message << '\n'; } }
void __fastcall Decode(void*, void*, void*) {
    ++decoded; SetLastError(0x5678);
    if (hold_decode) { SetEvent(entered); WaitForSingleObject(released, INFINITE); }
}
std::uint32_t __fastcall Process(void*, void*) { ++processed; SetLastError(0x8765); return 0x12345678; }
void* __fastcall Destroy(void* message, void*, unsigned) { ++destroyed; return message; }
void __fastcall Serialize(void*, void*, void*) { ++serialized; SetLastError(0x4321); }
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
bool ReadNativeMovementLifetime(NativeScene& out) noexcept {
    out = {}; out.epoch = epoch.load(); out.identity = {42, 53}; return out.epoch != 0;
}
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {
    return scene.epoch && scene.epoch == epoch.load();
}
}
DWORD ReplaceImportAddressSlot(std::uint32_t* slot, std::uint32_t expected, std::uint32_t replacement) noexcept {
    const auto prior = InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),
        static_cast<LONG>(replacement), static_cast<LONG>(expected));
    if (static_cast<std::uint32_t>(prior) != expected) { return ERROR_INVALID_DATA; }
    return ++replacements == fail_at ? ERROR_ACCESS_DENIED : ERROR_SUCCESS;
}
}
int main(int argc, char** argv) {
    if (argc > 2 && !std::strcmp(argv[1], "reader")) {
        wchar_t name[160]{};
        StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.VendorProduction.v3.%lu.123456789",
            static_cast<unsigned long>(std::strtoul(argv[2], nullptr, 10)));
        const auto handle = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
        if (!handle) { return 2; }
        const auto* view = static_cast<const p::Storage*>(MapViewOfFile(handle, FILE_MAP_READ, 0, 0, sizeof(p::Storage)));
        const bool valid = view && view->sequence == 3 && view->records[2].stage == 3
            && view->records[2].decode_sequence == 1 && view->records[2].payload.stack_count == 1;
        if (view) { UnmapViewOfFile(view); } CloseHandle(handle); return valid ? 0 : 3;
    }
    if (argc > 1) { fail_at = static_cast<unsigned>(std::strtoul(argv[1], nullptr, 10)); }
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1200000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!image) { return 4; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    std::array<std::uint32_t*, 4> slots{};
    std::array<std::uint32_t, 4> targets{reinterpret_cast<std::uint32_t>(&Destroy),
        reinterpret_cast<std::uint32_t>(&Process), reinterpret_cast<std::uint32_t>(&Decode),
        reinterpret_cast<std::uint32_t>(&Serialize)};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + p::kTable + p::kSlots[i]); *slots[i] = targets[i];
    }
    constexpr unsigned char stub[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,0x1c,0x5d,0xc2,0x08,0x00};
    auto* decode_at = image + p::kDecoderReturn - 14;
    std::memcpy(decode_at, stub, sizeof(stub)); DWORD protection = 0;
    if (!VirtualProtect(decode_at, sizeof(stub), PAGE_EXECUTE_READ, &protection)
        || !FlushInstructionCache(GetCurrentProcess(), decode_at, sizeof(stub))) { return 5; }
    using Decoder = void(__stdcall*)(void*, void*);
    const auto decode = reinterpret_cast<Decoder>(decode_at);
    const wonderbane::extension::ProcessIdentity identity{GetCurrentProcessId(), 123456789};
    Check(p::StartBound(identity, base, slots, targets) == static_cast<DWORD>(fail_at ? ERROR_ACCESS_DENIED : ERROR_SUCCESS), "start");
    if (fail_at) {
        for (std::size_t i = 0; i < slots.size(); ++i) { Check(*slots[i] == targets[i], "partial hook cleanup"); }
        p::DecodeHook(nullptr, nullptr, nullptr);
        Check(p::ProcessHook(nullptr, nullptr) == 0x12345678, "late original process");
        p::DestroyHook(nullptr, nullptr, 1);
        p::SerializeHook(nullptr, nullptr, nullptr);
        Check(!p::storage && decoded == 1 && processed == 1 && destroyed == 1 && serialized == 1,
            "failure preserves native callbacks");
        p::Stop(); return failures;
    }
    p::Cursor baseline{}; auto batch = std::make_unique<p::Batch>();
    Check(p::ReadCursor(baseline) && p::ReadAfter(baseline, *batch) && !batch->count, "empty current interval");
    std::array<std::uint32_t, 72> message{};
    std::array<std::uint32_t, 8> socket{};
    message[0] = static_cast<std::uint32_t>(base + p::kTable);
    message[0x70/4] = 8; message[0x78/4] = 2229645; message[0x7c/4] = 8;
    message[0x80/4] = 2517204; message[0x84/4] = 42;
    message[0xc0/4] = 4294925624U; message[0xc4/4] = 40;
    message[0xc8/4] = 26990; message[0xcc/4] = 0; message[0xdc/4] = 1;
    message[0xe0/4] = 0; message[0x90/4] = 10;
    socket[0] = static_cast<std::uint32_t>(base + 0x116019c);
    decode(message.data(), socket.data()); Check(GetLastError() == 0x5678, "decoder error preserved");
    Check(p::ProcessHook(message.data(), nullptr) == 0x12345678, "native return preserved");
    Check(GetLastError() == 0x8765 && decoded == 1 && processed == 1, "one call through");
    Check(p::ReadAfter(baseline, *batch) && batch->count == 3, "contiguous copied stages");
    const auto& received = batch->records[2];
    Check(received.flags == 7 && received.decode_sequence == 1 && received.scene_epoch == 7, "current single-use receive lineage");
    Check(received.payload.fields == 1 && received.payload.stack_count == 1
        && received.payload.queue_ignored == 0 && received.payload.complete == 0
        && received.payload.quantity == 10 && received.payload.item[0] == 4294925624U
        && received.payload.item_template == 26990, "normal cooking and independent stack/quantity preserved");
    if (argc > 1 && !std::strcmp(argv[1], "fixture")) {
        std::array<unsigned char, 64 + 3 * sizeof(p::Record)> bytes{};
        std::memcpy(bytes.data(), p::storage, bytes.size());
        const std::uint32_t pid = 7; const std::uint64_t creation = 11;
        std::memcpy(bytes.data() + 20, &pid, 4); std::memcpy(bytes.data() + 24, &creation, 8);
        for (auto byte : bytes) { std::printf("%02x", byte); } std::printf("\n");
        p::Stop(); VirtualFree(image, 0, MEM_RELEASE); return failures;
    }
    wchar_t executable[MAX_PATH]{}, command[2*MAX_PATH]{};
    GetModuleFileNameW(nullptr, executable, MAX_PATH);
    StringCchPrintfW(command, 2*MAX_PATH, L"\"%s\" reader %lu", executable, GetCurrentProcessId());
    STARTUPINFOW startup{}; startup.cb = sizeof(startup); PROCESS_INFORMATION child{};
    const bool launched = CreateProcessW(executable, command, nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &startup, &child) != FALSE;
    Check(launched, "independent reader");
    if (launched) {
        Check(WaitForSingleObject(child.hProcess, 5000) == WAIT_OBJECT_0, "reader finished");
        DWORD code = 1; GetExitCodeProcess(child.hProcess, &code); Check(code == 0, "interprocess layout");
        CloseHandle(child.hThread); CloseHandle(child.hProcess);
    }
    auto cursor = batch->after;
    p::ProcessHook(message.data(), nullptr);
    Check(!(p::storage->records[3].flags & 4), "ticket consumed once");
    decode(message.data(), socket.data()); ++message[0xdc/4]; p::ProcessHook(message.data(), nullptr);
    Check(!(p::storage->records[6].flags & 4), "changed body cannot inherit receive identity");
    --message[0xdc/4]; decode(message.data(), socket.data()); p::DestroyHook(message.data(), nullptr, 0);
    p::ProcessHook(message.data(), nullptr); Check(!(p::storage->records[9].flags & 4), "destroyed message loses lineage");
    std::array<std::uint32_t, 12> instance{};
    instance[0] = static_cast<std::uint32_t>(base + 0x114bb68);
    instance[4] = 26990; instance[6] = 123; instance[7] = 40;
    message[0x70/4] = 10; message[0x100/4] = reinterpret_cast<std::uint32_t>(instance.data());
    message[0x11c/4] = 1; message[0x10c/4] = 11620;
    p::Payload deposited{}; Check(p::Snapshot(message.data(), deposited) && deposited.fields == 6
        && deposited.deposited_item == p::Key{123,40} && deposited.deposited_template == p::Key{26990,0}
        && deposited.strongbox_gold == 11620, "copied deposit identity and gold");
    instance[7] = 0; Check(!p::Snapshot(message.data(), deposited), "invalid deposited item rejected"); instance[7] = 40;
    message[0x70/4] = 8; message[0x11c/4] = 0; message[0xe0/4] = 0x100;
    Check(p::Snapshot(message.data(), deposited) && deposited.complete == 1
        && deposited.queue_ignored == 0 && deposited.stack_count == 1, "completed item flags");
    message[0xe0/4] = 0x101;
    message[0xd4/4] = 300;
    Check(p::Snapshot(message.data(), deposited) && deposited.queue_ignored == 1
        && deposited.complete == 1 && deposited.seconds == 300, "ignored and complete are independent bytes");
    message[0xe0/4] = 2;
    Check(!p::Snapshot(message.data(), deposited) && deposited.rejection == 11
        && deposited.queue_flags_raw == 2, "invalid flags retained with reason"); message[0xe0/4] = 0;
    message[0xcc/4] = 40;
    Check(!p::Snapshot(message.data(), deposited), "template type is not a count"); message[0xcc/4] = 0;
    decode(message.data(), socket.data()); epoch = 8; p::ProcessHook(message.data(), nullptr);
    Check(!(p::storage->records[12].flags & 4), "old scene cannot qualify");
    auto observed = p::storage->sequence;
    message[0xcc/4] = 40;
    decode(message.data(), socket.data()); p::ProcessHook(message.data(), nullptr);
    const auto& rejected = p::storage->records[static_cast<std::size_t>(observed) % p::kCapacity];
    Check(rejected.flags == 10 && rejected.payload.rejection == 9
        && rejected.payload.item_template == 26990 && rejected.payload.template_type == 40,
        "rejected decoded body remains diagnostic without a ticket");
    Check(!(p::storage->records[static_cast<std::size_t>(observed + 1) % p::kCapacity].flags & 4),
        "rejected body cannot grant processing lineage");
    message[0xcc/4] = 0; message[0x70/4] = 1; message[0x11c/4] = 0x100;
    observed = p::storage->sequence;
    p::SerializeHook(message.data(), nullptr, socket.data());
    const auto& outgoing = p::storage->records[static_cast<std::size_t>(observed) % p::kCapacity];
    Check(serialized == 1 && GetLastError() == 0x4321 && outgoing.stage == 4
        && outgoing.flags == 3 && outgoing.decode_sequence == 0
        && outgoing.payload.quantity == 10 && outgoing.payload.multiple == 1,
        "serialized quantity copied once without receive acceptance");
    const auto rejected_before = p::storage->rejected;
    message[0x11c/4] = 0x200; p::SerializeHook(message.data(), nullptr, socket.data());
    Check(p::storage->rejected == rejected_before + 1 && serialized == 2,
        "invalid serialization preserves call-through and rejection accounting");
    message[0x70/4] = 13; message[0x11c/4] = 0;
    std::array<p::Key, 2> references{{{123, 40}, {456, 42}}};
    const auto references_begin = reinterpret_cast<std::uint32_t>(references.data());
    message[0x110/4] = references_begin;
    message[0x114/4] = references_begin + sizeof(references);
    message[0x118/4] = message[0x114/4];
    Check(p::Snapshot(message.data(), deposited) && deposited.action == 13
        && deposited.references_count == 2 && deposited.references[1] == p::Key{456,42},
        "native action 13 typed-reference vector copied");
    message[0x114/4] += 4;
    Check(!p::Snapshot(message.data(), deposited) && deposited.rejection == 15,
        "malformed reference range rejected");
    message[0x110/4] = message[0x114/4] = message[0x118/4] = 0;
    auto wrong = cursor; ++wrong.creation; Check(!p::ReadAfter(wrong, *batch), "foreign lifetime rejected");
    ++p::storage->rejected; Check(!p::ReadAfter(cursor, *batch), "decoder loss rejected");
    Check(p::ReadCursor(cursor), "fresh observation cursor retains rejection count");
    ++p::storage->ticket_drops; Check(!p::ReadAfter(cursor, *batch), "ticket loss rejected");
    for (unsigned i = 0; i < 300; ++i) { decode(message.data(), socket.data()); }
    Check(p::storage->overwritten == p::storage->sequence - static_cast<LONG64>(p::kCapacity), "bounded overwrite accounting");
    Check(!p::ReadAfter(baseline, *batch), "overrun cannot be adopted");
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr); released = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    hold_decode = true;
    std::thread late([&]{ decode(message.data(), socket.data()); });
    Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "callback held");
    p::Stop(); SetEvent(released); late.join();
    Check(!p::ReadCursor(cursor) && !p::storage, "stop invalidates observer");
    for (std::size_t i = 0; i < slots.size(); ++i) { Check(*slots[i] == targets[i], "stop removes observation hooks"); }
    Check(p::ProcessHook(message.data(), nullptr) == 0x12345678, "late callback preserves original");
    p::SerializeHook(message.data(), nullptr, socket.data());
    Check(serialized == 3 && GetLastError() == 0x4321, "late serialization preserves original");
    CloseHandle(entered); CloseHandle(released); VirtualFree(image, 0, MEM_RELEASE);
    return failures;
}
