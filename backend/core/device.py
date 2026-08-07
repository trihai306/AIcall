import logging
import platform
import torch

logger = logging.getLogger(__name__)


def detect_device() -> str:
    """Auto-detect best available compute device: cuda > mps > cpu."""
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        logger.info(f"Device: CUDA - {name} ({vram:.1f}GB VRAM)")
        return "cuda"

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        logger.info(f"Device: MPS (Apple Silicon - {platform.processor()})")
        return "mps"

    logger.info("Device: CPU (no GPU acceleration)")
    return "cpu"


def get_system_info() -> dict:
    """Return system info for diagnostics."""
    info = {
        "platform": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "device": detect_device(),
    }

    if info["device"] == "cuda":
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["gpu_vram_gb"] = round(
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 1
        )
        info["cuda_version"] = torch.version.cuda or "N/A"
    elif info["device"] == "mps":
        info["gpu_name"] = "Apple Silicon (Metal)"

    return info


def nproc() -> int:
    """Cross-platform CPU core count."""
    import os
    return os.cpu_count() or 4


# Detect once at import
DEVICE = detect_device()
