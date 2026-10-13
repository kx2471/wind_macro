"""미니게임(매크로 확인) 창이 떠 있는지 본다. 떠 있으면 "minigame 값"을, 아니면 "none 값"을 찍는다.

2026-10-12 17:46에 처음 화면에 잡혔다: 게임 화면 가운데에 "왼쪽 아래의 몬스터를 드래그하여 똑같은 몬스터 위에
배치한 뒤 OK 버튼을 눌러주세요" 창이 뜨고, 그 안이 색색의 잡음 무늬로 채워져 있으며 남은 시간이 줄어든다.
못 풀면 메시지 창에 "실패!"가 찍힌다. 잡음 무늬는 옆 픽셀끼리 색이 크게 다르고 서로 닮지 않아서 게임 그림과 구분된다.

사용: .venv/bin/python minigame.py            지금 화면을 본다 (게임 창이 맨 앞이어야 한다)
      .venv/bin/python minigame.py 그림.bmp x y 너비 높이   저장된 그림의 그 영역을 본다 (시험용 BMP)
"""

import sys

import numpy as np

AREA = (800, 420, 200, 140)  # 잡음 무늬 한가운데 (게임 창 기준 x, y, 너비, 높이)
# 2026-10-12 19:58의 실제 창(원본 해상도)에서 잰 값: 거칠기 22.0, 두 칸 상관 0.06.
# 평소 게임 화면 여섯 장: 거칠기 2.4 ~ 11.8, 두 칸 상관 0.58 ~ 0.91. (처음 기준 30/25는 실제 창을 놓쳤다.)
ROUGH, ALIKE = 15.0, 0.30
SAME = 0.03  # 옆 게임 픽셀과 색이 완전히 같은 칸의 비율이 이보다 크면 잡음 판이 아니다


def measure(pixels):
    """(높이, 너비, 채널) 배열의 (거칠기, 두 칸 상관).

    거칠기: 가로로 이웃한 픽셀끼리의 평균 색 차이. 잡음 무늬는 크다.
    두 칸 상관: 두 칸 떨어진 픽셀끼리 밝기가 같이 움직이는 정도. 게임 그림은 이웃끼리 닮아서 1에 가깝고,
    잡음은 제각각이라 0에 가깝다 (게임의 점 하나가 화면 2픽셀이라 한 칸이 아니라 두 칸을 본다).
    """
    pixels = pixels[..., :3].astype(np.float64)
    rough = float(np.abs(pixels[:, 1:] - pixels[:, :-1]).mean())
    gray = pixels.mean(2)
    gray = gray - gray.mean()
    power = float((gray * gray).mean())
    alike = float((gray[:, 2:] * gray[:, :-2]).mean() / power) if power else 1.0
    return rough, alike


def is_noise(pixels):
    """전체가 잡음이거나, 네 조각 가운데 둘 이상이 잡음이면 잡음 판으로 본다.

    흐린 후보 몬스터가 보는 영역에 걸치면 값이 기준 쪽으로 밀린다 (2026-10-13 18:39의 판은 거칠기 17.1, 두 칸 상관 0.18.
    평소 판은 20.9, 0.06). 더 진한 후보가 걸쳐도 놓치지 않게 조각으로도 본다.
    """
    # 잡음은 게임 픽셀(화면 2×2)마다 색이 달라서 옆 칸과 완전히 같은 경우가 없다 (실제 판 네 장 모두 0.000).
    # 평소 화면은 0.17 ~ 0.56이다. 거칠기와 상관만 보던 때, 평소 화면(거칠기 17.9, 상관 0.21, 같은 칸 0.170)을
    # 판으로 잘못 읽어서 사용자가 직접 조작하는 중에 마우스를 끌었다 (2026-10-13 19:42)
    game = pixels[::2, ::2, :3].astype(np.int64)
    if float((game[:, 1:] == game[:, :-1]).all(2).mean()) > SAME:
        return False
    rough, alike = measure(pixels)
    if rough > ROUGH and alike < ALIKE:
        return True
    tall, wide = pixels.shape[0] // 2, pixels.shape[1] // 2
    parts = [measure(pixels[y:y + tall, x:x + wide]) for y in (0, tall) for x in (0, wide)]
    return sum(r > ROUGH and a < ALIKE for r, a in parts) >= 2


def look():
    """지금 화면의 AREA 그림(높이, 너비, 4). 게임 창이 앞에 없으면 None."""
    import wind
    shot = wind.grab(*AREA)
    if shot is None:
        return None
    raw, stride, scale = shot
    rows = len(raw) // stride
    # 한 줄 끝에 여분 바이트가 붙어 온다 (200픽셀을 달라고 하면 224픽셀 분량). 그것까지 그림으로 읽으면
    # 값이 틀어져서 실제 창을 놓친다 (2026-10-12 22:27). 진짜 너비만큼만 쓴다
    wide = int(round(AREA[2] * scale))
    return np.frombuffer(raw, np.uint8).reshape(rows, stride)[:, :wide * 4].reshape(rows, wide, 4)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = open(sys.argv[1], "rb").read()
        offset, width = int.from_bytes(data[10:14], "little"), int.from_bytes(data[18:22], "little")
        height, depth = int.from_bytes(data[22:26], "little", signed=True), int.from_bytes(data[28:30], "little") // 8
        row = (width * depth + 3) // 4 * 4
        image = np.frombuffer(data, np.uint8, row * abs(height), offset).reshape(abs(height), row)[:, :width * depth]
        image = image.reshape(abs(height), width, depth)
        if height > 0:
            image = image[::-1]
        x, y, w, h = map(int, sys.argv[2:6])
        patch = image[y:y + h, x:x + w]
    else:
        patch = look()
        if patch is None:
            print("none 0")
            raise SystemExit
    rough, alike = measure(patch)
    print(f"{'minigame' if is_noise(patch) else 'none'} {rough:.1f} {alike:.2f}")
