---
name: gui-file-nghe
description: Dùng khi cần người dùng NGHE một file audio (TTS, bản ghi cuộc gọi, giọng mẫu) - họ nói "cho tôi nghe", "gửi file nghe", "nghe thử", "nghe trên điện thoại", "file đó nghe thế nào", "bản nào nghe rõ hơn", "bản nào hay hơn", "so sánh hai giọng", "chọn giữa hai bản", "đánh giá giọng này", hoặc send me the audio, let me hear it, listen to this. ĐẶC BIỆT dùng khi bạn sắp đo RMS, SNR, phổ tần, spectral centroid, thời lượng hay CER để tự kết luận giọng nào "rõ hơn", "mượt hơn", "sạch hơn" - số đo KHÔNG thay được tai người và hai lần đo khác nhau đã cho hai kết luận ngược nhau.
---

# Gửi file audio cho người dùng nghe trên điện thoại

## Cốt lõi

**Bạn không nghe được.** Mọi kết luận về chất lượng giọng — rè, méo, ngắt quãng, sai chữ, ngữ điệu — đều phải do người dùng nghe rồi phán. Skill này là đường đưa file tới tai họ; nó không thay được việc hỏi.

Máy Mac chạy sẵn một trang nghe. iPhone của người dùng đã ở trong Tailscale nên vào được mọi lúc, không cần chung Wi-Fi.

## Cách dùng

```bash
# File trên máy Windows (đường dẫn bắt đầu bằng C:/)
scripts/gui_nghe.sh 'C:/duan/chat-ai/tmp_la.wav' "giọng A, nfe 12, tốc 0.90"

# File trên máy Mac
scripts/gui_nghe.sh ./ket_qua.wav "bản gốc chưa nén"
```

Rồi đưa người dùng link: **http://100.64.195.48:8123**

## Nhãn là bắt buộc, không phải tuỳ chọn

Bỏ trống nhãn thì trang chỉ hiện tên file, người dùng mở lên không biết đang nghe cái gì. Nhãn phải ghi **thứ đang đem ra so** — giọng nào, nfe bao nhiêu, tốc mấy, sửa gì:

| Tệ | Được |
|---|---|
| `"test"` | `"giọng B, nfe 16, tốc 0.90"` |
| `"file mới"` | `"sau khi bỏ dấu ... ở cuối"` |
| `"wav 1"`, `"wav 2"` | `"A: chưa gộp mảnh"` / `"B: đã gộp mảnh"` |

Đối chứng thì gửi **cả hai bản trong cùng một lượt**, nhãn A/B rõ ràng — nghe một bản rồi đoán là cách chắc chắn nhận nhầm.

## Hỏi cho đúng cách

Đừng hỏi trống "anh nghe thử xem". Nói rõ **nghe cái gì, ở giây thứ mấy**:

> Đã gửi 2 bản, anh mở http://100.64.195.48:8123
> - **A** giọng cũ · **B** đã tăng tuần hoàn
> Anh nghe giúp quãng "ba trăm sáu mươi triệu" ở giây thứ 4 — B có bớt kim loại hơn A không?

Rồi **dừng lại chờ**. Không được viết tiếp kiểu "chắc là ổn rồi" hay "bản B nghe sẽ mượt hơn" — bạn chưa nghe, đó là bịa.

## Khi người dùng bảo không vào được

Kiểm theo thứ tự này:

```bash
launchctl list | grep nghe                       # còn chạy không
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/   # phải là 200
tail -5 logs/may_chu_nghe.log                    # địa chỉ thật đang phục vụ
launchctl kickstart -k gui/$(id -u)/com.hainc.nghe   # dựng lại
```

Nếu địa chỉ Tailscale trong log khác `100.64.195.48` thì đưa địa chỉ trong log, đừng đưa số nhớ sẵn. Người dùng ra khỏi nhà thì **iPhone phải bật Tailscale** mới vào được; ở nhà thì địa chỉ Wi-Fi trong log cũng dùng được.

## Lỗi hay mắc

| Lỗi | Hậu quả |
|---|---|
| Tự kết luận "giọng đã mượt hơn" | Bịa. Bạn không nghe được. Chỉ người dùng phán được. |
| Gửi 1 bản rồi hỏi "có hay không" | Không có mốc so, câu trả lời vô nghĩa. Gửi cặp A/B. |
| Nhãn trống hoặc `"test"` | Người dùng mở lên không biết đang nghe gì. |
| Chép tay file vào `nghe/` | Mất nhãn và mất dấu thời gian. Luôn qua `gui_nghe.sh`. |
| `git add nghe/` | Đã chặn trong `.gitignore`. Đừng ép thêm vào. |
| Gửi xong nói tiếp luôn | Phải dừng chờ người dùng nghe rồi mới đi tiếp. |

## Số đo không thay được tai

Đo RMS, SNR, spectral centroid, tỉ lệ năng lượng 1–4kHz… đều **không** trả lời được "bản nào nghe rõ hơn". Đã thử: hai agent phân tích cùng một cặp file bằng cùng bộ chỉ số, một bên kết luận nfe16 thắng, bên kia kết luận nfe12 thắng. Số đo chỉ dùng để **khoanh vùng chỗ đáng nghe** ("giây thứ 4 có đỉnh lạ, anh nghe chỗ đó giúp"), không dùng để phán.

## Khi giao việc cho agent con

Agent con **không nhận được description của skill**, nó chỉ thấy mỗi cái tên. Nên khi giao việc dính tới audio, phải bảo thẳng trong lời giao:

> Dùng skill "gui-file-nghe" rồi làm việc sau: …

Không nói thì nó sẽ ngồi đo phổ rồi tự phán — đã kiểm chứng hai lần, lần nào cũng vậy.

## Ai lo phần nào

- `scripts/gui_nghe.sh` — kéo file (từ Win qua `ssh win`, hoặc Mac), đặt tên theo giờ, ghi nhãn ra file `.txt` kèm
- `scripts/may_chu_nghe.py` — trang nghe, mới nhất trên cùng, chạy nền qua launchd (`com.hainc.nghe`), tự dựng lại khi chết
- `nghe/` — chỗ chứa, ngoài git

Trang **không tự tải lại** khi có file mới, chỉ hiện nút "có file mới" — cố ý, vì tải lại giữa chừng là đứt tiếng đang nghe.
