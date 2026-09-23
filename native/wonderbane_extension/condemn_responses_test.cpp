#include "condemn_responses.cpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <thread>
namespace ko = wonderbane::extension::condemn;
namespace {
std::atomic<std::uint64_t> epoch{7};
std::atomic<unsigned> decoded{0}, processed{0}, destroyed{0};
unsigned install_calls = 0, fail_at = 0;
HANDLE entered = nullptr, released = nullptr;
bool hold_decode = false, hold_process = false;
int failures = 0;
void Check(bool value, const char* text) { if (!value) { ++failures; std::cerr << text << '\n'; } }
void __fastcall DecodeOriginal(void*, void*, void*) {
    ++decoded;
    SetLastError(0x5678);
    if (hold_decode) { SetEvent(entered); WaitForSingleObject(released, INFINITE); }
}
std::uint32_t __fastcall ProcessOriginal(void*, void*) {
    ++processed;
    if (hold_process) { SetEvent(entered); WaitForSingleObject(released, INFINITE); }
    SetLastError(0x8765);
    return 0x12345678;
}
void* __fastcall DestroyOriginal(void* message, void*, unsigned) { ++destroyed; return message; }
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
        StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.Condemn.v1.%lu.123456789",
            static_cast<unsigned long>(std::strtoul(argv[2], nullptr, 10)));
        const auto handle = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
        if (!handle) { return 2; }
        const auto* view = static_cast<const ko::Storage*>(MapViewOfFile(handle, FILE_MAP_READ, 0, 0, sizeof(ko::Storage)));
        const bool valid = view && view->sequence == 3 && view->records[2].stage == 3
            && view->records[2].decode_sequence == 1 && view->records[2].payload.rows[0].nation[0] == 21;
        if (view) { UnmapViewOfFile(view); } CloseHandle(handle); return valid ? 0 : 3;
    }
    if (argc > 1) { fail_at = static_cast<unsigned>(std::strtoul(argv[1], nullptr, 10)); }
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x1200000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!image) { return 4; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    std::array<std::uint32_t*, 3> slots{};
    std::array<std::uint32_t, 3> targets{reinterpret_cast<std::uint32_t>(&DestroyOriginal),
        reinterpret_cast<std::uint32_t>(&ProcessOriginal), reinterpret_cast<std::uint32_t>(&DecodeOriginal)};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + ko::kTable + ko::kSlots[i]); *slots[i] = targets[i];
    }
    constexpr unsigned char decoder[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,0x1c,0x5d,0xc2,0x08,0x00};
    auto* decode_at = image + ko::kDecoderReturn - 14;
    std::memcpy(decode_at, decoder, sizeof(decoder));
    DWORD protection = 0;
    if (!VirtualProtect(decode_at, sizeof(decoder), PAGE_EXECUTE_READ, &protection)
        || !FlushInstructionCache(GetCurrentProcess(), decode_at, sizeof(decoder))) { return 5; }
    using Decoder = void(__stdcall*)(void*, void*);
    const auto decode = reinterpret_cast<Decoder>(decode_at);
    const wonderbane::extension::ProcessIdentity identity{GetCurrentProcessId(), 123456789};
    Check(ko::StartBound(identity, base, slots, targets) == static_cast<DWORD>(fail_at ? ERROR_ACCESS_DENIED : ERROR_SUCCESS), "start result");
    if (fail_at) {
        for (std::size_t i = 0; i < slots.size(); ++i) { Check(*slots[i] == targets[i], "restore every partially installed slot"); }
        ko::DecodeHook(nullptr, nullptr, nullptr);
        Check(ko::ProcessHook(nullptr, nullptr) == 0x12345678, "late failed-start call-through");
        ko::DestroyHook(nullptr, nullptr, 1);
        Check(!ko::storage && decoded == 1 && processed == 1 && destroyed == 1, "rollback closes capture only");
        ko::Stop(); return failures;
    }
    ko::Cursor baseline{};
    Check(ko::ReadCursor(baseline) && baseline.process_id == identity.process_id
        && baseline.creation == identity.creation_filetime_utc && !baseline.sequence, "locked cursor lifetime");
    auto batch = std::make_unique<ko::Batch>();
    Check(ko::ReadAfter(baseline, *batch) && !batch->count, "empty current interval");
    std::array<std::uint32_t, 54> message{};
    std::array<std::uint32_t, 8> socket{};
    std::array<std::uint32_t, 2> head{};
    std::array<std::uint32_t, 3> node{};
    std::array<std::uint32_t, 14> wrapper{};
    std::array<std::uint32_t, 22> entry{};
    const auto ptr = [](const void* p) { return reinterpret_cast<std::uint32_t>(p); };
    message[0] = static_cast<std::uint32_t>(base + ko::kTable);
    message[32] = 13; message[33] = 0xdeadbeef; message[36] = 0xdeadbeef;
    message[48] = 10; message[49] = 8; message[51] = 999; message[52] = ptr(head.data());
    head = {ptr(node.data()), ptr(node.data())}; node = {ptr(head.data()), ptr(head.data()), ptr(wrapper.data())};
    wrapper[0] = ptr(entry.data()); entry[0] = 5; entry[2] = 21; entry[3] = 23;
    entry[16] = 21; entry[17] = 23; entry[18] = 0xee010000;
    socket[0] = static_cast<std::uint32_t>(base + 0x116019c);
    decode(message.data(), socket.data());
    Check(GetLastError() == 0x5678, "native decoder error retained");
    Check(ko::ProcessHook(message.data(), nullptr) == 0x12345678, "native processing result retained");
    Check(GetLastError() == 0x8765, "native processor error retained");
    Check(decoded == 1 && processed == 1 && ko::storage->sequence == 3, "one native call and three stages");
    const auto& record = ko::storage->records[2];
    Check(record.flags == 7 && record.decode_sequence == 1 && record.scene_epoch == 7, "decode identity survives processing");
    Check(record.payload.scope == 0 && record.payload.character[0] == 0, "absent scope and keys never leak stale bytes");
    Check(record.payload.rows[0].nation == ko::Key{21,23} && record.payload.rows[0].flags == 0x10000, "row identity and flags exclude padding");
    Check(record.payload.reported_count == 999 && record.payload.row_count == 1, "wire counter is not assumed to be row count");
    wchar_t executable[MAX_PATH]{}, command[2*MAX_PATH]{};
    GetModuleFileNameW(nullptr, executable, MAX_PATH);
    StringCchPrintfW(command, 2*MAX_PATH, L"\"%s\" reader %lu", executable, GetCurrentProcessId());
    STARTUPINFOW startup{}; startup.cb = sizeof(startup); PROCESS_INFORMATION child{};
    const bool launched = CreateProcessW(executable, command, nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &startup, &child) != FALSE;
    Check(launched, "independent reader launched");
    if (launched) {
        Check(WaitForSingleObject(child.hProcess,5000)==WAIT_OBJECT_0, "reader finished");
        DWORD status = 1; GetExitCodeProcess(child.hProcess,&status); Check(status==0,"interprocess row layout");
        CloseHandle(child.hThread);CloseHandle(child.hProcess);
    }
    Check(ko::ReadAfter(baseline, *batch) && batch->count == 3 && batch->after.sequence == 3,
        "locked copy returns complete contiguous interval");
    const auto saved = batch->after;
    batch->records[2].payload.state = 1;
    Check(ko::storage->records[2].payload.state == 0, "reader copy does not alias recorder memory");
    auto wrong = baseline; ++wrong.creation;
    Check(!ko::ReadAfter(wrong, *batch) && !batch->count && !batch->after.sequence, "cross-process cursor rejected");
    wrong = saved; ++wrong.sequence;
    Check(!ko::ReadAfter(wrong, *batch), "future cursor rejected");
    ++ko::storage->rejected;
    Check(!ko::ReadAfter(saved, *batch), "new rejection invalidates interval");
    ko::Cursor fresh{};
    Check(ko::ReadCursor(fresh) && fresh.rejected == 1 && ko::ReadAfter(fresh, *batch),
        "fresh baseline retains historical rejection");
    ++ko::storage->ticket_drops;
    Check(!ko::ReadAfter(fresh, *batch), "new ticket loss invalidates interval");
    --ko::storage->ticket_drops;
    const auto original_sequence = ko::storage->records[0].sequence;
    ko::storage->records[0].sequence = 99;
    baseline.rejected = 1;
    Check(!ko::ReadAfter(baseline, *batch) && !batch->count, "corrupt ring slot rejected without partial output");
    ko::storage->records[0].sequence = original_sequence;
    ko::ProcessHook(message.data(),nullptr);
    Check(!(ko::storage->records[3].flags & 4), "decode ticket consumed once");
    decode(message.data(),socket.data());
    entry[16] = 22;
    ko::ProcessHook(message.data(),nullptr);
    Check(!(ko::storage->records[6].flags & 4), "changed payload cannot inherit ticket");
    entry[16] = 21;
    decode(message.data(),socket.data()); ko::DestroyHook(message.data(),nullptr,0);
    ko::ProcessHook(message.data(),nullptr);
    Check(!(ko::storage->records[9].flags & 4), "destroyed message cannot carry old receive identity");
    ko::Payload invalid{}; node[1] = 0;
    Check(!ko::Snapshot(message.data(),invalid),"broken list parent rejected"); node[1] = ptr(head.data());
    node[0] = ptr(node.data()); Check(!ko::Snapshot(message.data(),invalid),"cyclic list rejected"); node[0] = ptr(head.data());
    decode(message.data(),socket.data()); epoch = 8;
    ko::ProcessHook(message.data(),nullptr);
    Check(!(ko::storage->records[12].flags & 4), "queued old epoch never becomes current response");
    const auto before = ko::storage->sequence; socket[7] = 1;
    decode(message.data(),socket.data()); Check(ko::storage->sequence==before,"retired socket excluded"); socket[7]=0;
    for (unsigned i=0;i<35;++i) { decode(message.data(),socket.data()); }
    Check(ko::storage->overwritten==ko::storage->sequence-32,"bounded ring overwrite accounting");
    Check(!ko::ReadAfter(baseline, *batch), "overrun cannot become new baseline");
    entered=CreateEventW(nullptr,TRUE,FALSE,nullptr); released=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    hold_decode=true;
    std::thread crossing([&]{decode(message.data(),socket.data());});
    Check(WaitForSingleObject(entered,5000)==WAIT_OBJECT_0,"decode held"); epoch=9;
    SetEvent(released);crossing.join();hold_decode=false;
    const auto crossed=ko::storage->sequence;
    Check(!(ko::storage->records[(crossed-1)%32].flags&2),"decode spanning replacement epoch is unqualified");
    ResetEvent(entered);ResetEvent(released);hold_process=true;
    auto* retained=static_cast<const ko::Storage*>(MapViewOfFile(ko::mapping,FILE_MAP_READ,0,0,sizeof(ko::Storage)));
    std::thread closing([&]{ko::ProcessHook(message.data(),nullptr);});
    Check(WaitForSingleObject(entered,5000)==WAIT_OBJECT_0,"processing held");
    ko::Stop();
    Check(!ko::ReadCursor(fresh) && !fresh.process_id && !ko::ReadAfter(saved, *batch), "stopped recorder cannot produce proof");
    const auto stopped_sequence=retained?retained->sequence:0;
    SetEvent(released);closing.join();hold_process=false;
    Check(ko::StartBound(identity,base,slots,targets)==ERROR_ALREADY_INITIALIZED,"no replacement generation");
    for(std::size_t i=0;i<slots.size();++i){Check(*slots[i]==targets[i],"shutdown restores slots");}
    Check(!ko::storage && retained && retained->stopped && retained->sequence==stopped_sequence,"late callback cannot publish after closure");
    if(retained){UnmapViewOfFile(retained);}CloseHandle(entered);CloseHandle(released);
    ko::Stop();VirtualFree(image,0,MEM_RELEASE);return failures;
}
