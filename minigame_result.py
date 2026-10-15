"""미니게임을 푼 뒤 오른쪽 메시지창에 "성공하였습니다."가 떴는지 본다. minigame_pause.sh가 매크로를 다시 움직이기 전에 부른다.

예전에는 끝난 뒤 헬파이어가 나가는지(실패하면 마법이 한동안 막힌다)로 성공을 짐작했는데,
사용자가 "풀자마자 상태창에 성공 메시지가 있나를 기준으로 확인해. 스크롤하면 지나간 것도 볼 수 있어"라고 했다 (2026-10-15).
성공하면 "경험치가 900000(4%) 올랐습니다." 다음 줄에 "성공하였습니다."가 나온다 (2026-10-14 13:51 화면).
메시지창은 휠 한 칸에 한 줄씩 넘어간다. 마우스가 메시지창 위에 있어야 한다.
"""

import sys
import time
from pathlib import Path

import numpy as np
import Quartz

import wind

HERE = Path(__file__).parent
BOX = (1380, 660, 390, 150)  # 메시지창 (게임 창 기준 x, y, 너비, 높이). 다섯 줄이 보인다
INK = (58, 58, 58)  # 메시지 글자색
SUCCESS = np.load(HERE / "data" / "msg_success.npy")  # "성공하였습니다." 글자 모양 (22×173)
CURSOR = (1570, 730)  # 메시지창 안


def picture():
    shot = wind.grab(*BOX)
    if shot is None:
        return None
    raw, stride, scale = shot
    rows = len(raw) // stride
    wide = int(round(BOX[2] * scale))
    step = int(round(scale))
    return np.frombuffer(raw, np.uint8).reshape(rows, stride)[:, :wide * 4].reshape(rows, wide, 4)[::step, ::step, 2::-1].copy()


def has_success(image):
    ink = np.abs(image.astype(np.int64) - np.array(INK)).sum(2) < 15
    rows = np.nonzero(ink.sum(1) > 0)[0]
    if not len(rows):
        return False
    tall, wide = SUCCESS.shape
    for run in np.split(rows, np.nonzero(np.diff(rows) > 1)[0] + 1):
        for y in range(int(run[0]), int(run[-1]) - tall + 2, 24):  # 붙어 있는 여러 줄도 24픽셀씩 나눠 본다
            band = ink[y:y + tall]
            cols = np.nonzero(band.any(0))[0]
            if band.shape[0] < tall or not len(cols):
                continue
            part = band[:, cols[0]:cols[0] + wide]
            if part.shape == SUCCESS.shape and (part != SUCCESS).sum() <= 40:
                return True
    return False


def post(event):
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def wheel(lines_up):
    for _ in range(abs(lines_up)):
        post(Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, 1 if lines_up > 0 else -1))
        time.sleep(0.06)
    time.sleep(0.3)


def check(limit=20):
    """(성공 메시지를 찾았는가, 위로 넘긴 줄 수). 못 찾으면 limit줄까지 한 줄씩 위로 넘겨 본다."""
    origin = wind.game_window()
    if origin is None:
        return None, 0
    time.sleep(0.5)  # OK를 누른 뒤 메시지가 뜰 틈
    image = picture()
    if image is not None and has_success(image):
        return True, 0
    post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (origin[0] + CURSOR[0], origin[1] + CURSOR[1]), 0))
    time.sleep(0.15)
    found, scrolled = False, 0
    try:
        while scrolled < limit:
            wheel(1)
            scrolled += 1
            image = picture()
            if image is not None and has_success(image):
                found = True
                break
    finally:
        wheel(-(scrolled + 3))  # 맨 아래로 되돌린다
    return found, scrolled


if __name__ == "__main__":
    stamp = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%m%d-%H%M%S")
    found, scrolled = check()
    image = picture()
    if image is not None:
        from PIL import Image
        folder = HERE / "logs" / "minigame"
        folder.mkdir(parents=True, exist_ok=True)
        Image.fromarray(image).save(folder / f"{stamp}-message.png")
    if found is None:
        print(f"{time.strftime('%H:%M:%S')} 결과: 게임 창이 안 보여서 메시지창을 못 봤다", flush=True)
    elif found:
        where = "바로 보였다" if scrolled == 0 else f"{scrolled}줄 위에 있었다"
        print(f"{time.strftime('%H:%M:%S')} 결과: 성공 (메시지창에 '성공하였습니다.', {where})", flush=True)
    else:
        print(f"{time.strftime('%H:%M:%S')} 결과: 성공 메시지 없음 → 실패로 본다 ({scrolled}줄 위까지 봤다). 메시지창 logs/minigame/{stamp}-message.png", flush=True)
