from utils.parse_resource import _parse_cpu, _parse_memory, _assess_node_resource


def test_parse_cpu_millicores():
    assert _parse_cpu("500m") == 500
    assert _parse_cpu("2") == 2000
    assert _parse_cpu("0.5") == 500


def test_parse_cpu_zero_and_empty():
    assert _parse_cpu("0") == 0
    assert _parse_cpu("") == 0
    assert _parse_cpu(None) == 0


def test_parse_cpu_nanocores_rounds_to_zero():
    # 纳核 < 1 毫核时应归零，避免 0.0005 之类的小数干扰
    assert _parse_cpu("500n") == 0


def test_parse_memory_binary_units():
    assert _parse_memory("1Gi") == 1024**3
    assert _parse_memory("512Mi") == 512 * 1024**2
    assert _parse_memory("1Ki") == 1024


def test_parse_memory_decimal_units():
    assert _parse_memory("1G") == 1000**3
    assert _parse_memory("1M") == 1000**2


def test_parse_memory_bare_bytes():
    assert _parse_memory("1024") == 1024
    assert _parse_memory("0") == 0
    assert _parse_memory("") == 0


def test_assess_node_resource_normal():
    assert "正常" in _assess_node_resource(50, 50)


def test_assess_node_resource_overload():
    out = _assess_node_resource(95, 30)
    assert "CPU" in out and "过载" in out


def test_assess_node_resource_high():
    out = _assess_node_resource(75, 80)
    assert "偏高" in out
