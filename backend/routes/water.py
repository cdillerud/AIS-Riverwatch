# River Watch Backend - Water Conditions Routes
# USGS water level, temperature, and current speed data
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from config import LOCKS, USGS_GAUGES
from services.usgs_service import (
    get_water_conditions_for_lock,
    get_all_water_conditions,
    format_water_conditions_for_display
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/water-conditions", tags=["Water Conditions"])


@router.get("/{lock_id}")
async def get_water_conditions_for_lock_endpoint(lock_id: str):
    """Get water conditions for a specific lock's nearest gauge."""
    if lock_id not in LOCKS:
        raise HTTPException(status_code=404, detail=f"Lock {lock_id} not found")
    
    if lock_id not in USGS_GAUGES:
        return {
            "lock_id": lock_id,
            "available": False,
            "message": "No gauge data available for this lock"
        }
    
    data = await get_water_conditions_for_lock(lock_id)
    return format_water_conditions_for_display(data)


@router.get("")
async def get_all_water_conditions_endpoint():
    """Get water conditions for all locks with USGS gauges."""
    all_conditions = await get_all_water_conditions()
    
    result = []
    for lock_id, data in all_conditions.items():
        formatted = format_water_conditions_for_display(data)
        formatted["lock_id"] = lock_id
        result.append(formatted)
    
    return result
