"""미니게임 창을 1초마다 보고, 뜨면 minigame_pause.sh(매크로 세움 → 풀이 → 다시 움직임)를 부른다.

감시(watch.sh)에 얹어 두었더니 감시가 화면 찍기에 매달려 6시간 멈춘 사이 03:59 창을 놓쳤다 (2026-10-13).
그래서 따로 돈다. 스스로 멈춘 것을 알아채면(6초 동안 한 바퀴를 못 돌면) 죽고, minigame_daemon.sh가 다시 띄운다.
logs/minigame.beat 파일의 시각이 살아 있다는 표시다.
"""

import os
import subprocess
import threading
import time
from pathlib import Path

import minigame

HERE = Path(__file__).parent
BEAT = HERE / "logs" / "minigame.beat"
RENEW = 1200  # 이만큼 돌면 끝낸다 (다시 띄워진다). 오래 도는 프로세스에 메모리가 쌓이는 것을 피한다
alive = time.monotonic()
busy = False  # 풀이 도우미가 도는 동안에는 오래 걸려도 죽이지 않는다


def watchdog():
    while True:
        time.sleep(1)
        # 처음에는 20초였는데, 화면 읽기에 매달려 22초를 못 본 적이 있다 (2026-10-13 13:08). 창은 20초면 닫히므로 6초로 줄였다
        if time.monotonic() - alive > (200 if busy else 6):
            print(f"{time.strftime('%H:%M:%S')} 6초 동안 한 바퀴를 못 돌아서 끝낸다", flush=True)
            os._exit(1)


def hunting():
    """사냥 매크로가 돌고 있는가. 꺼져 있을 때(사용자가 직접 조작할 때)는 화면도 마우스도 건드리지 않는다."""
    return subprocess.run(["pgrep", "-f", "hunt.py"], capture_output=True).returncode == 0


def seen():
    patch = minigame.look()
    return patch is not None and minigame.is_noise(patch)


threading.Thread(target=watchdog, daemon=True).start()
born = time.monotonic()
print(f"{time.strftime('%H:%M:%S')} 미니게임 지킴이 시작", flush=True)
while time.monotonic() - born < RENEW:
    alive = time.monotonic()
    BEAT.write_text(time.strftime("%H:%M:%S"))
    if not hunting():
        time.sleep(2)
        continue
    if seen():
        time.sleep(0.25)
        if seen():  # 한 번 더 봐서 번쩍이는 효과에 속지 않게
            print(f"{time.strftime('%H:%M:%S')} 미니게임 창이 떴다", flush=True)
            busy = True
            try:
                subprocess.run(["./minigame_pause.sh"], cwd=HERE, timeout=180)
            except subprocess.TimeoutExpired:
                subprocess.run(["pkill", "-CONT", "-f", "hunt.py"])
            busy = False
            continue
    time.sleep(0.8)
