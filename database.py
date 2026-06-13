import sqlite3

def init_db(db_path='crewlist.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Voyage Info Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voyage_info (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ship_name TEXT,
            arrival_departure TEXT,
            port_arrival_departure TEXT,
            date_arrival_departure TEXT,
            nationality_of_ship TEXT,
            last_port_of_call TEXT
        )
    ''')

    # Crew Members Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crew_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_number INTEGER UNIQUE,
            surname TEXT,
            given_names TEXT,
            rank TEXT,
            sex TEXT,
            nationality TEXT,
            date_of_birth TEXT,
            place_of_birth TEXT,
            passport_number TEXT,
            passport_expiry TEXT,
            seamans_book_number TEXT,
            seamans_book_expiry TEXT,
            joining_date TEXT,
            joining_place TEXT,
            ocr_confidence TEXT  -- JSON or comma-separated scores
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
