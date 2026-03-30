"""Which plants are exposed via the API: require Form 923 facility-fuel data in ``plant_metrics``."""

from __future__ import annotations

from sqlalchemy import ColumnElement, exists
from sqlalchemy.sql.selectable import Exists

from app.models.schemas import PlantMetric


def plant_has_923_metrics(plant_id_column: ColumnElement) -> Exists:
    """Correlate with a query that defines ``plant_id_column`` (e.g. ``Plant.plant_id``)."""
    return exists().where(PlantMetric.plant_id == plant_id_column)
