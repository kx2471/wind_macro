"""비밀세작의집의 방을 차례로 지나가며 사냥한다. 사냥은 방 안에서만 한다.

사용: .venv/bin/python hunt.py 지금있는맵이름      (끝없이 돈다. Ctrl+C로 끈다)
예:   .venv/bin/python hunt.py 부여만번한성              (성의 입구 건물 앞에서 시작)
      .venv/bin/python hunt.py 만번한비밀세작의집입구    (입구에서 시작)
      .venv/bin/python hunt.py 제2만번한비밀세작의집4    (제2 묶음 4번 방에서 이어서)

도는 순서: 1번 묶음 1~10번 방 → 성으로 나옴 → 제2 묶음 1~10번 → 제3 → 제4 → 다시 1번 묶음.

다음 방 출구 쪽으로 걸으면서, 몇 걸음마다(또는 맞아서 체력이 줄면) 화면에 몹이 있는지 본다.
몹이 있으면 더 안 잡힐 때까지 그 자리에서 잡고 다시 걷는다.
"""

import os
import re
import sys
import time
from pathlib import Path

import nav
import wind
from wind import AUTO, KEYS

HUNT = wind.CONFIG["hunt"]
DEBUG_DIR = __import__("os").environ.get("HUNT_DEBUG")  # 지정하면 기본 공격 방향을 고를 때 화면을 저장한다


class Dead(Exception):
    """캐릭터가 죽었다."""


BLOCKER_FILE = Path(__file__).parent / "data" / "look_blockers.txt"  # 살펴보기에 찍히는 이름 중 몹(막는 것)의 글자 그림
BLOCKERS = {bytes.fromhex(line) for line in BLOCKER_FILE.read_text().split()} if BLOCKER_FILE.exists() else set()


NOISE = set()  # 살펴보기와 상관없이 메시지 창에 찍히는 줄 (주문 메시지 등)의 글자 그림


def look_lines():
    """오른쪽 메시지 창에 보이는 네 줄의 글자 그림 (위에서 아래로). 글자가 없는 줄은 0으로 찬 바이트."""
    import numpy as np
    x, y, width, height = wind.REGIONS["messages"]
    shot = wind.grab(x, y, width, height)
    if shot is None:
        raise wind.Abort
    data, row_bytes, scale = shot
    pixels = np.frombuffer(data, dtype=np.uint8).reshape(-1, row_bytes)[:, :int(width * scale) * 4]
    pixels = pixels.reshape(pixels.shape[0], -1, 4)[:, :, :3].astype(int).sum(axis=2)
    ink = pixels < 200  # 글자는 어둡고(합 120쯤) 바탕은 밝다(360 이상)
    top, pitch, tall = int(13 * scale), int(24 * scale), int(22 * scale)  # 줄은 24픽셀마다, 글자 높이 22픽셀
    return [np.packbits(ink[top + pitch * k:top + pitch * k + tall]).tobytes() for k in range(4)]


def new_lines(before, after):
    """메시지 창이 before에서 after로 바뀌었을 때 새로 찍힌 줄들. 안 바뀌었으면 빈 목록."""
    if before == after:
        return []
    for count in range(1, len(after)):
        if after[:-count] == before[count:]:
            return after[-count:]
    return list(after)


class Fighter:
    def __init__(self):
        self.healing = False
        self.drained = False   # 헬파이어로 마력을 다 써서 공력증강 전에 물약이 필요한 상태
        self.hellfire_at = 0.0
        self.bomu_at = 0.0
        self.misfire_shots = 0  # 헬파이어가 안 나간 순간의 화면을 몇 장 남겼는지
        self.suspect = None    # (칸, 글자 그림): 살펴보기에 한 줄 찍혔는데 못 들어간 칸. 몹이 맞으면 그 이름을 외운다
        self.drops = set()     # 싸우는 동안 몹이 붙어 있던 칸. 싸움이 끝나면 밟고 줍는다
        self.lock_at = 0.0     # 대상 고정을 다음에 확인할 시각
        self.curse_at = 0.0
        self.poison_at = 0.0
        self.steps = HUNT["scan_every"]  # 처음 한 번은 바로 본다
        self.walked = 0  # 마지막으로 저주를 건 뒤 걸은 칸 수
        self.refill_fails = 0    # 공력증강으로 마력을 못 채운 연속 횟수
        self.dead_checks = 0     # 체력이 0으로 읽힌 연속 횟수
        self.hellfire_mana = []  # 헬파이어를 쓸 때의 마력 비율들
        self.last_seen = []    # 마지막으로 본 몹들의 위치 (나로부터의 칸 차이)
        self.swinging = False  # 기본 공격 키를 누르고 있는지
        self.facing = None     # 기본 공격을 하려고 마지막으로 돌아선 방향
        self.chum = False  # 힐 사이에 끼워 넣을 첨 차례 (첨 1, 첨 2를 번갈아)
        self.last_hp = 1.0
        self.count = {"hellfire": 0, "attack": 0, "ranged": 0, "curse": 0, "poison": 0, "approach": 0, "bomu": 0, "rescue": 0, "basic": 0, "spam": 0}
        self.room = None   # 지금 있는 방 이름 (몹에게 걸어갈 때 길찾기에 쓴다)
        self.ports = self.sizes = None

    def heal(self):
        """힐을 한 번 쓴다. 체력이 올랐으면 True.

        마력이 바닥이면 힐을 못 쓴다. 동동주는 한 잔에 마력 30, 공력증강은 30이 들고 마력을 가득 채운다.
        그래서 바닥일 때는 동동주 1잔 → 공력증강으로 한 번에 채운 뒤 힐을 쓴다 (동동주만으로는 못 채운다).
        """
        hp, mp = wind.read_bars() or (1.0, 1.0)
        if mp < AUTO["potion_below"]:
            wind.drink()
            wind.tap(KEYS["gongjeung"])  # 체력을 깎지만 마력이 없으면 힐을 못 쓴다. 한 번만 누른다
            wind.sleep(0.15)
        wind.cast_self(KEYS["heal"])
        # 힐을 쓰는 사이에도 첨은 나간다. 힐 한 번마다 첨 하나를 번갈아 끼워 넣는다
        self.chum = not self.chum
        wind.tap(KEYS["attack1"] if self.chum else KEYS["attack2"])
        if self.swinging:
            self.swing()
        return (wind.read_bars() or (1.0, 1.0))[0] > hp + 0.005

    def in_danger(self):
        """체력이 힐을 시작할 만큼 내려갔는지 (hp_low 아래)."""
        return (wind.read_bars() or (1.0, 1.0))[0] < AUTO["hp_low"]

    def check_dead(self):
        """체력이 0으로 여러 번 연달아 읽히면 죽은 것으로 보고 멈춘다."""
        hp = (wind.read_bars() or (1.0, 1.0))[0]
        self.dead_checks = self.dead_checks + 1 if hp < 0.006 else 0
        if self.dead_checks >= 8:
            raise Dead

    def rescue(self):
        self.check_dead()
        return self._rescue()

    def _rescue(self):
        """체력이 hp_low 아래면 다른 건 다 제쳐 두고 힐을 이어서 쓴다 (힐 사이에 첨은 나간다). heal_to까지.

        한 바퀴에 힐을 한 번만 쓰면 못 버틴다 (몹 2마리에게 맞으면서 체력이 4%까지 내려간 적이 있다).
        그래서 한 바퀴 안에서도 동작 사이사이에 불러서, 내려가면 바로 여러 번 쓴다.
        """
        hp = (wind.read_bars() or (1.0, 1.0))[0]
        if hp >= AUTO["hp_low"]:
            return False
        if hp < HUNT["danger_hp"]:
            print(f"  체력 {hp:.0%} → 힐부터", flush=True)
        for _ in range(25):
            if (wind.read_bars() or (1.0, 1.0))[0] >= HUNT["heal_to"]:
                break
            self.heal()
        if (wind.read_bars() or (1.0, 1.0))[0] < 0.006:
            # 힐을 25번 눌렀는데 체력이 0이다 = 죽었다. 여기서 안 잡으면 "힐이 안 먹는다 → 창을 다시 잡는다"만 되풀이해서
            # check_dead가 8번을 못 채우고 부활 절차로 못 넘어간다 (2026-10-11 13:34)
            raise Dead
        if (wind.read_bars() or (1.0, 1.0))[0] < HUNT["danger_hp"]:
            # 힐을 25번 눌렀는데도 체력이 그대로다 = 키가 게임에 안 들어가고 있다
            print("  힐이 안 먹는다 → 게임 창을 다시 잡는다", flush=True)
            wind.refocus()
        self.count["rescue"] += 1
        return True

    def upkeep(self):
        """체력/마력이 모자라면 하나만 채운다. 뭔가 했으면 True.

        체력이 적으면 죽을 수 있으니 힐이 가장 먼저다. 마력이 없으면 동동주를 마셔서라도 힐을 쓴다.
        그래도 힐이 안 들어가면(마력이 모자라면) 공력증강으로 마력을 채운다. 공력증강으로는 죽지 않는다.
        """
        hp, mp = wind.read_bars() or (1.0, 1.0)
        # 헬파이어를 쓰려면 체력이 hellfire_min_hp 이상이어야 하므로 그 아래면 힐부터 한다
        heal_below = max(AUTO["hp_low"], AUTO["hellfire_min_hp"] if KEYS["hellfire"] else 0)
        if hp < heal_below:
            self.healing = True
        elif hp >= AUTO["hp_ok"]:
            self.healing = False
        empty = mp < AUTO["potion_below"]
        # 공력증강은 마력을 가득 채워 주므로 마력이 거의 바닥났을 때만 쓰면 된다
        mp_floor = AUTO["mp_low"]
        if self.healing:
            self.heal()
        elif mp < mp_floor:
            if hp < AUTO["gongjeung_min_hp"] and not empty:
                self.heal()  # 공력증강은 체력을 쓴다. 체력이 모자라면 힐부터
            elif wind.refill(self.drained or empty):
                self.drained = False
                self.refill_fails = 0
            else:
                self.refill_fails += 1
        else:
            return False
        return True

    def buff(self):
        """보호와 무장을 주기마다 건다. 회복이나 몹 유무와 상관없이 먼저 챙긴다."""
        if AUTO["bomu_every"] <= 0 or time.monotonic() < self.bomu_at:
            return
        mp = (wind.read_bars() or (1.0, 1.0))[1]
        if mp < AUTO["mp_low"]:
            return  # 마력이 없으면 안 걸린다. 채운 뒤 다음 바퀴에 건다
        wind.bomu()
        self.bomu_at = time.monotonic() + AUTO["bomu_every"]
        self.count["bomu"] += 1

    def debuff(self):
        """저주와 중독을 화면의 몹들에게 건다. 마력이 있을 때(헬파이어 전에) 건다. 한 마리라도 걸었으면 True."""
        found = False
        now = time.monotonic()
        if (wind.read_bars() or (1.0, 1.0))[1] < AUTO["mp_low"]:
            return False  # 마력이 없으면 걸리지 않는다. 시각을 넘기지 않고 다음 바퀴에 다시 본다
        # 저주는 3분쯤 간다. 같은 몹에게 또 걸 필요가 없으니, 자리를 옮겨 새 몹을 만났을 때나
        # 한참 지났을 때만 다시 건다
        curse_due = now >= self.curse_at or self.walked >= HUNT["curse_after_steps"]
        for name, due in (("curse", curse_due), ("poison", now >= self.poison_at)):
            if not KEYS[name] or not due or KEYS[name] in HUNT.get("spam_keys", ()):
                continue  # spam_keys에 든 스킬(저주)은 spam()이 계속 누른다
            if self.rescue():
                break
            cast = wind.cast_each(KEYS[name], HUNT["targets"], stop=self.in_danger)
            if name == "curse" and cast:
                self.walked = 0
            self.count[name] += cast
            found |= cast > 0
            # 몹이 없었으면 주기를 채우지 않는다. 다음에 몹이 보이면 바로 건다
            wait = HUNT[f"{name}_every"] if cast else 2
            setattr(self, f"{name}_at", time.monotonic() + wait)
        return found

    def try_hellfire(self):
        """헬파이어를 쓸 때가 됐으면 체력/마력을 맞춘 뒤 쓴다.

        돌려주는 값: True 몹에게 썼다, False 화면에 고를 몹이 없다, None 쓸 때가 아니거나 준비가 안 됐다.
        """
        if not KEYS["hellfire"] or time.monotonic() < self.hellfire_at or self.in_danger():
            return None
        if self.refill_fails >= 3:
            # 헬파이어 뒤에 마력을 못 채우는 일이 이어졌다 (동동주가 떨어진 듯). 마력을 0으로 만들면
            # 힐도 못 쓰게 되므로 10분 동안 헬파이어를 쉬고 다시 해 본다
            print("  마력을 못 채운다 (동동주가 떨어진 듯). 헬파이어를 10분 쉰다", flush=True)
            self.hellfire_at = time.monotonic() + 600
            self.refill_fails = 0
            return None
        # 마력이 hellfire_min_mp 이상일 때만 쓴다. 헬파이어를 쓰려고 공력증강을 누르지는 않는다
        # (공력증강은 체력을 깎아서, 그렇게 채우다 위험해진 적이 있다)
        hp, mp = wind.read_bars() or (1.0, 1.0)
        if mp < AUTO["hellfire_min_mp"]:
            # 힐을 쓰다 보면 마력이 10~70% 사이에 걸려서 헬파이어도 공력증강도 안 나가는 상태가 된다.
            # 체력이 넉넉할 때만(hellfire_refill_hp 이상) 공력증강을 한 번 눌러 채우고 쓴다
            if hp < HUNT["hellfire_refill_hp"] or not wind.refill(mp < AUTO["potion_below"]):
                return None
            self.rescue()  # 공력증강으로 깎인 체력을 먼저 메우고 헬파이어를 쓴다
            mp = (wind.read_bars() or (1.0, 1.0))[1]
            if mp < AUTO["hellfire_min_mp"]:
                return None  # 메우느라 마력을 다시 많이 썼다. 이번 차례는 넘긴다
        if not wind.cast_at_monster(KEYS["hellfire"], AUTO["hellfire_target_hp"]):
            self.hellfire_at = time.monotonic() + AUTO["hellfire_retry"]
            return False
        wind.sleep(AUTO["cast_wait"])
        bars = wind.read_bars()
        if bars and bars[1] < AUTO["mp_low"]:  # 마력이 바닥났으면 나간 것
            self.hellfire_mana.append(round(mp, 2))  # 어느 마력에서 썼는지 (조절용 기록)
            self.drained = True
            self.hellfire_at = time.monotonic() + AUTO["hellfire_every"]
            self.count["hellfire"] += 1
        else:
            self.hellfire_at = time.monotonic() + AUTO["hellfire_retry"]
        return True

    def approach(self):
        """화면에서 가장 가까운 몹 옆 칸으로 걸어간다 (첨이 닿게). 몹이 있으면 True, 화면에 없으면 False.

        첨으로 붙어서 싸우는 게 더 빨리 잡는다. 너무 멀면(approach_max 칸 초과) 가지 않는다.
        """
        offsets = wind.locate_monsters(HUNT["targets"])
        if not offsets:
            return False
        dx, dy = min(offsets, key=lambda o: abs(o[0]) + abs(o[1]))
        distance = abs(dx) + abs(dy)
        if distance <= 1 or distance > HUNT["approach_max"] or not self.room:
            return True
        here = nav.position()
        monster = (here[0] + dx, here[1] + dy)
        width, height = self.sizes[self.room]
        exits = self.ports.get(self.room, {})
        beside = [(monster[0] + ax, monster[1] + ay) for ax, ay in wind.DELTA.values()]
        beside = [c for c in beside if 0 <= c[0] < width and 0 <= c[1] < height and c not in exits]
        if not beside:
            return True
        goal = min(beside, key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
        try:
            nav.go(self.room, goal, self.ports, self.sizes, max_steps=distance + 4, near=-1, quiet=True)
        except RuntimeError:
            pass  # 길이 막혔거나 몹이 움직였다. 지금 자리에서 싸운다
        self.count["approach"] += 1
        return True

    def swing(self):
        """기본 공격 키를 다시 눌러 누른 채로 둔다. 스킬과 동시에 들어가므로 스킬 사이사이에 부른다.

        게임이 "누르고 있는 동안"을 보는지 "누르는 순간"을 보는지 몰라서, 뗐다가 다시 눌러 둘 다 되게 한다.
        입력창이 열려 있으면 누르지 않는다 (글자로 들어간다).
        """
        if not KEYS.get("basic") or wind.game_window() is None or wind.prompt_open():
            return
        code = wind.KEYCODES[KEYS["basic"]]
        wind._post(code, False)
        time.sleep(0.01)
        wind._post(code, True)
        self.swinging = True

    def spam(self):
        """spam_keys(첨, 힐, 첨, 저주)를 기본 공격을 누른 채로 쉬지 않고 돌려 누른다.

        이 스킬들은 대상 선택창 없이 키만 누르면 나가고 쿨이 거의 없으며 동시에 들어간다 (2026-10-10 확인:
        0.15초 간격으로 눌러도 누를 때마다 메시지가 찍히고 마력이 준다). 사람이 1, 2, 3, 4, 스페이스를
        계속 누르고 있는 것과 같다. 마력이 mp_low 아래로 내려가면 멈추고 돌아가서 공력증강을 쓰게 한다.
        """
        keys = HUNT.get("spam_keys")
        if not keys:
            return
        # 대상이 자신에게 고정돼 있어야 힐이 나에게, 저주가 주위 몹에게 선택창 없이 나간다
        if time.monotonic() >= self.lock_at:
            if not wind.lock_self():
                print("  대상 고정(Tab 두 번)이 안 됐다", flush=True)
            self.lock_at = time.monotonic() + 10
        for _ in range(HUNT["spam_rounds"]):
            if wind.prompt_open():
                wind.tap("esc")  # 입력창이 열려 있으면 숫자가 글자로 들어간다
            self.swing()
            for key in keys:
                wind.tap(key)
                time.sleep(HUNT["spam_gap"])
            hp, mp = wind.read_bars() or (1.0, 1.0)
            if mp < AUTO["mp_low"] or hp < HUNT["danger_hp"]:
                break
        self.count["spam"] += 1

    def release(self):
        """기본 공격 키를 뗀다. 싸움이 끝나면 꼭 부른다 (누른 채로 걸으면 안 된다)."""
        if self.swinging:
            wind._post(wind.KEYCODES[KEYS["basic"]], False)
            self.swinging = False

    def melee(self):
        """옆 칸(상하좌우)에 붙은 몹 쪽으로 돌아서서 기본 공격을 건다. 몹이 붙어 있으면 True.

        기본 공격은 바라보는 방향의 옆 칸만 친다. 방향키를 누르면 그쪽을 보게 되고 자리는 안 바뀐다.
        """
        if not KEYS.get("basic"):
            return False
        turn = {offset: name for name, offset in wind.DELTA.items()}
        beside = [o for o in self.monsters() if o in turn]
        if not beside:
            self.release()
            return False
        # 방향은 매번 다시 잡는다. 기억해 둔 방향을 믿으면, 그 사이 다른 입력으로 돌아서 있을 때 허공을 친다
        self.release()
        wind.tap(turn[beside[0]])
        self.facing = turn[beside[0]]
        self.swing()
        self.count["basic"] += 1
        if DEBUG_DIR and self.count["basic"] <= 6:
            time.sleep(0.15)
            shot = wind.grab(0, 0, 1920, 1050)
            if shot:
                Path(DEBUG_DIR, f"melee{self.count['basic']}.raw").write_bytes(shot[0])
                me = wind.box_tile(wind.last_boxes[0]) if wind.last_boxes and wind.last_boxes[0] else None
                print(f"  [확인] 내 칸 {me} 상자 {wind.last_boxes[0] if wind.last_boxes else None} 몹 {self.last_seen} → {turn[beside[0]]}", flush=True)
        return True

    def act(self):
        """한 바퀴. 몹을 건드렸으면 True, 스킬이 닿는 몹이 없으면 다른 건 하지 않고 바로 False.

        1. 닿는 몹이 있는지부터 본다: 첨이 나가는지, 안 나가면 화면에 몹이 있는지.
           화면에 있는데 첨이 안 닿으면 그 몹 옆으로 걸어가서 첨을 쓴다.
           (체력이 위험할 때만 그 전에 회복한다.)
        2. 몹이 있으면: 헬파이어(쿨이 돌았으면 가장 먼저) → 회복 → 저주/중독.
        첨은 매 바퀴 쓴다. 저주/중독은 주기가 되면 마력이 있을 때 건다.
        """
        self.rescue()
        self.buff()
        hp = (wind.read_bars() or (1.0, 1.0))[0]
        if hp < AUTO["hp_low"]:
            self.upkeep()
        if wind.attack():
            self.count["attack"] += 1
        elif HUNT["approach_max"] <= 0:
            # 첨이 안 닿았다. 가까이 따라온 몹이 있으면 붙을 때까지 제자리에서 원거리로 때리며 기다린다.
            # 가까이에 없으면 쫓아가지 않고 다음 목적지로 걷는다
            if not self.near():
                return False
            if KEYS["ranged"] and wind.cast_at_monster(KEYS["ranged"]):
                self.count["ranged"] += 1
        elif not self.approach():
            return False
        elif wind.attack():  # 몹 옆으로 걸어갔으니 첨이 닿는다
            self.count["attack"] += 1
        elif KEYS["ranged"] and wind.cast_at_monster(KEYS["ranged"]):
            self.count["ranged"] += 1  # 아직 안 닿으면 원거리로 때린다
        self.melee()
        self.rescue()
        self.try_hellfire()
        self.swing()
        self.spam()
        self.rescue()
        self.upkeep()
        self.rescue()  # 공력증강은 지금 체력의 60~70%를 깎는다. 누른 직후에 바로 힐로 메운다
        self.swing()
        self.debuff()
        self.swing()
        return True

    def probe(self):
        """첨 둘을 눌러서 닿는 몹이 있는지 본다. 0.35초쯤 걸린다.

        첨은 닿아야 나가고, 나가면 하나에 마력이 2.2%쯤 준다. 둘을 눌러 마력이 3% 넘게 줄었으면 닿은 것이다.
        메시지 창은 안 본다: 계속 누르는 중에는 늦게 찍히는 힐 메시지 때문에 몹이 없어도 바뀌고,
        같은 첨 메시지가 이어지면 몹이 있어도 안 바뀐다. 힐 하나(1.1%)가 늦게 나가도 3%는 안 넘는다.
        """
        time.sleep(0.12)  # 앞서 누른 힐/저주가 다 나가기를 기다린다
        mp = (wind.read_bars() or (1.0, 1.0))[1]
        if mp < 0.06:
            return True  # 마력이 없어서 첨이 안 나간다. 몹이 없다고 보지 않는다
        wind.press(KEYS["attack1"])
        time.sleep(0.03)
        wind.press(KEYS["attack2"])
        time.sleep(0.18)
        return mp - (wind.read_bars() or (1.0, 1.0))[1] > 0.03

    def fill(self, mp):
        """공력증강으로 마력을 채운다 (바닥이면 동동주 한 잔 먼저). 체력은 보지 않는다: 고정 중에는 힐이 계속 나간다."""
        if mp < AUTO["potion_below"]:
            wind.drink()  # 공력증강에 마력 30이 든다
        wind.press(KEYS["gongjeung"])
        end = time.monotonic() + AUTO["gongjeung_wait"]
        while time.monotonic() < end:
            if (wind.read_bars() or (1.0, 1.0))[1] >= HUNT["fast_mp_low"]:
                self.refill_fails = 0
                return True
            time.sleep(0.03)
        self.refill_fails += 1
        return False

    def fight_fast(self):
        """대상을 자신에게 고정하고 spam_keys와 기본 공격을 쉬지 않고 누른다.

        돌려주는 값: True 싸웠다, False 닿는 몹이 없다, None 고정이 안 걸려서 못 했다(예전 방식으로 싸울 것).

        고정(Esc → Tab → Tab)돼 있으면 선택창이 안 뜬다: 힐은 나에게, 첨/저주는 주위 몹에게 바로 나간다.
        한 바퀴는 키 4개와 체력/마력 한 번 읽기뿐이다.
        - 헬파이어는 고정한 채로는 자신에게 나가서 안 걸린다. 쿨마다 고정을 풀고 선택창에서 몹을 골라 쓴 뒤
          곧바로 다시 고정한다. 선택창을 여는 김에 붙은 몹의 방향을 재서 그쪽으로 돌아선다 (기본 공격이 맞게).
        - 공력증강은 체력을 안 보고 쓴다: 마력이 fast_mp_low 아래일 때, 헬파이어 차례에 마력이 모자랄 때, 헬파이어 직후.
        - probe_every초마다 첨이 닿는지 보고, clear_checks번 연달아 안 닿으면 끝낸다. 끝나면 Esc로 고정을 푼다
          (풀어야 걷는 동안 선택창으로 몹 수를 셀 수 있다).
        """
        keys = HUNT["spam_keys"]
        turn = {offset: name for name, offset in wind.DELTA.items()}
        locked, broken, fought, clear, scan_at, blind = False, False, False, 0, 0.0, 0
        wind.scan_me = None
        early_at = 0.0  # 쿨이 끝났을 때 scan_gap보다 일찍 선택창을 열어도 되는 시각
        look_at = 0.0  # 앞 칸을 살펴볼 시각. 선택창을 여는 시각(scan_at)과 따로 간다
        front = home = None  # 내가 보고 있는 붙은 몹의 방향과 내 칸. 쿨 중에는 선택창 대신 그 칸만 살펴본다
        exits = set(self.ports.get(self.room, {})) if self.room else set()
        looks = []
        began, spam0, hell0, scans = time.monotonic(), self.count["spam"], self.count["hellfire"], []
        try:
            while True:
                self.check_dead()
                hp, mp = wind.read_bars() or (1.0, 1.0)
                now = time.monotonic()
                if (front and now >= look_at and locked and KEYS.get("look") and hp >= HUNT["fast_hellfire_hp"]
                        and wind.cooling()):
                    # 헬파이어 쿨이 도는 동안은 선택창(1.2~2초, 고정이 풀려 힐이 끊긴다)을 열지 않고 앞 칸만 살펴본다 (0.3초).
                    # 몹이 그대로면 계속 싸우고, 죽어서 아이템이 떨어졌으면 쿨이 도는 김에 바로 밟고 주운 뒤 제자리로 온다.
                    # 앞 칸이 비었을 때만 선택창으로 다른 몹을 찾는다.
                    self.release()
                    seen = self.peek(home, front, "facing")
                    looks.append(seen)
                    print(f"   {time.strftime('%H:%M:%S')} 앞 칸({front}) 보기: {seen}", flush=True)
                    if seen in ("mob", "under"):
                        look_at = time.monotonic() + HUNT["look_gap"]
                        scan_at = max(scan_at, look_at)  # 앞에 몹이 있는 것을 알았으니 선택창은 미룬다 (쿨이 끝나면 연다)
                        continue
                    if seen == "got":
                        image, here = wind.snapshot("map_name"), nav.read_position()
                        for _ in range(3):  # 처음 누르면 돌기만 한다
                            if here in (home, None):
                                break
                            here = nav.try_step(wind.OPPOSITE[front], here, image)
                        if here != home:
                            wind.scan_me = None  # 제자리로 못 돌아왔다. 내 칸을 다시 읽는다
                    front = None
                    now = scan_at = time.monotonic()  # 앞 칸이 비었다. 바로 선택창으로 다른 몹을 찾는다
                # 쿨이 끝났고 앞에 몹이 있으면 scan_gap을 다 기다리지 않고 선택창을 열어 쓴다. 다만 직전 선택창에서
                # look_gap은 지나야 한다: 이 틈이 없으면 못 썼을 때 선택창만 쉬지 않고 열어서 힐도 공격도 안 나간다
                # (2026-10-11 13:30, 몹이 길을 막고 있는데 싸우는 키가 안 눌렸다)
                if now >= scan_at and hp < HUNT["fast_hellfire_hp"] and locked and fought:
                    # 체력이 낮을 때는 선택창을 열지 않는다 (여는 1~2초 동안 힐이 끊긴다). 맞고 있으니 몹은 있는 것이다.
                    # 체력 50% 아래에서 몹 확인용 선택창을 4초마다 열다가 죽었다 (2026-10-11 18:36, 몹 4마리)
                    scan_at = now + 1.0
                if now >= scan_at or (front and now >= early_at and not wind.cooling() and now >= self.hellfire_at
                                      and hp >= HUNT["fast_hellfire_hp"]):
                    # 고정을 풀고 선택창으로 몹을 본다: 붙은 몹이 남았는지, 어느 쪽인지. 헬파이어 차례면 그 몹에게 쓴다.
                    # (첨을 눌러 마력이 주는지로 몹이 있는지 보려 했는데, 몹에 둘러싸여서도 안 준다고 나와서 버렸다.)
                    # 푸는 1초쯤 힐이 끊기므로 헬파이어는 체력이 넉넉할 때만 쓴다
                    use = bool(KEYS["hellfire"]) and now >= self.hellfire_at and hp >= HUNT["fast_hellfire_hp"] and self.refill_fails < 5
                    use = use and not wind.cooling()  # 쿨 글자가 떠 있으면 눌러도 선택창이 안 뜬다
                    if use and mp < AUTO["hellfire_min_mp"]:
                        self.fill(mp)
                        time.sleep(0.1)
                        mp = (wind.read_bars() or (1.0, 1.0))[1]
                        use = mp >= AUTO["hellfire_min_mp"]
                    self.release()
                    # 헬파이어는 쿨이 도는 동안 눌러도 선택창이 안 뜬다 (몹이 있는데 "없다"로 읽혀 싸움이 끝났다).
                    # 헬파이어를 쓸 차례가 아니면 쿨이 없는 저주 키로 선택창을 열어 보기만 한다
                    print(f"   {time.strftime('%H:%M:%S')} 선택창 연다 (헬파이어 차례={use})", flush=True)
                    cast, offsets = wind.hellfire_scan(KEYS["hellfire"] if use else KEYS["curse"], HUNT["targets"], use)
                    early_at = time.monotonic() + HUNT["look_gap"]  # 어느 갈래로 나가든 다음 선택창까지 틈을 둔다
                    for note in wind.last_boxes:
                        if isinstance(note, str):
                            print(f"   {time.strftime('%H:%M:%S')} 헬파이어: {note}", flush=True)
                    fired = False
                    for _ in range(12 if cast else 0):  # 나갔으면 왼쪽 위에 쿨 글자가 뜬다 (0.2초로는 모자랐다. 0.6초까지 본다)
                        fired = wind.cooling()
                        if fired:
                            break
                        time.sleep(0.05)
                    if cast and not fired and self.misfire_shots < 6:
                        # 몹을 골라 Enter를 눌렀는데 쿨 글자가 안 떴다. 왜 그런지 보려고 화면을 남긴다 (메시지 창에 이유가 찍힌다)
                        self.misfire_shots += 1
                        print(f"  헬파이어가 안 나갔다. 화면 {save_status('misfire')}", flush=True)
                    locked = wind.relock()
                    scans.append((round(time.monotonic() - now, 1), offsets, f"쓸차례={use} 썼다={cast} 쿨글자={fired} 체력{hp:.0%} 마력{mp:.0%}→{(wind.read_bars() or (1.0, 1.0))[1]:.0%} 쿨{self.hellfire_at - now:.0f}"))
                    if not offsets:
                        scans.append(list(wind.last_boxes))
                    if cast:
                        left = (wind.read_bars() or (1.0, 1.0))[1]
                        # 나갔는지는 쿨 글자로 안다. 몹을 죽이면 마력이 남고 못 죽이면 다 쓴다 (사용자 정보)라서
                        # 마력이 줄었는지만 보면 죽인 경우를 "안 나갔다"로 센다. 마력 기준은 글자를 못 읽었을 때를 위해 남겨 둔다
                        if fired or wind.cooling() or left < mp - 0.4:
                            self.hellfire_mana.append(round(mp, 2))
                            self.hellfire_at = now + AUTO["hellfire_every"]
                            self.count["hellfire"] += 1
                            if left < AUTO["hellfire_min_mp"]:
                                self.fill(left)  # 바닥난 마력을 바로 채운다
                    if not offsets and wind.last_boxes == ["선택창이 안 떴다"] and locked and blind < 3:
                        # 선택창이 안 떠서 몹을 못 본 것이지 몹이 없는 게 아니다. 이걸 "몹 없음"으로 보고 체력 54%에서
                        # 싸움을 끝낸 뒤 주우러 다니다 죽었다 (2026-10-10 19:43). 고정한 채 계속 싸우고 곧 다시 본다
                        blind += 1
                        scan_at = time.monotonic() + 1.0
                        continue
                    blind = 0
                    if cast and fired and not offsets:
                        # 헬파이어는 나갔는데 몹 위치는 못 쟀다 (내 상자가 안 읽혔다). 몹이 있는 것이니 계속 싸우고 곧 다시 본다
                        fought, clear = True, 0
                        scan_at = time.monotonic() + HUNT["look_gap"]
                        continue
                    beside = [o for o in offsets if o in turn]
                    spot = nav.read_position() if offsets else None
                    if self.suspect and spot:
                        cell, line = self.suspect
                        self.suspect = None
                        if (cell[0] - spot[0], cell[1] - spot[1]) in offsets and line not in BLOCKERS:
                            # 못 들어간 그 칸에 선택창으로도 몹이 보인다 → 그 이름은 몹이다. 다음부터는 안 밟아 본다
                            BLOCKERS.add(line)
                            with BLOCKER_FILE.open("a") as file:
                                file.write(line.hex() + "\n")
                            print(f"  살펴보기: 몹 이름을 하나 외웠다 (모두 {len(BLOCKERS)}개)", flush=True)
                    front = home = None
                    if beside and spot and (spot[0] + beside[-1][0], spot[1] + beside[-1][1]) not in exits:
                        front, home = turn[beside[-1]], spot
                    if spot:
                        # 몹은 죽은 칸에 아이템을 떨어뜨린다. 옆 칸뿐 아니라 떨어져 있던 몹도 첨·헬파이어에 죽으므로
                        # 선택창에서 본 몹 칸을 다 적어 두고, 싸움이 끝나면 밟고 줍는다
                        self.drops.update((spot[0] + dx, spot[1] + dy) for dx, dy in offsets if max(abs(dx), abs(dy)) <= 4)
                    if beside:
                        wind.press(turn[beside[-1]])  # 붙은 몹 쪽을 본다 (몹이 있는 칸으로는 걸어가지지 않는다)
                        self.count["basic"] += 1
                        fought, clear = True, 0
                    else:
                        clear += 1
                        close = any(max(abs(dx), abs(dy)) <= HUNT["near"] for dx, dy in offsets)
                        if not close or clear >= HUNT["clear_checks"]:
                            break  # 붙은 몹이 없다. 가까이 오는 몹이 있으면 한 번 더 기다려 준다
                    if not locked:
                        broken = True
                        break
                    # 헬파이어가 나갔으면 그 몹은 곧 죽는다. 금방 앞 칸을 살펴봐서 줍고 다음 몹으로 넘어간다
                    scan_at = time.monotonic() + HUNT["scan_gap"]
                    early_at = time.monotonic() + HUNT["look_gap"]
                    look_at = time.monotonic() + (0.6 if fired else HUNT["look_gap"])
                    continue
                if mp < HUNT["fast_mp_low"]:
                    self.fill(mp)
                    if self.refill_fails >= 20:
                        print("  마력을 못 채운다 (동동주가 떨어진 듯). 싸움을 끝낸다", flush=True)
                        self.refill_fails = 0
                        break
                    continue
                self.swing()
                for key in keys:
                    wind.press(key)
                    time.sleep(HUNT["spam_gap"])
                self.count["spam"] += 1
                if wind.prompt_open():
                    locked = wind.relock()  # 선택창이 떴다. 고정이 풀린 것
                    if not locked:
                        broken = True
                        break
                    continue
                self.buff()
            # 고정이 걸려 있는 동안 체력을 채우고 끝낸다 (풀고 나면 힐이 느리다)
            for _ in range(60):
                hp, mp = wind.read_bars() or (1.0, 1.0)
                if not locked or hp >= HUNT["heal_to"] or mp < AUTO["potion_below"]:
                    break
                wind.press(KEYS["heal"])
                time.sleep(0.05)
        finally:
            self.release()
        if wind.game_window() is not None:
            wind.press("esc")  # 고정을 푼다
            time.sleep(0.05)
        self.last_hp = (wind.read_bars() or (1.0, 1.0))[0]
        if fought:
            hp, mp = wind.read_bars() or (1.0, 1.0)
            print(f"  빠른 싸움 {time.monotonic() - began:.1f}초: 누르기 {self.count['spam'] - spam0}바퀴, 헬파이어 {self.count['hellfire'] - hell0}, "
                  f"체력 {hp:.0%} 마력 {mp:.0%}, 앞 칸 보기 {looks}, 살펴보기 {scans}", flush=True)
        if broken:
            print("  대상 고정이 안 걸린다 → 예전 방식으로 싸운다", flush=True)
            return None
        return fought

    def peek(self, home, name, sure):
        """home에 서서 name 쪽 옆 칸을 살펴보고, 아이템이 있으면 밟고 줍는다.

        돌려주는 값: "empty" 빈 칸, "mob" 몹(막는 것)만 있다, "got" 밟고 주웠다(그 칸에 서 있다),
        "under" 아이템이 있는데 몹이 서 있어서 못 들어갔다, "block?" 모르는 이름 한 줄인데 못 들어갔다(몹일 것),
        "lost" 좌표가 안 읽힌다.
        sure: "facing" 이미 그쪽을 보고 있다(방향키를 안 누른다), True 그쪽을 안 보고 있는 것이 확실하다(방향키가 돌기만 한다),
        False 모른다(방향키를 누르면 돌 수도, 한 칸 걸을 수도 있다).
        """
        if sure != "facing":
            nav.last_tap = time.monotonic()
            wind.tap(name)
            time.sleep(0.05 if sure else 0.18)
            now = nav.read_position()
            if now is None:
                return "lost"
            if now != home:
                self.grab_here()
                return "got"
        # 싸우는 중에는 "태양의기원을 외웠습니다" 같은 주문 메시지가 뒤늦게 찍힌다. 메시지 창이 가만히 있을 때까지 기다리고,
        # 그동안 찍힌 줄은 살펴보기 결과가 아니므로 외워 뒀다가 뺀다
        before = look_lines()
        for _ in range(6):
            time.sleep(0.04)
            again = look_lines()
            if again == before:
                break
            # 몇 줄이 새로 찍혔는지 분명할 때만 외운다 (창이 통째로 바뀌었으면 몹 이름까지 잡음으로 외우게 된다)
            if any(again[:-count] == before[count:] for count in (1, 2)):
                NOISE.update(line for line in new_lines(before, again) if line not in BLOCKERS)
            before = again
        wind.tap(KEYS["look"])
        lines = []
        for _ in range(5):
            time.sleep(0.04)
            lines = [line for line in new_lines(before, look_lines()) if line not in NOISE]
            if lines:
                break
        if not lines:
            return "empty"
        time.sleep(0.06)  # 두 줄이 찍힐 때 나머지 줄까지 기다린다
        lines = [line for line in new_lines(before, look_lines()) if line not in NOISE]
        if all(line in BLOCKERS for line in lines):
            return "mob"
        image = wind.snapshot("map_name")
        for _ in range(2):  # 걸음을 너무 빨리 누르면 게임이 버린다. 한 번 더 눌러 보고 판단한다
            now = nav.try_step(name, home, image)
            if now != home:
                self.grab_here()
                return "got"
        if len(lines) == 1:
            # 한 줄만 찍혔는데 못 들어간다 → 아이템이 아니라 몹 이름일 것이다. 여기서 바로 외우면 걸음이 씹혔을 때
            # 아이템 이름을 몹으로 외워 버린다. 선택창에서 그 칸에 몹이 보일 때 외운다 (fight_fast)
            self.suspect = ((home[0] + wind.DELTA[name][0], home[1] + wind.DELTA[name][1]), lines[0])
            return "block?"
        return "under"

    def grab_here(self):
        """선 칸의 아이템을 줍는다. 주우면 메시지 창에 "호박 30개" 같은 줄이 찍힌다. 그걸로 실제로 주운 횟수를 센다."""
        before = look_lines()
        wind.tap(KEYS["pickup"])
        self.count["pickup"] = self.count.get("pickup", 0) + 1
        for _ in range(4):
            time.sleep(0.04)
            if new_lines(before, look_lines()):
                self.count["items"] = self.count.get("items", 0) + 1
                break

    def collect(self, depth=0):
        """싸움이 끝난 자리에서 아이템을 줍는다 (줍기 키는 내가 선 칸의 아이템만 줍는다).

        살펴보기 키(;)를 누르면 바라보는 앞 칸에 있는 몹과 아이템의 이름이 메시지 창에 한 줄씩 찍히고,
        빈 칸이면 아무것도 안 찍힌다 (2026-10-11 확인, 0.3초). 그래서 몹이 있던 칸을 다 밟지 않고 (9할이 빈 칸이었다)
        옆에서 살펴봐서 아이템이 있는 칸만 밟는다. 몹 이름만 찍힌 칸은 안 간다 (몹이 선 칸으로는 못 들어간다).
        아이템 위에 몹이 서 있으면 그 몹을 잡고 다시 줍는다.
        """
        cells, self.drops = sorted(self.drops), set()
        key, look = KEYS.get("pickup"), KEYS.get("look")
        if not key or not look or not self.room:
            return
        if (wind.read_bars() or (1.0, 1.0))[0] < HUNT["heal_to"]:
            return  # 체력이 덜 찬 채로는 주우러 다니지 않는다
        exits = set(self.ports.get(self.room, {}))
        width, height = self.sizes.get(self.room, (999, 999))
        began = time.monotonic()
        until = began + HUNT.get("pickup_seconds", 8)  # 줍는 데 9칸에 55초가 걸린 적이 있다. 오래 끌지 않는다
        tally = {"empty": 0, "mob": 0, "got": 0, "under": 0, "block?": 0}
        # 줍기는 wind.tap으로 누른다. 짧게 누르는 chord는 Shift가 남아 다른 키가 잘못 먹었다 (장안성비서가 써져 장안성으로 날아갔다)
        home = nav.read_position()
        if home is None:
            return
        # 볼 칸: 싸우던 자리의 상하좌우 네 칸. 싸우는 동안은 자리를 안 옮기고 몹은 붙어서 죽으므로 거기에 떨어진다.
        # pickup_far를 켜면 싸우는 동안 몹이 있던 떨어진 칸도 옆까지 걸어가서 본다 (빈 칸 7개에 8.7초가 걸려서 꺼 둔다)
        todo = [(home[0] + dx, home[1] + dy) for dx, dy in wind.DELTA.values()]
        if HUNT.get("pickup_far"):
            todo += [c for c in cells if c not in todo and c != home]
        todo = [c for c in todo if c not in exits and 0 <= c[0] < width and 0 <= c[1] < height]
        here, facing, under = home, None, None
        todo = sorted(todo, key=lambda c: abs(c[0] - home[0]) + abs(c[1] - home[1]))[:14]
        while todo and time.monotonic() < until:
            if (wind.read_bars() or (1.0, 1.0))[0] < HUNT["gather_hp"]:
                break  # 맞고 있다. 그만 줍고 싸우러 간다
            cell = min(todo, key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
            todo.remove(cell)
            if abs(cell[0] - here[0]) + abs(cell[1] - here[1]) != 1:
                # 떨어진 칸: 그 옆 칸까지 걸어가서 살펴본다
                sides = [(cell[0] - dx, cell[1] - dy) for dx, dy in wind.DELTA.values()]
                sides = [c for c in sides if c not in exits and 0 <= c[0] < width and 0 <= c[1] < height]
                if not sides:
                    continue
                side = min(sides, key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
                try:
                    nav.go(self.room, side, self.ports, self.sizes, max_steps=8, quiet=True)
                except RuntimeError:
                    pass
                here, facing = nav.read_position(), None
                if here is None:
                    return
                if here == cell:
                    self.grab_here()  # 가다가 그 칸을 밟았다
                    continue
                if abs(cell[0] - here[0]) + abs(cell[1] - here[1]) != 1:
                    continue  # 옆까지 못 갔다
            name = next(n for n, d in wind.DELTA.items() if (here[0] + d[0], here[1] + d[1]) == cell)
            result = self.peek(here, name, facing is not None and facing != name)
            if result == "lost":
                return
            tally[result] += 1
            facing = name
            if result == "got":
                here = cell
                facing = None  # 걸어 들어갔다. 다음 방향키가 돌기일지 걷기일지 모른다
            elif result == "under":
                under = cell
                break
        print(f"  줍기 {time.monotonic() - began:.1f}초: 밟음 {tally['got']}, 빈 칸 {tally['empty']}, 몹 {tally['mob'] + tally['block?']}, "
              f"몹 밑 아이템 {tally['under']}, 못 본 칸 {len(todo)}", flush=True)
        if under and depth < 2:
            # 아이템 위에 몹이 서 있다. 그 몹을 잡고 나서 다시 줍는다
            self.drops.update(todo + [under])
            if self.fight_fast():
                self.collect(depth + 1)

    def fight(self):
        """붙은 몹이 없어질 때까지 싸운다. 한 번이라도 건드렸으면 True."""
        if HUNT.get("spam_keys"):
            result = self.fight_fast()
            if result:
                self.collect()
            if result is not None:
                return result
        fought, clear = False, 0
        self.facing = None  # 걸어오면서 바라보는 방향이 바뀌었다
        try:
            while clear < HUNT["clear_checks"]:
                if self.act():
                    fought, clear = True, 0
                else:
                    clear += 1
                    if not fought:
                        break  # 처음부터 아무것도 없었다. 한 번만 보고 걷는다
        finally:
            self.release()
        self.last_hp = (wind.read_bars() or (1.0, 1.0))[0]
        return fought

    def monsters(self):
        """화면의 몹들이 나로부터 몇 칸 떨어져 있는지 (dx, dy) 목록."""
        # 내 위치는 Home으로 건 내 상자로 잰다. 좌표와 맵 크기로 계산해 봤더니 틀렸다
        # (9번 방에서 계산은 (15, 7)칸, 실제는 (12, 10)칸이었다. 자료의 맵 크기가 게임과 다른 것 같다).
        # 기본 공격 중에는 내 상자가 넓어지므로 키를 떼고 잰다
        self.release()
        self.last_seen = wind.locate_monsters(HUNT["targets"])
        return self.last_seen

    def near(self):
        """나로부터 near칸 안(대각선 포함)에 있는 몹 수. 걷는 동안 따라오는 몹은 한두 칸 뒤에 있다."""
        offsets = self.monsters()
        return sum(1 for dx, dy in offsets if max(abs(dx), abs(dy)) <= HUNT["near"])

    def before_step(self):
        """걸음마다 불린다. 싸울 때인지 본다.

        웬만하면 싸우지 않고 계속 걷는다. 몹이 near칸 안에 adjacent마리 이상 따라왔을 때 멈춰서 싸운다
        (멈추면 몹이 붙고, 첨이 한 번에 여러 마리를 때린다). 예외: 체력이 gather_hp 아래로 내려가면 바로 싸운다.
        길이 몹에 막혔을 때는 is_monster()가 따로 싸운다.
        """
        self.steps += 1
        self.walked += 1
        self.rescue()
        self.buff()
        hurt = (wind.read_bars() or (1.0, 1.0))[0] < HUNT["gather_hp"]
        for _ in range(12):  # 체력이 낮은 채로 걸어 들어가지 않는다. gather_hp 위로 채우고 간다 (힐 사이에 첨도 나간다)
            if (wind.read_bars() or (1.0, 1.0))[0] >= HUNT["gather_hp"]:
                break
            self.heal()
        self.last_hp = (wind.read_bars() or (1.0, 1.0))[0]
        if not hurt:
            if self.steps < HUNT["scan_every"]:
                return
            self.steps = 0
            beside = self.near()
            if beside or len(self.last_seen) >= HUNT["adjacent"]:
                print(f"   {time.strftime('%H:%M:%S')} 걷는 중 몹 {self.last_seen} → {HUNT['near']}칸 안 {beside}마리", flush=True)
            if beside < HUNT["adjacent"]:
                return
            print(f"  몹 {beside}마리가 가까이 왔다 → 멈춰서 싸운다")
        self.steps = 0
        if self.fight():
            print(f"  사냥 {self.count}")

    def is_monster(self):
        """길이 막혔을 때: 첨이 나가면 몹이 막고 있는 것이다."""
        if wind.attack():
            self.count["attack"] += 1
            self.fight()
            return True
        return False


def leave(name, cell, ports, sizes, fighter):
    """name 맵에서 cell(자료의 출구 칸)을 밟아 나간다. 자료가 한두 칸 틀릴 수 있어 주변도 밟아 본다."""
    width, height = sizes[name]
    around = sorted(
        ((cell[0] + dx, cell[1] + dy) for dx in range(-2, 3) for dy in range(-2, 3)),
        key=lambda c: abs(c[0] - cell[0]) + abs(c[1] - cell[1]),
    )
    for goal in around:
        if not (0 <= goal[0] < width and 0 <= goal[1] < height):
            continue
        try:
            result = nav.go(name, goal, ports, sizes, before_step=fighter.before_step, is_monster=fighter.is_monster)
        except RuntimeError as error:
            if "길이 없다" not in str(error):
                raise
            continue
        if result == "left":
            return nav.last_exit
    raise RuntimeError(f"{name}에서 {cell} 주변을 다 밟아도 맵이 안 바뀌었다")


def remember_exit(name, cell, destination, ports):
    """자료와 다른 칸에서 나갔으면 data/ports_fixed.tsv 에 적어 둔다."""
    if ports.get(name, {}).get(cell) == destination:
        return
    path = Path(__file__).parent / "data" / "ports_fixed.tsv"
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{name}\t{cell[0]}\t{cell[1]}\t{destination}\n")
    print(f"  출구 기록: {name} {cell} → {destination}")


LAST_ROOM = 10  # 방은 10번까지 있다 (10번에서 성으로 나간다)
active = None  # 지금 돌고 있는 Fighter
current_room = None  # 지금 있는 방. 멈췄다가 이어 할 때 쓴다


def wait_for_game():
    """게임 창이 맨 앞에 올 때까지 기다린다."""
    while wind.game_window() is None:
        time.sleep(0.3)
    time.sleep(0.5)
    if wind.prompt_open():
        wind.tap("esc")


HAUNT = re.compile(r"((?:제\d+)?(.+)흉가)(\d+)")  # 흉가 방 이름 (예: 제2상곡흉가3)
haunt = None  # 흉가를 돌 때 그 묶음 이름 (예: "제2상곡흉가"). None이면 비밀세작의집을 돈다
GROUPS = 4  # 한 성의 비밀세작의집은 묶음이 4개다 (그냥, 제2, 제3, 제4)
ENTRANCE_DOOR = (87, 142)  # 성에서 비밀세작의집입구로 들어가는 칸 (성 11곳 공통)


LOGS = Path(__file__).parent / "logs"


def save_status(name=None):
    """화면 오른쪽 아래 상태창(체력, 마력, 경험치, 돈)을 logs/에 그림으로 저장하고 파일 이름을 돌려준다."""
    from PIL import Image
    LOGS.mkdir(exist_ok=True)
    shot = wind.grab(1380, 800, 400, 200) if name is None else wind.grab(0, 0, 1920, 1050)
    if shot is None:
        return None
    data, row_bytes, scale = shot
    width, height = (400, 200) if name is None else (1920, 1050)
    image = Image.frombuffer("RGBA", (int(width * scale), int(height * scale)), data, "raw", "BGRA", row_bytes, 1)
    path = LOGS / f"{name or 'status'}-{time.strftime('%m%d-%H%M%S')}.png"
    image.convert("RGB").save(path)
    return path.name


def activate_game():
    """게임 창을 맨 앞으로 가져온다 (밤새 돌릴 때, 다른 창이 앞에 와서 멈춰 있지 않게)."""
    from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.localizedName() == wind.APP_NAME:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


def hold(fighter, seconds):
    """길을 잃었을 때: 걷지 않고 제자리에서 싸우고 회복만 한다."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        fighter.rescue()
        fighter.fight()
        time.sleep(0.5)


TITLES = Path(__file__).parent / "data" / "titles"  # 맵 이름 그림. 지금 어느 맵인지 확인하는 데 쓴다


def check_map(here):
    """화면의 맵 이름 그림으로 지금 맵이 here가 맞는지 확인한다. 맞는 이름을 돌려준다.

    처음 보는 맵이면 그림을 here라는 이름으로 저장해 둔다. 저장해 둔 그림과 다르면 다른 맵에 있는 것이므로
    저장된 그림 중에서 지금 화면과 같은 것을 찾아 그 이름으로 바꾼다 (다른 방 길로 걷는 일을 막는다).
    """
    TITLES.mkdir(parents=True, exist_ok=True)
    title = None
    for _ in range(20):
        title = wind.snapshot("map_name")
        if title is not None and title == wind.snapshot("map_name"):
            break
        time.sleep(0.1)
    if title is None:
        raise wind.Abort
    # 예전 캡처는 끝에 빈 바이트가 붙어 저장돼 있어서, 지금 그림 길이만큼만 견준다
    mine = TITLES / f"{here}.bin"
    if mine.exists() and mine.read_bytes()[:len(title)] == title:
        return here
    for other in TITLES.glob("*.bin"):
        if other.read_bytes()[:len(title)] == title:
            print(f"   지금 맵은 {here}이 아니라 {other.stem}이다. 거기서 이어 간다", flush=True)
            return other.stem
    if mine.exists():
        raise RuntimeError(f"지금 맵이 {here}이 아니다. 어느 맵인지 모르겠다")
    mine.write_bytes(title)
    return here


SHRINE_EXIT = (5, 9)  # 좌성황당에서 성으로 나가는 칸 (상곡좌성황에서 확인)


def revive(castle="상곡"):
    """죽은 뒤(귀신) 되살아나 성으로 나오고 체력을 채운다. 나온 성 이름을 돌려준다.

    성황령(Shift+Z, l) → "갈 곳은?(좌, 우)"에 "좌" → 좌성황당 (5, 4)에 선다 → Enter, "살려주세요", Enter.
    확률로 살아나므로 살 때까지 되풀이한다 (2026-10-11에는 6번째에 살았다). 살아나면 체력이 0.5%쯤이다.
    성황당 안에서는 힐이 안 나간다 (200번 눌러도 마력이 그대로). 성으로 나와서 채운다.
    """
    shrine = f"{castle}좌성황"
    wind.refocus()
    for _ in range(3):
        if wind.prompt_open():
            wind.tap("esc")
            time.sleep(0.2)
    for key in KEYS["revive"]:
        wind.tap(key)
    time.sleep(0.5)
    if not wind.prompt_open():
        raise RuntimeError("성황령을 눌렀는데 갈 곳을 묻는 창이 안 떴다")
    wind.type_text("좌")
    wind.tap("enter")
    for _ in range(30):  # 성황당으로 옮겨지는 데 2초가 넘게 걸린 적이 있다 (2026-10-11 18:36, 그래서 부활을 못 하고 끝났다)
        time.sleep(0.2)
        if nav.read_position() == (5, 4):
            break
    if nav.read_position() != (5, 4):
        raise RuntimeError(f"성황령을 썼는데 성황당 자리가 아니다 ({nav.read_position()})")
    check_map(shrine)
    for attempt in range(1, 61):
        wind.tap("enter")
        time.sleep(0.2)
        wind.type_text("살려주세요")
        time.sleep(0.2)
        wind.tap("enter")
        time.sleep(1.5)
        if (wind.read_bars() or (0.0, 0.0))[0] > 0.002:
            print(f"  {attempt}번째 '살려주세요'에 살아났다", flush=True)
            break
    else:
        raise RuntimeError("'살려주세요'를 60번 했는데 안 살아났다")
    if wind.prompt_open():
        wind.tap("esc")
    if nav.go(shrine, SHRINE_EXIT) != "left":
        raise RuntimeError(f"{shrine}의 {SHRINE_EXIT}을 밟았는데 맵이 안 바뀌었다")
    time.sleep(wind.ROAM["map_wait"])
    home = check_map(f"부여{castle}성")
    locked = wind.relock()
    for _ in range(400):
        if not locked or (wind.read_bars() or (1.0, 1.0))[0] >= 0.9:
            break
        wind.press(KEYS["heal"])
        time.sleep(0.05)
    wind.press("esc")
    time.sleep(0.2)
    print(f"  {home}으로 나왔다. 체력 {(wind.read_bars() or (0.0, 0.0))[0]:.0%}", flush=True)
    return home


BORN = time.monotonic()
RENEW_SECONDS = 2400


def circuit(here):
    """here(지금 있는 맵)에서 시작해 끝없이 돈다.

    성 → 입구 → 1번 묶음 1~10번 방 → (10번 방에서 나가면 성의 입구 건물 앞) → 입구 → 제2 묶음 1~10번
    → … → 제4 묶음 → 다시 1번 묶음. 방 안에서만 사냥하고, 성과 입구에서는 걷기만 한다.
    here는 성 이름, 입구 이름, 방 이름 어느 것이든 된다. 방에서 시작하면 그 묶음의 그 방부터 이어 간다.
    """
    global current_room, active, haunt
    ports, sizes = nav.load_ports()
    fighter = active = Fighter()
    fighter.ports, fighter.sizes = ports, sizes
    started = time.monotonic()
    group = 1  # 다음에 들어갈 묶음
    laps = 0
    while True:
        if time.monotonic() - BORN > RENEW_SECONDS and "--overnight" in sys.argv:
            # 오래 돌면 메모리가 계속 불어서(4시간 반에 90GB), 맵을 넘어갈 때 프로세스를 새로 띄운다
            print(f"{time.strftime('%H:%M:%S')} 메모리를 비우려고 새로 띄운다 ({here})", flush=True)
            extra = [f"--haunt={haunt}"] if haunt else []
            os.execv(sys.executable, [sys.executable, "-u", sys.argv[0], here, "--overnight", *extra])
        here = check_map(here)
        current_room = here
        elapsed = time.monotonic() - started
        room = nav.ROOM.fullmatch(here)
        spooky = HAUNT.fullmatch(here)
        if spooky:
            # 흉가는 묶음을 바꾸지 않는다. 10번 방에서 성으로 나오면 같은 묶음으로 다시 들어간다 (사용자 지시)
            haunt, number = spooky[1], int(spooky[3])
            following = f"{haunt}{number + 1}" if number < LAST_ROOM else f"부여{spooky[2]}성"
            cell = next(c for c, d in ports[here].items() if d == following)
            print(f"== {time.strftime('%H:%M:%S')} {here} → {following} ({elapsed:.0f}초, 사냥 {fighter.count}, "
                  f"헬파이어 때 마력 {fighter.hellfire_mana[-8:]})", flush=True)
            fighter.room = here
            fighter.steps = HUNT["scan_every"]
            try:
                leave(here, cell, ports, sizes, fighter)
            except RuntimeError as error:
                if "싸우는 중에 맵이 바뀌었다" not in str(error):
                    raise
                print(f"   {error} → {following}에 온 것으로 보고 이어 간다", flush=True)
            if number == LAST_ROOM:
                laps += 1
                print(f"   흉가 한 바퀴 끝 {time.strftime('%H:%M:%S')} ({laps}번 돎). 상태창 {save_status()}", flush=True)
        elif here.endswith("흉가입구"):
            if haunt is None:
                raise RuntimeError("어느 흉가 묶음을 돌지 모른다. --haunt=제2상곡흉가 처럼 알려 줘야 한다")
            following = f"{haunt}1"
            cell = next(c for c, d in ports[here].items() if d == following)
            print(f"== {here} → {following} ({elapsed:.0f}초)", flush=True)
            fighter.room = None
            if nav.go(here, cell, ports, sizes) != "left":
                raise RuntimeError(f"{here}의 {cell}을 밟았는데 맵이 안 바뀌었다")
        elif room:
            group = int(re.match(r"제(\d+)", here)[1]) if here.startswith("제") else 1
            number = int(room[3])
            following = next(d for c, d in ports[here].items() if not d.endswith(f"집{number - 1}") and not d.endswith("입구"))
            cell = next(c for c, d in ports[here].items() if d == following)
            print(f"== {time.strftime('%H:%M:%S')} {here} → {following} ({elapsed:.0f}초, 사냥 {fighter.count}, "
                  f"헬파이어 때 마력 {fighter.hellfire_mana[-8:]})", flush=True)
            fighter.room = here
            fighter.steps = HUNT["scan_every"]
            try:
                leave(here, cell, ports, sizes, fighter)
            except RuntimeError as error:
                if "싸우는 중에 맵이 바뀌었다" not in str(error):
                    raise
                # 출구 근처에서 싸우다 출구를 밟았다. 다음 방으로 넘어간 것으로 보고 이어 간다
                print(f"   {error} → {following}에 온 것으로 보고 이어 간다", flush=True)
            if number == LAST_ROOM:
                group = group % GROUPS + 1
                laps += group == 1
                print(f"   묶음 끝 {time.strftime('%H:%M:%S')}. 다음은 {group}번 묶음 (한 바퀴 {laps}번 돎). "
                      f"상태창 {save_status()}", flush=True)
        elif here.endswith("입구"):
            base = here.removesuffix("입구")
            following = f"{'' if group == 1 else f'제{group}'}{base}1"
            cell = next(c for c, d in ports[here].items() if d == following)
            print(f"== {here} → {following} ({elapsed:.0f}초)", flush=True)
            fighter.room = None
            if nav.go(here, cell, ports, sizes) != "left":
                raise RuntimeError(f"{here}의 {cell}을 밟았는데 맵이 안 바뀌었다")
        elif nav.is_castle(here):
            door = ENTRANCE_DOOR
            if haunt:
                door = next(c for c, d in ports[here].items() if d.endswith("흉가입구"))
            nav.use_gate(door)  # 멀면 가까운 문으로 날아간다 (성황당에서 나오면 북서쪽이라 남문이 훨씬 가깝다)
            following = ports[here][door]
            print(f"== {here} → {following} ({elapsed:.0f}초)", flush=True)
            fighter.room = None
            if nav.go(here, door, ports, sizes) != "left":
                raise RuntimeError(f"{here}의 {door}을 밟았는데 맵이 안 바뀌었다")
        else:
            raise RuntimeError(f"{here}은 성도 입구도 방도 아니다")
        here = following
        time.sleep(wind.ROAM["map_wait"])


def release_keys(*_):
    """끝날 때 기본 공격 키가 눌린 채로 남지 않게 뗀다."""
    if KEYS.get("basic"):
        wind._post(wind.KEYCODES[KEYS["basic"]], False)
    raise SystemExit


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, release_keys)
    signal.signal(signal.SIGINT, release_keys)

    def watch_stop_key():
        """게임 창에서 F7(config의 hotkeys.quit)을 누르면 바로 끝낸다."""
        import os
        import Quartz
        code = wind.KEYCODES[wind.HOTKEYS["quit"]]
        # 게임 창이 맨 앞일 때 누른 것만 친다. 키 상태는 어느 창에서 눌러도 읽혀서, 다른 창에서 F7을 쓰면 매크로가 꺼진다
        while not (Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateHIDSystemState, code)
                   and wind.game_window() is not None):
            time.sleep(0.03)
        print(f"{time.strftime('%H:%M:%S')} {wind.HOTKEYS['quit']}을 눌러서 끝낸다", flush=True)
        if KEYS.get("basic"):
            wind._post(wind.KEYCODES[KEYS["basic"]], False)
        os._exit(0)

    import threading
    threading.Thread(target=watch_stop_key, daemon=True).start()
    # 게임 창이 맨 앞일 때만 움직인다. 다른 창을 누르면 그 자리에서 쉬고, 게임 창으로 돌아오면 이어 한다.
    # --overnight: 사람이 없는 동안 돌린다. 게임 창이 앞에 없으면 스스로 앞으로 가져오고,
    # 오류가 나도 끝내지 않고 지금 맵을 다시 확인해 이어 간다. 죽었을 때만 끝낸다.
    overnight = "--overnight" in sys.argv
    current_room = next(arg for arg in sys.argv[1:] if not arg.startswith("--"))
    haunt = next((arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--haunt=")), None)
    print(f"시작 {time.strftime('%Y-%m-%d %H:%M:%S')} {current_room}" + (" (밤새 모드)" if overnight else ""), flush=True)
    errors = deaths = 0
    while True:
        if wind.game_window() is None:
            print(f"{time.strftime('%H:%M:%S')} 게임 창을 기다린다", flush=True)
            if overnight:
                time.sleep(5)
                activate_game()
                time.sleep(1)
        wait_for_game()
        try:
            circuit(current_room)
        except wind.Abort:
            print(f"{time.strftime('%H:%M:%S')} 게임 창이 앞에 없어서 쉰다 ({current_room})", flush=True)
        except Dead:
            deaths += 1
            print(f"{time.strftime('%H:%M:%S')} 죽었다 ({current_room}), {deaths}번째. 화면 {save_status('dead')}", flush=True)
            if KEYS.get("basic"):
                wind._post(wind.KEYCODES[KEYS["basic"]], False)
            if not (overnight and KEYS.get("revive")) or deaths > 20:
                print("끝낸다", flush=True)
                release_keys()
            try:
                current_room = revive()
            except Exception as error:
                print(f"{time.strftime('%H:%M:%S')} 되살아나지 못했다: {error}. 끝낸다. 화면 {save_status('dead')}", flush=True)
                release_keys()
        except Exception as error:
            if "좌표를 읽지 못했다" in str(error):
                print(f"{time.strftime('%H:%M:%S')} 좌표가 안 읽혀서 잠깐 쉬고 다시 한다 ({current_room})", flush=True)
                time.sleep(2)
            elif not overnight:
                raise
            else:
                errors += 1
                print(f"{time.strftime('%H:%M:%S')} 오류 {errors}번째 ({current_room}): {error}. 화면 {save_status('error')}", flush=True)
                try:
                    if active:
                        hold(active, 20)  # 몹 사이에 가만히 서 있지 않게, 제자리에서 싸우다가 다시 해 본다
                except Dead:
                    print(f"{time.strftime('%H:%M:%S')} 죽었다 ({current_room}). 끝낸다. 화면 {save_status('dead')}", flush=True)
                    release_keys()
                except (wind.Abort, RuntimeError):
                    pass
