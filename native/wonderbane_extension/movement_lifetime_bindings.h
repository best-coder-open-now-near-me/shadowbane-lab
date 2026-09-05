#pragma once
#include <array>
#include <cstdint>
namespace wonderbane::extension::movement {
struct LifetimeBinding { std::uint32_t slot, original; };
// Exact reference-finalizer slots for every ArcObj-family type in the reviewed
// image's RTTI hierarchy. Generic reference Release verifies the shared ABI.
// Pre-register before scene observation; never lazily hook a captured actor.
inline constexpr std::array<LifetimeBinding, 34> kLifetimeBindings{{
    {0x11410f8, 0x1bc89}, // .?AVArcBaseCollisionObject@@
    {0x11415bc, 0x6a46}, // .?AVArcCharacter@@
    {0x1141de0, 0x13cc3}, // .?AVArcCombatObj@@
    {0x1142100, 0xe683}, // .?AVArcContainerObject@@
    {0x11423f8, 0x1a63b}, // .?AVArcDeed@@
    {0x11426d8, 0x24361}, // .?AVArcItem@@
    {0x1142af4, 0x287ef}, // .?AVArcMobile@@
    {0x1142e70, 0xb25d}, // .?AVArcObj@@
    {0x1143208, 0xc293}, // .?AVArcRune@@
    {0x11434d0, 0x1ecb8}, // .?AVArcStaticObject@@
    {0x11437ac, 0x2670b}, // .?AVArcStructureObject@@
    {0x1143c98, 0x169e1}, // .?AVWeatherEffectObject@@
    {0x1143ec4, 0x5d35}, // .?AVArcDoorObject@@
    {0x11440e4, 0x1229c}, // .?AVArcKey@@
    {0x114c068, 0x278e}, // .?AVArcTerrain@@
    {0x115adf4, 0x9755}, // .?AVArcDungeonUnitObject@@
    {0x115b038, 0x13827}, // .?AVArcDungeonExitObject@@
    {0x115b27c, 0x20360}, // .?AVArcDungeonStairObject@@
    {0x116482c, 0x32dd}, // .?AVArcWater@@
    {0x1177b9c, 0x25f9f}, // .?AVArcAssetStructureObject@@
    {0x1178240, 0xdf67}, // .?AVArcCityAsset@@
    {0x1178544, 0x2676f}, // .?AVArcCityAssetSupport@@
    {0x11787f0, 0x1122a}, // .?AVArcCityAssetWall@@
    {0x1178a9c, 0x8d55}, // .?AVArcCityAssetBuildingNexus@@
    {0x1178d48, 0x9b24}, // .?AVArcCityAssetBuildingNorm@@
    {0x1178ff4, 0x1c00d}, // .?AVArcCityAssetRunecircle@@
    {0x11792a0, 0x2c8e}, // .?AVArcCityAssetWartent@@
    {0x117954c, 0x5b0f}, // .?AVArcCityAssetLogic@@
    {0x11797f8, 0x236ff}, // .?AVArcCityAssetTree@@
    {0x1179ab0, 0x66ea}, // .?AVArcCityAssetWarehouse@@
    {0x1179d6c, 0x29163}, // .?AVArcCityAssetShrine@@
    {0x117a018, 0x1e286}, // .?AVArcCityAssetSpire@@
    {0x117a2c4, 0x28cef}, // .?AVArcCityAssetMineTower@@
    {0x117a4d0, 0x10181}, // .?AVArcCityAssetTemplate@@
}};
}
