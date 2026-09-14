from __future__ import annotations

import logging
from collections.abc import Callable

from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

logger = logging.getLogger(__name__)


class _CallbackGaugeCollector(Collector):
    """Generic PULL-based collector — the callback runs fresh on every
    Prometheus scrape, not on some separate push schedule. Used for
    domain-specific gauges (outbox lag, the booking funnel, audit chain
    status) that don't fit the generic HTTP-level metrics
    instrument_metrics() already provides.

    prometheus_client calls collect() once immediately at
    REGISTRY.register() time (to collision-check metric names) — before
    the app has served a single request, possibly before migrations have
    even run against a fresh DB. Same risk on every real scrape too (a DB
    blip shouldn't 500 the whole /metrics endpoint for every collector).
    So compute() failures are caught and logged rather than propagated —
    the gauge is just absent from that one scrape."""

    def __init__(self, compute: Callable[[], dict[str, tuple[str, float]]]) -> None:
        self._compute = compute

    def collect(self):
        try:
            values = self._compute()
        except Exception:
            logger.warning("gauge collector compute() failed", exc_info=True)
            return
        for name, (help_text, value) in values.items():
            gauge = GaugeMetricFamily(name, help_text)
            gauge.add_metric([], value)
            yield gauge


def register_gauge_collector(compute: Callable[[], dict[str, tuple[str, float]]]) -> None:
    """`compute` returns {metric_name: (help_text, value)} — called once
    per scrape. Keep it cheap (a single query or two), or cache internally
    with your own TTL if the real computation is expensive (see audit's
    chain-verification gauge, which re-verifies at most once a minute
    regardless of how often Prometheus scrapes)."""
    REGISTRY.register(_CallbackGaugeCollector(compute))


class _CallbackLabeledGaugeCollector(Collector):
    """Same pull-on-scrape shape as _CallbackGaugeCollector, but for a
    single gauge broken down by a label (e.g. one appointment count per
    status) instead of one gauge per Python-level name — a real
    Prometheus label, not a name suffix, so `sum by (status) (...)` works
    in Grafana."""

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: list[str],
        compute_rows: Callable[[], list[tuple[list[str], float]]],
    ) -> None:
        self._name = name
        self._help_text = help_text
        self._label_names = label_names
        self._compute_rows = compute_rows

    def collect(self):
        try:
            rows = self._compute_rows()
        except Exception:
            logger.warning("labeled gauge collector compute_rows() failed", exc_info=True)
            return
        gauge = GaugeMetricFamily(self._name, self._help_text, labels=self._label_names)
        for label_values, value in rows:
            gauge.add_metric(label_values, value)
        yield gauge


def register_labeled_gauge_collector(
    name: str,
    help_text: str,
    label_names: list[str],
    compute_rows: Callable[[], list[tuple[list[str], float]]],
) -> None:
    """`compute_rows` returns [(label_values, value), ...] where
    label_values lines up positionally with `label_names` — called once
    per scrape. Use this over register_gauge_collector whenever the
    breakdown is a real dimension (status, consumer group) rather than a
    fixed, known-in-advance set of independent gauges."""
    REGISTRY.register(_CallbackLabeledGaugeCollector(name, help_text, label_names, compute_rows))
