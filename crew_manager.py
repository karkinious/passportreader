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
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN TRANSACTION')

            # Check if crew_number already exists
            cursor.execute('SELECT id FROM crew_members WHERE crew_number = ?', (new_num,))
            if cursor.fetchone():
                # Shift existing ones to avoid UNIQUE constraint violation
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
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def update_crew_member(self, member_id, data):
        """Updates an existing crew member's details."""
        conn = self.get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN TRANSACTION')

            # Get old number
            cursor.execute('SELECT crew_number FROM crew_members WHERE id = ?', (member_id,))
            row = cursor.fetchone()
            if not row:
                return
            old_num = row[0]
            new_num = int(data.get('crew_number'))

            if new_num != old_num:
                # Move current member to a temporary safe number to avoid UNIQUE constraints during shifting
                cursor.execute('UPDATE crew_members SET crew_number = -99999 WHERE id = ?', (member_id,))

                if new_num < old_num:
                    # Shifting down: increment intermediate numbers (e.g., moving 5 to 2: 2,3,4 become 3,4,5)
                    cursor.execute('UPDATE crew_members SET crew_number = -crew_number WHERE crew_number >= ? AND crew_number < ?', (new_num, old_num))
                    cursor.execute('UPDATE crew_members SET crew_number = (-crew_number) + 1 WHERE crew_number < 0')
                else:
                    # Shifting up: decrement intermediate numbers (e.g., moving 2 to 5: 3,4,5 become 2,3,4)
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
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def remove_crew_member(self, member_id):
        conn = self.get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN TRANSACTION')

            # Get the number before deleting to shift back
            cursor.execute('SELECT crew_number FROM crew_members WHERE id = ?', (member_id,))
            row = cursor.fetchone()
            if row:
                num = row[0]
                cursor.execute('DELETE FROM crew_members WHERE id = ?', (member_id,))
                # Shift back using temporary negative numbers to avoid UNIQUE constraint violations
                cursor.execute('UPDATE crew_members SET crew_number = -crew_number WHERE crew_number > ?', (num,))
                cursor.execute('UPDATE crew_members SET crew_number = (-crew_number) - 1 WHERE crew_number < 0')

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
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

    def get_member_by_number(self, crew_number):
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM crew_members WHERE crew_number = ?', (crew_number,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

if __name__ == '__main__':
    print("Crew Manager ready.")
