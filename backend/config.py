# River Watch Backend - Configuration
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB Configuration
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# CORS Configuration
def get_cors_origins():
    """Get CORS origins from environment or use defaults."""
    cors_origins_env = os.environ.get('CORS_ORIGINS', '')
    if cors_origins_env:
        return [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
    # Default origins for development and production
    return [
        "http://localhost:3000",
        "https://vessel-tracker-24.preview.emergentagent.com"
    ]

# AIS Connection defaults
DEFAULT_AIS_HOST = "136.116.165.255"
DEFAULT_AIS_PORT = 7000

# Lock definitions for Upper Mississippi River (with GPS coordinates and phone)
LOCKS = {
    "lock_1": {"name": "Lock & Dam #1 (Minneapolis)", "river_mile": 847.6, "lat": 44.9178, "lon": -93.2056, "phone": "612-724-2971"},
    "lock_2": {"name": "Lock & Dam #2 (Hastings)", "river_mile": 815.2, "lat": 44.7433, "lon": -92.8506, "phone": "651-436-2900"},
    "lock_3": {"name": "Lock & Dam #3 (Red Wing)", "river_mile": 796.9, "lat": 44.5533, "lon": -92.5356, "phone": "651-388-5794"},
    "lock_4": {"name": "Lock & Dam #4 (Alma)", "river_mile": 752.8, "lat": 44.3189, "lon": -91.9150, "phone": "608-685-4421"},
    "lock_5": {"name": "Lock & Dam #5 (Minnesota City)", "river_mile": 738.1, "lat": 44.1047, "lon": -91.7428, "phone": "507-689-2101"},
    "lock_5a": {"name": "Lock & Dam #5A (Fountain City)", "river_mile": 728.5, "lat": 44.0317, "lon": -91.7089, "phone": "507-452-2789"},
    "lock_6": {"name": "Lock & Dam #6 (Trempealeau)", "river_mile": 714.3, "lat": 43.8697, "lon": -91.5006, "phone": "608-534-6424"},
    "lock_7": {"name": "Lock & Dam #7 (Dresbach)", "river_mile": 702.5, "lat": 43.8128, "lon": -91.3053, "phone": "507-895-2170"},
    "lock_8": {"name": "Lock & Dam #8 (Genoa)", "river_mile": 679.2, "lat": 43.5789, "lon": -91.2294, "phone": "608-689-2625"},
    "lock_9": {"name": "Lock & Dam #9 (Lynxville)", "river_mile": 647.9, "lat": 43.2108, "lon": -91.0836, "phone": "608-874-4311"},
    "lock_10": {"name": "Lock & Dam #10 (Guttenberg)", "river_mile": 615.1, "lat": 42.7856, "lon": -91.1003, "phone": "563-252-1261"},
    "lock_11": {"name": "Lock & Dam #11 (Dubuque)", "river_mile": 583.0, "lat": 42.5036, "lon": -90.6581, "phone": "563-582-0881"},
    "lock_12": {"name": "Lock & Dam #12 (Bellevue)", "river_mile": 556.7, "lat": 42.2578, "lon": -90.4214, "phone": "563-872-4384"},
    "lock_13": {"name": "Lock & Dam #13 (Fulton)", "river_mile": 522.5, "lat": 41.8711, "lon": -90.1547, "phone": "815-589-2274"},
    "lock_14": {"name": "Lock & Dam #14 (Le Claire)", "river_mile": 493.3, "lat": 41.5978, "lon": -90.4336, "phone": "563-289-4233"},
    "lock_15": {"name": "Lock & Dam #15 (Rock Island)", "river_mile": 482.9, "lat": 41.5189, "lon": -90.5628, "phone": "309-794-5338"},
    "lock_16": {"name": "Lock & Dam #16 (Muscatine)", "river_mile": 457.2, "lat": 41.4231, "lon": -91.0439, "phone": "563-263-7913"},
    "lock_17": {"name": "Lock & Dam #17 (New Boston)", "river_mile": 437.1, "lat": 41.1725, "lon": -91.0142, "phone": "309-587-8461"},
    "lock_18": {"name": "Lock & Dam #18 (Gladstone)", "river_mile": 410.5, "lat": 40.8681, "lon": -91.0506, "phone": "319-524-2933"},
    "lock_19": {"name": "Lock & Dam #19 (Keokuk)", "river_mile": 364.2, "lat": 40.3883, "lon": -91.3750, "phone": "319-524-2933"},
    "lock_20": {"name": "Lock & Dam #20 (Canton)", "river_mile": 343.2, "lat": 40.1411, "lon": -91.5153, "phone": "573-853-4213"},
    "lock_21": {"name": "Lock & Dam #21 (Quincy)", "river_mile": 324.9, "lat": 39.9131, "lon": -91.4097, "phone": "217-228-0890"},
    "lock_22": {"name": "Lock & Dam #22 (Saverton)", "river_mile": 301.2, "lat": 39.6428, "lon": -91.2461, "phone": "573-754-4451"},
    "lock_24": {"name": "Lock & Dam #24 (Clarksville)", "river_mile": 273.4, "lat": 39.3706, "lon": -90.9042, "phone": "573-242-3564"},
    "lock_25": {"name": "Lock & Dam #25 (Cap au Gris)", "river_mile": 241.4, "lat": 39.0044, "lon": -90.8536, "phone": "636-899-2301"},
    "melvin_price": {"name": "Melvin Price Lock & Dam (Alton)", "river_mile": 200.8, "lat": 38.8697, "lon": -90.1492, "phone": "618-462-6979"},
    "chain_of_rocks": {"name": "Chain of Rocks Lock (Granite City)", "river_mile": 185.0, "lat": 38.7542, "lon": -90.1711, "phone": "314-355-6100"},
}

# Upper Mississippi lock numbers for USACE API
UPPER_MISS_LOCKS = [
    "1", "2", "3", "4", "5", "5A", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "24", "25", "27"  # Note: no 23, 26
]

# River mile reference points for estimation
RIVER_MILE_POINTS = [
    (44.9778, -93.2650, 847.6),   # L1 - Minneapolis
    (44.7319, -92.8500, 815.2),   # L2 - Hastings
    (44.5620, -92.5340, 796.9),   # L3 - Red Wing
    (44.3240, -91.9150, 752.8),   # L4 - Alma
    (44.0510, -91.6390, 738.1),   # L5 - Minnesota City
    (43.9560, -91.5850, 728.5),   # L5A - Fountain City
    (43.8500, -91.4390, 714.1),   # L6 - Trempealeau
    (43.7600, -91.2890, 702.5),   # L7 - Dresbach
    (43.5660, -91.2290, 679.2),   # L8 - Genoa
    (43.1920, -91.0720, 647.9),   # L9 - Lynxville
    (42.7860, -91.0990, 615.1),   # L10 - Guttenberg
    (42.4900, -90.6650, 583.0),   # L11 - Dubuque
    (42.2590, -90.4230, 556.7),   # L12 - Bellevue
    (41.8690, -90.1590, 522.5),   # L13 - Fulton
    (41.5980, -90.4430, 493.3),   # L14 - Le Claire
    (41.5130, -90.5780, 482.9),   # L15 - Rock Island
    (41.4240, -91.0430, 457.2),   # L16 - Muscatine
    (41.2610, -91.0060, 437.1),   # L17 - New Boston
    (40.9640, -91.0680, 410.5),   # L18 - Gladstone
    (40.3960, -91.3750, 364.3),   # L19 - Keokuk
    (40.1540, -91.5140, 343.2),   # L20 - Canton
    (39.9290, -91.4090, 324.9),   # L21 - Quincy
    (39.6340, -91.2340, 301.2),   # L22 - Saverton
    (39.3770, -90.9110, 273.4),   # L24 - Clarksville
    (39.0050, -90.8180, 241.4),   # L25 - Cap au Gris
    (38.7080, -90.1510, 185.0),   # L27 - Chain of Rocks
]
