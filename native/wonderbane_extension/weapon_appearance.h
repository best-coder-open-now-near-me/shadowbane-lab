#pragma once
#include <Windows.h>
#include <cstdint>
namespace wonderbane::extension::weapon {
void Start(std::uint32_t base) noexcept;
void Stop() noexcept;
void BeginScene(bool camera_available) noexcept;
void EndScene() noexcept;
bool WantsDraws() noexcept;
class RenderScope {
    float previous_;
public:
    explicit RenderScope(void* submission) noexcept;
    ~RenderScope();
};
class DrawScale {
    bool pushed_=false;
public:
    DrawScale() noexcept;
    ~DrawScale();
};
}
