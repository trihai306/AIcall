"""Xoa cau dem co van tay CU. Chi giu van tay dang dung.

Doi toc/nfe/ref_text la van tay doi, ban cu nam lai tren dia mai mai: co che don
trong `_dung_mot_filler` chi xoa khi TO HOP DO duoc dung lai, ma to hop khong con
duoc goi thi khong ai dung toi.
"""
import sys
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import urllib.request, json
with urllib.request.urlopen("http://127.0.0.1:8100/api/health",timeout=30) as r: json.load(r)
from backend.main import app_state
from backend.services.filler_store import lay_kho
from backend.services.filler_pick import ghep
tts=app_state.tts
kho=lay_kho()
giong=tts._default_voice
toc_giong=tts.toc_do_cua(giong)
giu=set()
for d in kho.duoi:
    giu.add(tts._duong_dan_filler(giong,"",d.id,
            tts._van_tay_filler(ghep("",d.text),giong,toc_giong)))
for t in kho.tinh_huong:
    toc=t.speed if t.speed is not None else toc_giong
    for m in t.mo_dau:
        for d in kho.duoi:
            giu.add(tts._duong_dan_filler(giong,t.id,d.id,
                    tts._van_tay_filler(ghep(m,d.text),giong,toc)))
D=Path(r"C:\duan\chat-ai\data\fillers_wav")
co=[p for p in D.rglob("*.wav")]
thua=[p for p in co if p not in giu]
thieu=[p for p in giu if not p.exists()]
print(f"cần giữ {len(giu)}   trên đĩa {len(co)}   thừa {len(thua)}   thiếu {len(thieu)}")
b=sum(p.stat().st_size for p in thua)
for p in thua: p.unlink(missing_ok=True)
print(f"đã xoá {len(thua)} tệp ({b/1024/1024:.1f} MB)")
print(f"còn lại {len(list(D.rglob('*.wav')))} tệp")
