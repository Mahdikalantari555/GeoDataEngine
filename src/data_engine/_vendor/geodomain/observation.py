"""Observation models and contracts."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .identity import EntityRef
from .temporal import UtcTimestamp, utc_now_iso


class ObservationKind:
    """Standard observation metric/kind identifiers."""

    NDVI = "ndvi"
    EVI = "evi"
    NDWI = "ndwi"
    SAVI = "savi"
    WATER_STRESS = "water_stress"
    NITROGEN_DEFICIENCY = "nitrogen_deficiency"
    SALINITY_STRESS = "salinity_stress"
    HEALTHY_CANOPY = "healthy_canopy"
    EVAPOTRANSPIRATION = "evapotranspiration"
    SOIL_MOISTURE = "soil_moisture"


class ObservationRef(BaseModel):
    """Reference to an observation."""

    model_config = ConfigDict(frozen=True)

    observation_id: str
    uri: str = ""

    def __init__(self, observation_id: str, **data: Any) -> None:
        uri = data.get("uri") or f"geo:observation/{observation_id}"
        super().__init__(observation_id=observation_id, uri=uri)


def default_obs_id() -> str:
    return f"obs_{uuid.uuid4().hex[:12]}"


class Observation(BaseModel):
    """Authoritative domain observation representing a biophysical/remote sensing measurement."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(default_factory=default_obs_id)
    subject_id: str
    subject_type: str = "raster_scene"  # farm, field, raster_scene, asset, etc.
    metric: str
    value: float
    unit: str | None = None
    observed_at: UtcTimestamp = Field(default_factory=utc_now_iso)
    valid_from: UtcTimestamp | None = None
    valid_to: UtcTimestamp | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: UtcTimestamp = Field(default_factory=utc_now_iso)

    @property
    def entity_ref(self) -> EntityRef:
        """Return EntityRef for the observation's subject."""
        return EntityRef(type=self.subject_type, id=self.subject_id)

    @property
    def observation_ref(self) -> ObservationRef:
        """Return ObservationRef for this observation."""
        return ObservationRef(observation_id=self.id)
