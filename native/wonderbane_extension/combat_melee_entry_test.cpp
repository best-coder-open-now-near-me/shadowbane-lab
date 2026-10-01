#include "combat_melee_entry.h"
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstring>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace melee = wonderbane::extension::combat::melee;
namespace submission = wonderbane::extension::combat::submission;
namespace {
void Check(bool ok, const char* error) { if (!ok) { throw std::runtime_error(error); } }
template<class T> T& At(void* object, std::size_t offset) {
    return *reinterpret_cast<T*>(static_cast<unsigned char*>(object) + offset);
}
using Key = std::array<std::uint32_t, 2>;
using Iterator = std::array<std::uintptr_t, 3>;
std::uintptr_t image{};
std::array<unsigned char, 0xe00> actor{}, target{};
std::array<std::uintptr_t, 64> actor_table{}, target_table{};
std::array<std::int32_t, 4> offsets{0, 8, 8, 0x18};
std::array<std::uint32_t, 12> actor_state{};
struct Message { std::uintptr_t* table{}; unsigned refs{}; } message;
std::array<std::uintptr_t, 3> message_table{};
struct Counts {
    unsigned toggle{}, factory{}, retain{}, sends{}, releases{}, followup{};
    bool operator==(const Counts&) const = default;
} counts;
std::vector<unsigned> trace;
bool live = true, toggle_accepted = true, actor_peace = false, target_peace = false;
bool invalidate_toggle = false, invalidate_factory = false, invalidate_send = false, throw_factory = false;
unsigned controller{};
bool Current(void*) noexcept { return live; }
bool __fastcall Mask(void* self, void*, std::uint32_t mask) { trace.push_back(mask); return (At<std::uint32_t>(self, 4) & mask) != 0; }
std::uint32_t __fastcall Mode(void*, void*) { trace.push_back(1); return actor_state[0x18 / 4]; }
std::uint32_t __fastcall State(void*, void*) { trace.push_back(2); return actor_state[0x10 / 4]; }
void __fastcall Toggle(void* self, void*, bool requested, bool force) {
    Check(self == actor.data() && requested && force, "wrong native mode ABI");
    trace.push_back(3); ++counts.toggle; if (toggle_accepted) { actor_state[0x18 / 4] = 2; }
    if (invalidate_toggle) { live = false; }
}
bool __fastcall Peace(void* self, void*) { trace.push_back(self == actor.data() ? 4U : 5U); return self == actor.data() ? actor_peace : target_peace; }
Iterator* __fastcall End(void*, void*, Iterator* out) { trace.push_back(6); *out = {0xdead, 0, 0}; return out; }
Iterator* __fastcall Find(void* self, void*, Iterator* out, const std::uint32_t* key) {
    trace.push_back(7); Check(key == reinterpret_cast<const std::uint32_t*>(image + 0x137314c), "wrong native property key");
    *out = {At<std::uint32_t>(self, 0) ? 0xbeefU : 0xdeadU, 0, 0}; return out;
}
Iterator* __fastcall CopyIterator(Iterator* self, void*, const Iterator* from) { *self = *from; return self; }
bool __fastcall Guard(void*, void*) { return true; }
Key* __fastcall ReadKey(void* self, void*, Key* out) { trace.push_back(8); *out = At<Key>(self, 0x18); return out; }
void* __fastcall Dereference(void** self, void*) { return *self; }
void __fastcall KeyDestructor(void*, void*) {}
void __fastcall Retain(void* self, void*, void**) {
    Check(self == &message && message.refs, "retain lost message ownership"); trace.push_back(9); ++message.refs; ++counts.retain;
}
void __fastcall Drop(void* self, void*, void** output) {
    Check(self == &message && message.refs && !*output, "release ABI/ownership changed");
    trace.push_back(10); --message.refs; ++counts.releases;
}
void* __fastcall Factory(void* self, void*, void** output, void* recipient, const void* key, bool send) {
    Check(self == actor.data() && recipient == target.data() && send, "wrong factory objects/ABI");
    Check(*static_cast<const Key*>(key) == At<Key>(target.data(), 0x18), "wrong factory key");
    Check(!message.refs, "factory reused live output");
    trace.push_back(11); ++counts.factory; message.refs = 1; *output = &message;
    if (invalidate_factory) { live = false; }
    if (throw_factory) { throw std::runtime_error("factory returned ownership then failed"); }
    return output;
}
void* __cdecl Controller() { trace.push_back(12); return &controller; }
void __fastcall Send(void* self, void*, void* request) {
    Check(self == &controller && request == &message && message.refs == 2, "wrong sender ownership/ABI");
    trace.push_back(13); ++counts.sends; void* empty{}; Drop(request, nullptr, &empty);
    if (invalidate_send) { live = false; }
}
void __fastcall Followup(void* self, void*) { Check(self == actor.data(), "wrong followup actor"); trace.push_back(14); ++counts.followup; }
void Jump(std::uintptr_t rva, std::uintptr_t destination) {
    auto* at = reinterpret_cast<unsigned char*>(image + rva); *at = 0xe9;
    const auto displacement = static_cast<std::int32_t>(destination - (image + rva + 5));
    std::memcpy(at + 1, &displacement, 4);
}
void Reset(unsigned flags, unsigned mode, unsigned state, bool blocked, bool special, bool property) {
    actor.fill(0); target.fill(0); actor_state.fill(0); counts = {}; trace.clear(); message.refs = 0;
    live = true; invalidate_toggle = invalidate_factory = invalidate_send = throw_factory = false;
    actor_state[0x18 / 4] = mode; actor_state[0x10 / 4] = state;
    for (auto* object : {actor.data(), target.data()}) {
        At<std::int32_t*>(object, 8) = offsets.data();
        At<Key>(object, 0x18) = object == actor.data() ? Key{100, 53} : Key{200, 53};
    }
    At<std::uintptr_t*>(actor.data(), 0) = actor_table.data();
    At<std::uintptr_t*>(target.data(), 0) = target_table.data();
    At<void*>(actor.data(), 0xad0) = actor_state.data();
    At<std::uint32_t>(actor.data(), 0xb04) = blocked ? 1U : 0U;
    At<std::uint32_t>(target.data(), 0x24) = flags;
    At<unsigned char>(target.data(), 0x680) = special ? 1 : 0;
    At<std::uint32_t>(target.data(), 0x34) = property ? 1U : 0U;
    *reinterpret_cast<void**>(image + 0x16a2d98) = actor.data();
    *reinterpret_cast<void**>(image + 0x16a2da4) = target.data();
}
void InstallPrimitives() {
    actor_table[0xd0 / 4] = reinterpret_cast<std::uintptr_t>(&Factory);
    actor_table[0xcc / 4] = reinterpret_cast<std::uintptr_t>(&Followup);
    actor_table[0xdc / 4] = target_table[0xdc / 4] = reinterpret_cast<std::uintptr_t>(&Peace);
    message.table = message_table.data(); message_table[2] = reinterpret_cast<std::uintptr_t>(&Drop);
    for (const auto rva : {0x5e61U, 0xc9c80U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Mask)); }
    for (const auto rva : {0x28097U, 0x613c0U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Mode)); }
    for (const auto rva : {0x10e24U, 0x4f100U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Toggle)); }
    for (const auto rva : {0x1eed4U, 0x611d0U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&State)); }
    for (const auto rva : {0x70eaU, 0x83920U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&End)); }
    for (const auto rva : {0x2597dU, 0x141330U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Find)); }
    Jump(0x10ca3, reinterpret_cast<std::uintptr_t>(&CopyIterator));
    for (const auto rva : {0x289c0U, 0x10c53U, 0x12dd80U, 0x12ddc0U}) {
        Jump(rva, reinterpret_cast<std::uintptr_t>(&Guard));
    }
    for (const auto rva : {0xbd25U, 0x1125d0U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&ReadKey)); }
    Jump(0x3c24, reinterpret_cast<std::uintptr_t>(&Dereference));
    Jump(0x23cb3, reinterpret_cast<std::uintptr_t>(&KeyDestructor));
    for (const auto rva : {0xb2b7U, 0x131190U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Retain)); }
    for (const auto rva : {0x7dabU, 0x7f4490U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Controller)); }
    for (const auto rva : {0x5a65U, 0x7f4da0U}) { Jump(rva, reinterpret_cast<std::uintptr_t>(&Send)); }
}
std::string Digest(const std::vector<unsigned char>& bytes) {
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{}; std::array<unsigned char, 32> digest{};
    const bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<unsigned char*>(bytes.data()), static_cast<ULONG>(bytes.size()), 0) >= 0
        && BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); } if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    Check(ok, "SHA256 failure"); std::string result; constexpr char hex[] = "0123456789abcdef";
    for (auto byte : digest) { result += hex[byte >> 4]; result += hex[byte & 15]; } return result;
}
EXCEPTION_DISPOSITION __cdecl NativeFault(EXCEPTION_RECORD*, void*, CONTEXT*, void*) {
    TerminateProcess(GetCurrentProcess(), 3); return ExceptionContinueSearch;
}
void LoadOriginal(const wchar_t* path) {
    std::ifstream file(std::filesystem::path(path), std::ios::binary | std::ios::ate);
    Check(file.good(), "cannot read reviewed client"); const auto length = file.tellg();
    Check(length > 0 && length < 64 * 1024 * 1024, "invalid client length");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(length)); file.seekg(0);
    Check(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()), length)), "short client read");
    const auto digest = Digest(bytes);
    Check(digest == "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7"
        || digest == "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289"
        || digest == "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8"
        || digest == "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
        "unreviewed client: exact original/prepared1.3.38.12 or1.3.38.13 required");
    // Private image control-flow oracle. Only ordinary1551 is copied. Its native
    // helper ABI boundaries are instrumented identically for both executions;
    // no actual stance, action, request, message, UI or network effect occurs.
    constexpr auto start = 0x7d3c10U, end = 0x7d3e86U;
    std::memcpy(reinterpret_cast<void*>(image + start), bytes.data() + start, end - start);
    for (const auto offset : {0x7d3c2cU, 0x7d3c55U, 0x7d3c65U, 0x7d3c72U,
            0x7d3c86U, 0x7d3ca8U, 0x7d3d33U, 0x7d3dedU, 0x7d3e58U, 0x7d3d0eU}) {
        *reinterpret_cast<std::uintptr_t*>(image + offset) += image - 0x400000U;
    }
    *reinterpret_cast<std::uintptr_t*>(image + 0x7d3c16) = reinterpret_cast<std::uintptr_t>(&NativeFault);
    Jump(0x7d3d51, image + 0x7d3e76); // Replace rejected-attack error UI reporting only.
}
void Verify(bool original) {
    unsigned cases{};
    for (const unsigned flags : {0x2010U, 0x2030U, 0x2000U, 0x10U})
    for (const unsigned mode : {0U, 1U, 2U, 3U})
    for (const unsigned state : {1U, 5U})
    for (const bool blocked : {false, true})
    for (const bool special : {false, true})
    for (const bool property : {false, true})
    for (const bool peace_actor : {false, true})
    for (const bool peace_target : {false, true})
    for (const bool toggle : {false, true}) {
        toggle_accepted = toggle; actor_peace = peace_actor; target_peace = peace_target;
        Reset(flags, mode, state, blocked, special, property);
        const bool accepted = !(flags & 0x20) && (mode == 2 || (mode == 1 && toggle))
            && !blocked && state != 1 && (flags & 0x2000)
            && (!(flags & 0x10) || (special && !property) || (!peace_actor && !peace_target));
        Counts expected{}; unsigned expected_mode{}; std::vector<unsigned> expected_trace;
        if (original) {
            reinterpret_cast<void(__cdecl*)(void*, void*)>(image + 0x7d3c10)(nullptr, nullptr);
            expected = counts; expected_trace = trace; expected_mode = actor_state[0x18 / 4];
            Check(counts.factory == static_cast<unsigned>(accepted), "native oracle predicate mismatch");
            Check(!message.refs, "native oracle leaked its request");
            Reset(flags, mode, state, blocked, special, property);
        }
        // Poisoned UI selection proves the production adapter never dereferences
        // or overwrites selection; the held object owns target admission.
        *reinterpret_cast<void**>(image + 0x16a2da4) = reinterpret_cast<void*>(1);
        submission::Context context{}; context.route = submission::Route::explicit_object;
        submission::Scope scope(context); void* request{}, *transfer{};
        const bool result = melee::Invoke(image, actor.data(), target.data(), scope,
            request, transfer, Current, nullptr);
        Check(result == accepted, "adapter predicate mismatch");
        Check(!request && !transfer && !message.refs, "adapter leaked request ownership");
        Check(*reinterpret_cast<void**>(image + 0x16a2da4) == reinterpret_cast<void*>(1), "adapter changed selection");
        if (original) { Check(expected == counts && expected_trace == trace && expected_mode == actor_state[0x18 / 4], "native/adapter call sequence differs"); }
        ++cases;
    }
    for (unsigned change = 0; change < 4; ++change) {
        toggle_accepted = true; actor_peace = target_peace = false;
        Reset(0x2010, 1, 5, false, false, false);
        invalidate_toggle = change == 0; invalidate_factory = change == 1;
        invalidate_send = change == 2; throw_factory = change == 3;
        submission::Context context{}; submission::Scope scope(context); void* request{}, *transfer{};
        bool threw = false;
        try { Check(!melee::Invoke(image, actor.data(), target.data(), scope, request, transfer,
            Current, nullptr), "invalidated entry was reported complete"); }
        catch (const std::runtime_error&) { threw = true; }
        Check(threw == throw_factory && !counts.followup, "failed entry continued followup");
        Check(counts.sends == (change == 2 ? 1U : 0U), "failed admission submitted message");
        // Fixture disposal only: production quarantines all returned ownership on fault.
        melee::Release(transfer); melee::Release(request); Check(!message.refs, "fixture lost returned ownership");
    }
    std::printf("%u melee guard combinations: %s; callback invalidation and owned output passed.\n",
        cases, original ? "exact native1551 control-flow/ABI equivalence" : "synthetic predicate/ownership checks");
}
}
namespace wonderbane::extension::combat::submission {
Scope::Scope(const Context& c) noexcept : context_(c) {}
Scope::~Scope() {}
void* Scope::Factory(void* actor_value, void** out, void* target_value, const void* key, bool send) {
    return ::Factory(actor_value, nullptr, out, target_value, key, send);
}
void Scope::Followup(void* actor_value) { ::Followup(actor_value, nullptr); }
}
int wmain(int argc, wchar_t** argv) {
    try {
#ifdef MELEE_NATIVE_PROBE
        Check(argc == 2, "usage: combat_melee_probe <exact reviewed private sb.exe>");
#else
        Check(argc == 1, "synthetic melee fixture takes no arguments");
#endif
        auto* arena = VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        Check(arena != nullptr, "arena allocation failed"); image = reinterpret_cast<std::uintptr_t>(arena);
        std::memset(arena, 0xcc, 0x1800000);
        const bool original = argc == 2; if (original) { LoadOriginal(argv[1]); }
        InstallPrimitives(); DWORD old{};
        Check(VirtualProtect(arena, 0x900000, PAGE_EXECUTE_READ, &old) != 0, "code protection failed");
        Check(FlushInstructionCache(GetCurrentProcess(), arena, 0x900000) != 0, "cache flush failed");
        Verify(original); Check(VirtualFree(arena, 0, MEM_RELEASE) != 0, "arena release failed"); return 0;
    } catch (const std::exception& e) { std::fprintf(stderr, "%s\n", e.what()); return 1; }
}
