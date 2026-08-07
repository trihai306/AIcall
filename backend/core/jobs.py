"""Chạy script dài dưới nền và stream log về UI.

Tách ra từ backend/api/setup.py để trang Cài Model và trang Training giọng
dùng chung một cơ chế: cùng cách tách dòng, cùng cách lọc mã ANSI, cùng cách
hủy cả cây tiến trình con.

Mỗi module API tạo một JobRunner riêng, nên mutex "một job tại một thời điểm"
là cục bộ: đang train giọng thì vẫn xem được trạng thái cài model.
"""

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_LOG_LINES = 500

# Thêm đường dẫn Homebrew vào PATH: ollama vừa cài xong sẽ nằm ở đây
_EXTRA_PATHS = ["/opt/homebrew/bin", "/usr/local/bin"]

_PROGRESS_RE = re.compile(r"\d+%|\d+(\.\d+)?\s*[KMG]B")
# Thanh tqdm: "  7%|▋         | 2/30 [00:04<01:07,  2.39s/it]"
#
# Phần mô tả đứng TRƯỚC phần trăm là tuỳ chọn của tqdm và F5-TTS có dùng:
#   "Epoch 1/30:  67%|██████▋   | 28/42 [04:29<02:00, 8.63s/update, loss=0.76]"
# Bản cũ neo `^\s*\d+%` nên không khớp dạng này -> không gộp được, mỗi lần tqdm
# vẽ lại là một dòng mới. Đo trên log thật: mỗi bước train đẩy thêm 2 dòng, buổi
# train 30 epoch trôi sạch log thật khỏi bộ đệm 500 dòng, và người dùng chỉ còn
# thấy thanh tiến trình vỡ font lặp đi lặp lại.
_TQDM_RE = re.compile(r"^.{0,40}?\d+%\|")

# Bóc số từ dòng tqdm. Hai dạng trong dự án:
#   F5-TTS  "Epoch 1/30:  67%|...| 28/42 [04:29<02:00,  8.63s/update, loss=0.76, update=27]"
#   chung   " 33%|...| 10/30 [00:21<00:40,  2.04s/it]"
_TQDM_SO_RE = re.compile(
    r"(?:Epoch\s+(?P<epoch>\d+)\s*/\s*(?P<tong_epoch>\d+)\s*:)?"
    r"\s*(?P<pt>\d+)%\|[^|]*\|\s*(?P<buoc>\d+)\s*/\s*(?P<tong_buoc>\d+)"
    r"\s*\[(?P<da>[\d:]+)<(?P<con>[\d:?]+)"
    r"(?:,\s*(?P<toc>[\d.]+)(?P<don_vi>s/\w+|\w+/s))?"
)
_TQDM_LOSS_RE = re.compile(r"loss=([\d.]+)")
# Ký tự vẽ thanh của tqdm. Qua PowerShell -> SSH -> log, chúng thành "�-^�-^..."
# và chiếm gần hết bề ngang dòng mà không mang tin gì.
_TQDM_BAR_RE = re.compile(r"\|[^|]*\|")
# ollama pull / pip vẽ thanh tiến trình bằng mã ANSI - lọc bỏ cho log dễ đọc
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-B0-2]")
# Ngắt dòng: xuống dòng thật, \r, và cả escape đưa con trỏ về đầu dòng /
# lên dòng trên (ESC[1G, ESC[A) - ollama dùng chúng thay cho \r.
_LINE_SPLIT_RE = re.compile(rb"[\r\n]|\x1b\[[0-9]*[GAB]")

_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏|/-\\"

# Script con phát tiến độ bằng dòng '[PROGRESS] {json}'. Cố ý lặp lại chuỗi này
# thay vì import từ training/: script train chạy trong .venv-train riêng, không
# có backend trên sys.path. Đổi ở đây thì phải đổi cả training/llm/train_lora.py.
_PROGRESS_PREFIX = "[PROGRESS] "


def build_env(project_dir: Path, extra: dict[str, str] | None = None) -> dict:
    env = os.environ.copy()
    parts = env.get("PATH", "").split(os.pathsep)
    for p in _EXTRA_PATHS:
        if p not in parts:
            parts.append(p)
    env["PATH"] = os.pathsep.join(parts)
    env["PROJECT_DIR"] = str(project_dir)
    env["PYTHONUNBUFFERED"] = "1"
    # Console Windows mặc định cp1252: script con in tiếng Việt là chết giữa
    # chừng vì UnicodeEncodeError, và job báo lỗi ở chỗ chẳng liên quan gì tới
    # việc nó đang làm. Ép UTF-8 cho mọi tiến trình con.
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def kill_tree(proc) -> None:
    """Hạ cả cây tiến trình con của một job.

    POSIX: job chạy với start_new_session=True nên pid cũng là process-group id,
    killpg là hạ được cả nhóm.

    Windows: os.killpg và os.getpgid KHÔNG tồn tại - gọi thẳng là ném
    AttributeError, mà except bên dưới chỉ bắt ProcessLookupError/PermissionError
    nên lỗi lọt ra ngoài: UI báo đã huỷ, còn tiến trình train vẫn chạy và vẫn
    giữ VRAM. Phải nhờ taskkill /T mới hạ được cây tiến trình.
    """
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=15)
        except Exception as e:
            logger.warning("taskkill thất bại: %s", e)
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _is_progress_update(prev: str, cur: str) -> bool:
    """Dòng mới có phải chỉ là cập nhật của dòng trước (thanh %, spinner)?"""
    # Thanh tqdm (" 33%|███▎ | 10/30 [00:21<00:40, 2.04s/it]") đổi phần trăm ở
    # ngay đầu dòng, nên phép so 14 ký tự đầu bên dưới luôn cho là dòng mới và
    # mỗi bước train lại đẩy thêm một dòng. Train vài nghìn bước là trôi sạch
    # log thật khỏi bộ đệm 500 dòng. Tiến độ đã có đường riêng qua [PROGRESS]
    # nên ở đây chỉ cần giữ lại dòng cuối cùng.
    if _TQDM_RE.match(prev) and _TQDM_RE.match(cur):
        return True
    if prev[:14] != cur[:14]:
        return False
    if _PROGRESS_RE.search(cur) and _PROGRESS_RE.search(prev):
        return True
    return cur[-1] in _SPINNER_CHARS and prev[-1] in _SPINNER_CHARS


def _giay(s: str) -> int | None:
    """'04:29' hoặc '1:02:33' -> giây. '?' (tqdm chưa ước lượng được) -> None."""
    if not s or "?" in s:
        return None
    phan = s.split(":")
    try:
        so = [int(x) for x in phan]
    except ValueError:
        return None
    giay = 0
    for x in so:
        giay = giay * 60 + x
    return giay


def _doc_tqdm(text: str) -> dict | None:
    """Bóc dòng tqdm thành tiến độ TOÀN BUỔI.

    Vì sao không dùng thẳng số tqdm in ra: nó chỉ biết vòng lặp hiện tại. Train
    giọng chạy 30 epoch thì tqdm báo "còn 02:00" trong khi thực tế còn gần hai
    tiếng - người dùng nhìn số đó rồi tưởng sắp xong, đây là câu hỏi họ hỏi
    nhiều nhất. Nhân lên theo epoch mới ra con số trả lời được.
    """
    m = _TQDM_SO_RE.search(text)
    if not m:
        return None
    g = m.groupdict()
    buoc, tong_buoc = int(g["buoc"]), int(g["tong_buoc"])
    if tong_buoc <= 0:
        return None

    toc = float(g["toc"]) if g.get("toc") else None
    # tqdm in "8.63s/update" (giây mỗi bước) HOẶC "2.04it/s" (bước mỗi giây) tuỳ
    # tốc độ. Lẫn hai cái là ETA sai cả trăm lần.
    if toc and g.get("don_vi") and not g["don_vi"].startswith("s/"):
        toc = 1.0 / toc if toc else None

    ep = int(g["epoch"]) if g.get("epoch") else None
    tong_ep = int(g["tong_epoch"]) if g.get("tong_epoch") else None

    if ep and tong_ep:
        xong = (ep - 1) * tong_buoc + buoc
        tong = tong_ep * tong_buoc
    else:
        xong, tong = buoc, tong_buoc

    tien = {
        "percent": round(xong * 100 / tong, 1),
        "step": xong,
        "total": tong,
        "epoch": f"{ep}/{tong_ep}" if ep else None,
        "buoc_trong_epoch": f"{buoc}/{tong_buoc}",
        "giay_moi_buoc": round(toc, 2) if toc else None,
        "da_chay_s": _giay(g["da"] or ""),
        # ETA của TOÀN BUỔI. Khi thiếu tốc độ thì lùi về ETA của tqdm (chỉ đúng
        # cho epoch hiện tại) chứ không bịa số.
        "eta_s": round((tong - xong) * toc) if toc else _giay(g["con"] or ""),
        "eta_toan_buoi": bool(toc and ep and tong_ep),
    }
    ml = _TQDM_LOSS_RE.search(text)
    if ml:
        tien["loss"] = ml.group(1)
    return tien


def _gon_tqdm(text: str) -> str:
    """Bỏ thanh vẽ, giữ lại số. Thanh qua SSH thành '�-^�-^...' vô nghĩa."""
    return _TQDM_BAR_RE.sub("| ", text, count=1).rstrip()


@dataclass
class Job:
    id: str
    component: str
    label: str
    status: str = "running"           # running | done | error | cancelled
    lines: deque = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    returncode: int | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    process: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None   # giữ tham chiếu, tránh bị GC giữa chừng
    progress: dict | None = None       # mốc tiến độ mới nhất do script con phát
    step_label: str = ""               # tên bước đang chạy, hiện lên UI

    def log(self, text: str):
        # Dòng tiến độ không đi vào log: nó lặp lại mỗi vài giây, để lẫn vào thì
        # trôi hết log thật trong buffer 500 dòng.
        #
        # Dùng find() chứ KHÔNG phải startswith(): tqdm vẽ thanh tiến trình ra
        # stderr bằng \r và không xuống dòng, nên dòng tới nơi thường có dạng
        #   " 33%|███▎ | 5/15 [00:11<00:21] [PROGRESS] {...}"
        # tức là tiền tố nằm giữa dòng. startswith() không khớp -> tiến độ
        # không bao giờ được cập nhật, mà cũng chẳng có lỗi nào báo ra.
        vi_tri = text.find(_PROGRESS_PREFIX)
        if vi_tri >= 0:
            phan_json = text[vi_tri + len(_PROGRESS_PREFIX):]
            try:
                # raw_decode: bỏ qua phần thừa phía sau nếu tqdm lại ghi tiếp
                # vào cùng dòng.
                tien = json.JSONDecoder().raw_decode(phan_json)[0]
                # Đánh dấu để bộ bóc tqdm bên dưới không ghi đè lên.
                tien["tu_script"] = True
                self.progress = tien
            except ValueError:
                logger.debug("dòng tiến độ hỏng: %r", text[:200])
            return

        # Script không tự phát [PROGRESS] (F5-TTS dùng trainer của thư viện, ta
        # không sửa được vòng lặp của nó) thì bóc số từ chính dòng tqdm.
        # KHÔNG ghi đè tiến độ do script tự phát: dòng đó luôn chính xác hơn.
        if _TQDM_RE.match(text):
            tien = _doc_tqdm(text)
            if tien and not (self.progress or {}).get("tu_script"):
                self.progress = tien
            text = _gon_tqdm(text)

        # Thanh tiến trình (ollama pull, huggingface) ghi đè dòng cuối thay vì
        # đẩy thêm hàng trăm dòng vào buffer.
        if self.lines and _is_progress_update(self.lines[-1], text):
            self.lines[-1] = text
        else:
            self.lines.append(text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "component": self.component,
            "label": self.label,
            "status": self.status,
            "returncode": self.returncode,
            "elapsed_s": round((self.finished or time.time()) - self.started, 1),
            "lines": list(self.lines),
            "progress": self.progress,
            "step_label": self.step_label,
        }


async def _pump(job: Job, stream: asyncio.StreamReader):
    """Đọc output, tách dòng theo cả ký tự xuống dòng lẫn escape con trỏ."""
    buf = b""
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        buf += chunk
        parts = _LINE_SPLIT_RE.split(buf)
        buf = parts.pop()
        for raw in parts:
            line = _ANSI_RE.sub("", raw.decode("utf-8", "replace")).rstrip()
            if line:
                job.log(line)
    if buf:
        line = _ANSI_RE.sub("", buf.decode("utf-8", "replace")).rstrip()
        if line:
            job.log(line)


@dataclass
class Step:
    """Một lệnh trong job. `label` chỉ hiện khi job có nhiều bước."""
    command: list[str]
    label: str = ""
    env: dict[str, str] | None = None


class JobRunner:
    """Hàng đợi một-job-một-lúc, giữ log của các job đã chạy để UI đọc lại."""

    def __init__(self, project_dir: Path, timeout_s: int = 3600):
        self.project_dir = project_dir
        self.timeout_s = timeout_s
        self._jobs: dict[str, Job] = {}
        self._running_job_id: str | None = None

    # --- truy vấn ---

    @property
    def running_job_id(self) -> str | None:
        job = self._jobs.get(self._running_job_id or "")
        return self._running_job_id if job and job.status == "running" else None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def is_busy(self) -> bool:
        return self.running_job_id is not None

    # --- chạy ---

    def start(self, component: str, steps: list[Step], label: str) -> Job:
        job = Job(id=f"job_{int(time.time() * 1000)}", component=component, label=label)
        self._jobs[job.id] = job
        self._running_job_id = job.id
        job.log(f"Bắt đầu: {label}")
        job.task = asyncio.create_task(self._run(job, steps))
        return job

    async def _run(self, job: Job, steps: list[Step]):
        """Chạy lần lượt các bước; dừng ngay khi có bước lỗi."""
        try:
            for step in steps:
                if job.status == "cancelled":
                    break
                if len(steps) > 1 and step.label:
                    job.log(f"══ {step.label} ══")

                # start_new_session chỉ có nghĩa trên POSIX (tách process group
                # để hủy được cả cây). Windows bỏ qua tham số này, việc hủy do
                # kill_tree() lo bằng taskkill.
                extra_kw = {} if os.name == "nt" else {"start_new_session": True}

                proc = await asyncio.create_subprocess_exec(
                    *step.command,
                    cwd=str(self.project_dir),
                    env=build_env(self.project_dir, step.env),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    **extra_kw,
                )
                job.process = proc

                try:
                    await asyncio.wait_for(
                        asyncio.gather(_pump(job, proc.stdout), proc.wait()),
                        timeout=self.timeout_s,
                    )
                except asyncio.TimeoutError:
                    # kill_tree chứ không phải proc.kill(): train sinh tiến
                    # trình con, giết mỗi tiến trình cha là bỏ lại con giữ VRAM.
                    kill_tree(proc)
                    job.log(f"[ERROR] Quá thời gian {self.timeout_s}s, đã hủy.")
                    job.status = "error"
                    job.returncode = -1
                    return

                job.returncode = proc.returncode
                if job.status == "cancelled":
                    return
                if proc.returncode != 0:
                    name = step.label or " ".join(step.command[:2])
                    job.log(f"[ERROR] Bước '{name}' thất bại (exit {proc.returncode})")
                    job.status = "error"
                    return

            if job.status != "cancelled":
                job.status = "done"
                job.log("[OK] Hoàn tất.")
        except FileNotFoundError as e:
            # Lệnh không tồn tại (thiếu python/bash/script) - nói rõ thiếu gì
            # thay vì để job treo ở trạng thái running.
            job.log(f"[ERROR] Không chạy được lệnh: {e}")
            job.status = "error"
        except Exception as e:
            logger.exception("job failed")
            job.log(f"[ERROR] {e}")
            job.status = "error"
        finally:
            job.finished = time.time()
            job.process = None
            self._running_job_id = None

    def cancel(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            return {"error": "Job không tồn tại"}
        if job.status != "running":
            return {"error": f"Job đã ở trạng thái '{job.status}'"}

        job.status = "cancelled"
        job.log("[INFO] Đã hủy theo yêu cầu.")
        if job.process:
            kill_tree(job.process)
        return job.to_dict()
