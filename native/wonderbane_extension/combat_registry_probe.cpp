#include <Windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

// Developer-only exact-image conformance. No client startup, other process,
// window, network or game state is touched. This verifies the real resolver's
// ABI, exact key lookup and returned ownership; it does not prove registry
// writer serialization in the running engine. No proprietary bytes are embedded.
namespace {
void Require(bool condition, const char* message) {
    if (!condition) { throw std::runtime_error(message); }
}
std::string Digest(const unsigned char* bytes, std::size_t size) {
    BCRYPT_ALG_HANDLE algorithm{};
    BCRYPT_HASH_HANDLE hash{};
    std::array<unsigned char, 32> digest{};
    const bool ok = size <= std::numeric_limits<ULONG>::max()
        && BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<unsigned char*>(bytes), static_cast<ULONG>(size), 0) >= 0
        && BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); }
    if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    Require(ok, "SHA256 failed");
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (const auto byte : digest) {
        result += hex[byte >> 4]; result += hex[byte & 15];
    }
    return result;
}

using Key = std::array<std::uint32_t, 2>;
using Resolve = void** (__thiscall*)(void*, void**, const Key*);
using Release = void (__thiscall*)(void**, void*);
struct Object {
    std::array<std::uint32_t, 2> prefix{};
    const std::int32_t* offsets = nullptr;
    std::uint32_t padding = 0;
    const std::uintptr_t* table = nullptr;
    volatile LONG references = 1;
    Key key{};
    std::uint32_t finalizations = 0;
    std::uint32_t finalizer_flags = 0;
};
static_assert(sizeof(void*) == 4);
static_assert(offsetof(Object, offsets) == 8 && offsetof(Object, table) == 16
    && offsetof(Object, references) == 20 && offsetof(Object, key) == 0x18);
struct Registry { std::uintptr_t unused = 0; Object** buckets = nullptr; std::uint32_t exponent = 0; };
struct World { std::array<unsigned char, 0x94> prefix{}; Registry* registry = nullptr; };
static_assert(offsetof(Registry, buckets) == 4 && offsetof(World, registry) == 0x94);
LONG increments = 0, decrements = 0;
LONG WINAPI Increment(volatile LONG* value) { ++increments; return InterlockedIncrement(value); }
LONG WINAPI Decrement(volatile LONG* value) { ++decrements; return InterlockedDecrement(value); }
void __fastcall Finalize(void* pointer, void*, std::uint32_t flags) {
    auto& object = *reinterpret_cast<Object*>(static_cast<unsigned char*>(pointer) - 16);
    ++object.finalizations; object.finalizer_flags = flags;
}
// Native C++ EH metadata refers to its original executable. Exception unwinding
// is outside this conformance contract. Any unexpected native exception must
// terminate this isolated fixture rather than follow foreign EH metadata.
EXCEPTION_DISPOSITION __cdecl NativeFault(EXCEPTION_RECORD*, void*, CONTEXT*, void*) {
    TerminateProcess(GetCurrentProcess(), 3);
    return ExceptionContinueSearch;
}
struct Arena {
    void* memory = nullptr;
    ~Arena() { if (memory) { VirtualFree(memory, 0, MEM_RELEASE); } }
};
void Verify(unsigned char* arena) {
    const auto resolve = reinterpret_cast<Resolve>(arena + 0x1fcc80);
    const auto release = reinterpret_cast<Release>(arena + 0x89bd0);
    const std::array<std::int32_t, 2> offsets{0, 8};
    const std::array<std::uintptr_t, 3> table{0, reinterpret_cast<std::uintptr_t>(&Finalize),
        reinterpret_cast<std::uintptr_t>(arena + 0x1311b0)};
    Registry registry{}; World world{}; world.registry = &registry;
    const Key missing{0xabcdef01, 53};
    void* output = nullptr;
    Require(resolve(&world, &output, &missing) == &output && output == nullptr,
        "empty registry changed return ABI or result");
    Require(increments == 0 && decrements == 0, "empty registry touched references");
    for (const unsigned exponent : {3U, 4U, 6U, 8U}) {
        const auto capacity = std::uint32_t{1} << exponent;
        const auto mask = capacity - 1;
        std::vector<Object*> buckets(capacity, nullptr);
        std::array<Object, 4> objects{};
        for (std::size_t i = 0; i != objects.size(); ++i) {
            objects[i].offsets = offsets.data(); objects[i].table = table.data();
            // Different exact keys deliberately share the same XOR hash.
            const auto difference = static_cast<std::uint32_t>(i) << 8;
            objects[i].key = {0xabc000U ^ difference, 53U ^ difference};
        }
        const auto hash = objects[0].key[0] ^ objects[0].key[1];
        const auto initial = ~hash & mask;
        auto step = (hash ^ (hash >> 3)) & mask;
        if (!step) { step = mask; }
        std::uint32_t polynomial = 0;
        std::memcpy(&polynomial, arena + 0x114a868 + exponent * 4, 4);
        std::array<std::uint32_t, 4> slots{initial};
        for (std::size_t i = 1; i != slots.size(); ++i) {
            slots[i] = (initial + step) & mask;
            step <<= 1;
            if (step > mask) { step ^= polynomial; }
        }
        for (std::size_t i = 0; i != objects.size(); ++i) {
            Require(buckets[slots[i]] == nullptr, "fixture collision placement repeated");
            buckets[slots[i]] = &objects[i];
        }
        registry.buckets = buckets.data(); registry.exponent = exponent;
        for (auto& object : objects) {
            const auto before_increment = increments, before_decrement = decrements;
            output = nullptr;
            Require(resolve(&world, &output, &object.key) == &output && output == &object,
                "exact collision lookup or thiscall/outref ABI mismatch");
            Require(object.references == 2 && increments - before_increment == 2
                && decrements - before_decrement == 1 && object.finalizations == 0,
                "resolver must return one owned reference after releasing local reference");
            release(&output, nullptr);
            Require(output == nullptr && object.references == 1 && !object.finalizations,
                "caller release did not preserve registry ownership");
        }
        for (const Key absent : {Key{objects[0].key[0] ^ 0x800U, objects[0].key[1] ^ 0x800U},
                 Key{objects[0].key[0], 54U}, Key{objects[0].key[0] + 1, objects[0].key[1]}}) {
            const auto before_increment = increments, before_decrement = decrements;
            output = nullptr;
            Require(resolve(&world, &output, &absent) == &output && output == nullptr,
                "same hash or one matching key word authorized a different object");
            Require(increments == before_increment && decrements == before_decrement,
                "missing key changed ownership");
        }
        // A deleted bucket cannot hide a later colliding live key.
        buckets[slots[0]] = reinterpret_cast<Object*>(~std::uintptr_t{0});
        void* retired = &objects[0]; release(&retired, nullptr);
        Require(objects[0].references == 0 && objects[0].finalizations == 1,
            "registry-only object did not finalize at removal");
        output = nullptr;
        Require(resolve(&world, &output, &objects[0].key) == &output && output == nullptr,
            "tombstone resolved removed key");
        Require(resolve(&world, &output, &objects[3].key) == &output && output == &objects[3],
            "tombstone interrupted collision lookup");
        // Remove registry membership while the returned reference remains owned.
        buckets[slots[3]] = reinterpret_cast<Object*>(~std::uintptr_t{0});
        retired = &objects[3]; release(&retired, nullptr);
        Require(objects[3].references == 1 && !objects[3].finalizations,
            "returned reference failed to keep removed object alive");
        release(&output, nullptr);
        Require(output == nullptr && objects[3].references == 0
            && objects[3].finalizations == 1 && objects[3].finalizer_flags == 1,
            "last returned reference did not finalize exactly once");
        for (std::size_t i : {1U, 2U}) {
            retired = &objects[i]; release(&retired, nullptr);
            Require(objects[i].finalizations == 1 && objects[i].references == 0,
                "fixture registry reference leaked");
        }
    }
}
int Run(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "usage: combat_registry_probe <reviewed-client-executable>");
        std::ifstream file(std::filesystem::path(argv[1]), std::ios::binary | std::ios::ate);
        Require(file.good(), "cannot open executable");
        const auto size = file.tellg();
        Require(size > 0 && size <= 64 * 1024 * 1024, "invalid executable size");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size)); file.seekg(0);
        Require(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()), size)), "short read");
        const auto digest = Digest(bytes.data(), bytes.size());
        Require(digest == "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7"
            || digest == "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289"
        || (digest == "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" || (digest=="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" || (digest=="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" || (digest=="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a" || digest=="051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698"))))
        || (digest == "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" || (digest=="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" || (digest=="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" || (digest=="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c" || digest=="baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9")))),
            "unsupported executable: require exact reviewed original/prepared 1.3.38.12 or 1.3.38.13");
        struct Segment { std::size_t offset, size; const char* sha256; };
        constexpr std::array segments{
            Segment{0x2923, 5, "77cce6d31669d1c69469ee7dbd3ddcd2515bc17296beeac33df555030c5c5f2d"},
            Segment{0x4d9a, 5, "2eb2fdaf3e971496eb6ad5682e4906c69d7a931249367f72132f29767af8a882"},
            Segment{0xab5f, 5, "749d41d7b7c20c0b1cfca850f2ba092b87f25969a3a7617c40469a704e3e12c2"},
            Segment{0xb2b7, 5, "64c03dded86ce9f2b6b89075b5954e449701ee2bb83ac77f4fecf8c2195bf50f"},
            Segment{0xbd25, 5, "cc68893872dd003dcc6eaa399e64cfb0cc984518e075c63562633e4c29fc9851"},
            Segment{0xbdc5, 5, "9514894e992f15e5297c31adf885f7704fca66bf0fd325d5dcc941f258661f57"},
            Segment{0xca40, 5, "87627132e661fac4222861ad34bc1605bc1fe3ca7458fad6b889713aa668928a"},
            Segment{0x1331d, 5, "9d72232993ed34eaca4b956763998d411dc431f269b00388a3c1d8e857ed234d"},
            Segment{0x15744, 5, "df0c9d3761e3607ceb67f609965735a34bea2e904452f85f4c4b16c995a1e570"},
            Segment{0x16149, 5, "66fcfd0a964b3139039d116edfc57f02cf70c1af501cf8bc3dfd967b63c0b076"},
            Segment{0x1795e, 5, "94ca8b3be29653a21239620e3d6928d66d781ba94d7176ac9da8d854cdf551af"},
            Segment{0x1a357, 5, "39878aee9b0e0739d11206e24fda154115b58c55da86a1608c94e4699c6de223"},
            Segment{0x1bc66, 5, "c3b90a2d0077ad5e148b1d9dfc62c766b29f326931b4bcefe2c99822d32a8e5c"},
            Segment{0x23cb3, 5, "51437f515e988923edf0497a63088d6a5bb422b277d8b8321a07560ba177575f"},
            Segment{0x2526b, 5, "db21e0b69424d70cf431c9f382e40e9e1be816e883aad8042573fe5cdde893d8"},
            Segment{0x25581, 5, "12016bb9ec4d24cba32a73ce915a9fde09a56d275e51577bd40687da508707cf"},
            Segment{0x89ba0, 32, "b0ab95be3a4f6f24c5d85d28e1aab39afbf12f851cae46ba828b8db4018ee024"},
            Segment{0x89bd0, 80, "71143912a599771d1ff4abb3f52541c02c6d7c5f9c766198aad1e4bf84dc21eb"},
            Segment{0x1117b0, 32, "29625c1b1f2a52a0571368c344551f9e5b688a078a4d3695ed16327d50815564"},
            Segment{0x1119d0, 16, "499f1f307c1cb989f968a6b7fcaec591e1828877223d0b0e7e8e8b76cde8c9ca"},
            Segment{0x111b20, 48, "b8e415f16edc3d2c1292cc8ede5fa1c3055d39c87280d837a45d593ab4720da7"},
            Segment{0x112210, 32, "d67f89f3b1df836f457d1cc59f18db80a16428923d9e464b1a6b3cdfe7e73a00"},
            Segment{0x1125d0, 48, "314cae6b4718e18cc2ec96d39e08c8afafd35fb1591e82af97b8196fdc385322"},
            Segment{0x131190, 16, "f4c4b561fa6ccb6f1a77357a1a9c026a2a3a2e39f58bf4ecb34b2a360f4bc885"},
            Segment{0x1311b0, 48, "48cdd88b5b609916a4a15b600abcc64bd12346e81ee1d6d7b6523bf3f16aa316"},
            Segment{0x14c7a0, 16, "94fdb24b707e0417c827ff428b87b43e35d771a503084dbc90fcaf277ef86309"},
            Segment{0x14c7c0, 16, "c66f50ad9fce94c26c624d26f5eb503c760095dc99ac2e511abffc6712bd5753"},
            Segment{0x1fb160, 414, "3fe566e855bc6eee4b34387ca9ba12df2a3cb1526a45b2343fc8c5cd1e420dff"},
            Segment{0x1fcc80, 48, "3049e8027321e722dc96f69c04cf99f7f0090f26546eff61fe746baa5d1dae54"},
            Segment{0x210b00, 48, "c0601e0f6057bf3af5166bf52b303ae4324da23ebaeb57b4908be359202f82a0"},
            Segment{0x210c10, 80, "36e59e9c66e1e905d3823c373805a22368576695cfca2605302e342faa341b2a"},
            Segment{0x2150c0, 560, "b6798862974a498c86e68cca59d5b86967735eaa8af5a49f9b65f0c03c839569"},
            Segment{0x2155f0, 32, "688d38c2e4919eabea2258be2bfdf81c67a570ad62969019ed83c0cba572f4c0"},
            Segment{0x215680, 32, "1d749d18563b9cf3f72eda619a92a950631b29754edb32bc2a6ef6ad1cc0f0c8"},
            Segment{0x2184d0, 32, "1d749d18563b9cf3f72eda619a92a950631b29754edb32bc2a6ef6ad1cc0f0c8"},
            Segment{0x114a868, 128, "761c563b9cef2d07f81dc2c7d33edaf3ae6136ba9acd3d072351e96fd0976a40"},
        };
        constexpr std::size_t code_length = 0x219000, length = 0x16c0000;
        for (const auto& segment : segments) {
            Require(segment.offset + segment.size <= bytes.size(), "missing reviewed primitive");
            Require(Digest(bytes.data() + segment.offset, segment.size) == segment.sha256,
                "native primitive digest mismatch");
        }
        Arena code; code.memory = VirtualAlloc(nullptr, length, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        Require(code.memory != nullptr, "arena allocation failed");
        auto* arena = static_cast<unsigned char*>(code.memory);
        std::fill_n(arena, length, static_cast<unsigned char>(0xcc));
        // Reviewed raw offsets equal RVAs for this closure. Relative calls stay
        // intact. Uncopied instructions trap; data and import pages stay non-executable.
        for (const auto& segment : segments) {
            std::copy_n(bytes.data() + segment.offset, segment.size, arena + segment.offset);
        }
        for (const auto location : {0x14c7a9U, 0x14c7c9U, 0x2151edU}) {
            std::uint32_t operand = 0; std::memcpy(&operand, arena + location, 4);
            operand += reinterpret_cast<std::uintptr_t>(arena) - 0x400000U;
            std::memcpy(arena + location, &operand, 4);
        }
        const auto fault = reinterpret_cast<std::uintptr_t>(&NativeFault);
        for (const auto location : {0x1fb166U, 0x2150c6U}) {
            std::memcpy(arena + location, &fault, 4);
        }
        const auto increment = reinterpret_cast<std::uintptr_t>(&Increment);
        const auto decrement = reinterpret_cast<std::uintptr_t>(&Decrement);
        std::memcpy(arena + 0x16b0254, &increment, 4);
        std::memcpy(arena + 0x16b0258, &decrement, 4);
        DWORD previous = 0;
        Require(VirtualProtect(arena, code_length, PAGE_EXECUTE_READ, &previous) != 0,
            "code protection failed");
        Require(FlushInstructionCache(GetCurrentProcess(), arena, code_length) != 0,
            "instruction cache flush failed");
        Verify(arena);
        std::puts("Real native registry resolver: ABI, exact keys, collisions, misses, tombstones, owned retention and final release passed. Thread serialization is a separate contract.");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what()); return 1;
    }
}
} // namespace
int wmain(int argc, wchar_t** argv) {
    __try { return Run(argc, argv); }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        std::fprintf(stderr, "Native registry conformance exception: 0x%08lx\n", GetExceptionCode());
        return 2;
    }
}
