"""Value sets the STF entity files accept, plus shared constants."""

DATA_TYPES = ("string", "number", "integer", "date", "longitude")
DATA_SHAPES = ("continuous", "categorical", "ordinal", "binary")
DISPLAY_TYPES = ("default", "multifilter", "geoaggregator", "latitude", "longitude")
HIDDEN = ("download", "variableTree", "map", "everywhere")

PLACEHOLDERS = ("NA", "N/A", "n/a", "na", "-", "--", ".", "null", "NULL", "none", "None", "unknown", "Unknown", "not done")
UNAMBIGUOUS_PLACEHOLDERS = ("NA", "N/A", "n/a", "na", "-", "--", ".", "null", "NULL")

MAX_VALUE_LENGTH = 80
SAVED_SPEC = "curation-spec.json"
RAW_DIR = "raw-data"
