#!/bin/zsh
# 사냥 매크로를 끈다.
pkill -f "hunt.py" && echo "껐다" || echo "돌고 있지 않다"
# 미니게임 지킴이는 그대로 둔다 (매크로가 없으면 하는 일이 없다). 지킴이까지 끄려면: pkill -f minigame_daemon
