#pragma once
#include "event_channel.h"

namespace wonderbane::extension {
// Passive, opt-in diagnostic only. Records decoded fields, never attack authority.
DWORD StartTargetedActionTrace(const ProcessIdentity& identity) noexcept;
void StopTargetedActionTrace() noexcept;
}  // namespace wonderbane::extension
