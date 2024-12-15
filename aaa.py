import subprocess
import pytesseract
import os

# Tesseract 실행 파일 경로 지정
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 바탕화면 경로 설정
desktop_path = r'C:\Users\aa\Desktop'

# Tesseract 명령어 경로 (subprocess에서 사용)
tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 1부터 50까지 tesseract 명령어 실행
for i in range(1, 51):
    image_file = os.path.join(desktop_path, f"{i}.png")  # 바탕화면 경로와 파일 이름 결합
    text_file = os.path.join(desktop_path, f"{i}.txt")  # 바탕화면 경로와 파일 이름 결합
    
    # tesseract 명령어 생성
    command = [tesseract_cmd, image_file, text_file, "-l", "kor"]
    
    # tesseract 실행
    result = subprocess.run(command, capture_output=True, text=True)
    
    # 디버깅 출력
    print(f"명령어 실행: {' '.join(command)}")
    print(f"결과: {result.stdout}")
    print(f"오류: {result.stderr}")

    print(f"Tesseract {i}번 파일 실행 완료: {image_file} -> {text_file}")
