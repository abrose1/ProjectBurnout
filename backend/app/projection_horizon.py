"""
Projection horizon shared by ``projection.py`` and ``aeo_refresh.py``.

EIA Annual Energy Outlook reference-case series are published through **2050**. Years beyond
that reuse the last AEO year (forward-fill) so the stranded-year loop can run to
``PROJECTION_END_YEAR`` without missing fuel/wholesale/renewable inputs.
"""

PROJECTION_START_YEAR = 2025
PROJECTION_END_YEAR = 2060
AEO_DATA_LAST_YEAR = 2050
