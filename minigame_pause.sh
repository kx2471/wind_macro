#!/bin/zsh
# 미니게임 창이 떠 있는 동안 사냥 매크로를 세워 두고, 창이 사라지면(직접 풀었거나 시간이 다 됐거나) 다시 움직인다.
# watch.sh가 창을 보면 부른다. 매크로는 끄지 않고 멈춰만 둔다 (SIGSTOP → SIGCONT). 그래서 어느 방에 있었는지 등은 그대로다.
# 사용: ./minigame_pause.sh            (시험할 때는 PATTERN="다른 프로세스 이름" MAX=초 로 바꿔 부른다)
cd "$(dirname "$0")"
pattern="${PATTERN:-hunt.py}"
pkill -STOP -f "$pattern"
# 기본 공격 키(Space)가 눌린 채로 멈추면 창을 푸는 데 방해가 된다. 뗀다
.venv/bin/python -c "
import wind
key = wind.KEYS.get('basic')
if key:
    wind._post(wind.KEYCODES[key], False)
" 2>/dev/null
echo "$(date +%T) 미니게임 창이 떠서 매크로를 세웠다" >> logs/minigame.log
# 한 번만 풀어 본다 (운영자가 자동 풀이를 허용했다는 답변을 사용자가 확인. 틀려도 다시 하지 않는다). 시험 때는 SOLVE=0
if [ "${SOLVE:-1}" = "1" ] && [ "$pattern" = "hunt.py" ]; then
  .venv/bin/python minigame_solve.py >> logs/minigame.log 2>&1
fi
gone=0
for i in $(seq 1 $(( ${MAX:-120} / 2 ))); do   # 길어도 MAX초(기본 2분) 뒤에는 다시 움직인다
  sleep 2
  if [ "$(.venv/bin/python minigame.py 2>/dev/null | tail -1 | cut -d' ' -f1)" = "minigame" ]; then gone=0; else gone=$((gone + 1)); fi
  if [ $gone -ge 2 ]; then break; fi
done
# 매크로가 아직 멈춰 있을 때 메시지창에서 "성공하였습니다."를 찾는다 (매크로가 돌면 새 메시지에 밀려 올라간다)
if [ "${SOLVE:-1}" = "1" ] && [ "$pattern" = "hunt.py" ]; then
  .venv/bin/python minigame_result.py >> logs/minigame.log 2>&1
fi
pkill -CONT -f "$pattern"
echo "$(date +%T) 창이 사라져 매크로를 다시 움직인다" >> logs/minigame.log
