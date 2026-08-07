import io, re, sys, os
sys.stdout.reconfigure(encoding="utf-8")
L = io.open(r"C:\duan\chat-ai\logs\train.log", encoding="utf-8", errors="replace").read().splitlines()
print("tong %d dong" % len(L))
key = ("epoch", "step", "update", "loss", "Epoch", "Error", "error", "Traceback", "warn", "WARN", "saving", "Save")
hit = [l for l in L if any(k in l for k in key)]
print("--- dong lien quan train (20 cuoi) ---")
for l in hit[-20:]:
    print("  " + l.strip()[:130])
print("\n--- checkpoint sinh ra ---")
for d in (r"C:\duan\chat-ai\tools\F5-TTS-Vietnamese\ckpts\your_training_dataset",
          r"C:\duan\chat-ai\models\tts\finetuned\giong_vivos"):
    if os.path.isdir(d):
        for f in os.listdir(d):
            p = os.path.join(d, f)
            print("  %-52s %8.1f MB" % (p.replace("C:\\duan\\chat-ai\\",""), os.path.getsize(p)/1024/1024))
    else:
        print("  (khong co) " + d)
