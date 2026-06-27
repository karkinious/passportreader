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
            if result:
                all_results.extend(self._extract_pairs(result))

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

    def _extract_pairs(self, data):
        """
        Recursively extracts (text, confidence) pairs from PaddleOCR result structure.
        Handles both dictionary formats (new PaddleOCR/PaddleX) and classic list-of-lists formats.
        """
        pairs = []
        if isinstance(data, dict):
            if 'rec_texts' in data and 'rec_scores' in data:
                texts = data['rec_texts']
                scores = data['rec_scores']
                if isinstance(texts, list) and isinstance(scores, list):
                    for t, s in zip(texts, scores):
                        if isinstance(t, str) and isinstance(s, (int, float)):
                            pairs.append((t, s))
            else:
                for val in data.values():
                    pairs.extend(self._extract_pairs(val))
        elif isinstance(data, (list, tuple)):
            if len(data) == 2 and isinstance(data[1], (list, tuple)) and len(data[1]) == 2 and isinstance(data[1][0], str) and isinstance(data[1][1], (int, float)):
                pairs.append((data[1][0], data[1][1]))
            else:
                for item in data:
                    pairs.extend(self._extract_pairs(item))
        return pairs

    def _parse_ocr_results(self, results):
        """Extracts MRZ lines and other potential data from PaddleOCR results."""
        # results format: list of (text, confidence) tuples
        lines_with_spaces = [item[0].upper().strip() for item in results if item]
        lines = [line.replace(' ', '') for line in lines_with_spaces]
        confidences = [item[1] for item in results]

        middle_name = self._extract_middle_name(lines_with_spaces)

        mrz_lines = []
        mrz_confidences = []

        for i, line in enumerate(lines):
            # MRZ lines are typically 30, 36, or 44 characters long and contain many '<'
            # Enhanced detection: MRZ lines usually have a specific structure
            if line.count('<') > 5 or (len(line) in [30, 36, 44] and any(c.isdigit() for c in line) and '<' in line):
                mrz_lines.append(line)
                mrz_confidences.append(confidences[i])

        # Try to correct first line of PHL passports
        is_phl = False
        if len(mrz_lines) >= 2 and len(mrz_lines[1]) >= 13 and mrz_lines[1][10:13] == 'PHL':
            is_phl = True
        else:
            is_phl = any('FILIPINO' in l or 'PHL' in l for l in lines)

        if is_phl and len(mrz_lines) >= 1:
            line1 = mrz_lines[0]
            if line1.startswith('P<PL'):
                mrz_lines[0] = 'P<PHL' + line1[4:]
            elif line1.startswith('P<PH') and not line1.startswith('P<PHL'):
                mrz_lines[0] = 'P<PHL' + line1[4:]
            elif line1.startswith('P<P') and not line1.startswith('P<PH') and not line1.startswith('P<PL'):
                mrz_lines[0] = 'P<PHL' + line1[3:]

        extracted_data = {
            'raw_text': lines,
            'raw_text_lines': lines_with_spaces,
            'middle_name': middle_name,
            'mrz': mrz_lines,
            'mrz_confidence': sum(mrz_confidences)/len(mrz_confidences) if mrz_confidences else 0,
            'parsed_mrz': None
        }

        if mrz_lines:
            target_len = 44
            if len(mrz_lines) == 3:
                target_len = 30
            elif len(mrz_lines) == 2:
                max_len = max(len(l) for l in mrz_lines)
                if max_len <= 36:
                    target_len = 36
                else:
                    target_len = 44

            cleaned_mrz_lines = [self._clean_mrz_line(line, target_len) for line in mrz_lines]
            mrz_text = "\n".join(cleaned_mrz_lines)

            # Try parsing with different checkers
            for checker_class in [TD3CodeChecker, TD2CodeChecker, TD1CodeChecker]:
                try:
                    checker = checker_class(mrz_text)
                    fields = checker.fields()
                    extracted_data['parsed_mrz'] = self._format_checker_fields(fields, lines_with_spaces, middle_name=middle_name)
                    if extracted_data['parsed_mrz']:
                        surname = extracted_data['parsed_mrz'].get('surname', '')
                        given_names = extracted_data['parsed_mrz'].get('given_names', '')
                        place_of_birth = self._extract_place_of_birth(lines_with_spaces, surname=surname, given_names=given_names)
                        extracted_data['parsed_mrz']['place_of_birth'] = place_of_birth
                    break
                except:
                    continue

        return extracted_data

    def _extract_middle_name(self, raw_text_lines):
        """Extracts middle name based on common labels."""
        # 'APELYIDO' alone refers to Surname in PHL passports.
        # We need the full 'PANGGITNANG APELYIDO' for middle name.
        labels = ['MIDDLE NAME', 'PANGGITNANG APELYIDO', 'PANGGITNANG']
        lines = [l.strip().upper() for l in raw_text_lines if l.strip()]

        for idx, line in enumerate(lines):
            line_no_spaces = line.replace(' ', '')
            # Check if any label is in the line
            matching_label = next((l for l in labels if l.replace(' ', '') in line_no_spaces), None)
            if matching_label:
                # 1. Try same line first (in case OCR merged label and value)
                potential = line.replace(matching_label, '').replace('/', '').replace(':', '').strip()
                if len(potential) >= 2 and not any(c.isdigit() for c in potential):
                    if not any(l.replace(' ', '') in potential.replace(' ', '') for l in labels + ['PLACEOFBIRTH', 'BIRTH', 'SURNAME', 'GIVEN']):
                        return potential

                # 2. Try to find the value in the next few lines
                for offset in [1, 2]:
                    if idx + offset < len(lines):
                        candidate = lines[idx + offset]
                        candidate_no_spaces = candidate.replace(' ', '')

                        # Skip if it is noise, standard labels, or too short
                        if candidate_no_spaces in ['M', 'F', 'MALE', 'FEMALE', 'PHL'] or len(candidate_no_spaces) < 2:
                            continue
                        # Skip if it contains digits (likely a date or passport number)
                        if any(char.isdigit() for char in candidate):
                            continue
                        # Skip if it's another label
                        if any(label.replace(' ', '') in candidate_no_spaces for label in labels + ['PLACEOFBIRTH', 'BIRTH', 'SURNAME', 'GIVEN']):
                            continue

                        return candidate
        return ""

    def _extract_place_of_birth(self, raw_text_lines, surname="", given_names=""):
        # Normalize lines
        lines = [l.strip().upper() for l in raw_text_lines if l.strip()]
        
        # 1. Try to find by label first
        for idx, line in enumerate(lines):
            line_no_spaces = line.replace(' ', '')
            if 'PLACEOFBIRTH' in line_no_spaces or 'PLACE OF BIRTH' in line or 'LUGARNGKAPANGANAKAN' in line_no_spaces:
                # Look at the next few lines (up to 2) to find a valid place of birth
                for offset in [1, 2]:
                    if idx + offset < len(lines):
                        candidate = lines[idx + offset]
                        candidate_no_spaces = candidate.replace(' ', '')
                        # Skip if it is noise or standard labels
                        if candidate_no_spaces in ['M', 'F', 'MALE', 'FEMALE', 'PLACEOFBIRTH', 'GRC', 'PHL']:
                            continue
                        if any(char.isdigit() for char in candidate):
                            continue
                        return candidate
                        
        # 2. Fall back to nationality-relative search
        nat_index = -1
        for idx, line in enumerate(lines):
            if any(term in line.replace(' ', '') for term in ['FILIPINO', 'HELLENIC', 'EAAHNIKH', 'NATIONALITY', 'LUGARNGKAPANGANAKAN', 'PLACEOFBIRTH']):
                nat_index = idx
                break
                
        if nat_index != -1:
            # Prepare names to skip
            names_to_skip = set()
            for name in [surname, given_names]:
                if name:
                    # add parts of name
                    for part in name.upper().split():
                        names_to_skip.add(part.replace(' ', ''))
                        
            for i in range(nat_index + 1, len(lines)):
                line = lines[i]
                line_no_spaces = line.replace(' ', '')
                # Skip if it matches sex
                if line_no_spaces in ['M', 'F', 'MALE', 'FEMALE']:
                    continue
                # Skip if it matches name parts
                if any(part in line_no_spaces or line_no_spaces in part for part in names_to_skip):
                    continue
                # Skip if it is a date
                has_month = any(m in line_no_spaces for m in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])
                has_digits = any(c.isdigit() for c in line_no_spaces)
                if has_month and has_digits:
                    continue
                # Skip small codes
                if len(line_no_spaces) <= 3 and any(c.isdigit() for c in line_no_spaces):
                    continue
                # Skip standard passport identifiers
                if line_no_spaces.startswith('P<') or any(line_no_spaces.startswith(p) for p in ['P4', 'P6', 'P1', 'P8', 'P9']):
                    continue
                # Skip common labels
                if 'PLACEOFBIRTH' in line_no_spaces or 'PLACEOF' in line_no_spaces or 'BIRTH' in line_no_spaces:
                    continue
                return line
        return ""

    def _clean_mrz_line(self, line, target_len):
        """Applies fuzzy logic to correct common OCR errors in MRZ lines."""
        # Keep only alphanumeric and '<'
        cleaned = ''.join(c for c in line if c.isalnum() or c == '<')
        
        # Adjust length to target_len (pad with '<' if too short, truncate if too long)
        if len(cleaned) > target_len:
            cleaned = cleaned[:target_len]
        elif len(cleaned) < target_len:
            cleaned = cleaned + '<' * (target_len - len(cleaned))

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

    def _clean_name_digits(self, name_str):
        if not name_str:
            return ""
        mapping = {
            '0': 'O',
            '1': 'I',
            '2': 'Z',
            '8': 'B',
            '5': 'S'
        }
        return "".join(mapping.get(c, c) for c in name_str.upper())

    def _correct_name(self, name_str, raw_lines):
        if not name_str:
            return ""
            
        name_str = self._clean_name_digits(name_str)
        
        clean_mrz = name_str.replace('<', '').replace(' ', '')
        if len(clean_mrz) >= 3:
            for line in raw_lines:
                line_clean = ''.join(c for c in line.upper() if c.isalnum())
                line_clean = self._clean_name_digits(line_clean)
                line_clean = ''.join(c for c in line_clean if c.isalpha())
                
                if len(line_clean) > len(clean_mrz) and len(line_clean) <= len(clean_mrz) + 4:
                    it = iter(line_clean)
                    if all(char in it for char in clean_mrz):
                        return line_clean
                        
        return name_str

    def _format_checker_fields(self, fields, raw_lines, middle_name=""):
        from utils import parse_date
        
        nat = getattr(fields, 'nationality', '')
        if not nat:
            nat = getattr(fields, 'country', '')
            
        # Normalize nationality if it has common OCR errors
        if nat in ['PLV', 'PLB', 'PH1', 'P1HL']:
            nat = 'PHL'
            
        dob = getattr(fields, 'birth_date', '')
        dob_iso = parse_date(dob) if dob else ''
        
        exp = getattr(fields, 'expiry_date', '')
        exp_iso = parse_date(exp) if exp else ''
        
        surname = getattr(fields, 'surname', '')
        given_names = getattr(fields, 'name', '')
        
        surname = self._correct_name(surname, raw_lines)
        given_names = self._correct_name(given_names, raw_lines)
        
        if middle_name:
            # Append middle name to given names if not already present
            middle_name_upper = middle_name.upper().strip()
            given_names_upper = given_names.upper()

            # Split given names and middle name to check for exact part match
            given_parts = given_names_upper.split()
            middle_parts = middle_name_upper.split()

            # If any part of middle name is missing from given names, append the whole thing
            if not all(part in given_parts for part in middle_parts):
                given_names = f"{given_names} {middle_name_upper}".strip()

        return {
            'surname': surname,
            'given_names': given_names,
            'nationality': nat,
            'passport_number': getattr(fields, 'document_number', ''),
            'sex': getattr(fields, 'sex', ''),
            'date_of_birth': dob_iso,
            'passport_expiry': exp_iso,
            'issuer': getattr(fields, 'issuer', '')
        }

if __name__ == '__main__':
    print("OCR Engine ready.")
