from datetime import datetime
import re

def parse_date(date_str):
    """
    Parses various date formats into ISO YYYY-MM-DD.
    Supported: DDMMYYYY, DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD, or "N/A"
    """
    if not date_str:
        return None

    if date_str.strip().upper() in ['N/A', 'PERMANENT']:
        return date_str.strip().upper()
    
    # Remove separators for easier parsing if it matches DDMMYYYY
    clean_date = re.sub(r'[-/.\s]', '', date_str)
    
    formats_to_try = [
        '%d%m%Y',   # 13062026
        '%Y-%m-%d', # 2026-06-13
        '%d-%m-%Y', # 13-06-2026
        '%d/%m/%Y', # 13/06/2026
        '%y%m%d',   # 260613 (MRZ format)
    ]
    
    # Try the clean version first for fixed-length numeric formats
    if len(clean_date) == 8:
        try:
            return datetime.strptime(clean_date, '%d%m%Y').strftime('%Y-%m-%d')
        except ValueError:
            pass
    elif len(clean_date) == 6:
        try:
            # Note: %y is sensitive to century, usually 00-68 is 2000-2068
            return datetime.strptime(clean_date, '%y%m%d').strftime('%Y-%m-%d')
        except ValueError:
            pass

    # Try original string with various separators
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
            
    return None

def format_date_display(iso_date):
    """Converts YYYY-MM-DD to DD-MM-YYYY for display."""
    if not iso_date:
        return ""
    try:
        return datetime.strptime(iso_date, '%Y-%m-%d').strftime('%d-%m-%Y')
    except ValueError:
        return iso_date

def validate_sex(sex_str):
    """Validates and standardizes sex to M or F."""
    if not sex_str:
        return ""
    sex = sex_str.strip().upper()
    if sex in ['M', 'F', 'MALE', 'FEMALE']:
        return sex[0]
    return None

def validate_nationality(nat_str):
    """Ensures nationality is a 3-letter uppercase string."""
    if not nat_str:
        return ""
    nat = nat_str.strip().upper()
    if nat in ['PLV', 'PLB', 'PH1', 'P1HL']:
        nat = 'PHL'
    if len(nat) == 3 and nat.isalpha():
        return nat
    return None
