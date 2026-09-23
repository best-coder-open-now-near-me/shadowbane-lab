"""Equipment data and legal affix composition for PvP simulation."""

from shadowbane_lab.equipment.loader import (
    EquipmentCatalogLoadError,
    load_bundled_equipment_catalog,
    load_equipment_catalog,
    load_equipment_catalog_text,
)
from shadowbane_lab.equipment.model import (
    AffixChoice,
    AffixModifier,
    AffixPool,
    AffixPoolEntry,
    AffixPosition,
    AffixRoute,
    BaseItem,
    EquipmentCatalog,
    ItemRequirement,
)

__all__ = [
    "AffixChoice",
    "AffixModifier",
    "AffixPool",
    "AffixPoolEntry",
    "AffixPosition",
    "AffixRoute",
    "BaseItem",
    "EquipmentCatalog",
    "EquipmentCatalogLoadError",
    "ItemRequirement",
    "load_bundled_equipment_catalog",
    "load_equipment_catalog",
    "load_equipment_catalog_text",
]
