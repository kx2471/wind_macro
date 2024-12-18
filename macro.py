import keyboard

import pyautogui
import time
import threading
import subprocess

# 키매크로 활성화 상태를 나타내는 변수
key_macro_active = True

# 자동사냥매크로 활성화 상태를 나타내는 변수
auto_macro_active = False

# auto_macro_thread 변수를 전역 변수로 선언
auto_macro_thread = None
macro_ai_process = None  # macro_ai.py 프로세스 핸들러

read_detected_text_thread = None  # read_detected_text 스레드 핸들러

def start_read_detected_text():
    """텍스트 파일 읽기 스레드를 시작합니다."""
    global read_detected_text_thread
    
    # 기존 스레드가 실행 중이면 종료 대기
    if read_detected_text_thread is not None and read_detected_text_thread.is_alive():
        print("기존 텍스트 읽기 스레드 종료 중...")
        stop_read_detected_text()
        read_detected_text_thread.join()
        print("기존 텍스트 읽기 스레드 종료 완료")

    # 새 스레드 시작
    read_detected_text_thread = threading.Thread(target=read_detected_text)
    read_detected_text_thread.daemon = True
    read_detected_text_thread.start()
    print("텍스트 읽기 스레드 시작")

def stop_read_detected_text():
    """텍스트 파일 읽기 스레드를 중지합니다."""
    global auto_macro_active
    auto_macro_active = False

def read_detected_text():
    """3초마다 텍스트 파일을 읽고 '마' 또는 '력'을 포함하면 Ctrl + Z를 한 번만 실행."""
    last_processed_text = ""  # 마지막으로 처리된 텍스트를 저장하는 변수

    while auto_macro_active:
        try:
            with open("detected_text.txt", "r", encoding="utf-8") as file:
                # 텍스트 파일 읽기
                text = file.read()
                normalized_text = ''.join(text.split())  # 공백 제거

                # 파일 내용이 변경된 경우 실행
                if normalized_text != last_processed_text:
                    last_processed_text = normalized_text  # 처리한 텍스트 업데이트

                    # '마력'이 포함되어 있는지 확인
                    if '마력' in normalized_text:
                        pyautogui.keyDown('ctrl')
                        pyautogui.press('z')  # Ctrl + Z 누르기
                        pyautogui.keyUp('ctrl')
                        print(normalized_text)
                        print("마력이 부족하여 Ctrl + Z")
        except Exception as e:
            print(f"텍스트 파일 읽기 오류: {e}")

        # 3초 대기 후 다시 읽기 (파일 갱신 주기와 동기화)
        time.sleep(3)





def start_macro_ai():
    """macro_ai.py 스크립트 실행"""
    global macro_ai_process
    if macro_ai_process is None or macro_ai_process.poll() is not None:  # 프로세스가 종료된 경우만 실행
        print("macro_ai.py 스크립트 실행 중...")
        macro_ai_process = subprocess.Popen(["python", "macro_ai.py"])  # macro_ai.py 실행
    else:
        print("macro_ai.py 스크립트는 이미 실행 중입니다.")

def stop_macro_ai():
    """macro_ai.py 스크립트 종료"""
    global macro_ai_process
    if macro_ai_process is not None:
        macro_ai_process.terminate()  # macro_ai.py 프로세스 종료
        macro_ai_process = None
        print("macro_ai.py 스크립트 종료됨.")

def press_key_with_duration(key, duration):
    """지정된 키를 자동으로 누르고 있는 동안 →와 Enter를 반복적으로 실행."""
    print(f"{key} 매크로 실행 중...")
    start_time = time.time()
    while time.time() - start_time < duration:
        pyautogui.keyDown(key)
        pyautogui.press('left')
        pyautogui.press('enter')
        time.sleep(0.01)
    pyautogui.keyUp(key)
    print(f"{key} 매크로 중지")

def debuff_macro(key):
    """지정된 키를 누르고 있는 동안 →와 Enter를 반복적으로 실행."""
    print(f"{key} 매크로 실행 중...")
    while keyboard.is_pressed(key):  # 해당 키가 눌린 상태인지 확인
        pyautogui.press('left')
        time.sleep(0.01)
        pyautogui.press('enter')
        time.sleep(0.01)
    print(f"{key} 매크로 중지")

def bomu_macro():
    """보무 매크로: 5번 + Home + Enter, 6번 + Home + Enter"""
    print("보무 매크로 실행 중...")
    
    time.sleep(0.1)
    pyautogui.press('5')
    pyautogui.press('home')
    pyautogui.press('enter')
    time.sleep(0.1)
    pyautogui.press('6')
    pyautogui.press('home')
    pyautogui.press('enter')
    print("보무 매크로 완료")

def heal_macro():
    """Heal 매크로: 2번을 누르면 2번 + Home 키를 차례대로 누른다."""
    print("Heal 매크로 실행 중...")
    pyautogui.press('home')
    print("2번과 Home 키가 눌렸습니다.")

def heal_auto():
    pyautogui.press('2')
    pyautogui.press('home')
    pyautogui.press('enter')
    time.sleep(0.1)

def auto_macro():
    """자동 사냥 매크로 동작"""
    print("자동 사냥 매크로 시작")
    last_bomu_time = time.time() - 50  # 시작할 때 보무 매크로가 실행되도록 초기화
    last_posion_time = time.time() - 15  # 중독 쿨타임 15초로 초기화

    while auto_macro_active:  # auto_macro_active 상태를 확인
        current_time = time.time()

        # 보무 매크로 실행 조건
        if current_time - last_bomu_time >= 50:
            bomu_macro()
            last_bomu_time = current_time  # 보무 매크로 실행 시간 갱신

        # 중독 매크로 실행 조건
        if current_time - last_posion_time >= 15:
            press_key_with_duration('1', 3)  # 1번 키를 3초 동안 누름
            last_posion_time = current_time  # 중독 실행 시간 갱신

        if not auto_macro_active:
            break

        # 반복 동작
        heal_auto()
        heal_auto()
        pyautogui.press('3')
        time.sleep(0.75)
        pyautogui.press('3')
        time.sleep(0.75)
        pyautogui.press('3')
        time.sleep(0.75)
        pyautogui.press('4')
        heal_auto()
        heal_auto()
        heal_auto()
        heal_auto()
        heal_auto()
        pyautogui.press('4')
        heal_auto()
        heal_auto()
        heal_auto()
        heal_auto()
        heal_auto()

    print("자동 사냥 매크로 종료")


def start_auto_macro():
    """자동 매크로를 스레드로 실행"""
    global auto_macro_thread

    # 기존 자동 매크로 스레드 종료
    if auto_macro_thread is not None and auto_macro_thread.is_alive():
        print("기존 자동 매크로 스레드 종료 중...")
        global auto_macro_active
        auto_macro_active = False
        auto_macro_thread.join()
        print("기존 자동 매크로 스레드 종료 완료")

    # 새 자동 매크로 스레드 시작
    auto_macro_active = True
    auto_macro_thread = threading.Thread(target=auto_macro)
    auto_macro_thread.daemon = True
    auto_macro_thread.start()
    print("자동 매크로 즉시 시작")

    # 텍스트 파일 읽기 스레드 시작
    start_read_detected_text()

    # macro_ai.py 스크립트 실행
    start_macro_ai()

def stop_auto_macro():
    """자동 매크로 중지"""
    global auto_macro_active
    auto_macro_active = False
    stop_macro_ai()  # macro_ai.py 종료

def main():
    global key_macro_active, auto_macro_active
    print("디버프 매크로 실행 중. 일반 숫자 키 7, 8, 9 키를 누르고 있으면 매크로가 실행됩니다.")
    print("보무 매크로는 숫자 키 '5'로 실행됩니다.")
    print("힐 매크로는 숫자 키 '2'로 실행됩니다.")
    print("프로그램을 활성화/비활성화하려면 'f11'을 누르세요.")
    print("자동 매크로는 'f9'로 활성화/비활성화됩니다.")

    try:
        previous_key_macro_state = key_macro_active
        previous_auto_macro_state = auto_macro_active

        while True:
            # 상태가 변경되었을 때만 출력
            if key_macro_active != previous_key_macro_state or auto_macro_active != previous_auto_macro_state:
                print(f"키매크로 : {key_macro_active}\n자동사냥 매크로 : {auto_macro_active}")
                previous_key_macro_state = key_macro_active
                previous_auto_macro_state = auto_macro_active

            # 키 입력 처리
            if keyboard.is_pressed('f11'):
                key_macro_active = not key_macro_active
                if key_macro_active:
                    auto_macro_active = False  # auto_macro 비활성화
                    print("매크로 활성화")
                else:
                    print("매크로 비활성화")
                time.sleep(1)

            if keyboard.is_pressed('f9'):
                auto_macro_active = not auto_macro_active
                if auto_macro_active:
                    key_macro_active = False  # key_macro 비활성화
                    print("자동 매크로 활성화")
                    start_auto_macro()
                else:
                    print("자동 매크로 비활성화")
                    stop_auto_macro()
                time.sleep(1)

            if key_macro_active:  # 매크로가 활성화 상태일 때만 실행
                if keyboard.is_pressed('7'):
                    debuff_macro('7')

                if keyboard.is_pressed('1'):
                    debuff_macro('1')

                if keyboard.is_pressed('9'):
                    debuff_macro('9')

                if keyboard.is_pressed('5'):
                    bomu_macro()

                if keyboard.is_pressed('2'):
                    heal_macro()

            if keyboard.is_pressed('f12'):  # f12로 프로그램 종료
                print("프로그램 종료")
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("프로그램 강제 종료")

if __name__ == "__main__":
    main()
