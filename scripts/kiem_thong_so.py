import sys
sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.streaming_pipeline import StreamingPipeline as P
from backend.services import phone_call_service as PS

print(f"  nhip doan lai      {P._SPEC_STEP_BYTES/32000:.2f} s")
print(f"  bat dau doan sau   {P._SPEC_MIN_BYTES/32000:.2f} s")
print(f"  im lang chot luot  {PS.SILENCE_END_MS} ms")
print(f"  so tu dem cuoi     {len(P._TU_DEM_CUOI)}")
print(f"  rate_xuong         {PS.RATE_XUONG}")
xau = [t for t in ("rồi", "không", "hả", "luôn") if t in P._TU_DEM_CUOI]
print(f"  tu doi nghia lot vao: {xau or 'khong co (dung)'}")
