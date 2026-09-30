#pragma once
#include "combat_submission.h"
#include <cstdint>

namespace wonderbane::extension::combat::melee {
using Admission = bool (*)(void*) noexcept;
// Owner-thread entry for exact retained ArcCharacter objects. NativeTarget owns
// both request slots outside this faulting frame; an exception quarantines them.
// Bind/identity/party/admission and exact-image verification belong to the caller.
bool Invoke(std::uintptr_t image, void* actor, void* target, submission::Scope&,
    void*& request, void*& transfer, Admission current, void* context);
void Release(void*& request);
}
