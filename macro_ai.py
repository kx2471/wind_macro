import os
import pytesseract
from PIL import ImageGrab, Image
import time

# Tesseract 경로 설정
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR\tessdata'


def capture_screen():
    """게임 화면에서 특정 영역을 캡처합니다."""
    bbox = (1395, 656, 1758, 785)  # 캡처할 화면 영역 (좌측 상단, 우측 하단)
    screen = ImageGrab.grab(bbox)
    
    # 스크린샷 파일로 저장 (디버깅 용)
    screen.save("captured_image.png")
    return screen

def detect_text(image):
    """캡처한 이미지에서 텍스트를 검출합니다."""
    try:
        # Tesseract로 텍스트 검출
        custom_config = r'--psm 11'  # PSM 11 옵션 추가
        text = pytesseract.image_to_string(image, lang='kor', config=custom_config)
        
        # 텍스트 파일로 저장 (디버깅 용)
        with open("detected_text.txt", "w", encoding="utf-8") as file:
            file.write(text)
        
        return text
    except Exception as e:
        print(f"텍스트 인식 오류: {e}")
        return ""

def main():
    """반복적으로 캡처하고 텍스트를 추출하여 갱신합니다."""
    while True:
        # 화면 캡처
        screenshot = capture_screen()
        
        # 캡처된 이미지에서 텍스트 추출
        detected_text = detect_text(screenshot)      
        
        # 1초 대기 후 다음 캡처 진행
        time.sleep(3)  # 3초 간격으로 계속 실행 (원하는 간격에 맞게 조정 가능)

if __name__ == "__main__":
    main()
