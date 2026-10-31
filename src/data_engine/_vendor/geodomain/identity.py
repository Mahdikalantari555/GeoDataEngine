"""Canonical identity model and GeoURI parser/serializer."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityRef(BaseModel):
    """Canonical typed reference to a domain entity (e.g. geo:farm/<id>)."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(..., min_length=1, description="Entity type: farm, field, scene, observation, asset, etc.")
    id: str = Field(..., min_length=1, description="Entity unique identifier")

    @classmethod
    def from_uri(cls, uri: str) -> "EntityRef":
        """Parse geo:<type>/<id> into an EntityRef."""
        if not uri.startswith("geo:"):
            raise ValueError(f"Invalid GeoURI, must start with 'geo:': {uri}")
        body = uri[4:]
        parts = body.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid GeoURI format, expected 'geo:<type>/<id>': {uri}")
        return cls(type=parts[0], id=parts[1])

    def to_uri(self) -> str:
        """Serialize EntityRef to geo:<type>/<id>."""
        return f"geo:{self.type}/{self.id}"

    def __str__(self) -> str:
        return self.to_uri()


class GeoURI(str):
    """String wrapper validating geo:<type>/<id> syntax."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        from pydantic_core import core_schema

        def validate(value: Any) -> str:
            if isinstance(value, EntityRef):
                return value.to_uri()
            if not isinstance(value, str):
                raise TypeError(f"Expected string or EntityRef, got {type(value).__name__}")
            EntityRef.from_uri(value)
            return value

        return core_schema.chain_schema(
            [
                core_schema.no_info_plain_validator_function(validate),
                core_schema.str_schema(),
            ]
        )
