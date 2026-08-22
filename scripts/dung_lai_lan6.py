"""Dung lai dung cac cau Lan 6, o BA muc nhip nghi de nguoi dung chon bang tai."""
import asyncio, io, sys, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.pipeline.text_chunker as tc
import backend.api.voices as V
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 6 - DA SUA")
CAU={
 "4 - Da, dat o do thi (cho nghi sau 'Da')":
   "Dạ, đất ở đô thị có nhà kiên cố như vậy thì thanh khoản rất tốt. Vị trí nhà mình là mặt tiền đường lớn hay trong hẻm ạ. Ngõ trước nhà rộng khoảng bao nhiêu mét, xe hơi có vào tận nơi được không anh",
 "6 - Vang, ngo o to (cho nghi sau 'Vang' + sau 'tham dinh.')":
   "Vâng, ngõ ô tô vào được là điểm cộng lớn khi định giá tài sản ạ. Thông thường ngân hàng sẽ cho vay tối đa khoảng 70% đến 75% giá trị tài sản mà ngân hàng thẩm định. Với căn nhà 80 mét vuông kèm nhà 3 tầng ở khu vực đó, nếu định giá sơ bộ tầm",
 "7 - Buoc tiep theo (cho nghi sau 'tra no.')":
   "Bước tiếp theo là phần nguồn thu để trả nợ. Hiện tại thu nhập chính của hai vợ chồng đến từ những nguồn nào vậy anh",
 "2 - Da vang, nhu cau bo sung von":
   "Dạ vâng, nhu cầu bổ sung vốn kinh doanh và sửa nhà thì bên em đang hỗ trợ rất tốt. Cho em hỏi thêm là dự kiến anh muốn vay trong thời gian bao lâu ạ. Ví dụ như 5 năm, 10 năm hay dài hơn là 15 đến 20 năm",
}
MUC=[("A nhip nay (phay 100, cham 200)",100.0,200.0),
     ("B nghi dai hon (phay 180, cham 320)",180.0,320.0),
     ("C nghi dai nhat (phay 250, cham 450)",250.0,450.0)]
def lang(x,sr,toi_thieu=60):
    o=int(sr*0.020); n=len(x)//o
    e=np.array([float(np.sqrt(np.mean(x[i*o:(i+1)*o]**2))) for i in range(n)])
    ng=0.20*float(np.percentile(e,95)); im=e<ng; ra=[];i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*20>=toi_thieu: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra
async def main():
    from backend.services.tts_service import F5TTSService
    tts=F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    RA.mkdir(parents=True, exist_ok=True)
    gp,gc=tc.NGHI_PHAY_MS,tc.NGHI_CHAM_MS
    for nhan,phay,cham in MUC:
        tc.NGHI_PHAY_MS,tc.NGHI_CHAM_MS=phay,cham
        d=RA/nhan; d.mkdir(exist_ok=True)
        print(f"\n=== {nhan}")
        for ten,van in CAU.items():
            manh=V._cat_manh_nhu_pipeline(van)
            wav=await V._ghep_nhu_pipeline(tts,manh,"giong_heu",toc,False)
            (d/f"{ten}.wav").write_bytes(wav)
            with wave.open(io.BytesIO(wav)) as w:
                sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
            q=sorted(lang(x,sr),reverse=True)[:4]
            print(f"   {ten[:42]:<44} {len(x)/sr:5.2f}s {len(manh)} mảnh  "
                  f"4 quãng nghỉ dài nhất: {', '.join(f'{v:.0f}ms' for v in q)}")
    tc.NGHI_PHAY_MS,tc.NGHI_CHAM_MS=gp,gc
    print(f"\nFile: {RA}")
asyncio.run(main())
