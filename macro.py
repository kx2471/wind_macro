import keyboard
import pyautogui
import time
import threading

# 키매크로 활성화 상태를 나타내는 변수
key_macro_active = True

# 자동사냥매크로 활성화 상태를 나타내는 변수
auto_macro_active = False

# auto_macro_thread 변수를 전역 변수로 선언
auto_macro_thread = None

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
    last_bomu_time = time.time()  # 시작할 때 보무 매크로가 실행되도록 초기화

    while auto_macro_active:  # auto_macro_active 상태를 확인
        current_time = time.time()

        
        # 보무 매크로 실행 조건
        if current_time - last_bomu_time >= 100:
            bomu_macro()           
            last_bomu_time = current_time  # 보무 매크로 실행 시간 갱신

        # 중간에 상태를 다시 확인
        if not auto_macro_active:
            break

        # 반복 동작 전에 추가할 작업
        press_key_with_duration('1', 2)  # 1번 키로 2초 동안 실행
        if not auto_macro_active:
            break

        press_key_with_duration('9', 2)  # 9번 키로 2초 동안 실행
        if not auto_macro_active:
            break

        # for문 안에서 auto_macro_active 상태를 반복적으로 확인하도록 수정
        for _ in range(5):  # 다음 동작을 5회 반복
            if not auto_macro_active:
                break  # auto_macro_active가 False이면 반복문 종료
            
            heal_auto()
            heal_auto()
            pyautogui.press('3')            
            time.sleep(1)  # 1초 딜레이 추가
            pyautogui.press('3')
            time.sleep(1)
            pyautogui.press('3')
            time.sleep(1)
            pyautogui.press('4')
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

    # 기존 스레드가 실행 중이면 종료 상태를 설정
    if auto_macro_thread is not None and auto_macro_thread.is_alive():
        print("기존 자동 매크로 스레드 종료 중...")
        global auto_macro_active
        auto_macro_active = False
        auto_macro_thread.join()  # 기존 스레드가 종료되길 기다림
        print("기존 자동 매크로 스레드 종료 완료")

    # 새 스레드 시작
    auto_macro_active = True
    auto_macro_thread = threading.Thread(target=auto_macro)
    auto_macro_thread.daemon = True
    auto_macro_thread.start()
    print("자동 매크로 즉시 시작")

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
