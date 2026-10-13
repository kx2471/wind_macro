#!/bin/zsh
# 게임이 바람의나라 첫 화면(처음하기/이어하기)으로 나와 있을 때 다시 접속한다: "이어하기" → 이름 확인 창의 OK.
# 월드가 다시 로드되면 이 화면으로 나온다 (2026-10-12 15:08). 접속하면 끊긴 자리에 그대로 선다.
cd "$(dirname "$0")"
osascript -e 'tell application "MapleStory Worlds" to activate'; sleep 1.5
.venv/bin/python - <<'PY'
import time
import nav
nav.click(1440, 746)  # 이어하기
time.sleep(2.5)
nav.click(1052, 743)  # OK (이름 칸에 캐릭터 이름이 들어 있고 암호는 안 묻는다)
time.sleep(6)
PY
