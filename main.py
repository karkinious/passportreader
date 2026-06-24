import os
import sys
import subprocess
import importlib.util
import re

def check_dependencies():
    """Checks if all requirements are installed, installs them if missing."""
    # List of (import_name, package_name)
    dependencies = [
        ("paddleocr", "paddleocr"),
        ("paddle", "paddlepaddle"),
        ("openpyxl", "openpyxl"),
        ("mrz", "mrz"),
        ("fitz", "pymupdf"),
        ("PIL", "pillow")
    ]

    missing = []
    for import_name, package_name in dependencies:
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Installing requirements from requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("\nDependencies installed successfully. Please restart the application.")
            sys.exit(0)
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)

def init_folders():
    """Creates default folders if they don't exist."""
    for folder in ['passports', 'export']:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created folder: {folder}")

# Run check before other imports that might fail
if __name__ == '__main__':
    check_dependencies()
    init_folders()

# These imports are here to avoid failing if dependencies are missing during the check above
from ocr_engine import OCREngine
from crew_manager import CrewManager
from database import init_db
import utils

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def open_file(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])

class CrewListApp:
    def __init__(self):
        init_db()
        self.cm = CrewManager()
        self.ocr = OCREngine()

    def _get_date_input(self, label, default=""):
        display_default = utils.format_date_display(default)
        while True:
            val = input(f"{label} [{display_default}]: ") or default
            parsed = utils.parse_date(val)
            if parsed:
                return parsed
            if not val and not default:
                return ""
            print("Invalid date format. Please use DDMMYYYY or DD-MM-YYYY.")

    def _get_sex_input(self, default=""):
        while True:
            val = input(f"Sex (M/F) [{default}]: ") or default
            validated = utils.validate_sex(val)
            if validated:
                return validated
            print("Invalid input. Please enter M or F.")

    def _get_nat_input(self, default=""):
        while True:
            val = input(f"Nationality (3-letter code) [{default}]: ") or default
            validated = utils.validate_nationality(val)
            if validated:
                return validated
            print("Invalid input. Please enter a 3-letter country code (e.g., GRC).")

    def main_menu(self):
        while True:
            clear_screen()
            print("=== IMO Crew List Generator ===")
            print("1. Set/Edit Voyage Information")
            print("2. Process Passport Scans Folder")
            print("3. Add Crew Member Manually")
            print("4. View/Edit/Remove Crew Members")
            print("5. Generate Excel Crew List")
            print("0. Exit")

            choice = input("\nSelect an option: ")

            if choice == '1': self.edit_voyage_info()
            elif choice == '2': self.process_folder()
            elif choice == '3': self.add_manual_crew()
            elif choice == '4': self.manage_crew()
            elif choice == '5': self.generate_excel()
            elif choice == '0': break

    def edit_voyage_info(self):
        info = self.cm.get_voyage_info()
        print("\n--- Voyage Information ---")
        data = {
            'ship_name': input(f"Ship Name [{info.get('ship_name', '')}]: ") or info.get('ship_name', ''),
            'arrival_departure': input(f"Arrival or Departure [{info.get('arrival_departure', 'Arrival')}]: ") or info.get('arrival_departure', 'Arrival'),
            'port_arrival_departure': input(f"Port of Arrival/Departure [{info.get('port_arrival_departure', '')}]: ") or info.get('port_arrival_departure', ''),
            'date_arrival_departure': input(f"Date of Arrival/Departure [{info.get('date_arrival_departure', '')}]: ") or info.get('date_arrival_departure', ''),
            'nationality_of_ship': input(f"Ships Nationality [{info.get('nationality_of_ship', '')}]: ") or info.get('nationality_of_ship', ''),
            'last_port_of_call': input(f"Last Port of Call [{info.get('last_port_of_call', '')}]: ") or info.get('last_port_of_call', '')
        }
        self.cm.save_voyage_info(data)
        input("\nSaved. Press Enter to continue...")

    def process_folder(self):
        default_folder = 'passports'
        folder = input(f"\nEnter path to folder with passport scans [{default_folder}]: ") or default_folder
        if not os.path.isdir(folder):
            print("Invalid directory.")
            input("Press Enter...")
            return

        files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf'))]
        if not files:
            print("No supported files found.")
            input("Press Enter...")
            return

        for filename in files:
            file_path = os.path.join(folder, filename)
            print(f"\nProcessing {filename}...")

            # Open file for user to see
            open_file(file_path)

            result = self.ocr.process_file(file_path)
            parsed = result['parsed_mrz'] if result else None
            conf = result['mrz_confidence'] if result else 0

            print(f"OCR Confidence: {conf:.2f}")

            # Form data
            match = re.match(r'^(\d+)', filename)
            if match:
                crew_num = match.group(1)
            else:
                crew_num = self.cm.get_next_crew_number()

            pob_default = parsed.get('place_of_birth', '') if parsed else ''

            data = {
                'crew_number': input(f"Crew Number [{crew_num}]: ") or crew_num,
                'surname': self._verify("Surname", parsed.get('surname', '') if parsed else ''),
                'given_names': self._verify("Given Names", parsed.get('given_names', '') if parsed else ''),
                'rank': input("Rank: "),
                'sex': self._get_sex_input(parsed.get('sex', '') if parsed else ''),
                'nationality': self._get_nat_input(parsed.get('nationality', '') if parsed else ''),
                'date_of_birth': self._get_date_input("Date of Birth", parsed.get('date_of_birth', '') if parsed else ''),
                'place_of_birth': input(f"Place of Birth [{pob_default}]: ") or pob_default,
                'passport_number': self._verify("Passport No", parsed.get('passport_number', '') if parsed else ''),
                'passport_expiry': self._get_date_input("Passport Expiry", parsed.get('passport_expiry', '') if parsed else ''),
                'seamans_book_number': input("Seaman's Book No: "),
                'seamans_book_expiry': self._get_date_input("Seaman's Book Expiry"),
                'joining_date': self._get_date_input("Sign-on Date"),
                'joining_place': input("Sign-on Port: "),
                'ocr_confidence': str(conf)
            }
            self.cm.add_crew_member(data)
            print(f"Added {data['surname']} to database.")

        input("\nAll files processed. Press Enter...")

    def _verify(self, label, value):
        val = input(f"{label} [{value}]: ")
        return val if val else value

    def add_manual_crew(self):
        crew_num = self.cm.get_next_crew_number()
        data = {
            'crew_number': input(f"Crew Number [{crew_num}]: ") or crew_num,
            'surname': input("Surname: "),
            'given_names': input("Given Names: "),
            'rank': input("Rank: "),
            'sex': self._get_sex_input(),
            'nationality': self._get_nat_input(),
            'date_of_birth': self._get_date_input("Date of Birth"),
            'place_of_birth': input("Place of Birth: "),
            'passport_number': input("Passport Number: "),
            'passport_expiry': self._get_date_input("Passport Expiry"),
            'seamans_book_number': input("Seaman's Book No: "),
            'seamans_book_expiry': self._get_date_input("Seaman's Book Expiry"),
            'joining_date': self._get_date_input("Sign-on Date"),
            'joining_place': input("Sign-on Port: "),
            'ocr_confidence': "Manual"
        }
        self.cm.add_crew_member(data)
        input("\nAdded. Press Enter...")

    def manage_crew(self):
        while True:
            clear_screen()
            crew = self.cm.get_all_crew()
            print(f"{'No.':<4} {'Name':<25} {'Rank':<15} {'Passport':<15}")
            print("-" * 60)
            for m in crew:
                name = f"{m['surname']}, {m['given_names']}"[:24]
                print(f"{m['crew_number']:<4} {name:<25} {m['rank']:<15} {m['passport_number']:<15}")

            print("\nOptions: (e) Edit [No.], (r) Remove [No.], (b) Back")
            choice = input("Select: ").lower()
            if choice == 'b': break

            try:
                parts = choice.split()
                cmd = parts[0]
                num = int(parts[1])
                member = next((m for m in crew if m['crew_number'] == num), None)

                if not member:
                    print("Member not found.")
                    input()
                    continue

                if cmd == 'e':
                    self.edit_member(member)
                elif cmd == 'r':
                    self.cm.remove_crew_member(member['id'])
            except:
                continue

    def edit_member(self, m):
        print(f"\nEditing {m['surname']}")
        data = {
            'crew_number': input(f"Crew Number [{m['crew_number']}]: ") or m['crew_number'],
            'surname': input(f"Surname [{m['surname']}]: ") or m['surname'],
            'given_names': input(f"Given Names [{m['given_names']}]: ") or m['given_names'],
            'rank': input(f"Rank [{m['rank']}]: ") or m['rank'],
            'sex': self._get_sex_input(m['sex']),
            'nationality': self._get_nat_input(m['nationality']),
            'date_of_birth': self._get_date_input("DOB", m['date_of_birth']),
            'place_of_birth': input(f"POB [{m['place_of_birth']}]: ") or m['place_of_birth'],
            'passport_number': input(f"Passport [{m['passport_number']}]: ") or m['passport_number'],
            'passport_expiry': self._get_date_input("Passport Expiry", m['passport_expiry']),
            'seamans_book_number': input(f"S-Book [{m['seamans_book_number']}]: ") or m['seamans_book_number'],
            'seamans_book_expiry': self._get_date_input("S-Expiry", m['seamans_book_expiry']),
            'joining_date': self._get_date_input("Joining Date", m['joining_date']),
            'joining_place': input(f"Joining Place [{m['joining_place']}]: ") or m['joining_place']
        }
        self.cm.update_crew_member(m['id'], data)

    def generate_excel(self):
        from excel_generator import ExcelGenerator
        info = self.cm.get_voyage_info()
        crew = self.cm.get_all_crew()

        if not info:
            print("Please fill Voyage Info first.")
            input()
            return

        gen = ExcelGenerator()
        filename = gen.generate(info, crew)
        print(f"\nExcel file generated: {filename}")
        input("Press Enter...")

if __name__ == '__main__':
    # check_dependencies() is already called above
    app = CrewListApp()
    app.main_menu()
