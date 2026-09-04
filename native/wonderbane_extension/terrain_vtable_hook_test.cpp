#include "terrain_vtable_hook.h"

#include <cstdlib>
#include <iostream>

namespace terrain = wonderbane::extension::terrain_material;

namespace {

void Original() {}
void Replacement() {}
void ThirdParty() {}

void Expect(const bool condition, const char* message) {
    if (!condition) {
        std::cerr << "terrain_vtable_hook_test: " << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

}  // namespace

int main() {
#if defined(_WIN32)
    void* slot = reinterpret_cast<void*>(&Original);
    terrain::VtableHook hook;

    Expect(
        terrain::InstallVtableHook(
            hook,
            &slot,
            reinterpret_cast<void*>(&Original),
            reinterpret_cast<void*>(&Replacement)) == terrain::VtableHookResult::ok,
        "installation failed");
    Expect(slot == reinterpret_cast<void*>(&Replacement) && hook.installed,
        "installation did not own slot");
    Expect(
        terrain::InstallVtableHook(
            hook,
            &slot,
            reinterpret_cast<void*>(&Original),
            reinterpret_cast<void*>(&Replacement)) ==
            terrain::VtableHookResult::already_installed,
        "duplicate installation accepted");
    Expect(terrain::RemoveVtableHook(hook) == terrain::VtableHookResult::ok,
        "removal failed");
    Expect(slot == reinterpret_cast<void*>(&Original) && !hook.installed,
        "removal did not restore original");

    slot = reinterpret_cast<void*>(&ThirdParty);
    Expect(
        terrain::InstallVtableHook(
            hook,
            &slot,
            reinterpret_cast<void*>(&Original),
            reinterpret_cast<void*>(&Replacement)) ==
            terrain::VtableHookResult::unexpected_original,
        "unexpected original was overwritten");
    Expect(slot == reinterpret_cast<void*>(&ThirdParty),
        "failed install changed third-party slot");

    slot = reinterpret_cast<void*>(&Original);
    Expect(
        terrain::InstallVtableHook(
            hook,
            &slot,
            reinterpret_cast<void*>(&Original),
            reinterpret_cast<void*>(&Replacement)) == terrain::VtableHookResult::ok,
        "second installation failed");
    slot = reinterpret_cast<void*>(&ThirdParty);
    Expect(
        terrain::RemoveVtableHook(hook) ==
            terrain::VtableHookResult::restore_conflict,
        "restore conflict was hidden");
    Expect(slot == reinterpret_cast<void*>(&ThirdParty) && !hook.installed,
        "restore conflict clobbered another owner");
#else
    terrain::VtableHook hook;
    void* slot = nullptr;
    Expect(
        terrain::InstallVtableHook(hook, &slot, &slot, &hook) ==
            terrain::VtableHookResult::unsupported_platform,
        "non-Windows installation did not fail closed");
    Expect(
        terrain::RemoveVtableHook(hook) ==
            terrain::VtableHookResult::unsupported_platform,
        "non-Windows removal did not fail closed");
#endif

    std::cout << "terrain vtable hook tests passed\n";
    return EXIT_SUCCESS;
}
