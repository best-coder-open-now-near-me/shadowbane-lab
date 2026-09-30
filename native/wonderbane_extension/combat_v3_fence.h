#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <array>
#include <bcrypt.h>

namespace wonderbane::extension::combat::v3::fence {
constexpr std::uint32_t schema = 3, size = 320;
enum class State : std::uint32_t { registering, pending, entered, revoked, entered_revoked };
#pragma pack(push, 1)
struct Binding {
    char magic[8]{'W','B','C','F','N','C','3',0};
    std::uint32_t version = schema, bytes = size;
    State state = State::registering;
    std::uint32_t reserved = 0, client_pid = 0, producer_pid = 0;
    std::uint64_t client_creation = 0, producer_creation = 0, producer_generation = 0;
    std::uint64_t movement_generation = 0, scene = 0, revision = 0;
    std::uint8_t engagement[16]{}, store[32]{}, owner[32]{}, entry[32]{}, operation[32]{};
    std::uint32_t local_key[2]{}, target_key[2]{};
    std::uint8_t target_name[32]{};
    std::uint32_t authority = 0, actor_hint = 0, target_hint = 0;
    std::uint8_t padding[36]{};
};
#pragma pack(pop)
static_assert(sizeof(Binding) == size && offsetof(Binding, state) == 16);
static_assert(offsetof(Binding, engagement) == 80 && offsetof(Binding, store) == 96);
static_assert(offsetof(Binding, operation) == 192 && offsetof(Binding, local_key) == 224);
static_assert(offsetof(Binding, target_name) == 240 && offsetof(Binding, authority) == 272 && offsetof(Binding, padding) == 284);
template<std::size_t N> inline bool Any(const std::uint8_t (&value)[N]) noexcept {
    for (const auto byte : value) { if (byte) { return true; } } return false;
}
inline bool Address(std::uint32_t value) noexcept {
    return value >= 0x10000 && value <= 0x7fff0000 - 4 && value % 4 == 0;
}
inline bool Valid(const Binding& b) noexcept {
    constexpr char magic[8]{'W','B','C','F','N','C','3',0};
    const bool manual = b.authority == 1 && b.target_key[1] == 53 && b.revision
        && Any(b.store) && Any(b.entry) && Any(b.target_name);
    const bool npc = b.authority == 2 && b.target_key[1] == 37 && !b.revision
        && !Any(b.store) && !Any(b.entry) && !Any(b.target_name);
    return !std::memcmp(b.magic, magic, 8) && b.version == schema && b.bytes == size
        && b.state <= State::entered_revoked && !b.reserved && !Any(b.padding)
        && b.client_pid && b.producer_pid && b.client_creation && b.producer_creation
        && b.producer_generation
        && b.movement_generation && b.scene && Any(b.engagement) && Any(b.owner) && Any(b.operation)
        && b.local_key[0] && b.local_key[1] == 53 && b.target_key[0] && (manual || npc)
        && std::memcmp(b.local_key, b.target_key, sizeof(b.local_key))
        && Address(b.actor_hint) && Address(b.target_hint) && b.actor_hint != b.target_hint;
}
using Digest = std::array<std::uint8_t, 32>;
inline bool Hash(const void* bytes, ULONG byte_count, Digest& out) noexcept {
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{}; Digest next{};
    const bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<PUCHAR>(static_cast<const unsigned char*>(bytes)), byte_count, 0) >= 0
        && BCryptFinishHash(hash, next.data(), static_cast<ULONG>(next.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); } if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    if (ok) { out = next; } return ok;
}
inline bool HashBinding(Binding binding, Digest& out) noexcept {
    binding.state = State::registering; return Valid(binding) && Hash(&binding, sizeof(binding), out);
}
inline bool Same(Binding a, Binding b) noexcept {
    a.state = b.state = State::registering;
    return !std::memcmp(&a, &b, sizeof(a));
}
inline std::wstring Name(const Binding& b) {
    Digest digest{};
    if (!HashBinding(b, digest)) { return {}; }
    std::wstring result = L"Local\\WonderBane.CombatFence.v3.";
    constexpr wchar_t digits[] = L"0123456789abcdef";
    for (auto byte : digest) { result += digits[byte >> 4]; result += digits[byte & 15]; }
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
        if (name.empty()) { Close(); return false; }
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
    Result TryAdmit(const Binding& current_binding, bool retained) noexcept {
        if (!Valid(current_binding) || !Same(current_binding, expected_)) { return Result::invalid; }
        return Transition(true, retained, nullptr);
    }
    Result Inspect(State& state) noexcept { return Transition(false, false, &state); }
    void Close() noexcept {
        if (view_) { UnmapViewOfFile(view_); view_ = nullptr; }
        for (auto* handle : {&producer_, &mapping_, &mutex_}) {
            if (*handle) { CloseHandle(*handle); *handle = nullptr; }
        }
    }
private:
    Result Transition(bool enter, bool retained, State* observed) noexcept {
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
            else if (view_->state == State::entered && retained) { result = Result::admitted; }
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
} // namespace wonderbane::extension::combat::v3::fence
