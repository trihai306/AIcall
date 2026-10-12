# Trò chuyện thử với AI tư vấn, 09-10-2026

Chạy trên backend thật ở máy Win (chế độ kết hợp: luật + kho trước, kho không có thì Qwen 9B viết).
Mỗi cuộc là một phiên liền mạch, lời khách do Claude đóng vai và gõ từng lượt theo câu AI vừa đáp.
Cột "Nguồn" là phần nào của hệ thống đã trả lời.

## Cuộc 1: vay tín chấp (khách đi làm, lương 15 triệu, cần 200 triệu sửa nhà)

| # | Khách | AI | Nguồn | Đánh giá |
|---|---|---|---|---|
| 1 | a lô em ơi cho anh hỏi tí | Dạ anh chị cứ hỏi thoải mái ạ. Em xin nghe và giải thích lại cho rõ hơn ạ. Anh chị dự định vay khoảng bao nhiêu ạ? | kho (0.53s) | Được |
| 2 | anh đang cần ít tiền sửa nhà, bên em cho vay lãi suất thế nào | Dạ, lãi suất từ 7.9%/năm, hạn mức lên đến 500 triệu, thời hạn 12-60 tháng và giải ngân trong vòng 24 giờ ạ. | kho (0.49s) | Được |
| 3 | anh tính vay khoảng hai trăm triệu | Dạ 200 triệu đồng nằm trong hạn mức tối đa 500 triệu đồng của gói, hạn mức thực tế vẫn cần thẩm định theo hồ sơ ạ. Anh chị muốn vay trong bao lâu ạ? | luật (0.0s) | Được |
| 4 | chắc ba năm, thế mỗi tháng anh phải trả bao nhiêu | Dạ nếu được duyệt 200 triệu đồng trong 36 tháng, tạm tính theo lãi suất từ 7,9% một năm trên dư nợ giảm dần thì tháng đầu khoảng 6,9 triệu đồng; các tháng sau sẽ giảm dần ạ. Đây là số ước tính, chưa phải lịch trả nợ chính thức. | luật (0.01s) | Được: Tài liệu ghi ví dụ đúng ca này là "khoảng 6.8 triệu", AI tính ra 6,9. |
| 5 | lương anh mười lăm triệu thì có vay được hai trăm không em | Dạ anh chị vừa nói hai trăm không. Số tiền này tính theo triệu hay tỷ đồng ạ? | luật (0.0s) | Sai: Hiểu "hai trăm không" là số tiền rồi hỏi lại đơn vị; không trả lời câu về lương 15 triệu. |
| 6 | mà lãi bảy phẩy chín đấy là cố định hay sau này nó tăng lên | Dạ anh chị vừa nói bảy phẩy chín. Số tiền này tính theo triệu hay tỷ đồng ạ? | luật (0.0s) | Sai: Lấy lãi suất "bảy phẩy chín" làm số tiền vay. |
| 7 | không anh hỏi lãi suất cơ, lãi đấy có cố định suốt ba năm không | Dạ, lãi suất từ 7.9%/năm, hạn mức lên đến 500 triệu đồng, thời hạn 12 - 60 tháng và giải ngân trong vòng 24 giờ ạ. | kho (0.48s) | Sai: Đọc lại câu giới thiệu sản phẩm, không trả lời lãi có cố định hay không (tài liệu không nêu). |
| 8 | thế lương anh mười lăm triệu một tháng thì vay hai trăm triệu có được duyệt không | Dạ nếu được duyệt 200 triệu đồng trong 36 tháng, tạm tính theo lãi suất từ 7,9% một năm trên dư nợ giảm dần thì tháng đầu khoảng 6,9 triệu đồng; các tháng sau sẽ giảm dần ạ. Đây là số ước tính, chưa phải lịch trả nợ chính thức. | luật (0.01s) | Sai: Lặp lại phép tính trả góp, không trả lời lương 15 triệu có đủ điều kiện không. |
| 9 | nếu anh trả hết sớm trước hạn thì có bị phạt không | Dạ vay tín chấp bên em miễn phí trả trước hạn ạ. Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ làm hồ sơ không ạ? | luật (0.2s) | Được |
| 10 | từ từ đã, thế làm hồ sơ thì cần những giấy tờ gì | Dạ hồ sơ chính gồm căn cước công dân và xác nhận thu nhập hoặc sao kê lương 3 tháng gần nhất ạ. | luật (0.21s) | Được |
| 11 | năm ngoái anh có chậm trả thẻ tín dụng bên ngân hàng khác mấy lần, có sao không | Dạ, nếu trả chậm thẻ tín dụng, ngân hàng sẽ tính lãi phạt và ảnh hưởng điểm CIC ạ. | kho (0.44s) | Tạm: Nói chuyện trả chậm thẻ nói chung, không trả lời việc đó ảnh hưởng hồ sơ vay thế nào. |
| 12 | bên kia người ta chào anh có sáu phẩy năm phần trăm thôi, bên em cao thế | Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. Anh chị đang quan tâm đến sản phẩm vay tín chấp hay thẻ tín dụng? | Qwen (1.33s) | Sai: Qwen nói đúng 7.9% nhưng lưới chặn số coi là bịa và thay bằng câu "kiểm tra lại"; còn hỏi lại khách quan tâm vay hay thẻ. Tài liệu có sẵn câu đáp khi khách chê lãi cao. |
| 13 | thôi được rồi, giờ anh muốn làm thì làm thế nào | Dạ anh chuẩn bị CCCD và xác nhận thu nhập để em hỗ trợ làm hồ sơ ngay ạ. Anh có cần em hướng dẫn chi tiết từng bước không? | Qwen (0.66s) | Được |
| 14 | ừ thế em ghi nhận cho anh đi, bao giờ thì có người gọi lại | Em sẽ ghi nhận yêu cầu của anh và có chuyên viên liên hệ lại ạ. Cảm ơn anh đã quan tâm. | Qwen (0.73s) | Được |
| 15 | ok cảm ơn em nhé | Dạ vâng ạ. Anh chị còn cần em hỗ trợ thêm thông tin nào nữa không ạ? | luật (0.01s) | Được |

## Cuộc 2: vay mua nhà (căn 3,2 tỷ, có sẵn 1 tỷ)

| # | Khách | AI | Nguồn | Đánh giá |
|---|---|---|---|---|
| 1 | chào em, chị đang tính mua căn chung cư, bên em có cho vay mua nhà không | Dạ bên em có sản phẩm vay mua nhà ạ. Anh chị dự định vay khoảng bao nhiêu ạ? | luật (0.01s) | Được |
| 2 | căn đấy giá ba tỷ hai, chị có sẵn một tỷ rồi, vay được phần còn lại không | Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. Chị cho em biết thu nhập hàng tháng của mình để em tính toán xem chị đủ điều kiện vay bao nhiêu? | Qwen (1.38s) | Sai: Không trả lời được: cần vay 2,2 tỷ, tối đa 80% của 3,2 tỷ là 2,56 tỷ. Lưới coi 3,2 tỷ (số của khách) là hạn mức sai. |
| 3 | lãi suất bao nhiêu em | Dạ, sản phẩm lãi suất ưu đãi từ 6,5%/năm trong 2 năm đầu và thả nổi 8-10%/năm sau ạ. Anh chị muốn vay trong bao lâu ạ? | kho (0.45s) | Được |
| 4 | hết hai năm ưu đãi thì lãi lên bao nhiêu | Dạ, sau 2 năm, lãi suất sẽ thả nổi theo thị trường từ 8-10%/năm ạ. | kho (0.48s) | Được |
| 5 | chị muốn vay hai tỷ hai trong hai mươi năm thì mỗi tháng trả khoảng bao nhiêu | Dạ anh chị nhắc lại giúp em một số tiền muốn vay, kèm đơn vị triệu hoặc tỷ đồng ạ. | luật (0.0s) | Sai: Không đọc được "hai tỷ hai". |
| 6 | hai vợ chồng chị thu nhập tầm bốn mươi triệu một tháng thì có đủ không | Dạ em ghi nhận anh chị thu nhập 40 triệu đồng một tháng ạ. Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ làm hồ sơ không ạ? | luật (0.0s) | Tạm: Ghi nhận thu nhập nhưng không trả lời "có đủ không" (tài liệu: từ 10 triệu/tháng). |
| 7 | nhà đấy đang xây chưa có sổ hồng thì có vay được không | Dạ, anh chị cần có tài sản đảm bảo là bất động sản mua hoặc tài sản khác ạ. | kho (0.47s) | Tạm: Né câu hỏi; tài liệu có nêu cần sổ đỏ/sổ hồng và giấy phép xây dựng nếu xây nhà. |
| 8 | nếu sau này chị có tiền trả hết sớm thì có mất phí không | Dạ, anh chị trả nợ trước hạn miễn phí sau 3 năm theo ưu đãi ạ. | kho (0.44s) | Được |
| 9 | chị vay hai phẩy hai tỷ, hai mươi năm, mỗi tháng trả bao nhiêu | Dạ nếu được duyệt 2,2 tỷ đồng trong 240 tháng, tạm tính theo lãi suất từ 6,5% một năm trên dư nợ giảm dần thì tháng đầu khoảng 21,1 triệu đồng; các tháng sau sẽ giảm dần ạ. Đây là số ước tính, chưa phải lịch trả nợ chính thức. | luật (0.01s) | Được |
| 10 | thế trước ba năm mà trả thì phí bao nhiêu | Trước 3 năm, anh chị sẽ bị tính phí từ 1-2% trên số tiền trả trước ạ. | Qwen (0.91s) | Được |
| 11 | chị năm nay năm mươi tám tuổi rồi có vay được hai mươi năm không | Dạ, anh chị cần từ 22 - 65 tuổi ạ | kho (0.5s) | Tạm: Chỉ đọc khung tuổi, không nói gì về việc 58 tuổi vay 20 năm. |
| 12 | để chị bàn với chồng đã rồi gọi lại em sau nhé | Dạ vâng ạ, việc này anh chị bàn thêm với gia đình là hợp lý ạ. Anh chị còn cần em làm rõ thông tin nào để tiện trao đổi với người nhà không ạ? | kho (0.48s) | Được |

## Cuộc 3: hỏi lan man nhiều sản phẩm (không chọn sản phẩm trước)

| # | Khách | AI | Nguồn | Đánh giá |
|---|---|---|---|---|
| 1 | ai đấy | Dạ em là Lan bên Ngân hàng Quân đội, em gọi để giới thiệu chương trình ạ. | luật (0.0s) | Được |
| 2 | em là người thật hay máy đấy | Dạ em là trợ lý tư vấn tự động của ngân hàng ạ. Phần nào cần chuyên viên hỗ trợ trực tiếp, em xin ghi nhận để chuyên viên liên hệ lại anh chị ạ. | kho (0.4s) | Được |
| 3 | ừ thế bên em có những sản phẩm gì | Dạ bên em hiện có vay tín chấp, vay mua nhà, thẻ tín dụng và tiết kiệm ạ. Anh chị đang quan tâm sản phẩm nào ạ? | luật (0.0s) | Được |
| 4 | anh có khoản tiền nhàn rỗi năm trăm triệu, gửi một năm thì lãi được bao nhiêu | Dạ để tính tiền lãi, anh chị cho em biết số tiền muốn vay và thời hạn vay ạ. | luật (0.0s) | Sai: Khách hỏi GỬI tiết kiệm, AI hỏi số tiền muốn VAY. |
| 5 | thế gửi online với gửi ở quầy khác gì nhau | Dạ gửi online lãi suất cao hơn 0.2% so với gửi tại quầy ạ. | Qwen (1.01s) | Được |
| 6 | anh gửi tiết kiệm năm trăm triệu kỳ hạn mười hai tháng thì cuối kỳ được bao nhiêu tiền lãi | Dạ gửi tiết kiệm 12 tháng, lãi suất là 5.5%/năm ạ. Anh chị mở sổ tại quầy hoặc online nhé. Anh chị dự định gửi khoảng bao nhiêu ạ? | kho (0.56s) | Sai: Khách đã nói 500 triệu, AI không tính ra tiền lãi (27,5 triệu) mà hỏi lại gửi bao nhiêu. |
| 7 | đang gửi mà cần tiền gấp rút ra trước hạn thì có mất lãi không | Dạ, nếu rút trước hạn, phần tiền rút chỉ được hưởng lãi suất không kỳ hạn 0.5%/năm, phần còn lại vẫn giữ nguyên lãi suất ban đầu ạ. | kho (0.47s) | Được |
| 8 | à mà anh cũng đang muốn làm cái thẻ tín dụng, lương anh mười hai triệu thì làm được thẻ gì | Dạ, anh chị cần thu nhập từ 5 triệu đồng/tháng trở lên ạ. Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ mở thẻ không ạ? | kho (0.46s) | Tạm: Chỉ nêu điều kiện thu nhập, không gợi ý hạng thẻ nào. |
| 9 | phí thường niên thế nào em | Dạ, thẻ được miễn phí thường niên năm đầu tiên ạ. | kho (0.4s) | Tạm: Chỉ nói miễn phí năm đầu; tài liệu có phí từng hạng thẻ 200/400/800 nghìn. |
| 10 | thẻ đấy rút tiền mặt được không, phí rút bao nhiêu | Dạ phần ứng tiền mặt hiện em chưa có thông tin chính xác, em xin phép kiểm tra lại và báo anh chị sau ạ. | luật (0.0s) | Được |
| 11 | dạo này anh kẹt tiền quá, em có cách nào vay nhanh mà không cần chứng minh thu nhập không | Dạ điều kiện mở thẻ tín dụng là thu nhập từ 5 triệu đồng/tháng ạ. | luật (0.52s) | Sai: Vẫn bám sản phẩm thẻ ở lượt trước, không trả lời câu vay không cần chứng minh thu nhập. |
| 12 | em giảm lãi cho anh được không, anh là khách quen mà | Em xin lỗi, lãi suất theo quy định của ngân hàng ạ. Anh chị có cần tư vấn thêm về các ưu đãi khác không? | Qwen (1.23s) | Được |
| 13 | thế vay tín chấp với cái thẻ tín dụng thì cái nào lợi hơn hả em | Dạ, thẻ tín dụng cho phép chi tiêu trước trả sau, vay tín chấp là vay tiền trực tiếp ạ. | kho (0.44s) | Tạm: Nêu khác nhau chung chung, không so sánh. |
| 14 | bên em có bán bảo hiểm nhân thọ không | Dạ phần bảo hiểm hiện em chưa có thông tin chính xác, em xin phép kiểm tra lại và báo anh chị sau ạ. | luật (0.0s) | Được |
| 15 | thôi anh bận rồi, hôm khác nói chuyện nhé | Dạ vâng ạ. Em xin phép liên hệ lại lúc anh chị rảnh hơn ạ. | kho (0.47s) | Được |

## Tổng hợp

| Nguồn | Được | Tạm | Sai |
|---|---|---|---|
| kho | 9 | 6 | 2 |
| luật | 11 | 1 | 6 |
| Qwen | 5 | 0 | 2 |
| **Cộng** | 25 | 7 | 10 |
