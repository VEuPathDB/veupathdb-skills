"""Port of study-wrangler v1.0.56's two latitude/longitude name matchers, plus the geo constants.

- inference (`infer_geo_variables_for_eda`): `(\\b|_)token(\\b|_)` on the variable name.
- validator (`validate_geocoordinate_variables`): `\\btoken\\b` on the name and each provider_label.

Both are case-insensitive. re.ASCII keeps `\\b` ASCII-only, as in JS.
"""

import re

_FLAGS = re.IGNORECASE | re.ASCII
_LAT_TOKENS = ("latitude", "lat")
_LNG_TOKENS = ("longitude", "long", "lng")


def _any_match(tokens, make, text) -> bool:
    return any(re.search(make(t), str(text), _FLAGS) for t in tokens)


def _inference(t: str) -> str:
    return rf"(\b|_){t}(\b|_)"


def _validator(t: str) -> str:
    return rf"\b{t}\b"


def is_latitude_name(name: str) -> bool:
    return _any_match(_LAT_TOKENS, _inference, name)


def is_longitude_name(name: str) -> bool:
    return _any_match(_LNG_TOKENS, _inference, name)


def validator_sees_latitude(text: str) -> bool:
    return _any_match(_LAT_TOKENS, _validator, text)


def validator_sees_longitude(text: str) -> bool:
    return _any_match(_LNG_TOKENS, _validator, text)


GEO = {
    "latitude": {"stable_id": "OBI_0001620", "data_type": "number", "display_type": "latitude"},
    "longitude": {"stable_id": "OBI_0001621", "data_type": "longitude", "display_type": "longitude"},
    "geohash_columns": tuple(f"geohash_{i}" for i in range(1, 7)),
}
