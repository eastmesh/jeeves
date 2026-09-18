from __future__ import annotations

from meshcore_pathbot.core.bot import PathBot


def test_extract_advert_pub_key_from_string_payload() -> None:
    assert PathBot._extract_advert_pub_key("abcd1234") == "abcd1234"


def test_extract_advert_pub_key_from_dict_payload() -> None:
    assert PathBot._extract_advert_pub_key({"public_key": "abcd1234"}) == "abcd1234"
    assert PathBot._extract_advert_pub_key({"pub_key": "abcd1234"}) == "abcd1234"


def test_extract_advert_pub_key_rejects_unsupported_payload() -> None:
    assert PathBot._extract_advert_pub_key({"other": "x"}) is None
    assert PathBot._extract_advert_pub_key(["abcd1234"]) is None
