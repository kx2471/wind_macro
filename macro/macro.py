import keyboard
import pyautogui
import time

# 매크로 활성화 상태를 나타내는 변수
macro_active = True

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

def main():
    global macro_active  # 활성화 상태를 변경할 수 있도록 설정
    print("디버프 매크로 실행 중. 일반 숫자 키 7, 8, 9 키를 누르고 있으면 매크로가 실행됩니다.")
    print("보무 매크로는 숫자 키 '5'로 실행됩니다.")
    print("힐 매크로는 숫자 키 '2'로 실행됩니다.")
    print("프로그램을 활성화/비활성화하려면 'f11'을 누르세요.")

    try:
        while True:
            if keyboard.is_pressed('f11'):  # F11 키로 매크로 활성화/비활성화
                macro_active = not macro_active
                if macro_active:
                    print("매크로 활성화")
                else:
                    print("매크로 비활성화")
                time.sleep(1)  # F11이 여러 번 눌리지 않도록 딜레이 추가

            if macro_active:  # 매크로가 활성화 상태일 때만 실행
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
