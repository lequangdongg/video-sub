#!/usr/bin/env bash
# clean.sh — xoá sạch input/, output/ và webapp/jobs/ (giữ .gitkeep)
#   ./clean.sh        # hỏi xác nhận
#   ./clean.sh -y     # xoá luôn không hỏi
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

YES=0
[[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]] && YES=1

echo "Sẽ xoá toàn bộ nội dung trong:"
echo "  - input/      (video nguồn)"
echo "  - output/     (kết quả)"
echo "  - webapp/jobs/ (job của giao diện web)"

if [[ $YES -eq 0 ]]; then
  read -r -p "Tiếp tục? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Huỷ."; exit 0; }
fi

for d in input output webapp/jobs; do
  if [[ -d "$d" ]]; then
    find "$d" -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
  fi
done
echo "Đã dọn xong."
