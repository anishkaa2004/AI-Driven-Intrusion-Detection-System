from agent.collector import ConnKey, Snapshot
from agent.flow_builder import FlowBuilder
from agent.sender import Sender


def snap(conns, listening=()):
    return Snapshot(connections=conns, listening_ports=set(listening), mode="system")


def test_flow_emitted_when_connection_closes():
    k = ConnKey("TCP", ("10.0.0.5", 50000), ("93.184.216.34", 443))
    fb = FlowBuilder()
    assert fb.update(snap({k: "ESTABLISHED"}), now=100.0) == []
    assert fb.update(snap({k: "ESTABLISHED"}), now=105.0) == []
    [rec] = fb.update(snap({}), now=110.0)
    assert rec["src_ip"] == "10.0.0.5" and rec["dst_port"] == 443
    assert rec["flow_duration"] == 5.0 and rec["conn_state"] == "established"
    assert "bytes_in" not in rec  # unobserved counters are omitted, not zero


def test_inbound_direction_and_failed_handshake():
    k = ConnKey("TCP", ("10.0.0.5", 22), ("10.0.0.66", 41000))
    fb = FlowBuilder()
    fb.update(snap({k: "SYN_RECV"}, listening=[22]), now=1.0)
    [rec] = fb.update(snap({}, listening=[22]), now=2.0)
    assert rec["src_ip"] == "10.0.0.66" and rec["dst_port"] == 22
    assert rec["conn_state"] == "failed"


def test_long_lived_connection_reported_periodically():
    k = ConnKey("TCP", ("10.0.0.5", 50001), ("1.1.1.1", 443))
    fb = FlowBuilder(max_flow_age_s=60)
    fb.update(snap({k: "ESTABLISHED"}), now=0.0)
    assert len(fb.update(snap({k: "ESTABLISHED"}), now=61.0)) == 1
    assert k in fb.active


def test_sender_queue_is_bounded():
    s = Sender("http://127.0.0.1:9", "aiids_dev_1_x", max_queue=5)
    s.enqueue([{"i": i} for i in range(8)])
    assert len(s.queue) == 5 and s.dropped == 3
    s.close()
