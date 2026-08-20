from types import SimpleNamespace

from utils.parse_watch import (
    _node_snapshot,
    _detect_node_change,
    format_node_watch,
    _pod_snapshot,
    _detect_pod_change,
    format_pod_watch,
)


# ---------------- Node ----------------

def _mk_condition(type_, status):
    return SimpleNamespace(type=type_, status=status)


def _mk_node(name, ready="True", unschedulable=False):
    conds = [
        _mk_condition("Ready", ready),
        _mk_condition("MemoryPressure", "False"),
        _mk_condition("DiskPressure", "False"),
        _mk_condition("PIDPressure", "False"),
    ]
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(conditions=conds),
        spec=SimpleNamespace(unschedulable=unschedulable),
    )


def test_node_snapshot():
    snap = _node_snapshot(_mk_node("n1"))
    assert snap["ready"] == "True"
    assert snap["unschedulable"] is False


def test_detect_node_change_ready_transition():
    old = _node_snapshot(_mk_node("n1", ready="True"))
    new = _node_snapshot(_mk_node("n1", ready="False"))
    changes = _detect_node_change(old, new)
    assert any("Ready" in c for c in changes)


def test_detect_node_change_no_change():
    snap = _node_snapshot(_mk_node("n1"))
    assert _detect_node_change(snap, _node_snapshot(_mk_node("n1"))) == []


def test_format_node_watch_modified_skips_when_no_change():
    node = _mk_node("n1")
    snap = _node_snapshot(node)
    assert format_node_watch("MODIFIED", node, snap) is None


def test_format_node_watch_added():
    out = format_node_watch("ADDED", _mk_node("n1"))
    assert "n1" in out


# ---------------- Pod ----------------

def _mk_container_state(reason=None):
    if reason is None:
        return SimpleNamespace(waiting=None, terminated=None, running=SimpleNamespace(started_at=None))
    return SimpleNamespace(
        waiting=SimpleNamespace(reason=reason, message=""),
        terminated=None,
        running=None,
    )


def _mk_pod(ns, name, phase="Running", node="worker-1", restarts=0, state_reason=None):
    cs = SimpleNamespace(
        name="app",
        ready=True,
        restart_count=restarts,
        state=_mk_container_state(state_reason),
    )
    return SimpleNamespace(
        metadata=SimpleNamespace(namespace=ns, name=name),
        spec=SimpleNamespace(node_name=node),
        status=SimpleNamespace(phase=phase, container_statuses=[cs]),
    )


def test_pod_snapshot():
    snap = _pod_snapshot(_mk_pod("ns", "p"))
    assert snap["phase"] == "Running"
    assert snap["container_states"]["app"] == "Running"


def test_detect_pod_change_restart_increase():
    old = _pod_snapshot(_mk_pod("ns", "p", restarts=0))
    new = _pod_snapshot(_mk_pod("ns", "p", restarts=1))
    changes = _detect_pod_change(old, new)
    assert any("重启" in c for c in changes)


def test_detect_pod_change_phase_transition():
    old = _pod_snapshot(_mk_pod("ns", "p", phase="Pending"))
    new = _pod_snapshot(_mk_pod("ns", "p", phase="Running"))
    changes = _detect_pod_change(old, new)
    assert any("Phase" in c for c in changes)


def test_format_pod_watch_crashloop_shows_state():
    pod = _mk_pod("ns", "p", state_reason="CrashLoopBackOff")
    out = format_pod_watch("ADDED", pod)
    assert "CrashLoopBackOff" in out
