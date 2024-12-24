import pytesseract
from PIL import Image
import os


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR\tessdata'

# 이미지에서 텍스트 추출\
custom_config = r'--psm 11'  # PSM 11 옵션 추가
text = pytesseract.image_to_string('aaaaa.png', lang='kor', config=custom_config)
print(text)