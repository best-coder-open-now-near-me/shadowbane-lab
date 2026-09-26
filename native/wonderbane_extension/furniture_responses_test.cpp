#include "furniture_responses.cpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <thread>
namespace fr = wonderbane::extension::furniture;
namespace {
std::atomic<std::uint64_t> epoch{7};
std::atomic<unsigned> decoded{0}, processed{0}, destroyed{0}, serialized{0};
unsigned install_calls = 0, fail_at = 0, destroy_flags = 0;
DWORD decode_error = 0, process_error = 0, serialize_error = 0, destroy_error = 0;
void* last_stream = nullptr;
HANDLE decode_entered = nullptr, process_entered = nullptr, serialize_entered = nullptr, released = nullptr;
bool hold_decode = false, hold_process = false, hold_serialize = false;
bool throw_decode = false, throw_process = false, throw_serialize = false, clear_scene = false;
int failures = 0;
void Check(bool value, const char* text) { if (!value) { ++failures; std::cerr << text << '\n'; } }
void __fastcall DecodeOriginal(void*, void*, void*) {
    ++decoded; decode_error = GetLastError();
    if (hold_decode) { SetEvent(decode_entered); WaitForSingleObject(released, INFINITE); }
    SetLastError(0x5678);
    if (throw_decode) { throw std::runtime_error("native decode exception"); }
}
std::uint32_t __fastcall ProcessOriginal(void* message, void*) {
    ++processed; process_error = GetLastError();
    if (clear_scene && message) {
        auto* words = static_cast<std::uint32_t*>(message);
        words[0x9c / 4] = words[0x98 / 4];
    }
    if (hold_process) { SetEvent(process_entered); WaitForSingleObject(released, INFINITE); }
    SetLastError(0x8765);
    if (throw_process) { throw std::runtime_error("native processing exception"); }
    return 0x12345678;
}
void __fastcall SerializeOriginal(void*, void*, void* stream) {
    ++serialized; serialize_error = GetLastError(); last_stream = stream;
    if (hold_serialize) { SetEvent(serialize_entered); WaitForSingleObject(released, INFINITE); }
    SetLastError(0x2468);
    if (throw_serialize) { throw std::runtime_error("native serialization exception"); }
}
void* __fastcall DestroyOriginal(void* message, void*, unsigned flags) {
    ++destroyed; destroy_error = GetLastError(); destroy_flags = flags;
    SetLastError(0x1357); return message;
}
std::uint32_t Ptr(const void* value) { return reinterpret_cast<std::uint32_t>(value); }
const fr::Record& Last() { return fr::storage->records[(fr::storage->sequence - 1) % fr::kCapacity]; }
bool Zero(const fr::Payload& body) {
    const fr::Payload zero{}; return std::memcmp(&body, &zero, sizeof(body)) == 0;
}
struct Fixture {
    std::array<std::uint32_t, 47> message{};
    std::array<std::uint32_t, 8> socket{};
    std::array<std::uint32_t, 16> info{}, second{};
    std::array<std::uint32_t, 65> scene{}, secondary{};
    std::array<fr::Key, 65> consumed{};
    explicit Fixture(std::uintptr_t base) {
        message[0] = static_cast<std::uint32_t>(base + fr::kTable);
        message[0x60 / 4] = 2;
        message[0x68 / 4] = 10; message[0x6c / 4] = 8;
        message[0x70 / 4] = 20; message[0x74 / 4] = 8;
        message[0x94 / 4] = 0xabcdef80; // Only serialized byte 0x80 is defined.
        info[0] = static_cast<std::uint32_t>(base + fr::kFurnitureInfo);
        info[8 / 4] = 30; info[0x0c / 4] = 42;
        info[0x10 / 4] = 40; info[0x14 / 4] = 43;
        info[0x18 / 4] = 50; info[0x1c / 4] = 44;
        const std::array<float, 4> transform{1.25F, -2.5F, 3.75F, 90.0F};
        std::memcpy(info.data() + 0x20 / 4, transform.data(), sizeof(transform));
        info[0x30 / 4] = 0xfffffffe; info[0x34 / 4] = 0xabcdef01;
        info[0x38 / 4] = 0xdeadbeef; // Copy low byte, never native padding.
        second = info; second[0x10 / 4] = 41;
        scene.fill(Ptr(info.data())); secondary.fill(Ptr(second.data()));
        consumed.fill(fr::Key{60, 45});
        Bounds(0x98, scene.data(), 1, 4);
        Bounds(0xa4, secondary.data(), 1, 4);
        Bounds(0xb0, consumed.data(), 1, 8);
        socket[0] = static_cast<std::uint32_t>(base + 0x116019c);
    }
    void Bounds(unsigned offset, const void* data, unsigned count, unsigned stride) {
        const auto begin = Ptr(data);
        message[offset / 4] = begin;
        message[offset / 4 + 1] = begin + count * stride;
        message[offset / 4 + 2] = begin + count * stride;
    }
};
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
    if (++install_calls == fail_at) { return ERROR_ACCESS_DENIED; }
    return ERROR_SUCCESS;
}
}
int main(int argc, char** argv) {
    if (argc > 2 && std::strcmp(argv[1], "reader") == 0) {
        wchar_t name[160]{};
        StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.Furniture.v1.%lu.123456789",
            static_cast<unsigned long>(std::strtoul(argv[2], nullptr, 10)));
        const auto handle = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
        if (!handle) { return 2; }
        const auto* view = static_cast<const fr::Storage*>(MapViewOfFile(handle, FILE_MAP_READ, 0, 0, sizeof(fr::Storage)));
        const bool valid = view && view->sequence == 3 && view->records[2].stage == 3
            && view->records[2].decode_sequence == 1 && view->records[2].payload.scene[0].instance[0] == 40
            && view->records[2].payload.secondary[0].instance[0] == 41
            && view->records[2].payload.consumed[0][0] == 60;
        if (view) { UnmapViewOfFile(view); } CloseHandle(handle); return valid ? 0 : 3;
    }
    if (argc > 1) { fail_at = static_cast<unsigned>(std::strtoul(argv[1], nullptr, 10)); }
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1200000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!image) { return 4; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    std::array<std::uint32_t*, 4> slots{};
    std::array<std::uint32_t, 4> targets{Ptr(reinterpret_cast<void*>(&DestroyOriginal)),
        Ptr(reinterpret_cast<void*>(&ProcessOriginal)), Ptr(reinterpret_cast<void*>(&DecodeOriginal)),
        Ptr(reinterpret_cast<void*>(&SerializeOriginal))};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + fr::kTable + fr::kSlots[i]); *slots[i] = targets[i];
    }
    // Synthetic wrappers reproduce the reviewed thiscall callsites and stack cleanup.
    using Callback = void(__stdcall*)(void*, void*);
    const auto wrapper = [&](std::uintptr_t return_rva, unsigned char slot) {
        unsigned char code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,slot,0x5d,0xc2,0x08,0x00};
        auto* at = image + return_rva - 14;
        DWORD protection = 0;
        if (!VirtualProtect(at, sizeof(code), PAGE_READWRITE, &protection)) { return Callback{}; }
        std::memcpy(at, code, sizeof(code));
        if (!VirtualProtect(at, sizeof(code), PAGE_EXECUTE_READ, &protection)
            || !FlushInstructionCache(GetCurrentProcess(), at, sizeof(code))) { return Callback{}; }
        return reinterpret_cast<Callback>(at);
    };
    const auto decode = wrapper(fr::kDecoderReturn, 0x1c);
    const auto serialize = wrapper(fr::kSerializerReturn, 0x20);
    if (!decode || !serialize) { return 5; }
    const wonderbane::extension::ProcessIdentity identity{GetCurrentProcessId(), 123456789};
    Check(fr::StartBound(identity, base, slots, targets) == static_cast<DWORD>(fail_at ? ERROR_ACCESS_DENIED : ERROR_SUCCESS), "start result");
    if (fail_at) {
        for (std::size_t i = 0; i < slots.size(); ++i) { Check(*slots[i] == targets[i], "restore every partially installed slot"); }
        fr::DecodeHook(nullptr, nullptr, nullptr);
        Check(fr::ProcessHook(nullptr, nullptr) == 0x12345678, "late failed-start call-through");
        fr::SerializeHook(nullptr, nullptr, nullptr); fr::DestroyHook(nullptr, nullptr, 1);
        Check(!fr::storage && decoded == 1 && processed == 1 && serialized == 1 && destroyed == 1, "rollback closes capture only");
        fr::Stop(); VirtualFree(image, 0, MEM_RELEASE); return failures;
    }
    auto fixture = std::make_unique<Fixture>(base);
    auto& f = *fixture;
    fr::Cursor baseline{};
    Check(fr::ReadCursor(baseline) && baseline.process_id == identity.process_id
        && baseline.creation == identity.creation_filetime_utc && !baseline.sequence, "locked cursor lifetime");
    auto batch = std::make_unique<fr::Batch>();
    Check(fr::ReadAfter(baseline, *batch) && !batch->count, "empty current interval");
    SetLastError(0x1111); decode(f.message.data(), f.socket.data());
    Check(decode_error == 0x1111 && GetLastError() == 0x5678, "decoder input and native last-error retained");
    clear_scene = true; SetLastError(0x2222);
    Check(fr::ProcessHook(f.message.data(), nullptr) == 0x12345678, "native processing result retained");
    Check(process_error == 0x2222 && GetLastError() == 0x8765, "processor input and native last-error retained");
    clear_scene = false;
    Check(decoded == 1 && processed == 1 && fr::storage->sequence == 3, "one native call and three phases");
    Check(Last().flags == 7 && Last().decode_sequence == 1 && Last().scene_epoch == 7, "decode lineage survives handler mutation");
    Check(Last().payload.scene_count == 1 && f.message[0x9c / 4] == f.message[0x98 / 4], "retained copy survives handler deleting scene rows");
    Check(Last().payload.scene[0].auxiliary == fr::Key{50,44}
        && Last().payload.scene[0].floor == -2 && Last().payload.scene[0].flag38_raw == 0xef
        && Last().payload.scene[0].word34_raw == 0xabcdef01, "every serialized row field copied without padding");
    Check(Last().payload.refresh == 0x80 && Last().payload.deed == fr::Key{}
        && Last().payload.position == std::array<float,3>{}, "operation2 copies byte refresh and omits unencoded placement fields");
    wchar_t executable[MAX_PATH]{}, command[2*MAX_PATH]{};
    GetModuleFileNameW(nullptr, executable, MAX_PATH);
    StringCchPrintfW(command, 2*MAX_PATH, L"\"%s\" reader %lu", executable, GetCurrentProcessId());
    STARTUPINFOW startup{}; startup.cb = sizeof(startup); PROCESS_INFORMATION child{};
    const bool launched = CreateProcessW(executable, command, nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &startup, &child) != FALSE;
    Check(launched, "independent reader launched");
    if (launched) {
        Check(WaitForSingleObject(child.hProcess,5000) == WAIT_OBJECT_0, "reader finished");
        DWORD status = 1; GetExitCodeProcess(child.hProcess,&status); Check(status == 0,"interprocess expanded row layout");
        CloseHandle(child.hThread); CloseHandle(child.hProcess);
    }
    Check(fr::ReadAfter(baseline, *batch) && batch->count == 3, "locked copy complete interval");
    auto saved = batch->after; batch->records[2].payload.scene[0].instance = {};
    Check(Last().payload.scene[0].instance[0] == 40, "reader copy never aliases recorder");
    auto wrong = baseline; ++wrong.creation; Check(!fr::ReadAfter(wrong, *batch) && !batch->count, "foreign cursor rejected");
    wrong = saved; ++wrong.sequence; Check(!fr::ReadAfter(wrong, *batch), "future cursor rejected");
    ++fr::storage->rejected; Check(!fr::ReadAfter(saved, *batch), "rejection invalidates interval");
    Check(fr::ReadCursor(saved), "new baseline retains rejection");
    ++fr::storage->ticket_drops; Check(!fr::ReadAfter(saved, *batch), "ticket loss invalidates interval");
    --fr::storage->ticket_drops;
    const auto sequence = fr::storage->records[0].sequence; fr::storage->records[0].sequence = 99;
    baseline.rejected = 1; Check(!fr::ReadAfter(baseline, *batch) && !batch->count && !batch->after.sequence, "broken ring rejects entire copy");
    fr::storage->records[0].sequence = sequence;
    f.Bounds(0x98, f.scene.data(), 1, 4);
    fr::ProcessHook(f.message.data(), nullptr); Check(!(Last().flags & 4), "ticket consumed once");
    decode(f.message.data(), f.socket.data()); f.info[0x18 / 4]++;
    fr::ProcessHook(f.message.data(), nullptr); Check(!(Last().flags & 4), "changed auxiliary field prevents lineage"); f.info[0x18 / 4]--;
    decode(f.message.data(), f.socket.data()); SetLastError(0x3333);
    Check(fr::DestroyHook(f.message.data(), nullptr, 0xabcdef01) == f.message.data()
        && destroy_flags == 0xabcdef01 && destroy_error == 0x3333 && GetLastError() == 0x1357, "destructor ABI and error retained");
    fr::ProcessHook(f.message.data(), nullptr); Check(!(Last().flags & 4), "destruction forgets pointer reuse");
    decode(f.message.data(), f.socket.data()); ++epoch;
    fr::ProcessHook(f.message.data(), nullptr); Check(!(Last().flags & 4), "old scene ticket cannot become current response");
    auto before = fr::storage->sequence; f.socket[7] = 1;
    decode(f.message.data(), f.socket.data()); Check(fr::storage->sequence == before, "retired socket excluded"); f.socket[7] = 0;
    fr::DecodeHook(f.message.data(), nullptr, f.socket.data()); Check(fr::storage->sequence == before, "unqualified decode caller forwards without observation");
    fr::SerializeHook(f.message.data(), nullptr, f.socket.data()); Check(fr::storage->sequence == before, "unqualified serialize caller forwards without observation");
    f.message[0x60 / 4] = 3; f.message[0x70 / 4] = 0; f.message[0x74 / 4] = 0;
    f.message[0x78 / 4] = 77; f.message[0x7c / 4] = 46;
    const std::array<float,4> position{1.5F,-2.5F,3.5F,45};
    std::memcpy(f.message.data() + 0x80 / 4, position.data(), sizeof(position)); f.message[0x90 / 4] = 0xffffffff;
    f.message[0xb0 / 4] = 1; // Operation3 never reads this inactive malformed vector.
    SetLastError(0x4444); serialize(f.message.data(), f.socket.data());
    Check(serialize_error == 0x4444 && GetLastError() == 0x2468 && last_stream == f.socket.data(), "serializer ABI and error preserved");
    Check(Last().stage == 4 && Last().flags == 3 && !Last().decode_sequence
        && Last().caller_rva == fr::kSerializerReturn && Last().payload.fields == 5
        && Last().payload.deed == fr::Key{77,46} && Last().payload.floor == -1
        && Last().payload.scene_count == 1 && Last().payload.secondary_count == 1
        && !Last().payload.refresh && !Last().payload.consumed_count, "serialization is copied attempt only, not send or acceptance");
    fr::Payload body{};
    const auto invalid = [&](const char* label) {
        Check(fr::Snapshot(f.message.data(), body) == fr::Capture::invalid && Zero(body), label);
    };
    f.message[0]++; invalid("wrong message class rejected"); f.message[0]--;
    f.info[0]++; invalid("wrong scene class rejected"); f.info[0]--;
    f.second[0]++; invalid("wrong secondary class rejected"); f.second[0]--;
    const auto scene_begin = f.message[0x98 / 4];
    for (unsigned offset : {0x98U, 0xa4U}) {
        const auto old = f.message;
        f.message[offset / 4] = 0; invalid("null vector with nonnull end rejected"); f.message = old;
        f.message[offset / 4 + 1]--; invalid("misaligned vector end rejected"); f.message = old;
        f.message[offset / 4 + 2] = f.message[offset / 4]; invalid("end beyond vector capacity rejected"); f.message = old;
        f.message[offset / 4] = 0x80000000; invalid("high invalid vector rejected"); f.message = old;
    }
    f.scene[0] = 0; invalid("null furniture pointee rejected"); f.scene[0] = Ptr(f.info.data());
    f.info[0x20 / 4] = 0x7fc00000; invalid("nonfinite scene transform rejected");
    f.info[0x20 / 4] = 0x3fa00000;
    f.message[0x8c / 4] = 0x7f800000; invalid("nonfinite placement rotation rejected");
    std::memcpy(f.message.data() + 0x80 / 4, position.data(), sizeof(position));
    f.message[0x60 / 4] = 2;
    f.Bounds(0xb0, f.consumed.data(), 1, 8);
    f.message[0xb4 / 4] -= 4; invalid("misaligned consumed key stride rejected"); f.message[0xb4 / 4] += 4;
    // Inactive op2 placement fields may contain nonfinite/uninitialized data.
    f.message[0x80 / 4] = 0x7f800000;
    Check(fr::Snapshot(f.message.data(), body) == fr::Capture::valid && body.position == std::array<float,3>{}, "only operation-specific fields read");
    f.Bounds(0x98, f.scene.data(), 65, 4); f.Bounds(0xa4, f.secondary.data(), 65, 4); f.Bounds(0xb0, f.consumed.data(), 65, 8);
    f.scene[64] = 1; f.secondary[64] = 1; // These pointees must never be dereferenced.
    Check(fr::Snapshot(f.message.data(), body) == fr::Capture::valid && body.status == 7
        && body.reported_scene == 65 && body.reported_secondary == 65 && body.reported_consumed == 65
        && body.scene_count == 64 && body.secondary_count == 64 && body.consumed_count == 64, "bounded prefix preserves full reported counts and explicit truncation");
    decode(f.message.data(), f.socket.data()); fr::ProcessHook(f.message.data(), nullptr);
    Check(!(Last().flags & 4) && Last().payload.status == 7, "matching truncated prefixes cannot establish full-body lineage");
    f.Bounds(0x98, f.scene.data(), 1, 4); f.Bounds(0xa4, f.secondary.data(), 1, 4); f.Bounds(0xb0, f.consumed.data(), 1, 8);
    before = fr::storage->sequence; const auto rejected = fr::storage->rejected;
    f.message[0x60 / 4] = 4; f.message[0x98 / 4] = 1;
    decode(f.message.data(), f.socket.data()); fr::ProcessHook(f.message.data(), nullptr); serialize(f.message.data(), f.socket.data());
    Check(fr::storage->sequence == before && fr::storage->rejected == rejected, "other operations forward without invented errors or records");
    f.message[0x60 / 4] = 2; f.message[0x98 / 4] = scene_begin;
    f.info[0]++; decode(f.message.data(), f.socket.data());
    Check(!(Last().flags & 1) && Zero(Last().payload) && fr::storage->rejected == rejected + 1, "invalid decode publishes canonical gap without stale body"); f.info[0]--;
    // Native exceptions propagate; a process exception cannot synthesize a returned event.
    throw_decode = true; before = fr::storage->sequence;
    try { decode(f.message.data(), f.socket.data()); Check(false,"decoder exception swallowed"); } catch (const std::runtime_error&) {}
    throw_decode = false; Check(fr::storage->sequence == before, "throwing decoder publishes no response");
    throw_process = true;
    try { fr::ProcessHook(f.message.data(), nullptr); Check(false,"processor exception swallowed"); } catch (const std::runtime_error&) {}
    throw_process = false; Check(Last().stage == 2, "throwing processor has no fabricated return");
    throw_serialize = true;
    try { serialize(f.message.data(), f.socket.data()); Check(false,"serializer exception swallowed"); } catch (const std::runtime_error&) {}
    throw_serialize = false; Check(Last().stage == 4 && !(Last().flags & 4), "serializer exception remains attempt diagnostic only");
    // Every decode has a distinct pointer so ticket overflow is exercised, not pointer reuse.
    auto messages = std::make_unique<std::array<decltype(f.message), 65>>();
    for (auto& message : *messages) { message = f.message; decode(message.data(), f.socket.data()); }
    Check(fr::storage->ticket_drops > 0, "bounded ticket loss explicit");
    Check(fr::storage->overwritten == fr::storage->sequence - 32, "bounded ring overwrite accounting");
    Check(!fr::ReadAfter(baseline, *batch), "overrun cannot manufacture fresh baseline");
    decode_entered = CreateEventW(nullptr,TRUE,FALSE,nullptr);
    process_entered = CreateEventW(nullptr,TRUE,FALSE,nullptr);
    serialize_entered = CreateEventW(nullptr,TRUE,FALSE,nullptr);
    released = CreateEventW(nullptr,TRUE,FALSE,nullptr);
    hold_decode = true;
    std::thread crossing([&] { decode(f.message.data(), f.socket.data()); });
    Check(WaitForSingleObject(decode_entered,5000) == WAIT_OBJECT_0,"decode held"); ++epoch;
    SetEvent(released); crossing.join(); hold_decode = false;
    Check(!(Last().flags & 2),"decode spanning scene replacement is unqualified");
    ResetEvent(decode_entered); ResetEvent(released);
    hold_decode = hold_process = hold_serialize = true;
    auto* retained = static_cast<const fr::Storage*>(MapViewOfFile(fr::mapping,FILE_MAP_READ,0,0,sizeof(fr::Storage)));
    std::thread d([&] { decode(f.message.data(), f.socket.data()); });
    std::thread p([&] { fr::ProcessHook(f.message.data(),nullptr); });
    std::thread s([&] { serialize(f.message.data(), f.socket.data()); });
    Check(WaitForSingleObject(decode_entered,5000) == WAIT_OBJECT_0
        && WaitForSingleObject(process_entered,5000) == WAIT_OBJECT_0
        && WaitForSingleObject(serialize_entered,5000) == WAIT_OBJECT_0,"all callback call-throughs held");
    fr::Stop(); const auto stopped_sequence = retained ? retained->sequence : 0;
    Check(!fr::ReadCursor(saved) && !saved.process_id && !fr::ReadAfter(baseline, *batch),"stopped recorder cannot produce new diagnostic interval");
    SetEvent(released); d.join(); p.join(); s.join();
    hold_decode = hold_process = hold_serialize = false;
    Check(fr::StartBound(identity,base,slots,targets) == ERROR_ALREADY_INITIALIZED,"no replacement recorder lifetime");
    for (std::size_t i = 0; i < slots.size(); ++i) { Check(*slots[i] == targets[i],"shutdown restores every owned slot"); }
    Check(!fr::storage && retained && retained->stopped && retained->sequence == stopped_sequence,"late callbacks never publish after stop");
    if (retained) { UnmapViewOfFile(retained); }
    CloseHandle(decode_entered); CloseHandle(process_entered); CloseHandle(serialize_entered); CloseHandle(released);
    fr::Stop(); VirtualFree(image,0,MEM_RELEASE);
    if (!failures) { std::cout << "Furniture diagnostic ABI, bounded payloads, lineage, interprocess layout, native forwarding and stop safety passed.\n"; }
    return failures;
}
