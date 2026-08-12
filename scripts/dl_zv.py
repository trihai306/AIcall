import sys
sys.stdout.reconfigure(encoding="utf-8")
from huggingface_hub import snapshot_download
p = snapshot_download(repo_id="hynt/ZipVoice-Vietnamese-2500h",
                      local_dir=r"C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h")
print("da tai ve:", p)
import os
for f in os.listdir(p):
    print("  %-28s %.1f MB" % (f, os.path.getsize(os.path.join(p,f))/1024/1024))
