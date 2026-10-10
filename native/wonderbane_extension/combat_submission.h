#pragma once
#include <array>
#include <cstdint>
namespace wonderbane::extension::combat::submission {
struct Receipt;
enum class Route { manual_selection, explicit_object };
struct Context {
    std::uintptr_t actor{}, target{}, writer{}, container{};
    std::array<std::uint32_t, 2> local_key{}, target_key{};
    bool (*current)(void*) noexcept = nullptr;
    void* context = nullptr;
    // Runs under the native queue lock: bounded scalar/atomic reads only.
    // No allocation, extension locks, native callbacks, or full party scans.
    bool (*append_current)(void*) noexcept = nullptr;
    // Optional owner-thread sink retained outside the faulting dispatch frame.
    // It must outlive Scope AND the enclosing SEH boundary; never use a Run-local
    // receipt. Bounded copies preserve known append history through native faults.
    Receipt* receipt = nullptr;
    Route route = Route::manual_selection;
};
enum class Result { no_submission, queued, uncertain, denied };
struct Receipt {
    Result result = Result::no_submission;
    bool native_entered = false;
    bool append_observed = false;
    bool followup_entered = false;
};
// Fixed process-pinned power and item observers share one outbound queue hook.
// Conflicting claims reject every claimant and consume the transferred reference once.
// claim/complete run under the native queue lock: bounded reads only, no locks,
// allocation, or native calls. An allow claim publishes uncertain entry history
// before returning. Its owner outlives the original append and any nested calls.
enum class AppendDecision { unrelated, allow, deny };
enum class AppendResult { denied, queued, fault };
struct AppendClaim {
    AppendDecision decision = AppendDecision::unrelated;
    void* owner = nullptr;
};
enum class AppendObserverKind { power, item, group_chat };
struct AppendObserver {
    AppendClaim (*claim)(void* container, void* message, std::uintptr_t caller_rva) noexcept = nullptr;
    // The transferred message may be destroyed; complete receives only the owner.
    void (*complete)(void* owner, AppendResult) noexcept = nullptr;
};
bool RegisterAppendObserver(AppendObserverKind, const AppendObserver&) noexcept;
namespace detail { struct Observer; }
class Scope final {
public:
    explicit Scope(const Context&) noexcept;
    ~Scope();
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
    Receipt Finish() noexcept;
    // Internal explicit-object entry; native call-throughs and receipt ownership
    // stay inside this scope. Legacy handler callbacks cannot borrow this route.
    void* Factory(void* actor, void** output, void* target, const void* key, bool send);
    void Followup(void* actor);
private:
    friend struct detail::Observer;
    Context context_{};
    Receipt receipt_{};
    Scope* previous_{};
    std::uintptr_t ticket_{};
    bool active_ = false;
    bool factory_seen_ = false;
    bool append_seen_ = false;
    bool followup_seen_ = false;
    bool blocked_ = false;
};
// Capture outside a faulting native frame and call Restore from __finally.
// /EHsc does not promise C++ Scope destruction for SEH. This trivial boundary
// restores TLS without reading any abandoned Scope storage.
class Boundary final {
public:
    Boundary() noexcept;
    void Restore() noexcept;
    Boundary(const Boundary&) = delete;
    Boundary& operator=(const Boundary&) = delete;
private:
    Scope* previous_{};
};
// One installation generation, immutable native call-throughs, no unloading.
// Independently verifies the exact reviewed file and loaded executable image.
bool Start(std::uintptr_t image_base) noexcept;
bool Ready() noexcept;
}
