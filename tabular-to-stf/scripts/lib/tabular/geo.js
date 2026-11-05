/**
 * Port of study-wrangler v1.0.54's two latitude/longitude name matchers, plus
 * the geo constants. The two rules differ and both are needed:
 *
 * - inference (`infer_geo_variables_for_eda`): `(\b|_)token(\b|_)` on the
 *   variable name, so `wgs84_lat` is a latitude.
 * - validator (`validate_geocoordinate_variables`): `\btoken\b` on the variable
 *   name and each provider_label, so `_` is not a boundary.
 *
 * Both are case-insensitive. JS and TRE agree on `\b` and `_` for ASCII; for
 * non-ASCII letters JS `\b` treats them as non-word, which may differ from R.
 */

const LAT_TOKENS = ['latitude', 'lat'];
const LNG_TOKENS = ['longitude', 'long', 'lng'];

const anyMatch = (tokens, make, text) =>
  tokens.some((t) => new RegExp(make(t), 'i').test(text));

const inference = (t) => `(\\b|_)${t}(\\b|_)`;
const validator = (t) => `\\b${t}\\b`;

export const isLatitudeName = (name) => anyMatch(LAT_TOKENS, inference, String(name));
export const isLongitudeName = (name) => anyMatch(LNG_TOKENS, inference, String(name));
export const validatorSeesLatitude = (text) => anyMatch(LAT_TOKENS, validator, String(text));
export const validatorSeesLongitude = (text) => anyMatch(LNG_TOKENS, validator, String(text));

export const GEO = Object.freeze({
  latitude: Object.freeze({ stableId: 'OBI_0001620', dataType: 'number', displayType: 'latitude' }),
  longitude: Object.freeze({ stableId: 'OBI_0001621', dataType: 'longitude', displayType: 'longitude' }),
  geohashColumns: Object.freeze([1, 2, 3, 4, 5, 6].map((i) => `geohash_${i}`)),
});
