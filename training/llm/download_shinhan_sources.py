"""Download a pinned, auditable set of public Shinhan PDFs for offline review.

These are source documents, not automatically approved training targets.  Old
rates/promotions remain archived and must never become current product facts.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "external" / "shinhan"

# Only files hosted by Shinhan Bank.  Keep the URL, age and intended use with
# every downloaded file so another bank's terms cannot enter this corpus.
SOURCES = [
    ("card_user_guide_vi", "card", "https://shinhan.com.vn/public/uploads/card/PDF/Guideline/SH-Consumer-Credit-Userguide-VN.pdf", "review"),
    ("sol_club_faq", "digital", "https://shinhan.com.vn/public/uploads/personal/mobile-banking/SOL%20Club/C%C3%A1c%20c%C3%A2u%20h%E1%BB%8Fi%20th%C6%B0%E1%BB%9Dng%20g%E1%BA%B7p%20SOL%20Club%20Final.pdf", "archive"),
    ("loan_household_terms", "loan", "https://shinhan.com.vn/public/uploads/static-file/T%26C/2024/Personal/CPD/040101C.1.4_Credit%20agreement_PE.Household_one-time_loan_VN%28T%26C%29.pdf", "review"),
    ("card_fees", "card", "https://shinhan.com.vn/public/uploads/PDF%20Card/Standard_Fee_Charges_%28Credit_Card%29_VN.pdf", "verify_current"),
    ("digital_card_guide", "card", "https://shinhan.com.vn/public/uploads/card/2024/Product/Guideline/External%20Guideline%20for%20Digital%20Card%20Function%20Registration_VN_final.pdf", "review"),
    ("consumer_credit_terms_2025", "card", "https://shinhan.com.vn/public/uploads/card/PDF/TnC/2020_M1-%C4%90I%E1%BB%80U%20KI%E1%BB%86N%20V%C3%80%20%C4%90I%E1%BB%80U%20KHO%E1%BA%A2N%20TH%E1%BA%BA%20T%C3%8DN%20D%E1%BB%A4NG%20C%C3%81%20NH%C3%82N.pdf", "review"),
    ("consumer_credit_terms_2018", "card", "https://shinhan.com.vn/public/uploads/card/PDF/TnC/REF.CARDTC-01-VN-201808-DKDK%20THE%20TD%20MOI.pdf", "archive"),
    ("taekwang_card_terms", "card", "https://shinhan.com.vn/public/uploads/card/2024/Product/TnC/VN_T%26C_Taekwang%20Card.pdf", "review"),
    ("ray_vina_card_terms", "card", "https://shinhan.com.vn/public/uploads/card/2024/Product/TnC/TnC_RAY%20VINA_VN.pdf", "review"),
    ("corporate_credit_card_terms", "card", "https://shinhan.com.vn/public/uploads/card/PDF/corporate%20credit-01.pdf", "review"),
    ("corporate_debit_card_terms", "card", "https://shinhan.com.vn/public/uploads/card/PDF/TnC/201909/Corporate%20Debit%20Card-VN.pdf", "review"),
    ("remittance_terms_2025", "transfer", "https://shinhan.com.vn/public/uploads/static-file/T%26C/2025/Remittance%20T%26C_1.pdf", "review"),
    ("general_terms_v18", "account", "https://shinhan.com.vn/public/uploads/static-file/T%26C/2025/1.%20General%20Terms%20and%20Conditions%20V18.pdf", "review"),
    ("general_terms_previous", "account", "https://shinhan.com.vn/public/uploads/static-file/T%26C/General_Terms_and_Conditions.pdf", "archive"),
    ("individual_loan_terms", "loan", "https://shinhan.com.vn/public/uploads/static-file/T%26C/2024/Personal/CPD/040101R.1.1_%20Credit%20agreement_IND_one-time_loan_EN%28T%26C%29.pdf", "review"),
    ("personal_account_form_2023", "account", "https://shinhan.com.vn/public/uploads/static-file/forms-center/accounts_and_deposits/2023/1810/Deposit%2001A%20%28VN%29.pdf", "archive"),
    ("personal_account_form_legacy", "account", "https://shinhan.com.vn/public/uploads/static-file/forms-center/accounts_and_deposits/Deposit_01A_%C4%90o%CC%9Bn_%C4%91a%CC%86ng_ky%CC%81_tho%CC%82ng_tin%2C_mo%CC%9B%CC%89_ta%CC%80i_khoa%CC%89n_va%CC%80_di%CC%A3ch_vu%CC%A3_da%CC%80nh_cho_kha%CC%81ch_ha%CC%80ng_ca%CC%81_nha%CC%82n.pdf", "archive"),
    ("card_application_form", "card", "https://shinhan.com.vn/public/uploads/static-file/forms-center/cards/CARD-04-202003%20-%20SHINHAN%20CARD%20APPLICATION%20FORM%20-%20FOR%20CURRENT%20CUSTOMER.pdf", "review"),
    ("deposit_rates_2025", "deposit", "https://shinhan.com.vn/public/uploads/static-file/deposit_personal_vi.pdf", "verify_current"),
    ("business_review_2025", "overview", "https://shinhan.com.vn/public/uploads/Business%20Review/2025/SHBVN_Business%20Review%202025_VIE.pdf", "review"),
    ("old_fee_comparison", "fee", "https://shinhan.com.vn/public/uploads/static-file/IB_and_counter_comparison_table_11092019_%281%29.pdf", "archive"),
    ("old_home_loan_promotion", "loan", "https://shinhan.com.vn/public/uploads/static-file/PHU_MY_HUNG%20-%20THONG_TIN_CHI_TIET.pdf", "archive"),
    ("google_pay_terms", "card", "https://shinhan.com.vn/public/uploads/Port%20and%20Usage/Google%20Pay/T%26C_GGP_VN.pdf", "archive"),
    ("general_terms_legacy", "account", "https://shinhan.com.vn/public/uploads/static-file/T%26C/SHBVN_Cac%20dieu%20khoan%20va%20dieu%20kien%20chung.pdf", "archive"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, category, url, use in SOURCES:
        target = OUT / f"{name}.pdf"
        tmp = target.with_suffix(".part")
        if not target.exists():
            result = subprocess.run(
                ["curl", "-fLSs", "--retry", "2", "--max-time", "90", "-o", str(tmp), url],
                capture_output=True, text=True,
            )
            if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1024:
                tmp.unlink(missing_ok=True)
                manifest.append({"name": name, "url": url, "status": "failed",
                                 "error": result.stderr[-300:]})
                continue
            if tmp.open("rb").read(4) != b"%PDF":
                tmp.unlink()
                manifest.append({"name": name, "url": url, "status": "not_pdf"})
                continue
            tmp.replace(target)
        data = target.read_bytes()
        manifest.append({"name": name, "category": category, "url": url,
                         "use": use, "status": "downloaded", "path": str(target),
                         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                         "downloaded_utc": datetime.now(timezone.utc).isoformat()})
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"downloaded": sum(x["status"] == "downloaded" for x in manifest),
                      "failed": [x["name"] for x in manifest if x["status"] != "downloaded"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
