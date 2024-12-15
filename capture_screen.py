import keyboard
from PIL import ImageGrab
import numpy as np
import os
import time

# 바탕화면 경로 설정
desktop_path = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')

# 파일 번호 초기화
counter = 1

def capture_screen(counter):
    """게임 화면에서 특정 영역을 캡처하고 번호를 붙여서 저장한 후 tesseract 명령어 실행."""
    bbox = (1395, 705, 1727, 827)

    screen = ImageGrab.grab(bbox)
    
    # 파일 이름 생성: 바탕화면에 "1.png", "2.png", ... 형식으로 저장
    image_file = os.path.join(desktop_path, f"{counter}.png")
    
    # 캡처된 이미지를 바탕화면에 저장
    screen.save(image_file)
    print(f"이미지 {counter} 저장됨: {image_file}")
    
    
    return counter + 1  # 번호를 증가시켜 반환

def main():
    """엔터 키를 누를 때마다 화면을 캡처하고, 번호를 붙여 바탕화면에 저장하고, tesseract 실행."""
    global counter
    print("엔터 키를 누를 때마다 화면을 캡처하고, 바탕화면에 번호를 붙여 저장하고, tesseract를 실행합니다. 종료하려면 'Esc'를 누르세요.")
    try:
        while True:
            if keyboard.is_pressed('enter'):  # 엔터 키가 눌리면
                counter = capture_screen(counter)  # 화면 캡처 후 번호 증가
                time.sleep(0.5)  # 키 입력이 여러 번 감지되지 않도록 잠시 대기
            elif keyboard.is_pressed('esc'):  # esc 키를 누르면 종료
                print("프로그램 종료")
                break
            time.sleep(0.1)  # CPU 사용을 줄이기 위한 대기
    except KeyboardInterrupt:
        print("프로그램 종료")

if __name__ == "__main__":
    main()
