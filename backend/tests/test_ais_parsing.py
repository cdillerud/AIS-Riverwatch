"""AIS parsing: multi-sentence reassembly, sentinels, static-name persistence path."""
import pytest

from services.ais_parser import NmeaFragmentAssembler, clean_sog, clean_cog

TYPE5_A = "!AIVDM,2,1,1,A,55?MbV02;H;s<HtKR20EHE:0@T4@Dn2222222216L961O5Gf0NSQEp6ClRp8,0*1C"
TYPE5_B = "!AIVDM,2,2,1,A,88888888880,2*25"
POS_A = "!AIVDM,1,1,,A,15RTgt0PAso;90TKcjM8h6g208CQ,0*4A"


def test_assembler_single_sentence_passthrough():
    asm = NmeaFragmentAssembler()
    assert asm.feed(POS_A) == [POS_A]


def test_assembler_waits_for_all_fragments():
    asm = NmeaFragmentAssembler()
    assert asm.feed(TYPE5_A) is None
    assert asm.feed(TYPE5_B) == [TYPE5_A, TYPE5_B]


def test_assembler_drops_orphan_continuation_and_ignores_noise():
    asm = NmeaFragmentAssembler()
    assert asm.feed(TYPE5_B) is None
    assert asm.feed("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A") is None
    assert asm.feed("garbage") is None


def test_assembler_expires_stale_fragments(monkeypatch):
    # Drive the clock directly: Windows' monotonic() ticks every ~15 ms, so a
    # short real sleep can measure as zero elapsed time.
    from services import ais_parser
    now = [1000.0]
    monkeypatch.setattr(ais_parser._time, "monotonic", lambda: now[0])
    asm = NmeaFragmentAssembler(timeout_s=5)
    assert asm.feed(TYPE5_A) is None
    now[0] += 6
    assert asm.feed(TYPE5_B) is None  # first half expired


def test_sentinels():
    assert clean_sog(102.3) == 0.0
    assert clean_sog(None) == 0.0
    assert clean_sog(7.5) == 7.5
    assert clean_cog(360) is None
    assert clean_cog(359.9) == 359.9
    assert clean_cog(None) is None


def test_server_parser_decodes_type5_name():
    import server
    assert server.parse_nmea_ais(TYPE5_A) is None
    out = server.parse_nmea_ais(TYPE5_B)
    assert out is not None and out["_static_only"] and out["_persist_to_db"]
    assert out["mmsi"] == "351759000"
    assert out["name"] == "EVER DIADEM"
    assert server.vessel_static_cache["351759000"]["name"] == "EVER DIADEM"


def test_server_parser_position_report_sentinels(monkeypatch):
    import asyncio
    import server

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(server, "persist_vessel_sighting", _noop)

    async def run():
        return server.parse_nmea_ais(POS_A)
    out = asyncio.run(run())
    assert out is not None and out.get("lat") is not None
    assert 0 <= out["speed"] < 102.2
    assert out["course_valid"] is True
