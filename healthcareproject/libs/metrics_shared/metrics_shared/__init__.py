from metrics_shared.collectors import register_gauge_collector, register_labeled_gauge_collector
from metrics_shared.config import instrument_metrics

__all__ = ["instrument_metrics", "register_gauge_collector", "register_labeled_gauge_collector"]
