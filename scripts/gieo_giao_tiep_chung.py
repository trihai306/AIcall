"""Gieo nhóm đáp án GIAO TIẾP CHUNG vào kho trả lời.

Kho trả lời vốn chỉ học từ tài liệu sản phẩm, nên mọi câu ngoài sản phẩm ("cảm
ơn em", "để anh suy nghĩ", "có phải lừa đảo không"...) lần nào cũng phải để mô
hình tự viết, chậm 0,4-2,7 giây và mỗi lần một kiểu. Tệp này soạn sẵn các câu
đó: ghi tài liệu `knowledge/faq/giao_tiep_chung.md` (mọi đáp án phải thuộc một
tài liệu nguồn) rồi thêm từng đáp án qua API của backend ĐANG CHẠY - để kho
đang dùng nạp lại và tiếng đọc được dựng như mọi đáp án soạn tay khác.

Chạy lại bao nhiêu lần cũng được: đáp án đã có (trùng chữ) thì bỏ qua.

    .venv\\python.exe scripts\\gieo_giao_tiep_chung.py [--url http://127.0.0.1:8100]

NỘI DUNG CỐ Ý KHÔNG CÓ CON SỐ, lãi suất, điều kiện hay lời hứa nào về sản phẩm:
những thứ đó phải đến từ tài liệu sản phẩm. Bên nghiệp vụ nên đọc lại một lượt
ở trang Tri thức AI -> Câu hỏi thường gặp -> giao_tiep_chung.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

NHOM, TEN = "faq", "giao_tiep_chung"

# (chủ đề, [các cách khách nói], câu trả lời)
BANG = [
    ("Khách cảm ơn",
     ["cảm ơn em", "cảm ơn em nhé", "ok cảm ơn em", "anh cảm ơn nhé", "chị cảm ơn em nhiều"],
     "Dạ không có gì ạ. Anh chị cần em hỗ trợ thêm thông tin nào nữa không ạ?"),
    ("Khách khen",
     ["em tư vấn nhiệt tình quá", "em nói dễ nghe đấy", "em tư vấn hay đấy", "giọng em dễ nghe quá"],
     "Dạ em cảm ơn anh chị ạ. Em hỗ trợ anh chị tiếp phần thông tin sản phẩm nhé ạ."),
    ("Khách muốn suy nghĩ thêm",
     ["để anh suy nghĩ thêm", "để chị suy nghĩ đã", "anh còn đang phân vân", "chị chưa quyết được",
      "để anh cân nhắc thêm đã"],
     "Dạ vâng ạ, anh chị cứ cân nhắc thêm. Anh chị còn băn khoăn điểm nào, em giải thích rõ "
     "hơn để anh chị dễ quyết định ạ."),
    ("Khách cần hỏi ý người nhà",
     ["để anh hỏi ý vợ đã", "để chị bàn với chồng đã", "anh phải hỏi vợ anh đã",
      "để anh bàn với gia đình đã", "chị phải hỏi ý kiến chồng"],
     "Dạ vâng ạ, việc này anh chị bàn thêm với gia đình là hợp lý ạ. Anh chị còn cần em làm "
     "rõ thông tin nào để tiện trao đổi với người nhà không ạ?"),
    ("Khách bảo nói chậm lại",
     ["em nói chậm lại đi", "nói chậm thôi em", "em nói nhanh quá", "nói từ từ thôi em",
      "em nói chậm lại một chút"],
     "Dạ vâng, em xin lỗi anh chị. Em sẽ nói chậm lại ạ."),
    ("Khách không nghe rõ",
     ["em nói to lên", "anh không nghe rõ", "chị nghe không rõ lắm", "em nói nhỏ quá",
      "nghe không rõ em ơi"],
     "Dạ em xin lỗi anh chị, em sẽ nói rõ hơn ạ. Anh chị nghe được em chưa ạ?"),
    ("Khách không hiểu",
     ["anh không hiểu em nói gì", "chị chưa hiểu lắm", "em nói gì anh không hiểu",
      "anh nghe mà chưa hiểu", "khó hiểu quá em"],
     "Dạ em xin lỗi vì em nói chưa rõ ạ. Anh chị chưa rõ ở phần nào, em giải thích lại phần "
     "đó ạ."),
    ("Khách bảo chờ một chút",
     ["chờ anh một chút", "đợi chị tí", "em chờ máy một lát", "đợi anh một tí nhé",
      "em giữ máy chờ anh chút"],
     "Dạ vâng ạ, em giữ máy chờ anh chị ạ."),
    ("Khách đã biết thông tin",
     ["cái này anh biết rồi", "chị nghe rồi", "anh biết rồi em", "phần đó anh rõ rồi",
      "thông tin này chị biết rồi"],
     "Dạ vâng ạ. Vậy anh chị còn cần em làm rõ thêm điểm nào không ạ?"),
    ("Khách hỏi có phải lừa đảo không",
     ["có phải lừa đảo không đấy", "sao anh tin được em", "em có lừa đảo không",
      "làm sao biết em không lừa đảo", "bên em có phải lừa đảo không"],
     "Dạ anh chị cẩn thận như vậy là đúng ạ. Em chỉ giới thiệu thông tin sản phẩm, không yêu "
     "cầu anh chị chuyển tiền hay cung cấp mật khẩu, mã xác thực qua điện thoại. Anh chị có "
     "thể đến chi nhánh hoặc gọi tổng đài chính thức của ngân hàng để kiểm tra lại ạ."),
    ("Khách hỏi em là người hay máy",
     ["em là người hay máy đấy", "em là robot à", "em có phải AI không", "em là máy trả lời tự động à",
      "đang nói chuyện với người thật hay máy"],
     "Dạ em là trợ lý tư vấn tự động của ngân hàng ạ. Phần nào cần chuyên viên hỗ trợ trực "
     "tiếp, em xin ghi nhận để chuyên viên liên hệ lại anh chị ạ."),
    ("Khách hỏi nghe máy có mất tiền không",
     ["nghe máy có mất tiền không", "cuộc gọi này có mất phí không", "anh nghe có bị trừ tiền không",
      "nghe điện thoại này có tốn cước không"],
     "Dạ cuộc gọi này do bên em gọi tới, anh chị không mất cước ạ."),
    ("Khách hỏi tư vấn có mất phí không",
     ["tư vấn có mất phí không", "em tư vấn có tính tiền không", "nghe tư vấn có mất tiền không",
      "tư vấn thế này có thu phí không"],
     "Dạ em tư vấn thông tin hoàn toàn miễn phí ạ."),
    ("Khách hỏi nghe xong có bắt buộc đăng ký không",
     ["nghe xong có bắt buộc đăng ký không", "anh nghe tư vấn có bị ràng buộc gì không",
      "nghe thông tin có phải đăng ký luôn không", "tư vấn xong có bắt buộc làm không"],
     "Dạ không ạ. Anh chị nghe thông tin để tham khảo, không bắt buộc phải đăng ký ạ."),
    ("Khách lo lộ thông tin",
     ["thông tin của anh có bị lộ không", "bên em có bảo mật thông tin không",
      "thông tin chị cung cấp có an toàn không", "em có đem thông tin của anh cho người khác không"],
     "Dạ thông tin anh chị cung cấp chỉ dùng để tư vấn và xử lý hồ sơ theo quy định của ngân "
     "hàng ạ."),
    ("Khách đang khó khăn tài chính",
     ["anh đang khó khăn lắm", "dạo này chị không có tiền", "kinh tế đang khó khăn em ạ",
      "anh làm gì có tiền", "công việc anh đang bấp bênh"],
     "Dạ em hiểu ạ. Anh chị cứ tham khảo thông tin trước, khi nào thấy phù hợp thì mình tính "
     "tiếp, không có gì ràng buộc ạ."),
    ("Khách phàn nàn bị gọi nhiều",
     ["sao gọi hoài vậy", "bên em gọi nhiều quá", "ngày nào cũng gọi", "gọi gì mà gọi lắm thế",
      "phiền quá em ơi"],
     "Dạ em xin lỗi đã làm phiền anh chị ạ. Nếu anh chị không muốn nhận cuộc gọi nữa, em xin "
     "ghi nhận để bên em không liên hệ lại ạ."),
    ("Khách hỏi sao gọi giờ này",
     ["sao em gọi giờ này", "gọi gì giờ này", "sao lại gọi vào giờ này", "giờ này mà còn gọi"],
     "Dạ em xin lỗi nếu em gọi chưa đúng lúc ạ. Anh chị cho em xin khung giờ tiện hơn, em sẽ "
     "liên hệ lại ạ."),
    ("Khách đã được người khác tư vấn",
     ["có người gọi tư vấn cho anh rồi", "hôm trước có bạn gọi cho chị rồi",
      "bên em gọi tư vấn rồi mà", "anh được tư vấn rồi em"],
     "Dạ em xin lỗi vì đã liên hệ trùng ạ. Anh chị còn cần em hỗ trợ thêm thông tin nào không "
     "ạ? Nếu không, em xin phép không làm phiền thêm ạ."),
    ("Gọi nhầm người",
     ["em gọi nhầm số rồi", "anh không phải tên đó", "nhầm người rồi em", "chị không phải người đó",
      "em nhầm máy rồi"],
     "Dạ em xin lỗi anh chị vì sự nhầm lẫn này ạ. Em xin ghi nhận lại để bên em kiểm tra thông "
     "tin ạ."),
    ("Khách hỏi chuyện riêng của tư vấn viên",
     ["em bao nhiêu tuổi", "em có người yêu chưa", "em quê ở đâu", "em có gia đình chưa",
      "em xinh không"],
     "Dạ em cảm ơn anh chị đã quan tâm ạ. Em xin phép quay lại phần thông tin sản phẩm để hỗ "
     "trợ anh chị cho đúng việc ạ."),
    ("Khách không còn câu hỏi",
     ["anh hết câu hỏi rồi", "chị không hỏi gì nữa", "thế thôi em nhé", "anh không cần hỏi gì thêm",
      "vậy được rồi em"],
     "Dạ vâng ạ. Em cảm ơn anh chị đã dành thời gian, em chào anh chị ạ."),
    ("Khách chào kết thúc",
     ["chào em nhé", "thôi chào em", "tạm biệt em", "anh cúp máy nhé", "chị tắt máy đây"],
     "Dạ em cảm ơn anh chị đã nghe máy. Em chào anh chị ạ."),
    ("Khách đồng ý nghe tiếp",
     ["em cứ nói tiếp đi", "em nói tiếp đi anh nghe", "ừ em tư vấn tiếp đi", "em cứ tư vấn đi",
      "nói tiếp đi em"],
     "Dạ vâng ạ. Anh chị muốn em nói rõ hơn về phần nào trước ạ?"),
    ("Khách hỏi chung chung muốn biết thêm",
     ["em tư vấn cho anh đi", "em nói rõ hơn đi", "em giới thiệu kỹ hơn xem", "cụ thể là thế nào em",
      "em tư vấn kỹ hơn cho chị"],
     "Dạ vâng ạ. Anh chị quan tâm nhất tới phần nào, lãi suất, hạn mức hay hồ sơ thủ tục, để "
     "em nói kỹ phần đó trước ạ?"),
    ("Khách chưa có nhu cầu ngay",
     ["hiện tại anh chưa cần", "bây giờ chị chưa có nhu cầu", "lúc này anh chưa dùng tới",
      "tạm thời chị chưa cần đâu"],
     "Dạ vâng ạ. Anh chị cứ lưu lại thông tin để tham khảo, khi nào có nhu cầu anh chị liên "
     "hệ lại bên em ạ."),
    ("Khách xin lỗi vì đường truyền",
     ["sóng yếu quá em", "mạng chập chờn quá", "chỗ anh sóng kém", "anh đang ở chỗ sóng yếu"],
     "Dạ không sao ạ. Anh chị nghe được em thì mình trao đổi tiếp, nếu chưa tiện em xin phép "
     "gọi lại sau ạ."),
]


# Bộ thứ hai nằm ở TÀI LIỆU RIÊNG. Không được thêm dòng vào tài liệu đã gieo:
# đổi nội dung một tài liệu nguồn là kho tự TẮT mọi đáp án thuộc tài liệu đó (kể
# cả dòng soạn tay) vì mã băm nguồn không còn khớp. Muốn thêm đợt mới thì tạo
# một tài liệu mới với tên khác.
TEN_BO_HAI = "giao_tiep_theo_tinh_huong"


def cac_bo():
    """[(tên tài liệu, [(nhóm, tình huống, cách nói, trả lời)])]"""
    from du_lieu_giao_tiep_chung import BANG_MOI, NHOM_CUA_DONG_GOC
    goc = [(NHOM_CUA_DONG_GOC.get(t, ""), t, q, a) for t, q, a in BANG]
    return [(TEN, goc), (TEN_BO_HAI, list(BANG_MOI))]


def viet_tai_lieu(goc: Path, ten: str, bang, theo_nhom: bool) -> Path:
    p = goc / "knowledge" / NHOM / f"{ten}.md"
    dong = ["# Giao tiếp chung trong cuộc gọi tư vấn", "",
            "Phạm vi: các câu khách nói KHÔNG thuộc một sản phẩm cụ thể nào - cảm ơn, phân vân, "
            "hỏi về chính cuộc gọi, phàn nàn, chào kết thúc. Tài liệu này không chứa lãi suất, "
            "hạn mức hay điều kiện sản phẩm; những thông tin đó nằm ở tài liệu sản phẩm.", ""]
    nhom_truoc = None
    for nhom, chu_de, cach_hoi, tra_loi in bang:
        if theo_nhom and nhom != nhom_truoc:
            dong += [f"## Nhóm tình huống: {nhom}", ""]
            nhom_truoc = nhom
        dong += [f"{'###' if theo_nhom else '##'} {chu_de}", "",
                 "Khách thường nói: " + "; ".join(f'"{c}"' for c in cach_hoi) + ".", "",
                 f"Tư vấn viên trả lời: {tra_loi}", ""]
    moi = "\n".join(dong)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(moi, encoding="utf-8")
        print("Đã ghi tài liệu", p)
    elif p.read_text(encoding="utf-8") != moi:
        print(f"GIỮ NGUYÊN {p.name}: tài liệu đã gieo khác bản trong mã. Không ghi đè vì "
              "sẽ tắt mọi đáp án của nó; thêm dòng mới thì tạo tài liệu mới.")
    return p


def goi(url: str, data=None, method=None, form=False):
    headers = {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100")
    ap.add_argument("--chi-tai-lieu", action="store_true", help="chỉ ghi tài liệu, không gọi API")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    bo = cac_bo()
    for ten, bang in bo:
        viet_tai_lieu(Path(__file__).resolve().parents[1], ten, bang, theo_nhom=ten != TEN)
    if a.chi_tai_lieu:
        return 0
    goc = a.url.rstrip("/") + "/api/knowledge"
    # Tài liệu mới phải vào chỉ mục tri thức trước, bộ soạn mới nhận nó làm nguồn.
    goi(goc + "/nap-lai", data={}, form=True)
    for ten, bang in bo:
        q = urllib.parse.urlencode({"nhom": NHOM, "ten": ten})
        co = goi(f"{goc}/hoi-dap?{q}")
        if co.get("error"):
            print("Backend chưa thấy tài liệu:", co["error"])
            return 1
        da_co = {str(i.get("tra_loi", "")).strip(): i["id"] for i in co.get("items", [])}
        them = 0
        for nhom, chu_de, cach_hoi, tra_loi in bang:
            if tra_loi in da_co:
                # Dòng gieo từ trước khi có nhóm tình huống: chỉ gắn nhãn.
                goi(f"{goc}/hoi-dap/{da_co[tra_loi]}/tinh-huong", data={"tinh_huong": nhom})
                continue
            r = goi(goc + "/hoi-dap", data={"nhom": NHOM, "ten": ten, "cau_hoi": cach_hoi,
                                             "tra_loi": tra_loi, "bat": True, "tinh_huong": nhom})
            them += 1
            print(f"+ [{nhom}] {chu_de}: tiếng {r.get('voice', {}).get('status')}")
        print(f"{ten}: thêm {them}, đã có sẵn {len(bang) - them}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
