#!/bin/zsh
# 미니게임 지킴이(minigame_daemon.py)를 끝없이 다시 띄운다. start.sh와 watch.sh가 안 돌고 있으면 켠다. 끄기: ./stop.sh
cd "$(dirname "$0")"
while true; do
  .venv/bin/python -u minigame_daemon.py >> logs/minigame-daemon.log 2>&1
  sleep 1
done
