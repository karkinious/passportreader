import os
import fitz  # PyMuPDF
import re
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
                    surname = getattr(fields, 'surname', '')
                    given_names = getattr(fields, 'name', '')

                    # Fallback for PHL passports if label search failed
                    if is_phl and not middle_name:
                        middle_name = self._extract_middle_name_positional(lines_with_spaces, surname_anchor=surname, given_anchor=given_names)
                        extracted_data['middle_name'] = middle_name

                    extracted_data['parsed_mrz'] = self._format_checker_fields(fields, lines_with_spaces, middle_name=middle_name)
                    if extracted_data['parsed_mrz']:
                        surname_corr = extracted_data['parsed_mrz'].get('surname', '')
                        given_corr = extracted_data['parsed_mrz'].get('given_names', '')
                        place_of_birth = self._extract_place_of_birth(lines_with_spaces, surname=surname_corr, given_names=given_corr)
                        extracted_data['parsed_mrz']['place_of_birth'] = place_of_birth
                    break
                except:
                    continue

        return extracted_data

    def _extract_middle_name_positional(self, raw_text_lines, surname_anchor="", given_anchor="", debug=True):
        """
        Fallback for PHL passports where the label might be missed or mangled.
        Looks for the line immediately following Surname and Given Names.
        Uses MRZ-parsed names as anchors to find the correct name block.
        """
        if debug:
            print(f"  DEBUG: Positional Search Anchors - Surname: '{surname_anchor}', Given: '{given_anchor}'")

        lines = [l.strip().upper() for l in raw_text_lines if l.strip()]

        # Clean anchors - don't remove '<' yet, use them as delimiters
        s_anchor = surname_anchor.upper().replace('<', ' ').strip()
        g_anchor = given_anchor.upper().replace('<', ' ').strip()

        if not s_anchor or not g_anchor:
            return ""

        # In PHL passports, the layout is usually:
        # [Index N] Surname
        # [Index N+1] Given Names
        # [Index N+2] Middle Name

        s_parts = [p.strip() for p in s_anchor.split() if p.strip()]
        g_parts = [p.strip() for p in g_anchor.split() if p.strip()]

        for i in range(len(lines) - 2):
            line1 = lines[i]
            line2 = lines[i+1]
            line3 = lines[i+2]

            # Match Surname (line1)
            # Check if at least one part of the surname is in the line
            match1 = any(p in line1 for p in s_parts) if s_parts else False

            # Match Given Names (line2)
            # Strip punctuation like dots from the OCR line for better matching
            line2_clean = re.sub(r'[^A-Z\s]', '', line2)
            match2 = any(p in line2_clean for p in g_parts) if g_parts else False
            if match1 and match2:
                # Validate line 3 (potential Middle Name)
                # Should not be a label, should not have digits, should not be too short
                labels = [r'PLACE', r'BIRTH', r'SEX', r'NATIONALITY', r'DATE', r'PASSPORT', r'REPUBLIC', r'PHL']
                if any(re.search(l, line3) for l in labels):
                    continue
                if any(char.isdigit() for char in line3):
                    continue
                if len(line3.replace(' ', '')) < 2:
                    continue

                if debug: print(f"  DEBUG: Positional Fallback (Anchored) found at [{i}]: '{line1}', '{line2}' -> Middle: '{line3}'")
                return line3

        return ""

    def _extract_middle_name(self, raw_text_lines, debug=True):
        """Extracts middle name based on common labels using fuzzy matching."""
        if debug:
            print("\n--- DEBUG: OCR Raw Lines ---")
            for i, l in enumerate(raw_text_lines):
                print(f"  [{i}] {l}")

        # 'APELYIDO' alone refers to Surname in PHL passports.
        # We need the full 'PANGGITNANG APELYIDO' for middle name.
        # Added variants and common OCR errors.
        labels = [
            r'MIDDLE\s*NAME',
            r'MIDLE\s*NAME',
            r'PANGGITNANG\s*APELYIDO',
            r'PANGGITNANG',
            r'PANG-GITNANG',
            r'PANGITNANG',
            r'MOTHER\'S\s*MAIDEN\s*NAME',
            r'MAIDEN\s*NAME',
            r'MOTHER'
        ]

        # Exclusion labels to avoid capturing other field headers as names
        exclusions = labels + [r'PLACE', r'BIRTH', r'SURNAME', r'GIVEN', r'NAME', r'APELYIDO', r'PANGALAN', r'SEX', r'NATIONALITY']

        lines = [l.strip().upper() for l in raw_text_lines if l.strip()]

        for idx, line in enumerate(lines):
            for label_pattern in labels:
                match = re.search(label_pattern, line)
                if match:
                    # 1. Try same line first
                    # Strip all known labels from the line to find the actual value
                    remainder = line
                    for lp in labels:
                        remainder = re.sub(lp, '', remainder)

                    potential = remainder.strip()
                    # Clean up separators
                    potential = re.sub(r'^[/:.\-\s]+', '', potential)
                    potential = re.sub(r'[/:.\-\s]+$', '', potential)

                    if len(potential) >= 2:
                        # Clean digits (e.g., '0' to 'O')
                        potential_cleaned = self._clean_name_digits(potential)
                        if not any(c.isdigit() for c in potential_cleaned):
                            # Ensure it's not just another label
                            if not any(re.search(ex, potential_cleaned) for ex in exclusions):
                                if debug: print(f"  DEBUG: Found Middle Name (same line): '{potential_cleaned}'")
                                return potential_cleaned

                    # 2. Try to find the value in the next few lines
                    for offset in [1, 2, 3]:
                        if idx + offset < len(lines):
                            candidate = lines[idx + offset]
                            candidate_no_spaces = candidate.replace(' ', '')

                            # Skip common noise, single chars, and other field labels
                            if candidate_no_spaces in ['M', 'F', 'MALE', 'FEMALE', 'PHL', 'SEX'] or len(candidate_no_spaces) < 2:
                                continue

                            # Clean digits and check if it's then alpha-only
                            candidate_cleaned = self._clean_name_digits(candidate)
                            if any(char.isdigit() for char in candidate_cleaned):
                                continue

                            if not any(char.isalpha() for char in candidate_cleaned):
                                continue
                            if any(re.search(ex, candidate_cleaned) for ex in exclusions):
                                continue

                            if debug: print(f"  DEBUG: Found Middle Name (offset {offset}): '{candidate_cleaned}'")
                            return candidate_cleaned
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
        
        return {
            'surname': surname,
            'given_names': given_names,
            'middle_name': middle_name.upper().strip() if middle_name else "",
            'nationality': nat,
            'passport_number': getattr(fields, 'document_number', ''),
            'sex': getattr(fields, 'sex', ''),
            'date_of_birth': dob_iso,
            'passport_expiry': exp_iso,
            'issuer': getattr(fields, 'issuer', '')
        }

if __name__ == '__main__':
    print("OCR Engine ready.")
