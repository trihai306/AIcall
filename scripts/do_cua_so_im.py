"""Ha cua so im xuong thi bao nhieu cau khach bi che doi? Do tren MOI ban ghi."""
import glob, os, numpy as np, soundfile as sf
GOC = r"C:\duan\chat-ai"
ONF, MINT, HSO = 4, 130, 3.0
ON_SAN, TAT = 500.0, 500.0

def dem_luot(R, nen, sil_ms):
    on = max(ON_SAN, nen*HSO); sil_can = sil_ms//20
    sp=False; st=im=dau=0; n=0
    for i,v in enumerate(R):
        if not sp:
            st = st+1 if v>=on else 0
            if st>=ONF: sp=True; st=0; im=0; dau=i
        else:
            if v<TAT:
                im+=1
                if im>=sil_can:
                    sp=False
                    if (i-im-dau)*20>=MINT: n+=1
            else: im=0
    return n

MOC = (400, 500, 600, 700, 800, 900, 1000)
tong = {m:0 for m in MOC}; nfile=0
for f in sorted(glob.glob(os.path.join(GOC,"data","recordings","**","*.opus"), recursive=True)):
    try: x,sr = sf.read(f, always_2d=True)
    except Exception: continue
    h=int(sr*0.02); n=len(x)//h*h
    KH=np.sqrt(np.mean(x[:n,0].reshape(-1,h)**2,axis=1))*32768
    nen=float(np.percentile(KH,20))
    for m in MOC: tong[m]+=dem_luot(KH,nen,m)
    nfile+=1
goc = tong[1000]
print(f"{nfile} ban ghi. Voi cua so im 1000ms hien tai: {goc} luot\n")
print("cua so im | so luot | CHE DOI them | AI cat tieng sau")
for m in MOC:
    them = tong[m]-goc
    print(f"{m:6d}ms  | {tong[m]:6d}  | {them:+5d} ({100*them/goc:+5.1f}%) | {m+9:5d}ms  {'DAT <1s' if m+9<1000 else 'khong dat'}")
