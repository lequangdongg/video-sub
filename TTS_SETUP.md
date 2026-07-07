# Đọc văn bản → Giọng nói (VietTTS) — cài đặt & chạy

Tab **"Đọc văn bản"** dùng [VietTTS (dangvansam)](https://github.com/dangvansam/viet-tts) chạy dưới
dạng **server HTTP OpenAI-compatible**. App (venv riêng) gọi sang server này qua HTTP nên 2 bên
độc lập về Python/thư viện.

## Đã cài sẵn ở máy này
- VietTTS: `/Users/dongquang/Desktop/viet-tts` (venv `.venvuv`, Python 3.11 qua `uv`)
- Model (~2.2GB) tự tải về `pretrained-models/` lần chạy đầu.

## Chạy
```bash
# 1) Bật VietTTS server (giữ cửa sổ này) — lần đầu nạp model ~10s
./tts_server.sh                 # http://127.0.0.1:8298

# 2) Bật web như bình thường (cửa sổ khác)
./serve.sh                      # hoặc ./web.sh (dev)
```
Vào web → tab **"Đọc văn bản"** → nhập text → chọn giọng (nữ/nam) → **▶ nghe trước** →
**Tạo giọng nói** → tải **.mp3** + **.srt** (khớp thời gian từng câu).

Đổi URL server nếu cần: `VIETTTS_URL=http://host:port ./serve.sh`.

## VietTTS repo chưa hỗ trợ macOS chính thức — các bản vá đã áp dụng
Cài trên macOS arm64 (M-series) cần 6 chỉnh sửa (xem chi tiết trong `viet-tts/`):
1. Python 3.11 qua `uv venv --python 3.11` (system 3.14 quá mới; brew python@3.11 lỗi pyexpat).
2. `onnxruntime-gpu` → `onnxruntime` (gói GPU không có bản mac arm64).
3. Ghim `ruamel.yaml==0.17.28` (bản mới vỡ `hyperpyyaml`).
4. `viettts/utils/frontend_utils.py`: bọc `TTSnorm(...)` trong try/except — `vinorm` là binary Linux.
5. `viettts/model.py`: chỉ `.half()` khi `torch.cuda.is_available()` (fp16 không chạy trên CPU).
6. `viettts/utils/common.py fade_in_out_audio`: `.clone()` trước khi sửa in-place (inference_mode).
Bắt buộc env: `PYTORCH_ENABLE_MPS_FALLBACK=1` (đã có trong `tts_server.sh`).

## Hiệu năng (M3 Pro, CPU/MPS)
~13s suy luận + ~7s nạp model cho 1 câu. Đọc theo lô ổn, không realtime.
24 giọng dựng sẵn (7 nam / 17 nữ), lấy động từ `/v1/voices`.
