import datetime
from types import SimpleNamespace

from utils.parse_event import (
    _event_key,
    _deduplicate_events,
    _sort_events_by_time,
)

UTC = datetime.timezone.utc


def _mk_event(ns, kind, name, reason, msg, ts):
    return SimpleNamespace(
        involved_object=SimpleNamespace(kind=kind, name=name),
        metadata=SimpleNamespace(namespace=ns),
        reason=reason,
        message=msg,
        type="Warning",
        last_timestamp=ts,
        event_time=None,
    )


def test_event_key_includes_namespace():
    key = _event_key(_mk_event("ns1", "Pod", "p", "R", "m", None))
    assert key == ("ns1", "Pod", "p", "R", "m")


def test_dedup_keeps_latest():
    t1 = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime.datetime(2026, 1, 2, tzinfo=UTC)
    e1 = _mk_event("ns1", "Pod", "p", "R", "m", t1)
    e2 = _mk_event("ns1", "Pod", "p", "R", "m", t2)
    result = _deduplicate_events([e1, e2])
    assert len(result) == 1
    assert result[0].last_timestamp == t2


def test_dedup_does_not_merge_across_namespace():
    t = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    e1 = _mk_event("ns1", "Pod", "p", "R", "m", t)
    e2 = _mk_event("ns2", "Pod", "p", "R", "m", t)
    result = _deduplicate_events([e1, e2])
    assert len(result) == 2


def test_dedup_dict_events():
    e1 = {
        "involvedObject": {"kind": "Pod", "name": "p"},
        "metadata": {"namespace": "ns1"},
        "reason": "R",
        "message": "m",
        "lastTimestamp": "2026-01-01T00:00:00Z",
    }
    e2 = {
        "involvedObject": {"kind": "Pod", "name": "p"},
        "metadata": {"namespace": "ns1"},
        "reason": "R",
        "message": "m",
        "lastTimestamp": "2026-01-02T00:00:00Z",
    }
    result = _deduplicate_events([e1, e2])
    assert len(result) == 1


def test_sort_desc():
    t1 = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime.datetime(2026, 1, 2, tzinfo=UTC)
    e1 = _mk_event("ns1", "Pod", "a", "R", "m", t1)
    e2 = _mk_event("ns1", "Pod", "b", "R", "m", t2)
    sorted_ = _sort_events_by_time([e1, e2])
    assert sorted_[0].last_timestamp == t2
