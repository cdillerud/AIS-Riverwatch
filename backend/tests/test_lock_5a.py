import importlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
server = importlib.import_module("server")
from config import UPPER_MISS_LOCKS


def test_lock_5a_uses_usace_code_55():
    assert "55" in UPPER_MISS_LOCKS and "05A" not in UPPER_MISS_LOCKS
    assert server.usace_lock_id("55") == "lock_5a"
    assert server.usace_lock_id("05") == "lock_5"
    assert "lock_5a" not in server.USACE_NO_DATA_LOCKS
