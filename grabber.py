"""화면 캡처만 하는 일꾼 프로세스. wind.grab이 띄워서 쓴다.

CGWindowListCreateImage는 찍을 때마다 찍은 프로세스 안에 "Mach message" 메모리를 남기고 풀 방법이 없다
(2026-10-11, 4시간 반에 90GB). 그래서 캡처는 여기서 하고, 많이 찍으면 wind 쪽에서 이 프로세스를 갈아 치운다.

표준 입력으로 "x y width height" 한 줄(화면 좌표)을 받으면, 표준 출력으로
"길이 줄당바이트 그림너비" 한 줄과 픽셀 바이트를 돌려준다. 못 찍으면 "0 0 0".
"""

import sys

import Quartz

out = sys.stdout.buffer
out.write(b"ready\n")
out.flush()
for line in sys.stdin.buffer:
    x, y, width, height = map(float, line.split())
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectMake(x, y, width, height),
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if image is None:
        out.write(b"0 0 0\n")
    else:
        data = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image)))
        out.write(b"%d %d %d\n" % (len(data), Quartz.CGImageGetBytesPerRow(image), Quartz.CGImageGetWidth(image)))
        out.write(data)
    out.flush()
