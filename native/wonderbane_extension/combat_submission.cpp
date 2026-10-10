#include "combat_submission.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include <Windows.h>
#include <intrin.h>
#include <cstring>

namespace wonderbane::extension::combat::submission {
static_assert(sizeof(void*) == 4, "Qualified submission ABI requires x86");
namespace {
using Factory = void*(__thiscall*)(void*, void**, void*, const void*, bool);
using Followup = void(__thiscall*)(void*);
using Append = void(__thiscall*)(void*, void*);
constexpr std::uintptr_t actor_table = 0x114165c;
constexpr std::uintptr_t request_table = 0x1156e0c;
constexpr std::uintptr_t writer_table = 0x116036c;
constexpr std::uintptr_t container_table = 0x114ce9c;
constexpr std::uintptr_t factory_slot = actor_table + 0xd0;
constexpr std::uintptr_t followup_slot = actor_table + 0xcc;
constexpr std::uintptr_t append_slot = container_table + 8;
constexpr std::uintptr_t factory_return = 0x7d3e0b;
constexpr std::uintptr_t followup_return = 0x7d3e67;
constexpr std::uintptr_t append_return = 0x2c6eb7;
std::uintptr_t base = 0;
Factory original_factory = nullptr;
Followup original_followup = nullptr;
Append original_append = nullptr;
SRWLOCK installation_lock = SRWLOCK_INIT;
bool attempted = false;
volatile LONG installed = 0;
thread_local Scope* active = nullptr;
struct RegisteredObserver { AppendObserver callbacks{}; volatile LONG ready = 0; };
std::array<RegisteredObserver, 3> append_observers{};

bool Copy(void* destination, std::uintptr_t source, std::size_t size) noexcept {
    __try { std::memcpy(destination, reinterpret_cast<const void*>(source), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Pointer(std::uintptr_t at, std::uintptr_t expected) noexcept {
    std::uintptr_t value{};
    return Copy(&value, at, sizeof(value)) && value == expected;
}
bool Key(std::uintptr_t at, const std::array<std::uint32_t, 2>& expected) noexcept {
    std::array<std::uint32_t, 2> value{};
    return Copy(value.data(), at, sizeof(value)) && value == expected;
}
bool Binding(const Context& c) noexcept {
    return Pointer(base + 0x16a2d98, c.actor)
        && (c.route == Route::explicit_object
            || (c.route == Route::manual_selection && Pointer(base + 0x16a2da4, c.target)))
        && Pointer(c.actor, base + actor_table)
        && Key(c.actor + 0x18, c.local_key) && Key(c.target + 0x18, c.target_key)
        && Pointer(base + 0x16ab88c, c.writer)
        && Pointer(c.writer, base + writer_table)
        && Pointer(c.writer + 0x44, c.container)
        && Pointer(c.container, base + container_table);
}
bool Ticket(const Context& c, std::uintptr_t value) noexcept {
    return value && Pointer(value, base + request_table)
        && Key(value + 0x70, c.local_key) && Key(value + 0x78, c.target_key);
}
// Identical consumption of the native by-value ArcMemToken argument. Only the
// incoming reference is released; the caller's independent reference is untouched.
// The native handler still owns the factory out-reference at this boundary, so
// consuming this additional append reference does not destroy the scoped ticket.
// Do not catch native release exceptions or release a second time on unwind.
void Consume(void* value) {
    if (!value || value == reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1))) { return; }
    void* empty = nullptr;
    using Release = void(__thiscall*)(void*, void**);
    const auto table = *static_cast<std::uintptr_t*>(value);
    reinterpret_cast<Release>(*reinterpret_cast<std::uintptr_t*>(table + 8))(value, &empty);
}
}
namespace detail {
struct Observer {
    static void Publish(Scope& s) noexcept {
        if (s.context_.receipt) { *s.context_.receipt = s.receipt_; }
    }
    static void Block(Scope& s, Result result) noexcept {
        s.blocked_ = true;
        s.receipt_.result = result;
        Publish(s);
    }
    static void* __fastcall FactoryHook(void* actor, void*, void** output, void* target,
        const void* key, bool send) {
        const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
        const DWORD error = GetLastError();
        auto* s = active;
        if (!s || caller != base + factory_return) {
            SetLastError(error);
            return original_factory(actor, output, target, key, send);
        }
        return FactoryCall(s, actor, output, target, key, send, Route::manual_selection);
    }
    static void* FactoryCall(Scope* s, void* actor, void** output, void* target,
        const void* key, bool send, Route route) {
        const DWORD error = GetLastError();
        std::uintptr_t prior_output{};
        const bool empty_output = route != Route::explicit_object || (output
            && Copy(&prior_output, reinterpret_cast<std::uintptr_t>(output), sizeof(prior_output))
            && !prior_output);
        const bool allowed = active == s && s->active_ && s->context_.route == route && output
            && empty_output && !s->blocked_ && !s->factory_seen_ && Ready()
            && actor == reinterpret_cast<void*>(s->context_.actor)
            && target == reinterpret_cast<void*>(s->context_.target) && send
            && Key(reinterpret_cast<std::uintptr_t>(key), s->context_.target_key)
            && Binding(s->context_) && s->context_.current(s->context_.context);
        s->factory_seen_ = true;
        if (!allowed) {
            Block(*s, s->receipt_.native_entered ? Result::uncertain : Result::denied);
            SetLastError(error);
            // A failed explicit retry must not erase an already-owned reference.
            if (output && empty_output) { *output = nullptr; }
            return output;
        }
        s->receipt_.native_entered = true;
        s->receipt_.result = Result::uncertain; // Survives an original native exception.
        Publish(*s);
        SetLastError(error);
        void* result{};
        try { result = original_factory(actor, output, target, key, send); }
        catch (...) { Block(*s, Result::uncertain); throw; }
        const DWORD native_error = GetLastError();
        std::uintptr_t ticket{};
        const bool copied = Copy(&ticket, reinterpret_cast<std::uintptr_t>(output), sizeof(ticket));
        s->ticket_ = ticket; // Retain provenance even if returned fields fail validation.
        if (s->blocked_ || result != output || !copied || (ticket && !Ticket(s->context_, ticket))) {
            Block(*s, Result::uncertain);
        } else {
            s->receipt_.result = Result::no_submission;
            if (!Ready() || !Binding(s->context_) || !s->context_.current(s->context_.context)) {
                Block(*s, Result::uncertain);
            }
        }
        Publish(*s);
        SetLastError(native_error);
        return result;
    }
    static void __fastcall FollowupHook(void* actor, void*) {
        const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
        const DWORD error = GetLastError();
        auto* s = active;
        if (!s || caller != base + followup_return) {
            SetLastError(error); original_followup(actor); return;
        }
        FollowupCall(s, actor, Route::manual_selection);
    }
    static void FollowupCall(Scope* s, void* actor, Route route) {
        const DWORD error = GetLastError();
        const bool allowed = active == s && s->active_ && s->context_.route == route
            && !s->blocked_ && s->factory_seen_ && !s->followup_seen_ && Ready()
            && actor == reinterpret_cast<void*>(s->context_.actor) && Binding(s->context_)
            && s->context_.current(s->context_.context);
        s->followup_seen_ = true;
        if (!allowed) {
            if (!s->blocked_) { Block(*s, s->receipt_.native_entered ? Result::uncertain : Result::denied); }
            SetLastError(error); return;
        }
        const auto prior = s->receipt_.result;
        s->receipt_.followup_entered = true;
        s->receipt_.result = Result::uncertain;
        Publish(*s);
        SetLastError(error);
        try { original_followup(actor); }
        catch (...) { Block(*s, Result::uncertain); throw; }
        const DWORD native_error = GetLastError();
        if (!s->blocked_ && Ready() && Binding(s->context_)
            && s->context_.current(s->context_.context)) { s->receipt_.result = prior; }
        else { Block(*s, Result::uncertain); }
        Publish(*s);
        SetLastError(native_error);
    }
    static void __fastcall AppendHook(void* container, void*, void* message) {
        const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
        const DWORD error = GetLastError();
        auto* s = active;
        // Match the originating frame even while another scope is nested above
        // it. Exact returned-ticket provenance, not keys/class, owns this append.
        while (s && (!s->ticket_ || message != reinterpret_cast<void*>(s->ticket_))) { s = s->previous_; }
        std::array<AppendClaim, 3> claims{};
        std::size_t claimed = 0, selected = 0;
        for (std::size_t i = 0; i < append_observers.size(); ++i) {
            auto& observer = append_observers[i];
            if (InterlockedCompareExchange(&observer.ready, 0, 0)) {
                claims[i] = observer.callbacks.claim(container, message, caller >= base ? caller - base : 0);
                if (claims[i].decision != AppendDecision::unrelated) { ++claimed; selected = i; }
            }
        }
        if (claimed) {
            // Claim history lives in each originating owner, never in the message.
            // A collision cannot select a winner or consume the argument twice.
            const auto claim = claims[selected];
            const bool allowed = claimed == 1 && !s && claim.owner && claim.decision == AppendDecision::allow
                && Ready() && caller == base + append_return;
            if (s) { Block(*s, Result::uncertain); }
            if (!allowed) {
                for (std::size_t i = 0; i < claims.size(); ++i) {
                    if (claims[i].decision != AppendDecision::unrelated && claims[i].owner) {
                        append_observers[i].callbacks.complete(claims[i].owner, AppendResult::denied);
                    }
                }
                SetLastError(error); Consume(message); return;
            }
            // Registration is immutable and process-pinned. Capture the owner and
            // callback before native append, which may reenter or destroy message.
            const auto complete = append_observers[selected].callbacks.complete;
            SetLastError(error);
            try { original_append(container, message); }
            catch (...) { complete(claim.owner, AppendResult::fault); throw; }
            const DWORD native_error = GetLastError();
            complete(claim.owner, AppendResult::queued);
            SetLastError(native_error); return;
        }
        if (!s) {
            SetLastError(error); original_append(container, message); return;
        }
        const bool allowed = !s->blocked_ && !s->append_seen_ && caller == base + append_return
            && container == reinterpret_cast<void*>(s->context_.container) && Ready()
            && Binding(s->context_) && Ticket(s->context_, s->ticket_)
            && s->context_.append_current(s->context_.context);
        s->append_seen_ = true;
        if (!allowed) {
            Block(*s, Result::uncertain);
            SetLastError(error); Consume(message); return;
        }
        s->receipt_.result = Result::uncertain;
        Publish(*s);
        SetLastError(error);
        try { original_append(container, message); }
        catch (...) { Block(*s, Result::uncertain); throw; }
        const DWORD native_error = GetLastError();
        // Under native queue lock: bounded scalar/atomic observations only. The
        // transferred argument may already be destroyed; never dereference it.
        s->receipt_.append_observed = true;
        Publish(*s); // Publish insertion fact before any later validation can fault.
        if (!s->blocked_ && Ready() && Binding(s->context_)
            && s->context_.append_current(s->context_.context)) { s->receipt_.result = Result::queued; }
        else { Block(*s, Result::uncertain); }
        Publish(*s);
        SetLastError(native_error);
    }
};
}
namespace {
bool SlotsCurrent() noexcept {
    return base && Pointer(base + factory_slot, reinterpret_cast<std::uintptr_t>(&detail::Observer::FactoryHook))
        && Pointer(base + followup_slot, reinterpret_cast<std::uintptr_t>(&detail::Observer::FollowupHook))
        && Pointer(base + append_slot, reinterpret_cast<std::uintptr_t>(&detail::Observer::AppendHook));
}
bool StartBound(std::uintptr_t image, Factory factory, Followup followup, Append append) noexcept {
    AcquireSRWLockExclusive(&installation_lock);
    if (attempted) { const bool same = image == base; ReleaseSRWLockExclusive(&installation_lock); return same && Ready(); }
    attempted = true;
    base = image; original_factory = factory; original_followup = followup; original_append = append;
    const std::array<std::uintptr_t, 3> slots{factory_slot, followup_slot, append_slot};
    const std::array<std::uintptr_t, 3> old{reinterpret_cast<std::uintptr_t>(factory),
        reinterpret_cast<std::uintptr_t>(followup), reinterpret_cast<std::uintptr_t>(append)};
    const std::array<std::uintptr_t, 3> replacements{reinterpret_cast<std::uintptr_t>(&detail::Observer::FactoryHook),
        reinterpret_cast<std::uintptr_t>(&detail::Observer::FollowupHook),
        reinterpret_cast<std::uintptr_t>(&detail::Observer::AppendHook)};
    bool ok = image && factory && followup && append;
    for (std::size_t i = 0; ok && i < slots.size(); ++i) { ok = Pointer(image + slots[i], old[i]); }
    for (std::size_t i = 0; ok && i < slots.size(); ++i) {
        ok = ReplaceImportAddressSlot(reinterpret_cast<std::uint32_t*>(image + slots[i]),
            static_cast<std::uint32_t>(old[i]), static_cast<std::uint32_t>(replacements[i])) == ERROR_SUCCESS;
    }
    if (!ok) {
        // A protection-restore failure can follow a successful slot write. Restore
        // only our own values. Keep call-throughs immutable for late callbacks.
        for (std::size_t i = 0; image && i < slots.size(); ++i) {
            (void)ReplaceImportAddressSlot(reinterpret_cast<std::uint32_t*>(image + slots[i]),
                static_cast<std::uint32_t>(replacements[i]), static_cast<std::uint32_t>(old[i]));
        }
    }
    if (ok) { InterlockedExchange(&installed, 1); }
    ReleaseSRWLockExclusive(&installation_lock);
    return ok && SlotsCurrent();
}
}
Scope::Scope(const Context& context) noexcept : context_(context), previous_(active) {
    const DWORD error = GetLastError();
    active = this; active_ = true;
    if (!Ready() || !context.actor || !context.target || !context.writer || !context.container
        || !context.current || !context.append_current
        || (context.route != Route::manual_selection && context.route != Route::explicit_object)) {
        receipt_.result = Result::denied; blocked_ = true;
    }
    detail::Observer::Publish(*this);
    SetLastError(error);
}
Scope::~Scope() { (void)Finish(); }
void* Scope::Factory(void* actor, void** output, void* target, const void* key, bool send) {
    return detail::Observer::FactoryCall(this, actor, output, target, key, send, Route::explicit_object);
}
void Scope::Followup(void* actor) {
    detail::Observer::FollowupCall(this, actor, Route::explicit_object);
}
Receipt Scope::Finish() noexcept {
    if (active_) {
        if (active == this) { active = previous_; }
        else {
            // Defensive support for early/out-of-order Finish: revoke descendants
            // and unlink this frame before its storage can leave scope.
            for (auto* child = active; child; child = child->previous_) {
                detail::Observer::Block(*child, child->receipt_.native_entered ? Result::uncertain : Result::denied);
                if (child->previous_ == this) { child->previous_ = previous_; break; }
            }
        }
        active_ = false;
        if (!Ready() && !blocked_) { receipt_.result = Result::uncertain; }
        if (ticket_ && !append_seen_ && !blocked_) { receipt_.result = Result::uncertain; }
    }
    detail::Observer::Publish(*this);
    return receipt_;
}
Boundary::Boundary() noexcept : previous_(active) {}
void Boundary::Restore() noexcept { active = previous_; }
bool RegisterAppendObserver(AppendObserverKind kind, const AppendObserver& observer) noexcept {
    const DWORD error = GetLastError();
    if ((kind != AppendObserverKind::power && kind != AppendObserverKind::item
        && kind != AppendObserverKind::group_chat)
        || !observer.claim || !observer.complete) { SetLastError(error); return false; }
    const auto index = static_cast<std::size_t>(kind);
    AcquireSRWLockExclusive(&installation_lock);
    auto& slot = append_observers[index];
    bool ok = Ready();
    if (ok && InterlockedCompareExchange(&slot.ready, 0, 0)) {
        ok = slot.callbacks.claim == observer.claim && slot.callbacks.complete == observer.complete;
    } else if (ok) {
        slot.callbacks = observer;
        InterlockedExchange(&slot.ready, 1);
    }
    ReleaseSRWLockExclusive(&installation_lock);
    SetLastError(error); return ok;
}
bool Ready() noexcept { return InterlockedCompareExchange(&installed, 0, 0) != 0 && SlotsCurrent(); }
bool Start(std::uintptr_t image_base) noexcept {
    const DWORD error = GetLastError();
    std::uintptr_t verified{};
    const bool ok = image_base
        && (GraphicsExecutableSha256Matches("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f")
            || GraphicsExecutableSha256Matches("2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289")
            || (GraphicsExecutableSha256Matches("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d") || (GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903") || (GraphicsExecutableSha256Matches("e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437") || (GraphicsExecutableSha256Matches("1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c") || GraphicsExecutableSha256Matches("baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9"))))))
        && movement::VerifyNativeMovementImage(verified) && verified == image_base
        && StartBound(image_base, reinterpret_cast<Factory>(image_base + 0xf9f7),
            reinterpret_cast<Followup>(image_base + 0x14fba), reinterpret_cast<Append>(image_base + 0x1e556));
    SetLastError(error); return ok;
}
}
