import logging
import sys
import time


class LatencyFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "latency_ms"):
            record.latency_ms = ""
        return True


def setup_logging(level: str = "info"):
    fmt = "%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s %(latency_ms)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    handler.addFilter(LatencyFilter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class Timer:
    """Context manager to measure elapsed time."""

    def __init__(self, name: str = "", logger: logging.Logger | None = None):
        self.name = name
        self.logger = logger
        self.elapsed_ms: float = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        if self.logger and self.name:
            self.logger.info(
                f"{self.name}: {self.elapsed_ms:.0f}ms",
                extra={"latency_ms": f"[{self.elapsed_ms:.0f}ms]"},
            )
