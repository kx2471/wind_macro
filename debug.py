from pynput import keyboard

def on_press(key):
    try:
        if key == keyboard.Key.left:
            print("왼쪽 화살표가 눌렸습니다.")
        elif key.char == '4':
            print("NumPad 4이 눌렸습니다.")
    except AttributeError:
        pass

def on_release(key):
    if key == keyboard.Key.esc:
        print("프로그램 종료")
        return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    print("키보드 입력을 감지 중입니다. ESC를 눌러 종료하세요.")
    listener.join()
