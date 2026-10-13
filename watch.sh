#!/bin/zsh
# screencapture가 끝나지 않고 매달려서 감시가 6시간 멈춘 적이 있다 (2026-10-13 01:08 ~ 07:24). 10초가 넘으면 죽인다
snap() {
  screencapture "$@" 2>/dev/null &
  local pid=$! n=0
  while kill -0 $pid 2>/dev/null; do
    sleep 0.2; n=$((n+1))
    if [ $n -ge 50 ]; then kill -9 $pid 2>/dev/null; echo "$(date +%H:%M:%S) 화면 찍기가 10초 넘게 걸려서 죽였다"; return 1; fi
  done
  return 0
}

# 사냥 매크로를 570초 동안 지켜본다. 꺼져 있으면 다시 켠다 (F7로 끈 경우는 다시 켜지 않는다). 끝에 요약을 찍는다.
cd "$(dirname "$0")"
mkdir -p logs/watch logs/suspect
lastL=""; lastn=0; found=""
touch logs/minigame.log; minilines=$(wc -l < logs/minigame.log | tr -d ' ')
# 세워 둔 채로 남지 않게: 다시 움직이게 할 도우미가 안 돌고 있으면 매크로를 깨운다
pgrep -f minigame_pause.sh > /dev/null || pkill -CONT -f "hunt.py"
for i in $(seq 1 38); do
  # 15초마다 화면을 한 장 남긴다 (최근 3시간치). 미니게임 창 같은 것이 떴을 때 무엇이었는지 나중에 볼 수 있게
  shot="logs/watch/$(date +%m%d-%H%M%S).jpg"
  snap -x -t jpg "$shot" && sips -Z 1280 "$shot" > /dev/null 2>&1
  find logs/watch -name '*.jpg' -mmin +180 -delete 2>/dev/null
  # 평소에 드문 줄(맵 이름 가림, 선택창이 안 뜸, 키가 안 먹음, 오류)이 새로 찍혔으면 그 화면을 logs/suspect/에 따로 둔다
  cur=$(ls -t logs/haunt-*.log | head -1); n=$(wc -l < "$cur" | tr -d ' ')
  if [ "$cur" = "$lastL" ] && [ "$n" -gt "$lastn" ]; then
    odd=$(tail -n +$((lastn + 1)) "$cur" | grep -a '가려졌다\|선택창이 안 떴다\|싸우는 중에 맵이\|오류 \|입력창이 열려\|Esc가 안 먹\|힐이 안 먹' | tail -1 | cut -c1-90)
    if [ -n "$odd" ]; then
      cp "$shot" "logs/suspect/$(basename "$shot")" 2>/dev/null
      case "$odd" in *"선택창이 안 떴다"*) snap -x "logs/suspect/full-$(date +%m%d-%H%M%S).png" 2>/dev/null;; esac
      echo "$(date +%T) 눈여겨볼 줄: $odd → 화면 logs/suspect/$(basename "$shot")"
    fi
  fi
  lastL="$cur"; lastn="$n"
  if ! pgrep -f "hunt.py" > /dev/null; then
    L=$(ls -t logs/haunt-*.log | head -1)
    if tail -12 "$L" | grep -aq "을 눌러서 끝낸다"; then echo "$(date +%T) F7로 꺼져 있다. 다시 켜지 않는다"; break; fi
    echo "$(date +%T) 꺼져 있다: $(grep -a '오류\|죽었다\|되살아나지\|Traceback\|Error' "$L" | tail -2 | cut -c1-150)"
    if ! ./start.sh; then
      # 맵을 모르겠다 = 게임이 첫 화면으로 나와 있을 수 있다. 다시 접속해 보고 켠다 (아직 로딩 중이면 다음 확인 때 또 한다)
      echo "$(date +%T) 못 켰다. 다시 접속해 본다"
      ./reconnect.sh
      ./start.sh
    fi
  elif [ "$(tail -9 "$(ls -t logs/haunt-*.log | head -1)" | grep -ac '갇혔다')" -ge 3 ]; then
    # 몹이 막은 칸을 벽으로 잘못 기억해 제자리에서 맴돈다 (2026-10-12 05:41, 06:35). 껐다 켜면 기억이 지워져 풀린다
    echo "$(date +%T) 갇혀서 맴돈다. 껐다 켠다"
    ./stop.sh
  fi
  # 미니게임은 따로 도는 지킴이(minigame_daemon.py)가 1초마다 보고 푼다. 여기서는 지킴이가 살아 있는지와 새 기록만 본다
  beat=$(( $(date +%s) - $(stat -f %m logs/minigame.beat 2>/dev/null || echo 0) ))
  if ! pgrep -f minigame_pause.sh > /dev/null && [ $beat -gt 30 ]; then
    echo "$(date +%T) 미니게임 지킴이가 ${beat}초째 조용하다. 다시 띄운다"
    pkill -f minigame_daemon; sleep 0.5
    (nohup ./minigame_daemon.sh > /dev/null 2>&1 &)
  fi
  for j in 1 2 3 4 5 6; do
    m=$(wc -l < logs/minigame.log | tr -d ' ')
    if [ "$m" -gt "$minilines" ]; then
      # 풀이가 끝날 때까지(도우미가 끝날 때까지) 기다렸다가 기록을 찍고 감시를 끝낸다 (지켜보는 쪽이 결과를 보게)
      for k in $(seq 1 70); do pgrep -f minigame_pause.sh > /dev/null || break; sleep 2; done
      echo "$(date +%T) 미니게임 창이 떴다. 기록:"; tail -n +$((minilines + 1)) logs/minigame.log
      found=1; break
    fi
    sleep 2
  done
  if [ -n "$found" ]; then break; fi
done
L=$(ls -t logs/haunt-*.log | head -1)
echo "$(date +%T) 로그 $L, 프로세스 $(pgrep -f hunt.py | wc -l | tr -d ' ')개"
echo "쏨 $(grep -ao '썼다=True 쿨글자=True' $L | wc -l | tr -d ' ') / 헛발 $(grep -ac '헬파이어가 안 나갔다' $L) / 차례인데 못 씀 $(grep -ao '쓸차례=True 썼다=False' $L | wc -l | tr -d ' ') / 싸움 $(grep -ac '빠른 싸움' $L) / 죽음 $(grep -ac '죽었다' $L) / 부활 $(grep -ac '살아났다' $L) / 오류 $(grep -ac '오류 ' $L)"
grep -a "오류 \|죽었다\|살아났다\|되살아나지\|한 바퀴 끝" $L | tail -3 | cut -c1-140
grep -a "^== " $L | tail -1 | cut -c1-48
top -l 1 -o mem -n 40 -stats pid,command,mem | grep -i python | head -2
