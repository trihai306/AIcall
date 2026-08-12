import inspect, sys
sys.stdout.reconfigure(encoding="utf-8")
import f5_tts.infer.utils_infer as u
s = inspect.getsource(u.infer_batch_process)
print(s[:3000])
