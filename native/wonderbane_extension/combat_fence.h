#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

namespace wonderbane::extension::combat::fence {
constexpr std::uint32_t schema = 2, size = 320;
enum class State : std::uint32_t { registering, pending, entered, revoked, entered_revoked };
#pragma pack(push, 1)
struct Binding {
    char magic[8]{'W','B','C','F','N','C','2',0};
    std::uint32_t version = schema, bytes = size;
    State state = State::registering;
    std::uint32_t reserved = 0, client_pid = 0, producer_pid = 0;
    std::uint64_t client_creation = 0, producer_creation = 0, producer_generation = 0;
    std::uint64_t movement_generation = 0, scene = 0, revision = 0;
    std::uint8_t request[16]{}, store[32]{}, owner[32]{}, entry[32]{}, operation[32]{};
    std::uint32_t local_key[2]{}, target_key[2]{};
    std::uint8_t target_name[32]{}, padding[48]{};
};
#pragma pack(pop)
static_assert(sizeof(Binding) == size && offsetof(Binding, state) == 16);
static_assert(offsetof(Binding, request) == 80 && offsetof(Binding, store) == 96);
static_assert(offsetof(Binding, operation) == 192 && offsetof(Binding, local_key) == 224);
static_assert(offsetof(Binding, target_name) == 240 && offsetof(Binding, padding) == 272);
template<std::size_t N> inline bool Any(const std::uint8_t (&value)[N]) noexcept {
    for (const auto byte : value) { if (byte) { return true; } } return false;
}
inline bool Valid(const Binding& b) noexcept {
    constexpr char magic[8]{'W','B','C','F','N','C','2',0};
    return !std::memcmp(b.magic, magic, 8) && b.version == schema && b.bytes == size
        && b.state <= State::entered_revoked && !b.reserved && !Any(b.padding)
        && b.client_pid && b.producer_pid && b.client_creation && b.producer_creation
        && b.producer_generation && b.movement_generation && b.scene && b.revision
        && Any(b.request) && Any(b.store) && Any(b.owner) && Any(b.entry) && Any(b.operation) && Any(b.target_name)
        && b.local_key[0] && b.local_key[1] && b.target_key[0] && b.target_key[1] == 53
        && std::memcmp(b.local_key, b.target_key, sizeof(b.local_key));
}
inline bool Same(Binding a, Binding b) noexcept {
    a.state = b.state = State::registering;
    return !std::memcmp(&a, &b, sizeof(a));
}
inline std::wstring Name(const Binding& b) {
    std::wstring result = L"Local\\WonderBane.CombatFence.v2.";
    constexpr wchar_t digits[] = L"0123456789abcdef";
    for (auto byte : b.request) { result += digits[byte >> 4]; result += digits[byte & 15]; }
    return result;
}
inline std::uint64_t Creation(HANDLE process) noexcept {
    FILETIME creation{}, exit{}, kernel{}, user{};
    if (!GetProcessTimes(process, &creation, &exit, &kernel, &user)) { return 0; }
    return (static_cast<std::uint64_t>(creation.dwHighDateTime) << 32) | creation.dwLowDateTime;
}
inline State Revoked(State state) noexcept {
    return state == State::entered || state == State::entered_revoked
        ? State::entered_revoked : State::revoked;
}
enum class Result { admitted, busy, unavailable, invalid, not_pending, revoked };

// Consumer opens only. No callbacks, file locks, blocking waits, or object creation.
// Fresh native lease/Grant/party/target validation remains the caller's obligation.
// Retain this object through the cancellation transaction, including entered-revoked.
class Ticket final {
public:
    Ticket() = default;
    Ticket(const Ticket&) = delete;
    Ticket& operator=(const Ticket&) = delete;
    ~Ticket() { Close(); }
    bool Open(const Binding& expected) {
        Close();
        if (!Valid(expected) || expected.client_pid != GetCurrentProcessId()
            || expected.client_creation != Creation(GetCurrentProcess())) { return false; }
        expected_ = expected;
        const auto name = Name(expected);
        mutex_ = OpenMutexW(SYNCHRONIZE | MUTEX_MODIFY_STATE, FALSE, (name + L".lock").c_str());
        if (!mutex_) { Close(); return false; }
        mapping_ = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, name.c_str());
        if (!mapping_) { Close(); return false; }
        view_ = static_cast<Binding*>(MapViewOfFile(mapping_, FILE_MAP_READ | FILE_MAP_WRITE,
                                                   0, 0, sizeof(Binding)));
        producer_ = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                                FALSE, expected.producer_pid);
        if (!view_ || !producer_) { Close(); return false; }
        if (Creation(producer_) != expected.producer_creation) { Close(); return false; }
        return true;
    }
    Result TryEnter(const Binding& current) noexcept {
        if (!Valid(current) || !Same(current, expected_)) { return Result::invalid; }
        return Transition(true, nullptr);
    }
    Result Inspect(State& state) noexcept { return Transition(false, &state); }
    void Close() noexcept {
        if (view_) { UnmapViewOfFile(view_); view_ = nullptr; }
        for (auto* handle : {&producer_, &mapping_, &mutex_}) {
            if (*handle) { CloseHandle(*handle); *handle = nullptr; }
        }
    }
private:
    Result Transition(bool enter, State* observed) noexcept {
        if (!view_ || !mutex_ || !producer_) { return Result::unavailable; }
        const auto wait = WaitForSingleObject(mutex_, 0);
        if (wait == WAIT_TIMEOUT) { return Result::busy; }
        if (wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED) { return Result::unavailable; }
        Result result = Result::invalid;
        if (Valid(*view_) && Same(*view_, expected_)) {
            if (wait == WAIT_ABANDONED || WaitForSingleObject(producer_, 0) != WAIT_TIMEOUT) {
                view_->state = Revoked(view_->state);
            }
            if (observed) { *observed = view_->state; }
            if (view_->state == State::revoked || view_->state == State::entered_revoked) {
                result = Result::revoked;
            } else if (!enter) { result = Result::not_pending; }
            else if (view_->state != State::pending) { result = Result::not_pending; }
            else { view_->state = State::entered; result = Result::admitted; }
        }
        if (!ReleaseMutex(mutex_)) { return Result::unavailable; }
        return result;
    }
    Binding expected_{};
    HANDLE mutex_ = nullptr, mapping_ = nullptr, producer_ = nullptr;
    Binding* view_ = nullptr;
};
} // namespace wonderbane::extension::combat::fence
