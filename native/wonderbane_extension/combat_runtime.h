#pragma once
#include "event_channel.h"
namespace wonderbane::extension::combat {
bool Start(const ProcessIdentity&) noexcept;
bool Ready() noexcept;
}
