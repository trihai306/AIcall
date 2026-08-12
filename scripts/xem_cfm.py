import inspect, sys
sys.stdout.reconfigure(encoding="utf-8")
from f5_tts.model.cfm import CFM
s = inspect.getsource(CFM.sample)
print(s[:2600])
