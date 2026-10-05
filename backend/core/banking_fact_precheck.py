"""Deterministic comparisons for explicit customer facts and retrieved rules.

Only emit a note when both sides are present. This never declares a loan
approved; it only compares the particular condition the customer asked about.
"""
from __future__ import annotations

import re
from decimal import Decimal


def banking_fact_precheck(messages: list[dict], system_prompt: str) -> str:
    source = system_prompt.split("THÔNG TIN THAM KHẢO:", 1)[-1]
    if source == system_prompt:
        return ""
    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    if not users:
        return ""
    latest = users[-1]
    history = " ".join(users)
    notes: list[str] = []

    if re.search(r"(?i)tuổi|đủ điều kiện|vay được|mở thẻ", latest):
        recent_ages = re.findall(r"(?<!\d)(\d{1,2})\s*tuổi\b", latest, re.I)
        ages = recent_ages or re.findall(r"(?<!\d)(\d{1,2})\s*tuổi\b", history, re.I)
        minimums = {int(n) for n in re.findall(
            r"(?i)\btừ\s+(\d{2})\s*(?:[-–]\s*\d{2}\s*)?tuổi\b", source
        )}
        ranges = {(int(a), int(b)) for a, b in re.findall(
            r"(?i)\btừ\s+(\d{2})\s*[-–]\s*(\d{2})\s*tuổi\b", source
        )}
        if ages and (recent_ages or len(set(ages)) == 1) and len(minimums) == 1:
            age, minimum = int(ages[-1]), next(iter(minimums))
            if age < minimum:
                notes.append(
                    f"Khách {age} tuổi < mức tối thiểu {minimum} tuổi trong nguồn: "
                    "CHƯA đạt riêng điều kiện tuổi. Không được nói là đã đạt."
                )
            elif len(ranges) == 1:
                lower, upper = next(iter(ranges))
                if lower == minimum and age > upper:
                    notes.append(
                        f"Khách {age} tuổi > mức tối đa {upper} tuổi trong nguồn: "
                        "CHƯA đạt riêng điều kiện tuổi. Không được nói là đã đạt."
                    )

    if re.search(r"(?i)nợ xấu|tất toán|trả hết nợ", latest) and re.search(
        r"(?i)tất toán\s+trên\s+(?:1|một)\s+năm", source
    ):
        settled = r"(?:tất toán|trả hết(?: nợ xấu| nợ)?)"
        month_matches = re.findall(rf"(?i){settled}[^.!?\n]{{0,35}}?(\d{{1,2}})\s*tháng", history)
        month_matches += re.findall(rf"(?i)(\d{{1,2}})\s*tháng[^.!?\n]{{0,35}}?{settled}", history)
        if month_matches and len(set(month_matches)) == 1:
            months = int(month_matches[-1])
            if months <= 12:
                notes.append(
                    f"Khách đã tất toán {months} tháng <= 12 tháng: CHƯA qua "
                    "mốc trên 1 năm để có thể xem xét. Không nói đã qua mốc."
                )
            else:
                notes.append(
                    f"Khách đã tất toán {months} tháng > 12 tháng: chỉ CÓ THỂ "
                    "xem xét; không khẳng định được duyệt."
                )

    if re.search(r"(?i)chưa có tài sản (?:bảo đảm|đảm bảo)", history) and re.search(
        r"(?i)có tài sản (?:bảo đảm|đảm bảo)", source
    ) and re.search(r"(?i)đủ điều kiện|vay được|kết luận", latest):
        notes.append(
            "Khách đã nói CHƯA có tài sản bảo đảm, còn nguồn yêu cầu có: "
            "CHƯA đạt điều kiện tài sản; đừng hỏi lại như thể chưa biết."
        )

    return "\n".join(notes)


def direct_condition_answer(messages: list[dict], system_prompt: str,
                            prefill: str = "") -> str:
    """Answer only an explicit numeric-condition question with checked facts."""
    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    if not users:
        return ""
    latest = users[-1]
    note = banking_fact_precheck(messages, system_prompt)
    prefix = "" if prefill.strip() else ("Vâng, " if re.search(r"(?i)miền Bắc", " ".join(users)) else "Dạ, ")
    source = system_prompt.split("THÔNG TIN THAM KHẢO:", 1)[-1]

    age = re.search(r"Khách (\d+) tuổi < mức tối thiểu (\d+) tuổi", note)
    if age and re.search(r"(?i)riêng tuổi|điều kiện tuổi|tuổi.*(đạt|đủ|được)", latest):
        return (f"{prefix}{age.group(1)} tuổi chưa đạt điều kiện tuổi ạ; "
                f"tài liệu yêu cầu từ {age.group(2)} tuổi.")

    above = re.search(r"Khách (\d+) tuổi > mức tối đa (\d+) tuổi", note)
    if above and re.search(r"(?i)riêng tuổi|điều kiện tuổi|tuổi.*(đạt|đủ|được)", latest):
        return (f"{prefix}{above.group(1)} tuổi chưa đạt điều kiện tuổi ạ; "
                f"tài liệu giới hạn đến {above.group(2)} tuổi.")

    debt = re.search(r"Khách đã tất toán (\d+) tháng <= 12 tháng", note)
    if debt and re.search(r"(?i)đã qua mốc|trên (?:1|một) năm|được xem xét|thuộc diện", latest):
        return (f"{prefix}{debt.group(1)} tháng chưa qua mốc trên 1 năm trong "
                "tài liệu, nên chưa thuộc trường hợp có thể xem xét theo điều kiện này ạ.")

    debt_above = re.search(r"Khách đã tất toán (\d+) tháng > 12 tháng", note)
    if debt_above and re.search(r"(?i)được xem xét|được vay|duyệt|chắc|trên (?:1|một) năm", latest):
        return (f"{prefix}{debt_above.group(1)} tháng đã qua mốc trên 1 năm ạ; "
                "hồ sơ có thể được xem xét, nhưng chưa thể khẳng định được duyệt.")

    if "CHƯA đạt điều kiện tài sản" in note and re.search(
        r"(?i)có thể kết luận|đủ điều kiện|vay được", latest
    ):
        return (f"{prefix}chưa thể kết luận đủ điều kiện ạ; tài liệu yêu cầu "
                "có tài sản bảo đảm, còn anh/chị vừa nói mình chưa có.")

    card = re.search(r"(?i)thẻ\s+(Classic|Gold|Platinum)", latest)
    if card and re.search(r"(?i)năm thứ (?:2|hai)|từ năm thứ hai", latest) and re.search(
        r"(?i)miễn phí thường niên năm đầu", source
    ):
        fees = re.findall(
            rf"(?im)^\s*\d+\.\s*Thẻ\s+{re.escape(card.group(1))}:"
            r"[^\n]*?phí thường niên\s+([\d.]+)\s*đ/năm", source
        )
        if len(fees) == 1:
            return (f"{prefix}năm đầu được miễn phí; từ năm thứ hai, phí thường niên "
                    f"thẻ {card.group(1)} là {fees[0]}đ/năm ạ.")

    if re.search(r"(?i)gửi online|gửi trực tuyến", latest) and re.search(
        r"(?i)bao nhiêu|cộng lên|thành bao nhiêu", latest
    ):
        term = re.search(r"(?i)(\d{1,2})\s*tháng", latest)
        bonus = re.search(r"(?i)lãi suất cộng thêm\s+(\d+(?:[.,]\d+)?)%/năm", source)
        if term and bonus:
            rates = re.findall(
                rf"(?i)kỳ hạn\s+{re.escape(term.group(1))}\s+tháng:\s*lãi suất\s+(\d+(?:[.,]\d+)?)%/năm",
                source,
            )
            if len(rates) == 1:
                base = Decimal(rates[0].replace(",", "."))
                extra = Decimal(bonus.group(1).replace(",", "."))
                total = format(base + extra, "f")
                return (f"{prefix}gửi online kỳ hạn {term.group(1)} tháng là "
                        f"{total}%/năm, gồm mức tại quầy {rates[0]}% cộng thêm {bonus.group(1)}% ạ.")

    if re.search(r"(?i)trả trước hạn|trả nợ trước hạn", latest):
        years = re.search(r"(?i)sau\s+(\d{1,2})\s+năm", latest)
        free_after = re.search(r"(?i)miễn phí trả nợ trước hạn sau\s+(\d{1,2})\s+năm", source)
        if years and free_after and int(years.group(1)) > int(free_after.group(1)):
            return (f"{prefix}trả trước hạn sau {years.group(1)} năm thuộc diện miễn phí ạ; "
                    f"tài liệu miễn phí sau {free_after.group(1)} năm.")
    return ""
