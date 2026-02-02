from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional


class ChannelUpdate(BaseModel):
    """Request model for updating a channel value."""
    value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Channel value between 0.0 and 1.0"
    )

    @field_validator('value')
    @classmethod
    def validate_value_precision(cls, v: float) -> float:
        """Limit precision to 3 decimal places."""
        return round(v, 3)


class Channel(BaseModel):
    """Model representing a single channel."""
    id: int = Field(..., ge=1, le=8, description="Channel ID (1-8)")
    value: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Current channel value"
    )
    last_updated: datetime = Field(
        default_factory=datetime.now,
        description="Last update timestamp"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": 1,
                "value": 0.500,
                "last_updated": "2026-01-28T12:00:00"
            }
        }
    }


class ChannelState(BaseModel):
    """Model representing the state of all channels."""
    channels: list[Channel]
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="State snapshot timestamp"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "channels": [
                    {"id": 1, "value": 0.500, "last_updated": "2026-01-28T12:00:00"},
                    {"id": 2, "value": 0.750, "last_updated": "2026-01-28T12:00:01"}
                ],
                "timestamp": "2026-01-28T12:00:01"
            }
        }
    }
