import asyncio

from services import db_indexes


class FakeColl:
    def __init__(self, docs):
        self.docs = docs
        self.indexes = []

    def aggregate(self, pipeline):
        field = pipeline[0]["$group"]["_id"][1:]
        tkey = pipeline[0]["$group"]["ids"]["$push"]["t"][1:]
        groups = {}
        for d in self.docs:
            groups.setdefault(d.get(field), []).append({"id": d["_id"], "t": d.get(tkey)})

        async def gen():
            for k, ids in groups.items():
                if k is not None and len(ids) > 1:
                    yield {"_id": k, "ids": ids, "n": len(ids)}
        return gen()

    async def delete_many(self, q):
        ids = set(q["_id"]["$in"])
        before = len(self.docs)
        self.docs = [d for d in self.docs if d["_id"] not in ids]

        class R:
            deleted_count = before - len(self.docs)
        return R()

    async def create_index(self, keys, **opts):
        self.indexes.append((keys, opts))


class FakeDB(dict):
    def __missing__(self, k):
        self[k] = FakeColl([])
        return self[k]


def test_unique_index_keeps_newest_duplicate():
    db = FakeDB()
    db["vessel_sightings"] = FakeColl([
        {"_id": 1, "mmsi": "367000001", "timestamp": "2026-11-09T10:00"},
        {"_id": 2, "mmsi": "367000001", "timestamp": "2026-11-10T10:00"},
        {"_id": 3, "mmsi": "367000002", "timestamp": "2026-11-10T10:00"},
    ])
    out = asyncio.run(db_indexes.ensure_indexes(db))
    assert out["errors"] == [] and out["deduplicated"] == 1
    assert sorted(d["_id"] for d in db["vessel_sightings"].docs) == [2, 3]
    assert out["created"] == len(db_indexes.INDEXES)


def test_one_failing_index_does_not_stop_the_rest():
    class Broken(FakeColl):
        async def create_index(self, keys, **opts):
            raise RuntimeError("boom")
    db = FakeDB()
    db["users"] = Broken([])
    out = asyncio.run(db_indexes.ensure_indexes(db))
    n_users = sum(1 for c, _, _ in db_indexes.INDEXES if c == "users")
    assert len(out["errors"]) == n_users and out["created"] == len(db_indexes.INDEXES) - n_users
