#!/bin/zsh
# 사냥 매크로를 끈다.
pkill -f "hunt.py" && echo "껐다" || echo "돌고 있지 않다"
