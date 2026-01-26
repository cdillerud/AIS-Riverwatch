# River Watch Backend - Database Connection
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

# MongoDB connection
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Collection references
user_accounts = db.user_accounts
sessions = db.sessions
vessel_settings = db.vessel_settings
blocked_mmsi = db.blocked_mmsi
lockage_history = db.lockage_history
