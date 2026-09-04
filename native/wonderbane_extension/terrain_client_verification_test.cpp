#include "terrain_client_verification.h"

#include <cstdlib>
#include <iostream>

int main() {
#if !defined(_WIN32) || defined(_WIN64)
    const auto report =
        wonderbane::extension::terrain_material::VerifyClientProfile(nullptr);
    if (report.error != wonderbane::extension::terrain_material::
                            ClientVerificationError::unsupported_platform) {
        std::cerr << "unsupported profile did not fail closed\n";
        return EXIT_FAILURE;
    }
#endif
    std::cout << "terrain client verification tests passed\n";
    return EXIT_SUCCESS;
}
