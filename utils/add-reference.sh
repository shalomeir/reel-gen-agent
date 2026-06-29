#!/usr/bin/env bash
#
# add-reference.sh - YouTube/TikTok 등의 URL을 reference_video/ 폴더로 내려받는다.
#
# 왜 스크립트로 두는가: URL마다 다운로드 옵션(포맷 병합, 파일명 규칙, 메타데이터)을
# 손으로 맞추면 결과가 들쭉날쭉해진다. 한 군데 고정해두면 누가 언제 실행해도
# reference_video/ 안의 파일명·화질 규칙이 같아진다.
#
# 사용법:
#   utils/add-reference.sh "<url>"
#
# 출력: 저장된 파일 경로 한 줄(STDOUT). list.md 갱신은 호출하는 쪽에서 한다.

set -euo pipefail

URL="${1:-}"
if [[ -z "$URL" ]]; then
  echo "usage: utils/add-reference.sh \"<youtube_or_tiktok_url>\"" >&2
  exit 1
fi

# 스크립트 위치 기준으로 프로젝트 루트와 저장 폴더를 잡는다(어디서 호출해도 동작).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="$PROJECT_ROOT/reference_video"
mkdir -p "$DEST_DIR"

# 파일명: "<제목 80자> [<source>-<id>].<ext>" 형태로 출처와 원본 ID를 보존한다.
# - 화질: 가능한 최고 화질 영상+오디오를 mp4로 병합(없으면 단일 best).
# - --no-playlist: 재생목록 URL이라도 영상 1개만.
# - --restrict-filenames: 공백/특수문자 제거로 셸·git에서 안전.
OUTPUT_TEMPLATE="$DEST_DIR/%(title).80s [%(extractor_key)s-%(id)s].%(ext)s"

# 다운로드 후 실제 저장 경로를 받아오기 위해 --print after_move:filepath 사용.
SAVED_PATH="$(
  yt-dlp \
    --no-playlist \
    --restrict-filenames \
    -f "bv*+ba/b" \
    --merge-output-format mp4 \
    -o "$OUTPUT_TEMPLATE" \
    --print after_move:filepath \
    --no-simulate \
    "$URL"
)"

echo "$SAVED_PATH"
