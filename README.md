# IMO Crew List Generator

A local, offline command-line application for generating IMO Crew Lists from passport scans. This tool is designed for use on ships to automate the extraction of crew data and ensure accurate Excel reporting.

## Features

- **Offline OCR**: Uses PaddleOCR to extract data from passport images and PDFs without requiring an internet connection.
- **MRZ Parsing**: Automatically parses the Machine Readable Zone (MRZ) of passports for names, passport numbers, nationality, and expiry dates.
- **Manual Verification**: Forces a manual review of OCR results against the original scan for 100% accuracy.
- **Auto-Numbering with Insert-and-Shift**: Automatically generates crew numbers. If you insert a member at an existing position, all subsequent members are automatically renumbered.
- **Excel Generation**: Populates a standardized `TEMPLATE.xlsx` to generate official IMO Crew Lists.
- **Persistence**: Saves all voyage and crew data in a local SQLite database.

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
   *Note: On the first run, the app will automatically check for and install required Python dependencies from `requirements.txt`. It will also download the necessary local OCR model files (approx. 20-50MB).*

## Usage

### Main Menu Options

1. **Set/Edit Voyage Information**: Enter ship details, port of arrival/departure, dates, and nationality. This info appears in the header of the Excel file.
2. **Process Passport Scans Folder**:
   - Point the app to a folder containing JPG, PNG, or PDF scans.
   - The app will OCR each file and **open the image** using your system's default viewer.
   - You will be prompted to confirm or edit each extracted field.
   - Fields not in the MRZ (like Rank or Seaman's Book) will be requested manually.
3. **Add Crew Member Manually**: Add a member without a scan.
4. **View/Edit/Remove Crew Members**:
   - Lists all current members.
   - Use `e [No.]` to edit a member (e.g., `e 5`).
   - Use `r [No.]` to remove a member.
5. **Generate Excel Crew List**: Creates an Excel file named `CrewList_[ShipName]_[Arrival/Departure].xlsx`.

## Project Structure

- `main.py`: The entry point and CLI logic.
- `ocr_engine.py`: Handles PaddleOCR processing and MRZ parsing.
- `crew_manager.py`: Manages the SQLite database and crew numbering logic.
- `excel_generator.py`: Maps data to the `TEMPLATE.xlsx` file.
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
