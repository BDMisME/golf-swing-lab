import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("GolfSwingLabDesktop")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "GolfSwingLab"
MODELS_DIR = SUPPORT_DIR / "models"

_SPAWNED_PROCESSES: list[subprocess.Popen] = []


def _cleanup_spawned_processes() -> None:
    for p in _SPAWNED_PROCESSES:
        try:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


atexit.register(_cleanup_spawned_processes)


def ensure_environment() -> None:
    """確保 Mac 本機目錄與模型權重快取目錄就緒。"""
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"本地快取目錄就緒: {SUPPORT_DIR}")

    # 若工作目錄有 yolov8x-pose.pt，確保複製或連結至 Application Support
    repo_model = APP_DIR / "yolov8x-pose.pt"
    dest_model = MODELS_DIR / "yolov8x-pose.pt"
    if repo_model.exists() and not dest_model.exists():
        try:
            import shutil

            shutil.copy2(repo_model, dest_model)
            logger.info(f"已將 YOLOv8x 權重持久化至: {dest_model}")
        except Exception as e:
            logger.warning(f"複製模型權重至應用目錄失敗: {e}")


def ensure_services_running() -> None:
    """確保 PostgreSQL, Redis, MinIO, API, Worker, Web 已在本機就緒。"""
    import httpx

    # 1. 檢查 Docker Compose 基礎設施
    compose_file = APP_DIR / "infra" / "compose.dev.yml"
    try:
        if compose_file.exists():
            res = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "ps", "--status", "running", "-q"],
                cwd=str(APP_DIR),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if not res.stdout.strip():
                logger.info("正在啟動本地容器基礎設施 (Postgres, Redis, MinIO)...")
                subprocess.run(["docker", "compose", "-f", str(compose_file), "up", "-d"], cwd=str(APP_DIR), check=True)
                time.sleep(2)
    except Exception as exc:
        logger.warning(f"檢查 Docker 基礎設施提示: {exc}")

    # 2. 檢查 API 伺服器 (Port 28000)
    api_ready = False
    try:
        r = httpx.get("http://127.0.0.1:28000/healthz", timeout=1.5)
        if r.status_code == 200:
            api_ready = True
    except Exception:
        pass

    if not api_ready:
        logger.info("啟動本地 API 伺服器 Sidecar...")
        p_api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "28000"],
            cwd=str(APP_DIR),
        )
        _SPAWNED_PROCESSES.append(p_api)

    # 3. 檢查 RQ Worker 是否正在運行
    worker_running = False
    try:
        check = subprocess.run(
            ["pgrep", "-f", "apps.worker.main"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if check.returncode == 0 and check.stdout.strip():
            worker_running = True
    except Exception:
        pass

    if not worker_running:
        logger.info("啟動本地 RQ 背景任務 Worker Sidecar...")
        worker_env = os.environ.copy()
        worker_env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
        p_worker = subprocess.Popen(
            [sys.executable, "-m", "apps.worker.main"],
            cwd=str(APP_DIR),
            env=worker_env,
        )
        _SPAWNED_PROCESSES.append(p_worker)

    # 4. 檢查 Web 伺服器 (Port 23000)
    web_ready = False
    try:
        r = httpx.get("http://127.0.0.1:23000", timeout=1.5)
        if r.status_code == 200:
            web_ready = True
    except Exception:
        pass

    if not web_ready:
        logger.info("啟動本地 Web 伺服器 Sidecar...")
        p_web = subprocess.Popen(
            ["npm", "run", "start", "--", "-p", "23000"],
            cwd=str(APP_DIR / "apps" / "web"),
        )
        _SPAWNED_PROCESSES.append(p_web)

    # 5. 等待 Web 伺服器與 API 就緒 (最長 12 秒)
    start_wait = time.time()
    while time.time() - start_wait < 12:
        try:
            rw = httpx.get("http://127.0.0.1:23000", timeout=1.0)
            ra = httpx.get("http://127.0.0.1:28000/healthz", timeout=1.0)
            if rw.status_code == 200 and ra.status_code == 200:
                logger.info("本地服務健康檢查通過，準備載入視窗。")
                break
        except Exception:
            pass
        time.sleep(0.8)


def launch_desktop_window() -> None:
    """使用 macOS 原生 WebKit 視窗加載 Golf Swing Lab 介面。"""
    import webview

    url = "http://localhost:23000"
    window = webview.create_window(
        title="Golf Swing Lab — AI 高爾夫動作分析室 (Mac 原生桌面版)",
        url=url,
        width=1320,
        height=880,
        min_size=(1024, 720),
        background_color="#0a0f14",
        confirm_close=True,
        text_select=True,
    )

    logger.info(f"啟動原生 macOS 視窗，載入: {url}")
    webview.start(debug=False)


def main() -> None:
    ensure_environment()
    ensure_services_running()
    launch_desktop_window()


if __name__ == "__main__":
    main()
