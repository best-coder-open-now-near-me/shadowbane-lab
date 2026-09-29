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
    if (!IsReviewedSceneExecutable("3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7")
        || !IsReviewedSceneExecutable("2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289")
        || !IsReviewedSceneExecutable("6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19")
        || !IsReviewedSceneExecutable("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f")
        || !IsReviewedSceneExecutable("cae5311b5b6134bf25155b16c70b1743c1216c0bd0c88f1240d7e92388211d26")
        || !IsReviewedSceneExecutable("761f375e422332cac2512398bb935af38b30267b9b3a7a5cede9f87e98982442")
        || !IsReviewedSceneExecutable("a32275aabab8d5955f4d45adde6e84a666f44be54c951ccf8dc2d538237e8be4")
        || !IsReviewedSceneExecutable("e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891")
        || !IsReviewedSceneExecutable("ac9ca46467997667d49b85cd6076954813a72b56f71e2ad85a4085f3a9f391ca")
        || !IsReviewedSceneExecutable("b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3")
        || !IsReviewedSceneExecutable("feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff")
        || !IsReviewedSceneExecutable("bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87")) { return 4; }
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
