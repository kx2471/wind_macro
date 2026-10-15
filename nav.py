"""좌표 찾아가기. 화면의 좌표 숫자를 읽고, 걸어 본 칸을 기억하면서 목표까지 걷는다.

벽 정보가 없어서 처음에는 모든 칸이 뚫려 있다고 보고 걷는다. 걸었는데 좌표가 안 바뀌면 막힌 칸으로,
밟아 본 칸은 뚫린 칸으로 data/walls/맵이름.json 에 저장한다. 다음에는 밟아 본 길을 먼저 고른다.

사용: .venv/bin/python nav.py 맵이름 목표x 목표y      한 맵 안에서 그 칸까지
      .venv/bin/python nav.py 지금맵이름 목표맵이름   여러 맵을 거쳐 목표 맵까지
"""

import heapq
import json
import re
import sys
import time
from pathlib import Path

import Quartz

import wind

WALLS = Path(__file__).parent / "data" / "walls"
DIGITS_FILE = Path(__file__).parent / "data" / "digits.json"
DIGITS = json.loads(DIGITS_FILE.read_text()) if DIGITS_FILE.exists() else {}  # 숫자 모양 → 숫자

# 좌표 숫자 8개의 자리 (게임 창 기준). 글자 하나는 가로 6 × 세로 9 점이고 점 하나가 화면 2픽셀이다
DIGIT_X = (1585, 1603, 1621, 1639, 1675, 1693, 1711, 1729)
DIGIT_Y = 973
DOT = 2


def digit_shapes():
    """좌표 숫자 8개의 모양을 "#"과 "."으로 된 문자열 8개로 읽는다."""
    left, width = DIGIT_X[0], DIGIT_X[-1] + 6 * DOT - DIGIT_X[0]
    grabbed = wind.grab(left, DIGIT_Y, width, 9 * DOT)
    if grabbed is None:
        raise wind.Abort
    data, row_bytes, scale = grabbed
    shapes = []
    for x0 in DIGIT_X:
        shape = ""
        for row in range(9):
            for column in range(6):
                x = round((x0 - left + column * DOT) * scale)
                y = round(row * DOT * scale)
                red = data[y * row_bytes + x * 4 + 2]  # 숫자는 밝은 노랑, 배경과 테두리는 어둡다
                shape += "#" if red > 165 else "."
        shapes.append(shape)
    return shapes


def read_position():
    """화면 오른쪽 아래 좌표를 (x, y)로 읽는다. 모르는 모양이 있으면 None."""
    digits = [DIGITS.get(shape) for shape in digit_shapes()]
    if None in digits:
        return None
    return (int("".join(map(str, digits[:4]))), int("".join(map(str, digits[4:]))))


def position():
    """같은 값이 두 번 연달아 읽힐 때까지 읽는다 (숫자가 바뀌는 순간을 피하려고)."""
    last = None
    for _ in range(60):  # 3초쯤. 숫자 위에 마우스나 다른 그림이 잠깐 겹칠 수 있다
        now = read_position()
        if now is not None and now == last:
            return now
        last = now
        time.sleep(0.05)
    raise RuntimeError("좌표를 읽지 못했다")


UNKNOWN_COST = 8  # 안 밟아 본 칸은 밟아 본 칸보다 이만큼 비싸게 친다 (기록한 길을 벗어나지 않게)


def find_path(start, goal, size, blocked, free, facing=None):
    """막힌 칸을 피해 가는 가장 싼 경로의 방향 목록. 길이 없으면 None.

    방향을 바꾸면 키를 한 번 더 눌러야 해서 한 걸음만큼 비싸게 친다 (지그재그보다 직선을 고르게).
    """
    width, height = size
    distance = lambda cell: abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])
    first = (start, facing)
    queue = [(distance(start), 0, first)]
    best = {first: 0}
    came = {first: None}
    while queue:
        _, cost, state = heapq.heappop(queue)
        cell, heading = state
        if cell == goal:
            path = []
            while came[state]:
                path.append(state[1])
                state = came[state]
            return path[::-1]
        if cost > best[state]:
            continue
        for direction, (dx, dy) in wind.DELTA.items():
            nxt = (cell[0] + dx, cell[1] + dy)
            if nxt in blocked or not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                continue
            new = cost + (1 if nxt in free or nxt == goal else UNKNOWN_COST) + (direction != heading)
            if new < best.get((nxt, direction), 1e9):
                best[(nxt, direction)] = new
                came[(nxt, direction)] = state
                heapq.heappush(queue, (new + distance(nxt), new, (nxt, direction)))
    return None


def load_memory(map_name):
    """이 맵에서 기억해 둔 (막힌 칸, 밟아 본 칸)."""
    path = WALLS / f"{map_name}.json"
    if not path.exists():
        # 방 구조는 성이 달라도 번호가 같으면 거의 같다. 다른 성의 같은 번호 방에서 밟아 본 길을 빌려 온다
        # (막힌 칸은 조금 다를 수 있어서 빌리지 않는다)
        found = ROOM.fullmatch(map_name)
        twins = sorted(WALLS.glob(f"*비밀세작의집{found[3]}.json")) if found else []
        twins = [twin for twin in twins if ROOM.fullmatch(twin.stem) and ROOM.fullmatch(twin.stem)[3] == found[3]]
        if twins:
            return set(), {tuple(c) for c in json.loads(twins[0].read_text())["free"]}
        spooky = HAUNT_ROOM.fullmatch(map_name)
        if spooky:
            # 흉가는 묶음이 달라도 방이 같다. 다른 묶음의 같은 번호 방에서 걸어 본 것을 그대로 빌린다 (막힌 칸까지)
            for other in sorted(WALLS.glob(f"*흉가{spooky[3]}.json")):
                found = HAUNT_ROOM.fullmatch(other.stem)
                if found and found[3] == spooky[3]:
                    saved = json.loads(other.read_text())
                    return {tuple(c) for c in saved["blocked"]}, {tuple(c) for c in saved["free"]}
        if map_name.endswith("흉가입구") and (WALLS / "상곡흉가입구.json").exists():
            return set(), {tuple(c) for c in json.loads((WALLS / "상곡흉가입구.json").read_text())["free"]}
        return set(), set()
    saved = json.loads(path.read_text())
    if isinstance(saved, list):  # 예전 형식: 막힌 칸만
        saved = {"blocked": saved, "free": []}
    return {tuple(c) for c in saved["blocked"]}, {tuple(c) for c in saved["free"]}


TITLES = Path(__file__).parent / "data" / "titles"


def map_changed(map_image, wait=10.0):
    """맵 이름 그림이 map_image와 달라졌는지. 아는 맵 이름으로 바뀌었으면 바로 True.

    게임이 한 시간마다 화면 위에 "N시간 동안 플레이하였습니다" 안내를 몇 초 띄우는데 이 상자가 맵 이름을 덮는다.
    그때 그림만 견주면 맵이 바뀐 줄 알고 다음 방 길로 걷거나 오류를 낸다 (2026-10-12 03:57, 05:57).
    그래서 아는 맵 이름이 아닌 그림이면 wait초까지 원래 그림으로 돌아오는지 기다려 본다.
    """
    now = wind.snapshot("map_name")
    if now == map_image:
        return False
    known = [path.read_bytes() for path in TITLES.glob("*.bin")]
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if now is not None and any(title[:len(now)] == now for title in known):
            return True
        time.sleep(0.4)
        now = wind.snapshot("map_name")
        if now == map_image:
            print("  맵 이름이 잠깐 가려졌다가 돌아왔다", flush=True)
            return False
    return True


def save_memory(map_name, blocked, free):
    WALLS.mkdir(parents=True, exist_ok=True)
    saved = {"blocked": sorted(blocked - free), "free": sorted(free)}
    (WALLS / f"{map_name}.json").write_text(json.dumps(saved))


def load_ports():
    """자료의 모든 출구. {맵이름: {(x, y): 도착맵이름}} 과 {맵이름: (가로, 세로)}.

    data/ports_fixed.tsv 는 게임에서 직접 확인한 값이다 (맵이름, x, y, 도착맵이름).
    같은 맵에서 같은 곳으로 가는 자료의 칸을 이 값으로 바꾼다.
    """
    ports, sizes = {}, {}
    data = Path(__file__).parent / "data"
    for path in sorted(data.glob("ports_*.tsv")):
        if path.name == "ports_fixed.tsv":
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            row = line.split("\t")
            if len(row) == 8:
                ports.setdefault(row[1], {})[(int(row[4]), int(row[5]))] = row[7]
                sizes[row[1]] = (int(row[2]), int(row[3]))
    shift_rooms(ports, sizes)
    fixed = data / "ports_fixed.tsv"
    sized = []  # (크기를 빌릴 맵, 빌려줄 맵)
    if fixed.exists():
        for line in fixed.read_text(encoding="utf-8").splitlines()[1:]:
            name, x, y, destination = line.split("\t")
            targets = [(name, destination)]
            room, following = ROOM.fullmatch(name), ROOM.fullmatch(destination)
            if room and following:
                # 방 구조는 성이 달라도 번호가 같으면 같다고 본다. 한 성에서 확인한 방 출구를 모든 성에 쓴다
                for other in ports:
                    twin = ROOM.fullmatch(other)
                    if twin and twin[3] == room[3] and other != name:
                        targets.append((other, f"{twin[1]}{following[3]}"))
            spooky = HAUNT_ROOM.fullmatch(name)
            if spooky:
                # 흉가는 묶음(상곡흉가, 제2상곡흉가, … )이 달라도, 성이 달라도 방 안의 길이 같다 (사용자 확인, 2026-10-13).
                # 한 묶음에서 확인한 방 출구를 모든 성의 모든 묶음에 쓴다. 10번 방은 그 성으로 나간다
                onward = HAUNT_ROOM.fullmatch(destination)
                for castle in haunt_castles(spooky[2].removesuffix("흉가")):
                    for group in range(1, 10):
                        prefix = f"{castle}흉가" if group == 1 else f"제{group}{castle}흉가"
                        twin = (f"{prefix}{spooky[3]}", f"{prefix}{onward[3]}" if onward else f"부여{castle}성")
                        if twin not in targets:
                            targets.append(twin)
                        sized.append((twin[0], name))
            for map_name, goes_to in targets:
                exits = ports.setdefault(map_name, {})
                for cell in [c for c, d in exits.items() if d == goes_to]:
                    del exits[cell]
                exits[(int(x), int(y))] = goes_to
    # 흉가입구에서 각 묶음으로 들어가는 문은 설정에 적은 것을 쓴다 (자료의 문 좌표는 맞지 않는다). 모든 성의 입구가 같다고 본다
    for castle in haunt_castles():
        hall = f"{castle}흉가입구"
        # 성에서 흉가입구로 들어가는 칸: 자료와 사용자 설명은 (69, 121)인데, 그 칸에 서도 안 넘어간다 (2026-10-13 천안궁성).
        # 상곡성에서 걸어서 확인한 칸은 한 칸 위 (69, 120)이다. 모든 성에 그 칸을 쓴다
        town = ports.setdefault(f"부여{castle}성", {})
        for cell in [c for c, d in town.items() if d == hall]:
            del town[cell]
        town[(69, 120)] = hall
        exits = ports.setdefault(hall, {})
        for group, door in wind.CONFIG.get("haunt_doors", {}).items():
            first = f"{castle}흉가1" if int(group) == 1 else f"제{group}{castle}흉가1"
            for cell in [c for c, d in exits.items() if d == first]:
                del exits[cell]
            exits[(door[0], door[1])] = first
    # 흉가는 출구 자료가 없어 크기도 없다. 맵 목록의 크기를 쓴다. 게임의 흉가 k번 방은 자료의 "제8…흉가k"와
    # 구조가 비슷하다 (2026-10-10 제2상곡흉가를 걸어 본 칸 범위와 맞는다. 정확히 확인한 값은 아니다)
    index = {}
    for line in (data / "maps_index.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        row = line.split("\t")
        if len(row) == 4:
            index[row[1]] = (int(row[2]), int(row[3]))
    for name in ports:
        if name not in sizes:
            found = re.fullmatch(r"(?:제\d+)?(.+)흉가(\d+)", name)
            model = f"제8{found[1]}흉가{found[2]}" if found else name
            if model in index:
                sizes[name] = index[model]
    for name, size in index.items():
        sizes.setdefault(name, size)  # 출구 자료가 없는 맵(성황당 등)도 크기는 맵 목록에 있다
    for borrower, lender in sized:
        if lender in sizes:
            sizes[borrower] = sizes[lender]  # 길이 같다 = 크기도 같다 (맵 목록의 크기는 성마다 달라서 믿지 않는다)
    for castle in haunt_castles():
        if "상곡흉가입구" in sizes:
            sizes[f"{castle}흉가입구"] = sizes["상곡흉가입구"]
    return ports, sizes


def haunt_castles(first=None):
    """흉가를 돌 수 있는 성 이름들 (설정의 haunt_castles). first를 주면 그 성을 꼭 넣는다."""
    names = list(wind.CONFIG.get("hunt", {}).get("haunt_castles", ["상곡"]))
    if first and first not in names:
        names.insert(0, first)
    return names


HAUNT_ROOM = re.compile(r"(제\d+)?(.+흉가)(\d+)")  # 흉가의 방: (묶음 앞머리, 바탕 이름, 방 번호)
ROOM = re.compile(r"((?:제\d+)?(.+)비밀세작의집)(\d+)")


def shift_rooms(ports, sizes):
    """비밀세작의집 방의 크기와 출구를 게임에 맞게 고친다.

    게임(옛날바람)의 방은 사이트 자료와 한 방씩 밀려 있다. 게임의 k번 방은 어느 성이든 자료의
    "부여비밀세작의집k"와 크기·출구가 같다 (만번한 1번 방의 출구와 2번 방 도착 좌표로 확인).
    """
    for name in list(ports):
        found = ROOM.fullmatch(name)
        if not found or found[2] == "부여":
            continue
        base, castle, number = found[1], found[2], int(found[3])
        model = f"부여비밀세작의집{number}"
        exits = {}
        for cell, destination in ports[model].items():
            if destination == f"부여비밀세작의집{number + 1}":
                exits[cell] = f"{base}{number + 1}"
            elif destination == f"부여비밀세작의집{number - 1}":
                exits[cell] = f"{base}{number - 1}"
            elif number == 1:
                exits[cell] = f"{castle}비밀세작의집입구"  # 1번 방에서 뒤로 나가면 입구
        ports[name] = exits
        sizes[name] = sizes[model]
        if number == 9:
            # 자료에는 9번까지만 있지만 게임에는 10번 방이 있고, 거기서 성으로 나간다 (사용자가 걸어서 확인)
            town = "동부여성" if castle == "동부여" else f"부여{castle}성"
            last = {}
            for cell, destination in ports["부여비밀세작의집10"].items():
                last[cell] = f"{base}9" if destination == "부여비밀세작의집9" else town
            ports[f"{base}10"] = last
            sizes[f"{base}10"] = sizes["부여비밀세작의집10"]


def find_route(start_map, goal_map, ports):
    """start_map에서 goal_map까지 거쳐 갈 [(맵이름, 밟을 출구 칸, 다음 맵이름)]. 길이 없으면 None."""
    came = {start_map: None}
    queue = [start_map]
    while queue:
        name = queue.pop(0)
        if name == goal_map:
            route = []
            while came[name]:
                previous, cell = came[name]
                route.append((previous, cell, name))
                name = previous
            return route[::-1]
        for cell, destination in ports.get(name, {}).items():
            if destination not in came:
                came[destination] = (name, cell)
                queue.append(destination)
    return None


NEAR = 4  # 출구는 자료의 한 칸보다 넓을 수 있다. 목표에서 이 칸 수 안에서 맵이 바뀌면 도착으로 본다


def go_back(direction, map_image):
    """엉뚱한 출구를 밟아 다른 맵에 들어갔을 때 바로 돌아 나온다. 돌아왔으면 돌아온 좌표."""
    time.sleep(wind.ROAM["map_wait"])
    for _ in range(4):
        wind.tap(wind.OPPOSITE[direction])
        time.sleep(wind.ROAM["map_wait"])
        if wind.snapshot("map_name") == map_image:
            return position()
    raise RuntimeError(f"다른 맵에서 돌아오지 못했다. 지금 좌표 {position()}")


STEP_INTERVAL = 0.36  # 걸음 사이 최소 간격(초). 0.30초 이하로 누르면 게임이 절반을 버린다 (실측)
MOVE_TIMEOUT = 0.3    # 누른 뒤 이 시간 안에 좌표가 안 바뀌면 못 움직인 것 (움직이면 0.12~0.14초에 바뀐다)
last_tap = 0.0


def try_step(direction, here, map_image):
    """방향키를 한 번 누르고 좌표나 맵이 바뀌길 기다린다. 바뀐 좌표, 안 바뀌면 here."""
    global last_tap
    rest = last_tap + STEP_INTERVAL - time.monotonic()
    if rest > 0:
        time.sleep(rest)
    last_tap = time.monotonic()
    wind.tap(direction)
    end = last_tap + MOVE_TIMEOUT
    while time.monotonic() < end:
        if wind.snapshot("map_name") != map_image:
            return here
        if read_position() not in (None, here):
            return position()
        time.sleep(0.01)
    return here


last_exit = None  # 마지막으로 맵을 바꾼 칸


def go(map_name, goal, ports=None, sizes=None, max_steps=1500, near=NEAR, before_step=None, is_monster=None, quiet=False):
    """goal 칸까지 걷는다. goal을 밟아 맵이 바뀌면 "left", 맵이 안 바뀌고 도착하면 "arrived".

    - 자료에 있는 다른 출구 칸은 처음부터 피해 간다.
    - 걸었는데 좌표가 안 바뀌면 막힌 칸으로 기록하고 돌아간다.
    - 자료에 없는 출구를 밟아 맵이 바뀌면 바로 돌아 나오고 그 칸을 막힌 칸으로 기록한다.

    before_step()은 걸음마다 먼저 불린다 (사냥). is_monster()는 막혔을 때 불리고, 참이면 벽으로 적지 않는다.
    """
    global last_exit
    if ports is None:
        ports, sizes = load_ports()
    exits = set(ports.get(map_name, {}))
    walls, free = load_memory(map_name)
    blocked = (walls | exits) - {goal}
    here = position()
    free.add(here)
    map_image = wind.snapshot("map_name")  # 맵 이름 그림. 이게 바뀌면 맵이 바뀐 것
    facing = None  # 마지막으로 누른 방향. 같은 방향을 또 누르면 돌기만 하는 일이 없다
    fresh = set()  # 이번 걸음에서 새로 막힌 칸으로 적은 것. 몹이 서 있던 칸일 수 있다
    if not quiet:
        print(f"{map_name} {here} → {goal}, 아는 막힌 칸 {len(walls)}개, 밟아 본 칸 {len(free)}개")
    try:
        for _ in range(max_steps):
            if before_step:
                before_step()
                if map_changed(map_image):
                    raise RuntimeError(f"{map_name}에서 싸우는 중에 맵이 바뀌었다")
                moved = position()
                if moved != here:  # 싸우다 밀렸다
                    here, facing = moved, None
                    free.add(here)
            if here == goal and quiet:
                return "arrived"
            if here == goal:
                # 출구 칸은 좌표가 먼저 바뀌고 맵이 조금 뒤에 바뀐다
                time.sleep(wind.ROAM["map_wait"])
                if map_changed(map_image):
                    print(f"  {time.strftime('%H:%M:%S')} {goal}을 밟고 맵이 바뀌었다. 도착 좌표 {read_position()}", flush=True)
                    last_exit = goal
                    return "left"
                return "arrived"
            path = find_path(here, goal, sizes[map_name], blocked, free, facing)
            if path is None and fresh:
                # 몹이 통로를 막고 있을 때 그 칸이 벽으로 적히면 문이 닫힌 것으로 계산돼서, 벽을 따라 방 끝까지 더듬어 간 뒤
                # 제자리에서 맴돈다 (2026-10-12 05:41 6번 방 8분, 06:35 9번 방 10분). 이번 걸음에서 적은 것은 다 지우고 다시 찾는다
                print(f"  길이 없다. 이번 걸음에서 막힌 칸으로 적은 {len(fresh)}칸을 지우고 다시 찾는다", flush=True)
                blocked -= fresh
                walls -= fresh
                fresh.clear()
                continue
            if path is None:
                # 몹이 사방을 막고 있을 때 옆 칸들이 벽으로 잘못 적히면 그 자리에 갇힌다
                # (제3상곡 5번 방 (14, 4)에서 네 칸이 다 막힌 칸으로 적혀 3분을 서 있었다). 내 옆의 막힌 칸은 지우고 다시 찾는다
                beside = {(here[0] + ax, here[1] + ay) for ax, ay in wind.DELTA.values()} & blocked
                if not beside:
                    raise RuntimeError(f"{here}에서 {goal}까지 길이 없다")
                print(f"  갇혔다. 옆의 막힌 칸 {sorted(beside)} 기록을 지우고 다시 찾는다", flush=True)
                blocked -= beside
                if len(beside) == 4:
                    # 네 방향이 다 안 움직였다 = 키가 게임에 안 들어가고 있을 수 있다 (맥 알림 창이 키를 가져간 채로 죽은 적이 있다)
                    wind.refocus()
                continue
            direction = path[0]
            dx, dy = wind.DELTA[direction]
            target = (here[0] + dx, here[1] + dy)
            now = here
            for _ in range(1 if facing == direction else 2):  # 방향이 다르면 첫 입력은 돌기만 할 수 있다
                now = try_step(direction, here, map_image)
                if now != here or wind.snapshot("map_name") != map_image:
                    break
            facing = direction
            if map_changed(map_image):
                if abs(target[0] - goal[0]) + abs(target[1] - goal[1]) <= near:
                    time.sleep(wind.ROAM["map_wait"])
                    print(f"  {time.strftime('%H:%M:%S')} {target}을 밟고 맵이 바뀌었다. 도착 좌표 {read_position()}", flush=True)
                    last_exit = target
                    return "left"
                print(f"  {target}을 밟았더니 다른 맵으로 갔다. 자료에 없는 출구 → 돌아 나온다")
                blocked.add(target)
                walls.add(target)
                now = go_back(direction, map_image)
                facing = None
                print(f"  돌아왔다 {now}")
            elif now == here:
                if wind.prompt_open():
                    # 입력창이 열려 있으면 방향키가 안 먹는다. 벽으로 적지 않고 닫은 뒤 다시 한다
                    print("  입력창이 열려 있어 닫는다")
                    wind.tap("esc")
                    time.sleep(0.1)
                    if wind.prompt_open():
                        # Esc를 눌렀는데도 안 닫혔다. 키가 게임에 안 들어가고 있다
                        print("  Esc가 안 먹는다 → 게임 창을 다시 잡는다", flush=True)
                        wind.refocus()
                    facing = None
                    continue
                if is_monster and is_monster():
                    continue  # 몹이 길을 막고 있었다. 벽이 아니다
                if quiet:
                    raise RuntimeError("막혔다")  # 몹에게 다가가는 중: 몹일 수 있으니 벽으로 적지 않는다
                blocked.add(target)
                walls.add(target)
                fresh.add(target)
                print(f"  막힘 {target}")
            elif now != target:
                # 맵은 그대로인데 한 칸보다 많이 움직였다 = 밀렸거나 읽는 순간이 어긋났다. 다시 읽는다
                time.sleep(0.3)
                now = position()
                print(f"  좌표가 {here} → {now}. 다시 읽고 계속")
            free.add(now)
            here = now
        raise RuntimeError("걸음 수 한도를 넘었다")
    finally:
        save_memory(map_name, walls, free)


# 비영사천문: 성 안에서 동서남북 문 앞으로 순간이동한다. 누르면 "갈 곳은? 동(1), 서(2), 남(3), 북(4)?"가 뜬다.
# 도착 좌표는 부여범안성에서 잰 값이다. 부여의 성은 크기와 출구가 같아서 다른 성도 같다고 가정한다.
GATES = {1: (134, 88), 2: (9, 88), 3: (76, 143), 4: (74, 16)}
GATE_GAIN = 10  # 문으로 날아가면 이 칸 수 넘게 가까워질 때만 쓴다


def is_castle(map_name):
    return map_name == "동부여성" or (map_name.startswith("부여") and map_name.endswith("성"))


def teleport(number):
    """비영사천문으로 문 앞에 간다. 갔으면 True."""
    before = position()
    for key in wind.KEYS["gate"]:
        wind.tap(key)
    time.sleep(0.2)
    if not wind.prompt_open():  # 입력창이 안 떴는데 숫자를 누르면 다른 스킬이 나간다
        return False
    wind.tap(str(number))
    wind.tap("enter")
    time.sleep(wind.ROAM["map_wait"])
    if wind.prompt_open():
        wind.tap("esc")
        return False
    return position() != before


def use_gate(goal):
    """goal에 더 가까운 문이 있으면 그 문으로 날아간다."""
    if not wind.KEYS.get("gate"):
        return
    distance = lambda cell: abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])
    number = min(GATES, key=lambda n: distance(GATES[n]))
    if distance(GATES[number]) + GATE_GAIN < distance(position()):
        print(f"  비영사천문 {number} → {GATES[number]} 근처" if teleport(number) else "  비영사천문 실패, 걸어서 간다")


# 세계지도 화면에서 각 성 그림의 위치 (게임 창 기준 픽셀). 성 그림을 누르면 그 성의 북문 안쪽으로 간다.
# 천안궁성만 눌러 봤다. 나머지는 화면에서 읽은 위치다.
WORLD = {
    "부여상곡성": (675, 258), "부여천안궁성": (880, 337), "부여송원성": (1348, 332), "부여장훈성": (1231, 446),
    "부여어양성": (543, 566), "부여만번한성": (919, 605), "동부여성": (1454, 558), "부여읍루성": (1100, 746),
    "부여관령성": (535, 798), "부여범안성": (745, 880), "부여성": (1441, 836),
}


def click(x, y):
    """게임 창 기준 (x, y)를 마우스 왼쪽 버튼으로 누른다."""
    origin = wind.game_window()
    if origin is None:
        raise wind.Abort
    point = (origin[0] + x, origin[1] + y)
    for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        event = Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, wind.MAGIC)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.08)


def world_hop(castle, target, ports, sizes):
    """성 castle에서 세계지도를 거쳐 성 target으로 간다.

    북문으로 날아가 그대로 위로 걸으면 맵 맨 윗줄에서 세계지도 화면이 뜬다 (부여성은 다르다고 한다).
    세계지도 화면에서는 좌표 숫자가 안 보인다. 그걸로 화면이 떴는지 확인한다.
    """
    if not teleport(4):
        raise RuntimeError("비영사천문(북)이 안 됐다")
    # 자료의 세계지도 칸에서 시작해 맨 윗줄을 좌우로 훑는다 (실제 출구는 자료와 한두 칸 다르다)
    known = [cell for cell, name in ports.get(castle, {}).items() if name == "세계지도"]
    start = known[0][0] if known else position()[0]
    for offset in (0, 1, 2, 3, 4, -1, -2, 5, 6):
        if go(castle, (start + offset, 0), ports, sizes, near=8) == "left":
            break
    else:
        raise RuntimeError(f"{castle} 맨 윗줄을 훑었는데 세계지도가 안 떴다")
    time.sleep(wind.ROAM["map_wait"])
    if read_position() is not None:
        raise RuntimeError(f"{castle}에서 맵은 바뀌었는데 세계지도 화면이 아니다")
    click(*WORLD[target])
    for _ in range(50):
        time.sleep(0.2)
        if read_position() is not None:
            print(f"  세계지도 → {target} {position()}")
            return
    raise RuntimeError(f"세계지도에서 {target}을 눌렀는데 화면이 안 바뀌었다")


def travel(start_map, goal_map):
    """여러 맵을 거쳐 goal_map까지 간다. 지금 start_map에 있다고 믿고 시작한다.

    가는 길에 성이 둘 이상 있으면 그 사이는 걷지 않고 세계지도로 건너뛴다.
    """
    ports, sizes = load_ports()
    route = find_route(start_map, goal_map, ports)
    if route is None:
        raise RuntimeError(f"{start_map}에서 {goal_map}까지 가는 길이 자료에 없다")
    castles = [i for i, leg in enumerate(route) if is_castle(leg[0])]
    if len(castles) > 1 and route[castles[0]][0] != "부여성":
        first, last = castles[0], castles[-1]
        route = route[:first] + [(route[first][0], "world", route[last][0])] + route[last:]
    print(" → ".join([start_map] + [leg[2] for leg in route]))
    for name, cell, destination in route:
        if cell == "world":
            world_hop(name, destination, ports, sizes)
            continue
        if is_castle(name):
            use_gate(cell)
        if go(name, cell, ports, sizes) != "left":
            raise RuntimeError(f"{name}의 {cell}을 밟았는데 맵이 안 바뀌었다")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        travel(sys.argv[1], sys.argv[2])
    else:
        print(go(sys.argv[1], (int(sys.argv[2]), int(sys.argv[3]))), position())
