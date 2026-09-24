#pragma once
namespace wonderbane::extension::furnishing {
// Optional startup after shared initialization, outside loader lock. Native work
// remains confined to the existing observed owner callback and reviewed drain.
bool Start() noexcept;
}
