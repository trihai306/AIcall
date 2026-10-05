"""Phục vụ frontend/ ở dạng tĩnh để soi giao diện khi không có backend (Mac).

/static/* -> frontend/*, / -> index.html, /api/* -> JSON rỗng. Không thay backend:
chỉ để nhìn bố cục, màu, chữ. Chạy: python3 scripts/xem_giao_dien_tinh.py [cổng]
"""
import http.server, json, pathlib, sys, mimetypes

GOC = pathlib.Path(__file__).resolve().parent.parent / "frontend"


import time
T = time.time()
# Dữ liệu mẫu, đúng hình dạng các API mà trang Tổng quan đọc - chỉ để soi bố cục.
MAU = {
    "/api/reports/summary": {"tong_cuoc": 128, "ty_le_nghe_may": 64, "tong_thoi_luong": 9340, "co_ghi_am": 82},
    "/api/phones/running": {"campaigns": [
        {"campaign_id": "Vay tín chấp tháng 10", "trang_thai": "dang_chay", "ly_do": "Đang chạy trong khung giờ 8:00-17:30",
         "da_goi": 74, "da_nghe_may": 49, "ty_le_nghe_may": 66, "dang_goi": [1]},
        {"campaign_id": "Mở thẻ tín dụng", "trang_thai": "tam_dung", "ly_do": "Tạm dừng: ngoài khung giờ",
         "da_goi": 54, "da_nghe_may": 33, "ty_le_nghe_may": 61, "dang_goi": []}]},
    "/api/devices": {"devices": [{"name": "Galaxy S9+ (SIM 0833…298)", "status": "online"},
                                 {"name": "Galaxy S9+ dự phòng", "status": "offline"}]},
    "/api/reports/calls": {"calls": [
        {"customer_name": "Anh Minh", "quality_label": "Quan tâm", "created_at": T - 600},
        {"customer_name": "Chị Hương", "quality_label": "Hẹn gọi lại", "created_at": T - 1900},
        {"phone": "0912 345 678", "outcome": "Không nghe máy", "created_at": T - 3300},
        {"customer_name": "Anh Tuấn", "quality_label": "Từ chối", "created_at": T - 5200},
        {"customer_name": "Chị Lan", "quality_label": "Quan tâm", "created_at": T - 7100}]},
    "/api/knowledge/thu-vien-tu-dong": {"enabled": True, "stats": {"answers": 2552, "voice_ready": 2493, "voice_total": 2552},
                                        "job": {"status": "running", "error": ""}},
}


class H(http.server.BaseHTTPRequestHandler):
    def _gui(self, ma, kieu, than):
        self.send_response(ma)
        self.send_header("Content-Type", kieu)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(than)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/health":
            return self._gui(200, "application/json", json.dumps({"status": "ok", "system": {
                "gpu_name": "NVIDIA GeForce RTX 5070", "gpu_vram_gb": 11.9}, "services": {"stt": "ok", "stt_engine": "gipformer",
                "llm": "ok", "tts": "loaded", "rag": "102 docs"}}).encode())
        if p in MAU:
            return self._gui(200, "application/json", json.dumps(MAU[p]).encode())
        if p.startswith("/api/"):
            return self._gui(200, "application/json", b"{}")
        # Trang dùng pushState (/overview, /knowledge...): mọi đường không phải
        # /static/ đều trả index.html.
        f = GOC / (p.removeprefix("/static/") if p.startswith("/static/") else "index.html")
        if not f.is_file() or GOC not in f.resolve().parents:
            return self._gui(404, "text/plain", b"khong co")
        self._gui(200, mimetypes.guess_type(f.name)[0] or "application/octet-stream", f.read_bytes())

    do_POST = do_GET

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8431), H).serve_forever()
