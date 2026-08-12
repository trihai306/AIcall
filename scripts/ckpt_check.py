import sys, json, torch
sys.stdout.reconfigure(encoding="utf-8")
p = r"C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h\iter-525000-avg-2.pt"
ck = torch.load(p, map_location="cpu", weights_only=False)
print("kieu:", type(ck).__name__)
if isinstance(ck, dict):
    keys = list(ck.keys())
    print("khoa cap 1 (%d):" % len(keys), keys[:8])
    sd = ck.get("model", ck)
    if isinstance(sd, dict):
        ks = list(sd.keys())
        print("so tensor:", len(ks))
        print("vai khoa :", ks[:5])
cfg = json.load(open(r"C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h\model.json", encoding="utf-8"))
print("\nmodel.json khoa cap 1:", list(cfg.keys()))
print("so token trong tokens.txt:", sum(1 for _ in open(r"C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h\tokens.txt", encoding="utf-8")))
