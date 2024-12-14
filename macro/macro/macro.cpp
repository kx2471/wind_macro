#include <iostream>
#include <Windows.h>
#include <thread>

void pressKey(WORD key) {
    INPUT input = { 0 };
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = key;
    SendInput(1, &input, sizeof(INPUT));  // 키 누름

    ZeroMemory(&input, sizeof(INPUT));
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = key;
    input.ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(1, &input, sizeof(INPUT));  // 키 뗌
}

void debuffMacro(int key) {
    std::cout << key << " 매크로 실행 중..." << std::endl;

    while (GetAsyncKeyState(key) & 0x8000) {  // 해당 키가 눌린 상태인 경우
        pressKey(VK_LEFT);  // 왼쪽 방향키
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        pressKey(VK_RETURN);  // Enter키
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    std::cout << key << " 매크로 중지" << std::endl;
}

void bomuMacro() {
    std::cout << "보무 매크로 실행 중..." << std::endl;
    pressKey('5');  // '5' 키
    pressKey(VK_HOME);  // Home 키
    pressKey(VK_RETURN);  // Enter 키
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    pressKey('6');  // '6' 키
    pressKey(VK_HOME);  // Home 키
    pressKey(VK_RETURN);  // Enter 키
    std::cout << "보무 매크로 완료" << std::endl;
}

void healMacro() {
    std::cout << "Heal 매크로 실행 중..." << std::endl;
    pressKey(VK_HOME);  // Home 키
    std::cout << "2번과 Home 키가 눌렸습니다." << std::endl;
}

int main() {
    std::cout << "디버프 매크로 실행 중. 넘버패드의 7, 8, 9 키를 누르고 있으면 매크로가 실행됩니다." << std::endl;
    std::cout << "보무 매크로는 넘버패드의 '5' 키로 실행됩니다." << std::endl;
    std::cout << "힐 매크로는 넘버패드의 '2' 키로 실행됩니다." << std::endl;
    std::cout << "프로그램 종료를 원하면 'F11'을 누르세요." << std::endl;

    try {
        while (true) {
            if (GetAsyncKeyState(0x27) & 0x8000) {  // 7 키
                debuffMacro(0x27);
            }

            if (GetAsyncKeyState(0x28) & 0x8000) {  // 8 키
                debuffMacro(0x28);
            }

            if (GetAsyncKeyState(0x29) & 0x8000) {  // 9 키
                debuffMacro(0x29);
            }

            if (GetAsyncKeyState(0x64) & 0x8000) {  // 넘버패드 5
                bomuMacro();
            }

            if (GetAsyncKeyState(0x62) & 0x8000) {  // 넘버패드 2
                healMacro();
            }

            if (GetAsyncKeyState(VK_F11) & 0x8000) {  // F11 키
                std::cout << "프로그램 종료" << std::endl;
                break;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
    catch (const std::exception& e) {
        std::cout << "프로그램 강제 종료" << std::endl;
    }

    return 0;
}
