#pragma once
#include "combat_fence.h"
#include "movement_wire.h"
#include <bcrypt.h>

namespace wonderbane::extension::combat::wire {
using Digest = std::array<std::uint8_t, 32>;
enum class Verb : std::uint32_t { start = 34, status = 35, cancel = 36 };
#pragma pack(push, 1)
struct Command {
    movement::wire::Host host{};
    std::uint64_t window = 0;
    movement::wire::Grant grant{};
    std::array<std::uint8_t, 16> request{};
    Digest binding_digest{}, local_name{}, server{}, target_name{};
    std::uint32_t local_key[2]{}, target_key[2]{};
    std::uint64_t revision = 0;
    Digest store{}, owner{}, entry{}, operation{};
    std::uint8_t reserved[40]{};
};
#pragma pack(pop)
static_assert(sizeof(Command) == 576 && offsetof(Command, request) == 240);
static_assert(offsetof(Command, local_key) == 384 && offsetof(Command, store) == 408);

inline bool Hash(const void* bytes, ULONG size, Digest& out) noexcept {
    BCRYPT_ALG_HANDLE algorithm = nullptr; BCRYPT_HASH_HANDLE hash = nullptr;
    Digest next{};
    const bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<PUCHAR>(static_cast<const unsigned char*>(bytes)), size, 0) >= 0
        && BCryptFinishHash(hash, next.data(), static_cast<ULONG>(next.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); }
    if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    if (ok) { out = next; }
    return ok;
}
inline bool IdentityDigest(const std::uint16_t* units, std::size_t count, Digest& out) noexcept {
    if (!units || !count || count > 64) { return false; }
    for (std::size_t i = 0; i < count; ++i) {
        const auto value = units[i];
        if (!value || (value >= 0xdc00 && value <= 0xdfff)) { return false; }
        if (value >= 0xd800 && value <= 0xdbff) {
            if (++i == count || units[i] < 0xdc00 || units[i] > 0xdfff) { return false; }
        }
    }
    return Hash(units, static_cast<ULONG>(count * sizeof(*units)), out);
}
struct Text { const std::uint16_t* units = nullptr; std::size_t count = 0; };
// Exact json.dumps(..., ensure_ascii=True) encoding used by the existing durable
// owner and entry keys. Fixed storage bounds cover three maximally escaped strings.
struct IdentityJson {
    std::array<char, 2048> bytes{}; std::size_t count = 0;
    bool Append(char value) noexcept {
        if (count == bytes.size()) { return false; }
        bytes[count++] = value; return true;
    }
    bool Literal(const char* value) noexcept {
        for (; *value; ++value) { if (!Append(*value)) { return false; } } return true;
    }
    bool String(Text text) noexcept {
        if (!Append('"')) { return false; }
        constexpr char digits[] = "0123456789abcdef";
        for (std::size_t i = 0; i < text.count; ++i) {
            const auto v = text.units[i];
            const char short_escape = v == 8 ? 'b' : v == 9 ? 't' : v == 10 ? 'n'
                : v == 12 ? 'f' : v == 13 ? 'r' : 0;
            if (short_escape) { if (!Append('\\') || !Append(short_escape)) { return false; } }
            else if (v == '"' || v == '\\') {
                if (!Append('\\') || !Append(static_cast<char>(v))) { return false; }
            } else if (v < 0x20 || v >= 0x7f) {
                if (!Literal("\\u")) { return false; }
                for (int shift = 12; shift >= 0; shift -= 4) {
                    if (!Append(digits[(v >> shift) & 15])) { return false; }
                }
            } else if (!Append(static_cast<char>(v))) { return false; }
        }
        return Append('"');
    }
    bool Finish(Digest& out) const noexcept { return Hash(bytes.data(), static_cast<ULONG>(count), out); }
};
inline bool IdentitiesMatch(const Command& c, Text local_name, Text server,
                            Text target_name, Text target_server) noexcept {
    Digest local{}, shard{}, target{}, target_shard{}, owner{}, entry{};
    if (!IdentityDigest(local_name.units, local_name.count, local)
        || !IdentityDigest(server.units, server.count, shard)
        || !IdentityDigest(target_name.units, target_name.count, target)
        || !IdentityDigest(target_server.units, target_server.count, target_shard)
        || local != c.local_name || shard != c.server || target != c.target_name
        || target_shard != shard) { return false; }
    IdentityJson owner_json;
    if (!owner_json.Append('[') || !owner_json.String(server) || !owner_json.Literal(", ")
        || !owner_json.String(local_name) || !owner_json.Append(']')
        || !owner_json.Finish(owner) || owner != c.owner) { return false; }
    IdentityJson entry_json;
    if (!entry_json.Literal("[\"player\", ") || !entry_json.String(server)
        || !entry_json.Literal(", \"")) { return false; }
    constexpr char digits[] = "0123456789abcdef";
    for (std::size_t index = 0; index != 2; ++index) {
        if (index && !entry_json.Append(':')) { return false; }
        for (int shift = 28; shift >= 0; shift -= 4) {
            if (!entry_json.Append(digits[(c.target_key[index] >> shift) & 15])) { return false; }
        }
    }
    return entry_json.Literal("\"]") && entry_json.Finish(entry) && entry == c.entry;
}
// Call with the channel's independently verified native process lifetime. Mapping
// digest is a reference pin, never a replacement for full equality or live gates.
inline bool BindingFor(const Command& c, std::uint32_t client_pid,
                       std::uint64_t client_creation, fence::Binding& out) noexcept {
    movement::Grant grant{}; Digest operation{}, binding_digest{};
    if (!movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || !movement::wire::Decode(c.grant, grant) || grant.owner != movement::Owner::automation
        || !movement::wire::Zero(c.reserved, sizeof(c.reserved))
        || movement::wire::Zero(c.local_name.data(), c.local_name.size())
        || movement::wire::Zero(c.server.data(), c.server.size())
        || movement::wire::Zero(c.target_name.data(), c.target_name.size())
        || !Hash(&c.grant.token, sizeof(c.grant.token), operation) || operation != c.operation) { return false; }
    fence::Binding b{};
    b.client_pid = client_pid; b.client_creation = client_creation;
    b.producer_pid = c.host.process; b.producer_creation = c.host.creation;
    b.producer_generation = c.host.generation;
    b.movement_generation = grant.generation; b.scene = grant.scene; b.revision = c.revision;
    std::memcpy(b.request, c.request.data(), sizeof(b.request));
    std::memcpy(b.store, c.store.data(), sizeof(b.store));
    std::memcpy(b.owner, c.owner.data(), sizeof(b.owner));
    std::memcpy(b.entry, c.entry.data(), sizeof(b.entry));
    std::memcpy(b.operation, c.operation.data(), sizeof(b.operation));
    std::memcpy(b.local_key, c.local_key, sizeof(b.local_key));
    std::memcpy(b.target_key, c.target_key, sizeof(b.target_key));
    std::memcpy(b.target_name, c.target_name.data(), sizeof(b.target_name));
    if (!fence::Valid(b) || !Hash(&b, sizeof(b), binding_digest) || binding_digest != c.binding_digest) { return false; }
    out = b; return true;
}
}
