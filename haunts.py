"""지금 있는 성의 어느 흉가 묶음에 사람이 있는지 본다: 대화창에 "/출 흉가"를 치면
"제3상곡흉가3: (아이디), 18초 경과"처럼 사람이 있는 방마다 한 줄씩 보라색 글씨로 나온다 (2026-10-13 사용자가 알려 줌).
**그 성의 흉가만 나온다** (부여성에서 치면 부여성 흉가가 나온다). 그래서 성 이름은 읽지 않고 "제N"만 읽는다.
"제"가 없이 바로 성 이름으로 시작하면 1번 묶음이다. 흉가 안에서 치면 "여기서는 할 수 없습니다."가 나온다.

글자는 가방 목록과 같은 글꼴(높이 22, 한글 칸 24, 숫자 칸 12)이다. 숫자 견본(data/chat_digits.npy)은 가방의 숫자에서 땄고,
대화 칸의 "제3"의 3, "18초"의 1과 8이 픽셀 하나 안 틀리고 맞았다. "제", "흉가" 견본은 결과 줄에서 땄다.

사용: .venv/bin/python haunts.py          지금 "/출 흉가"를 쳐 보고 읽은 것을 찍는다
      .venv/bin/python haunts.py 그림.png  저장된 전체 화면에서 읽기만 한다
"""

import sys
import time
from pathlib import Path

import numpy as np

import wind

DATA = Path(__file__).parent / "data"
CHAT = (150, 829, 1210, 150)  # 대화 칸 (게임 창 기준 x, y, 너비, 높이). 다섯 줄이 보인다
INK = (41, 0, 159)  # 결과 줄의 글자색 (RGB)
LEFT = 9  # 줄의 첫 글자가 시작하는 x (대화 칸 기준)
_glyphs = None


def glyphs():
    global _glyphs
    if _glyphs is None:
        _glyphs = np.load(DATA / "chat_digits.npy"), np.load(DATA / "chat_je.npy"), np.load(DATA / "chat_hyungga.npy")
    return _glyphs


SLOTS = (13, 39, 65, 91, 117)  # 대화 칸 다섯 줄의 글자가 시작하는 y

# 그 성의 흉가에 아무도 없으면 결과 줄 대신 "결과가 없습니다." 한 줄이 나온다 (2026-10-15 05:56 새벽).
# 이걸 몰라서 "못 읽음 → 꽉 참"으로 보고 다섯 성을 돌다가 범안성에서 기다렸다
NO_RESULT = -9
_nothing = None


def no_result():
    global _nothing
    if _nothing is None:
        _nothing = np.load(DATA / "chat_noresult.npy")
    return _nothing


def lines(picture):
    """대화 칸 그림(RGB)의 다섯 줄을 위에서부터: 결과 줄이면 묶음 번호, 보라색인데 결과 줄이 아니면 0, 다른 줄이면 None.

    결과 줄: ["제" 숫자] 성 이름(두세 글자) "흉가" 방 번호 ":" …. "제N"이 없으면 1번 묶음이다.
    성 이름은 읽지 않는다 (지금 있는 성의 것만 나온다). 대신 그 뒤에 "흉가"가 있는지로 결과 줄인지 가린다.
    묶음 숫자를 못 읽었으면 -1이다 (사람이 있는 줄인데 어느 묶음인지 모른다).
    """
    ink = np.abs(picture.astype(np.int64) - np.array(INK)).sum(2) < 40
    digits, je, haunt = glyphs()
    found = [None] * len(SLOTS)
    rows = np.nonzero(ink.sum(1) > 0)[0]
    if not len(rows):
        return found
    for run in np.split(rows, np.nonzero(np.diff(rows) > 1)[0] + 1):
        y = int(run[0])  # 글자가 실제로 시작하는 줄 (캡처가 한두 픽셀 어긋나도 맞게)
        slot = int(round((y - SLOTS[0]) / 26))
        band = ink[y:y + 22]
        if not 0 <= slot < len(SLOTS) or band.shape[0] < 22 or band.sum() < 60:
            continue
        x = int(np.nonzero(band.any(0))[0][0])  # 첫 글자가 시작하는 칸
        nothing = no_result()
        if band[:, x:x + nothing.shape[1]].shape == nothing.shape and (band[:, x:x + nothing.shape[1]] != nothing).sum() <= 30:
            found[slot] = NO_RESULT
            continue
        group, start = 1, x
        if (band[:, x:x + 24] != je).sum() <= 6:
            errors = [(band[:, x + 24:x + 36] != digit).sum() for digit in digits]
            group, start = (int(np.argmin(errors)) if min(errors) <= 4 else -1), x + 36
        # 성 이름은 두 글자(상곡, 어양 …) 아니면 세 글자(천안궁, 동부여 …). 그 뒤가 "흉가"여야 결과 줄이다
        named = any((band[:, start + skip:start + skip + 48] != haunt).sum() <= 10 for skip in (48, 72))
        found[slot] = group if named else 0
    return found


_command = None


def command_slot(picture):
    """내가 친 "미아내: /출 흉가" 줄이 보이는 가장 아래 자리 (0 ~ 4). 안 보이면 None."""
    global _command
    if _command is None:
        _command = np.load(DATA / "chat_command.npy")
    dark = picture.astype(np.int64).sum(2) < 30  # 내가 한 말은 새까만 글씨다
    best = None
    for slot, y in enumerate(SLOTS):
        for dy in (-2, -1, 0, 1, 2):
            band = dark[y + dy:y + dy + 22, LEFT:LEFT + _command.shape[1]]
            if band.shape == _command.shape and (band != _command).sum() <= 12:
                best = slot
    return best


def below_command(picture):
    """(내가 친 줄 아래의 보라색 줄들, 내가 친 줄이 보였는가). 사이에 다른 사람의 말이 끼어 있어도 건너뛰고 센다.

    처음에는 "맨 아래에서부터 이어진 보라색 줄"만 셌는데, 결과 뒤에 다른 사람의 말이 한 줄 올라오면
    아무도 없는 것으로 읽혔다 (2026-10-13).
    """
    rows, slot = lines(picture), command_slot(picture)
    start = 0 if slot is None else slot + 1
    return [row for row in rows[start:] if row is not None], slot is not None


def recent(picture):
    return below_command(picture)[0]


def occupied(picture):
    """(사람이 있는 묶음 번호들, 못 믿겠는가). 저장된 그림 한 장만 볼 때 쓴다 (스크롤은 ask가 한다)."""
    run, anchored = below_command(picture)
    if run == [NO_RESULT]:
        run = []  # "결과가 없습니다" = 아무도 없다
    return {group for group in run if group > 0}, not anchored or any(group <= 0 for group in run)


def chat_picture():
    shot = wind.grab(*CHAT)
    if shot is None:
        return None
    raw, stride, scale = shot
    rows = len(raw) // stride
    wide = int(round(CHAT[2] * scale))
    step = int(round(scale))
    return np.frombuffer(raw, np.uint8).reshape(rows, stride)[:, :wide * 4].reshape(rows, wide, 4)[::step, ::step, 2::-1]


def point(x, y):
    """마우스 커서를 게임 창 기준 (x, y)로 옮긴다."""
    import Quartz
    origin = wind.game_window()
    if origin is None:
        raise wind.Abort
    event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (origin[0] + x, origin[1] + y), Quartz.kCGMouseButtonLeft)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    time.sleep(0.15)


def wheel(lines_up):
    """대화 칸을 lines_up줄 위로 넘긴다 (음수면 아래로). 마우스가 대화 칸 위에 있어야 한다. 한 칸에 정확히 한 줄(26픽셀)씩 움직인다."""
    import Quartz
    step = 1 if lines_up > 0 else -1
    for _ in range(abs(lines_up)):
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, step)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.06)
    time.sleep(0.3)


CORNER = (1250, 900)  # 대화 칸 안의 오른쪽. 결과 줄은 짧아서 여기까지 안 온다 (커서 그림이 글자를 가리면 안 된다).
                      # 오른쪽 아래 구석 (1335, 965)에 두었더니 휠이 안 먹었다. 대화 칸 안쪽이어야 넘어간다


def ask():
    """"/출 흉가"를 치고 (지금 있는 성에서 사람이 있는 묶음 번호들, 못 믿겠는가)를 돌려준다.

    대화 칸에는 다섯 줄만 보인다. 다섯 줄이 모두 보라색이면 위로 넘겨 가며 다른 줄("미아내: /출 흉가")이
    나올 때까지 읽는다 (사용자: "대화창 스크롤하면 위의 것도 보여. /출 흉가 아래 메시지만 보면 되지 않을까").
    둘째 값이 True면 결과를 믿으면 안 된다: 결과 줄이 아닌 보라색 줄이 있었거나 (예: "여기서는 할 수 없습니다"),
    묶음 숫자를 못 읽었거나, 끝을 못 찾았다. 그때 화면을 logs/tmp/unread-*.png로 남긴다.
    """
    if wind.prompt_open():
        wind.tap("esc")
        time.sleep(0.2)
    point(*CORNER)
    wind.tap("enter")
    time.sleep(0.3)
    wind.type_text("/출 흉가")
    time.sleep(0.2)
    wind.tap("enter")
    time.sleep(1.2)
    taken, unsure, scrolled = set(), False, 0
    while True:
        picture = chat_picture()
        if picture is None:
            raise wind.Abort
        run, anchored = below_command(picture)
        if anchored and run == [NO_RESULT]:
            run = []  # "결과가 없습니다" = 이 성의 흉가에 아무도 없다
        taken |= {group for group in run if group > 0}
        if any(group <= 0 for group in run):
            unsure = True
            from PIL import Image
            folder = Path(__file__).parent / "logs" / "tmp"
            folder.mkdir(parents=True, exist_ok=True)
            Image.fromarray(picture.astype(np.uint8)).save(folder / f"unread-{time.strftime('%m%d-%H%M%S')}.png")
        if anchored:
            break  # 내가 친 줄이 보인다 = 이번 결과의 맨 위까지 봤다
        if scrolled >= 80:
            unsure = True
            break
        wheel(len(SLOTS) - 1)  # 네 줄 위로 (한 줄은 겹치게)
        scrolled += len(SLOTS) - 1
    if scrolled:
        wheel(-(scrolled + 5))  # 맨 아래로 되돌린다
    return taken, unsure


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from PIL import Image
        image = np.array(Image.open(sys.argv[1]).convert("RGB"))
        picture = image[CHAT[1] + 31:CHAT[1] + 31 + CHAT[3], CHAT[0]:CHAT[0] + CHAT[2]]
        print(lines(picture), occupied(picture))
    else:
        wind.refocus()
        time.sleep(0.5)
        result = ask()
        from PIL import Image
        Image.fromarray(chat_picture().astype(np.uint8)).save(Path(__file__).parent / "logs" / "tmp" / "chat_live.png")
        print(result, lines(chat_picture()))
