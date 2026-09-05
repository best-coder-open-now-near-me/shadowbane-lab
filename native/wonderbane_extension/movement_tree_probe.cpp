#include <Windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

// Developer-only conformance probe. Never opens or modifies another process.
// No proprietary bytes are distributed: an explicitly supplied, exact reviewed
// executable supplies reviewed native primitives. The pool test forwards only
// its two verified Win32 imports and uses private allocator globals.
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
struct Node {
    std::uint8_t black = 1;
    std::array<std::uint8_t, 3> padding{};
    Node* parent = nullptr;
    Node* left = nullptr;
    Node* right = nullptr;
    // Deliberately opaque to the native tree algorithm.
    std::array<std::uint32_t, 6> payload{};
};
static_assert(sizeof(void*) == 4);
static_assert(offsetof(Node, parent) == 4 && offsetof(Node, left) == 8
    && offsetof(Node, right) == 12 && offsetof(Node, payload) == 16);
static_assert(sizeof(Node) == 40);
using Erase = Node* (__cdecl*)(Node*, Node**, Node**, Node**);
using Identity = std::array<std::uint32_t, 2>;
using Find = Node** (__thiscall*)(void*, Node**, const Identity*);
using CopyIdentity = Identity* (__thiscall*)(Identity*, const Identity*);
using DestroyIdentity = void (__thiscall*)(Identity*);
using ClearContinuation = void (__thiscall*)(void*);
using PoolReturn = void (__cdecl*)(void*, std::uint32_t);
HANDLE pool_contention_event = nullptr;
LONG WINAPI ForwardPoolExchange(volatile LONG* target, LONG value) {
    const LONG previous = InterlockedExchange(target, value);
    if (previous && pool_contention_event) { SetEvent(pool_contention_event); }
    return previous;
}
struct EventHandle {
    HANDLE value = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    ~EventHandle() { if (value) { CloseHandle(value); } }
};
struct Map { Node* sentinel; std::uint32_t size; };
struct ExecutableCode {
    void* memory = nullptr;
    ~ExecutableCode() { if (memory) { VirtualFree(memory, 0, MEM_RELEASE); } }
};
struct Tree {
    Node sentinel{};
    std::vector<std::unique_ptr<Node>> nodes;
    std::vector<bool> present;
    explicit Tree(std::size_t count) : present(count, true) {
        nodes.reserve(count);
        for (std::size_t i = 0; i < count; ++i) {
            auto node = std::make_unique<Node>();
            for (std::size_t j = 0; j < node->payload.size(); ++j) {
                node->payload[j] = static_cast<std::uint32_t>(i * 101 + j);
                if (j == 0) { node->payload[j] = static_cast<std::uint32_t>(i % 32) * 0x08421084U; }
                if (j == 1) { node->payload[j] = static_cast<std::uint32_t>(i / 32) * 0x24924924U; }
                if (i + 1 == count && j < 2) { node->payload[j] = 0xffffffffU; }
            }
            nodes.push_back(std::move(node));
        }
        sentinel.black = 0;
        sentinel.parent = Build(0, count, &sentinel);
        sentinel.left = nodes.front().get();
        sentinel.right = nodes.back().get();
    }
    Node* Build(std::size_t first, std::size_t end, Node* parent) {
        if (first == end) { return nullptr; }
        const auto middle = first + (end - first) / 2;
        Node* node = nodes[middle].get();
        node->parent = parent;
        node->left = Build(first, middle, node);
        node->right = Build(middle + 1, end, node);
        return node;
    }
    unsigned Visit(Node* node, Node* parent, std::vector<Node*>& ordered,
                   unsigned depth) const {
        Require(depth <= 64, "cycle or invalid height");
        if (!node) { return 1; }
        Require(node != &sentinel && node->parent == parent, "broken parent link");
        Require(node->black <= 1, "invalid color");
        if (!node->black) {
            Require((!node->left || node->left->black)
                && (!node->right || node->right->black), "red child of red node");
        }
        const auto left = Visit(node->left, node, ordered, depth + 1);
        ordered.push_back(node);
        const auto right = Visit(node->right, node, ordered, depth + 1);
        Require(left == right, "unequal black heights");
        return left + node->black;
    }
    void Verify() const {
        Require(!sentinel.parent || sentinel.parent->black == 1, "red root");
        std::vector<Node*> expected, ordered;
        for (std::size_t i = 0; i < nodes.size(); ++i) {
            for (std::size_t j = 0; j < nodes[i]->payload.size(); ++j) {
                const auto expected_word = i + 1 == nodes.size() && j < 2 ? 0xffffffffU
                    : j == 0 ? static_cast<std::uint32_t>(i % 32) * 0x08421084U
                    : j == 1 ? static_cast<std::uint32_t>(i / 32) * 0x24924924U
                    : static_cast<std::uint32_t>(i * 101 + j);
                Require(nodes[i]->payload[j] == expected_word, "payload changed");
            }
            if (present[i]) { expected.push_back(nodes[i].get()); }
        }
        (void)Visit(sentinel.parent, const_cast<Node*>(&sentinel), ordered, 0);
        Require(ordered == expected, "node loss, duplication or order corruption");
        const Node* minimum = expected.empty() ? &sentinel : expected.front();
        const Node* maximum = expected.empty() ? &sentinel : expected.back();
        Require(sentinel.left == minimum && sentinel.right == maximum, "bad extrema");
    }
};
}
int RunProbe(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "usage: movement_tree_probe <reviewed-client-executable>");
        std::ifstream file(std::filesystem::path(argv[1]), std::ios::binary | std::ios::ate);
        Require(file.good(), "cannot open executable");
        const auto size = file.tellg();
        Require(size > 0 && size <= 64 * 1024 * 1024, "invalid executable size");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));
        file.seekg(0);
        Require(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()), size)), "short read");
        Require(Digest(bytes.data(), bytes.size()) ==
            "feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff",
            "unsupported executable");
        struct Segment { std::size_t offset; std::size_t size; const char* sha256; };
        constexpr std::array segments{
            Segment{0x40270,284,"bdce79064089f17dd744e34dfdac4187203ca9c6f3c8bc05c77708a11a332b93"},
            Segment{0x63a30,24,"a786e52b8f763cb0e705244fa2e34c1b0db4e27a8234c762e6e6795b75107604"},
            Segment{0x8edd0,1001,"647324142ed2d678037248e82d948a9666f084962476a5f5cb866c008723fffa"},
            Segment{0x21b7b0,93,"6e9518982122e7fd858e307e98f652372ef5c9efb4960317349aea232b97e62a"},
            Segment{0x12a3f,5,"22f1ce707ccfeb03ab5559276494c7045f1804b9820eabeec33d00f6b5832b79"},
            Segment{0x111bd0,43,"614f594fbe84d1ecd760eb1cccfc199275c3b84be0e0fb2055acdbf8b3378f03"},
            Segment{0x1117b0,22,"66b42201ae2adac5438161fdb2a8dc60eb4bf84b6a9462a2564677c9a809cdd4"},
            Segment{0x1119d0,1,"ae3f4619b0413d70d3004b9131c3752153074e45725be13b9a148978895e359e"}};
        // Reviewed PE raw offsets equal RVAs for these segments. Preserve relative
        // native calls between lookup, its thunk and comparator. Code gaps trap;
        // data pages are never executable. No client startup is copied/executed.
        constexpr std::size_t code_length = 0x220000;
        constexpr std::size_t length = 0x16c0000;
        for (const auto& segment : segments) {
            Require(segment.offset + segment.size <= bytes.size()
                && segment.offset + segment.size <= code_length, "missing native primitive");
            Require(Digest(bytes.data() + segment.offset, segment.size) == segment.sha256,
                "native primitive digest mismatch");
        }
        ExecutableCode code;
        code.memory = VirtualAlloc(nullptr, length, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        Require(code.memory != nullptr, "allocation failed");
        auto* arena = static_cast<unsigned char*>(code.memory);
        std::fill_n(arena, length, static_cast<unsigned char>(0xcc));
        for (const auto& segment : segments) {
            std::copy_n(bytes.data() + segment.offset, segment.size, arena + segment.offset);
        }
        // These are the complete reviewed HIGHLOW relocation sites in PoolReturn.
        constexpr std::array pool_relocations{0x13,0x18,0x21,0x2f,0x34,0x4e,0x59,
            0x5f,0xa0,0xa6,0xc2,0xc8,0xde,0xe4,0xfa};
        for (const auto offset : pool_relocations) {
            std::uint32_t operand{};
            std::memcpy(&operand, arena + 0x40270 + offset, sizeof(operand));
            operand += reinterpret_cast<std::uintptr_t>(arena) - 0x400000U;
            std::memcpy(arena + 0x40270 + offset, &operand, sizeof(operand));
        }
        // Native import names verified from the reviewed PE import directory:
        // KERNEL32!InterlockedExchange and KERNEL32!Sleep. No game API stubs.
        const auto exchange_address = reinterpret_cast<std::uintptr_t>(&ForwardPoolExchange);
        const auto sleep_address = reinterpret_cast<std::uintptr_t>(&Sleep);
        std::memcpy(arena + 0x16b0308, &exchange_address, sizeof(exchange_address));
        std::memcpy(arena + 0x16b030c, &sleep_address, sizeof(sleep_address));
        auto* pool_heads = reinterpret_cast<Node**>(arena + 0x1372ddc);
        auto* pool_lock = reinterpret_cast<volatile LONG*>(arena + 0x1372e28);
        // All native allocator data stays inside this developer process.
        std::fill_n(pool_heads, 16, nullptr);
        InterlockedExchange(pool_lock, 0);
        std::uint32_t spin = 0;
        std::memcpy(arena + 0x12c464c, &spin, sizeof(spin));
        std::memcpy(arena + 0x1372e2c, &spin, sizeof(spin));
        DWORD previous{};
        Require(VirtualProtect(code.memory, code_length, PAGE_EXECUTE_READ, &previous) != 0,
            "executable protection failed");
        Require(FlushInstructionCache(GetCurrentProcess(), code.memory, code_length) != 0,
            "instruction cache flush failed");
        const auto pool_return = reinterpret_cast<PoolReturn>(arena + 0x40270);
        const auto erase = reinterpret_cast<Erase>(arena + 0x8edd0);
        const auto find = reinterpret_cast<Find>(arena + 0x21b7b0);
        const auto copy = reinterpret_cast<CopyIdentity>(arena + 0x1117b0);
        const auto destroy = reinterpret_cast<DestroyIdentity>(arena + 0x1119d0);
        // Execute the native empty-path continuation helper against complete byte
        // snapshots, including restricted/incapacitated state values. It must not
        // force idle, change follow preferences, dereference path data or touch state.
        const auto clear_continuation = reinterpret_cast<ClearContinuation>(arena + 0x63a30);
        unsigned continuation_cases = 0;
        for (std::uint32_t state = 0; state < 16; ++state) {
            for (const std::uint32_t path_case : {0U, 1U, 2U}) {
                for (const auto continuation : std::array<unsigned char, 3>{0, 1, 0xa5}) {
                    std::array<unsigned char, 0xc20> actor;
                    std::array<unsigned char, 0x30> state_object;
                    actor.fill(0xa5); state_object.fill(0x5a);
                    std::memcpy(state_object.data() + 0x10, &state, sizeof(state));
                    const auto state_address = reinterpret_cast<std::uintptr_t>(state_object.data());
                    std::memcpy(actor.data() + 0xad0, &state_address, sizeof(state_address));
                    const std::uint32_t begin = path_case == 0 ? 0 : 0x1000;
                    const std::uint32_t end = path_case == 2 ? begin + 16 : begin;
                    std::memcpy(actor.data() + 0xc10, &begin, sizeof(begin));
                    std::memcpy(actor.data() + 0xc14, &end, sizeof(end));
                    actor[0xc1e] = continuation;
                    auto expected = actor;
                    const auto expected_state = state_object;
                    if (begin == end) { expected[0xc1e] = 0; }
                    clear_continuation(actor.data());
                    Require(actor == expected && state_object == expected_state,
                        "native continuation clear changed unrelated actor/state or nonempty path");
                    clear_continuation(actor.data());
                    Require(actor == expected && state_object == expected_state,
                        "native continuation clear is not idempotent");
                    ++continuation_cases;
                }
            }
        }
        std::printf("PASS: %u native continuation cases; complete actor/state preservation and idempotence\n",
            continuation_cases);
        std::mt19937 random(0x53424d56);
        std::uint64_t removals = 0;
        for (unsigned height = 1; height <= 8; ++height) {
            const std::size_t count = (1U << height) - 1U;
            for (unsigned trial = 0; trial < 128; ++trial) {
                pool_heads[4] = nullptr;
                Tree tree(count);
                tree.Verify();
                Map map{&tree.sentinel, static_cast<std::uint32_t>(count)};
                Node* found = nullptr;
                const Identity missing{0xfffffffeU, 0xffffffffU};
                Require(find(&map, &found, &missing) == &found && found == &tree.sentinel,
                    "absent identity found");
                std::vector<std::size_t> order(count);
                std::iota(order.begin(), order.end(), 0U);
                if (trial == 1) { std::reverse(order.begin(), order.end()); }
                else if (trial > 1) { std::shuffle(order.begin(), order.end(), random); }
                for (auto index : order) {
                    Identity identity{};
                    const Identity expected{tree.nodes[index]->payload[0], tree.nodes[index]->payload[1]};
                    Require(copy(&identity, &expected) == &identity && identity == expected,
                        "identity copy changed words or return address");
                    Require(find(&map, &found, &identity) == &found && found == tree.nodes[index].get(),
                        "lookup selected wrong actor identity");
                    Node* removed = erase(found, &tree.sentinel.parent,
                        &tree.sentinel.left, &tree.sentinel.right);
                    Require(removed == tree.nodes[index].get(), "wrong detached identity");
                    tree.present[index] = false;
                    --map.size;
                    Require(find(&map, &found, &identity) == &found && found == &tree.sentinel,
                        "retired actor still found");
                    destroy(&identity);
                    Require(identity == expected, "identity destructor changed value");
                    tree.Verify();
                    destroy(reinterpret_cast<Identity*>(removed->payload.data()));
                    const auto old_head = pool_heads[4];
                    const auto payload = removed->payload;
                    pool_return(removed, sizeof(Node));
                    Node* next{};
                    std::memcpy(&next, removed, sizeof(next));
                    Require(pool_heads[4] == removed && next == old_head && *pool_lock == 0,
                        "native 40-byte pool return lost node, chain or lock");
                    Require(removed->payload == payload, "pool return changed payload bytes");
                    for (std::size_t bucket = 0; bucket < 16; ++bucket) {
                        Require(bucket == 4 || pool_heads[bucket] == nullptr,
                            "native pool return changed another size class");
                    }
                    ++removals;
                }
            }
        }
        pool_heads[4] = nullptr;
        // Force native allocator contention: the releasing thread cannot unlock
        // until the native function actually attempts its first locked exchange.
        EventHandle contention;
        Require(contention.value != nullptr, "contention event failed");
        pool_contention_event = contention.value;
        Node contended_node{};
        InterlockedExchange(pool_lock, 1);
        DWORD observed = WAIT_FAILED;
        {
            std::jthread releaser([&] {
                observed = WaitForSingleObject(contention.value, 5000);
                InterlockedExchange(pool_lock, 0);
            });
            pool_return(&contended_node, sizeof(Node));
        }
        pool_contention_event = nullptr;
        Require(observed == WAIT_OBJECT_0 && pool_heads[4] == &contended_node && *pool_lock == 0,
            "native contended pool return failed to wait and release");
        pool_heads[4] = nullptr;
        std::printf("PASS: native pool contention uses verified Win32 imports and releases lock\n");
        std::printf("PASS: %llu native lookup/removal/copy/destruction/pool-return sequences; tree invariants and payload preservation\n",
            static_cast<unsigned long long>(removals));
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}

int wmain(int argc, wchar_t** argv) {
    __try { return RunProbe(argc, argv); }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        std::fprintf(stderr, "Native conformance exception: 0x%08lx\n", GetExceptionCode());
        return 2;
    }
}
