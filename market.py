"""호박을 팔러 부여장터에 다녀온다. 부여상곡성에서 시작해서 부여상곡성으로 돌아온다.

사용자가 직접 걸어서 알려 준 길이다 (2026-10-13, logs/route-장터/route.txt):
1. 부여성비서(u, h) → 부여성
2. 비영사천문 북(4) → (74, 13). 서쪽으로 y=12를 따라 (11, 12), 북으로 (11, 5), (13, 5), 북으로 (13, 0)을 밟으면 부여장터 (22, 42)
3. 장터 (22, 40)에서 "호박 다 판다", "진호박 다 판다"라고 말한다 (팔 것이 없으면 장돌뱅이가 "물건이 모자랍니다"라고 한다)
4. 장터 (22, 43)을 밟으면 부여성 (12, 2)
5. 비영사천문 북 → 동쪽으로 y=13을 따라 (115, 13), 북으로 (115, 0)을 밟으면 세계지도 → 상곡성 → 부여상곡성 (73, 3)
북문에서 곧장 위로 가면 (70, 0)에서 부여진입로로 나가 버린다. 그래서 꼭 거쳐 갈 칸을 차례로 준다.

사용: .venv/bin/python -u market.py      (부여상곡성에 서 있을 때)
"""

import time
from pathlib import Path

import numpy as np

import nav
import wind

WORDS = ["호박 다 판다", "진호박 다 판다"]
TO_MARKET = [(11, 12), (11, 6), (13, 0)]  # 사용자는 (11, 5) → (13, 5) → (13, 0)으로 걸었다. (13, 5)에 사람이 서 있기도 해서 뺐다
TO_WORLD = [(115, 13), (115, 0)]


def where():
    title = wind.snapshot("map_name")
    for file in nav.TITLES.glob("*.bin"):
        if title and file.read_bytes()[:len(title)] == title:
            return file.stem
    return None


def arrive(name, wait=6.0):
    """맵 이름이 name이 될 때까지 기다린다. 안 되면 오류."""
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if where() == name and nav.read_position() is not None:
            return
        time.sleep(0.2)
    raise RuntimeError(f"{name}에 와 있어야 하는데 지금은 {where()}다")


def walk(name, cells, ports, sizes):
    """cells를 차례로 거쳐 간다. 마지막 칸에서 맵이 바뀌면 True.

    거쳐 가는 칸은 방향만 잡아 주는 것이라 꼭 밟지 않아도 된다. 그 칸에 사람이 서 있으면 끝없이 맴돌기 때문에
    (2026-10-13 20:00, 부여성 (13, 5)에 다른 사람이 서 있었다) 150걸음 안에 못 밟으면 다음 칸으로 넘어간다.
    """
    for index, cell in enumerate(cells):
        last = index == len(cells) - 1
        try:
            if nav.go(name, cell, ports, sizes, near=0, max_steps=1500 if last else 150) == "left":
                return True
        except RuntimeError as error:
            if last or "걸음 수 한도" not in str(error):
                raise
            print(f"  {cell}을 못 밟았다 (누가 서 있는 듯). 다음 칸으로 간다", flush=True)
    return False


def forget_people(name):
    """성과 장터에서는 길을 막는 것이 벽이 아니라 사람이다. 막힌 칸으로 적어 둔 것을 지운다 (밟아 본 칸은 둔다)."""
    blocked, free = nav.load_memory(name)
    if blocked:
        nav.save_memory(name, set(), free)


def north():
    """부여성에서 비영사천문으로 북문에 간다. 한 번에 안 될 때가 있어서 세 번까지 한다."""
    for attempt in range(3):
        if wind.prompt_open():
            wind.tap("esc")
            time.sleep(0.3)
        if nav.teleport(4):
            return
        time.sleep(0.8)
    raise RuntimeError("부여성에서 비영사천문(북)이 안 됐다")


def say(text):
    wind.tap("enter")
    time.sleep(0.3)
    wind.type_text(text)
    time.sleep(0.2)
    wind.tap("enter")
    time.sleep(1.0)


def sell(home="부여상곡성"):
    """home에서 부여장터에 가서 호박을 팔고 home으로 돌아온다. 돌아온 성 이름을 돌려준다.
    """
    scroll = wind.KEYS.get("buyeo_scroll")
    if not scroll:
        raise RuntimeError("부여성비서 키(buyeo_scroll)가 설정에 없다")
    ports, sizes = nav.load_ports()
    started = time.monotonic()
    forget_people("부여성")
    forget_people("부여장터")
    wind.refocus()
    if wind.prompt_open():
        wind.tap("esc")
    for attempt in range(3):
        # 부여성비서가 한 번에 안 써질 때가 있다 (2026-10-13 20:59: 6초를 기다려도 안 넘어갔다가 다시 누르니 됐다)
        for key in scroll:
            wind.tap(key)
            time.sleep(0.5)
        try:
            arrive("부여성", wait=5)
            break
        except RuntimeError:
            if attempt == 2:
                raise
            if wind.prompt_open():
                wind.tap("esc")
            time.sleep(0.5)
    print(f"  부여성비서 → 부여성 {nav.position()}", flush=True)
    north()
    if not walk("부여성", TO_MARKET, ports, sizes):
        raise RuntimeError(f"부여성 {TO_MARKET[-1]}을 밟았는데 장터로 안 넘어갔다 ({nav.position()})")
    time.sleep(wind.ROAM["map_wait"])
    arrive("부여장터")
    print(f"  부여장터 {nav.position()}", flush=True)
    nav.go("부여장터", (22, 40), ports, sizes, near=0)
    for words in WORDS:
        say(words)
    if wind.prompt_open():
        wind.tap("esc")
    print(f"  {WORDS}라고 말했다", flush=True)
    if nav.go("부여장터", (22, 43), ports, sizes, near=0) != "left":
        raise RuntimeError(f"장터 (22, 43)을 밟았는데 부여성으로 안 나갔다 ({nav.position()})")
    time.sleep(wind.ROAM["map_wait"])
    arrive("부여성")
    north()
    if not walk("부여성", TO_WORLD, ports, sizes):
        raise RuntimeError(f"부여성 {TO_WORLD[-1]}을 밟았는데 세계지도가 안 떴다 ({nav.position()})")
    time.sleep(wind.ROAM["map_wait"])
    if nav.read_position() is not None:
        raise RuntimeError("부여성에서 맵은 바뀌었는데 세계지도 화면이 아니다")
    nav.click(*nav.WORLD[home])
    end = time.monotonic() + 4
    while time.monotonic() < end and nav.read_position() is None:
        time.sleep(0.2)
    if nav.read_position() is None:
        wind.tap("enter")  # 사용자는 Enter로 넘어갔다 (상곡성이 골라져 있었다)
    if home not in {file.stem for file in nav.TITLES.glob("*.bin")}:
        # 처음 가 보는 성이다. 맵 이름 그림을 모른다 → 좌표가 읽히면 도착한 것으로 보고 그림을 그 이름으로 저장한다
        time.sleep(wind.ROAM["map_wait"])
        title = wind.snapshot("map_name")
        if nav.read_position() is None or not title or where() is not None:
            raise RuntimeError(f"{home}에 왔어야 하는데 지금은 {where()}다")
        (nav.TITLES / f"{home}.bin").write_bytes(title)
        print(f"  {home}은 처음이다. 맵 이름 그림을 저장했다", flush=True)
    arrive(home, wait=10)
    print(f"  세계지도 → {home} {nav.position()} ({time.monotonic() - started:.0f}초 걸림)", flush=True)
    return home


if __name__ == "__main__":
    sell()


# ── 가방에 호박이 100개 찼는지 본다 ──────────────────────────────────────────────
# 호박은 100개까지만 가질 수 있고, 100개일 때 또 주우려 하면 "호박 100개 이상 가질 수 없습니다"가 뜬다 (사용자 설명).
# 그 글의 견본은 없지만 오른쪽 가방 목록에 "호박 100개"라고 찍힌 화면은 있다 (2026-10-13 18:40, data/pumpkin100.npy).
# 가방 목록에서 그 글자 모양을 그대로 찾는다. 가방이 호박이 있는 쪽을 보여 주고 있어야 한다 (show_bag).
BAG = (1390, 100, 380, 490)  # 오른쪽 칸 (게임 창 기준 x, y, 너비, 높이). 가방 목록이 여기 찍힌다
_full = None


def name_pixels(picture):
    """가방 목록의 아이템 이름 글자(노란색)만 True. picture는 (높이, 너비, 3) RGB."""
    picture = picture.astype(np.int64)
    return (picture[..., 0] > 170) & (picture[..., 1] > 170) & (picture[..., 2] < 150)


def pumpkin_state(picture):
    """RGB 그림(가방 목록)에서 호박 줄을 찾는다: "full"(호박 100개), "some"(호박 줄은 있다), None(이 쪽에는 없다).

    앞에 글자가 더 붙은 "진호박", "황금호박"은 호박으로 치지 않는다 (호박 앞 한 글자 너비가 비어 있어야 한다).
    줄이 어느 칸(글자)에 있든 상관없다. 목록 전체에서 글자 모양을 찾는다.
    2026-10-13에 찍힌 화면 104장으로 재 보니 15:10(호박 97개)까지는 "some", 15:31(100개)부터는 전부 "full"이었다.
    """
    global _full
    if _full is None:
        _full = np.load(Path(__file__).parent / "data" / "pumpkin100.npy")
    mask = name_pixels(picture).astype(np.float64)

    def found(letters, after):
        tall, wide = letters.shape
        shape = np.zeros((tall, 26 + wide + after))  # 앞(한 글자 너비)과 뒤가 비어 있어야 한다
        shape[:, 26:26 + wide] = letters
        if mask.shape[0] < shape.shape[0] or mask.shape[1] < shape.shape[1]:
            return False
        hit, ink, count = slide(mask, shape), slide(mask, np.ones(shape.shape)), letters.sum()
        return bool(((hit >= count - 3) & (ink <= count + 3)).any())

    if found(_full, 24):
        return "full"
    return "some" if found(_full[:, :45], 8) else None  # 앞 45픽셀이 "호박" 두 글자. 뒤 빈칸은 숫자에 따라 12 ~ 16픽셀이라 8만 본다


def has_full_pumpkins(picture):
    return pumpkin_state(picture) == "full"


def slide(image, kernel):
    tall, wide = image.shape
    spectrum = np.fft.rfft2(image) * np.conj(np.fft.rfft2(kernel, (tall, wide)))
    return np.fft.irfft2(spectrum, (tall, wide))[:tall - kernel.shape[0] + 1, :wide - kernel.shape[1] + 1]


def bag_picture():
    shot = wind.grab(*BAG)
    if shot is None:
        return None
    raw, stride, scale = shot
    rows = len(raw) // stride
    wide = int(round(BAG[2] * scale))
    step = int(round(scale))
    return np.frombuffer(raw, np.uint8).reshape(rows, stride)[:, :wide * 4].reshape(rows, wide, 4)[::step, ::step, 2::-1]


def pumpkins_full():
    """지금 화면의 가방 목록에 "호박 100개"가 보이는가."""
    picture = bag_picture()
    return picture is not None and has_full_pumpkins(picture)


_looked = 0.0


def watch_pumpkins(search_every=600):
    """호박이 100개 찼으면 True. 호박 줄이 지금 쪽에 안 보이면 가끔(search_every초마다) 쪽을 넘겨 찾아 그 쪽을 띄워 둔다.

    호박이 어느 칸에 들어갈지는 정해져 있지 않다 (사용자: 랜덤). 팔고 나면 줄이 없어졌다가 다시 주울 때 생긴다.
    가방은 i로 띄우고 Page Down / Page Up으로 넘긴다 (세 쪽. 끝에서는 더 안 넘어간다).
    마우스로 화살표를 눌렀더니 다른 단추가 눌려 상태창으로 바뀌었다 (2026-10-13). 그래서 키로 한다.
    """
    global _looked
    picture = bag_picture()
    if picture is None:
        return False
    state = pumpkin_state(picture)
    if state:
        return state == "full"
    if time.monotonic() - _looked < search_every:
        return False
    _looked = time.monotonic()
    wind.tap("i")  # 오른쪽 칸이 상태창이면 가방으로 바뀐다. 이미 가방이면 그대로다
    time.sleep(0.4)
    for _ in range(2):  # 첫 쪽으로
        wind.tap("pageup")
        time.sleep(0.25)
    for page in (1, 2, 3):
        picture = bag_picture()
        state = pumpkin_state(picture) if picture is not None else None
        if state:
            print(f"   가방 {page}쪽에 호박 줄이 있다 ({state}). 이 쪽을 띄워 둔다", flush=True)
            return state == "full"
        if page < 3:
            wind.tap("pagedown")
            time.sleep(0.35)
    wind.tap("pageup")  # 호박이 아직 없다. 둘째 쪽을 띄워 둔다
    return False
