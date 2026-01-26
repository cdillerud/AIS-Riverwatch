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

# Lock definitions for Upper Mississippi River
LOCKS = {
    "L1": {"name": "Lock & Dam #1", "river_mile": 847.6, "location": "Minneapolis"},
    "L2": {"name": "Lock & Dam #2 (Hastings)", "river_mile": 815.2, "location": "Hastings"},
    "L3": {"name": "Lock & Dam #3", "river_mile": 796.9, "location": "Red Wing"},
    "L4": {"name": "Lock & Dam #4", "river_mile": 752.8, "location": "Alma"},
    "L5": {"name": "Lock & Dam #5", "river_mile": 738.1, "location": "Minnesota City"},
    "L5A": {"name": "Lock & Dam #5A", "river_mile": 728.5, "location": "Fountain City"},
    "L6": {"name": "Lock & Dam #6", "river_mile": 714.1, "location": "Trempealeau"},
    "L7": {"name": "Lock & Dam #7", "river_mile": 702.5, "location": "Dresbach"},
    "L8": {"name": "Lock & Dam #8", "river_mile": 679.2, "location": "Genoa"},
    "L9": {"name": "Lock & Dam #9", "river_mile": 647.9, "location": "Lynxville"},
    "L10": {"name": "Lock & Dam #10", "river_mile": 615.1, "location": "Guttenberg"},
    "L11": {"name": "Lock & Dam #11", "river_mile": 583.0, "location": "Dubuque"},
    "L12": {"name": "Lock & Dam #12", "river_mile": 556.7, "location": "Bellevue"},
    "L13": {"name": "Lock & Dam #13", "river_mile": 522.5, "location": "Fulton"},
    "L14": {"name": "Lock & Dam #14", "river_mile": 493.3, "location": "Le Claire"},
    "L15": {"name": "Lock & Dam #15", "river_mile": 482.9, "location": "Rock Island"},
    "L16": {"name": "Lock & Dam #16", "river_mile": 457.2, "location": "Muscatine"},
    "L17": {"name": "Lock & Dam #17", "river_mile": 437.1, "location": "New Boston"},
    "L18": {"name": "Lock & Dam #18", "river_mile": 410.5, "location": "Gladstone"},
    "L19": {"name": "Lock & Dam #19", "river_mile": 364.3, "location": "Keokuk"},
    "L20": {"name": "Lock & Dam #20", "river_mile": 343.2, "location": "Canton"},
    "L21": {"name": "Lock & Dam #21", "river_mile": 324.9, "location": "Quincy"},
    "L22": {"name": "Lock & Dam #22", "river_mile": 301.2, "location": "Saverton"},
    "L24": {"name": "Lock & Dam #24", "river_mile": 273.4, "location": "Clarksville"},
    "L25": {"name": "Lock & Dam #25", "river_mile": 241.4, "location": "Cap au Gris"},
    "L27": {"name": "Lock & Dam #27 (Chain of Rocks)", "river_mile": 185.0, "location": "Granite City"},
}

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
