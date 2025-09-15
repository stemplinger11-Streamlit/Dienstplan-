"""
Dienstplan+ Cloud v3.0 - Database Manager
Vollständige SQLite-Datenbankschicht mit allen CRUD-Operationen
"""
import sqlite3
import hashlib
import json
import streamlit as st
from datetime import datetime, timedelta
from app.config.constants import WEEKLY_SLOTS, DEFAULT_SMS_TEMPLATES, DEFAULT_EMAIL_TEMPLATES, DEFAULT_SHIFT_INFO, DEFAULT_RESCUE_CHAIN

class DatabaseManager:
    """Zentrale Datenbankklasse für alle Operationen"""
    
    def __init__(self):
        self.init_database()
    
    def get_connection(self):
        """Sichere SQLite-Verbindung mit Thread-Unterstützung"""
        return sqlite3.connect('dienstplan.db', check_same_thread=False)
    
    def init_database(self):
        """Erstelle alle Tabellen und initialisiere Standarddaten"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Aktiviere Foreign Key Constraints
        cursor.execute('PRAGMA foreign_keys=on')
        
        # Users Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                is_initial_admin BOOLEAN DEFAULT 0,
                whatsapp_opt_in BOOLEAN DEFAULT 0,
                sms_opt_in BOOLEAN DEFAULT 1,
                email_opt_in BOOLEAN DEFAULT 1,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Bookings Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(slot_id, booking_date)
            )
        ''')
        
        # Audit Log Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Reminder Templates Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminder_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                timing TEXT NOT NULL,
                sms_template TEXT,
                whatsapp_template TEXT,
                email_template TEXT,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # E-Mail Templates Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                template_type TEXT NOT NULL,
                subject_template TEXT,
                body_template TEXT,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Notifications Sent Tabelle für De-Duplikation
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                notification_date DATE NOT NULL,
                notification_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slot_id, notification_date, notification_type)
            )
        ''')
        
        # Favorites Tabelle für Watchlist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, slot_id, date)
            )
        ''')
        
        # Info Pages Tabelle für editierbare Inhalte
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS info_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users (id)
            )
        ''')
        
        # Backup Log Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_date DATE NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                details TEXT
            )
        ''')
        
        conn.commit()
        
        # Standarddaten erstellen
        self._create_initial_admin()
        self._create_default_templates()
        self._create_default_info_pages()
        
        conn.close()
    
    def _create_initial_admin(self):
        """Erstelle Initial-Admin aus Secrets"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Prüfe ob bereits ein Initial-Admin existiert
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_initial_admin = 1')
        if cursor.fetchone()[0] > 0:
            conn.close()
            return
        
        try:
            admin_email = st.secrets.get("ADMIN_EMAIL", "")
            admin_password = st.secrets.get("ADMIN_PASSWORD", "")
            
            if admin_email and admin_password:
                password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
                
                cursor.execute('''
                    INSERT INTO users (email, phone, name, password_hash, role, is_initial_admin, sms_opt_in)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (admin_email, "+49151999999999", "Initial Admin", password_hash, "admin", 1, 1))
                
                conn.commit()
                
                # Log erstellen
                user_id = cursor.lastrowid
                self.log_action(user_id, 'admin_created', 'Initial admin created from secrets')
                
        except Exception:
            pass  # Secrets nicht verfügbar
        
        conn.close()
    
    def _create_default_templates(self):
        """Erstelle Standard-Templates"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # SMS Templates
        cursor.execute('SELECT COUNT(*) FROM reminder_templates')
        if cursor.fetchone()[0] == 0:
            for timing, template in DEFAULT_SMS_TEMPLATES.items():
                cursor.execute('''
                    INSERT INTO reminder_templates (name, timing, sms_template, whatsapp_template, email_template)
                    VALUES (?, ?, ?, ?, ?)
                ''', (timing.replace('_', ' ').title(), timing, template, template, ''))
        
        # E-Mail Templates
        cursor.execute('SELECT COUNT(*) FROM email_templates')
        if cursor.fetchone()[0] == 0:
            for template_type, data in DEFAULT_EMAIL_TEMPLATES.items():
                cursor.execute('''
                    INSERT INTO email_templates (name, template_type, subject_template, body_template)
                    VALUES (?, ?, ?, ?)
                ''', (template_type.replace('_', ' ').title(), template_type, data['subject'], data['body']))
        
        conn.commit()
        conn.close()
    
    def _create_default_info_pages(self):
        """Erstelle Standard-Info-Seiten"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM info_pages')
        if cursor.fetchone()[0] == 0:
            # Schicht-Info Seite
            cursor.execute('''
                INSERT INTO info_pages (page_key, title, content)
                VALUES (?, ?, ?)
            ''', ('schicht_info', 'Schicht-Informationen', DEFAULT_SHIFT_INFO))
            
            # Rettungskette Seite
            cursor.execute('''
                INSERT INTO info_pages (page_key, title, content)
                VALUES (?, ?, ?)
            ''', ('rettungskette', 'Rettungskette Hallenbad', DEFAULT_RESCUE_CHAIN))
        
        conn.commit()
        conn.close()
    
    # CRUD Operationen für Users
    def create_user(self, email, phone, name, password, role='user'):
        """Erstelle neuen Benutzer"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        try:
            cursor.execute('''
                INSERT INTO users (email, phone, name, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (email, phone, name, password_hash, role))
            
            user_id = cursor.lastrowid
            conn.commit()
            
            # Log erstellen
            self.log_action(user_id, 'user_created', f'User {name} registered')
            
            return user_id
            
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    def authenticate_user(self, email, password):
        """Authentifiziere Benutzer"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin, active
            FROM users 
            WHERE email = ? AND password_hash = ? AND active = 1
        ''', (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Admin-Whitelist prüfen
            admin_emails = st.secrets.get("ADMIN_EMAILS", [])
            if admin_emails and isinstance(admin_emails, list):
                if user[4] == 'admin' and email not in admin_emails:
                    # Admin-Rolle entziehen
                    self.update_user_role(user[0], 'user')
                    user = list(user)
                    user[4] = 'user'
            
            return {
                'id': user[0],
                'email': user[1],
                'phone': user[2],
                'name': user[3],
                'role': user[4],
                'sms_opt_in': user[5],
                'whatsapp_opt_in': user[6],
                'email_opt_in': user[7],
                'is_initial_admin': user[8],
                'active': user[9]
            }
        
        return None
    
    def get_user_by_id(self, user_id):
        """Lade Benutzer nach ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin, active
            FROM users WHERE id = ? AND active = 1
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user[0],
                'email': user[1],
                'phone': user[2],
                'name': user[3],
                'role': user[4],
                'sms_opt_in': user[5],
                'whatsapp_opt_in': user[6],
                'email_opt_in': user[7],
                'is_initial_admin': user[8],
                'active': user[9]
            }
        
        return None
    
    def get_all_users(self):
        """Alle aktiven Benutzer laden"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin, created_at, active
            FROM users WHERE active = 1 ORDER BY name
        ''')
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0],
                'email': row[1],
                'phone': row[2],
                'name': row[3],
                'role': row[4],
                'sms_opt_in': row[5],
                'whatsapp_opt_in': row[6],
                'email_opt_in': row[7],
                'is_initial_admin': row[8],
                'created_at': row[9],
                'active': row[10]
            })
        
        conn.close()
        return users
    
    def update_user_profile(self, user_id, name, phone, sms_opt_in):
        """Aktualisiere Benutzerprofil"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users SET name = ?, phone = ?, sms_opt_in = ?
                WHERE id = ?
            ''', (name, phone, sms_opt_in, user_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                self.log_action(user_id, 'profile_updated', 'User updated profile')
            
            return success
            
        except Exception:
            return False
        finally:
            conn.close()
    
    def update_user_password(self, user_id, new_password):
        """Ändere Benutzer-Passwort"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = hashlib.sha256(new_password.encode()).hexdigest()
            
            cursor.execute('''
                UPDATE users SET password_hash = ?
                WHERE id = ?
            ''', (password_hash, user_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                self.log_action(user_id, 'password_changed', 'User changed password')
            
            return success
            
        except Exception:
            return False
        finally:
            conn.close()
    
    def update_user_role(self, user_id, new_role):
        """Ändere Benutzer-Rolle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users SET role = ?
                WHERE id = ?
            ''', (new_role, user_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                self.log_action(user_id, 'role_changed', f'Role changed to {new_role}')
            
            return success
            
        except Exception:
            return False
        finally:
            conn.close()
    
    # Booking Operationen
    def create_booking(self, user_id, slot_id, date_str):
        """Erstelle neue Buchung mit Validierung"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Prüfe auf Kollision
            cursor.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE slot_id = ? AND booking_date = ?
            ''', (slot_id, date_str))
            
            if cursor.fetchone()[0] > 0:
                return False, "Slot bereits belegt"
            
            # Buchung erstellen
            cursor.execute('''
                INSERT INTO bookings (user_id, slot_id, booking_date)
                VALUES (?, ?, ?)
            ''', (user_id, slot_id, date_str))
            
            booking_id = cursor.lastrowid
            conn.commit()
            
            # Log erstellen
            self.log_action(user_id, 'booking_created', f'Booked slot {slot_id} for {date_str}')
            
            return True, booking_id
            
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
    
    def cancel_booking(self, booking_id, user_id=None):
        """Storniere Buchung"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if user_id:
                # Nur eigene Buchungen stornieren (für normale User)
                cursor.execute('''
                    DELETE FROM bookings 
                    WHERE id = ? AND user_id = ?
                ''', (booking_id, user_id))
            else:
                # Admin kann alle Buchungen stornieren
                cursor.execute('''
                    DELETE FROM bookings 
                    WHERE id = ?
                ''', (booking_id,))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success and user_id:
                self.log_action(user_id, 'booking_cancelled', f'Cancelled booking {booking_id}')
            
            return success
            
        except Exception:
            return False
        finally:
            conn.close()
    
    def get_user_bookings(self, user_id):
        """Lade alle Buchungen eines Benutzers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.slot_id, b.booking_date, b.status, b.created_at
            FROM bookings b
            WHERE b.user_id = ?
            ORDER BY b.booking_date DESC
        ''', (user_id,))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0],
                'slot_id': row[1],
                'date': row[2],
                'status': row[3],
                'created_at': row[4]
            })
        
        conn.close()
        return bookings
    
    def get_all_bookings(self):
        """Lade alle Buchungen mit Benutzerinformationen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.user_id, b.slot_id, b.booking_date, b.status, b.created_at, u.name, u.email
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            ORDER BY b.booking_date DESC
        ''')
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0],
                'user_id': row[1],
                'slot_id': row[2],
                'date': row[3],
                'status': row[4],
                'created_at': row[5],
                'user_name': row[6],
                'user_email': row[7]
            })
        
        conn.close()
        return bookings
    
    def get_bookings_for_date_slot(self, slot_id, date_str):
        """Lade Buchungen für spezifischen Slot und Datum"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.user_id, b.slot_id, b.booking_date, b.status, b.created_at, u.name, u.email
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.slot_id = ? AND b.booking_date = ?
        ''', (slot_id, date_str))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0],
                'user_id': row[1],
                'slot_id': row[2],
                'date': row[3],
                'status': row[4],
                'created_at': row[5],
                'user_name': row[6],
                'user_email': row[7]
            })
        
        conn.close()
        return bookings
    
    def _matches_slot_day(self, date_obj, slot_day):
        """Prüfe ob Datum zum Slot-Wochentag passt"""
        day_mapping = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        return date_obj.weekday() == day_mapping.get(slot_day, -1)
    
    # Favorites/Watchlist Operationen
    def add_favorite(self, user_id, slot_id, date_str):
        """Termin zur Watchlist hinzufügen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO favorites (user_id, slot_id, date)
                VALUES (?, ?, ?)
            ''', (user_id, slot_id, date_str))
            
            conn.commit()
            self.log_action(user_id, 'favorite_added', f'Added favorite: slot {slot_id}, date {date_str}')
            return True
            
        except sqlite3.IntegrityError:
            # Bereits in Favorites
            return False
        finally:
            conn.close()
    
    def remove_favorite(self, user_id, slot_id, date_str):
        """Termin aus Watchlist entfernen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM favorites 
                WHERE user_id = ? AND slot_id = ? AND date = ?
            ''', (user_id, slot_id, date_str))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                self.log_action(user_id, 'favorite_removed', f'Removed favorite: slot {slot_id}, date {date_str}')
            
            return success
            
        except Exception:
            return False
        finally:
            conn.close()
    
    def get_user_favorites(self, user_id):
        """Lade Watchlist eines Benutzers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, slot_id, date, created_at
            FROM favorites
            WHERE user_id = ?
            ORDER BY date ASC
        ''', (user_id,))
        
        favorites = []
        for row in cursor.fetchall():
            favorites.append({
                'id': row[0],
                'slot_id': row[1],
                'date': row[2],
                'created_at': row[3]
            })
        
        conn.close()
        return favorites
    
    def is_favorite(self, user_id, slot_id, date_str):
        """Prüfe ob Termin in Watchlist ist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM favorites 
            WHERE user_id = ? AND slot_id = ? AND date = ?
        ''', (user_id, slot_id, date_str))
        
        result = cursor.fetchone()[0] > 0
        conn.close()
        return result
    
    # 7-Tage-Warnungen
    def check_7_day_warnings(self):
        """Prüfe auf unbelegte Schichten in 7 Tagen mit De-Duplikation"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Datum in 7 Tagen
        warn_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        warn_date_obj = datetime.strptime(warn_date, '%Y-%m-%d')
        
        warnings = []
        
        for slot in WEEKLY_SLOTS:
            # Prüfe ob Datum zum Wochentag passt
            if not self._matches_slot_day(warn_date_obj, slot['day']):
                continue
            
            # Prüfe ob Slot belegt ist
            cursor.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE slot_id = ? AND booking_date = ?
            ''', (slot['id'], warn_date))
            
            if cursor.fetchone()[0] == 0:  # Unbelegt
                # Prüfe De-Duplikation
                cursor.execute('''
                    SELECT COUNT(*) FROM notifications_sent 
                    WHERE slot_id = ? AND notification_date = ? AND notification_type = '7_day_warning'
                ''', (slot['id'], warn_date))
                
                if cursor.fetchone()[0] == 0:  # Noch nicht gesendet
                    warnings.append({
                        'slot_id': slot['id'],
                        'date': warn_date,
                        'slot_name': f"{slot['day_name']} {slot['start_time']}-{slot['end_time']}"
                    })
                    
                    # Als gesendet markieren
                    cursor.execute('''
                        INSERT INTO notifications_sent (slot_id, notification_date, notification_type)
                        VALUES (?, ?, '7_day_warning')
                    ''', (slot['id'], warn_date))
        
        conn.commit()
        conn.close()
        return warnings
    
    # Backup/Restore
    def create_backup(self):
        """Erstelle vollständiges JSON-Backup"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        backup_data = {
            'created_at': datetime.now().isoformat(),
            'version': '3.0',
            'tables': {}
        }
        
        # Alle Tabellen sichern
        tables = [
            'users', 'bookings', 'audit_log', 'reminder_templates', 
            'email_templates', 'notifications_sent', 'favorites', 
            'info_pages', 'backup_log'
        ]
        
        for table in tables:
            cursor.execute(f'SELECT * FROM {table}')
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            backup_data['tables'][table] = {
                'columns': columns,
                'rows': rows
            }
        
        conn.close()
        return json.dumps(backup_data, indent=2, default=str)
    
    def restore_backup(self, backup_json):
        """Stelle Backup wieder her (VORSICHT: Überschreibt Daten!)"""
        try:
            backup_data = json.loads(backup_json)
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Foreign Keys temporär deaktivieren
            cursor.execute('PRAGMA foreign_keys=off')
            
            # Alle Tabellen leeren (außer aktueller Session)
            tables = backup_data['tables'].keys()
            for table in tables:
                cursor.execute(f'DELETE FROM {table}')
            
            # Daten wiederherstellen
            for table, data in backup_data['tables'].items():
                if data['rows']:
                    columns = data['columns']
                    placeholders = ','.join(['?' for _ in columns])
                    
                    cursor.executemany(
                        f'INSERT INTO {table} ({",".join(columns)}) VALUES ({placeholders})',
                        data['rows']
                    )
            
            # Foreign Keys wieder aktivieren
            cursor.execute('PRAGMA foreign_keys=on')
            conn.commit()
            
            # Restore loggen
            self.log_action(None, 'backup_restored', f'Restored backup from {backup_data["created_at"]}')
            
            conn.close()
            return True, "Backup erfolgreich wiederhergestellt"
            
        except Exception as e:
            return False, f"Restore-Fehler: {str(e)}"
    
    # Audit Log
    def log_action(self, user_id, action, details, ip_address=None):
        """Erstelle Audit-Log-Eintrag"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO audit_log (user_id, action, details, ip_address)
                VALUES (?, ?, ?, ?)
            ''', (user_id, action, details, ip_address))
            
            conn.commit()
            
        except Exception:
            pass  # Logging-Fehler sollten die App nicht stoppen
        finally:
            conn.close()
    
    def get_audit_log(self, limit=100):
        """Lade Audit-Log-Einträge"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id, a.user_id, a.action, a.details, a.timestamp, a.ip_address, u.name
            FROM audit_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'id': row[0],
                'user_id': row[1],
                'action': row[2],
                'details': row[3],
                'timestamp': row[4],
                'ip_address': row[5],
                'user_name': row[6] or 'System'
            })
        
        conn.close()
        return logs