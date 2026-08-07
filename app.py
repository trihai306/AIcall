"""
VoiceBank AI — Desktop Application
Cross-platform: macOS (WebKit) + Windows (WebView2/EdgeChromium)
"""
import logging
import os
import signal
import subprocess
import sys
import threading
import time

logger = logging.getLogger("voicebank")

PORT = int(os.environ.get("PORT", 8000))
backend_proc = None


def get_python():
    """Get the Python executable from the venv."""
    venv = os.path.join(os.path.dirname(__file__), ".venv")
    if sys.platform == "win32":
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python3")


def start_backend():
    global backend_proc
    python = get_python()
    if not os.path.exists(python):
        python = sys.executable

    logger.info(f"Starting backend: {python}")
    backend_proc = subprocess.Popen(
        [python, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "info"],
        cwd=os.path.dirname(__file__),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    def pipe_logs():
        for line in backend_proc.stdout:
            line = line.rstrip()
            if line:
                logger.info(f"[server] {line}")

    threading.Thread(target=pipe_logs, daemon=True).start()


def stop_backend():
    global backend_proc
    if backend_proc and backend_proc.poll() is None:
        logger.info("Stopping backend...")
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
    backend_proc = None


def wait_backend(timeout=60):
    import urllib.request
    url = f"http://127.0.0.1:{PORT}/api/health"
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = urllib.request.urlopen(url, timeout=2)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        import webview
    except ImportError:
        print("pywebview chưa cài. Chạy: pip install pywebview")
        sys.exit(1)

    debug = "--dev" in sys.argv

    logger.info("=" * 50)
    logger.info("  VoiceBank AI — Desktop App")
    logger.info("=" * 50)

    start_backend()
    logger.info("Đang khởi động server...")

    if not wait_backend(60):
        logger.error("Backend không khởi động được sau 60 giây")
        stop_backend()
        sys.exit(1)

    logger.info("Server sẵn sàng!")

    window = webview.create_window(
        title="VoiceBank AI",
        url=f"http://127.0.0.1:{PORT}",
        width=1440,
        height=920,
        min_size=(1000, 700),
        background_color="#06080f",
        text_select=True,
    )

    window.events.closed += lambda: stop_backend()

    signal.signal(signal.SIGINT, lambda *_: (stop_backend(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (stop_backend(), sys.exit(0)))

    logger.info("Đang mở cửa sổ ứng dụng...")
    webview.start(debug=debug)


if __name__ == "__main__":
    main()
