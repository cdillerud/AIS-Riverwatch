from services import user_settings as U

ADMIN = {"user_id": "u_admin", "is_admin": True}
SUPER = {"user_id": "u_super", "is_super_admin": True}
ALICE = {"user_id": "u_alice"}


def test_non_admin_never_sees_admins_boat_or_feed():
    g = {"user_mmsi": "338414076", "boat_name": "REBOOT", "last_ip": "192.168.1.104",
         "last_port": "5353", "default_lock": "lock_2", "max_speed_mph": "25",
         "last_connection_config": '{"ip_address": "192.168.1.104", "port": 5353}'}
    assert U.visible_global_settings(g, ALICE) == {"default_lock": "lock_2", "max_speed_mph": "25"}
    assert U.visible_global_settings(g, ADMIN) == g
    assert U.visible_global_settings(g, SUPER) == g


def test_per_boat_settings_are_scoped_to_the_account():
    assert U.read_filter("366000001", ALICE) == {"mmsi": "366000001", "user_id": "u_alice"}
    assert U.write_filter("366000001", ALICE) == {"mmsi": "366000001", "user_id": "u_alice"}


def test_admin_can_read_and_adopt_legacy_unowned_docs():
    f = U.read_filter("338414076", ADMIN)
    assert f["mmsi"] == "338414076"
    assert {"user_id": "u_admin"} in f["$or"] and {"user_id": {"$exists": False}} in f["$or"]
    assert U.write_filter("338414076", ADMIN) == f
