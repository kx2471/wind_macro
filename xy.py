import pyautogui
import time
import keyboard  # 키보드 이벤트 처리 라이브러리

while True:
    if keyboard.is_pressed('enter'):  # 엔터 키가 눌렸을 때
        print(pyautogui.position())  # 마우스 위치 출력
        time.sleep(1)  # 1초간 대기 (키 입력 중복 방지)
    time.sleep(0.1)  # CPU 과부하 방지를 위한 짧은 대기


