import sys
sys.path.insert(0, r"C:\duan\chat-ai\tools\ZipVoice")
sys.stdout.reconfigure(encoding="utf-8")
from zipvoice.tokenizer.tokenizer import EspeakTokenizer
tf = r"C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h\tokens.txt"
tok = EspeakTokenizer(token_file=tf, lang="vi")
cau = "dạ lãi suất vay tín chấp hiện tại"
try:
    ph = tok.texts_to_token_ids([cau])
    print("token ids :", ph[0][:30], "... tong", len(ph[0]))
except Exception as e:
    print("LOI texts_to_token_ids:", type(e).__name__, e)
try:
    t = tok.texts_to_tokens([cau])
    print("phoneme   :", t[0][:40])
except Exception as e:
    print("LOI texts_to_tokens:", type(e).__name__, e)
# so voi tieng Anh de biet espeak co chay khong
try:
    tok_en = EspeakTokenizer(token_file=tf, lang="en-us")
    print("EN phoneme:", tok_en.texts_to_tokens(["hello how are you"])[0][:30])
except Exception as e:
    print("LOI EN:", e)
