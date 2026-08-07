# Training giọng nói riêng (F5-TTS fine-tune)

Quy trình: **thu âm → chuẩn hoá dataset → train → đổi config**. Sau khi xong, AI sẽ trả lời bằng giọng của người được thu âm.

> **Pháp lý**: giọng nói là dữ liệu sinh trắc học (Nghị định 13/2023). Phải có **văn bản đồng ý** của người được thu âm trước khi clone giọng, kể cả nhân viên công ty.

## Bước 1 — Thu âm

**Thiết bị & môi trường:**
- Phòng yên tĩnh tuyệt đối (không quạt, không máy lạnh ồn, không tiếng đường)
- Micro càng tốt càng tốt (condenser USB là đủ; tai nghe điện thoại là mức tối thiểu)
- Giữ khoảng cách micro **đều nhau** giữa các câu (~15-20cm)
- Định dạng: WAV, mono, sample rate ≥ 24kHz (44.1kHz càng tốt)

**Cách đọc:**
- Đọc theo kịch bản [record_script.txt](record_script.txt) — 60 câu đã soạn đủ ngữ điệu nghiệp vụ
- Đọc **tự nhiên như đang nghe điện thoại**, không đọc đều đều như đọc văn bản
- Mỗi câu 1 file, đặt tên theo số thứ tự: `001.wav`, `002.wav`, ... `060.wav`
- Đọc sai thì thu lại cả câu, đừng giữ file có vấp

**Khối lượng:**
| Mức | Thời lượng | Kết quả |
|---|---|---|
| Tối thiểu | 10-15 phút (60 câu kịch bản) | Giọng nhận ra được, đôi chỗ chưa mượt |
| Khuyến nghị | 20-30 phút (đọc kịch bản 2 lần với ngữ điệu khác nhau + tự do) | Giọng giống, ngữ điệu ổn định |
| Tốt nhất | 45-60 phút | Giống nhất, số/ngày tháng đọc chuẩn |

## Bước 2 — Chuẩn hoá dataset

```bash
# STT server phải đang chạy nếu có file không theo kịch bản (để tự sinh transcript)
python training/voice/prepare_dataset.py --input ~/thu_am_giong
```

Script sẽ: resample 24kHz mono → cắt khoảng lặng → chuẩn âm lượng → gán transcript (ưu tiên kịch bản theo tên file, còn lại dùng PhoWhisper) → xuất vào `tools/F5-TTS-Vietnamese/data/your_dataset/`.

**Quan trọng:** nếu có transcript sinh bằng ASR, phải mở thư mục output **soát lại từng file .txt** trước khi train. Transcript sai = giọng train ra đọc sai.

## Bước 3 — Train

Chạy trên máy có GPU NVIDIA (RTX 5070 12GB: để nguyên tham số mặc định):

```bash
bash training/voice/train.sh giong_lan
```

Thời gian tham khảo trên RTX 5070: dataset 20 phút ≈ 2-4 giờ train (100 epochs).

Tuỳ chỉnh qua env: `EPOCHS=150 BATCH_SIZE=3200 bash training/voice/train.sh giong_lan`

## Bước 4 — Dùng giọng mới

Sửa `.env` theo hướng dẫn in ra cuối script train, rồi:

```bash
bash scripts/start_services.sh
```

Kiểm tra: `POST /api/benchmark/tts` và nghe thử trên web UI.

## Đánh giá & lặp lại

- Nghe thử **qua loa điện thoại thật** (audio 8kHz), không chỉ qua tai nghe máy tính — cuộc gọi thực tế sẽ nén giọng xuống narrowband.
- Chú ý nhất: **số tiền, số điện thoại, ngày tháng** — nếu đọc vấp, thu bổ sung nhóm 2-3 trong kịch bản rồi train tiếp.
- Nếu giọng "lơ lớ" hoặc thiếu tự nhiên → thu thêm dữ liệu (lên 45-60 phút) thay vì tăng epochs.
