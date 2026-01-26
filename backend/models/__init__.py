# River Watch Backend - Models Package
from models.auth import UserRegistration, UserLogin, VesselAdd, User
from models.vessel import VesselPosition, ConnectionConfig
from models.lock import LockInfo, LockStatus, LockageRecord, RaceAnalysis

__all__ = [
    'UserRegistration', 'UserLogin', 'VesselAdd', 'User',
    'VesselPosition', 'ConnectionConfig',
    'LockInfo', 'LockStatus', 'LockageRecord', 'RaceAnalysis'
]
