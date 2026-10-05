# Thư viện trả lời tự động

Qwen chuẩn bị các câu trả lời có căn cứ trước khi phục vụ khách. F5 dựng WAV
cho từng đáp án. Trong hội thoại, AI hiểu ý khách và ngữ cảnh, kiểm tra nội
dung các đáp án rồi chọn một đáp án phù hợp để phát nguyên chữ cùng voice.
Ví dụ lời khách chỉ hỗ trợ tìm kiếm; khách không cần nói giống ví dụ. Câu
chưa có đáp án phù hợp vẫn đi qua luồng tra tài liệu hiện tại.

## Sử dụng

Mở **Tri thức AI → Thư viện trả lời tự động**. Bật **Bật chuẩn bị tự động** để
hệ thống cập nhật khi máy rảnh. Thiết lập mặc định là 120 câu trả lời mục tiêu mỗi
tài liệu và tối đa 4 ví dụ lời khách hỗ trợ cho mỗi đáp án. Ví dụ không bắt buộc. Đây là mục tiêu; số câu được
chấp nhận phụ thuộc nội dung nguồn, kiểm tra và khử trùng.

**Tạo / cập nhật thư viện** bổ sung phần chưa chuẩn bị. **Tạo lại toàn bộ**
yêu cầu chuẩn bị lại theo cấu hình hiện tại. **Dừng** dừng tác vụ đang chạy.
Tắt chuẩn bị tự động dừng việc xây kho ở nền; các đáp án còn hợp lệ vẫn dùng
được trong hội thoại.

Bảng hiển thị số đáp án, số ví dụ hỗ trợ, ý học từ lịch sử và số voice sẵn sàng.
Đọc trạng thái và nhật ký khi model hoặc voice chưa sẵn sàng. Không coi số
đáp án đã tạo là số voice đã dựng.

## Sửa và thêm câu trả lời

Bấm **Quản lý câu trả lời** trong thư viện rồi chọn tài liệu, hoặc bấm
**Q&A + voice** ở dòng tài liệu cần sửa. Có thể tìm câu hỏi hoặc nội dung
đáp án trong ô tìm kiếm; danh sách chia trang khi có nhiều câu.

**Thêm câu trả lời** chỉ cần nhập đáp án muốn AI sử dụng. Có thể mở phần
**Ví dụ lời khách (không bắt buộc)** để nhập thêm ví dụ, mỗi dòng một câu. Bấm **Sửa** ở một câu đã có để đổi đáp án, ví dụ lời khách hoặc
trạng thái bật/tắt, rồi **Lưu**. Các câu bạn nhập hoặc sửa được ghi rõ trong
danh sách và được giữ khi AI tạo bổ sung hoặc tạo lại thư viện. Nếu người
khác đã sửa cùng câu, giao diện giữ bản đang soạn để bạn đối chiếu với bản mới.

Sau khi lưu nội dung, hệ thống cập nhật kho trả lời và xếp lịch dựng voice
F5 mới. **Voice chưa sẵn sàng** nghĩa là nội dung đã lưu nhưng WAV mới đang
chờ xử lý; giao diện tự cập nhật khi voice hoàn tất. Việc dựng voice cho câu
đã lưu vẫn hoạt động khi tắt chuẩn bị hỏi–đáp tự động.

**AI tạo thêm** yêu cầu Qwen đọc tài liệu và bổ sung đáp án cho những nội
dung chưa được phủ. Mục tiêu là các đáp án khác nội dung, mỗi đáp án dùng
được cho nhiều cách diễn đạt cùng ý của khách.
Có thể yêu cầu từ 1 đến 300 đáp án trong một lượt; mặc định 24. Các câu đang
có được giữ lại. Số được thêm có thể ít hơn yêu cầu nếu nguồn không đủ ý mới
hoặc câu chưa qua kiểm tra. Để mở rộng tự động nhiều hơn, tăng **Câu trả lời mục
tiêu mỗi tài liệu** lên tối đa 300.

Nếu chỉ có câu hỏi thực tế và muốn AI soạn đáp án, mở phần câu hỏi nhân viên,
dán mỗi câu một dòng rồi bấm **AI trả lời các câu hỏi này**. Khi tài liệu nguồn
đổi, các đáp án từ bản cũ được tạm tắt; câu nhập tay cần được xem lại và lưu
theo tài liệu mới trước khi bật dùng tiếp.

## Bộ nghiệp vụ ngân hàng cơ bản và lời thoại

Đã thêm bộ **Nghiệp vụ ngân hàng cơ bản & lời thoại** vào nhóm Shinhan,
gồm 60 đáp án: 20 câu giao tiếp cuộc gọi và 40 câu về tài khoản/thẻ,
chuyển khoản/giao dịch, bảo mật, ứng dụng/dịch vụ, tín dụng/vay/tiền gửi.
Đây là lời thoại biên soạn chung, có ghi rõ xuất xứ; các điều khoản, phí,
lãi suất, hạn mức và kết quả riêng vẫn cần căn cứ chính thức. Bộ này không
xác nhận đã tra cứu hoặc thực hiện thao tác trên tài khoản khách.

Mở **Xem & sửa câu trả lời**, chọn **Shinhan · Nghiệp vụ ngân hàng cơ bản
& lời thoại**. Các đáp án có thể sửa, tắt hoặc bổ sung bằng giao diện hiện
có. Cả 60 đáp án đã bật và có hai biến thể voice F5 hợp lệ trên Windows.
Mỗi mục có 0 ví dụ lời khách; lựa chọn dựa trên nội dung đáp án. Quy tắc
cuộc gọi đang có vẫn được ưu tiên, ví dụ tình huống khách đang bận.

Bản JSON để tái sử dụng nằm ở
`data/templates/nghiep_vu_ngan_hang_co_ban.json`; nguồn biên soạn nằm ở
`knowledge/shinhan/nghiep_vu_co_ban_va_loi_thoai.md`. Script
`scripts/import_basic_banking_pack.py` nhập qua API thêm/sửa đang có,
kiểm tra nội dung, trạng thái, ví dụ và nguồn nhập tay ở lần đọc cuối.
Chạy lại giữ nguyên ID; nội dung nguồn hoặc đáp án đã được người vận hành
đổi sẽ được giữ và báo cần đối chiếu.

Đã kiểm tra Qwen thật chọn đúng đáp án cho ba yêu cầu về tài khoản/thẻ,
số dư khả dụng, tiền gốc/lãi, và một yêu cầu giải thích dễ hiểu hơn chưa
có chủ đề trước đó. Lượt có voice phát cache F5, nhận 431.564 byte audio,
TTFA 493 ms trong lần chạy trên Windows/CUDA. Câu giải thích đã được rút
gọn sau thử nghiệm để hỏi lại đúng phần khách chưa rõ, giữ nguyên các
ngưỡng và cổng kiểm tra của bộ chọn. 60 ID được giữ qua lần cập nhật nguồn;
nhập lại không tạo thêm bản sao. Cấu hình tự động 300 câu/tài liệu, 1 ví dụ
và học lịch sử đã được khôi phục. Các thử nghiệm này dùng WebSocket;
chưa xác nhận cuộc gọi SIM thật cho bộ mới.

Xem [kết quả nhập bộ 60 câu](basic_banking_pack_windows_20261001.json),
[chọn đáp án và phát voice](basic_banking_pack_live_20261001.json) và
[giao diện](basic_banking_pack_windows_20261001.png).

## Trí nhớ và căn cứ

### Dùng trong chat và điện thoại

Trang **Nhắn tin** và **Hội thoại** có mục chọn **Kịch bản**. Chọn đúng tổ
chức và sản phẩm đang tư vấn để dùng cùng phạm vi kiến thức với cuộc gọi.
Đổi kịch bản bắt đầu lịch sử mới, xóa bản đoán trước và căn cứ của kịch bản
cũ. Nút gửi/micro chờ máy chủ xác nhận cấu hình trước khi nhận lượt khách.

Chat chữ, chat giọng, cuộc gọi ra và cuộc gọi đến dùng chung pipeline: xử lý
hồ sơ/phép tính xác định, tìm đáp án trong kho, nhờ Qwen chọn khi cần hiểu ý
khách, rồi phát đáp án đã lưu và voice F5 đã chuẩn bị. Không có đáp án phù
hợp thì tra tài liệu và sinh câu trả lời qua các bộ kiểm tra hiện tại.
Mỗi lượt có `answer_route` trong số đo và báo cáo, gồm nguồn trả lời,
model đã chọn, mã đáp án và file nguồn. `/api/devices/voice/status` cũng trả
dấu vết này cho cuộc gọi đang chạy.

Model được chọn riêng cho từng yêu cầu, giữ nguyên model của các cuộc gọi
khác. Mặc định bộ chọn dùng `qwen3.5:9b`; phần sinh câu mới dùng model
production. Nếu model của vai trò chưa cài thì dùng production hoặc các
fallback được khai rõ. Các model thử nghiệm có trên máy không tự trở thành
model phục vụ khách. Cấu hình: `LLM_AUTO_ROUTING`, `LLM_SELECTOR_MODEL`,
`LLM_RESPONSE_MODEL`, `LLM_FALLBACK_MODELS` (danh sách cách nhau bằng dấu phẩy).

Để thử gọi vào, nối điện thoại ADB với Windows, chọn kịch bản nhận cuộc gọi
ở **Thiết bị** và bật **Tự nhận cuộc gọi**. Kiểm thử qua WebSocket với audio
mô phỏng băng thông điện thoại xác nhận STT/Qwen/F5; cuộc gọi SIM thật còn
cần xác nhận trên điện thoại đã kết nối. Script kiểm tra loopback:
`scripts/verify_answer_routing_win.py --scenario-id <mã-kịch-bản-Shinhan>`.

Kịch bản **Tư vấn Shinhan — kho câu trả lời** (`sc_cfa532b8`) đã được tạo trên
Windows và gắn cho chế độ nhận cuộc gọi của S9+ mặc định. Kho và luồng tra
tài liệu của kịch bản này được giới hạn theo Shinhan; đường lấy toàn bộ tài
liệu sản phẩm demo không được dùng trong kịch bản ngân hàng khác hoặc có
`knowledge_tag`. Các tài liệu ABC demo vẫn thuộc kịch bản mặc định của chúng.

Hệ thống đọc câu hỏi **của khách** trong các phiên đã kết thúc để tìm ý hỏi
chung còn thiếu. Câu trả lời cũ của AI không trở thành nguồn kiến thức. Tên,
thông tin liên lạc, mã tài khoản và giá trị cá nhân được lọc trước khi xử lý.
Các câu hỏi về hồ sơ riêng tiếp tục dùng dữ liệu riêng trong phiên.

Đáp án tự tạo phải có trích dẫn từ tài liệu hiện tại, qua kiểm tra chữ số,
phong cách và kiểm tra nội dung trước khi được đưa vào kho. Đổi hoặc xóa tài
liệu làm đáp án từ bản cũ ngừng được chọn. Phạm vi ngân hàng và sản phẩm được
kiểm tra khi chọn câu trả lời.

Đây là mở rộng dữ liệu hỏi–đáp và cache voice, không phải huấn luyện lại trọng
số Qwen. Model lấy từ cấu hình đang chạy, mặc định `qwen3.5:9b`.

## Tác vụ nền

Bộ chuẩn bị chạy tuần tự, chờ khi có lượt khách hoặc tác vụ huấn luyện đang
dùng tài nguyên. Tiến độ và dữ liệu đã kiểm tra được lưu trong SQLite để
tiếp tục sau khi khởi động lại. Voice dùng kho `data/tieng_san`, gắn với chữ,
giọng và cấu hình F5 hiện tại.

Các endpoint nằm dưới `/api/knowledge/thu-vien-tu-dong`: `GET` đọc trạng thái,
`POST` lưu cấu hình, `POST /build` yêu cầu cập nhật và `POST /cancel` dừng tác
vụ. Không cần khởi động lại sau khi đổi cấu hình qua giao diện.

## Voice chuẩn bị sẵn

Mỗi đáp án có hai biến thể voice độc lập: `hd_<id>` cho câu trả lời đầy đủ và
`hd_<id>_noi_dem` cho phần nối tiếp sau lời đệm. Chỉ xem voice là sẵn sàng khi
cả hai biến thể đều tồn tại và khớp với nội dung hiện tại, giọng F5 hiện tại
và dấu vân tay cấu hình F5 hiện tại. Nếu một trong các yếu tố này đổi, cần
dựng lại biến thể tương ứng trước khi coi voice đã sẵn sàng.

## Xác nhận Windows (01/10/2026)

Đã xác nhận trên Windows với Python 3.11.15, torch 2.11.0+cu128, CUDA 12.8,
NVIDIA GeForce RTX 5070 11.9 GB, model `qwen3.5:9b`, checkpoint F5
`giong_nam` (`./models/tts/finetuned/giong_nam/model_last.pt`) và giọng tham
chiếu `heu_a6_35` (`./models/tts/ref_voices/heu_a6_35.wav`).
Kho hỏi–đáp có nguồn được tạo bằng Qwen/F5 thật, còn dùng được sau khi khởi
động lại dịch vụ. Bằng chứng chạy thực tế ghi nhận một mục được chọn với
`rag_ms=0` và `llm_ttft_ms=0`; hai biến thể cache voice đã phát lại thành công.
Thời gian TTFA ghi nhận là 419 ms cho biến thể nối tiếp và 492 ms cho câu đầy
đủ. Đây là xác nhận chức năng trên một phiên chạy, không phải benchmark hiệu
năng production.

Trong một lần thử khác, khi Qwen đang tạo đáp án cho `faq/faq_banking.md`,
tác vụ nền chuyển sang chờ khách sau 259,4 ms; lượt khách vẫn chọn đáp án từ
kho và phát cache F5 (`rag_ms=0`, `llm_ttft_ms=0`, 728 ms xử lý / 908,8 ms
WebSocket), kết quả thử đạt. Xem [bằng chứng chạy thật](answer_bank_windows_live_20261001.json)
và [bằng chứng tạm dừng khi có khách](answer_bank_windows_preemption_20261001.json).

Kiểm tra pytest Windows đã có: 194 passed, 1 deselected.
`tests/test_spec_vector_cache.py::test_phan_loai_dong_bo_dung_lai_vector_spec`
được loại khỏi lượt chạy vì lỗi baseline đã tái hiện trước đó (`session.tinh_huong`
là `None`).

Cấu hình giao diện khi kiểm tra là 120 câu mục tiêu mỗi tài liệu, 4 cách hỏi
mỗi đáp án và bật học từ lịch sử. Tác vụ mở rộng đã bắt đầu; tổng số tài liệu
và đáp án còn thay đổi nên chưa xác nhận hoàn tất mục tiêu. FAQ demo được dùng
cho QA chức năng, không đại diện chính sách ngân hàng đã được xác thực. Bốn
tài liệu ABC demo đang hiện trong giao diện cần được thay bằng tài liệu thật
trước khi tiếp nhận cuộc gọi trực tiếp.

Kiểm tra Qwen 9B, F5, CUDA và tốc độ phản hồi thực tế phải chạy trên máy có
đầy đủ model; các kiểm tra dùng model giả chỉ xác nhận logic điều phối.

### Sửa và thêm đáp án trên Windows

Lượt kiểm tra mở rộng đạt **217 passed, 1 deselected** với cùng test baseline
được loại như trên. Đã thao tác giao diện thật để thêm đáp án nhập tay, sửa
đáp án AI vừa tạo và sửa lại đáp án nhập tay. Hai mục giữ nguyên ID và các
cách hỏi; nội dung chỉnh sửa được lưu đúng, voice cũ mất trạng thái sẵn sàng
và F5 dựng lại cả hai biến thể cho chữ mới.

Với tài liệu hỗ trợ dùng riêng cho QA, yêu cầu bổ sung 8 đáp án tạo thêm
1 đáp án qua kiểm tra, giữ nguyên đáp án nhập tay. Giao diện báo đúng **1/8**.
Kiểm tra WebSocket chọn đúng mục vừa sửa, trả đúng chữ mới và phát cache F5,
với `rag_ms=0`, `llm_ttft_ms=0` và 131.084 byte audio. Lưu với phiên bản cũ
bị từ chối bằng HTTP 409. Console không có lỗi JavaScript mới.

Theo dõi health trên chính Windows trong 180 giây khi thao tác thư viện
không ghi nhận request lỗi. Cập nhật đáp án dùng lại vector của cách hỏi
không đổi; vòng chờ voice không tính lại toàn bộ kho.

Tài liệu và phiên QA đã được dọn. Đã bật chuẩn bị tự động, học câu hỏi khách,
4 cách hỏi mỗi đáp án và mục tiêu **300 ý hỏi mỗi tài liệu**. Sau QA, kho có
252 đáp án cùng 252 voice sẵn sàng; tác vụ mở rộng đã bắt đầu. Đây là trạng
thái tại thời điểm kiểm tra, chưa xác nhận đủ 300 ý hỏi cho mọi tài liệu.
Xem [bằng chứng editor trên Windows](answer_bank_editor_windows_live_20261001.json)
và [giao diện chỉnh sửa](answer_bank_editor_windows_20261001.png).

### Chọn theo nội dung đáp án, ví dụ lời khách tùy chọn

Đã triển khai và kiểm tra bản tập trung vào đáp án trên cùng máy Windows.
Kho được quản lý (`ab_*`) lập chỉ mục nội dung trả lời đầy đủ cùng các ví dụ
tùy chọn. Qwen đọc chính nội dung đáp án để xác nhận một lựa chọn, kể cả khi
lời khách trùng ví dụ; điểm vector chỉ dùng tìm ứng viên. Không có đáp án đủ
phù hợp thì giữ luồng tra tài liệu. Kho cũ giữ hợp đồng tương thích.

Đã thêm qua giao diện một đáp án có **0 ví dụ lời khách**. Ba cách diễn đạt
chưa lưu đều được Qwen chọn về đúng ID và trả nguyên chữ đã chuẩn bị, với
`rag_ms=0` và bằng chứng `bang_chon_qwen`. Lượt có voice phát cache F5 nối
tiếp, nhận 199.244 byte audio. Câu hỏi nấu ăn ngoài chủ đề không chọn kho.
Kết quả vẫn đúng sau khi bổ sung thêm các đáp án khác vào cùng tài liệu.
Đây là thử nghiệm chức năng qua WebSocket với đầu vào văn bản; không phải
kiểm tra nhận dạng giọng nói hoặc cuộc gọi điện thoại trực tiếp.

Qua nút **AI tạo thêm**, yêu cầu 8 đáp án bổ sung được 4 đáp án qua kiểm tra
nguồn, giữ nguyên ID, nội dung và trạng thái đáp án nhập tay. Cả 5 mục có voice
sẵn sàng. Ví dụ lời khách không còn là điều kiện tối thiểu để chấp nhận đáp án
tự tạo. Khi đang nhường tài nguyên cho khách, giao diện hiển thị lý do và thời
gian chờ thay vì chỉ yêu cầu thử lại. Lỗi bỏ hết ví dụ trên dòng cũ cũng báo
cách xử lý và giữ bản đang soạn.

Lượt pytest Windows đạt **245 passed, 1 deselected**; cùng test baseline được
loại như trên. Kiểm tra cú pháp Python/JavaScript và rà soát độc lập đạt.
Vector cho chữ không đổi được dùng lại; sửa nội dung đáp án chỉ tính lại phần
chữ thay đổi. Kho, vector và nguồn được cập nhật cùng một bản chụp dữ liệu.

Đã dọn tài liệu và hai phiên thử riêng. Đã bật lại chuẩn bị tự động với mục
tiêu **300 đáp án mỗi tài liệu**, tối đa 1 ví dụ hỗ trợ mỗi đáp án mới và bổ sung
ý khách còn thiếu. Sau khi dọn, kho có 240 đáp án/240 voice; tác vụ mới đang
chuẩn bị FAQ. Số lượng sẽ thay đổi và phụ thuộc nguồn; chưa xác nhận đủ 300.

Xem [chọn đáp án không có ví dụ](answer_bank_answer_first_windows_live_20261001.json),
[thử sau khi mở rộng kho](answer_bank_answer_first_windows_expanded_20261001.json),
[tạo bổ sung](answer_bank_answer_first_windows_append_20261001.json),
[trạng thái Windows](answer_bank_answer_first_windows_final_20261001.json) và
[giao diện nhập đáp án](answer_bank_answer_first_windows_saved_20261001.png).

### Giao diện kho câu trả lời dễ dùng hơn

Trang **Tri thức AI** đưa kho đáp án và giọng đọc lên trước. Bấm **Xem & sửa
câu trả lời**, chọn tài liệu rồi tìm nội dung bằng từ khóa có dấu hoặc không
dấu. Các bộ lọc giúp xem câu đã chỉnh tay, câu chờ giọng và câu đã tắt.

Bấm **+ Thêm câu trả lời** hoặc **Sửa**, nhập phần **Nội dung khách sẽ nghe**
rồi **Lưu câu trả lời**. Ví dụ lời khách nằm trong phần thu gọn và có thể để
trống. Trên màn hình rộng, danh sách và ô sửa nằm cạnh nhau. Khi có bản nháp,
hộp thoại trong trang cho chọn **Tiếp tục sửa** hoặc **Bỏ thay đổi**. Có thể
lưu bằng Ctrl/Cmd+S.

Để bổ sung cho tài liệu đang chọn, bấm **AI tạo thêm**, chọn nhanh 12/24/50/100
hoặc nhập số từ 1 đến 300, rồi **Bắt đầu tạo**. Kết quả báo số thực tế đã thêm
và giữ các câu cũ; giọng đọc được tạo tiếp. **AI bổ sung cả kho** trên trang
chính chạy cho toàn bộ tài liệu. Thiết lập tự động, nhật ký và tài liệu nguồn
được thu gọn; có nút **Lưu thiết lập** khi thay đổi các lựa chọn.

Đã kiểm tra lưu/sửa không có ví dụ, tìm không dấu, các bộ lọc và lưu nhanh
qua web Windows/CUDA. Kiểm tra tiếp trên Electron Windows xác nhận hộp thoại
bảo vệ bản nháp giữ đúng chữ khi chọn tiếp tục sửa, bỏ nháp quay lại danh sách,
nút chọn nhanh 100 cập nhật đúng số lượng, và Qwen bổ sung **8/8 đáp án** cho
tài liệu QA riêng. ID, nội dung và trạng thái câu nhập tay được giữ nguyên;
cả **9 câu có giọng F5 sẵn sàng**. Đây là QA chức năng giao diện, không phải
đánh giá độ chính xác nghiệp vụ của mọi đáp án AI sinh ra.

Xem [báo cáo giao diện Windows](answer_bank_ui_windows_20261001.json),
[hộp thoại giữ bản nháp](answer_bank_ui_draft_20261001.png) và
[kết quả bổ sung đáp án](answer_bank_ui_added_20261001.png).

Đã kiểm tra thêm ô sửa ở chiều rộng 375px: chỉ hiện biểu mẫu, nút quay lại
khôi phục danh sách, không tràn ngang. Browser cuối đã kết nối, có mã phiên
và không có lỗi console mới. Kho nhớ tài liệu Shinhan khi đóng rồi mở lại.
Tài liệu QA và 9 mục thử đã được dọn; bật lại tự động với mục tiêu 300 đáp án,
1 ví dụ hỗ trợ và học lịch sử. Tác vụ lịch sử từng gặp lỗi JSON Qwen và đã có
lần thử tiếp hoàn tất; số lượng kho tiếp tục thay đổi. Chưa xác nhận đủ
300 đáp án cho mọi tài liệu.

### Tự chọn model và đáp án trong chat/cuộc gọi

Bản tích hợp đã được đồng bộ chọn lọc và khởi động lại trên Windows/CUDA.
15 file code/test/script khớp SHA-256 giữa hai máy. Bộ test liên quan đạt
**107 passed, 1 deselected**; case baseline nêu trên vẫn được loại. Ca kiểm
tra nội dung đáp án dài dùng context cố định 8192 để độc lập với cấu hình
triển khai; Windows vẫn giữ context 4096 và từ chối chọn khi prompt vượt
ngân sách, không cắt mất điều kiện cuối đáp án.

Ba lượt WebSocket với model thật đều chọn cùng đáp án từ
`shinhan/shinhan_card_user_guide_vi.md`: câu hỏi gốc về bật/tắt giao dịch thẻ
quốc tế, cách hỏi khác về dùng thẻ ở nước ngoài, và audio F5 qua bộ lọc điện
thoại rồi nhận dạng bằng Gipformer. STT nghe “Shinhan” thành “xi nhan” nhưng
Qwen vẫn chọn đúng đáp án theo ngữ cảnh. Chat chữ hoàn tất trong 503/378 ms;
lượt audio có TTFA 433 ms và nhận 186.764 byte voice F5 đã chuẩn bị. Đây là
số đo chức năng tại Windows trong lượt chạy này, không phải cam kết độ trễ.

Đã gửi cách hỏi khác qua trang **Nhắn tin** thật: giao diện hiện nguồn thư
viện, model `qwen3.5:9b`, đúng ID/tệp và lý do “AI chọn câu phù hợp”; console
không có lỗi/cảnh báo. Trang **Hội thoại** áp dụng kịch bản Shinhan và bật
micro sau khi máy chủ xác nhận cấu hình.

S9+ mặc định (`21f10e44220c7ece`) đã bật tự nhận cuộc gọi sau 2 giây với kịch
bản `sc_cfa532b8`. Watcher đang chạy, nhưng ADB chưa thấy điện thoại và chưa
có cuộc gọi SIM thật. Người dùng sẽ nối điện thoại vào Windows và gọi vào
thử; kết quả loopback không xác nhận đường tiếng vật lý của cuộc gọi SIM.

Xem [báo cáo kiểm tra](answer_routing_windows_tests_20261001.json),
[ba lượt model thật](answer_routing_live_windows_20261001.json),
[trạng thái nhận cuộc gọi](answer_routing_inbound_ready_20261001.json) và
[giao diện chat](answer_routing_chat_windows_20261001.png).
