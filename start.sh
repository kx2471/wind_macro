#!/bin/zsh
# 지금 서 있는 맵에서 흉가 사냥을 시작한다.
# 성이나 흉가입구에서 PICK=1 ./start.sh 로 켜면 "/출 흉가"로 빈 흉가를 골라 입구 앞에 노란비서를 버리고 들어간다. 끄기: 게임 창에서 F7, 또는 ./stop.sh
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
rm -f logs/lap.json   # 바퀴 시작 기록은 새로 켤 때 지운다 (껐다 켠 사이의 시간과 경험치가 섞이지 않게)
log="logs/haunt-$(date +%m%d-%H%M%S).log"
# 돌 흉가 묶음: 방 안이면 그 방의 묶음, 성이나 입구면 그 성의 제2 묶음 (다른 성의 흉가에서 다시 켜도 맞게)
haunt=$(python3 - "$room" <<'PY'
import re, sys
room = sys.argv[1]
inside = re.fullmatch(r"((?:제\d+)?.+흉가)\d+", room)
castle = re.fullmatch(r"부여(.+)성|(.+)흉가입구", room)
print(inside[1] if inside else f"제2{castle[1] or castle[2]}흉가" if castle else "제2상곡흉가")
PY
)
haunt="${HAUNT:-$haunt}"   # HAUNT=제3천안궁흉가 ./start.sh 처럼 돌 묶음을 직접 정할 수도 있다
[ -n "$PICK" ] && export WIND_PICK=1
(caffeinate -dims .venv/bin/python -u hunt.py "$room" --haunt="$haunt" --overnight > "$log" 2>&1 &)
pgrep -f minigame_daemon.sh > /dev/null || (nohup ./minigame_daemon.sh > /dev/null 2>&1 &)
echo "$room 에서 시작했다 ($haunt). 로그: $log"
