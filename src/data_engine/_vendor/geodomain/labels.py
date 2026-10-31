"""Taxonomy of ground-truth labels and stress classes."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class LabelDefinition(BaseModel):
    """Single class label definition."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Canonical programmatic identifier, e.g. water_stress")
    class_id: int = Field(..., description="Zero-based or indexed integer label for ML models")
    display_name: str = Field(default="", description="Human-readable title")
    description: str = Field(default="", description="Agronomic or diagnostic description")
    color: str = Field(default="#888888", description="Hex color code for rendering")


class LabelSet(BaseModel):
    """Set of label definitions representing a complete classification schema."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str = "1.0.0"
    labels: list[LabelDefinition]

    @property
    def name_to_id(self) -> dict[str, int]:
        return {lbl.name: lbl.class_id for lbl in self.labels}

    @property
    def id_to_name(self) -> dict[int, str]:
        return {lbl.class_id: lbl.name for lbl in self.labels}

    def get(self, name_or_id: str | int) -> LabelDefinition | None:
        if isinstance(name_or_id, int):
            for lbl in self.labels:
                if lbl.class_id == name_or_id:
                    return lbl
            return None
        for lbl in self.labels:
            if lbl.name == name_or_id:
                return lbl
        return None


# Predefined canonical stress classification taxonomy
CANOPY_STRESS_TAXONOMY = LabelSet(
    name="canopy_stress",
    version="1.0.0",
    labels=[
        LabelDefinition(
            name="healthy_canopy",
            class_id=0,
            display_name="Healthy Canopy",
            description="Optimal vigor, balanced hydration, and normal chlorophyll absorption.",
            color="#2ecc71",
        ),
        LabelDefinition(
            name="water_stress",
            class_id=1,
            display_name="Water Stress",
            description="Reduced stomatal conductance, elevated thermal signature, depressed NDWI.",
            color="#e67e22",
        ),
        LabelDefinition(
            name="nitrogen_deficiency",
            class_id=2,
            display_name="Nitrogen Deficiency",
            description="Chlorosis, stunted canopy expansion, depressed red-edge response.",
            color="#f1c40f",
        ),
        LabelDefinition(
            name="salinity_stress",
            class_id=3,
            display_name="Salinity Stress",
            description="Osmotic stress, marginal leaf necrosis, reduced biomass accumulation.",
            color="#e74c3c",
        ),
    ],
)


class LabelRegistry:
    """Registry maintaining active label sets across regions and crops."""

    _registry: ClassVar[dict[str, LabelSet]] = {
        "canopy_stress": CANOPY_STRESS_TAXONOMY,
    }

    @classmethod
    def register(cls, label_set: LabelSet) -> None:
        cls._registry[label_set.name] = label_set

    @classmethod
    def get(cls, name: str = "canopy_stress") -> LabelSet:
        if name not in cls._registry:
            raise KeyError(f"LabelSet '{name}' not found in LabelRegistry")
        return cls._registry[name]

    @classmethod
    def validate_label(cls, name_or_id: str | int, label_set_name: str = "canopy_stress") -> bool:
        lset = cls.get(label_set_name)
        return lset.get(name_or_id) is not None
