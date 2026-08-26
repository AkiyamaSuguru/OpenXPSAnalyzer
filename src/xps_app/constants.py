"""Shared column names and schema settings."""

BE_COL = "Binding Energy (eV)"
INTENSITY_COL = "Intensity"
FIT_COL = "Fitting Curve"
BG_COL = "Background"

STANDARD_COLUMNS = (BE_COL, INTENSITY_COL, FIT_COL, BG_COL)
RAW_REQUIRED_COLUMNS = (BE_COL, INTENSITY_COL)
FIT_REQUIRED_COLUMNS = STANDARD_COLUMNS

SCHEMA_NAME = "xps-analyzer-project"
SCHEMA_VERSION = "1.0"
DEFAULT_FONT_FAMILY = "sans-serif"
DEFAULT_FONT_SIZE = 10
