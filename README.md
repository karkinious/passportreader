# IMO Crew List Generator

A local, offline command-line application for generating IMO Crew Lists from passport scans. This tool is designed for use on ships to automate the extraction of crew data and ensure accurate Excel reporting.

## Features

- **Offline OCR**: Uses PaddleOCR to extract data from passport images and PDFs without requiring an internet connection.
- **MRZ Parsing & Fuzzy Correction**: Automatically parses the Machine Readable Zone (MRZ). Includes fuzzy logic to correct common OCR character substitutions (e.g., 'O' for '0' in dates) before parsing.
- **Strict Data Validation**: Enforces standardized date formats (DDMMYYYY/ISO), Sex (M/F), and Nationality (ISO 3-letter codes). Supports "N/A" for expiry dates where applicable.
- **Manual Verification**: Forces a manual review of OCR results against the original scan for 100% accuracy.
- **Auto-Numbering with Insert-and-Shift**: Automatically generates crew numbers. If you insert a member at an existing position, all subsequent members are automatically renumbered to maintain a unique sequence.
- **Excel Generation**: Populates a standardized `TEMPLATE.xlsx` starting from row 9, with automatic cell unmerging and re-merging to ensure data (like Birth Date and Place) fits the official layout perfectly.
- **Persistence**: Saves all voyage and crew data in a local SQLite database using ISO date standards.

## Prerequisites

- **Python 3.8+**
- **MacOS (Recommended)** or **Windows**
- **Tesseract (Optional)**: PaddleOCR comes with its own engines, but ensure you have `pip` installed to manage dependencies.

## Installation & Setup

1. **Clone the repository** (or copy the files to your local machine).
2. **Ensure Python 3.8+ is installed**.
3. **Run the application**:
   ```bash
   python main.py
   ```
   *Note: On the first run, the app will automatically:*
   - *Check for and install required Python dependencies from `requirements.txt`.*
   - *Create default folders: `passports/` (for your scans) and `export/` (for generated Excel files).*
   - *Download necessary local OCR model files (approx. 20-50MB).*

## Usage

### Main Menu Options

1. **Set/Edit Voyage Information**: Enter ship details, port of arrival/departure, dates, and nationality. This info appears in the header of the Excel file.
2. **Process Passport Scans Folder**:
   - Point the app to a folder containing JPG, PNG, or PDF scans.
   - The app will OCR each file and **open the image** using your system's default viewer.
   - You will be prompted to confirm or edit each extracted field.
   - Fields not in the MRZ (like Rank or Seaman's Book) will be requested manually.
3. **Add Crew Member**:
   - **Insert Mode**: Add a new member and shift existing ones down.
   - **Replace Mode**: Overwrite an existing entry with new data.
   - Support for both **From Scan (OCR)** with file selection and **Manual Entry**.
4. **View/Edit/Remove Crew Members**:
   - Lists all current members with explicit UI feedback and confirmation prompts.
   - Use `e [No.]` to edit a member (e.g., `e 5`).
   - Use `r [No.]` to remove a member with automatic re-ordering.
5. **Generate Excel Crew List**: Creates an Excel file named `CrewList_[ShipName]_[Arrival/Departure].xlsx`.

## Project Structure

- `main.py`: The entry point and CLI logic with input validation.
- `ocr_engine.py`: Handles PaddleOCR processing and fuzzy MRZ parsing.
- `crew_manager.py`: Manages the SQLite database and crew numbering logic.
- `excel_generator.py`: Maps data to the `TEMPLATE.xlsx` file with formatted output.
- `utils.py`: Standardized parsing and validation utilities for dates and fields.
- `database.py`: Database schema initialization.
- `TEMPLATE.xlsx`: The base Excel template used for generation.

## Crew Numbering Logic

The application maintains a strict sequence.
- If you have members 1, 2, and 3, adding a new member will default to 4.
- If you manually set a new member to number **2**, the existing member 2 becomes 3, and member 3 becomes 4.
- Removing member 2 will cause members 3 and 4 to shift back to 2 and 3.

## Troubleshooting

- **OCR Accuracy**: Ensure scans are flat and well-lit. If the MRZ is not detected, the app will still allow you to enter data manually.
- **File Opening**: On some Linux systems, ensure `xdg-utils` is installed for the "Open image" feature to work. On Mac/Windows, it uses native commands.
