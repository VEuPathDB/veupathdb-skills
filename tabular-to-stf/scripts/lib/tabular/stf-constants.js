/**
 * Value sets the STF entity files accept for variable metadata. Shared by the
 * spec validator and the renderer.
 */

export const STF_CONSTANTS = Object.freeze({
  DATA_TYPES: Object.freeze(['string', 'number', 'integer', 'date', 'longitude']),
  DATA_SHAPES: Object.freeze(['continuous', 'categorical', 'ordinal', 'binary']),
  DISPLAY_TYPES: Object.freeze(['default', 'multifilter', 'geoaggregator', 'latitude', 'longitude']),
  HIDDEN: Object.freeze(['download', 'variableTree', 'map', 'everywhere']),
});
