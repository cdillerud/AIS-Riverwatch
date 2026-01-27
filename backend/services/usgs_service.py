# River Watch Backend - USGS Water Services
# Fetches real-time water level, temperature, and current data from USGS gauges
import asyncio
import logging
import httpx
from typing import Dict, Optional
from datetime import datetime, timezone

from config import USGS_GAUGES, USGS_PARAMS, FLOOD_STAGES

logger = logging.getLogger(__name__)

# Cache for USGS data
usgs_data_cache: Dict[str, dict] = {}


async def fetch_usgs_water_data(site_id: str) -> dict:
    """
    Fetch current water conditions from USGS Water Services API.
    Returns gage height, discharge, and water temperature if available.
    """
    try:
        # USGS instantaneous values service
        url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site_id}&siteStatus=active"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=15.0)
            
            if response.status_code != 200:
                logger.warning(f"USGS API returned {response.status_code} for site {site_id}")
                return {}
            
            data = response.json()
            
            result = {
                "site_id": site_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "values": {}
            }
            
            # Parse the time series data
            time_series = data.get("value", {}).get("timeSeries", [])
            
            for series in time_series:
                try:
                    variable = series.get("variable", {})
                    param_code = variable.get("variableCode", [{}])[0].get("value")
                    
                    if param_code not in USGS_PARAMS:
                        continue
                    
                    param_name = USGS_PARAMS[param_code]
                    
                    values = series.get("values", [{}])[0].get("value", [])
                    if values:
                        latest = values[-1]
                        value = float(latest.get("value", 0))
                        
                        result["values"][param_name] = {
                            "value": value,
                            "unit": variable.get("unit", {}).get("unitCode", ""),
                            "datetime": latest.get("dateTime")
                        }
                        
                except Exception as e:
                    logger.error(f"Error parsing USGS series: {e}")
                    continue
            
            # Add flood stage info if available
            if site_id in FLOOD_STAGES:
                stages = FLOOD_STAGES[site_id]
                gage_height = result["values"].get("gage_height", {}).get("value")
                
                if gage_height:
                    if gage_height >= stages["major"]:
                        result["flood_status"] = "major"
                    elif gage_height >= stages["moderate"]:
                        result["flood_status"] = "moderate"
                    elif gage_height >= stages["flood"]:
                        result["flood_status"] = "flood"
                    elif gage_height >= stages["action"]:
                        result["flood_status"] = "action"
                    else:
                        result["flood_status"] = "normal"
                    
                    result["flood_stages"] = stages
            
            return result
            
    except Exception as e:
        logger.error(f"Error fetching USGS data for site {site_id}: {e}")
        return {}


async def get_water_conditions_for_lock(lock_id: str) -> dict:
    """
    Get water conditions for a specific lock.
    Uses the nearest USGS gauge station.
    """
    gauge_info = USGS_GAUGES.get(lock_id)
    
    if not gauge_info:
        return {
            "error": f"No gauge data available for {lock_id}",
            "available": False
        }
    
    site_id = gauge_info["site_id"]
    
    # Check cache first (cache for 5 minutes)
    cache_key = f"{lock_id}_{site_id}"
    if cache_key in usgs_data_cache:
        cached = usgs_data_cache[cache_key]
        cache_time = datetime.fromisoformat(cached.get("timestamp", "2000-01-01T00:00:00+00:00").replace('Z', '+00:00'))
        if (datetime.now(timezone.utc) - cache_time).total_seconds() < 300:
            return cached
    
    # Fetch fresh data
    data = await fetch_usgs_water_data(site_id)
    
    if data:
        data["lock_id"] = lock_id
        data["gauge_name"] = gauge_info.get("name")
        data["gauge_river_mile"] = gauge_info.get("river_mile")
        data["available"] = True
        
        # Cache the result
        usgs_data_cache[cache_key] = data
        
        return data
    
    return {
        "lock_id": lock_id,
        "error": "Failed to fetch water data",
        "available": False
    }


async def get_all_water_conditions() -> Dict[str, dict]:
    """
    Fetch water conditions for all locks with USGS gauges.
    Returns dict keyed by lock_id.
    """
    results = {}
    
    # Get unique site IDs to avoid duplicate fetches
    site_to_locks: Dict[str, list] = {}
    for lock_id, gauge_info in USGS_GAUGES.items():
        site_id = gauge_info["site_id"]
        if site_id not in site_to_locks:
            site_to_locks[site_id] = []
        site_to_locks[site_id].append(lock_id)
    
    # Fetch data for each unique site
    for site_id, lock_ids in site_to_locks.items():
        data = await fetch_usgs_water_data(site_id)
        
        for lock_id in lock_ids:
            gauge_info = USGS_GAUGES[lock_id]
            lock_data = {
                **data,
                "lock_id": lock_id,
                "gauge_name": gauge_info.get("name"),
                "gauge_river_mile": gauge_info.get("river_mile"),
                "available": bool(data)
            }
            results[lock_id] = lock_data
    
    return results


def format_water_conditions_for_display(data: dict) -> dict:
    """
    Format water conditions data for frontend display.
    """
    if not data or not data.get("available"):
        return {
            "available": False,
            "message": "Water conditions data not available"
        }
    
    values = data.get("values", {})
    
    result = {
        "available": True,
        "gauge_name": data.get("gauge_name"),
        "gauge_river_mile": data.get("gauge_river_mile"),
        "flood_status": data.get("flood_status", "unknown"),
        "timestamp": data.get("timestamp")
    }
    
    # Gage height
    if "gage_height" in values:
        gh = values["gage_height"]
        result["water_level_ft"] = round(gh.get("value", 0), 1)
        result["water_level_unit"] = "ft"
    
    # Discharge (convert cfs to mph current estimate)
    if "discharge" in values:
        discharge = values["discharge"]
        cfs = discharge.get("value", 0)
        result["discharge_cfs"] = round(cfs, 0)
        # Very rough estimate: Mississippi current speed
        # Actual current varies greatly with river width/depth
        # This is just for display purposes
        if cfs > 0:
            result["estimated_current_mph"] = round(min(cfs / 50000, 5), 1)
    
    # Water temperature
    if "water_temp" in values:
        wt = values["water_temp"]
        celsius = wt.get("value", 0)
        fahrenheit = (celsius * 9/5) + 32
        result["water_temp_f"] = round(fahrenheit, 1)
        result["water_temp_c"] = round(celsius, 1)
    
    # Add flood stage thresholds if available
    if "flood_stages" in data:
        result["flood_stages"] = data["flood_stages"]
    
    return result
