# Nguồn công khai Shinhan Bank — 23/09/2026

`manifest.json` ghi 24 URL trên miền chính thức `shinhan.com.vn`. Tải thành
công 22 PDF (27 MB); 2 URL lỗi được giữ trong manifest để không lẫn với tài liệu
đã tải. Bản text trích từ PDF ở `text/` chỉ phục vụ rà nguồn. Trường `use`:

- `review`: cần đối chiếu hiệu lực và nội dung trước khi dùng làm dữ kiện.
- `verify_current`: biểu phí/lãi suất biến động; không đưa con số vào LoRA.
- `archive`: tài liệu cũ; chỉ lưu để đối chiếu, không dùng làm chính sách hiện hành.

Lượt này chỉ hai tài liệu `card_user_guide_vi.pdf` và
`digital_card_guide.pdf` được rà đoạn liên quan rồi đưa thành 30 hội thoại
ngắn trong `data/training/shinhan_dialogue_style_v1.jsonl`. Qwen3.5-9B soạn
bản nháp, sau đó loại câu sai chủ đề, tự nhận đã xem sao kê, đảo vai xưng hô
hoặc thêm dữ kiện. Những PDF khác chưa phải dữ liệu train đã duyệt.

Candidate Windows: `banking-qwen35-2b-style-20260923-231319`, job
`job_1790179999894`, base Qwen3.5-2B, 1 epoch, 27 mẫu train và 3 holdout.
Chấm sau train: Shinhan 6/6 câu cơ bản, hội thoại tự nhiên 6/10, nghiệp vụ
7 câu cũ đạt 4/7. Nội dung vẫn máy móc và sai ngưỡng ở một số câu, nên không
chuyển candidate vào production. Qwen3.5-9B tiếp tục phục vụ.

`knowledge/products/*.md` là dữ liệu sản phẩm giả lập trước khi xác định ngân
hàng Shinhan. Không dùng các ngưỡng trong đó làm chính sách Shinhan. Cần tài
liệu sản phẩm còn hiệu lực của Shinhan để đối chiếu trước khi huấn luyện nghiệp
vụ hoặc đổi nguồn tra cứu đang phục vụ khách.

## Sinh dữ liệu quy mô lớn

`data/training/shinhan_verified_fact_cards.json` chứa 29 fact card đã đối
chiếu đoạn PDF. `training/llm/shinhan_large_teacher.py` dùng Qwen3.5-9B để
viết **câu hỏi của khách** theo từng fact card; đáp án lấy từ fact card, không
lấy từ lời model tự bịa. Sau đó 9B chấm tính tự nhiên và khả năng trả lời
bằng đúng fact/đáp án; bộ lọc quy tắc chặn lỗi đã thấy trong thực tế. Kết quả
`teacher_pass` chỉ là hàng chờ rà nguồn, **không tự động thành dữ liệu train**.
SQLite `data/training/shinhan_large/pending.sqlite` giữ câu nháp và trạng thái
để chạy tiếp không trùng sau khi khởi động lại. `training/llm/shinhan_review.py`
dùng để ghi duyệt/từ chối và xuất dataset đã duyệt.

Scheduled Task Windows `Shinhan-Teacher-Questions` chạy lại mỗi phút. Scheduled
Task `Shinhan-Bulk-Curate` kiểm tra mỗi 5 phút, dùng 9B chấm lượt hai và xuất
`data/training/shinhan_bulk_shortlist.jsonl` riêng; đây vẫn chỉ là tập ứng viên
tự động, chưa phải mẫu duyệt tay. Bộ lọc loại câu hỏi mà đáp án cố định không
trả lời đủ. Trần hiện tại 90 câu cho mỗi fact card để giảm lặp cùng một ý.
Scheduled Task `Shinhan-Train-Candidate` kiểm tra mỗi 5 phút và chỉ tạo ứng
viên 2B khi có ít nhất 1.000 mẫu tổng cộng, trong đó tập bulk có ít nhất 900
mẫu và tăng ít nhất 500 mẫu so với ứng viên trước. Phải rà ít nhất 100 câu bulk
được lấy cân bằng theo chủ đề bằng `make_shinhan_bulk_audit_sample.py`, đánh dấu
từng câu đúng/sai, ghi số lỗi không quá 3 vào `shinhan_bulk_audit.json` gắn đúng
SHA-256 của shortlist. Nếu shortlist đổi thì audit cũ hết hiệu lực. Ba biến thể
đầu câu `Dạ`/`Vâng`/trung tính được phân bổ mà không đổi nội dung nghiệp vụ.
Các task
dùng chung khóa để không tranh GPU; ổ dự án phải còn ít nhất 11 GiB. Bộ train
không lấy thẳng `teacher_pass`. Mỗi ứng viên được chấm Shinhan, hội thoại tự
nhiên và bộ ca ngân hàng giả lập cũ; không tự đổi `OLLAMA_MODEL`. Log nằm tại
`logs/shinhan_train_cycle.log`. Hiện máy
ở chế độ dành riêng: app/backend :8100 và lịch mở app đã tắt; Qwen3.5-9B chạy
trong Ollama để tạo và chấm. Worker tự dừng nếu backend :8100 mở lại hoặc ổ
đĩa còn dưới 11 GiB. Không có lịch Codex hay API backend điều khiển job này.
Ngày 24/09, đã rà thêm 9 fact card từ PDF Shinhan và duyệt tay thêm 105 câu
hỏi/đáp khớp nguồn (`data/training/shinhan_review_decisions_3.json`), tổng
145 câu đủ điều kiện tạo ứng viên mới. Ứng viên
`shinhan-qwen35-2b-20260924-015747` đã train 131 câu, giữ 14 câu, 1 epoch;
đạt 6/6 ca Shinhan cơ bản, nhưng sau khi sửa bộ chấm và chấm lại nội dung đã
lưu chỉ còn 2/10 ca hội thoại tự nhiên, 3/7 ca ngân hàng giả lập. Có lời khẳng
định sai về mức lãi chắc chắn và lỗi xưng hô, nên **không đưa vào phục vụ**.
Các câu 9B tự chấm qua nhưng lủng củng, đảo vai hoặc hỏi ngoài đáp án tiếp tục
nằm ở hàng chờ, không được train.

Rà nguyên văn PDF sau lượt train phát hiện cụm “chức năng này” nói về chức năng
**Thanh toán thẻ**, không phải dịch vụ thanh toán tự động. Fact card chưa có mẫu
duyệt liên quan đã được thay bằng `pay_card_own_function`; các câu nháp thuộc
card cũ bị loại khi teacher khởi động lại. Bộ kiểm thử mới hỏi rõ phân biệt
Thanh toán thẻ với Chuyển khoản nội bộ. Đã dọn checkpoint trung gian của hai
adapter cũ, giữ adapter, để ổ dự án tăng từ sát 11 GiB lên khoảng 14,2 GiB.

`training/llm/shinhan_fact_miner.py` dùng chính 9B đọc tiếp 347 đoạn văn bản
trích từ 11 PDF có nhãn `review`, ưu tiên hướng dẫn thẻ. Nó chỉ lưu đề xuất
`fact_candidates` khi trích dẫn khớp nguyên văn với đoạn PDF và loại mức phí,
lãi suất, ngày tháng, khuyến mãi. Các đề xuất phải rà hiệu lực/ngữ cảnh trước
khi thêm vào 29 fact card đã xác minh; không tự biến thành dữ liệu train.

Mốc 100.000–1.000.000 câu là mục tiêu tích lũy dài hạn, không phải số mẫu đã
train. Với 29 fact card và trần 300 biến thể/fact, worker tối đa khoảng 8.700
câu thô; cần nhiều dữ kiện độc lập được xác minh từ tài liệu còn hiệu lực để
tăng quy mô mà không lặp câu hoặc huấn luyện sai nghiệp vụ.
Lịch task chạy 24/7 nhưng GPU chỉ bận khi còn công việc tạo/chấm/trích xuất
có ích; với nguồn hữu hạn, không thể cam kết GPU luôn 100% hoặc train 2B mãi.

## Log tiến độ

Worker lưu bản dễ đọc tại `logs/shinhan_training_progress_latest.txt`, bản
JSON tại `logs/shinhan_training_progress_latest.json`, và lịch sử định kỳ tại
`logs/shinhan_training_progress.jsonl`. Có thể xem ngay
bằng `C:\duan\chat-ai\.venv-train\Scripts\python.exe
C:\duan\chat-ai\training\llm\shinhan_progress.py`. Báo cáo tách câu thô,
câu chờ 9B chấm, câu 9B cho qua nhưng chưa rà nguồn, câu được duyệt để train,
khối lượng shortlist bulk lượt hai và câu thực sự dùng cập nhật 2B.
`remaining_to_configured_raw_cap_upper_bound`
là sức chứa cấu hình, không hứa sẽ có bấy nhiêu câu mới hữu ích. Các lượt train
Shinhan ghi vào `data/training/shinhan_train_runs.jsonl` sau khi adapter được
lưu. Kết quả kiểm tra là số **ca giữ riêng** trả lời đạt, không phải số câu
model đã nhớ; bản thử 2B hiện đạt 6/6 ca Shinhan, 2/10 ca hội thoại tự nhiên và
3/7 ca nghiệp vụ giả lập cũ, nên chưa qua cổng chất lượng. Chưa có lượt train
1.000 câu: cần đủ shortlist và audit đạt trước.
