#!/bin/bash
set -e

# Fine-tune F5-TTS-Vietnamese trên giọng đã thu.
#
# Yêu cầu trước khi chạy:
#   1. Đã chạy: python training/voice/prepare_dataset.py --input <thư mục ghi âm>
#      -> dữ liệu nằm ở tools/F5-TTS-Vietnamese/data/your_dataset/
#   2. Đã có model gốc: models/tts/F5-TTS-Vietnamese-ViVoice/model_last.pt
#   3. GPU NVIDIA (khuyến nghị; 12GB VRAM chạy được với BATCH_SIZE mặc định)
#
# Usage: bash training/voice/train.sh <ten_giong>
# Ví dụ: bash training/voice/train.sh giong_lan

VOICE_NAME="${1:?Usage: bash training/voice/train.sh <ten_giong>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
F5_DIR="$PROJECT_DIR/tools/F5-TTS-Vietnamese"
PRETRAIN_CKPT="$PROJECT_DIR/models/tts/F5-TTS-Vietnamese-ViVoice/model_last.pt"
PRETRAIN_VOCAB="$PROJECT_DIR/models/tts/F5-TTS-Vietnamese-ViVoice/vocab.txt"
OUTPUT_DIR="$PROJECT_DIR/models/tts/finetuned/$VOICE_NAME"

# Tham số train (override bằng env nếu cần)
BATCH_SIZE="${BATCH_SIZE:-3200}"        # frames/GPU - vừa cho 12GB VRAM
NUM_WORKERS="${NUM_WORKERS:-8}"
WARMUP_UPDATES="${WARMUP_UPDATES:-500}"
SAVE_UPDATES="${SAVE_UPDATES:-2000}"
LAST_UPDATES="${LAST_UPDATES:-1000}"
EPOCHS="${EPOCHS:-100}"                 # dataset nhỏ -> nhiều epoch

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

[ -f "$PRETRAIN_CKPT" ] || { echo "[ERROR] Thiếu model gốc: $PRETRAIN_CKPT (chạy scripts/install/06_models_download.sh)"; exit 1; }
[ -d "$F5_DIR/data/your_dataset" ] || { echo "[ERROR] Chưa có dataset. Chạy prepare_dataset.py trước."; exit 1; }

cd "$F5_DIR"
source "$PROJECT_DIR/.venv/bin/activate"

# pyproject của F5-TTS chỉ ghi accelerate>=0.33.0 nên pip kéo bản mới nhất, mà từ
# 1.10 trở đi finetune_cli chết với "AcceleratedOptimizer has no attribute
# '_modules'". Đo được 1.0.1 chạy được, 1.10.1 thì không.
ACC="$(python -m pip show accelerate 2>/dev/null | sed -n 's/^Version: //p')"
echo "=== [0/5] accelerate hiện có: ${ACC:-chưa cài} ==="
if [ -n "$ACC" ] && [ "$(printf '%s\n1.0.1\n' "$ACC" | sort -V | tail -1)" != "1.0.1" ]; then
    echo "  -> hạ về 1.0.1"
    python -m pip install --no-input "accelerate==1.0.1" >/dev/null
fi

echo "=== [1/4] Chuẩn bị metadata ==="
python prepare_metadata.py

echo "=== [2/4] Vocab: dùng vocab ViVoice (đã đủ tiếng Việt) ==="
# Fine-tune từ checkpoint ViVoice nên PHẢI dùng đúng vocab của nó
# (không extend embedding như flow train-từ-model-gốc-tiếng-Anh của repo)
cp "$PRETRAIN_VOCAB" data/your_training_dataset/vocab.txt

python - <<'EOF'
# Cảnh báo nếu dataset chứa ký tự ngoài vocab (sẽ bị bỏ qua khi train)
vocab = set(l.rstrip("\n") for l in open("data/your_training_dataset/vocab.txt", encoding="utf8"))
missing = set()
for line in open("data/your_training_dataset/metadata.csv", encoding="utf8"):
    if "|" in line:
        for ch in line.split("|", 1)[1].strip():
            if ch not in vocab:
                missing.add(ch)
if missing:
    print(f"[WARN] {len(missing)} ký tự ngoài vocab: {sorted(missing)}")
    print("       Sửa transcript (thường do ký tự lạ/số chưa viết thành chữ) rồi chạy lại.")
else:
    print("[OK] Toàn bộ ký tự trong dataset đều có trong vocab.")
EOF

echo "=== [3/4] Trích xuất đặc trưng ==="
python src/f5_tts/train/datasets/prepare_csv_wavs.py \
    data/your_training_dataset data/your_training_dataset --workers "$NUM_WORKERS"

# trainer.py đọc start_update từ checkpoint. Bản ViVoice có update=540000 nên
# skipped_epoch vượt xa $EPOCHS -> vòng lặp train không chạy lần nào, script vẫn
# báo "xong" sau hai phút và lưu lại đúng model gốc. Dùng bản sao có update=0.
echo "=== [3.5/4] Đặt lại bộ đếm bước của checkpoint gốc ==="
PRETRAIN_START="$PROJECT_DIR/models/tts/F5-TTS-Vietnamese-ViVoice/model_finetune_start.pt"
python "$PROJECT_DIR/scripts/reset_update.py" --src "$PRETRAIN_CKPT" --dst "$PRETRAIN_START"

echo "=== [4/4] Fine-tuning (pretrain: ViVoice) ==="
python src/f5_tts/train/finetune_cli.py \
    --exp_name F5TTS_Base \
    --dataset_name your_training_dataset \
    --batch_size_per_gpu "$BATCH_SIZE" \
    --epochs "$EPOCHS" \
    --num_warmup_updates "$WARMUP_UPDATES" \
    --save_per_updates "$SAVE_UPDATES" \
    --last_per_updates "$LAST_UPDATES" \
    --finetune \
    --log_samples \
    --pretrain "$PRETRAIN_START"

echo "=== Đóng gói kết quả ==="
mkdir -p "$OUTPUT_DIR"
CKPT_OUT="$F5_DIR/ckpts/your_training_dataset/model_last.pt"
[ -f "$CKPT_OUT" ] || { echo "[ERROR] Không tìm thấy checkpoint output: $CKPT_OUT"; exit 1; }
cp "$CKPT_OUT" "$OUTPUT_DIR/model_last.pt"
cp data/your_training_dataset/vocab.txt "$OUTPUT_DIR/vocab.txt"

# Giọng mẫu lúc chạy. KHÔNG lấy bừa file đầu tiên: F5-TTS bắt chước cả ngữ điệu
# của đoạn mẫu, và đoạn dài bị cắt về 12s làm chậm thêm ~96ms mỗi lượt.
# pick_ref.py chọn đoạn 3-8s, ưu tiên câu mở đầu bằng "Dạ".
python "$PROJECT_DIR/scripts/pick_ref.py" \
    --dataset "$F5_DIR/data/your_dataset" \
    --name "$VOICE_NAME" \
    --out "$PROJECT_DIR/models/tts/ref_voices/$VOICE_NAME.wav"

echo ""
echo "============================================"
echo " Train xong! Cập nhật .env để dùng giọng mới:"
echo "   F5TTS_CKPT_PATH=./models/tts/finetuned/$VOICE_NAME/model_last.pt"
echo "   F5TTS_VOCAB_PATH=./models/tts/finetuned/$VOICE_NAME/vocab.txt"
echo "   F5TTS_REF_AUDIO=./models/tts/ref_voices/$VOICE_NAME.wav"
echo "   F5TTS_REF_TEXT=<nội dung file $VOICE_NAME.txt>"
echo " Rồi restart: bash scripts/start_services.sh"
echo "============================================"
