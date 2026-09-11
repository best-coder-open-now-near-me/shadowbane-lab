#include "movement_boundary_trace.h"
#include <atomic>
#include <cstring>
#include <iostream>
#include <fstream>
#include <thread>

namespace we = wonderbane::extension;
namespace wonderbane::extension {
DWORD StartMovementBoundaryTraceForTesting(const ProcessIdentity&, std::uint32_t*, std::uint32_t) noexcept;
DWORD StartNativeMovementUpdatesForTesting(const ProcessIdentity&, NativeMovementUpdate, std::uint32_t*, std::uint32_t) noexcept;
const MovementBoundaryTrace* MovementBoundaryTraceForTesting() noexcept;
}
namespace {
using Update = std::uint32_t(__thiscall*)(void*, double);
HANDLE entered = nullptr, release_call = nullptr;
HANDLE install_entered = nullptr, install_release = nullptr;
bool hold_install = false;
std::atomic<int> calls{0}, movement_calls{0};
HANDLE movement_entered = nullptr, movement_release = nullptr;
bool hold_movement = false;
void Movement(void* receiver, double dt) noexcept;
std::atomic<bool> forwarded{true};
bool fail_after_install = false, failure_injected = false;
std::thread held;
constexpr auto result_value = 0x13579BDFU;
std::uint32_t __fastcall Original(void* receiver, void*, double dt) {
    if (reinterpret_cast<std::uintptr_t>(receiver) != 0x123450 || dt != 0.125) { forwarded=false; }
    ++calls; SetEvent(entered);
    (void)WaitForSingleObject(release_call,5000);
    return result_value;
}
bool Call(std::uint32_t address) {
    return reinterpret_cast<Update>(address)(reinterpret_cast<void*>(0x123450),0.125) == result_value;
}
void Movement(void* receiver, double dt) noexcept {
    if (reinterpret_cast<std::uintptr_t>(receiver) != 0x123450 || dt != 0.125) { forwarded = false; }
    ++movement_calls;
    if (hold_movement) {
        SetEvent(movement_entered);
        if (WaitForSingleObject(movement_release, 5000) != WAIT_OBJECT_0) { forwarded = false; }
    }
}
int failures=0;
void Check(bool ok,const char* message) { if (!ok) { ++failures; std::cerr << message << '\n'; } }
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
DWORD ReplaceImportAddressSlot(std::uint32_t* slot,std::uint32_t expected,std::uint32_t replacement) noexcept {
    const auto previous=InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),
        static_cast<LONG>(replacement),static_cast<LONG>(expected));
    if (static_cast<std::uint32_t>(previous)!=expected) { return ERROR_INVALID_DATA; }
    if (hold_install) {
        hold_install=false;
        SetEvent(install_entered);
        if (WaitForSingleObject(install_release,5000)!=WAIT_OBJECT_0) { forwarded=false; }
    }
    if (fail_after_install && !failure_injected) {
        failure_injected=true;
        held=std::thread([replacement] { if (!Call(replacement)) { forwarded=false; } });
        if (WaitForSingleObject(entered,5000)!=WAIT_OBJECT_0) { forwarded=false; }
        return ERROR_ACCESS_DENIED;
    }
    return ERROR_SUCCESS;
}
}
int main(int argc,char** argv) {
    fail_after_install = argc > 1 && (std::strcmp(argv[1], "startup-failure") == 0
        || std::strcmp(argv[1], "movement-startup-failure") == 0);
    SetEnvironmentVariableW(L"WONDERBANE_MOVEMENT_TRACE",nullptr);
    FILETIME creation{},exit{},kernel{},user{};
    Check(GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user)!=FALSE,"process identity");
    const we::ProcessIdentity identity{GetCurrentProcessId(),
        (static_cast<std::uint64_t>(creation.dwHighDateTime)<<32)|creation.dwLowDateTime};
    Check(we::StartMovementBoundaryTrace(identity)==ERROR_SUCCESS
        && !we::MovementBoundaryTraceForTesting(),"disabled creates no mapping or hook");
    SetEnvironmentVariableW(L"WONDERBANE_MOVEMENT_TRACE",L"1");
    Check(we::StartMovementBoundaryTrace(identity)==ERROR_NOT_SUPPORTED
        && !we::MovementBoundaryTraceForTesting(),"unreviewed binding cannot install");
    entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    release_call=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    Check(entered && release_call,"test synchronization");
    auto slot=reinterpret_cast<std::uint32_t>(&Original);
    auto stale=identity; ++stale.creation_filetime_utc;
    Check(we::StartMovementBoundaryTraceForTesting(stale,&slot,slot)==ERROR_INVALID_DATA
        && !we::MovementBoundaryTraceForTesting(),"stale current-process creation time rejected");
    if (argc > 1 && std::strcmp(argv[1], "movement-startup-failure") == 0) {
        const auto original = slot;
        Check(we::StartNativeMovementUpdatesForTesting(identity, &Movement, &slot, original) == ERROR_ACCESS_DENIED,
            "controls startup preserves concrete partial-install failure");
        Check(movement_calls == 0 && !we::MovementBoundaryTraceForTesting(),
            "failed controls installation admits no consumer or trace");
        we::StopNativeMovementUpdates(); SetEvent(release_call); held.join();
        Check(slot == original && forwarded && calls == 1, "failed installation retains original through admitted callback");
        CloseHandle(entered); CloseHandle(release_call); return failures ? 1 : 0;
    }
    if (argc > 1 && std::strcmp(argv[1], "shared-slot-replaced") == 0) {
        const auto original = slot;
        Check(we::StartNativeMovementUpdatesForTesting(identity, &Movement, &slot, original) == ERROR_SUCCESS,
            "controls install before competing slot replacement");
        slot = 1234;
        Check(we::StartMovementBoundaryTraceForTesting(identity, &slot, original) == ERROR_INVALID_DATA,
            "second consumer rejects lost hook ownership");
        we::StopMovementBoundaryTrace(); we::StopNativeMovementUpdates();
        Check(slot == 1234, "retirement does not overwrite competing slot owner");
        CloseHandle(entered); CloseHandle(release_call); return failures ? 1 : 0;
    }
    if (argc > 1 && (std::strcmp(argv[1], "shared-trace-first") == 0
        || std::strcmp(argv[1], "shared-controls-first") == 0
        || std::strcmp(argv[1], "shared-held-control") == 0)) {
        const bool trace_first = std::strcmp(argv[1], "shared-trace-first") == 0;
        const bool hold = std::strcmp(argv[1], "shared-held-control") == 0;
        const auto original = slot;
        Check(we::StartNativeMovementUpdatesForTesting(stale, &Movement, &slot, original) == ERROR_INVALID_DATA,
            "controls reject stale process identity without installation");
        Check(we::StartNativeMovementUpdatesForTesting(identity, nullptr, &slot, original) == ERROR_INVALID_DATA,
            "controls reject missing callback without installation");
        if (trace_first) {
            Check(we::StartMovementBoundaryTraceForTesting(identity, &slot, original) == ERROR_SUCCESS, "trace installs shared slot");
        }
        Check(we::StartNativeMovementUpdatesForTesting(identity, &Movement, &slot, original) == ERROR_SUCCESS,
            "controls join or install shared slot");
        const auto callback = slot;
        if (!trace_first) {
            Check(we::StartMovementBoundaryTraceForTesting(identity, &slot, original) == ERROR_SUCCESS, "trace joins controls slot");
        }
        Check(slot == callback, "second consumer does not replace shared callback");
        Check(we::StartNativeMovementUpdatesForTesting(identity, &Movement, &slot, original) == ERROR_ALREADY_INITIALIZED,
            "immutable controls callback cannot be replaced");
        SetEvent(release_call);
        Check(Call(callback) && movement_calls == 1 && we::MovementBoundaryTraceForTesting()->write_sequence == 1,
            "both consumers execute and original return survives");
        if (trace_first) {
            we::StopNativeMovementUpdates();
            Check(slot == callback && Call(callback) && movement_calls == 1
                && we::MovementBoundaryTraceForTesting()->write_sequence == 2,
                "controls retirement preserves active trace");
            we::StopMovementBoundaryTrace();
        } else {
            we::StopMovementBoundaryTrace();
            Check(slot == callback && Call(callback) && movement_calls == 2
                && we::MovementBoundaryTraceForTesting()->write_sequence == 1,
                "trace retirement preserves active controls");
            if (hold) {
                movement_entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
                movement_release = CreateEventW(nullptr, TRUE, FALSE, nullptr);
                hold_movement = true;
                held = std::thread([callback] { if (!Call(callback)) { forwarded = false; } });
                Check(WaitForSingleObject(movement_entered, 5000) == WAIT_OBJECT_0, "admitted controls callback held");
                we::StopNativeMovementUpdates();
                SetEvent(movement_release); held.join();
                CloseHandle(movement_entered); CloseHandle(movement_release);
            } else { we::StopNativeMovementUpdates(); }
        }
        const auto count = movement_calls.load();
        Check(slot == original && Call(callback) && movement_calls == count,
            "last consumer restores slot; late dispatch still calls original without consumers");
        Check(we::StartNativeMovementUpdatesForTesting(identity, &Movement, &slot, original) == ERROR_ALREADY_INITIALIZED,
            "retired runtime generation cannot restart");
        Check(forwarded, "shared controls callback preserves receiver and native delta");
        CloseHandle(entered); CloseHandle(release_call);
        return failures ? 1 : 0;
    }
    if (argc>1 && std::strcmp(argv[1],"concurrent-stop")==0) {
        install_entered=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        install_release=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        HANDLE stop_requested=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        HANDLE stop_complete=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        hold_install=true;
        DWORD status=ERROR_GEN_FAILURE;
        const auto original=slot;
        std::thread starting([&] { status=we::StartMovementBoundaryTraceForTesting(identity,&slot,original); });
        Check(WaitForSingleObject(install_entered,5000)==WAIT_OBJECT_0,"install held after slot visibility");
        std::thread stopping([&] { SetEvent(stop_requested); we::StopMovementBoundaryTrace(); SetEvent(stop_complete); });
        Check(WaitForSingleObject(stop_requested,5000)==WAIT_OBJECT_0,"concurrent stop requested");
        Check(WaitForSingleObject(stop_complete,100)==WAIT_TIMEOUT,"stop serialized behind admission");
        SetEvent(install_release);
        starting.join(); stopping.join();
        const auto* snapshot=we::MovementBoundaryTraceForTesting();
        Check(status==ERROR_SUCCESS && snapshot && snapshot->enabled==0
            && slot==original,"stop linearizes after installation and cannot be re-enabled");
        Check(we::StartMovementBoundaryTraceForTesting(identity,&slot,original)==ERROR_ALREADY_INITIALIZED,
            "retained generation cannot be restarted");
        CloseHandle(stop_requested); CloseHandle(stop_complete);
        CloseHandle(install_entered); CloseHandle(install_release);
        CloseHandle(entered); CloseHandle(release_call);
        return failures ? 1 : 0;
    }
    const auto start=we::StartMovementBoundaryTraceForTesting(identity,&slot,slot);
    const auto* trace=we::MovementBoundaryTraceForTesting();
    Check(trace && trace->process_id==identity.process_id
        && trace->creation_filetime==identity.creation_filetime_utc,"exact process lifetime publication");
    Check(we::StartMovementBoundaryTraceForTesting(identity,&slot,slot)==ERROR_ALREADY_INITIALIZED,
        "duplicate start cannot replace retained mapping");
    if (argc > 1 && std::strcmp(argv[1], "input-diagnostics") == 0) {
        Check(start == ERROR_SUCCESS && trace->schema == 2 && std::memcmp(trace->magic, "WBMVTR2", 8) == 0,
            "passive input trace has distinct schema and layout");
        HWND window = CreateWindowExW(0, L"STATIC", L"diagnostic fixture", 0, 0, 0, 1, 1, HWND_MESSAGE, nullptr, nullptr, nullptr);
        we::MovementInputRecord event{}; event.thread_id = GetCurrentThreadId(); event.window = reinterpret_cast<std::uint32_t>(window);
        event.keys = 1; event.gates = 255; event.policy = 193; event.generation = 2; event.owner = 2;
        we::PublishMovementInputTrace(event);
        event.keys = 9; event.suppressed_keys = 9; event.kind = 3; event.key_event = 44;
        we::PublishMovementInputTrace(event);
        Check(trace->input_write_sequence == 2 && trace->input_events[1].keys == 9
            && trace->input_events[1].key_event == 44 && !trace->last_owner_loss.committed_sequence,
            "second-key event survives without an ownership revocation");
        event.previous_owner = 2; event.owner = 0; event.previous_generation = 2; event.generation = 3;
        event.kind = 2; event.key_event = 0; event.reason = 3;
        we::PublishMovementInputTrace(event);
        const auto loss = trace->last_owner_loss.committed_sequence;
        event.kind = 1; event.reason = UINT32_MAX; event.keys = 0;
        for (int n = 0; n != 400; ++n) { event.keys = n % 2 ? 1U : 9U; we::PublishMovementInputTrace(event); }
        Check(trace->last_owner_loss.committed_sequence == loss && trace->last_owner_loss.reason == 3
            && trace->last_owner_loss.keys == 9 && trace->input_write_sequence > 256,
            "retained owner loss survives idle samples and transition-ring overwrite");
        const auto sequence = trace->input_write_sequence;
        std::thread foreign([&] { we::PublishMovementInputTrace(event); }); foreign.join();
        Check(trace->input_write_sequence == sequence, "foreign thread cannot publish client input diagnostics");
        event.kind = 3; event.key_event = 255; we::PublishMovementInputTrace(event);
        Check(trace->input_write_sequence == sequence, "invalid key diagnostic cannot publish");
        we::StopMovementBoundaryTrace(); event.kind = 1; event.key_event = 0; we::PublishMovementInputTrace(event);
        Check(trace->input_write_sequence == sequence && !we::MovementInputTraceEnabled(), "retirement suppresses diagnostic publication");
        if (argc > 2) {
            std::ofstream output(argv[2], std::ios::binary);
            output.write(reinterpret_cast<const char*>(trace), sizeof(*trace));
            Check(output.good(), "export actual native diagnostic layout for reader interoperability");
        }
        DestroyWindow(window); CloseHandle(entered); CloseHandle(release_call); return failures ? 1 : 0;
    }
    if (fail_after_install) {
        Check(start==ERROR_ACCESS_DENIED,"propagate startup failure after slot visibility");
        Check(trace->write_sequence==0,"failed startup never publishes");
        we::StopMovementBoundaryTrace();
    } else {
        Check(start==ERROR_SUCCESS,"install successful");
        const auto callback=slot;
        held=std::thread([callback] { if (!Call(callback)) { forwarded=false; } });
        Check(WaitForSingleObject(entered,5000)==WAIT_OBJECT_0,"held original callback entered");
        Check(trace->write_sequence==1 && trace->records[0].committed_sequence==1,
            "complete bounded record published before original");
        Check(trace->records[0].read_valid==0,"unverified receiver is not accepted as live state");
        we::StopMovementBoundaryTrace();
        SetEvent(release_call);
        Check(Call(callback),"stale callback still forwards after shutdown");
        Check(trace->write_sequence==1 && trace->enabled==0,"shutdown suppresses late publication");
    }
    Check(slot==reinterpret_cast<std::uint32_t>(&Original),"shutdown restores only own slot");
    SetEvent(release_call);
    if (held.joinable()) { held.join(); }
    Check(forwarded && calls>=1,"original receiver, double argument and return value preserved");
    slot=1234; we::StopMovementBoundaryTrace();
    Check(slot==1234,"repeat stop cannot overwrite a replacement owner");
    CloseHandle(entered); CloseHandle(release_call);
    return failures ? 1 : 0;
}

namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; }
}
