from _geo import (
    GEO, is_latitude_name, is_longitude_name, validator_sees_latitude, validator_sees_longitude,
)
from _common import to_column_name

MATCHED_LAT = ["lat-dd", "wgs84_lat", "sample_lat_value", "latitude-wgs84"]
MATCHED_LNG = ["lng_dd", "long-dd", "sample_long", "longitude_wgs84"]
NOT_MATCHED = ["lat1", "lng2", "platform", "flat", "slat", "belongs", "elongated", "latlong"]


def test_inference_rule_matched_examples():
    for n in MATCHED_LAT:
        assert is_latitude_name(n), n
    for n in MATCHED_LNG:
        assert is_longitude_name(n), n
    assert is_latitude_name("Latitude")
    assert is_longitude_name("LNG")


def test_inference_rule_not_matched_examples():
    for n in NOT_MATCHED:
        assert not is_latitude_name(n), n
        assert not is_longitude_name(n), n


def test_validator_rule_underscore_is_not_a_boundary():
    for n in ["wgs84_lat", "sample_lat_value"]:
        assert not validator_sees_latitude(n), n
    for n in ["lng_dd", "sample_long"]:
        assert not validator_sees_longitude(n), n


def test_validator_rule_seen_examples():
    assert validator_sees_latitude("Latitude")
    assert validator_sees_latitude("lat-dd")
    assert validator_sees_longitude("Long-term illness")
    assert not validator_sees_latitude("Long-term illness")


def test_validator_rule_non_matching_examples_are_not_seen():
    for n in NOT_MATCHED:
        assert not validator_sees_latitude(n), n
        assert not validator_sees_longitude(n), n


def test_geo_constants():
    assert GEO["latitude"] == {"stable_id": "OBI_0001620", "data_type": "number", "display_type": "latitude"}
    assert GEO["longitude"] == {"stable_id": "OBI_0001621", "data_type": "longitude", "display_type": "longitude"}
    assert GEO["geohash_columns"] == ("geohash_1", "geohash_2", "geohash_3", "geohash_4", "geohash_5", "geohash_6")


def test_geo_word_boundaries_are_ascii_like_js():
    # JS \b treats non-ASCII letters as non-word characters
    assert is_latitude_name("élat")
    assert validator_sees_latitude("élat")   # False under Unicode \b
    assert to_column_name("Âge (années)") == "ge_ann_es"
