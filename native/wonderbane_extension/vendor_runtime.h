#pragma once
#include "vendor_wire.h"
namespace wonderbane::extension::vendor {
// Initialization verifies the complete reviewed executable before registering
// the owning-thread service. It neither invokes the game nor starts a job.
bool Start() noexcept;
}
