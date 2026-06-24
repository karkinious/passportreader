import os
import fitz  # PyMuPDF
from paddleocr import PaddleOCR
from mrz.checker.td3 import TD3CodeChecker
from mrz.checker.td2 import TD2CodeChecker
from mrz.checker.td1 import TD1CodeChecker
from PIL import Image
import io
import numpy as np
import logging

# Suppress PaddleOCR logs
logging.getLogger('ppocr').setLevel(logging.ERROR)

class OCREngine:
    def __init__(self):
        # Initialize PaddleOCR
        # Updated parameters based on the latest PaddleOCR version
        self.ocr = PaddleOCR(use_textline_orientation=True, lang='en')

    def process_file(self, file_path):
        """Processes an image or PDF and returns extracted data."""
        if file_path.lower().endswith('.pdf'):
            images = self._pdf_to_images(file_path)
        else:
            try:
                images = [Image.open(file_path)]
            except Exception as e:
                print(f"Error opening image {file_path}: {e}")
                return None

        all_results = []
        for img in images:
            img_np = np.array(img.convert('RGB'))
            # Removed cls=True as it causes TypeError in some versions of PaddleOCR
            result = self.ocr.ocr(img_np)
            if result and result[0]:
                all_results.extend(result[0])

        return self._parse_ocr_results(all_results)

    def _pdf_to_images(self, pdf_path):
        """Converts PDF pages to PIL images."""
        images = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                images.append(Image.open(io.BytesIO(img_data)))
        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {e}")
        return images

    def _parse_ocr_results(self, results):
        """Extracts MRZ lines and other potential data from PaddleOCR results."""
        # result format: [ [[box], (text, confidence)], ... ]
        lines = []
        confidences = []

        for item in results:
            try:
                # Basic check for expected format [[box], (text, confidence)]
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                        text = text_info[0]
                        conf = text_info[1]
                        if isinstance(text, str):
                            lines.append(text.replace(' ', ''))
                            confidences.append(float(conf) if conf is not None else 0.0)
            except (IndexError, TypeError, ValueError):
                continue

        mrz_lines = []
        mrz_confidences = []

        for i, line in enumerate(lines):
            # MRZ lines are typically 30, 36, or 44 characters long and contain many '<'
            if line.count('<') > 5 or (len(line) in [30, 36, 44] and any(c.isdigit() for c in line) and '<' in line):
                mrz_lines.append(line)
                mrz_confidences.append(confidences[i])

        extracted_data = {
            'raw_text': lines,
            'mrz': mrz_lines,
            'mrz_confidence': sum(mrz_confidences)/len(mrz_confidences) if mrz_confidences else 0,
            'parsed_mrz': None
        }

        if mrz_lines:
            # Clean MRZ lines (sometimes OCR adds noise at the end)
            cleaned_mrz_lines = []
            for line in mrz_lines:
                # Keep only alphanumeric and '<'
                cleaned = ''.join(c for c in line if c.isalnum() or c == '<')
                cleaned_mrz_lines.append(cleaned)

            mrz_text = "\n".join(cleaned_mrz_lines)

            # Try parsing with different checkers
            for checker_class in [TD3CodeChecker, TD2CodeChecker, TD1CodeChecker]:
                try:
                    checker = checker_class(mrz_text)
                    if checker:
                        fields = checker.fields()
                        extracted_data['parsed_mrz'] = self._format_checker_fields(fields)
                        break
                except:
                    continue

        return extracted_data

    def _format_checker_fields(self, fields):
        return {
            'surname': getattr(fields, 'surname', ''),
            'given_names': getattr(fields, 'name', ''),
            'nationality': getattr(fields, 'country', ''),
            'passport_number': getattr(fields, 'document_number', ''),
            'sex': getattr(fields, 'sex', ''),
            'date_of_birth': getattr(fields, 'birth_date', ''),
            'passport_expiry': getattr(fields, 'expiry_date', ''),
            'issuer': getattr(fields, 'issuer', '')
        }

if __name__ == '__main__':
    print("OCR Engine ready.")
