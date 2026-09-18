from __future__ import annotations

from meshcore_pathbot.core.bot import parse_rx_log_data


def test_parse_rx_log_data_compacts_three_byte_hashes_from_raw_payload() -> None:
    # header=0x15 (route_type=FLOOD, payload_type=GRP_TXT, ver=0; no transport code),
    # path byte=0x83 => hash size=3 bytes, path_len=3
    parsed = parse_rx_log_data("1583a1b2c3d4e5f6070809")

    assert parsed["route_type"] == 0x01
    assert parsed["path_hash_size"] == 3
    assert parsed["path_len"] == 3
    assert parsed["path"] == "a1d407"
    assert parsed["full_path"] == "a1b2c3d4e5f6070809"


def test_parse_rx_log_data_uses_dict_payload_fields_when_available() -> None:
    parsed = parse_rx_log_data(
        {
            "path_len": 3,
            "path_hash_size": 2,
            "path": "a1b2c3d4e5f6",
        }
    )

    assert parsed["path_hash_size"] == 2
    assert parsed["path_len"] == 3
    assert parsed["path"] == "a1c3e5"
    assert parsed["full_path"] == "a1b2c3d4e5f6"


def test_parse_rx_log_data_skips_transport_code_on_region_scoped_packet() -> None:
    # header=0x14 (route_type=TRANSPORT_FLOOD), 4 transport_code bytes, then
    # path byte=0x02 (hash_size=1, path_len=2), then path "ab cd", then payload.
    parsed = parse_rx_log_data("14deadbeef02abcd99")

    assert parsed["route_type"] == 0x00
    assert parsed["transport_code"] == "deadbeef"
    assert parsed["path_hash_size"] == 1
    assert parsed["path_len"] == 2
    assert parsed["path"] == "abcd"
    assert parsed["full_path"] == "abcd"


def test_parse_rx_log_data_propagates_dict_route_type_and_transport_code() -> None:
    parsed = parse_rx_log_data(
        {
            "path_len": 1,
            "path_hash_size": 1,
            "path": "ab",
            "route_type": 0x00,
            "transport_code": "DEADBEEF",
        }
    )

    assert parsed["route_type"] == 0x00
    assert parsed["transport_code"] == "deadbeef"
    assert parsed["path"] == "ab"
