"""직접 걸어가는 길을 통째로 기록한다 (성 → 장터처럼 번호 없는 맵용. 번호 붙은 방은 record.py).

사용: .venv/bin/python -u record_route.py 이름        (끝내기: 게임 창에서 F8, 또는 Ctrl+C)

logs/route-이름/ 에 남기는 것:
- route.txt: 시각, 맵(아는 이름 또는 "새맵N"), 좌표가 바뀔 때마다 한 줄. 맵이 바뀌면 "맵 바뀜" 줄. 누른 키도 한 줄씩.
- title-새맵N.bin: 처음 보는 맵의 이름 그림 (나중에 data/titles/에 이름을 붙여 넣는다)
- 화면 그림: 맵이 바뀔 때, 그리고 좌표가 안 바뀐 채 키가 눌릴 때(상인과 거래할 때) 1초에 한 장까지
게임은 건드리지 않는다. 보기만 한다.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import Quartz

import nav
import wind

out = Path(__file__).parent / "logs" / f"route-{sys.argv[1]}"
out.mkdir(parents=True, exist_ok=True)
log = (out / "route.txt").open("a", encoding="utf-8")
titles = {file.read_bytes(): file.stem for file in (Path(__file__).parent / "data" / "titles").glob("*.bin")}
keys, done = [], threading.Event()


def say(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()


def on_event(proxy, kind, event, refcon):
    if kind == Quartz.kCGEventKeyDown and Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData) != wind.MAGIC:
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        name = wind.KEYNAMES.get(code, f"code{code}")
        if flags & Quartz.kCGEventFlagMaskShift:
            name = "shift+" + name
        if flags & Quartz.kCGEventFlagMaskControl:
            name = "ctrl+" + name
        keys.append(name)
    return event


def listen():
    tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap, Quartz.kCGEventTapOptionListenOnly,
                                  Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown), on_event, None)
    if tap is None:
        say("키를 읽을 권한이 없다. 좌표와 화면만 기록한다")
        return
    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    Quartz.CFRunLoopRun()


def name_of(title):
    for known, name in titles.items():
        if wind.same_title(known, title):
            return name
    name = f"새맵{sum(1 for n in titles.values() if n.startswith('새맵')) + 1}"
    titles[title] = name
    (out / f"title-{name}.bin").write_bytes(title)
    return name


def shot(tag):
    path = out / f"{time.strftime('%H%M%S')}-{tag}.jpg"
    try:
        subprocess.run(["screencapture", "-x", "-D", str(wind.game_display()), "-t", "jpg", str(path)], timeout=10)
        subprocess.run(["sips", "-Z", "1280", str(path)], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pass


threading.Thread(target=listen, daemon=True).start()
say(f"기록 시작 ({sys.argv[1]}). 끝내려면 게임 창에서 F8")
current, last, last_shot = None, None, 0.0
try:
    while not done.is_set():
        time.sleep(0.05)
        pressed, keys[:] = keys[:], []
        if "f8" in pressed:
            break
        if wind.game_window() is None:
            continue
        try:
            title, here = wind.snapshot("map_name"), nav.read_position()
        except wind.Abort:
            continue
        if title is not None and here is not None:
            name = name_of(title)
            if name != current:
                say(f"맵 바뀜: {current} {last} → {name} {here}")
                current, last = name, None
                shot("map")
            if here != last:
                say(f"{name} {here}")
                last = here
        for key in pressed:
            if key not in ("up", "down", "left", "right"):
                say(f"키 {key}  ({current} {last})")
                if time.monotonic() - last_shot > 1.0:
                    time.sleep(0.4)  # 키를 누른 결과가 화면에 뜬 뒤에 찍는다
                    shot(f"key-{key.replace('+', '_')}")
                    last_shot = time.monotonic()
except KeyboardInterrupt:
    pass
say("기록 끝")
