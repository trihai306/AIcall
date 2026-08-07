---
name: nhin-man-win
description: Xem và thao tác MÀN HÌNH máy Windows admin-pc từ xa - chụp ảnh desktop, bấm chuột, gõ phím. Dùng skill này khi cần nhìn app VoiceBank (Electron) hoặc bất cứ cửa sổ native nào trên máy Windows, khi người dùng nói "xem màn hình bên win", "app đang hiện gì", "bấm hộ tôi nút đó", "chụp màn hình máy kia", "thao tác trên máy Windows", "xem giao diện app", "app có mở lên không", "nhìn desktop", hoặc khi cần kiểm chứng thứ mà browser tool không thấy được (cửa sổ app, hộp thoại Windows, khay hệ thống, màn hình khoá). Cũng dùng khi user nói view windows screen, remote desktop, screenshot the app, click on windows, control windows machine.
---

# Xem và thao tác màn hình máy Windows

Máy Windows `admin-pc` chạy app VoiceBank (Electron) và các cửa sổ native. **Không MCP
nào trong dự án nhìn được màn hình của nó** — mỗi cái thiếu một kiểu:

| MCP | vì sao không dùng được |
|---|---|
| `computer-use` | điều khiển màn hình **Mac**, không phải máy Windows |
| `electron` | chỉ dò `localhost:9222`; app trên Win không bật cổng gỡ lỗi |
| `Claude_Browser`, `playwright`, `claude-in-chrome` | chỉ thấy **trang web**, không thấy desktop hay cửa sổ native |
| AnyDesk / TeamViewer | xem được, nhưng qua cửa sổ trên Mac, chậm, và phụ thuộc người dùng đang mở sẵn phiên |

Skill này dùng `scripts/man_win.sh` — chụp và thao tác thẳng trên máy Windows qua SSH.

## Dùng thế nào

```bash
scripts/man_win.sh chup            # chụp màn, kéo về Mac, in đường dẫn -> Read ảnh đó
scripts/man_win.sh bam 330 236     # bấm trái
scripts/man_win.sh bam2 330 236    # bấm đúp
scripts/man_win.sh phai 330 236    # bấm phải
scripts/man_win.sh chuot 330 236   # chỉ di chuột (rê để hiện tooltip)
scripts/man_win.sh go "xin chao"   # gõ chữ vào ô đang focus
scripts/man_win.sh phim "{ENTER}"  # phím đặc biệt: {ENTER} {TAB} {ESC} ^a (Ctrl+A)
```

Quy trình: **chụp → Read ảnh → đọc toạ độ trên ảnh → bấm → chụp lại để xác nhận.**
Luôn chụp lại sau khi thao tác. Không có ảnh sau thì không biết cú bấm có trúng không.

## Khi nào KHÔNG dùng

Việc gì làm được bằng HTTP hoặc browser tool thì **đừng dùng skill này** — mỗi lần
chụp là ~1.2 MB kéo qua Tailscale và vài giây chờ tác vụ.

| Việc | Dùng cái này thay vì |
|---|---|
| Kiểm dịch vụ sống chưa | `curl http://127.0.0.1:8100/api/health` |
| Bấm nút trong giao diện web | `test-web-win` (browser tool, có `read_page` thấy được `ref`) |
| Đọc log | `ssh win 'Get-Content ... -Tail 40'` |
| Kiểm tiến trình | `ssh win 'Get-CimInstance Win32_Process ...'` |

Chỉ dùng khi thứ cần nhìn **nằm ngoài trang web**: cửa sổ Electron, hộp thoại Windows,
khay hệ thống, trạng thái đăng nhập, hoặc khi nghi app không mở lên được.

## Bốn cái bẫy — đều đã mắc thật

**1. Phiên SSH không có màn hình.** Chạy thẳng `CopyFromScreen` qua SSH báo
`The handle is invalid`, vì SSH trên Windows chạy ở **Session 0** — phiên dịch vụ,
không có desktop nào. `query session` cho thấy desktop thật là Session 1 (`console`,
Active). Script đẩy lệnh sang phiên đó bằng `schtasks /it`. **Đừng sửa script để chạy
trực tiếp** — nó sẽ hỏng đúng chỗ này.

**2. Toạ độ lệch khi ảnh bị thu nhỏ.** Bản đầu thu ảnh về 1600px cho nhẹ; màn thật
1920x1080 nên mọi cú bấm lệch 1.2 lần và **trượt không báo gì**. Giờ chụp nguyên
kích thước, toạ độ khớp 1:1. Đừng bật lại thu nhỏ.

**3. Đọc `VirtualScreen` qua SSH cho số SAI.** Session 0 báo 1024x768 trong khi màn
thật 1920x1080. Muốn biết kích thước thật thì **đọc từ chính ảnh đã chụp**, đừng hỏi
qua SSH.

**4. Đọc kết quả quá sớm.** Chụp màn mất hơn 1.5 giây; ngủ cố định rồi đọc sẽ ra kết
quả của **lần chạy trước** — nó in "1600x900" trong khi ảnh vừa chụp là 1920x1080, và
làm lấy nhầm toạ độ. Script giờ chờ tệp kết quả thật sự đổi. Nếu thấy số lạ, nghi
chỗ này trước.

## Bảng chẩn đoán

| Triệu chứng | Nguyên nhân |
|---|---|
| `The handle is invalid` | Đang chạy ở Session 0 — phải qua `schtasks /it` |
| Ảnh đen thui | Máy đang khoá màn hình. Windows không cho chụp, không phải lỗi script |
| Bấm không trúng | Toạ độ lấy từ ảnh cũ, hoặc cửa sổ đã dịch chuyển. Chụp lại rồi lấy toạ độ mới |
| Cửa sổ PowerShell hiện lên che app | Thiếu `-WindowStyle Hidden` trong lệnh tác vụ |
| Chữ tiếng Việt gõ ra sai dấu | Tham số phải đi qua tệp mã base64, không truyền thẳng qua SSH |
| `schtasks` báo tạo được nhưng không chạy gì | Sai tên user ở `/ru` — phải là `Admin` (xem `query session`) |

## Ba tệp liên quan

| tệp | việc |
|---|---|
| `scripts/man_win.sh` | vỏ bọc trên Mac — tạo tác vụ, ghi lệnh, kéo ảnh về |
| `scripts/tac_vu_man.ps1` | bộ điều phối chạy trong Session 1, đọc lệnh từ tệp |
| `scripts/chup_man_win.ps1`, `scripts/dieu_khien_man_win.ps1` | chụp màn / bấm-gõ |

Lệnh truyền qua **tệp** chứ không qua tham số `schtasks /tr`: đường kia là bốn tầng
trích dẫn lồng nhau (bash → ssh → schtasks → powershell) và hỏng ngay lần đầu.
