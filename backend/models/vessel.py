# River Watch Backend - Vessel Models
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ConnectionConfig(BaseModel):
    host: str
    port: int


class VesselPosition(BaseModel):
    """Represents a vessel's current position and status."""
    model_config = ConfigDict(populate_by_name=True)
    
    mmsi: str
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    speed: Optional[float] = Field(None, description="Speed over ground in knots")
    course: Optional[float] = Field(None, description="Course over ground in degrees")
    heading: Optional[float] = Field(None, description="True heading in degrees")
    nav_status: Optional[int] = Field(None, description="Navigation status code")
    ship_type: Optional[int] = Field(None, description="Ship type code")
    dimension_a: Optional[int] = None
    dimension_b: Optional[int] = None
    dimension_c: Optional[int] = None
    dimension_d: Optional[int] = None
    destination: Optional[str] = None
    eta_month: Optional[int] = None
    eta_day: Optional[int] = None
    eta_hour: Optional[int] = None
    eta_minute: Optional[int] = None
    draught: Optional[float] = None
    last_update: Optional[str] = None
    last_ais_checkin: Optional[str] = None
    message_type: Optional[int] = None
    
    # Calculated fields
    river_mile: Optional[float] = None
    heading_direction: Optional[str] = None  # "upstream" or "downstream"
    is_user_vessel: bool = False
    is_commercial: bool = False
    
    # USACE data enrichment
    usace_data: Optional[dict] = None
    barge_count: Optional[int] = None
    tow_name: Optional[str] = None


class VesselUpdate(BaseModel):
    """Model for updating vessel position manually."""
    lat: float
    lon: float
    speed: Optional[float] = None
    course: Optional[float] = None
