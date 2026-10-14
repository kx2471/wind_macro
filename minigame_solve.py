"""미니게임 창을 한 번 풀어 본다: 왼쪽 아래 몬스터와 같은 몬스터를 잡음 속에서 찾아 끌어다 놓고 OK를 누른다.

운영자가 자동 풀이를 허용했다는 답변을 사용자가 보여 줘서 만들었다 (2026-10-12). "적당히 이용"하라고 해서
창 하나에 한 번만 시도하고, 틀려도 다시 하지 않는다. minigame_pause.sh가 매크로를 세운 뒤에 부른다.

창의 구조 (게임 창 기준 좌표, 2026-10-12 17:46 화면에서 잰 값):
- 잡음 판: (661, 339)에서 가로 600 × 세로 401. 색색의 잡음으로 덮여 있고 그 안에 흐릿한 몬스터가 몇 개 있다.
- 끌어 놓을 몬스터: 잡음 판 왼쪽 아래 구석에 또렷하게 그려져 있다 (판 기준 x 3~44, y 316~401쯤).
- OK 버튼: (960, 818).

찾는 방법: 잡음은 픽셀마다 제각각이라 주변과 평균하면 회색으로 뭉개지고, 몬스터가 있는 자리만 무늬가 남는다.
그렇게 흐리게 만든 판 전체에 왼쪽 아래 몬스터(같은 식으로 흐리게 만든 것)를 대 보고,
무늬가 가장 닮은(정규화 상관이 가장 큰) 자리에 놓는다. 닮음이 낮거나 다른 자리와 차이가 작으면 손대지 않는다.

사용: .venv/bin/python minigame_solve.py                실제 창을 푼다 (게임 창이 맨 앞이어야 한다)
      .venv/bin/python minigame_solve.py 화면.bmp       저장된 전체 화면(가로 1280으로 줄인 24비트 BMP)으로 찾기만 해 본다
"""

import sys
import time
from pathlib import Path

import numpy as np

PANEL = (661, 339, 600, 401)  # 잡음 판 (게임 창 기준 x, y, 너비, 높이)
OK_BUTTON = (960, 818)
OUT = Path(__file__).parent / "logs" / "minigame"


def box(image, size):
    """한 변이 size인 상자 평균 (가장자리는 가장자리 값을 늘려서 채운다). image는 (높이, 너비) 또는 (높이, 너비, 채널)."""
    pad = size // 2
    widths = ((pad + 1, pad), (pad + 1, pad)) + ((0, 0),) * (image.ndim - 2)
    total = np.pad(image.astype(np.float64), widths, mode="edge").cumsum(0).cumsum(1)
    return (total[size:, size:] - total[:-size, size:] - total[size:, :-size] + total[:-size, :-size]) / (size * size)


def likeness(first, second):
    """두 그림 조각(같은 크기)의 정규화 상관. 밝기 차이와 진하기 차이는 무시하고 무늬만 견준다."""
    first, second = first - first.mean((0, 1)), second - second.mean((0, 1))
    scale = np.sqrt((first ** 2).sum() * (second ** 2).sum())
    return float((first * second).sum() / scale) if scale else 0.0


SPRITE = (3, 316, 44, 401)  # 본으로 쓸 상자 (판 기준 왼쪽, 위, 오른쪽, 아래). 끌어 놓을 몬스터의 왼쪽 아래 부분이 들어온다
SURE, AHEAD = 0.40, 0.12  # 닮음이 이 이상이고 둘째 자리보다 이만큼 앞설 때만 끌어다 놓는다


def solve(panel):
    """잡음 판 그림(높이, 너비, 3)에서 (끌기 시작점, 놓을 점, 설명)을 판 기준 좌표로 돌려준다. 확신이 없으면 놓을 점이 None.

    구석의 고정 상자 SPRITE를 흐리게 만든 무늬를 판 전체에 3픽셀 간격으로 대 보고 가장 닮은 자리를 고른다.
    시작점은 상자 한가운데, 놓을 점은 닮은 자리의 한가운데라서 두 점이 같은 부위다 → 몬스터가 크든 작든 겹쳐진다.

    몬스터의 테두리를 찾아서 본으로 쓰려던 방법은 버렸다: 무늬가 촘촘한 몬스터(전사)는 잡음만큼 거칠어서
    "매끈한 영역"으로 안 잡히고, 바로 옆의 흐린 후보까지 한 덩어리로 묶여 닮음이 0.19로 떨어졌다 (2026-10-13 00:57).
    고정 상자로는 실제 화면 세 장(17:46 대머리, 19:58 고블린, 00:57 전사) 모두 정답 자리가 0.59 ~ 0.75,
    다른 자리는 0.34 아래였다.
    """
    soft = box(panel, 7)
    left, top, right, bottom = SPRITE
    sprite = soft[top:bottom, left:right]
    tall, wide = sprite.shape[:2]
    start = ((left + right) // 2, (top + bottom) // 2)
    scores = {}
    for y0 in range(0, panel.shape[0] - tall + 1, 3):
        for x0 in range(0, panel.shape[1] - wide + 1, 3):
            if x0 < right + 10 and y0 + tall > top - 10:
                continue  # 끌어 놓을 몬스터 자신
            scores[(x0 + wide // 2, y0 + tall // 2)] = likeness(sprite, soft[y0:y0 + tall, x0:x0 + wide])
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    (spot, best) = ranked[0]
    second = next((value for where, value in ranked if abs(where[0] - spot[0]) > wide or abs(where[1] - spot[1]) > tall), -1.0)
    notes = [f"가장 닮은 자리 {spot} 닮음 {best:.3f}, 다른 자리 중 최고 {second:.3f}"]
    if best < SURE or best - second < AHEAD:
        # 예전에는 여기서 손을 뗐다. 안 풀면 어차피 시간이 다 돼서 "실패!"가 되므로 가장 닮은 자리에 놓아 본다 (2026-10-13)
        notes.append("확신은 낮지만 가장 닮은 자리에 놓아 본다")
    return start, spot, notes


def from_file(path):
    """가로 1280으로 줄인 전체 화면 BMP에서 잡음 판만 원래 크기로 늘려서 꺼낸다 (시험용)."""
    data = open(path, "rb").read()
    offset, width = int.from_bytes(data[10:14], "little"), int.from_bytes(data[18:22], "little")
    height, depth = int.from_bytes(data[22:26], "little", signed=True), int.from_bytes(data[28:30], "little") // 8
    row = (width * depth + 3) // 4 * 4
    image = np.frombuffer(data, np.uint8, row * abs(height), offset).reshape(abs(height), row)[:, :width * depth]
    image = image.reshape(abs(height), width, depth)[..., :3]
    image = image[::-1] if height > 0 else image
    x, y, w, h = PANEL
    ys = ((np.arange(h) + y + 31) / 1.5).astype(int)  # 창은 화면의 (0, 31)에서 시작하고, 그림은 1.5배 줄어 있다
    xs = ((np.arange(w) + x) / 1.5).astype(int)
    return image[ys][:, xs].astype(np.float64)


def solid_pixels(game):
    """게임 픽셀 그림(높이, 너비, 3; 화면 픽셀을 2칸마다 하나씩 뽑은 것)에서 또렷한 그림이 있는 자리.

    잡음은 게임 픽셀마다 색이 달라서 이웃과 완전히 같은 색인 경우가 없다 (실제 판에서 0%).
    또렷한 몬스터 안에서는 15%쯤이 이웃과 같다. 흐린 후보들은 잡음과 섞여 있어서 0%다.
    그래서 "이웃과 색이 같은 픽셀이 5×5 안에 3개 이상"인 자리가 끌어 놓을 몬스터다. 판 테두리(한 색 줄)는 뺀다.
    """
    game = game.astype(np.int64)
    tall, wide = game.shape[:2]
    same = np.zeros((tall, wide), bool)
    across, down = (game[:, 1:] == game[:, :-1]).all(2), (game[1:] == game[:-1]).all(2)
    same[:, 1:] |= across
    same[:, :-1] |= across
    same[1:] |= down
    same[:-1] |= down
    total = np.pad(np.pad(same.astype(np.float64), 2).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    solid = (total[5:, 5:] - total[:-5, 5:] - total[5:, :-5] + total[:-5, :-5]) >= 3
    solid[:4] = solid[-2:] = False
    solid[:, :4] = solid[:, -4:] = False
    return solid


def sprite_mask(game, solid=None):
    """왼쪽 아래 구석에 붙어 있는 또렷한 덩어리 (끌어 놓을 몬스터).

    몬스터는 늘 판의 왼쪽 아래 구석에 붙어 있다. 그 구석(가로세로 20 게임 픽셀)의 또렷한 픽셀에서 시작해 이어진 것만 모은다
    (두 픽셀까지의 틈은 이어진 것으로 본다). 처음에는 "왼쪽 1/3, 아래 1/2 안의 또렷한 픽셀 전부"에서 시작했는데,
    그 안에 게임 마우스 커서가 있으면 커서까지 몬스터로 묶였다 (2026-10-14 05:09, 작은 불꽃 몬스터 + 커서 → 엉뚱한 모양).
    """
    if solid is None:
        solid = solid_pixels(game)
    tall, wide = solid.shape
    near = solid.copy()  # 틈을 메운 지도: 두 픽셀 안에 또렷한 픽셀이 있으면 이어진 것으로 친다
    for _ in range(2):
        grown = near.copy()
        grown[1:] |= near[:-1]
        grown[:-1] |= near[1:]
        grown[:, 1:] |= near[:, :-1]
        grown[:, :-1] |= near[:, 1:]
        near = grown
    reach = np.zeros_like(solid)
    reach[tall - 20:, :20] = near[tall - 20:, :20]
    for _ in range(600):
        grown = reach.copy()
        grown[1:] |= reach[:-1]
        grown[:-1] |= reach[1:]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= near
        if (grown == reach).all():
            break
        reach = grown
    return reach & solid


def stray(panel):
    """판에 몬스터가 아닌 또렷한 것(게임 마우스 커서)이 찍혀 있는가."""
    solid = solid_pixels(panel[::2, ::2])
    return int((solid & ~sprite_mask(None, solid)).sum()) > 12


def slide(image, kernel):
    """kernel을 image 위에서 밀며 곱해 더한 값 (FFT로 한 번에)."""
    tall, wide = image.shape
    spectrum = np.fft.rfft2(image) * np.conj(np.fft.rfft2(kernel, (tall, wide)))
    return np.fft.irfft2(spectrum, (tall, wide))[:tall - kernel.shape[0] + 1, :wide - kernel.shape[1] + 1]


def solve_shape(panel):
    """몬스터의 모양 전체로 찾는다. (잡을 점, 놓을 점, 설명, 몬스터 상자)를 판 기준 화면 좌표로. 몬스터를 못 찾으면 None.

    고정 상자 방법(solve)은 큰 몬스터(인어, 2026-10-13 07:42)에서 지팡이만 잡아 닮음 0.326 대 0.285로 흐릿했다.
    모양 전체로 대면 같은 판에서 0.347 대 0.066, 전사 판(00:57)은 0.454 대 0.124다.
    """
    game = panel[::2, ::2]
    mask = sprite_mask(game)
    ys, xs = np.nonzero(mask)
    if len(ys) < 30:
        return None
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    if (right - left) > game.shape[1] // 2 or (bottom - top) > game.shape[0] * 3 // 4:
        return None  # 몬스터가 판의 절반을 넘을 수는 없다. 판이 아닌 화면을 읽은 것이다 (2026-10-13 19:42)
    inside = mask[top:bottom, left:right].astype(np.float64)
    for row in inside:  # 몸 안의 구멍을 메운다: 줄마다 양 끝 사이를 채운다
        cells = np.nonzero(row)[0]
        if len(cells):
            row[cells.min():cells.max() + 1] = 1
    count = inside.sum()
    game = game.astype(np.float64)
    hit, spread, own = 0.0, 0.0, 0.0
    for channel in range(3):
        picture = game[..., channel]
        shape = game[top:bottom, left:right, channel]
        shape = (shape - (shape * inside).sum() / count) * inside
        hit = hit + slide(picture, shape)
        own += (shape ** 2).sum()
        spread = spread + slide(picture * picture, inside) - slide(picture, inside) ** 2 / count
    score = hit / np.sqrt(np.maximum(spread * own, 1e-9))
    tall, wide = inside.shape
    rows, columns = np.mgrid[:score.shape[0], :score.shape[1]]
    score[(np.abs(rows - top) < tall * 0.6) & (np.abs(columns - left) < wide * 0.6)] = -1  # 몬스터 자신
    y, x = np.unravel_index(score.argmax(), score.shape)
    best = float(score[y, x])
    score[(np.abs(rows - y) < tall * 0.6) & (np.abs(columns - x) < wide * 0.6)] = -1
    second = float(score.max())
    # 잡을 점: 상자 한가운데에서 가장 가까운 몸 위의 점 (빈 곳을 잡으면 안 끌린다. 한가운데라야 게임이 몬스터를
    # 마우스에 가운데로 붙이든 잡은 자리 그대로 끌든 같은 곳에 놓인다)
    nearest = ((ys - (top + bottom) / 2) ** 2 + (xs - (left + right) / 2) ** 2).argmin()
    grab = (int(xs[nearest]) * 2 + 1, int(ys[nearest]) * 2 + 1)
    drop = (grab[0] + int(x - left) * 2, grab[1] + int(y - top) * 2)
    box = (int(left) * 2, int(top) * 2, int(right) * 2, int(bottom) * 2)
    notes = [f"몬스터 상자 {box} (픽셀 {int(count)}개), 가장 닮은 자리 상자 왼쪽 위 ({int(x) * 2}, {int(y) * 2}) 닮음 {best:.3f}, 다른 자리 중 최고 {second:.3f}"]
    return grab, drop, notes, box, mask[top:bottom, left:right]


def locate(panel, shape):
    """판 그림에서 끌어 놓을 몬스터(shape: solve_shape가 준 또렷한 픽셀 모양)가 지금 있는 자리 (왼쪽, 위; 화면 좌표).

    또렷한 픽셀 전체의 테두리 상자(where)로 찾았더니, 판 안에 있던 게임 마우스 커서(당근 그림)까지 몬스터로 읽어서
    잡는 점이 빈 잡음 위로 갔고 세 번 다 안 끌렸다 (2026-10-13 18:39). 모양을 대 봐서 가장 많이 겹치는 자리로 찾는다.
    """
    solid = solid_pixels(panel[::2, ::2]).astype(np.float64)
    overlap = slide(solid, shape.astype(np.float64))
    y, x = np.unravel_index(overlap.argmax(), overlap.shape)
    return int(x) * 2, int(y) * 2, float(overlap[y, x] / max(shape.sum(), 1))


def where(panel):
    """판 그림에서 또렷한 몬스터가 지금 있는 상자 (왼쪽, 위, 오른쪽, 아래; 화면 좌표). 없으면 None."""
    ys, xs = np.nonzero(solid_pixels(panel[::2, ::2]))
    if len(ys) < 40:
        return None
    return int(xs.min()) * 2, int(ys.min()) * 2, int(xs.max() + 1) * 2, int(ys.max() + 1) * 2


def snap(path):
    """화면을 찍되 10초가 넘으면 그만둔다 (screencapture가 매달려 감시가 멈춘 적이 있다, 2026-10-13)."""
    import subprocess
    try:
        subprocess.run(["screencapture", "-x", str(path)], timeout=10)
    except subprocess.TimeoutExpired:
        print("  화면 찍기가 10초 넘게 걸려서 그만뒀다")


SLACK = 2  # 몬스터가 커서보다 뒤처지는 양(픽셀)의 첫 짐작. 끈 뒤 재서 고친다.
# 곧장 끌던 때(2026-10-14 00:43)에는 14픽셀 뒤처졌다. 먼저 40픽셀을 끌어 문턱을 넘기는 지금 방식에서는 14로 두었더니
# 두 번 다 10 ~ 14픽셀 넘쳤다 (03:57: 재서 4로, 06:45: 0으로 고쳐 둘째 끌기에 맞음). 그래서 거의 안 뒤처지는 것으로 본다


def drag(start, end, plain=False, slack=SLACK):
    """게임 창 기준 start를 눌러서, 그 자리에 있던 것이 end에 가 있게 끈다.

    게임은 누른 뒤 처음 14픽셀쯤의 움직임을 끌기로 안 친다 (끌기 문턱). 그래서
    - 곧장 끌면 늘 그만큼 모자라게 놓인다 (2026-10-14 00:43: 목표보다 14픽셀 앞. 10-13 15:58: 8픽셀 앞인데 통과).
    - 14픽셀짜리 보정 끌기는 통째로 무시된다 (00:43에 두 번 다 안 움직였고, 14픽셀 어긋난 채 OK를 눌러 실패했다).
    해결: 먼저 가는 방향으로 40픽셀을 끌어 문턱을 넘기고(이때부터 몬스터가 slack만큼 뒤처져 따라온다),
    커서를 end보다 그 방향으로 slack만큼 더 간 자리에 놓는다. 옮길 거리가 짧아도 같은 식으로 된다.
    이벤트마다 움직인 양(delta)을 넣는다. plain=True면 다른 길(세션 탭, 더 긴 누름)로 끈다.
    """
    import math
    import Quartz
    import wind
    origin = wind.game_window()
    if origin is None:
        raise wind.Abort
    tap = Quartz.kCGSessionEventTap if plain else Quartz.kCGHIDEventTap
    last = [None]

    def post(kind, x, y):
        point = (origin[0] + x, origin[1] + y)
        event = Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
        if kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, 1)
        if last[0] is not None:
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaX, int(round(point[0] - last[0][0])))
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaY, int(round(point[1] - last[0][1])))
        last[0] = point
        Quartz.CGEventPost(tap, event)

    def glide(a, b, steps):
        # 한 번에 5픽셀 넘게 움직이지 않는다. 빨리 끌면(한 번에 18픽셀) 몬스터가 16픽셀쯤 뒤처진 채 놓였다
        # (2026-10-14 08:40, 480픽셀을 24번에). 천천히 끈 것(한 번에 3 ~ 5픽셀)은 그대로 따라왔다
        steps = max(steps, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 5) + 1)
        for step in range(1, steps + 1):
            post(Quartz.kCGEventLeftMouseDragged, a[0] + (b[0] - a[0]) * step / steps, a[1] + (b[1] - a[1]) * step / steps)
            time.sleep(0.012)

    far = math.hypot(end[0] - start[0], end[1] - start[1])
    way = ((end[0] - start[0]) / far, (end[1] - start[1]) / far) if far >= 1 else (0.0, -1.0)  # 제자리면 위로 갔다 온다
    lead = (start[0] + way[0] * 40, start[1] + way[1] * 40)
    stop = (end[0] + way[0] * slack, end[1] + way[1] * slack)
    post(Quartz.kCGEventMouseMoved, start[0] - 6, start[1] - 6)
    time.sleep(0.05)
    post(Quartz.kCGEventMouseMoved, *start)
    time.sleep(0.15)
    post(Quartz.kCGEventLeftMouseDown, *start)
    time.sleep(0.45 if plain else 0.2)
    glide(start, lead, 10)
    glide(lead, stop, 24)
    post(Quartz.kCGEventLeftMouseDragged, *stop)
    time.sleep(0.25)
    post(Quartz.kCGEventLeftMouseUp, *stop)
    time.sleep(0.15)


PARKS = [(1180, 770), (700, 790), (1250, 880)]  # 판 밖의 빈 곳들. 찍기 전에 마우스 커서를 치운다 (커서 그림이 판에 찍히면 안 된다)


def park(spot=PARKS[0]):
    import Quartz
    import wind
    origin = wind.game_window()
    if origin is None:
        return
    for dx in (9, 6, 3, 0):  # 조금씩 움직여 가며 놓는다 (한 번에 옮기면 게임의 커서 그림이 안 따라올 때가 있었다)
        event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (origin[0] + spot[0] + dx, origin[1] + spot[1]), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaX, -3)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.04)
    time.sleep(0.2)


def shoot():
    """잡음 판을 한 장 찍는다 (높이, 너비, 3). 게임 창이 앞에 없으면 None."""
    import wind
    shot = wind.grab(*PANEL)
    if shot is None:
        return None
    raw, stride, scale = shot
    rows = len(raw) // stride
    wide = int(round(PANEL[2] * scale))  # 한 줄 끝의 여분 바이트는 버린다 (minigame.py 참고)
    frame = np.frombuffer(raw, np.uint8).reshape(rows, stride)[:, :wide * 4].reshape(rows, wide, 4)[..., :3]
    step = int(round(scale))
    return frame[::step, ::step].astype(np.float64)


def live():
    import minigame
    import nav
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%m%d-%H%M%S")
    for spot in PARKS:
        # 커서를 치우고, 정말 판에서 없어졌는지 본다. 남아 있으면 다른 자리로 다시 치운다
        # (2026-10-14 05:09: 치웠는데도 커서가 판 (120, 280)에 그대로 찍혀서 몬스터 모양을 망쳤다)
        park(spot)
        first = shoot()
        if first is None or not stray(first):
            break
        print(f"  커서가 판에 남아 있다. 다른 자리로 다시 치운다", flush=True)
    frames = []
    for _ in range(3):  # 세 장을 찍어 중앙값을 쓴다 (한 장에만 낀 것을 걸러 내려고)
        frame = shoot()
        if frame is None:
            print("게임 창이 앞에 없어서 못 찍었다")
            return
        frames.append(frame)
        time.sleep(0.1)
    np.save(OUT / f"{stamp}-frames.npy", np.array(frames, np.uint8))  # 나중에 방법을 다듬을 때 쓴다
    rough, alike = minigame.measure(frames[0][80:220, 140:340])
    if not minigame.is_noise(frames[0][80:220, 140:340]):
        # 잡음 판이 아니다. 평소 화면의 바닥 무늬가 우연히 닮아서 엉뚱한 곳을 끄는 일을 막는다
        print(f"{time.strftime('%H:%M:%S')} 미니게임 풀이: 잡음 판이 안 보여서 손대지 않는다 (거칠기 {rough:.1f}, 두 칸 상관 {alike:.2f})")
        return
    panel = np.median(frames, 0)  # 한 장에만 낀 것(시스템 창 등)은 중앙값이 걸러 낸다
    print(f"{time.strftime('%H:%M:%S')} 미니게임 풀이: 거칠기 {rough:.1f}, 두 칸 상관 {alike:.2f}")
    found = solve_shape(panel)
    if found is None:
        # 예전에는 여기서 고정 상자로라도 끌었다. 모양을 못 찾았다면 판이 아닐 수 있으므로 아무것도 끌지 않는다
        print("  끌어 놓을 몬스터의 모양을 못 찾아서 손대지 않는다", flush=True)
        return
    start, end, notes, box, shape = found
    for note in notes:
        print("  " + note)
    end = (int(end[0]), int(end[1]))
    goal = (box[0] + end[0] - start[0], box[1] + end[1] - start[1])  # 몬스터 상자의 왼쪽 위가 가야 할 자리
    at = (box[0], box[1])
    now = None

    def look():
        """커서를 치우고 판을 다시 찍어 몬스터가 지금 어디 있는지 본다."""
        nonlocal at, now
        park()
        now = shoot()
        if now is None or shape is None:
            return
        x, y, share = locate(now, shape)
        if share >= 0.6:  # 모양의 6할 이상이 겹쳐야 믿는다
            at = (x, y)
        else:
            print(f"  몬스터 자리를 못 찾았다 (겹침 {share:.2f}). 앞에서 본 자리 {at}를 쓴다", flush=True)

    close = lambda: abs(goal[0] - at[0]) <= 5 and abs(goal[1] - at[1]) <= 5
    slack = SLACK
    for attempt, plain in enumerate((False, False, False, True), 1):
        off = (goal[0] - at[0], goal[1] - at[1])
        hold = (start[0] + at[0] - box[0], start[1] + at[1] - box[1])  # 몬스터가 옮겨졌으면 잡을 점도 같이 옮긴다
        print(f"  끌기 {attempt}: 몬스터 왼쪽 위 {at} → {goal}, 잡는 점 {hold}, 문턱 {slack}" + (" (다른 방식)" if plain else ""), flush=True)
        before = at
        drag((PANEL[0] + hold[0], PANEL[1] + hold[1]), (PANEL[0] + hold[0] + off[0], PANEL[1] + hold[1] + off[1]), plain, slack)
        time.sleep(0.2)
        look()  # 끈 뒤 실제로 어디 놓였는지 본다
        if close():
            break
        # 보정은 남은 거리만큼만 끈다 (뒤처지는 양을 더하지 않는다). 짧게 끌 때는 몬스터가 그대로 따라온다.
        # 첫 끌기에서 잰 "모자란 양"을 짧은 보정에도 더했더니 보정할 때마다 20픽셀씩 넘쳐서 왔다 갔다 했다 (2026-10-14 08:40)
        slack = 10 if at == before else 0  # 전혀 안 움직였을 때만 더 멀리 끌어 본다
    moved = close()
    if now is not None:
        np.save(OUT / f"{stamp}-placed.npy", now.astype(np.uint8))
    print(f"  끈 뒤 몬스터 왼쪽 위 {at}, 가야 할 자리 {goal} → {'맞게 놓였다' if moved else '제자리에 못 놓았다'}", flush=True)
    snap(OUT / f"{stamp}-dropped.png")
    if not moved and at == (box[0], box[1]):
        print("  몬스터가 전혀 안 움직여서 OK를 누르지 않는다 (눌러도 실패다)")
        return
    nav.click(*OK_BUTTON)
    time.sleep(1.2)
    snap(OUT / f"{stamp}-after.png")
    print(f"  OK를 눌렀다. 화면 logs/minigame/{stamp}-dropped.png, {stamp}-after.png")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1].endswith(".npy"):  # 실전에서 남긴 판 그림
            start, end, notes, box, shape = solve_shape(np.median(np.load(sys.argv[1]).astype(np.float64), 0)[:, :PANEL[2]])
        else:
            start, end, notes = solve(from_file(sys.argv[1]))
        print("\n".join(notes))
        print("끌기", start, "→", end)
    else:
        live()
