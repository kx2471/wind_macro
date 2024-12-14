import pyautogui
import cv2
import numpy as np

def capture_screen(region=None):
    """화면 캡처 함수"""
    screenshot = pyautogui.screenshot(region=region)  # 특정 영역만 캡처 가능
    screenshot_np = np.array(screenshot)  # OpenCV에서 사용 가능한 형식으로 변환
    return cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

def extract_region(image, x, y, w, h):
    """화면의 특정 영역 추출"""
    return image[y:y+h, x:x+w]

# 예: 마나 창 좌표 (x=100, y=500, width=200, height=50)
mana_region = extract_region(image, 100, 500, 200, 50)

