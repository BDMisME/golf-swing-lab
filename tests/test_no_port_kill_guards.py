"""
Golf Swing Lab R4 — Port Kill Prevention & Process Safety Unit Tests (`tests/test_no_port_kill_guards.py`).

依據《R4 PR #4 第三輪獨立審查指令》P0-B 要求：
徹底拔除無條件暴力殺 Port (lsof -ti :28000 | xargs kill -9) 行為。
當指定 Port 已被外部程序佔用時，驗證程式必須安全拒絕啟動 (Fail-Closed) 並回報 BLOCKED_PORT_IN_USE，
絕不可殺死或干擾任何非本輪啟動之既有服務程序。
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
import pytest

from scripts.verify_r4_webkit import is_port_in_use


def test_is_port_in_use_detects_open_socket():
    """驗證 is_port_in_use 能準確探測 loopback 監聽狀態。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        free_port = s.getsockname()[1]
        assert is_port_in_use(free_port), f"Port {free_port} should be reported as in use"

    # Socket 關閉後應不再佔用
    assert not is_port_in_use(free_port), f"Port {free_port} should be free after close"


def test_port_in_use_refuses_to_kill_external_dummy_server():
    """負面測試：在 28000 埠啟動帶識別碼的 dummy server，驗證檢測邏輯拒絕暴力 kill 且該 dummy server 依然活著。"""
    # 建立一個測試用的 socket server 佔用 28000 (若未被佔用)
    if is_port_in_use(28000):
        pytest.skip("Port 28000 already in use in environment, skipping synthetic dummy test")

    dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dummy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dummy_sock.bind(("127.0.0.1", 28000))
    dummy_sock.listen(5)

    try:
        assert is_port_in_use(28000)

        # 呼叫 verify_r4_webkit 中的佔用檢查機制
        from scripts.verify_r4_webkit import run_verification

        with pytest.raises(RuntimeError, match="BLOCKED_PORT_IN_USE.*Port 28000 is occupied"):
            run_verification(sabotage="none")

        # 核心斷言：dummy_sock 必須完好無損，未被殺死
        assert is_port_in_use(28000)
    finally:
        dummy_sock.close()
        time.sleep(0.2)
