"""옛날바람(메이플스토리 월드) 주술사 매크로 - macOS용

실행:  .venv/bin/python wind.py          매크로 실행
       .venv/bin/python wind.py auto     자동사냥을 켠 채로 시작
       .venv/bin/python wind.py check    체력/마력 인식값만 출력 (좌표 확인용)
설정:  config.toml
"""
import random
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

import numpy as np
import Quartz

CONFIG = tomllib.loads((Path(__file__).parent / "config.toml").read_text(encoding="utf-8"))
HOTKEYS, BARS, REGIONS, TIMING, KEYS, AUTO, ROAM = (
    CONFIG[k] for k in ("hotkeys", "bars", "regions", "timing", "keys", "auto", "roam"))
APP_NAME = CONFIG["window"]["app"]

# macOS 가상 키코드
KEYCODES = {
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26, "8": 28, "9": 25, "0": 29,
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "space": 49, "enter": 36, "esc": 53, "home": 115, "tab": 48, ",": 43, ";": 41, "ctrl": 59, "shift": 56,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
KEYNAMES = {code: name for name, code in KEYCODES.items()}

# 매크로가 보낸 키에 붙이는 표식. 리스너가 자기 입력을 사람 입력으로 착각하지 않게 한다.
MAGIC = 0x57494E44


class Abort(Exception):
    """모드가 바뀌었거나 게임 창이 뒤로 가서 하던 동작을 즉시 멈춘다."""


mode = "keys"  # "keys" | "auto" | "off"
held = set()  # 사람이 실제로 누르고 있는 키
changed = threading.Event()
quitting = threading.Event()


# ---------------------------------------------------------------- 게임 창

_window_cache = (0.0, None)


def game_window():
    """게임 창이 맨 앞에 있으면 (x, y) 창 좌표를, 아니면 None을 돌려준다."""
    global _window_cache
    now = time.monotonic()
    if now - _window_cache[0] < 0.2:
        return _window_cache[1]
    origin = None
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    # 화면 서버가 죽었거나 화면이 잠겨 있으면 None이 온다
    for w in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or ():
        if w.get("kCGWindowLayer") != 0:
            continue
        if w.get("kCGWindowOwnerName") == APP_NAME:
            bounds = w["kCGWindowBounds"]
            origin = (bounds["X"], bounds["Y"])
        break  # 레이어 0의 첫 창이 맨 앞 창
    _window_cache = (now, origin)
    return origin


# ---------------------------------------------------------------- 체력/마력 바

def _is_hp(r, g, b):
    return r >= 100 and r >= 2.5 * g and b < 70


def _is_mp(r, g, b):
    return b >= 100 and b > r and b > g


def _fill(data, row_bytes, scale, rows, width, is_bar):
    """바는 오른쪽 끝에 붙어 있고 왼쪽부터 줄어든다. 바 색이 처음 나오는 열로 비율을 구한다.

    숫자가 바 위에 겹쳐 그려지므로 한 줄만 보지 않고 바의 모든 줄을 본다.
    """
    for x in range(width):
        column = int(x * scale) * 4
        for y in rows:
            i = int(y * scale) * row_bytes + column
            if is_bar(data[i + 2], data[i + 1], data[i]):
                return (width - x) / width
    return 0.0


purged = time.monotonic()


def purge_replayd():
    """화면을 찍을 때마다 맥의 캡처 데몬 replayd에 메모리가 쌓인다 (6시간에 8.8GB, 2026-10-10).

    그대로 두면 스왑이 차서 다른 앱들이 죽고, 그 알림 창이 키를 가져가 캐릭터가 죽는다.
    10분마다 replayd를 죽여 비운다 (필요하면 맥이 다시 띄운다. SIGTERM은 안 먹어서 -9).
    """
    global purged
    if time.monotonic() - purged < 600:
        return
    purged = time.monotonic()
    import subprocess
    subprocess.run(["pkill", "-9", "-x", "replayd"], capture_output=True)


def grab(x, y, width, height):
    """게임 창 기준 영역을 캡처해 (픽셀 바이트, 줄당 바이트 수, 배율)을 돌려준다. 실패하면 None."""
    origin = game_window()
    if origin is None:
        return None
    x += origin[0]
    y += origin[1]
    purge_replayd()
    # CGDisplayCreateImageForRect로 찍고 픽셀을 복사하면 찍을 때마다 화면 서버의 IOSurface가 하나씩 새서,
    # 1시간쯤 돌리면 WindowServer가 죽는다 (2026-10-10 02:39). 창 목록 캡처는 그건 안 새지만,
    # 찍은 프로세스 안에 메모리가 남는다 (2026-10-11, 4시간 반에 90GB) → 일꾼 프로세스(grabber.py)에서 찍는다.
    global _grabber, _spare, _grabbed
    with _grab_lock:
        for _ in range(2):
            if _grabber is None or _grabber.poll() is not None:
                _grabber, _spare = _spare or _spawn_grabber(), None
                _grabber.stdout.readline()  # "ready"
                _grabbed = 0
            try:
                _grabber.stdin.write(b"%f %f %f %f\n" % (x, y, width, height))
                _grabber.stdin.flush()
                size, row_bytes, image_width = map(int, _grabber.stdout.readline().split())
                data = _grabber.stdout.read(size)
                if len(data) != size:
                    raise ValueError("일꾼이 그림을 다 안 보냈다")
            except (OSError, ValueError):
                _grabber.kill()
                _grabber = None
                continue
            break
        else:
            return None
        # 일꾼에 쌓인 메모리가 커지기 전에 갈아 치운다. 다음 일꾼은 미리 띄워 둬서 싸우는 중에 멈칫하지 않게 한다.
        _grabbed += size
        if _grabbed > GRABBER_LIMIT * 0.7 and _spare is None:
            _spare = _spawn_grabber()
        if _grabbed > GRABBER_LIMIT:
            _grabber.kill()
            _grabber = None
    if not size:
        return None
    return data, row_bytes, image_width / width


GRABBER_LIMIT = 300_000_000  # 일꾼 하나가 찍을 바이트 수. 찍은 만큼(조금 더) 일꾼에 메모리가 남는다
_grab_lock = threading.Lock()
_grabber = _spare = None
_grabbed = 0


def _spawn_grabber():
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name("grabber.py"))],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)


def cooling():
    """화면 왼쪽 위에 쿨 글자("헬파이어 3초")가 떠 있는지. 헬파이어가 실제로 나갔는지 이걸로 안다.

    그 자리의 순백색 점 수로 본다: 저장해 둔 화면 23장에서 글자가 없으면 0개, 있으면 836~880개였다.
    헬파이어로 몹을 죽이면 마력이 남아서, 마력이 줄었는지로는 나갔는지 알 수 없다.
    """
    shot = grab(140, 82, 160, 30)
    if shot is None:
        return False
    data, row_bytes, scale = shot
    pixels = np.frombuffer(data, dtype=np.uint8).reshape(-1, row_bytes)[:, :int(160 * scale) * 4].reshape(-1, 4)
    white = (pixels[:, :3] >= 250).all(axis=1).sum() / (scale * scale)
    return white >= 200


def read_bars():
    """(체력, 마력)을 0.0~1.0으로 돌려준다. 게임 창이 앞에 없으면 None."""
    half = BARS["half_height"]
    width = BARS["x1"] - BARS["x0"]
    mp_top = BARS["mp_y"] - BARS["hp_y"]
    shot = grab(BARS["x0"], BARS["hp_y"] - half, width, mp_top + 2 * half + 1)
    if shot is None:
        return None
    data, row_bytes, scale = shot
    rows = range(0, 2 * half + 1, 2)
    return (
        _fill(data, row_bytes, scale, rows, width, _is_hp),
        _fill(data, row_bytes, scale, [mp_top + r for r in rows], width, _is_mp),
    )


def snapshot(region):
    """화면의 고정된 UI 영역이 바뀌었는지 비교할 때 쓰는 픽셀 값."""
    shot = grab(*REGIONS[region])
    return shot and shot[0]


# ---------------------------------------------------------------- 키 입력

def sleep(seconds):
    if changed.wait(seconds):
        raise Abort


def _post(code, down, flags=None):
    event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
    if flags is not None:
        Quartz.CGEventSetFlags(event, flags)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, MAGIC)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


MODIFIERS = {
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "shift": Quartz.kCGEventFlagMaskShift,
}


def tap(key):
    """키를 한 번 눌렀다 뗀다. "ctrl+z", "shift+z"처럼 조합키도 된다.

    게임 창이 앞에 없으면 보내지 않고 중단한다.
    """
    if game_window() is None:
        raise Abort
    *modifiers, name = key.split("+")
    flags = None
    for modifier in modifiers:
        flags = (flags or 0) | MODIFIERS[modifier]
        _post(KEYCODES[modifier], True, flags)
        time.sleep(TIMING["modifier_hold"])  # 조합키는 바로 이어 누르면 게임이 놓친다
    try:
        _post(KEYCODES[name], True, flags)
        time.sleep(TIMING["key_hold"])
        _post(KEYCODES[name], False, flags)
    finally:
        if modifiers:
            time.sleep(TIMING["modifier_hold"])
        for modifier in modifiers:
            _post(KEYCODES[modifier], False, 0)
    sleep(TIMING["key_delay"])


def press(key, hold=0.02):
    """키 하나를 쉬는 시간 없이 눌렀다 뗀다 (tap은 누른 뒤 key_delay만큼 쉰다). 계속 돌려 누를 때 쓴다."""
    if game_window() is None:
        raise Abort
    _post(KEYCODES[key], True)
    time.sleep(hold)
    _post(KEYCODES[key], False)


def type_text(text):
    """입력창에 글자를 그대로 넣는다 (한글 포함). 한/영 상태와 상관없이 글자 자체를 보낸다."""
    if game_window() is None:
        raise Abort
    for letter in text:
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(letter), letter)
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, MAGIC)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.03)
        time.sleep(0.05)


def chord(key):
    """"shift+,"같은 조합키를 tap보다 훨씬 짧게 누른다 (걸음마다 줍기를 누를 때 쓴다. tap은 0.25초쯤 걸린다)."""
    if game_window() is None:
        raise Abort
    *modifiers, name = key.split("+")
    flags = 0
    for modifier in modifiers:
        flags |= MODIFIERS[modifier]
        _post(KEYCODES[modifier], True, flags)
    time.sleep(0.03)
    _post(KEYCODES[name], True, flags or None)
    time.sleep(0.02)
    _post(KEYCODES[name], False, flags or None)
    for modifier in modifiers:
        _post(KEYCODES[modifier], False, 0)


def refocus():
    """키가 게임에 안 들어갈 때: 게임을 다시 앞으로 가져오고 창의 제목 줄을 눌러 키 입력을 받게 한다.

    맥이 띄운 알림 창(다른 앱이 죽었다는 창 등)이 키 입력을 가져가도 게임 창은 여전히 맨 앞 창으로 읽힌다.
    그 상태로 몹에게 맞아 죽은 적이 있다 (2026-10-10 09:28).
    """
    import subprocess
    from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace
    # 다른 앱이 죽었다는 창은 Problem Reporter가 띄운다. 그 창이 키를 가져가므로 없앤다 (2026-10-10 11:46에 또 죽었다)
    for name in ("Problem Reporter", "UserNotificationCenter"):
        subprocess.run(["killall", name], capture_output=True)
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.localizedName() == APP_NAME:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    time.sleep(0.3)
    origin = game_window()
    if origin is None:
        return
    point = (origin[0] + 400, origin[1] + 12)
    for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        event = Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, MAGIC)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.05)
    time.sleep(0.2)


def prompt_open():
    """화면 아래 입력줄(대상 선택창이나 채팅창)이 열려 있는지. 열리면 줄 전체가 흰색이 된다."""
    shot = snapshot("input_line")
    return bool(shot) and shot[0] > 200


def cast(key, *target_keys):
    """대상 지정 스킬: 스킬키 → 대상 고르는 키 → Enter. 시전했으면 True.

    key는 "2" 같은 키 하나이거나, ["shift+z", "s"]처럼 차례로 누를 키 목록이다.

    대상 선택창이 안 뜬 상태에서 Enter를 누르면 채팅창이 열려 이후 키가 채팅으로 나간다.
    그래서 선택창이 뜬 걸 확인한 뒤에만 Enter를 누르고, 끝난 뒤에도 입력줄이 열려 있으면 Esc로 닫는다.
    """
    if prompt_open():
        tap("esc")
    for skill_key in [key] if isinstance(key, str) else key:
        tap(skill_key)
    if not prompt_open():
        return False
    for target_key in target_keys:
        tap(target_key)
    tap("enter")
    if prompt_open():
        tap("esc")
    return True


def cast_self(key):
    """자신에게 시전: 스킬키 → Home → Enter"""
    return cast(key, "home")


# ---------------------------------------------------------------- 동작

def bomu():
    """보호 + 무장"""
    cast_self(KEYS["bomu1"])
    sleep(0.1)
    cast_self(KEYS["bomu2"])


def mabi():
    """마비를 상하좌우로 시전"""
    for direction in ("up", "left", "right", "down"):
        cast(KEYS["mabi"], "home", direction)


def sweep(key, duration):
    """스킬키 → ← → Enter를 반복해 주변 대상에게 차례로 건다."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        cast(key, "left")


def attack():
    """첨 두 개를 쓴다. 첨은 상하좌우 1칸 안에 몹이 있어야 나가고, 나가면 메시지 창에 새 줄이 찍힌다."""
    landed = False
    for key, wait in ((KEYS["attack1"], AUTO["attack_gap"]), (KEYS["attack2"], AUTO["attack_interval"])):
        before = snapshot("last_message")
        tap(key)
        sleep(wait)
        landed |= snapshot("last_message") != before
    return landed


def find_box():
    """대상 선택 상자(흰 사각형)를 찾아 (x0, y0, x1, y1, 체력)을 돌려준다. 없으면 None.

    체력은 상자 바로 위 초록색 체력바의 길이 비율이다. 맞은 적 없는 몹은 바가 없어서 None.
    """
    width, height = REGIONS["view"][2:]
    shot = grab(*REGIONS["view"])
    if shot is None:
        return None
    data, row_bytes, scale = shot
    step = int(scale)
    image = np.frombuffer(data, np.uint8)[:height * step * row_bytes]
    image = image.reshape(height * step, row_bytes // 4, 4)[::step, :width * step:step, :3]  # B, G, R
    white = image.min(axis=2) >= 250
    run = 40  # 상자의 윗변/아랫변은 흰 픽셀이 이만큼 이상 이어진다
    sums = np.cumsum(np.pad(white, ((0, 0), (1, 0))), axis=1)
    starts = (sums[:, run:] - sums[:, :-run]) == run
    edges = {}  # 변이 시작하는 x 위치별로 그 변이 있는 줄들
    for y, x in zip(*(axis.tolist() for axis in np.nonzero(starts))):
        if x == 0 or not starts[y, x - 1]:
            edges.setdefault(x // 4, []).append((y, x))
    for edge in edges.values():
        rows = sorted(y for y, _ in edge)
        if rows[-1] - rows[0] < 40:  # 윗변과 아랫변이 둘 다 있어야 상자다
            continue
        x0, y0, y1 = min(x for _, x in edge), rows[0], rows[-1]
        x1 = x0
        while x1 < width and white[y0, x1]:
            x1 += 1
        # 스킬에 맞은 몹은 그림 전체가 하얗게 번쩍여서 상자처럼 보인다. 진짜 상자는 테두리만 희다:
        # 양옆 세로선이 이어져 있고 안쪽은 희지 않다
        sides = min(white[y0:y1 + 1, x0].mean(), white[y0:y1 + 1, x1 - 1].mean())
        inside = white[y0 + 4:y1 - 3, x0 + 4:x1 - 4]
        if sides < 0.8 or inside.size == 0 or inside.mean() > 0.4:
            continue
        above = image[max(0, y0 - 24):y0, max(0, x0 - 6):x1 + 6].astype(int)
        green = (above[:, :, 1] > 120) & (above[:, :, 2] < 90) & (above[:, :, 0] < 90)
        columns = int(green.any(axis=0).sum())
        return x0, y0, x1, y1, (min(1.0, columns / (x1 - x0)) if columns else None)
    return None


def locked():
    """대상이 고정돼 있는지 (화면에 빨간 테두리 상자가 있는지).

    Tab을 두 번 누르면 대상이 자신에게 고정되고 상자가 빨간 테두리(RGB 236, 90, 81쯤)로 바뀐다.
    고정돼 있으면 스킬키만 눌러도 선택창 없이 나간다: 힐은 자신에게, 저주는 주위 몹에게 걸린다.
    """
    width, height = REGIONS["view"][2:]
    shot = grab(*REGIONS["view"])
    if shot is None:
        return False
    data, row_bytes, scale = shot
    step = int(scale)
    image = np.frombuffer(data, np.uint8)[:height * step * row_bytes]
    image = image.reshape(height * step, row_bytes // 4, 4)[::step, :width * step:step, :3].astype(int)  # B, G, R
    red = (abs(image[:, :, 2] - 236) <= 14) & (abs(image[:, :, 1] - 90) <= 16) & (abs(image[:, :, 0] - 80) <= 18)
    run = 24  # 이펙트에 일부 가려져도 윗변이나 아랫변이 이만큼은 이어져 보인다
    sums = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)
    return bool(((sums[:, run:] - sums[:, :-run]) == run).any())


def lock_self():
    """대상을 자신에게 고정한다 (Tab 두 번). 이미 고정돼 있으면 누르지 않는다. 고정됐으면 True."""
    for _ in range(2):
        if locked():
            return True
        sleep(0.2)  # 이펙트에 가려 잠깐 안 보였을 수 있다. 한 번 더 보고 누른다
    if prompt_open():
        tap("esc")
    tap("tab")
    sleep(0.15)
    tap("tab")
    sleep(0.3)
    return locked()


def relock():
    """대상을 자신에게 다시 고정한다: Esc(풀기) → Tab → Tab. 고정됐으면 True.

    몹을 대상으로 스킬을 쓴 뒤에도 Tab 한 번이면 상자가 자신에게 오고, 한 번 더 누르면 고정된다 (확인함).
    빨간 상자는 이펙트에 가려 안 보일 때가 있어서 눈으로 확인하지 않는다. 대신 힐 키를 눌러 본다:
    고정돼 있으면 선택창 없이 바로 나가고, 안 돼 있으면 선택창이 뜬다. 안 됐으면 조금 더 천천히 다시 누른다.
    """
    for pause in (0.05, 0.1, 0.2):
        press("esc")
        time.sleep(pause)
        press("tab")
        time.sleep(pause)
        press("tab")
        time.sleep(pause)
        press(KEYS["heal"])
        time.sleep(0.08)
        if not prompt_open():
            return True
    press("esc")
    return False


scan_me = None  # hellfire_scan이 마지막으로 읽은 내 칸. 싸움을 시작할 때 None으로 지운다


own_width = None  # 선택창에서 읽은 내 상자의 평소 폭 (픽셀). 이보다 넓게 읽히면 잘못 읽은 것일 수 있다


def own_box():
    """선택창에서 Home을 누른 직후, 내 위에 놓인 상자를 읽는다. 못 읽으면 None.

    기본 공격 동작 중에는 내 상자가 잠깐 넓어져서 옆 칸으로 읽힌다. 그러면 진짜 내 상자가 "옆 칸 몹"으로 보여서
    헬파이어를 나에게 쓴다 ("걸리지 않습니다", 2026-10-11 사용자가 봄). 여러 번 읽어 가장 좁은 상자를 쓴다.
    """
    best = None
    for _ in range(4):
        box = find_box()
        if box is not None and (best is None or box[2] - box[0] < best[2] - best[0]):
            best = box
        time.sleep(0.04)
    return best


def hellfire_scan(key, limit, use=True):
    """고정을 풀고 선택창을 연다. (썼는지, 본 몹들의 칸 차이 목록)을 돌려준다.

    use가 참이면 key(헬파이어)를 쓴다: Home으로 나에게 간 뒤 ←를 한 번만 눌러 바로 다음 대상에게 Enter.
    몹을 하나씩 넘겨 보며 고르면 선택창이 2~3초 열려 있어서 그동안 힐이 끊긴다 (체력 51%에서 죽었다, 2026-10-11 13:34).
    한 번만 넘기면 상자가 나에게 돌아올 일이 없어서 나에게 쓰는 일도 없다. 목록에는 그 몹 하나만 들어간다.

    use가 거짓이면 쓰지 않고 몹 위치만 잰다 (몹이 남았는지, 어느 쪽에 붙었는지). 옆 칸(상하좌우)에 붙은 몹을 만나면
    거기서 멈춘다. 목록의 마지막이 그 몹이다.
    """
    press("esc")
    time.sleep(0.05)
    tap(key)
    if not prompt_open():
        last_boxes[:] = ["선택창이 안 떴다"]
        return False, []
    tap("home")
    mine = find_box()
    for _ in range(4):  # 기본 공격 동작 중에는 내 상자가 잠깐 넓어진다. 두 번 같게 읽힐 때까지 본다
        time.sleep(0.04)
        again = find_box()
        if again == mine and mine is not None:
            break
        mine = again
    # 힐을 계속 쓰는 중에는 힐 이펙트가 내 상자를 가려서 안 읽힐 때가 많다 (몹이 있는데 "없다"가 돼서 싸움이 끊겼다).
    # 싸우는 동안은 자리를 안 옮기므로, 못 읽으면 이 싸움에서 앞서 읽은 내 칸을 쓴다
    global scan_me
    if mine is not None:
        scan_me = box_tile(mine)
    found = []
    last_boxes[:] = [mine]
    if use:
        # 쿨이 돌았으면 내 상자가 읽히든 말든 쓴다: ←를 한 번 눌러 바로 다음 대상에게 Enter.
        # 몹이 길을 막고 때리는 동안은 힐 이펙트에 내 상자가 가려 안 읽히는데, 그때 안 쓰게 돼 있어서
        # 선택창만 13번 열고 한 번도 못 썼다 (2026-10-11 14:49, 사용자가 보고 끔)
        box = None
        for _ in range(2):
            tap("left")
            box = find_box()
            if box is None:
                time.sleep(0.05)
                box = find_box()
            last_boxes.append(box)
            # 상자가 내 상자 그대로면 ←가 씹혔거나 고를 몹이 없는 것이다. 한 번 더 눌러 본다
            if box is None or mine is None or box[:4] != mine[:4]:
                break
        else:
            tap("esc")
            if prompt_open():
                tap("esc")
            last_boxes.append("넘겨도 상자가 나에게 있다 (고를 몹이 없다)")
            return False, []
        if box is not None and scan_me is not None:
            tile = box_tile(box)
            if tile != scan_me:
                found.append((tile[0] - scan_me[0], tile[1] - scan_me[1]))
        tap("enter")
        if prompt_open():
            tap("esc")
        return True, found
    if scan_me is None:
        tap("esc")
        last_boxes[:] = ["내 상자가 안 보인다"]
        return False, []
    me = scan_me
    for _ in range(limit):
        if not prompt_open():
            return False, found  # 선택창이 닫혔다. ←를 누르면 캐릭터가 돈다
        tap("left")
        box = find_box()
        if box is None:
            time.sleep(0.05)
            box = find_box()
        last_boxes.append(box)
        if box is None:
            continue
        tile = box_tile(box)
        offset = (tile[0] - me[0], tile[1] - me[1])
        if offset == (0, 0):
            break
        found.append(offset)
        if offset in DELTA.values():
            break
    tap("esc")
    if prompt_open():
        tap("esc")
    return False, found


def pick_monster(min_hp=0.0):
    """대상 선택창이 열린 상태에서 상자를 몹 위로 옮긴다. 옮겼으면 True.

    Home으로 자기 위치를 먼저 알아낸 뒤 ←로 대상을 넘기면서, 자신이 아니고
    체력이 min_hp 이상인(또는 아직 안 맞은) 몹에서 멈춘다. 그런 몹이 없으면 아무 몹에서나 멈춘다.
    """
    tap("home")
    me = find_box()
    on_monster = False
    for _ in range(AUTO["target_tries"]):
        if not prompt_open():
            return False  # 선택창이 닫혔다. ←를 누르면 캐릭터가 돈다
        tap("left")
        box = find_box()
        if box is None:
            continue
        if me and abs(box[0] - me[0]) < 8 and abs(box[1] - me[1]) < 8:
            if on_monster:
                break  # 한 바퀴 돌아 자신에게 왔다. 체력 많은 몹은 없다
            return False  # ←를 눌러도 자신에게 머문다. 화면에 고를 몹이 없다
        on_monster = True
        if box[4] is None or box[4] >= min_hp:
            return True
    if on_monster:
        tap("left")  # 자신에게 돌아온 상태이므로 한 번 더 넘겨 첫 몹으로
        box = find_box()
        return bool(box and me and (abs(box[0] - me[0]) >= 8 or abs(box[1] - me[1]) >= 8))
    return False


def cast_at_monster(key, min_hp=0.0):
    """대상 지정 공격 스킬을 화면 안의 몹에게 쓴다. 몹을 골라 시전했으면 True."""
    if prompt_open():
        tap("esc")
    for skill_key in [key] if isinstance(key, str) else key:
        tap(skill_key)
    if not prompt_open():
        return False
    picked = pick_monster(min_hp)
    tap("enter" if picked else "esc")
    if prompt_open():
        tap("esc")
    return picked


def cast_each(key, limit, stop=None):
    """대상 지정 스킬(저주, 중독)을 화면의 몹마다 한 번씩 건다. 건 횟수를 돌려준다.

    대상 선택창에서 Home(자신) 뒤 ←를 n번 누르면 n번째 몹이다. 몹 수보다 많이 누르면 자신에게
    돌아오므로, 상자가 자기 자리에 있으면 다 돈 것으로 보고 멈춘다.
    """
    count = 0
    for nth in range(1, limit + 1):
        if stop and stop():
            break  # 더 급한 일이 생겼다 (체력이 위험하다)
        if prompt_open():
            tap("esc")
        for skill_key in [key] if isinstance(key, str) else key:
            tap(skill_key)
        if not prompt_open():
            break
        tap("home")
        me = find_box()
        for _ in range(nth):
            if prompt_open():  # 선택창이 닫힌 뒤의 ←는 캐릭터를 돌린다
                tap("left")
        box = find_box()
        if box is None or me is None or (abs(box[0] - me[0]) < 8 and abs(box[1] - me[1]) < 8):
            tap("esc")
            break
        tap("enter")
        if prompt_open():
            tap("esc")
        count += 1
    return count


TILE = 48  # 게임 화면에서 한 칸의 픽셀 수
last_boxes = []  # 마지막 locate_monsters가 본 상자들 (맨 앞이 내 상자). 확인용


VIEW_TILES = (25, 15)  # 게임 화면에 보이는 칸 수 (가로, 세로). 캐릭터는 가운데(12, 7)에 선다


def my_tile(position, size):
    """화면에서 내가 서 있는 칸 (열, 행). 맵 가장자리에서는 화면이 더 밀리지 않아 가운데가 아니다."""
    tile = []
    for here, length, shown in zip(position, size, VIEW_TILES):
        first = min(max(here - shown // 2, 0), max(length - shown, 0))  # 화면 맨 왼쪽(위)에 보이는 칸
        tile.append(here - first)
    return tuple(tile)


def box_tile(box):
    """대상 선택 상자가 놓인 화면 칸 (열, 행).

    상자는 그림 크기에 맞춰 그려져서 몹마다 크기가 다르고, 겹친 그림에 가려 한쪽이 짧게 잡히기도 한다.
    그래서 가로는 상자와 가장 많이 겹치는 칸으로, 세로는 발이 놓인 아랫변으로 정한다.
    """
    x0, y0, x1, y1 = box[:4]
    columns = range(max(0, x0 // TILE), x1 // TILE + 1)
    column = max(columns, key=lambda c: min(x1, (c + 1) * TILE) - max(x0, c * TILE))
    return column, y1 // TILE


walk_me = None  # 걷는 중에 마지막으로 읽은 내 화면 칸


def locate_monsters(limit, me=None):
    """화면에서 대상으로 고를 수 있는 몹들의 위치를 나로부터의 칸 차이 (dx, dy) 목록으로 돌려준다.

    대상 선택창의 상자가 놓인 화면 칸으로 계산한다. 스킬은 쓰지 않는다.
    me는 화면에서 내가 선 칸(my_tile). 주면 그걸 기준으로 하고, 안 주면 Home으로 고른 상자를 나로 본다
    (몹이 겹쳐 있으면 Home 직후의 상자가 엉뚱하게 읽힐 때가 있어서 me를 주는 쪽이 정확하다).
    """
    if not KEYS["ranged"]:
        return []
    if prompt_open():
        tap("esc")
    for skill_key in KEYS["ranged"]:
        tap(skill_key)
    if not prompt_open():
        return []
    tap("home")
    # Home은 상자를 나에게 건다. 기본 공격 동작 중에는 내 상자가 잠깐 넓어지므로,
    # 같은 상자가 두 번 연달아 읽힐 때까지 기다렸다가 쓴다
    first = find_box()
    for _ in range(6):
        time.sleep(0.05)
        again = find_box()
        if again == first and first is not None:
            break
        first = again
    last_boxes[:] = [first]
    global walk_me
    if me is None:
        # 내 상자가 안 읽히면 지난번에 읽은 내 칸을 쓴다 (걷는 동안 화면은 나를 따라와서 내 칸은 거의 그대로다).
        # 예전에는 못 읽으면 "몹 없음"이 돼서, 몹이 따라오는데도 멈춰 싸우지 않았다
        if first:
            walk_me = box_tile(first)
        me = walk_me
    found, misses = [], 0
    while me and len(found) < limit:
        if not prompt_open():
            break  # 선택창이 닫혔다. 여기서 ←를 누르면 캐릭터가 왼쪽으로 돈다
        tap("left")
        box = find_box()
        if box is None:  # 번쩍이는 순간이었을 수 있다. 한 번 더 본다
            time.sleep(0.06)
            box = find_box()
        last_boxes.append(box)
        if box is None:
            misses += 1
            if misses > 2:
                break
            continue  # 못 읽은 상자 하나 때문에 세기를 끝내지 않는다
        tile = box_tile(box)
        offset = (tile[0] - me[0], tile[1] - me[1])
        if offset == (0, 0) or offset in found:
            break  # 한 바퀴 돌아 나에게 왔다
        found.append(offset)
    tap("esc")
    if prompt_open():
        tap("esc")
    return found


def count_monsters(limit):
    """화면에서 대상으로 고를 수 있는 몹 수를 센다 (limit까지). 스킬은 쓰지 않는다."""
    if not KEYS["ranged"]:
        return 0
    if prompt_open():
        tap("esc")
    for skill_key in KEYS["ranged"]:
        tap(skill_key)
    if not prompt_open():
        return 0
    tap("home")
    me = find_box()
    count = 0
    while me and count < limit and prompt_open():
        tap("left")
        box = find_box()
        if box is None or (abs(box[0] - me[0]) < 8 and abs(box[1] - me[1]) < 8):
            break
        count += 1
    tap("esc")
    if prompt_open():
        tap("esc")
    return count


def hellfire():
    """헬파이어: 단일 대상, 마력을 전부 쓴다. 체력이 많이 남은 몹을 골라 쓰고, 마력이 바닥났는지로 성공을 확인한다."""
    if not cast_at_monster(KEYS["hellfire"], AUTO["hellfire_target_hp"]):
        return False
    sleep(AUTO["cast_wait"])
    bars = read_bars()
    return bool(bars) and bars[1] < AUTO["mp_low"]


DIRECTIONS = ("up", "right", "down", "left")
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

roam_direction = random.choice(DIRECTIONS)
roam_offset = [0, 0]  # 자동사냥을 켠 자리에서 몇 칸 떨어져 있는지 (실제로 움직인 칸만 센다)
roam_exits = set()  # 밟으면 맵 밖으로 나가는 (칸, 방향)
home_map = None  # 자동사냥을 켠 맵의 이름 영역 픽셀


def can_step(direction):
    """그 방향으로 가도 되는지: 시작한 자리에서 radius칸 안이고, 맵 출구로 알려진 곳이 아니어야 한다."""
    x = roam_offset[0] + DELTA[direction][0]
    y = roam_offset[1] + DELTA[direction][1]
    return (max(abs(x), abs(y)) <= ROAM["radius"]
            and (roam_offset[0], roam_offset[1], direction) not in roam_exits)


def come_back(direction):
    """방금 걸음으로 맵 밖에 나왔다. 온 길로 되돌아가고, 그 칸을 출구로 기억한다."""
    print("맵 밖으로 나감 → 되돌아가는 중")
    roam_exits.add((roam_offset[0], roam_offset[1], direction))
    sleep(ROAM["map_wait"])
    for _ in range(4):
        tap(OPPOSITE[direction])
        sleep(ROAM["map_wait"])
        if snapshot("map_name") == home_map:
            print("원래 맵으로 돌아옴")
            return
    print("원래 맵으로 돌아가지 못했습니다. 자동사냥을 멈춥니다.")
    set_mode("off")
    raise Abort


def step(direction):
    """한 칸 이동한다. 방향이 다르면 첫 입력은 돌기만 하므로 좌표가 바뀔 때까지 두 번까지 누른다."""
    for _ in range(2):
        before = snapshot("coordinates")
        tap(direction)
        sleep(ROAM["step_wait"])
        if snapshot("coordinates") != before:
            if snapshot("map_name") != home_map:
                come_back(direction)
                return False
            roam_offset[0] += DELTA[direction][0]
            roam_offset[1] += DELTA[direction][1]
            return True
    return False


def seek():
    """상하좌우 1칸 안에 몹이 없을 때 자리를 옮긴다. 칸마다 공격해 보고 나가면 멈춘다."""
    global roam_direction
    for _ in range(ROAM["steps"]):
        if not can_step(roam_direction):
            choices = [d for d in DIRECTIONS if can_step(d)]
            if not choices:
                return
            roam_direction = random.choice(choices)
        if not step(roam_direction):
            roam_direction = random.choice([d for d in DIRECTIONS if d != roam_direction])
            return
        if attack():
            return


def drink():
    tap(KEYS["potion"])


def refill(potions_first):
    """공력증강으로 마력을 채운다. 채웠으면 True.

    공력증강도 시전에 마력이 들어서, 헬파이어 직후처럼 마력이 바닥이면 물약을 먼저 마셔야 한다.
    공력증강은 실패할 수도 있다. 눌렀는데 마력이 안 차면 물약을 한 번 더 마시고 다시 누른다.
    """
    for _ in range(AUTO["refill_tries"]):
        if potions_first:
            for _ in range(AUTO["potions_per_try"]):
                drink()
        tap(KEYS["gongjeung"])
        end = time.monotonic() + AUTO["gongjeung_wait"]
        while time.monotonic() < end:  # 마력바가 차는 대로 바로 다음 일로 넘어간다
            bars = read_bars()
            if bars and bars[1] >= AUTO["mp_low"]:
                return True
            sleep(0.03)
        potions_first = True
    return False


def auto_hunt():
    """매번 체력/마력을 읽고 지금 가장 급한 일 하나를 한다. 급한 일이 없으면 공격."""
    global home_map
    print("자동 사냥 시작")
    home_map = snapshot("map_name")
    roam_offset[:] = [0, 0]
    roam_exits.clear()
    last = {}  # 쿨타임 스킬별 마지막 시전 시각
    healing = False
    misses = 0  # 연속으로 공격이 안 나간 횟수
    hellfire_at = 0.0  # 이 시각 이후에 헬파이어를 다시 시도한다
    drained = False  # 헬파이어로 마력을 다 써서 공력증강 전에 물약이 필요한 상태
    # 헬파이어를 쓰려면 체력이 hellfire_min_hp 이상이어야 하므로 그 아래면 힐부터 한다
    heal_below = max(AUTO["hp_low"], AUTO["hellfire_min_hp"] if KEYS["hellfire"] else 0)

    def due(name, cooldown):
        now = time.monotonic()
        if cooldown > 0 and now - last.get(name, -1e9) >= cooldown:
            last[name] = now
            return True
        return False

    while True:
        hp, mp = read_bars() or (1.0, 1.0)
        if hp < heal_below:
            healing = True
        elif hp >= AUTO["hp_ok"]:
            healing = False

        empty = mp < AUTO["potion_below"]  # 힐 한 번 쓸 마력도 없는 상태
        # 헬파이어를 쓸 수 있는 때라면 마력이 헬파이어 기준에 못 미칠 때 바로 채운다
        hellfire_ready = bool(KEYS["hellfire"]) and time.monotonic() >= hellfire_at
        mp_floor = AUTO["hellfire_min_mp"] if hellfire_ready else AUTO["mp_low"]
        if healing and not empty:
            cast_self(KEYS["heal"])
        elif mp < mp_floor and hp >= AUTO["gongjeung_min_hp"]:
            print(f"마력 {mp:.0%} → 공력증강" + (" (물약 먼저)" if drained or empty else ""))
            if refill(drained or empty):
                drained = False
        elif empty:
            # 체력이 낮은데 힐 쓸 마력도 없다. 동동주 1잔(마력 30) → 공력증강(30 소모, 가득 채움) 뒤에 힐
            print(f"체력 {hp:.0%} 마력 {mp:.0%} → 물약 + 공력증강")
            refill(True)
        elif mp < mp_floor:
            cast_self(KEYS["heal"])  # 공력증강은 체력을 쓰므로 먼저 채운다
        elif hellfire_ready and hp >= AUTO["hellfire_min_hp"]:
            if hellfire():
                print("헬파이어")
                drained = True
                hellfire_at = time.monotonic() + AUTO["hellfire_every"]
            else:
                hellfire_at = time.monotonic() + AUTO["hellfire_retry"]
        elif due("bomu", AUTO["bomu_every"]):
            bomu()
        elif due("curse", AUTO["curse_every"]):
            sweep(KEYS["curse"], AUTO["curse_seconds"])
        elif due("poison", AUTO["poison_every"]):
            sweep(KEYS["poison"], AUTO["poison_seconds"])
        elif attack():
            misses = 0
        else:
            misses += 1
            if misses >= ROAM["misses"]:
                if KEYS["ranged"] and cast_at_monster(KEYS["ranged"]):
                    pass  # 몹이 다가올 때까지 제자리에서 계속 때린다
                elif ROAM["enabled"]:
                    seek()
                    misses = 0


def key_macro():
    """누르고 있는 스킬키에 맞춰 보조 입력을 넣는다."""
    if KEYS["mabi"] in held:
        mabi()
    elif KEYS["poison"] in held or KEYS["curse"] in held:
        if prompt_open():
            tap("left")
            tap("enter")
        else:
            sleep(0.02)
    elif KEYS["bomu1"] in held:
        bomu()
    elif KEYS["heal"] in held:
        cast_self(KEYS["heal"])
    else:
        sleep(0.02)


def worker():
    while not quitting.is_set():
        changed.clear()
        try:
            if game_window() is None or mode == "off":
                sleep(0.1)
            elif mode == "auto":
                auto_hunt()
            else:
                key_macro()
        except Abort:
            if prompt_open():  # 시전 도중 끊겼을 때 남는 '대상은?' 창을 닫는다
                _post(KEYCODES["esc"], True)
                _post(KEYCODES["esc"], False)
        except Exception as e:  # 스레드가 조용히 죽지 않게
            print(f"오류: {e!r}")
            time.sleep(1)


# ---------------------------------------------------------------- 단축키

def set_mode(new):
    global mode
    mode = new
    changed.set()
    print({"keys": "키매크로 켜짐", "auto": "자동사냥 켜짐", "off": "매크로 꺼짐"}[new])


def on_event(proxy, event_type, event, refcon):
    if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
        Quartz.CGEventTapEnable(_tap, True)  # 시스템이 탭을 꺼버린 경우 다시 켠다
        return event
    if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData) == MAGIC:
        return event
    name = KEYNAMES.get(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
    if name is None:
        return event
    if event_type == Quartz.kCGEventKeyUp:
        held.discard(name)
    elif not Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat):
        held.add(name)
        if game_window() is not None:
            if name == HOTKEYS["auto"]:
                set_mode("off" if mode == "auto" else "auto")
            elif name == HOTKEYS["keys"]:
                set_mode("off" if mode == "keys" else "keys")
            elif name == HOTKEYS["quit"]:
                quitting.set()
                changed.set()
    return event


_tap = None


def run():
    global _tap
    mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
    _tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly, mask, on_event, None,
    )
    if _tap is None:
        sys.exit("키 입력을 읽을 수 없습니다. 시스템 설정 → 개인정보 보호 및 보안 → 입력 모니터링에서 "
                 "이 터미널 앱을 허용하세요.")
    source = Quartz.CFMachPortCreateRunLoopSource(None, _tap, 0)
    Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetMain(), source, Quartz.kCFRunLoopCommonModes)

    print(f"{HOTKEYS['keys']}: 키매크로  {HOTKEYS['auto']}: 자동사냥  {HOTKEYS['quit']}: 종료"
          "  (게임 창이 맨 앞일 때만 동작)")
    set_mode(mode)
    threading.Thread(target=worker, daemon=True).start()
    try:
        # CFRunLoopRun()은 Ctrl+C를 받지 못하므로 짧게 끊어서 돌린다
        while not quitting.is_set():
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.2, False)
    except KeyboardInterrupt:
        pass
    quitting.set()
    changed.set()
    print("종료")


def check():
    print("게임 창을 맨 앞에 두세요. Ctrl+C로 종료.")
    try:
        while True:
            bars = read_bars()
            print("게임 창이 앞에 없음" if bars is None else f"체력 {bars[0]:4.0%}  마력 {bars[1]:4.0%}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        check()
    else:
        if sys.argv[1:] == ["auto"]:
            mode = "auto"  # 자동사냥을 켠 채로 시작
        run()
