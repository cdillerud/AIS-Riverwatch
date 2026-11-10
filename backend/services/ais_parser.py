# River Watch Backend - AIS Parsing Service
# NMEA GPS and AIS message parsing functions
import logging
from typing import Optional, Dict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Navigation status codes from AIS
NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted maneuverability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved for HSC",
    10: "Reserved for WIG",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "AIS-SART (active)",
    15: "Not defined"
}

# ---------------------------------------------------------------------------
# Multi-sentence AIS reassembly
# ---------------------------------------------------------------------------
# Class A static/voyage reports (type 5 - vessel name, dimensions, ship type,
# destination) and some type 24s span TWO !AIVDM sentences. Decoding each line
# on its own raises MissingMultipartMessageException, so commercial vessels
# never got names/dimensions. The assembler buffers fragments until the set is
# complete and then returns all of them for pyais.decode(*fragments).
import time as _time


class NmeaFragmentAssembler:
    """Collects multi-part !xxVDM/!xxVDO sentences into complete messages."""

    def __init__(self, timeout_s: float = 10.0, max_pending: int = 500):
        self.timeout_s = timeout_s
        self.max_pending = max_pending
        self._pending: Dict[tuple, dict] = {}

    def feed(self, line: str) -> Optional[list]:
        """
        Returns the list of sentences for a complete message, or None while a
        multi-part message is still incomplete (or the line is not AIS).
        """
        line = (line or "").strip()
        if not line.startswith("!") or "VD" not in line[:7]:
            return None
        parts = line.split(",")
        if len(parts) < 7:
            return None
        try:
            count, num = int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if count <= 1:
            return [line]
        if not (1 <= num <= count <= 9):
            return None

        now = _time.monotonic()
        self._expire(now)
        key = (parts[0][1:3], parts[3], parts[4], count)  # talker, seq id, channel, count
        entry = self._pending.get(key)
        if num == 1 or entry is None:
            if num != 1:
                return None  # orphan continuation fragment
            entry = {"t": now, "frags": {}}
            self._pending[key] = entry
        entry["frags"][num] = line
        if len(entry["frags"]) == count:
            del self._pending[key]
            return [entry["frags"][i] for i in range(1, count + 1)]
        if len(self._pending) > self.max_pending:
            oldest = min(self._pending, key=lambda k: self._pending[k]["t"])
            self._pending.pop(oldest, None)
        return None

    def _expire(self, now: float) -> None:
        stale = [k for k, v in self._pending.items() if now - v["t"] > self.timeout_s]
        for k in stale:
            del self._pending[k]


# AIS "not available" sentinels
AIS_SOG_NOT_AVAILABLE = 102.3
AIS_COG_NOT_AVAILABLE = 360.0


def clean_sog(value) -> float:
    """Speed over ground in knots; 0 for missing / 'not available' (102.3)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v < 0 or v >= 102.2 else v


def clean_cog(value) -> Optional[float]:
    """Course over ground in degrees, or None for missing / 'not available' (360)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v < 0 or v >= 360 else v


# In-memory cache for vessel static data (name, dimensions, etc.)
# This is populated by AIS Type 5/19/24 messages and shared across sessions
vessel_static_cache: Dict[str, dict] = {}


def parse_nmea_gps(line: str) -> Optional[dict]:
    """
    Parse NMEA GPS sentences for user's own position.
    Supports: $GPGGA, $GPRMC, $GPGLL, $GNGGA, $GNRMC, $GNGLL
    
    Returns dict with lat, lon, speed (if available), or None if parsing fails.
    """
    try:
        line = line.strip()
        
        # Check for GPS sentence types
        if not any(line.startswith(prefix) for prefix in ['$GPGGA', '$GPRMC', '$GPGLL', '$GNGGA', '$GNRMC', '$GNGLL']):
            return None
        
        # Remove checksum if present
        if '*' in line:
            line = line.split('*')[0]
        
        parts = line.split(',')
        sentence_type = parts[0]
        
        # Parse GPGGA / GNGGA (GPS Fix Data)
        if 'GGA' in sentence_type and len(parts) >= 10:
            lat_raw = parts[2]
            lat_dir = parts[3]
            lon_raw = parts[4]
            lon_dir = parts[5]
            
            if lat_raw and lon_raw:
                # Convert NMEA format (DDMM.MMMM) to decimal degrees
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': 0,  # GGA doesn't have speed
                    'course': 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
        
        # Parse GPRMC / GNRMC (Recommended Minimum)
        elif 'RMC' in sentence_type and len(parts) >= 10:
            status = parts[2]  # A=valid, V=invalid
            if status != 'A':
                return None
            
            lat_raw = parts[3]
            lat_dir = parts[4]
            lon_raw = parts[5]
            lon_dir = parts[6]
            speed_knots = parts[7]  # Speed over ground in knots
            course = parts[8]  # Course over ground
            
            if lat_raw and lon_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': float(speed_knots) if speed_knots else 0,
                    'course': float(course) if course else 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
        
        # Parse GPGLL / GNGLL (Geographic Position)
        elif 'GLL' in sentence_type and len(parts) >= 6:
            lat_raw = parts[1]
            lat_dir = parts[2]
            lon_raw = parts[3]
            lon_dir = parts[4]
            
            if lat_raw and lon_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                lat = lat_deg + lat_min / 60
                if lat_dir == 'S':
                    lat = -lat
                
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                lon = lon_deg + lon_min / 60
                if lon_dir == 'W':
                    lon = -lon
                
                return {
                    'lat': lat,
                    'lon': lon,
                    'speed': 0,
                    'course': 0,
                    'is_gps': True,
                    'sentence': sentence_type
                }
    except Exception as e:
        logger.debug(f"GPS parse error: {e}")
    
    return None


def parse_nmea_ais(data: str, get_usace_vessel_info_fn=None) -> Optional[dict]:
    """
    Parse NMEA/AIS data. Boat Beacon typically sends !AIVDM sentences.
    Returns vessel info dict or None if parsing fails.
    
    AIS Message Types:
    - Types 1,2,3: Class A position reports (frequent, NO name)
    - Type 5: Class A static/voyage data (every 6 min, HAS name, dimensions, ship type)
    - Type 18: Class B position report (frequent, NO name)  
    - Type 19: Class B extended position (infrequent, HAS name)
    - Type 24: Class B static data (HAS name)
    
    Args:
        data: Raw NMEA/AIS string
        get_usace_vessel_info_fn: Optional callback to get USACE vessel info
    """
    global vessel_static_cache
    
    # Debug: log all incoming data
    if data.startswith('!AIVDM') or data.startswith('!AIVDO'):
        logger.info(f"parse_nmea_ais called with: {data[:80]}")
    
    try:
        from pyais import decode
        
        lines = data.strip().split('\n')
        for line in lines:
            line = line.strip()
            
            # Handle AIVDO (own vessel) and AIVDM (other vessels) messages
            is_own_vessel = line.startswith('!AIVDO')
            
            if line.startswith('!AIVDM') or line.startswith('!AIVDO'):
                try:
                    msg = decode(line)
                    decoded = msg.asdict()
                    
                    if 'mmsi' not in decoded:
                        continue
                        
                    mmsi = str(decoded.get('mmsi', ''))
                    msg_type = decoded.get('msg_type', 0)
                    
                    # Mark if this is own vessel data (AIVDO)
                    if is_own_vessel:
                        logger.debug(f"Own vessel data received: MMSI {mmsi}")
                    
                    # Handle static data messages (Type 5, 19, 24) - cache the vessel info
                    if msg_type in [5, 19, 24]:
                        static_data = {'is_own_vessel': is_own_vessel}
                        
                        # Get vessel name
                        shipname = decoded.get('shipname', '') or decoded.get('name', '')
                        if shipname and shipname.strip() and shipname.strip() != '@@@@@@@@@@@@@@@@@@@@':
                            static_data['name'] = shipname.strip()
                        
                        # Get call sign
                        callsign = decoded.get('callsign', '')
                        if callsign and callsign.strip() and '@' not in callsign:
                            static_data['callsign'] = callsign.strip()
                        
                        # Get IMO number
                        if decoded.get('imo'):
                            static_data['imo'] = decoded.get('imo')
                        
                        # Get destination
                        destination = decoded.get('destination', '')
                        if destination and destination.strip() and '@' not in destination:
                            static_data['destination'] = destination.strip()
                        
                        # Get ETA (from Type 5)
                        if decoded.get('month') and decoded.get('day'):
                            eta_month = decoded.get('month', 0)
                            eta_day = decoded.get('day', 0)
                            eta_hour = decoded.get('hour', 0)
                            eta_min = decoded.get('minute', 0)
                            if eta_month > 0 and eta_day > 0:
                                static_data['eta'] = f"{eta_month:02d}/{eta_day:02d} {eta_hour:02d}:{eta_min:02d}"
                        
                        # Get ship type and dimensions
                        if decoded.get('ship_type'):
                            static_data['ship_type'] = decoded.get('ship_type')
                        
                        # Calculate dimensions from bow/stern/port/starboard
                        to_bow = decoded.get('to_bow', 0) or 0
                        to_stern = decoded.get('to_stern', 0) or 0
                        to_port = decoded.get('to_port', 0) or 0
                        to_starboard = decoded.get('to_starboard', 0) or 0
                        
                        if to_bow + to_stern > 0:
                            static_data['length'] = to_bow + to_stern
                        if to_port + to_starboard > 0:
                            static_data['width'] = to_port + to_starboard
                        
                        if decoded.get('draught'):
                            static_data['draught'] = decoded.get('draught')
                        
                        # Update cache
                        if static_data:
                            if mmsi not in vessel_static_cache:
                                vessel_static_cache[mmsi] = {}
                            vessel_static_cache[mmsi].update(static_data)
                            logger.info(f"Cached static data for MMSI {mmsi}: {static_data.get('name', 'unnamed')}")
                            
                            # Mark for persistence to database (will be done in async context)
                            if static_data.get('name'):
                                static_data['_persist_to_db'] = True
                                static_data['_mmsi'] = mmsi
                    
                    # Handle position messages (Type 1,2,3,18,19)
                    if msg_type in [1, 2, 3, 18, 19]:
                        lat = decoded.get('lat')
                        lon = decoded.get('lon')
                        
                        # Filter invalid positions
                        if lat is None or lon is None:
                            continue
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            continue
                        if lat == 91.0 or lon == 181.0:  # AIS "not available" values
                            continue
                        
                        # Get navigation status
                        nav_status = decoded.get('status')
                        nav_status_text = NAV_STATUS.get(nav_status, 'Unknown') if nav_status is not None else None
                        
                        # Get heading (true heading, different from course over ground)
                        heading_true = decoded.get('heading')
                        if heading_true == 511:  # 511 = not available
                            heading_true = None
                        
                        # Get rate of turn
                        turn_rate = decoded.get('turn')
                        if turn_rate == -128 or turn_rate == 128:  # not available
                            turn_rate = None
                        
                        # Build vessel data from position report
                        vessel = {
                            'mmsi': mmsi,
                            'lat': lat,
                            'lon': lon,
                            'speed': decoded.get('speed', 0) or 0,  # knots
                            'course': decoded.get('course', 0) or 0,
                            'name': '',
                            'vessel_type': 'unknown',
                            'ship_type': 0,
                            'length': None,
                            'width': None,
                            'draught': None,
                            'is_own_vessel': is_own_vessel,
                            'heading_true': heading_true,
                            'turn_rate': turn_rate,
                            'nav_status': nav_status,
                            'nav_status_text': nav_status_text,
                        }
                        
                        # Merge in cached static data if available
                        if mmsi in vessel_static_cache:
                            cached = vessel_static_cache[mmsi]
                            if cached.get('name'):
                                vessel['name'] = cached['name']
                            if cached.get('ship_type'):
                                vessel['ship_type'] = cached['ship_type']
                                vessel['vessel_type'] = str(cached['ship_type'])
                            if cached.get('length'):
                                vessel['length'] = cached['length']
                            if cached.get('width'):
                                vessel['width'] = cached['width']
                            if cached.get('draught'):
                                vessel['draught'] = cached['draught']
                            if cached.get('destination'):
                                vessel['destination'] = cached['destination']
                            if cached.get('callsign'):
                                vessel['callsign'] = cached['callsign']
                            if cached.get('imo'):
                                vessel['imo'] = cached['imo']
                            if cached.get('eta'):
                                vessel['eta'] = cached['eta']
                            if cached.get('is_own_vessel') or cached.get('is_user'):
                                vessel['is_own_vessel'] = True
                        
                        # Type 19 includes name directly
                        if msg_type == 19:
                            shipname = decoded.get('shipname', '')
                            if shipname and shipname.strip():
                                vessel['name'] = shipname.strip()
                        
                        # Check USACE lock queue data for authoritative barge count
                        if get_usace_vessel_info_fn:
                            usace_info = get_usace_vessel_info_fn(mmsi)
                            
                            if usace_info and usace_info.get('num_barges') is not None:
                                # Use USACE authoritative data
                                vessel['barge_count'] = usace_info['num_barges']
                                vessel['is_tow'] = usace_info['num_barges'] > 0
                                vessel['usace_source'] = True
                                vessel['usace_lock'] = usace_info.get('lock_id')
                                vessel['usace_status'] = usace_info.get('status')
                            elif usace_info and usace_info.get('barge_count') is not None:
                                vessel['barge_count'] = usace_info['barge_count']
                                vessel['is_tow'] = usace_info.get('is_tow', False)
                                vessel['usace_source'] = True
                        
                        # Estimate tow status from ship type if no USACE data
                        if not vessel.get('usace_source'):
                            ship_type = vessel.get('ship_type', 0)
                            if ship_type in [31, 32, 52]:  # Towing vessels
                                vessel['is_tow'] = True
                            elif vessel.get('name', '').upper().startswith(('M/V', 'TUG', 'TOW')):
                                vessel['is_tow'] = True
                        
                        return vessel
                        
                except Exception as e:
                    logger.debug(f"AIS decode error for line: {e}")
                    continue
    
    except ImportError:
        logger.error("pyais library not installed - cannot parse AIS data")
    except Exception as e:
        logger.error(f"AIS parse error: {e}")
    
    return None


def get_cached_vessel_name(mmsi: str) -> Optional[str]:
    """Get vessel name from static cache."""
    if mmsi in vessel_static_cache:
        return vessel_static_cache[mmsi].get('name')
    return None


def set_cached_vessel_info(mmsi: str, info: dict):
    """Set vessel info in static cache."""
    if mmsi not in vessel_static_cache:
        vessel_static_cache[mmsi] = {}
    vessel_static_cache[mmsi].update(info)


def get_all_cached_vessels() -> Dict[str, dict]:
    """Get all cached vessel static data."""
    return vessel_static_cache.copy()
