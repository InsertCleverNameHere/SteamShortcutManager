from hypothesis import given
from hypothesis import strategies as st

from core.appid import (
    generate_shortcut_appid,
    normalize_appid,
    to_int32,
    to_uint32,
)


@given(st.integers(min_value=0, max_value=0xFFFFFFFF))
def test_uint32_int32_roundtrip(val: int):
    """Property test: converting uint32 -> int32 -> uint32 must preserve the value."""
    signed = to_int32(val)
    unsigned = to_uint32(signed)
    assert unsigned == val


def test_real_steam_bazzite_fixture_value():
    """Verify against our real Bazzite fixture's known signed and unsigned pair."""
    # From golden_bazzite_single.vdf:
    # appid: int32 (0x02) -> signed -458462630 | unsigned 3836504666
    unsigned = 3836504666
    signed = -458462630

    assert to_int32(unsigned) == signed
    assert to_uint32(signed) == unsigned
    assert normalize_appid(signed) == str(unsigned)
    assert normalize_appid(unsigned) == str(unsigned)
    assert normalize_appid(str(signed)) == str(unsigned)


def test_generate_shortcut_appid_high_bit_set():
    """Shortcut AppIDs must always have the top bit set (>= 0x80000000)."""
    appid = generate_shortcut_appid("/usr/bin/game", "My Game")
    assert appid >= 0x80000000
    assert appid <= 0xFFFFFFFF


def test_generate_shortcut_appid_quotes_handling():
    """Quoting the exe path explicitly or leaving it unquoted must yield the same AppID."""
    id1 = generate_shortcut_appid("/usr/bin/game", "My Game")
    id2 = generate_shortcut_appid('"/usr/bin/game"', "My Game")
    assert id1 == id2


def test_normalize_appid_edge_cases():
    assert normalize_appid(None) == "0"
    assert normalize_appid("0") == "0"
    assert normalize_appid("invalid") == "invalid"
