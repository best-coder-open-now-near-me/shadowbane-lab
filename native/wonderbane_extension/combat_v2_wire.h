#pragma once
#include "combat_v3_fence.h"
#include "movement_wire.h"
#include <bcrypt.h>

namespace wonderbane::extension::combat::v2::wire {
namespace fence = ::wonderbane::extension::combat::v3::fence;
using Digest = std::array<std::uint8_t, 32>;
using Id = std::array<std::uint8_t, 16>;
enum class Verb : std::uint32_t { bind = 37, submit, action_status, cancel_action, engagement_status, stop };
enum class Authority : std::uint32_t { manual_player = 1, npc = 2 };
enum class Action : std::uint32_t { none, attack, cast };
enum class Outcome : std::uint32_t {
    observed, client_outbound_queued, stale, unavailable, invalid, pending,
    uncertain, exhausted, engagement_closed, native_rejected, bound,
    action_cancelled, deferred, history_expired
};
enum class Phase : std::uint32_t { unknown, bound, stopping, closed, retired, blocked };
enum class Entry : std::uint32_t { unknown, never_entered, entered };
enum class Closure : std::uint32_t { none, never_bound, native_stopped, scene_retired, history_expired };
enum Flag : std::uint32_t { cleanup_required = 1, outbound_queued = 2, uncertain_history = 4 };
constexpr std::uint32_t receipt_signature = 0x57424331;
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
    std::uint32_t version = 2;
    Authority authority = Authority::npc;
    Action action = Action::none;
    std::uint32_t power_id = 0, actor_hint = 0, target_hint = 0;
    Id engagement{};
};
// Every structured reply echoes the immutable command, including rejection.
// Queued means local native outbound queue admission, never server acceptance.
struct Receipt {
    std::array<std::uint8_t, 16> request{};
    movement::wire::Host host{};
    std::uint64_t window = 0;
    Outcome outcome = Outcome::unavailable;
    std::uint32_t flags = 0;
    movement::wire::Grant grant{};
    std::uint64_t revision = 0;
    std::uint32_t local_key[2]{}, target_key[2]{};
    std::uint32_t signature = receipt_signature;
    Phase phase = Phase::unknown;
    std::uint32_t mode = 0, action_state = 0, combat_target_present = 0;
    Digest binding_digest{};
    std::uint32_t version = 2;
    Authority authority = Authority::npc;
    Action action = Action::none;
    std::uint32_t power_id = 0;
    Id engagement{};
    Entry entry = Entry::unknown;
    Verb verb = Verb::engagement_status;
    Closure closure = Closure::none;
};
#pragma pack(pop)
static_assert(sizeof(Command) == 576 && offsetof(Command, request) == 240);
static_assert(offsetof(Command, local_key) == 384 && offsetof(Command, store) == 408);
static_assert(sizeof(Receipt) == 384 && offsetof(Receipt, grant) == 48);
static_assert(offsetof(Receipt, revision) == 264 && offsetof(Receipt, signature) == 288);
static_assert(offsetof(Receipt, binding_digest) == 308 && offsetof(Receipt, version) == 340);

static_assert(offsetof(Command, version) == 536 && offsetof(Command, engagement) == 560);
static_assert(offsetof(Receipt, engagement) == 356 && offsetof(Receipt, entry) == 372
    && offsetof(Receipt, verb) == 376 && offsetof(Receipt, closure) == 380);
inline bool ActionVerb(Verb verb) noexcept {
    return verb == Verb::submit || verb == Verb::action_status || verb == Verb::cancel_action;
}
inline bool Valid(Verb verb) noexcept { return verb >= Verb::bind && verb <= Verb::stop; }
inline bool Valid(Authority authority) noexcept {
    return authority == Authority::manual_player || authority == Authority::npc;
}
inline bool Valid(Action action, std::uint32_t power, Verb verb) noexcept {
    return Valid(verb) && (ActionVerb(verb)
        ? ((action == Action::attack && !power) || (action == Action::cast && power))
        : action == Action::none && !power);
}
inline Receipt Reply(const Command& command, Verb verb, Outcome outcome) noexcept {
    Receipt result{};
    result.request = command.request; result.host = command.host; result.window = command.window;
    result.outcome = outcome; result.grant = command.grant; result.revision = command.revision;
    std::memcpy(result.local_key, command.local_key, sizeof(result.local_key));
    std::memcpy(result.target_key, command.target_key, sizeof(result.target_key));
    result.binding_digest = command.binding_digest;
    result.authority = command.authority; result.action = command.action; result.power_id = command.power_id;
    result.engagement = command.engagement; result.verb = verb;
    return result;
}
inline bool Valid(const Receipt& r) noexcept {
    movement::Grant grant{};
    const bool owned = r.phase == Phase::bound || r.phase == Phase::stopping || r.phase == Phase::blocked;
    const bool closure = (r.phase == Phase::closed && (r.closure == Closure::never_bound
        || r.closure == Closure::native_stopped))
        || (r.phase == Phase::retired && r.closure == Closure::scene_retired)
        || (r.phase == Phase::unknown && r.closure == Closure::history_expired && r.outcome == Outcome::history_expired)
        || (r.phase != Phase::closed && r.phase != Phase::retired && r.closure == Closure::none);
    return r.signature == receipt_signature && r.version == 2 && Valid(r.authority)
        && Valid(r.action, r.power_id, r.verb) && r.outcome <= Outcome::history_expired
        && r.phase <= Phase::blocked && r.entry <= Entry::entered && !(r.flags & ~7U)
        && r.combat_target_present <= 1 && movement::wire::Valid(r.host)
        && r.window && r.window <= UINT32_MAX && movement::wire::Decode(r.grant, grant)
        && grant.owner == movement::Owner::automation
        && !movement::wire::Zero(r.request.data(), r.request.size())
        && !movement::wire::Zero(r.engagement.data(), r.engagement.size())
        && !movement::wire::Zero(r.binding_digest.data(), r.binding_digest.size())
        && r.local_key[0] && r.local_key[1] == 53 && r.target_key[0]
        && r.target_key[1] == (r.authority == Authority::manual_player ? 53U : 37U)
        && std::memcmp(r.local_key, r.target_key, sizeof(r.local_key))
        && (r.authority == Authority::manual_player ? r.revision != 0 : r.revision == 0)
        && closure && (r.closure != Closure::never_bound || r.entry != Entry::entered)
        && static_cast<bool>(r.flags & cleanup_required) == owned
        && (!(r.flags & outbound_queued) || r.entry == Entry::entered)
        && (r.action != Action::none || (r.entry == Entry::unknown && !(r.flags & (outbound_queued|uncertain_history))))
        && (r.outcome != Outcome::client_outbound_queued || (r.flags & outbound_queued))
        && (r.outcome != Outcome::action_cancelled || (r.entry == Entry::never_entered && !(r.flags & (outbound_queued|uncertain_history))))
        && (r.outcome != Outcome::deferred || (r.entry == (r.action == Action::none ? Entry::unknown : Entry::never_entered)
            && !(r.flags & (outbound_queued|uncertain_history))
            && (r.action != Action::none || (r.verb == Verb::bind && r.phase == Phase::closed
                && r.closure == Closure::never_bound))))
        && (r.outcome != Outcome::history_expired || (r.entry == Entry::unknown && !r.flags
            && r.phase == Phase::unknown && r.closure == Closure::history_expired));
}
inline bool Correlated(const Command& c, Verb verb, const Receipt& r) noexcept {
    return Valid(r) && r.request == c.request && r.verb == verb && r.engagement == c.engagement
        && r.authority == c.authority && r.action == c.action && r.power_id == c.power_id
        && !std::memcmp(&r.host,&c.host,sizeof(c.host)) && r.window == c.window
        && !std::memcmp(&r.grant,&c.grant,sizeof(c.grant)) && r.revision == c.revision
        && !std::memcmp(r.local_key,c.local_key,sizeof(c.local_key))
        && !std::memcmp(r.target_key,c.target_key,sizeof(c.target_key)) && r.binding_digest == c.binding_digest;
}
inline bool SameEngagement(Command a, Command b) noexcept {
    a.request = b.request = {}; a.action = b.action = Action::none; a.power_id = b.power_id = 0;
    return !std::memcmp(&a,&b,sizeof(a));
}
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
inline bool ActorIdentityMatches(const Command& c, Text local_name, Text server) noexcept {
    Digest local{}, shard{}, owner{}; IdentityJson json;
    return IdentityDigest(local_name.units,local_name.count,local) && local == c.local_name
        && IdentityDigest(server.units,server.count,shard) && shard == c.server
        && json.Append('[') && json.String(server) && json.Literal(", ")
        && json.String(local_name) && json.Append(']') && json.Finish(owner) && owner == c.owner;
}
// Reconstruct with independently verified process lifetime. The digest pins the
// complete normalized engagement ticket, never just its ordinal.
inline bool BindingFor(const Command& c, std::uint32_t client_pid,
    std::uint64_t client_creation, fence::Binding& out) noexcept {
    movement::Grant grant{}; Digest operation{}, digest{};
    if (c.version != 2 || !Valid(c.authority) || c.action > Action::cast
        || ((c.action == Action::cast) != (c.power_id != 0))
        || !movement::wire::Valid(c.host) || !c.window || c.window > UINT32_MAX
        || !movement::wire::Decode(c.grant,grant) || grant.owner != movement::Owner::automation
        || movement::wire::Zero(c.request.data(),c.request.size())
        || movement::wire::Zero(c.local_name.data(),c.local_name.size())
        || movement::wire::Zero(c.server.data(),c.server.size())
        || !Hash(&c.grant.token,sizeof(c.grant.token),operation) || operation != c.operation) { return false; }
    fence::Binding b{};
    b.client_pid=client_pid; b.client_creation=client_creation;
    b.producer_pid=c.host.process; b.producer_creation=c.host.creation; b.producer_generation=c.host.generation;
    b.movement_generation=grant.generation; b.scene=grant.scene; b.revision=c.revision;
    std::memcpy(b.engagement,c.engagement.data(),sizeof(b.engagement));
    std::memcpy(b.store,c.store.data(),sizeof(b.store)); std::memcpy(b.owner,c.owner.data(),sizeof(b.owner));
    std::memcpy(b.entry,c.entry.data(),sizeof(b.entry)); std::memcpy(b.operation,c.operation.data(),sizeof(b.operation));
    std::memcpy(b.local_key,c.local_key,sizeof(b.local_key)); std::memcpy(b.target_key,c.target_key,sizeof(b.target_key));
    std::memcpy(b.target_name,c.target_name.data(),sizeof(b.target_name));
    b.authority=static_cast<std::uint32_t>(c.authority); b.actor_hint=c.actor_hint; b.target_hint=c.target_hint;
    if (!fence::HashBinding(b,digest) || digest != c.binding_digest) { return false; }
    out=b; return true;
}
}
