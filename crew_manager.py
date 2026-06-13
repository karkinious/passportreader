import sqlite3
import json

class CrewManager:
    def __init__(self, db_path='crewlist.db'):
        self.db_path = db_path

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def get_all_crew(self):
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM crew_members ORDER BY crew_number')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_crew_member(self, data):
        """Adds a crew member with insert-and-shift logic if needed."""
        new_num = int(data.get('crew_number'))

        conn = self.get_conn()
        cursor = conn.cursor()

        # Check if crew_number already exists
        cursor.execute('SELECT id FROM crew_members WHERE crew_number = ?', (new_num,))
        if cursor.fetchone():
            # Shift existing ones to avoid UNIQUE constraint violation
            # Since SQLite UPDATE ORDER BY is often disabled, we'll do it by updating them one by one or using a trick.
            # Trick: temporary negative numbers
            cursor.execute('UPDATE crew_members SET crew_number = -crew_number WHERE crew_number >= ?', (new_num,))
            cursor.execute('UPDATE crew_members SET crew_number = (-crew_number) + 1 WHERE crew_number < 0')

        fields = [
            'crew_number', 'surname', 'given_names', 'rank', 'sex', 'nationality',
            'date_of_birth', 'place_of_birth', 'passport_number', 'passport_expiry',
            'seamans_book_number', 'seamans_book_expiry', 'joining_date', 'joining_place', 'ocr_confidence'
        ]

        placeholders = ', '.join(['?'] * len(fields))
        values = [data.get(f) for f in fields]

        cursor.execute(f'INSERT INTO crew_members ({", ".join(fields)}) VALUES ({placeholders})', values)

        conn.commit()
        conn.close()

    def update_crew_member(self, member_id, data):
        """Updates an existing crew member's details."""
        old_conn = self.get_conn()
        old_cursor = old_conn.cursor()
        old_cursor.execute('SELECT crew_number FROM crew_members WHERE id = ?', (member_id,))
        old_num = old_cursor.fetchone()[0]
        old_conn.close()

        new_num = int(data.get('crew_number'))

        conn = self.get_conn()
        cursor = conn.cursor()

        if new_num != old_num:
            # Handle shifting if number changed
            if new_num < old_num:
                # Shifting down: increment intermediate numbers
                cursor.execute('UPDATE crew_members SET crew_number = -crew_number WHERE crew_number >= ? AND crew_number < ?', (new_num, old_num))
                cursor.execute('UPDATE crew_members SET crew_number = (-crew_number) + 1 WHERE crew_number < 0')
            else:
                # Shifting up: decrement intermediate numbers
                cursor.execute('UPDATE crew_members SET crew_number = -crew_number WHERE crew_number > ? AND crew_number <= ?', (old_num, new_num))
                cursor.execute('UPDATE crew_members SET crew_number = (-crew_number) - 1 WHERE crew_number < 0')

        fields = [
            'crew_number', 'surname', 'given_names', 'rank', 'sex', 'nationality',
            'date_of_birth', 'place_of_birth', 'passport_number', 'passport_expiry',
            'seamans_book_number', 'seamans_book_expiry', 'joining_date', 'joining_place'
        ]

        set_clause = ', '.join([f'{f} = ?' for f in fields])
        values = [data.get(f) for f in fields] + [member_id]

        cursor.execute(f'UPDATE crew_members SET {set_clause} WHERE id = ?', values)

        conn.commit()
        conn.close()

    def remove_crew_member(self, member_id):
        conn = self.get_conn()
        cursor = conn.cursor()

        # Get the number before deleting to shift back
        cursor.execute('SELECT crew_number FROM crew_members WHERE id = ?', (member_id,))
        row = cursor.fetchone()
        if row:
            num = row[0]
            cursor.execute('DELETE FROM crew_members WHERE id = ?', (member_id,))
            cursor.execute('UPDATE crew_members SET crew_number = crew_number - 1 WHERE crew_number > ?', (num,))

        conn.commit()
        conn.close()

    def get_next_crew_number(self):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(crew_number) FROM crew_members')
        max_num = cursor.fetchone()[0]
        conn.close()
        return (max_num + 1) if max_num else 1

    def save_voyage_info(self, data):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO voyage_info (id, ship_name, arrival_departure, port_arrival_departure, date_arrival_departure, nationality_of_ship, last_port_of_call) VALUES (1, ?, ?, ?, ?, ?, ?)',
                       (data.get('ship_name'), data.get('arrival_departure'), data.get('port_arrival_departure'), data.get('date_arrival_departure'), data.get('nationality_of_ship'), data.get('last_port_of_call')))
        conn.commit()
        conn.close()

    def get_voyage_info(self):
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM voyage_info WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else {}

if __name__ == '__main__':
    print("Crew Manager ready.")
