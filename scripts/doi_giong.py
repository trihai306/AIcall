"""Chuyen .env sang giong nam vua train. Co sao luu de quay lai duoc.

VI SAO DUNG PYTHON: PowerShell Set-Content ghi mac dinh bang UTF-16 hoac cp1252,
tung lam .env thanh 'NgA¢n hA ng ABC' - loi ma phai doc file bang mat moi thay.
Python voi encoding chi dinh ro thi khong co cua do.
"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENV = Path(r"C:\duan\chat-ai\.env")
LUU = Path(r"C:\duan\chat-ai\.env.truoc_giong_nam")
REF_TXT = Path(r"C:\duan\chat-ai\models\tts\ref_voices\giong_nam.txt")

ref_text = REF_TXT.read_text(encoding="utf-8").strip()

MOI = {
    "F5TTS_CKPT_PATH":  "./models/tts/finetuned/giong_nam/model_last.pt",
    "F5TTS_VOCAB_PATH": "./models/tts/finetuned/giong_nam/vocab.txt",
    "F5TTS_REF_AUDIO":  "./models/tts/ref_voices/giong_nam.wav",
    "F5TTS_REF_TEXT":   ref_text,
}

if not LUU.exists():
    shutil.copy2(ENV, LUU)
    print(f"da sao luu -> {LUU.name}")
else:
    print(f"{LUU.name} da co tu truoc - giu nguyen ban goc")

dong = ENV.read_text(encoding="utf-8").splitlines()
da_sua = set()
ra = []
for d in dong:
    khoa = d.split("=", 1)[0].strip() if "=" in d and not d.lstrip().startswith("#") else ""
    if khoa in MOI:
        print(f"  {khoa}")
        print(f"    cu : {d.split('=', 1)[1]}")
        print(f"    moi: {MOI[khoa]}")
        ra.append(f"{khoa}={MOI[khoa]}")
        da_sua.add(khoa)
    else:
        ra.append(d)

for khoa, gt in MOI.items():
    if khoa not in da_sua:
        print(f"  {khoa} chua co -> them moi")
        ra.append(f"{khoa}={gt}")

ENV.write_text("\n".join(ra) + "\n", encoding="utf-8")
print("da ghi .env")

# Doc lai de chac chan khong hong dau - doc ma khong loi la du.
kt = ENV.read_text(encoding="utf-8")
for khoa in MOI:
    for d in kt.splitlines():
        if d.startswith(khoa + "="):
            print(f"kiem lai {khoa}={d.split('=', 1)[1]}")
