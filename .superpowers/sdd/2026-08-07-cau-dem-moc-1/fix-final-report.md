# Báo cáo sửa lỗi – vòng soát code cuối (nhánh cau-dem-moc-1)

## Việc 1 (BẮT BUỘC) — Bao `OSError` cho `p.write_bytes`

**File:** `backend/services/tts_service.py`, dòng 569–577 (sau sửa)

**Thay đổi:** Bao `p.write_bytes(wav)` trong `try/except OSError`. Khi ghi đĩa hỏng, log cảnh báo nêu rõ `c.id` và đường dẫn, rồi **vẫn tiếp tục** gán `_filler_cache[khoa]` và `_filler_ms[khoa]`, không dùng `continue` trong nhánh except. Phiên đang chạy vẫn có câu đệm trong bộ nhớ, lần khởi động sau mới phải dựng lại.

```python
            try:
                p.write_bytes(wav)
            except OSError as e:
                logger.warning(
                    "Ghi câu đệm %r ra %s thất bại (%s) — giữ trong bộ nhớ, "
                    "lần khởi động sau sẽ dựng lại.",
                    c.id, p, e,
                )
            self._filler_cache[khoa] = wav
            self._filler_ms[khoa] = self._wav_duration_ms(wav)
            dung_moi += 1
```

---

## Việc 2 — Sửa tên hàm trong chú thích

**File:** `backend/pipeline/streaming_pipeline.py`, dòng 441

Đổi `presynthesize_fillers` → `dung_fillers` trong chuỗi docstring của `_send_filler`.

---

## Việc 3, 4, 5 — Chỉnh chữ trong `data/fillers.json`

| id | Trước | Sau |
|---|---|---|
| `dai_04` | "…anh chị chờ em **xíu** nhé" | "…anh chị chờ em **một lát** nhé" |
| `noi_04` | "…một lát em tra nhé" | "…một lát**,** em tra nhé" |
| `trung_06` | "…trả lời anh chị ngay đây" | "…trả lời anh chị ngay đây **ạ**" |

39 câu còn lại không bị chạm. Tổng vẫn 42 câu.

---

## Kiểm chứng

### 1. pytest 25 tests

```
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 25 items

tests/test_filler_pick.py::test_rong_thi_tra_none PASSED                 [  4%]
tests/test_filler_pick.py::test_uu_tien_cau_vua_khit_thay_vi_cau_dai_nhat PASSED [  8%]
tests/test_filler_pick.py::test_noi_ra_ngoai_khoang_vua_khit_khi_khong_con_gi_khac PASSED [ 12%]
tests/test_filler_pick.py::test_khong_cau_nao_du_dai_thi_lay_cau_dai_nhat PASSED [ 16%]
tests/test_filler_pick.py::test_duyet_het_nhom_roi_moi_lap_lai PASSED    [ 20%]
tests/test_filler_pick.py::test_nhom_hai_cau_thi_luan_phien_khong_ket PASSED [ 24%]
tests/test_filler_pick.py::test_it_dung_nhat_duoc_uu_tien_hon_ca_do_vua_khit PASSED [ 28%]
tests/test_filler_store.py::test_nap_kho_hop_le PASSED                   [ 32%]
tests/test_filler_store.py::test_id_cau_trung_thi_bao_loi PASSED         [ 36%]
tests/test_filler_store.py::test_chu_de_khong_ton_tai_thi_bao_loi PASSED [ 40%]
tests/test_filler_store.py::test_text_rong_thi_bao_loi PASSED            [ 44%]
tests/test_filler_store.py::test_hop_cau_hoi_mac_dinh_la_true PASSED     [ 48%]
tests/test_filler_store.py::test_file_khong_ton_tai_thi_bao_loi PASSED   [ 52%]
tests/test_filler_store.py::test_van_tay_on_dinh_giua_hai_lan_goi PASSED [ 56%]
tests/test_filler_store.py::test_van_tay_an_toan_lam_ten_file PASSED     [ 60%]
tests/test_filler_store.py::test_van_tay_doi_khi_bat_ky_tham_so_nao_doi[text-Vâng ạ] PASSED [ 64%]
tests/test_filler_store.py::test_van_tay_doi_khi_bat_ky_tham_so_nao_doi[giong-giong_khac] PASSED [ 68%]
tests/test_filler_store.py::test_van_tay_doi_khi_bat_ky_tham_so_nao_doi[nfe-12] PASSED [ 72%]
tests/test_filler_store.py::test_van_tay_doi_khi_bat_ky_tham_so_nao_doi[speed-1.2] PASSED [ 76%]
tests/test_filler_store.py::test_van_tay_doi_khi_bat_ky_tham_so_nao_doi[ref_text-câu mẫu khác] PASSED [ 80%]
tests/test_filler_store.py::test_van_tay_khong_nham_ranh_gioi_truong PASSED [ 84%]
tests/test_kho_that.py::test_kho_that_nap_duoc PASSED                    [ 88%]
tests/test_kho_that.py::test_moc_1_chi_co_chu_de_chung PASSED            [ 92%]
tests/test_kho_that.py::test_du_cau_ngan_va_cau_dai PASSED               [ 96%]
tests/test_kho_that.py::test_lay_kho_nho_ket_qua PASSED                  [100%]

============================== 25 passed in 0.03s ==============================
```

### 2. Import tts_service

```
.venv/bin/python -c "import backend.services.tts_service"
OK
```

### 3. Kho 42 câu, ba câu đúng chữ

```
42
['Vâng, cái này em cần tra lại một chút, anh chị chờ em một lát nhé', 'Vâng ạ, em xem lại rồi trả lời anh chị ngay đây ạ', 'Vâng, anh chị đợi em một lát, em tra nhé']
```

### 4. Chứng minh Việc 1 — OSError không làm mất cache

```
WARNING backend.services.tts_service Ghi câu đệm 'c1' ra /tmp/filler_test_dir/c1__vantay123.wav thất bại ([Errno 28] No space left on device) — giữ trong bộ nhớ, lần khởi động sau sẽ dựng lại.
write_bytes gọi: ['c1__vantay123.wav', 'c2__vantay123.wav', 'c3__vantay123.wav']
_filler_cache keys: [('test_voice', 'c1'), ('test_voice', 'c2'), ('test_voice', 'c3')]
c1 trong cache? True
c2 trong cache? True
c3 trong cache? True
PASS — write_bytes thất bại nhưng _filler_cache vẫn đầy đủ cả 3 câu.
```

- Log cảnh báo: co (`WARNING ... Ghi câu đệm 'c1' ...`)
- `_filler_cache` vẫn có cả 3 câu kể cả c1 (write_bytes ném lỗi)
- Vòng lặp chạy tiếp: write_bytes được gọi đủ 3 lần (c1, c2, c3)
