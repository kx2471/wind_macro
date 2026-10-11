"""직접 걸어가는 길을 기록한다. 기록한 길은 nav.py와 hunt.py가 그대로 따라간다.

사용: .venv/bin/python record.py 지금있는방이름
예:   .venv/bin/python record.py 만번한비밀세작의집2
      .venv/bin/python record.py 만번한비밀세작의집1 wait   (지금 맵을 떠나 1번 방에 들어오면 시작)

실행해 두고 게임에서 다음 방, 그다음 방으로 평소처럼 걸어가면 된다.
- 밟은 칸을 data/walls/방이름.json 의 밟아 본 칸으로 저장한다.
- 맵이 바뀌면 방 번호를 하나 올리고, 나간 칸을 data/ports_fixed.tsv 에 출구로 적는다.
끝내려면 Ctrl+C.
"""

import re
import sys
import time
from pathlib import Path

import nav
import wind


def record(room, wait_for_change=False):
    found = re.fullmatch(r"(.*?)(\d+)", room)
    base, number = found[1], int(found[2])
    if wait_for_change:
        # 지금 있는 맵을 떠나 room 에 들어올 때까지 기다린다
        while wind.game_window() is None:
            time.sleep(0.3)
        before = wind.snapshot("map_name")
        print(f"지금 맵을 떠나 {room} 에 들어오면 기록을 시작한다", flush=True)
        while wind.game_window() is None or wind.snapshot("map_name") == before:
            time.sleep(0.2)
        time.sleep(wind.ROAM["map_wait"])
    fixed = Path(__file__).parent / "data" / "ports_fixed.tsv"
    while True:
        name = f"{base}{number}"
        map_image = None
        while map_image is None:
            time.sleep(0.3)
            try:
                if wind.game_window() is not None and nav.read_position() is not None:
                    map_image = wind.snapshot("map_name")
            except wind.Abort:
                pass
        walls, free = nav.load_memory(name)
        last = None
        print(f"{name}: 기록 시작", flush=True)
        try:
            while True:
                time.sleep(0.05)
                if wind.game_window() is None:
                    continue
                try:
                    title = wind.snapshot("map_name")
                    here = nav.read_position()
                except wind.Abort:
                    continue  # 읽는 순간에 다른 창이 앞으로 왔다
                if title is None:
                    continue
                if title != map_image:
                    break
                if here is not None and here != last:
                    if last is None:
                        print(f"  들어온 자리 {here}", flush=True)
                    free.add(here)
                    last = here
        finally:
            nav.save_memory(name, walls - free, free)
        following = f"{base}{number + 1}"
        print(f"  {name} {last} 에서 맵이 바뀌었다 → {following} 로 적는다 (밟은 칸 {len(free)}개)", flush=True)
        with fixed.open("a", encoding="utf-8") as file:
            file.write(f"{name}\t{last[0]}\t{last[1]}\t{following}\n")
        number += 1
        time.sleep(wind.ROAM["map_wait"])


if __name__ == "__main__":
    try:
        record(sys.argv[1], len(sys.argv) > 2 and sys.argv[2] == "wait")
    except KeyboardInterrupt:
        print("기록 끝")
