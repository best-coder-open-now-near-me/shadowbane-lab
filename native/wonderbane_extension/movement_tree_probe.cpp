#include <Windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

// Developer-only conformance probe. Never opens or modifies another process.
// No proprietary bytes are distributed: an explicitly supplied, exact reviewed
// executable supplies one relocation-free, import-free tree primitive.
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
                Require(nodes[i]->payload[j] == i * 101 + j, "payload changed");
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
int wmain(int argc, wchar_t** argv) {
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
        constexpr std::size_t offset = 0x8edd0, length = 1001;
        Require(bytes.size() >= offset + length, "missing native primitive");
        Require(Digest(bytes.data() + offset, length) ==
            "647324142ed2d678037248e82d948a9666f084962476a5f5cb866c008723fffa",
            "native primitive digest mismatch");
        ExecutableCode code;
        code.memory = VirtualAlloc(nullptr, length, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        Require(code.memory != nullptr, "allocation failed");
        std::copy_n(bytes.data() + offset, length, static_cast<unsigned char*>(code.memory));
        DWORD previous{};
        Require(VirtualProtect(code.memory, length, PAGE_EXECUTE_READ, &previous) != 0,
            "executable protection failed");
        Require(FlushInstructionCache(GetCurrentProcess(), code.memory, length) != 0,
            "instruction cache flush failed");
        const auto erase = reinterpret_cast<Erase>(code.memory);
        std::mt19937 random(0x53424d56);
        std::uint64_t removals = 0;
        for (unsigned height = 1; height <= 8; ++height) {
            const std::size_t count = (1U << height) - 1U;
            for (unsigned trial = 0; trial < 128; ++trial) {
                Tree tree(count);
                tree.Verify();
                std::vector<std::size_t> order(count);
                std::iota(order.begin(), order.end(), 0U);
                if (trial == 1) { std::reverse(order.begin(), order.end()); }
                else if (trial > 1) { std::shuffle(order.begin(), order.end(), random); }
                for (auto index : order) {
                    Node* removed = erase(tree.nodes[index].get(), &tree.sentinel.parent,
                        &tree.sentinel.left, &tree.sentinel.right);
                    Require(removed == tree.nodes[index].get(), "wrong detached identity");
                    tree.present[index] = false;
                    tree.Verify();
                    ++removals;
                }
            }
        }
        std::printf("PASS: %llu native removals; tree invariants, exact identity and payload preservation\n",
            static_cast<unsigned long long>(removals));
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}

