import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isLatitudeName, isLongitudeName, validatorSeesLatitude, validatorSeesLongitude, GEO,
} from '../scripts/lib/tabular/geo.js';

const MATCHED_LAT = ['lat-dd', 'wgs84_lat', 'sample_lat_value', 'latitude-wgs84'];
const MATCHED_LNG = ['lng_dd', 'long-dd', 'sample_long', 'longitude_wgs84'];
const NOT_MATCHED = ['lat1', 'lng2', 'platform', 'flat', 'slat', 'belongs', 'elongated', 'latlong'];

test('inference rule: matched examples from infer_geo_variables_for_eda', () => {
  for (const n of MATCHED_LAT) assert.equal(isLatitudeName(n), true, n);
  for (const n of MATCHED_LNG) assert.equal(isLongitudeName(n), true, n);
  assert.equal(isLatitudeName('Latitude'), true);
  assert.equal(isLongitudeName('LNG'), true);
});

test('inference rule: not-matched examples', () => {
  for (const n of NOT_MATCHED) {
    assert.equal(isLatitudeName(n), false, n);
    assert.equal(isLongitudeName(n), false, n);
  }
});

test('validator rule: underscore is not a boundary', () => {
  for (const n of ['wgs84_lat', 'sample_lat_value']) assert.equal(validatorSeesLatitude(n), false, n);
  for (const n of ['lng_dd', 'sample_long']) assert.equal(validatorSeesLongitude(n), false, n);
});

test('validator rule: seen examples', () => {
  assert.equal(validatorSeesLatitude('Latitude'), true);
  assert.equal(validatorSeesLatitude('lat-dd'), true);
  assert.equal(validatorSeesLongitude('Long-term illness'), true);
  assert.equal(validatorSeesLatitude('Long-term illness'), false);
});

test('validator rule: non-matching examples are not seen', () => {
  for (const n of NOT_MATCHED) {
    assert.equal(validatorSeesLatitude(n), false, n);
    assert.equal(validatorSeesLongitude(n), false, n);
  }
});

test('GEO constants', () => {
  assert.deepEqual(GEO.latitude, { stableId: 'OBI_0001620', dataType: 'number', displayType: 'latitude' });
  assert.deepEqual(GEO.longitude, { stableId: 'OBI_0001621', dataType: 'longitude', displayType: 'longitude' });
  assert.deepEqual(GEO.geohashColumns, ['geohash_1', 'geohash_2', 'geohash_3', 'geohash_4', 'geohash_5', 'geohash_6']);
});
