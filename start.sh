#!/bin/zsh
# 지금 서 있는 맵에서 흉가 사냥을 시작한다. 끄기: 게임 창에서 F7, 또는 ./stop.sh
# 맵 이름은 화면 위의 맵 이름 그림을 data/titles/와 견줘서 알아낸다 (흉가 방, 흉가입구, 부여상곡성에서 시작할 수 있다).
cd "$(dirname "$0")"
if pgrep -f "hunt.py" > /dev/null; then echo "이미 돌고 있다. 끄려면 F7 또는 ./stop.sh"; exit 1; fi
osascript -e 'tell application "MapleStory Worlds" to activate'; sleep 1.5
room=$(.venv/bin/python - <<'PY'
import wind
from pathlib import Path
title = wind.snapshot("map_name")
print(next((f.stem for f in Path("data/titles").glob("*.bin") if title and f.read_bytes()[:len(title)] == title), ""))
PY
)
if [ -z "$room" ]; then echo "지금 맵을 모르겠다 (게임 창이 화면에 보여야 한다)"; exit 1; fi
log="logs/haunt-$(date +%m%d-%H%M%S).log"
(caffeinate -dims .venv/bin/python -u hunt.py "$room" --haunt=제2상곡흉가 --overnight > "$log" 2>&1 &)
echo "$room 에서 시작했다. 로그: $log"
