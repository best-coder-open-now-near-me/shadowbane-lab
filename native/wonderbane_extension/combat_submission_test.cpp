#include "combat_submission.cpp"
#include <cstdlib>
#include <iostream>
#include <stdexcept>

namespace cs = wonderbane::extension::combat::submission;
namespace {
int failures = 0;
unsigned factories = 0, appends = 0, followups = 0, releases = 0, full_checks = 0, queue_checks = 0;
bool current = true, queue_current = true, under_queue_lock = false;
bool empty_factory = false, corrupt_ticket = false, throw_factory = false, throw_append = false, throw_followup = false;
bool raise_factory_seh = false, raise_append_seh = false, raise_followup_seh = false;
unsigned fail_install_at = 0, installs = 0;
std::array<std::uint32_t, 0x80 / 4> message{};
void Check(bool ok, const char* label) { if (!ok) { ++failures; std::cerr << label << '\n'; } }
bool Current(void*) noexcept {
    ++full_checks; Check(!under_queue_lock, "full admission must never run under queue lock");
    SetLastError(999); return current;
}
bool QueueCurrent(void*) noexcept { ++queue_checks; SetLastError(998); return queue_current; }
void __fastcall Release(void*, void*, void** ref) {
    ++releases; Check(*ref == nullptr, "denied append consumes a zeroed incoming reference");
}
void* __fastcall Factory(void*, void*, void** out, void*, const void*, bool) {
    ++factories; Check(GetLastError() == 42, "factory preserves incoming LastError");
    if (raise_factory_seh) { RaiseException(0xe0420101, 0, 0, nullptr); }
    if (throw_factory) { throw std::runtime_error("factory"); }
    *out = empty_factory ? nullptr : message.data();
    if (corrupt_ticket) { ++message[0x78 / 4]; }
    SetLastError(43); return out;
}
void __fastcall Followup(void*, void*) {
    ++followups; Check(GetLastError() == 42, "followup preserves incoming LastError");
    if (raise_followup_seh) { RaiseException(0xe0420101, 0, 0, nullptr); }
    if (throw_followup) { throw std::runtime_error("followup"); }
    SetLastError(44);
}
void __fastcall Append(void*, void*, void*) {
    ++appends; Check(GetLastError() == 42, "append preserves incoming LastError");
    if (raise_append_seh) { RaiseException(0xe0420101, 0, 0, nullptr); }
    if (throw_append) { throw std::runtime_error("append"); }
    SetLastError(45);
}
using FactoryCallForSeh = void*(__stdcall*)(void*, void**, void*, const void*, bool);
using AppendCallForSeh = void(__stdcall*)(void*, void*);
using FollowupCallForSeh = void(__stdcall*)(void*);
void RunForSeh(const cs::Context& context, FactoryCallForSeh factory, AppendCallForSeh append, FollowupCallForSeh followup) {
    cs::Scope scope(context);
    void* ticket{};
    SetLastError(42);
    factory(reinterpret_cast<void*>(context.actor), &ticket, reinterpret_cast<void*>(context.target),
        context.target_key.data(), true);
    SetLastError(42); append(reinterpret_cast<void*>(context.container), ticket);
    SetLastError(42); followup(reinterpret_cast<void*>(context.actor));
}
bool GuardedSeh(const cs::Context& context, FactoryCallForSeh factory, AppendCallForSeh append, FollowupCallForSeh followup) {
    cs::Boundary boundary;
    __try {
        __try { RunForSeh(context, factory, append, followup); }
        __finally { boundary.Restore(); }
    } __except(GetExceptionCode() == 0xe0420101 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        return false;
    }
    return true;
}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
namespace movement { bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; } }
DWORD ReplaceImportAddressSlot(std::uint32_t* slot, std::uint32_t expected, std::uint32_t value) noexcept {
    const auto prior = InterlockedCompareExchange(reinterpret_cast<LONG*>(slot),
        static_cast<LONG>(value), static_cast<LONG>(expected));
    if (static_cast<std::uint32_t>(prior) != expected) { return ERROR_INVALID_DATA; }
    if (fail_install_at && ++installs == fail_install_at) { return ERROR_ACCESS_DENIED; }
    return ERROR_SUCCESS;
}
}
int main(int argc, char** argv) {
    const bool installation_failure = argc > 1 && std::strcmp(argv[1], "install-failure") == 0;
    auto* image = static_cast<unsigned char*>(VirtualAlloc(nullptr, 0x16ac000,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (!image) { return 2; }
    const auto base = reinterpret_cast<std::uintptr_t>(image);
    const auto put = [base](std::uintptr_t at, std::uintptr_t value) {
        *reinterpret_cast<std::uintptr_t*>(base + at) = value;
    };
    put(cs::factory_slot, reinterpret_cast<std::uintptr_t>(&Factory));
    put(cs::followup_slot, reinterpret_cast<std::uintptr_t>(&Followup));
    put(cs::append_slot, reinterpret_cast<std::uintptr_t>(&Append));
    if (installation_failure) { fail_install_at = 2; }
    Check(cs::StartBound(base, reinterpret_cast<cs::Factory>(&Factory),
        reinterpret_cast<cs::Followup>(&Followup), reinterpret_cast<cs::Append>(&Append)) != installation_failure,
        "one all-or-nothing installation");
    if (installation_failure) {
        Check(!cs::Ready(), "partial install stays unavailable");
        Check(cs::Pointer(base + cs::factory_slot, reinterpret_cast<std::uintptr_t>(&Factory))
            && cs::Pointer(base + cs::followup_slot, reinterpret_cast<std::uintptr_t>(&Followup))
            && cs::Pointer(base + cs::append_slot, reinterpret_cast<std::uintptr_t>(&Append)), "restore only installed slots");
        SetLastError(42); cs::detail::Observer::FollowupHook(nullptr, nullptr);
        Check(followups == 1, "late callback after failed install retains original");
        return failures;
    }
    // Executable fixtures call the actual three fastcall wrappers from the exact
    // qualified return PCs using native thiscall stack cleanup and argument order.
    constexpr unsigned char factory_code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,
        0xff,0x75,0x18,0xff,0x75,0x14,0xff,0x75,0x10,0xff,0x75,0x0c,
        0x8b,0x01,0xff,0x90,0xd0,0,0,0,0x5d,0xc2,0x14,0};
    constexpr unsigned char followup_code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,
        0x8b,0x01,0xff,0x90,0xcc,0,0,0,0x5d,0xc2,4,0};
    constexpr unsigned char append_code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,
        0xff,0x75,0x0c,0x8b,0x01,0xff,0x50,8,0x5d,0xc2,8,0};
    const auto code = [image](std::uintptr_t return_rva, const void* bytes, std::size_t size, std::size_t prefix) {
        auto* destination = image + return_rva - prefix;
        DWORD old{};
        Check(VirtualProtect(destination, size, PAGE_READWRITE, &old) != FALSE, "writable fixture protection");
        std::memcpy(destination, bytes, size);
        Check(VirtualProtect(destination, size, PAGE_EXECUTE_READ, &old) != FALSE, "executable fixture protection");
        Check(FlushInstructionCache(GetCurrentProcess(), destination, size) != FALSE, "fixture instruction cache");
        return destination;
    };
    using FactoryCall = void*(__stdcall*)(void*, void**, void*, const void*, bool);
    using FollowupCall = void(__stdcall*)(void*);
    using AppendCall = void(__stdcall*)(void*, void*);
    const auto factory = reinterpret_cast<FactoryCall>(code(cs::factory_return, factory_code, sizeof(factory_code), 26));
    const auto followup = reinterpret_cast<FollowupCall>(code(cs::followup_return, followup_code, sizeof(followup_code), 14));
    const auto append = reinterpret_cast<AppendCall>(code(cs::append_return, append_code, sizeof(append_code), 14));
    std::array<std::uint32_t, 16> actor{}, target{};
    std::array<std::uint32_t, 32> writer{};
    std::array<std::uint32_t, 12> container{};
    actor[0] = static_cast<std::uint32_t>(base + cs::actor_table);
    actor[6] = 100; actor[7] = 53; target[6] = 200; target[7] = 53;
    writer[0] = static_cast<std::uint32_t>(base + cs::writer_table);
    writer[0x44 / 4] = reinterpret_cast<std::uint32_t>(container.data());
    container[0] = static_cast<std::uint32_t>(base + cs::container_table);
    put(0x16a2d98, reinterpret_cast<std::uintptr_t>(actor.data()));
    put(0x16a2da4, reinterpret_cast<std::uintptr_t>(target.data()));
    put(0x16ab88c, reinterpret_cast<std::uintptr_t>(writer.data()));
    put(cs::request_table + 8, reinterpret_cast<std::uintptr_t>(&Release));
    cs::Context context{reinterpret_cast<std::uintptr_t>(actor.data()), reinterpret_cast<std::uintptr_t>(target.data()),
        reinterpret_cast<std::uintptr_t>(writer.data()), reinterpret_cast<std::uintptr_t>(container.data()),
        {100,53}, {200,53}, &Current, nullptr, &QueueCurrent};
    void* ticket{};
    const auto reset = [&] {
        current = queue_current = true;
        empty_factory = corrupt_ticket = throw_factory = throw_append = throw_followup = false;
        message.fill(0); message[0] = static_cast<std::uint32_t>(base + cs::request_table);
        message[0x70 / 4] = 100; message[0x74 / 4] = 53;
        message[0x78 / 4] = 200; message[0x7c / 4] = 53;
        ticket = nullptr;
    };
    const auto make = [&] { SetLastError(42); return factory(actor.data(), &ticket, target.data(), context.target_key.data(), true); };
    const auto queue = [&] {
        under_queue_lock = true; SetLastError(42);
        try { append(container.data(), ticket); } catch (...) { under_queue_lock = false; throw; }
        under_queue_lock = false;
    };
    const auto finish_native = [&] { SetLastError(42); followup(actor.data()); };
    reset();
    {
        cs::Scope scope(context); make(); Check(GetLastError() == 43, "factory preserves original LastError");
        queue(); Check(GetLastError() == 45, "append preserves original LastError");
        finish_native(); Check(GetLastError() == 44, "followup preserves original LastError");
        const auto r = scope.Finish();
        Check(r.result == cs::Result::queued && r.native_entered && r.append_observed && r.followup_entered,
            "full native callback sequence proves local queue insertion");
    }
    reset();
    {
        cs::Scope scope(context); current = false; const auto before = factories;
        Check(make() == &ticket && ticket == nullptr && factories == before, "denied factory returns native empty out-reference");
        const auto cc = followups; finish_native(); Check(followups == cc, "denied factory blocks followup");
        const auto r = scope.Finish(); Check(r.result == cs::Result::denied && !r.native_entered, "pre-entry denial receipt");
    }
    reset();
    {
        cs::Scope scope(context); ++context.target_key[0]; const auto before = factories;
        make(); Check(factories == before && scope.Finish().result == cs::Result::denied,
            "factory input key mismatch cannot enter native factory");
        --context.target_key[0];
    }
    reset();
    {
        cs::Scope scope(context); put(0x16a2da4, context.actor); const auto before = factories;
        make(); Check(factories == before && scope.Finish().result == cs::Result::denied,
            "selection replacement before D0 cannot attack captured or replacement target");
        put(0x16a2da4, context.target);
    }
    reset();
    {
        cs::Scope scope(context); make(); queue_current = false;
        const auto before = appends, consumed = releases; queue();
        Check(appends == before && releases == consumed + 1, "revoked append consumes exactly incoming owned ref");
        const auto cc = followups; finish_native(); Check(followups == cc, "revoked append blocks followup");
        Check(scope.Finish().result == cs::Result::uncertain, "already entered denial is uncertain");
    }
    reset();
    {
        cs::Scope scope(context); corrupt_ticket = true; make();
        const auto before = appends, consumed = releases; queue();
        Check(appends == before && releases == consumed + 1, "malformed returned ticket retains provenance and cannot enqueue");
        Check(scope.Finish().result == cs::Result::uncertain, "malformed ticket uncertain");
    }
    reset();
    {
        cs::Scope scope(context); make(); queue(); const auto before = appends, consumed = releases; queue();
        Check(appends == before && releases == consumed + 1, "duplicate exact ticket never resubmits");
        const auto r = scope.Finish(); Check(r.result == cs::Result::uncertain && r.append_observed, "queued history survives duplicate");
    }
    reset();
    {
        cs::Scope outer(context); make();
        { cs::Scope inner(context); current = false; make(); Check(inner.Finish().result == cs::Result::denied, "nested scope owns denial"); }
        current = true; ticket = message.data(); queue(); finish_native();
        Check(outer.Finish().result == cs::Result::queued, "nested TLS scope restores original owner");
    }
    reset();
    {
        cs::Scope scope(context); make();
        std::array<std::uint32_t, 32> unrelated = message;
        const auto before = appends; SetLastError(42); append(container.data(), unrelated.data());
        Check(appends == before + 1, "same keys/class without returned ticket is unscoped pass-through");
        Check(scope.Finish().result == cs::Result::uncertain, "missing exact append is not submission proof");
    }
    reset();
    {
        cs::Scope scope(context); empty_factory = true; make(); finish_native();
        Check(scope.Finish().result == cs::Result::no_submission, "native null factory remains no submission");
    }
    reset();
    {
        cs::Scope scope(context); make(); put(0x16ab88c, 0);
        const auto before = appends; queue(); Check(appends == before, "writer replacement cannot inherit old ticket");
        put(0x16ab88c, context.writer);
    }
    reset();
    {
        cs::Scope scope(context); make(); queue(); throw_followup = true;
        bool caught = false; try { finish_native(); } catch (const std::runtime_error&) { caught = true; }
        const auto r = scope.Finish(); Check(caught && r.result == cs::Result::uncertain && r.append_observed,
            "native followup exception preserves queued history and propagates");
    }
    reset();
    {
        cs::Scope scope(context); make(); throw_append = true;
        bool caught = false; try { queue(); } catch (const std::runtime_error&) { caught = true; }
        const auto r = scope.Finish(); Check(caught && r.result == cs::Result::uncertain && !r.append_observed,
            "throwing append has no post-return receipt");
    }
    reset();
    try { cs::Scope scope(context); throw_factory = true; make(); } catch (const std::runtime_error&) {}
    Check(cs::active == nullptr, "native exception restores TLS scope on unwind");
    reset();
    {
        cs::Scope outer(context); make();
        cs::Scope inner(context);
        Check(outer.Finish().result == cs::Result::uncertain, "out-of-order parent lacks append proof");
        const auto before = factories; make();
        Check(factories == before && inner.Finish().result == cs::Result::denied,
            "out-of-order Finish revokes and unlinks descendants");
        Check(cs::active == nullptr, "out-of-order Finish leaves no stale TLS pointer");
    }
    reset();
    {
        auto missing = context; missing.append_current = nullptr; cs::Scope scope(missing);
        const auto before = factories; make(); Check(factories == before && scope.Finish().result == cs::Result::denied,
            "missing queue-safe predicate fails closed");
    }
    reset();
    {
        cs::Scope scope(context); make(); put(cs::followup_slot, reinterpret_cast<std::uintptr_t>(&Followup));
        const auto before = appends; queue(); Check(!cs::Ready() && appends == before, "hook collision closes entire admission");
        put(cs::followup_slot, reinterpret_cast<std::uintptr_t>(&cs::detail::Observer::FollowupHook));
    }
    reset();
    raise_factory_seh = true;
    Check(!GuardedSeh(context, factory, append, followup) && cs::active == nullptr, "SEH factory fault restores TLS boundary");
    raise_factory_seh = false;
    reset();
    {
        cs::Scope outer(context);
        raise_append_seh = true;
        Check(!GuardedSeh(context, factory, append, followup) && cs::active == &outer,
            "SEH append fault restores prior live nested scope without abandoned-frame reads");
        raise_append_seh = false;
    }
    reset();
    const auto after_seh_factory = factories, after_seh_append = appends;
    make(); queue();
    Check(factories == after_seh_factory + 1 && appends == after_seh_append + 1 && cs::active == nullptr,
        "next unscoped native callbacks pass through after SEH");
    reset();
    cs::Receipt persistent{};
    context.receipt = &persistent;
    raise_followup_seh = true;
    Check(!GuardedSeh(context, factory, append, followup) && cs::active == nullptr,
        "SEH after queued append restores boundary");
    Check(persistent.native_entered && persistent.append_observed && persistent.followup_entered
        && persistent.result == cs::Result::uncertain, "persistent sink preserves queued evidence through SEH unwind");
    raise_followup_seh = false;
    reset();
    try { cs::Scope scope(context); make(); queue(); throw_followup = true; finish_native(); }
    catch (const std::runtime_error&) {}
    Check(persistent.append_observed && persistent.result == cs::Result::uncertain,
        "persistent sink preserves queued evidence through C++ unwind");
    context.receipt = nullptr;
    Check(full_checks > 0 && queue_checks > 0, "both distinct admission barriers exercised");
    // Hooks are process-lifetime objects. The synthetic image is intentionally
    // left mapped until this test process exits, matching production no-unload.
    return failures;
}
