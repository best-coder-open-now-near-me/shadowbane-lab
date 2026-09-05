#pragma once
#include "movement_runtime.h"
namespace wonderbane::extension::movement {
Settings LoadMovementPreferences() noexcept;
bool ShowMovementSettings(const RuntimeSnapshot&) noexcept;
}
