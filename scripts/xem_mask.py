import inspect, sys
sys.stdout.reconfigure(encoding="utf-8")
from f5_tts.model.cfm import CFM
s = inspect.getsource(CFM.sample)
i = s.find("max_duration = duration.amax()")
print(s[i:i+2200])
