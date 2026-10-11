#!/usr/bin/env python3
"""Self-check for Understory's own logic (not the models). Run: python tests/test_understory.py"""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import understory as tg


def test_collapse_keeps_best_hit_per_species():
    dets = [
        {"common_name": "European Robin", "scientific_name": "Erithacus rubecula",
         "confidence": 0.4, "start_time": 0},
        {"common_name": "European Robin", "scientific_name": "Erithacus rubecula",
         "confidence": 0.9, "start_time": 3},
        {"common_name": "Great Tit", "scientific_name": "Parus major",
         "confidence": 0.6, "start_time": 0},
    ]
    rows = tg.collapse(dets)
    assert [r["common_name"] for r in rows] == ["European Robin", "Great Tit"], rows
    robin = rows[0]
    assert robin["confidence"] == 0.9 and robin["hits"] == 2 and robin["at"] == 3
    assert tg.collapse([]) == []


def test_card_reports_a_miss_clearly():
    assert "Nothing bird-shaped" in tg.format_card([], None, offline=False)
    card = tg.format_card(
        [{"common_name": "Great Tit", "confidence": 1.0}], "Black head, white cheeks.",
        offline=True)
    assert "Great Tit (100%)" in card and "Black head" in card


def test_offline_guard_blocks_the_internet_but_allows_loopback():
    # A real loopback listener the guard must let through.
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        with tg.offline_guard():
            socket.create_connection(("127.0.0.1", port), timeout=2).close()
            try:
                socket.create_connection(("1.1.1.1", 443), timeout=2).close()
                raise AssertionError("offline guard let a public connection through")
            except OSError as e:
                assert "offline" in str(e), e
    finally:
        srv.close()
    # Guard is lifted on exit.
    s = socket.socket()
    s.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all good")
