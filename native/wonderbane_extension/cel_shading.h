#pragma once

#include <Windows.h>

#include <cstddef>

namespace wonderbane::extension {

bool IsPerspectiveProjectionMatrix(const float* matrix, std::size_t count) noexcept;
bool IsOutlinePrimitive(unsigned int mode, int count) noexcept;

DWORD StartStrongCelShading() noexcept;
void StopStrongCelShading() noexcept;

}  // namespace wonderbane::extension
