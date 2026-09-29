#include "combat_native.h"
#include "movement_native_image.h"
#include <algorithm>
#include <cmath>

namespace wonderbane::extension::combat {
namespace {
template<class T> bool Read(std::uintptr_t at, T& out) noexcept {
    if (at < 0x10000 || at > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
struct Text {
    std::array<std::uint16_t, 64> units{};
    std::size_t count = 0;
    wire::Text View() const noexcept { return {units.data(), count}; }
};
bool ReadText(std::uintptr_t field, Text& out) noexcept {
    std::uintptr_t begin = 0, end = 0, capacity = 0;
    if (!Read(field + 4, begin) || !Read(field + 8, end) || !Read(field + 12, capacity)
        || begin < 0x10000 || begin % 2 || end <= begin || capacity < end || capacity - end < 2
        || capacity > 0x7fff0000 || (end - begin) % 2 || end - begin > 128) { return false; }
    out.count = (end - begin) / 2;
    for (std::size_t i = 0; i < out.count; ++i) {
        if (!Read(begin + i * 2, out.units[i])) { return false; }
    }
    std::uint16_t terminator = 1;
    if (!Read(end, terminator) || terminator) { return false; }
    std::uintptr_t after_begin = 0, after_end = 0, after_capacity = 0;
    return Read(field + 4, after_begin) && Read(field + 8, after_end)
        && Read(field + 12, after_capacity) && begin == after_begin
        && end == after_end && capacity == after_capacity;
}
using O = wire::Outcome;
}
bool NativeTarget::Owner() const noexcept {
    DWORD process = 0;
    return thread_ && GetCurrentThreadId() == thread_
        && GetWindowThreadProcessId(window_, &process) == thread_ && process == GetCurrentProcessId();
}
bool NativeTarget::Bind(HWND window) noexcept {
    if (base_ || faulted_) { return false; }
    window_ = window; thread_ = GetCurrentThreadId();
    if (!Owner() || !movement::VerifyNativeMovementImage(base_)) { base_ = 0; return false; }
    calls_.construct = reinterpret_cast<decltype(calls_.construct)>(base_ + 0x2140b0);
    calls_.query = reinterpret_cast<decltype(calls_.query)>(base_ + 0x20e970);
    calls_.retain = reinterpret_cast<decltype(calls_.retain)>(base_ + 0x131190);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x89bd0);
    calls_.pool_return = reinterpret_cast<decltype(calls_.pool_return)>(base_ + 0x40270);
    calls_.select = reinterpret_cast<decltype(calls_.select)>(base_ + 0x498730);
    calls_.dispatch = reinterpret_cast<decltype(calls_.dispatch)>(base_ + 0x7ca9c0);
    return true;
}
bool NativeTarget::RawCurrent(bool selected) const noexcept {
    std::uintptr_t actor = 0, root = 0, world = 0, chosen = 0;
    return Read(base_ + 0x16a2d98, actor) && actor == scene_.actor
        && Read(base_ + 0x16a7bfc, root) && root == scene_.window
        && Read(base_ + 0x1389028, world) && world == scene_.world
        && (!selected || (Read(base_ + 0x16a2da4, chosen)
            && chosen == reinterpret_cast<std::uintptr_t>(target_)));
}
bool NativeTarget::Identity() const noexcept {
    const auto actor = reinterpret_cast<std::uintptr_t>(actor_);
    const auto target = reinterpret_cast<std::uintptr_t>(target_);
    std::uintptr_t actor_table = 0, target_table = 0;
    std::array<std::uint32_t, 2> actor_key{}, target_key{};
    Text local_name{}, local_server{}, target_name{}, target_server{};
    return actor == scene_.actor && target && Read(actor, actor_table) && Read(target, target_table)
        && actor_table == base_ + 0x114165c && target_table == actor_table
        && Read(actor + 0x18, actor_key) && Read(target + 0x18, target_key)
        && !std::memcmp(actor_key.data(), command_.local_key, sizeof(command_.local_key))
        && !std::memcmp(target_key.data(), command_.target_key, sizeof(command_.target_key))
        && actor_key[1] == 53 && target_key[1] == 53 && target_key != actor_key
        && ReadText(actor + 0xc48, local_name) && ReadText(actor + 0xc90, local_server)
        && ReadText(target + 0xc48, target_name) && ReadText(target + 0xc90, target_server)
        && wire::IdentitiesMatch(command_, local_name.View(), local_server.View(),
                                 target_name.View(), target_server.View());
}
bool NativeTarget::Current() noexcept {
    if (!Available() || !Owner() || !current_ || !current_(context_)
        || !movement::NativeMovementLifetimeCurrent(scene_) || !RawCurrent(selected_)) { return false; }
    party::Snapshot fresh{};
    return party::Capture(base_, scene_, fresh) && party::Equal(party_, fresh)
        && !party::Protected(fresh, {command_.target_key[0], command_.target_key[1]})
        && (!target_ || Identity()) && RawCurrent(selected_)
        && current_(context_) && movement::NativeMovementLifetimeCurrent(scene_);
}
bool NativeTarget::Gate(void* context) noexcept { return static_cast<NativeTarget*>(context)->Current(); }
bool NativeTarget::AppendGate(void* context) noexcept {
    auto& self = *static_cast<NativeTarget*>(context);
    // Executed under the native outbound queue lock. No runtime/party/fence lock,
    // BCrypt, native call or allocation is permitted here. D0 already won entry.
    return !self.faulted_ && self.append_current_ && self.append_current_(self.context_)
        && self.RawCurrent(true);
}
bool NativeTarget::Position(movement::GroundPoint& point) const noexcept {
    std::uintptr_t component = 0, pose = 0, parent = 0, table = 0, getter = 0;
    return Read(scene_.actor, table) && Read(table + 0x58, getter) && getter == base_ + 0xa3d0
        && Read(scene_.actor + 0x4b0, component) && Read(component, pose)
        && Read(pose + 8, parent) && parent == scene_.parent && Read(pose + 0x20, point)
        && std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z)
        && point.x >= 0 && point.x <= 200000 && point.z <= 0 && point.z >= -200000
        && point.y >= -2000 && point.y <= 20000;
}
bool NativeTarget::Retain(void*& value) {
    const auto object = reinterpret_cast<std::uintptr_t>(value);
    std::uintptr_t table = 0; std::int32_t offset = 0;
    if (!Read(object + 8, table) || !Read(table + 4, offset)) { return false; }
    const auto adjusted = static_cast<std::int64_t>(object) + 8 + offset;
    if (adjusted < 0x10000 || adjusted > 0x7fff0000 - 8 || adjusted % 4) { return false; }
    calls_.retain(reinterpret_cast<void*>(static_cast<std::uintptr_t>(adjusted)), &value);
    return true;
}
void NativeTarget::ClearQuery() {
    if (!list_.sentinel) { return; }
    auto* previous = list_.sentinel;
    auto* node = list_.sentinel->next;
    std::size_t count = 0;
    while (node != list_.sentinel) {
        if (++count > 8192 || node->previous != previous) { faulted_ = true; return; }
        auto* next = node->next;
        previous = node;
        calls_.release(&node->object, nullptr);
        calls_.pool_return(node, sizeof(Node)); node = next;
    }
    calls_.pool_return(list_.sentinel, sizeof(Node)); list_.sentinel = nullptr;
}
void NativeTarget::ClearImpl() {
    ClearQuery();
    if (faulted_) { return; }
    if (selection_argument_) { calls_.release(&selection_argument_, nullptr); }
    if (target_) { calls_.release(&target_, nullptr); }
    if (actor_) { calls_.release(&actor_, nullptr); }
    selected_ = false;
}
bool NativeTarget::ClearCxx() noexcept {
    try { ClearImpl(); return !faulted_; }
    catch (...) { faulted_ = true; return false; }
}
bool NativeTarget::Clear() noexcept {
    if (faulted_ || !Owner() || running_) { return false; }
    running_ = true;
    bool result = false;
    __try { result = ClearCxx(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; }
    running_ = false;
    return result;
}
NativeTarget::Result NativeTarget::Run() {
    if (!party::Capture(base_, scene_, party_)
        || party::Protected(party_, {command_.target_key[0], command_.target_key[1]})
        || !Current()) { return {O::stale}; }
    actor_ = reinterpret_cast<void*>(scene_.actor);
    if (!Retain(actor_)) { actor_ = nullptr; return {O::unavailable}; }
    movement::GroundPoint origin{};
    if (!Current() || !Position(origin)) { return {O::stale}; }
    unsigned char allocator = 0;
    calls_.construct(&list_, &allocator);
    const movement::GroundPoint minimum{(std::max)(0.0f, origin.x - 1024), -2000,
        (std::max)(-200000.0f, origin.z - 1024)};
    const movement::GroundPoint maximum{(std::min)(200000.0f, origin.x + 1024), 20000,
        (std::min)(0.0f, origin.z + 1024)};
    if (!Current()) { return {O::stale}; }
    calls_.query(reinterpret_cast<void*>(scene_.world), &minimum, &maximum, &list_);
    if (!list_.sentinel) { faulted_ = true; return {O::unavailable}; }
    auto* previous = list_.sentinel;
    std::size_t count = 0, matches = 0;
    for (auto* node = list_.sentinel->next; node != list_.sentinel; node = node->next) {
        if (++count > 8192 || node->previous != previous) { faulted_ = true; return {O::unavailable}; }
        std::uintptr_t table = 0;
        const auto object = reinterpret_cast<std::uintptr_t>(node->object);
        if (!Read(object, table)) { faulted_ = true; return {O::unavailable}; }
        if (table == base_ + 0x114165c) {
            std::array<std::uint32_t, 2> key{};
            if (!Read(object + 0x18, key)) { faulted_ = true; return {O::unavailable}; }
            if (!std::memcmp(key.data(), command_.target_key, sizeof(command_.target_key))) {
                if (++matches == 1) { target_ = node->object; node->object = nullptr; }
            }
        }
        previous = node;
    }
    if (list_.sentinel->previous != previous) { faulted_ = true; return {O::unavailable}; }
    ClearQuery();
    if (matches != 1 || faulted_ || !Current() || !Identity()) { return {O::stale}; }
    selection_argument_ = target_;
    if (!Retain(selection_argument_)) { selection_argument_ = nullptr; return {O::unavailable}; }
    if (!Current()) { return {O::stale}; }
    auto* argument = selection_argument_; selection_argument_ = nullptr;
    calls_.select(argument); selected_ = true;
    if (!Current() || !enter_ || !enter_(context_) || !Current()) { return {O::stale}; }
    std::uintptr_t writer = 0, container = 0;
    if (!Read(base_ + 0x16ab88c, writer) || !Read(writer + 0x44, container)) { return {O::unavailable}; }
    submission::Context context{};
    context.actor = scene_.actor; context.target = reinterpret_cast<std::uintptr_t>(target_);
    context.writer = writer; context.container = container;
    std::memcpy(context.local_key.data(), command_.local_key, sizeof(command_.local_key));
    std::memcpy(context.target_key.data(), command_.target_key, sizeof(command_.target_key));
    context.current = &Gate; context.append_current = &AppendGate; context.context = this;
    context.receipt = &submission_receipt_;
    submission::Scope scope(context);
    const std::array<std::uint32_t, 9> action{0x60f};
    dispatched_ = true;
    (void)calls_.dispatch(action.data(), reinterpret_cast<void*>(scene_.window));
    const auto receipt = scope.Finish();
    if (!Current()) { return {O::uncertain, receipt.append_observed}; }
    if (receipt.result == submission::Result::queued) { return {O::client_outbound_queued, true}; }
    if (receipt.result == submission::Result::no_submission && !receipt.native_entered) {
        return {O::native_rejected};
    }
    return {receipt.result == submission::Result::denied ? O::stale : O::uncertain, receipt.append_observed};
}
NativeTarget::Result NativeTarget::RunCxx() noexcept {
    try { return Run(); }
    catch (...) { faulted_ = true; return {dispatched_ ? O::uncertain : O::unavailable, submission_receipt_.append_observed}; }
}
NativeTarget::Result NativeTarget::Guarded() noexcept {
    submission::Boundary boundary;
    Result result{};
    __try {
        __try { result = RunCxx(); }
        __finally { boundary.Restore(); }
    }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        faulted_ = true;
        result = {dispatched_ ? O::uncertain : O::unavailable, submission_receipt_.append_observed};
    }
    return result;
}
NativeTarget::Result NativeTarget::Attack(const movement::NativeScene& scene, const wire::Command& command,
    Admission current, Admission enter, Admission append_current, void* context) noexcept {
    if (!Available() || !Owner() || running_ || list_.sentinel || actor_ || target_
        || !current || !enter || !append_current || !submission::Ready()) { return {O::unavailable}; }
    scene_ = scene; command_ = command; current_ = current; enter_ = enter;
    append_current_ = append_current; context_ = context;
    submission_receipt_ = {};
    selected_ = dispatched_ = false; running_ = true;
    const auto result = Guarded(); running_ = false;
    return result;
}
bool NativeTarget::ReadState(const movement::NativeScene& scene, State& out) const noexcept {
    std::uintptr_t table = 0, state = 0, target = 0;
    State next{};
    if (!Read(scene.actor, table) || table != base_ + 0x114165c
        || !Read(scene.actor + 0xad0, state) || !Read(state + 0x18, next.mode)
        || !Read(state + 0x20, next.action) || !Read(scene.actor + 0xaf8, target)) { return false; }
    next.target = target != 0; out = next; return true;
}
bool NativeTarget::CombatTargetCurrent() const noexcept {
    std::uintptr_t target = 0;
    return Available() && target_ && RawCurrent(true)
        && Read(scene_.actor + 0xaf8, target) && target == reinterpret_cast<std::uintptr_t>(target_);
}
bool NativeTarget::CancelImpl(const movement::NativeScene& scene, Admission current, void* context, State& out) {
    if (!current || !current(context) || !movement::NativeMovementLifetimeCurrent(scene)
        || !ReadState(scene, out)) { return false; }
    if (out.mode == 2) {
        const std::array<std::uint32_t, 9> action{0x616};
        if (!current(context) || !movement::NativeMovementLifetimeCurrent(scene)) { return false; }
        (void)calls_.dispatch(action.data(), reinterpret_cast<void*>(scene.window));
    }
    return current(context) && movement::NativeMovementLifetimeCurrent(scene)
        && ReadState(scene, out) && out.mode == 1 && out.action == 1 && !out.target;
}
bool NativeTarget::CancelCxx(const movement::NativeScene& scene, Admission current, void* context, State& state) noexcept {
    try { return CancelImpl(scene, current, context, state); }
    catch (...) { faulted_ = true; return false; }
}
bool NativeTarget::Cancel(const movement::NativeScene& scene, Admission current, void* context, State& state) noexcept {
    if (!Available() || !Owner() || running_) { return false; }
    running_ = true;
    bool result = false;
    __try { result = CancelCxx(scene, current, context, state); }
    __except(EXCEPTION_EXECUTE_HANDLER) { faulted_ = true; }
    running_ = false;
    return result;
}
}
