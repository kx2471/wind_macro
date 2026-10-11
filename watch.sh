#!/bin/zsh
# 사냥 매크로를 570초 동안 지켜본다. 꺼져 있으면 다시 켠다 (F7로 끈 경우는 다시 켜지 않는다). 끝에 요약을 찍는다.
cd "$(dirname "$0")"
for i in $(seq 1 38); do
  if ! pgrep -f "hunt.py" > /dev/null; then
    L=$(ls -t logs/haunt-*.log | head -1)
    if tail -12 "$L" | grep -aq "을 눌러서 끝낸다"; then echo "$(date +%T) F7로 꺼져 있다. 다시 켜지 않는다"; break; fi
    echo "$(date +%T) 꺼져 있다: $(grep -a '오류\|죽었다\|되살아나지\|Traceback\|Error' "$L" | tail -2 | cut -c1-150)"
    ./start.sh
  fi
  sleep 15
done
L=$(ls -t logs/haunt-*.log | head -1)
echo "$(date +%T) 로그 $L, 프로세스 $(pgrep -f hunt.py | wc -l | tr -d ' ')개"
echo "쏨 $(grep -ao '썼다=True 쿨글자=True' $L | wc -l | tr -d ' ') / 헛발 $(grep -ac '헬파이어가 안 나갔다' $L) / 차례인데 못 씀 $(grep -ao '쓸차례=True 썼다=False' $L | wc -l | tr -d ' ') / 싸움 $(grep -ac '빠른 싸움' $L) / 죽음 $(grep -ac '죽었다' $L) / 부활 $(grep -ac '살아났다' $L) / 오류 $(grep -ac '오류 ' $L)"
grep -a "오류 \|죽었다\|살아났다\|되살아나지\|한 바퀴 끝" $L | tail -3 | cut -c1-140
grep -a "^== " $L | tail -1 | cut -c1-48
top -l 1 -o mem -n 40 -stats pid,command,mem | grep -i python | head -2
