#include "reviewed_scene_boundary.h"

#include <filesystem>
#include <fstream>
#include <cstdio>

int wmain(int argc, wchar_t** argv) {
    using namespace wonderbane::extension;
    std::array<std::uint8_t, kSceneDisplaySize> code{};
    if (IsReviewedSceneDisplayCode(nullptr, code.size(), kScenePreferredBase)
        || IsReviewedSceneDisplayCode(code.data(), code.size(), kScenePreferredBase)
        || IsReviewedSceneDisplayCode(code.data(), code.size() - 1U, kScenePreferredBase)
        || IsReviewedSceneExecutable(nullptr) || IsReviewedSceneExecutable("unknown")
        || !IsReviewedSceneExecutable(
            "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc")
        || !IsReviewedSceneExecutable(
            "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8")
        || !IsReviewedSceneCall(0xB981FBU, kScenePreferredBase, kSceneUiReturnRva)
        || IsReviewedSceneCall(0xB98246U, kScenePreferredBase, kSceneUiReturnRva)
        || IsReviewedSceneCall(0x100U, kScenePreferredBase, kSceneUiReturnRva)
        || IsReviewedSceneCall(kSceneUiReturnRva, 0U, kSceneUiReturnRva)) {
        return 1;
    }
    if (argc == 1) { return 0; }
    if (argc != 2) { return 2; }
    // Optional read-only integration check against the frozen reviewed PE.
    // Its .text raw offset equals its RVA; never load or execute the client.
    std::ifstream stream(std::filesystem::path(argv[1]), std::ios::binary);
    stream.seekg(kSceneDisplayRva);
    stream.read(reinterpret_cast<char*>(code.data()), code.size());
    if (!stream || !IsReviewedSceneDisplayCode(
            code.data(), code.size(), kScenePreferredBase)) { return 3; }
    for (const std::uint32_t base : {0x10000000U, 0x100000U}) {
        auto relocated = code;
        for (const std::size_t offset : kSceneDisplayRelocations) {
            std::uint32_t value = 0U;
            std::memcpy(&value, relocated.data() + offset, sizeof(value));
            value += base - kScenePreferredBase;
            std::memcpy(relocated.data() + offset, &value, sizeof(value));
        }
        if (!IsReviewedSceneDisplayCode(relocated.data(), relocated.size(), base)
            || IsReviewedSceneDisplayCode(relocated.data(), relocated.size(), kScenePreferredBase)) {
            return 4;
        }
        for (std::size_t offset = 0U; offset < relocated.size(); ++offset) {
            relocated[offset] ^= 1U;
            const bool accepted = IsReviewedSceneDisplayCode(
                relocated.data(), relocated.size(), base);
            relocated[offset] ^= 1U;
            if (accepted) { return 5; }
        }
    }
    std::puts("Reviewed routine, both relocation directions, and every-byte drift rejection passed.");
    return 0;
}
