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
            result = self.ocr.ocr(img_np, cls=True)
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
        lines = [line[1][0].upper().replace(' ', '') for line in results]
        confidences = [line[1][1] for line in results]

        mrz_lines = []
        mrz_confidences = []

        for i, line in enumerate(lines):
            # MRZ lines are typically 30, 36, or 44 characters long and contain many '<'
            # Enhanced detection: MRZ lines usually have a specific structure
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
            cleaned_mrz_lines = [self._clean_mrz_line(line) for line in mrz_lines]
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

    def _clean_mrz_line(self, line):
        """Applies fuzzy logic to correct common OCR errors in MRZ lines."""
        # Keep only alphanumeric and '<'
        cleaned = ''.join(c for c in line if c.isalnum() or c == '<')
        
        # If the line ends with a lot of noise, truncate to valid MRZ lengths
        if len(cleaned) > 44: cleaned = cleaned[:44]
        elif 36 < len(cleaned) < 44: cleaned = cleaned[:36]
        elif 30 < len(cleaned) < 36: cleaned = cleaned[:30]

        # Fuzzy corrections for common substitutions in numeric areas
        # This is a general sweep - professional MRZ checkers do this per-field
        # We target fields like DOB and Expiry which are highly sensitive to O vs 0
        
        # If it looks like a TD3 second line (starts with document number + check digit + nationality)
        # We can apply some heuristics. For now, let's do common swaps if they appear in numeric-heavy zones.
        if len(cleaned) == 44 and cleaned[0].isalnum():
             # TD3 Line 2: [0:9]Doc, [9]CD, [10:13]Nat, [13:19]DOB, [19]CD, [20]Sex, [21:27]Exp, [27]CD...
             list_line = list(cleaned)
             # Fix DOB [13:19] and Exp [21:27]
             for i in range(13, 19):
                 if list_line[i] == 'O': list_line[i] = '0'
                 if list_line[i] == 'I': list_line[i] = '1'
             for i in range(21, 27):
                 if list_line[i] == 'O': list_line[i] = '0'
                 if list_line[i] == 'I': list_line[i] = '1'
             cleaned = "".join(list_line)

        return cleaned

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
