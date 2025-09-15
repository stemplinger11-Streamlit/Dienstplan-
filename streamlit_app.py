# streamlit_app.py — Dienstplan+ Cloud v3.0 (Twilio Enterprise Edition)
# Enterprise-ready Features: Watchlist, Admin-Umbuchen, Daily Backup 20:00,
# Info-Seiten (editierbar), Profil Tests (SMS/E-Mail), Monatsansicht,
# mobilfreundliche UI, Twilio SMS, Gmail SMTP.
import streamlit as st
import sqlite3, hashlib, json, io, zipfile, threading, time, smtplib, os
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import requests
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from twilio.rest import Client  # Twilio SMS

# ===== Konfiguration & Konstanten =====
VERSION = "3.0"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = "Europe/Berlin"
TZ = pytz.timezone(TIMEZONE_STR)

WEEKLY_SLOTS = [
    {"id": 1, "day": "tuesday",  "day_name": "Dienstag", "start_time": "17:00", "end_time": "20:00", "color": "#3B82F6"},
    {"id": 2, "day": "friday",   "day_name": "Freitag",  "start_time": "17:00", "end_time": "20:00", "color": "#10B981"},
    {"id": 3, "day": "saturday", "day_name": "Samstag",  "start_time": "14:00", "end_time": "17:00", "color": "#F59E0B"},
]

HOLIDAYS = {
    "2025-01-01": "Neujahr",
    "2025-01-06": "Heilige Drei Könige",
    "2025-04-18": "Karfreitag",
    "2025-04-21": "Ostermontag",
    "2025-05-01": "Tag der Arbeit",
    "2025-05-29": "Christi Himmelfahrt",
    "2025-06-09": "Pfingstmontag",
    "2025-06-19": "Fronleichnam",
    "2025-08-15": "Mariä Himmelfahrt",
    "2025-10-03": "Tag der Deutschen Einheit",
    "2025-11-01": "Allerheiligen",
    "2025-12-25": "1. Weihnachtsfeiertag",
    "2025-12-26": "2. Weihnachtsfeiertag",
}

CLOSED_PERIODS = [
    {"start": "2025-06-01", "end": "2025-09-30", "reason": "Sommerpause"}
]

# ===== Datenbank-Layer =====
class DatabaseManager:
    def __init__(self):
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(DB_FILE, check_same_thread=False)

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
                user_id INTEGER,
                slot_id INTEGER,
                booking_date DATE,
                status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(slot_id, booking_date)
            )
        ''')
        
        # Favorites/Watchlist Tabelle
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
        
        # Info Pages Tabelle
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
        
        conn.commit()
        
        # Initial Admin und Templates erstellen
        self._create_initial_admin()
        self._ensure_info_pages()
        self._create_default_templates()
        
        conn.close()

    def _create_initial_admin(self):
        """Erstelle Initial-Admin aus Secrets falls noch keiner existiert"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_initial_admin = 1')
        if cursor.fetchone()[0] == 0:
            try:
                admin_email = st.secrets.get("ADMIN_EMAIL", "")
                admin_password = st.secrets.get("ADMIN_PASSWORD", "")
                if admin_email and admin_password:
                    password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
                    cursor.execute('''
                        INSERT INTO users (email, phone, name, password_hash, role, is_initial_admin, sms_opt_in)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (admin_email, "+4915199999999", "Initial Admin", password_hash, "admin", 1, 1))
                    conn.commit()
            except Exception:
                pass  # Secrets nicht verfügbar
        conn.close()

    def _ensure_info_pages(self):
        """Erstelle Standard-Info-Seiten"""
        defaults = {
            "schicht_info": (
                "Schicht-Informationen",
                """# Schicht-Checkliste

## Vor Schichtbeginn:
1. **Kasse holen** - Schlüssel im Büro abholen
2. **Hallenbad aufsperren** - 30 Minuten vor Öffnung
3. **Technik prüfen** - Beleuchtung, Heizung, Pumpen
4. **Sicherheit checken** - Erste-Hilfe-Kasten, AED-Gerät

## Während der Schicht:
- **Aufsichtspflicht** wahrnehmen
- **Badegäste** freundlich betreuen
- **Ordnung** im Bad aufrechterhalten
- **Kassierung** korrekt durchführen

## Nach Schichtende:
1. **Bad kontrollieren** - alle Bereiche prüfen
2. **Kasse abrechnen** - Einnahmen zählen
3. **Hallenbad abschließen** - alle Türen/Fenster
4. **Kasse zurückbringen** - sicher im Büro verstauen

## Besonderheiten:
- Bei **Feiertagen** gelten andere Öffnungszeiten
- Bei **Veranstaltungen** Sonderregelungen beachten
- Bei **Problemen** sofort Leitung kontaktieren"""
            ),
            "rettungskette": (
                "Rettungskette Hallenbad",
                """# 🚨 Offizieller Ablaufplan – Rettungskette

## Sofortmaßnahmen:
1. **Notruf 112 absetzen** (WO, WAS, WIE VIELE, WER)
2. **Patienten ansprechen** - Bewusstsein prüfen
3. **Atmung prüfen** - 10 Sekunden lang

## Bei bewusstloser Person:
4. **Keine Atmung:** 30:2 Reanimation (100–120/min, 5–6 cm tief)
5. **AED holen und anwenden** - Anweisungen des Geräts befolgen
6. **Bei vorhandener Atmung:** Stabile Seitenlage
7. **Weitermachen** bis Rettungsdienst eintrifft

## Wichtige Nummern:
- **Notruf:** 112
- **Giftnotruf:** 089 19240
- **Polizei:** 110

## Equipment-Standorte:
- **AED-Gerät:** Eingangsbereich
- **Erste-Hilfe-Kasten:** Büro
- **Notfallkoffer:** Pool-Bereich
- **Kühlpacks:** Büro-Kühlschrank

⚠️ **Wichtig:** Diese Informationen ersetzen keine Erste-Hilfe-Ausbildung!"""
            )
        }
        
        conn = self.get_connection()
        cursor = conn.cursor()
        for key, (title, content) in defaults.items():
            cursor.execute("SELECT COUNT(*) FROM info_pages WHERE page_key=?", (key,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO info_pages(page_key,title,content) VALUES(?,?,?)", (key, title, content))
        conn.commit()
        conn.close()

    def _create_default_templates(self):
        """Erstelle Standard E-Mail Templates"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM email_templates')
        if cursor.fetchone()[0] == 0:
            email_templates = [
                ('Einladung', 'booking_invite', '[Dienstplan+] Einladung: {{slot}} - {{datum}}', 
                 'Hallo {{name}},\n\nhier ist deine Kalender-Einladung für die Schicht am {{datum}} von {{slot}}.\n\nMit "Annehmen" im Kalender bestätigst du den Termin automatisch.\n\nViele Grüße\nDein Dienstplan+ Team'),
                ('Absage', 'booking_cancel', '[Dienstplan+] Absage: {{slot}} - {{datum}}', 
                 'Hallo {{name}},\n\ndie Schicht am {{datum}} von {{slot}} wurde storniert.\n\nDiese Nachricht aktualisiert oder entfernt den Kalendereintrag automatisch.\n\nViele Grüße\nDein Dienstplan+ Team'),
                ('Umbuchung', 'booking_reschedule', '[Dienstplan+] Umbuchung: {{slot}} - {{datum}}', 
                 'Hallo {{name}},\n\ndeine Schicht wurde umgebucht auf: {{datum}} von {{slot}}.\n\nBitte prüfe deinen Kalender für die Aktualisierung.\n\nViele Grüße\nDein Dienstplan+ Team')
            ]
            
            for template in email_templates:
                cursor.execute('''
                    INSERT INTO email_templates (name, template_type, subject_template, body_template)
                    VALUES (?, ?, ?, ?)
                ''', template)
        
        conn.commit()
        conn.close()

    # ---- Users
    def authenticate_user(self, email, password):
        conn = self.get_connection()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin
            FROM users WHERE email = ? AND password_hash = ? AND active = 1
        ''', (email, password_hash))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user[0], 'email': user[1], 'phone': user[2], 'name': user[3],
                'role': user[4], 'sms_opt_in': user[5], 'whatsapp_opt_in': user[6], 
                'email_opt_in': user[7], 'is_initial_admin': user[8]
            }
        return None

    def create_user(self, email, phone, name, password, role='user'):
        conn = self.get_connection()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            cursor.execute('''
                INSERT INTO users (email, phone, name, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (email, phone, name, password_hash, role))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            conn.close()
            return None

    def update_user_profile(self, user_id, name, phone, sms_opt_in):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET name = ?, phone = ?, sms_opt_in = ?
            WHERE id = ?
        ''', (name, phone, sms_opt_in, user_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def update_user_password(self, user_id, new_password):
        conn = self.get_connection()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, email, phone, name, role, active, created_at, is_initial_admin
            FROM users WHERE active = 1 ORDER BY name
        ''')
        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0], 'email': row[1], 'phone': row[2], 'name': row[3],
                'role': row[4], 'active': row[5], 'created_at': row[6], 'is_initial_admin': row[7]
            })
        conn.close()
        return users

    # ---- Bookings
    def create_booking(self, user_id, slot_id, booking_date):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Prüfen ob Slot bereits belegt
        cursor.execute('''
            SELECT COUNT(*) FROM bookings
            WHERE slot_id = ? AND booking_date = ? AND status = 'confirmed'
        ''', (slot_id, booking_date))
        
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False, "Slot bereits belegt"
        
        cursor.execute('''
            INSERT INTO bookings (user_id, slot_id, booking_date)
            VALUES (?, ?, ?)
        ''', (user_id, slot_id, booking_date))
        
        conn.commit()
        booking_id = cursor.lastrowid
        conn.close()
        return True, booking_id

    def cancel_booking(self, booking_id, user_id=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if user_id:
            cursor.execute('DELETE FROM bookings WHERE id = ? AND user_id = ?', (booking_id, user_id))
        else:
            # Admin kann alle Buchungen stornieren
            cursor.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def get_bookings_for_date_slot(self, slot_id, booking_date):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.id, b.user_id, u.name, u.phone, u.email, b.created_at
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.slot_id = ? AND b.booking_date = ? AND b.status = 'confirmed'
        ''', (slot_id, booking_date))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0], 'user_id': row[1], 'user_name': row[2], 
                'phone': row[3], 'email': row[4], 'created_at': row[5]
            })
        
        conn.close()
        return bookings

    def get_user_bookings(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, slot_id, booking_date, status, created_at
            FROM bookings
            WHERE user_id = ? AND status = 'confirmed'
            ORDER BY booking_date ASC
        ''', (user_id,))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0], 'slot_id': row[1], 'date': row[2], 
                'status': row[3], 'created_at': row[4]
            })
        
        conn.close()
        return bookings

    def get_booking_by_id(self, booking_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.id, b.user_id, b.slot_id, b.booking_date, u.name, u.email
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            WHERE b.id = ?
        ''', (booking_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0], 'user_id': row[1], 'slot_id': row[2], 
                'date': row[3], 'user_name': row[4], 'user_email': row[5]
            }
        return None

    def transfer_booking(self, booking_id, new_user_id):
        """Umbuchen einer Schicht auf einen anderen User"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE bookings SET user_id = ? WHERE id = ?', (new_user_id, booking_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    # ---- Favorites/Watchlist
    def is_favorite(self, user_id, slot_id, date_str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ? AND slot_id = ? AND date = ?',
                      (user_id, slot_id, date_str))
        result = cursor.fetchone()[0] > 0
        conn.close()
        return result

    def add_favorite(self, user_id, slot_id, date_str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO favorites (user_id, slot_id, date) VALUES (?, ?, ?)',
                          (user_id, slot_id, date_str))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_favorite(self, user_id, slot_id, date_str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM favorites WHERE user_id = ? AND slot_id = ? AND date = ?',
                      (user_id, slot_id, date_str))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def get_user_favorites(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT slot_id, date, created_at FROM favorites
            WHERE user_id = ? ORDER BY date ASC
        ''', (user_id,))
        
        favorites = []
        for row in cursor.fetchall():
            favorites.append({
                'slot_id': row[0], 'date': row[1], 'created_at': row[2]
            })
        
        conn.close()
        return favorites

    # ---- Audit Log
    def log_action(self, user_id, action, details):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO audit_log (user_id, action, details)
                VALUES (?, ?, ?)
            ''', (user_id, action, details))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Logging-Fehler sollten App nicht stoppen

    # ---- Info Pages
    def get_info_page(self, page_key):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title, content, last_updated, updated_by FROM info_pages WHERE page_key = ?', (page_key,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'title': row[0], 'content': row[1], 'last_updated': row[2], 'updated_by': row[3]}
        return {'title': '', 'content': '', 'last_updated': None, 'updated_by': None}

    def save_info_page(self, page_key, title, content, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO info_pages (page_key, title, content, last_updated, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(page_key) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                last_updated = excluded.last_updated,
                updated_by = excluded.updated_by
        ''', (page_key, title, content, datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()

    # ---- Backup
    def create_backup(self):
        """Erstelle Vollbackup der Datenbank"""
        conn = self.get_connection()
        backup_data = {
            'created_at': datetime.now().isoformat(),
            'version': VERSION,
            'tables': {}
        }
        
        tables = ['users', 'bookings', 'favorites', 'audit_log', 'info_pages', 'backup_log', 'email_templates']
        
        for table in tables:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM {table}')
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            backup_data['tables'][table] = {
                'columns': columns,
                'rows': rows
            }
        
        conn.close()
        return json.dumps(backup_data, indent=2, default=str)

# ===== Services =====
class TwilioSMSService:
    def __init__(self):
        try:
            self.account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
            self.auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
            self.from_number = st.secrets.get("TWILIO_PHONE_NUMBER", "")
            self.client = Client(self.account_sid, self.auth_token) if (self.account_sid and self.auth_token) else None
            self.enabled = bool(self.client and self.from_number and st.secrets.get("ENABLE_SMS", True))
        except Exception:
            self.client = None
            self.enabled = False

    def send_sms(self, to_number, message):
        if not self.enabled:
            return False, "SMS Service nicht konfiguriert"
        try:
            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            return True, message_obj.sid
        except Exception as e:
            return False, str(e)

    def send_admin_sms(self, message):
        """Sende SMS an alle Administratoren"""
        admin_sms_list = st.secrets.get("ADMIN_SMS_LIST", [])
        if not admin_sms_list:
            # Fallback: Alle Admins aus DB
            conn = st.session_state.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT phone FROM users WHERE role = "admin" AND active = 1 AND sms_opt_in = 1')
            admin_phones = [row[0] for row in cursor.fetchall()]
            conn.close()
        else:
            admin_phones = admin_sms_list
        
        results = []
        for phone in admin_phones:
            success, result = self.send_sms(phone, message)
            results.append((phone, success, result))
        return results

class EmailService:
    def __init__(self):
        try:
            self.gmail_user = st.secrets.get("GMAIL_USER", "")
            self.gmail_password = st.secrets.get("GMAIL_APP_PASSWORD", "")
            self.from_name = st.secrets.get("FROM_NAME", "Dienstplan+ Cloud")
            self.enabled = bool(self.gmail_user and self.gmail_password and st.secrets.get("ENABLE_EMAIL", True))
        except:
            self.enabled = False

    def send_email(self, to_email, subject, body, attachments=None):
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
        
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.gmail_user}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            
            # Anhänge hinzufügen
            if attachments:
                for attachment in attachments:
                    if isinstance(attachment, dict) and "filename" in attachment and "content" in attachment:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(attachment["content"])
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f'attachment; filename="{attachment["filename"]}"')
                        msg.attach(part)
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            return True, "E-Mail erfolgreich gesendet"
            
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"

    def send_calendar_invite(self, to_email, subject, body, ics_content, method="REQUEST"):
        """Sende Kalendereinladung per E-Mail"""
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
        
        try:
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{self.from_name} <{self.gmail_user}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = email.utils.formatdate(localtime=True)
            
            # Text-Teil
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # ICS als Attachment
            ics_part = MIMEBase('text', 'calendar')
            ics_part.add_header('Content-Disposition', f'attachment; filename="invite.ics"')
            ics_part.add_header('method', method)
            ics_part.set_payload(ics_content.encode('utf-8'))
            encoders.encode_base64(ics_part)
            msg.attach(ics_part)
            
            # Alternative: ICS als calendar MIME part
            cal_part = MIMEText(ics_content, 'calendar', 'utf-8')
            cal_part.add_header('Content-Disposition', 'inline')
            cal_part.add_header('method', method)
            msg.attach(cal_part)
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            return True, "E-Mail erfolgreich gesendet"
            
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"

# ===== Backup Service =====
class BackupService:
    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.scheduler = None
        self.scheduler_running = False

    def start_scheduler(self):
        """Starte täglichen Backup-Scheduler um 20:00"""
        if self.scheduler_running:
            return
            
        if not st.secrets.get("ENABLE_DAILY_BACKUP", True):
            return
            
        if not self.email_service.enabled:
            return
        
        try:
            self.scheduler = BackgroundScheduler(timezone=TZ, daemon=True)
            self.scheduler.add_job(
                func=self._send_daily_backup,
                trigger=CronTrigger(hour=20, minute=0),
                id="daily_backup",
                replace_existing=True,
                max_instances=1
            )
            self.scheduler.start()
            self.scheduler_running = True
        except Exception:
            self.scheduler_running = False

    def _send_daily_backup(self):
        """Täglicher Backup-Job"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Prüfe ob heute bereits Backup gesendet
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM backup_log WHERE backup_date = ? AND status = "success"',
                (today,)
            )
            
            if cursor.fetchone()[0] == 0:  # Noch kein erfolgreiches Backup heute
                success = self.send_backup_email()
                status = "success" if success else "failed"
                
                cursor.execute('''
                    INSERT INTO backup_log (backup_date, status, details)
                    VALUES (?, ?, ?)
                ''', (today, status, "Automated daily backup"))
                conn.commit()
            
            conn.close()
            
        except Exception as e:
            print(f"Daily backup error: {e}")

    def send_backup_email(self):
        """Sende Backup per E-Mail"""
        try:
            # Backup erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Info-Datei
                info_content = f"""Dienstplan+ Cloud v{VERSION} - Backup

Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Zeitzone: {TIMEZONE_STR}

Dieses Backup enthält alle App-Daten:
- Benutzer und Buchungen
- Favoriten/Watchlist
- Audit-Logs
- Info-Seiten
- E-Mail-Templates

Zum Wiederherstellen die ZIP-Datei im Admin-Panel hochladen.
"""
                zip_file.writestr("README.txt", info_content)
            
            zip_buffer.seek(0)
            
            # E-Mail senden
            backup_email = st.secrets.get("BACKUP_EMAIL", "wasserwachthauzenberg@gmail.com")
            subject = f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}"
            body = f"""Automatisches tägliches Backup der Dienstplan+ Cloud App.

📅 Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📦 Größe: {len(zip_buffer.getvalue()) / 1024:.1f} KB

Das Backup ist als ZIP-Datei angehängt und kann im Admin-Panel
der App wiederhergestellt werden.

Diese E-Mail wird täglich um 20:00 Uhr automatisch versendet.

Mit freundlichen Grüßen
Ihr Dienstplan+ System v{VERSION}"""
            
            attachments = [{
                "filename": f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip",
                "content": zip_buffer.getvalue()
            }]
            
            success, message = self.email_service.send_email(
                backup_email, subject, body, attachments
            )
            
            return success
            
        except Exception as e:
            return False

# ===== Helper Functions =====
def get_week_start(date_obj=None):
    """Gibt Montag der ISO-Kalenderwoche zurück"""
    if date_obj is None:
        date_obj = datetime.now()
    if isinstance(date_obj, datetime):
        date_obj = date_obj.date()
    return date_obj - timedelta(days=date_obj.weekday())

def get_current_week_start():
    """Gibt Montag der aktuellen Kalenderwoche zurück"""
    return get_week_start(datetime.now())

def get_iso_calendar_week(date_obj):
    """Gibt ISO-Kalenderwoche zurück"""
    return date_obj.isocalendar()[1]

def get_slot_date(week_start, day_name):
    """Berechne Datum für Slot basierend auf Wochentag"""
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    day_offset = days.get(day_name, 0)
    return (week_start + timedelta(days=day_offset)).strftime('%Y-%m-%d')

def is_holiday(date_str):
    """Prüfe ob Datum ein Feiertag ist"""
    return date_str in HOLIDAYS

def get_holiday_name(date_str):
    """Hole Feiertagsname"""
    return HOLIDAYS.get(date_str, "Feiertag")

def is_closed_period(date_str):
    """Prüft ob Datum in der Sperrzeit (Juni-September) liegt"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        month = date_obj.month
        # Juni (6) bis September (9) geschlossen
        return 6 <= month <= 9
    except:
        return False

def format_german_date(date_str):
    """Datum deutsch formatieren"""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except:
        return date_str

# ===== Streamlit App Setup =====
st.set_page_config(
    page_title="Dienstplan+ Cloud v3.0",
    page_icon="🏊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS für mobilfreundliches Design
st.markdown("""
<style>
.main > div {
    padding-top: 2rem;
}
.stAlert > div {
    padding: 0.5rem 1rem;
}
.success-card {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
    color: #155724;
}
.info-card {
    background-color: #d1ecf1;
    border: 1px solid #bee5eb;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
    color: #0c5460;
}
.warning-card {
    background-color: #fff3cd;
    border: 1px solid #ffeeba;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
    color: #856404;
}
.danger-card {
    background-color: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
    color: #721c24;
}
.week-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 1rem 0;
    flex-wrap: wrap;
}
.button-row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
@media (max-width: 768px) {
    .week-header {
        flex-direction: column;
        gap: 0.5rem;
    }
    .button-row {
        width: 100%;
        justify-content: center;
    }
}
</style>
""", unsafe_allow_html=True)

# ===== Session State Initialisierung =====
if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

if "sms_service" not in st.session_state:
    st.session_state.sms_service = TwilioSMSService()

if "email_service" not in st.session_state:
    st.session_state.email_service = EmailService()

if "backup_service" not in st.session_state:
    st.session_state.backup_service = BackupService(
        st.session_state.db, 
        st.session_state.email_service
    )
    try:
        st.session_state.backup_service.start_scheduler()
    except Exception:
        pass

if "current_week_start" not in st.session_state:
    st.session_state.current_week_start = get_current_week_start()

# ===== Main App Functions =====
def show_login():
    """Zeige Login/Registrierung"""
    st.markdown("# 🔐 Willkommen bei Dienstplan+ Cloud")
    st.markdown("**Professionelle Dienstplanung für Ihr Team**")
    
    tab1, tab2 = st.tabs(["🔑 Anmelden", "📝 Registrieren"])
    
    with tab1:
        with st.form("login_form"):
            st.markdown("### Anmelden")
            email = st.text_input("📧 E-Mail Adresse", placeholder="ihre.email@beispiel.de")
            password = st.text_input("🔒 Passwort", type="password")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                submit = st.form_submit_button("Anmelden", type="primary", use_container_width=True)
            
            if submit:
                if email and password:
                    user = st.session_state.db.authenticate_user(email, password)
                    if user:
                        st.session_state.current_user = user
                        st.session_state.current_week_start = get_current_week_start()
                        st.session_state.db.log_action(user['id'], 'login', f'User logged in from web')
                        st.success(f"Willkommen, {user['name']}! 🎉")
                        st.rerun()
                    else:
                        st.error("❌ Ungültige Anmeldedaten")
                else:
                    st.error("❌ Bitte alle Felder ausfüllen")
    
    with tab2:
        with st.form("register_form"):
            st.markdown("### 👥 Neuen Account erstellen")
            reg_name = st.text_input("👤 Vollständiger Name", placeholder="Max Mustermann")
            reg_email = st.text_input("📧 E-Mail Adresse", placeholder="max@beispiel.de")
            reg_phone = st.text_input(
                "📱 Telefonnummer", 
                placeholder="+49 151 12345678",
                help="Diese Nummer wird für Notfälle und automatische Erinnerungen verwendet."
            )
            reg_password = st.text_input("🔒 Passwort", type="password", help="Mindestens 6 Zeichen")
            reg_password_confirm = st.text_input("🔒 Passwort wiederholen", type="password")
            
            sms_consent = st.checkbox(
                "📱 SMS-Erinnerungen erhalten (empfohlen)", 
                value=True,
                help="Sie erhalten automatische Erinnerungen 24h und 1h vor Ihren Schichten."
            )
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                register = st.form_submit_button("Account erstellen", type="primary", use_container_width=True)
            
            if register:
                # Validierung
                errors = []
                if not all([reg_name, reg_email, reg_phone, reg_password, reg_password_confirm]):
                    errors.append("Bitte alle Felder ausfüllen")
                if reg_password != reg_password_confirm:
                    errors.append("Passwörter stimmen nicht überein")
                if len(reg_password) < 6:
                    errors.append("Passwort muss mindestens 6 Zeichen lang sein")
                if not reg_phone.startswith('+'):
                    errors.append("Telefonnummer muss mit Ländercode beginnen (z.B. +49)")
                if '@' not in reg_email or '.' not in reg_email:
                    errors.append("Ungültige E-Mail-Adresse")
                
                if errors:
                    for error in errors:
                        st.error(f"❌ {error}")
                    return
                
                # Benutzer erstellen
                user_id = st.session_state.db.create_user(reg_email, reg_phone, reg_name, reg_password)
                
                if user_id:
                    # Automatisches Login
                    user = st.session_state.db.authenticate_user(reg_email, reg_password)
                    if user:
                        st.session_state.current_user = user
                        st.session_state.current_week_start = get_current_week_start()
                        st.session_state.db.log_action(user_id, 'account_created', f'New user registered: {reg_name}')
                        st.success("✅ Account erfolgreich erstellt! Sie sind automatisch eingeloggt.")
                        st.balloons()
                        st.rerun()
                else:
                    st.error("❌ E-Mail bereits registriert")

def show_information_tab():
    """Informations-Tab mit bearbeitbaren Seiten"""
    st.markdown("# ℹ️ Informationen")
    
    tab1, tab2 = st.tabs(["📋 Schicht-Informationen", "🚨 Rettungskette"])
    
    with tab1:
        info = st.session_state.db.get_info_page("schicht_info")
        
        if st.session_state.current_user['role'] == 'admin':
            st.markdown("### 📝 Schicht-Informationen bearbeiten")
            
            with st.form("edit_schicht_info"):
                new_title = st.text_input("Titel", value=info['title'])
                new_content = st.text_area(
                    "Inhalt (Markdown)", 
                    value=info['content'], 
                    height=400,
                    help="Verwenden Sie Markdown-Syntax für Formatierung"
                )
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.form_submit_button("💾 Speichern", type="primary"):
                        st.session_state.db.save_info_page(
                            "schicht_info", 
                            new_title, 
                            new_content, 
                            st.session_state.current_user['id']
                        )
                        st.session_state.db.log_action(
                            st.session_state.current_user['id'], 
                            'info_page_updated', 
                            'Updated schicht_info page'
                        )
                        st.success("✅ Schicht-Informationen gespeichert!")
                        st.rerun()
        else:
            st.markdown(f"### {info['title']}")
            st.markdown(info['content'])
            
            if info['last_updated']:
                st.markdown(f"*Zuletzt aktualisiert: {info['last_updated'][:19]}*")
    
    with tab2:
        rettung_info = st.session_state.db.get_info_page("rettungskette")
        st.markdown(f"### {rettung_info['title']}")
        st.markdown(rettung_info['content'])
        
        if rettung_info['last_updated']:
            st.markdown(f"*Zuletzt aktualisiert: {rettung_info['last_updated'][:19]}*")

def show_schedule_tab():
    """Terminplan mit Watchlist-Funktionalität"""
    st.markdown("### 📅 Wochenplan")
    
    user = st.session_state.current_user
    week_start = st.session_state.current_week_start
    week_end = week_start + timedelta(days=6)
    kw = get_iso_calendar_week(week_start)
    
    # Navigation Header
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.button("⬅️ Vorherige Woche", key="prev_week"):
            st.session_state.current_week_start = week_start - timedelta(days=7)
            st.rerun()
    
    with col2:
        st.markdown(f"""
        <div style='text-align: center; font-size: 1.2em; font-weight: bold; padding: 0.5rem;'>
        📅 KW {kw} — {format_german_date(week_start.strftime('%Y-%m-%d'))} bis {format_german_date(week_end.strftime('%Y-%m-%d'))}
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        if st.button("Nächste Woche ➡️", key="next_week"):
            st.session_state.current_week_start = week_start + timedelta(days=7)
            st.rerun()
    
    # Heute Button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("📍 Aktuelle Woche", key="current_week"):
            st.session_state.current_week_start = get_current_week_start()
            st.rerun()
    
    # Quick Navigation Sidebar
    with st.sidebar:
        st.markdown("### 📅 Schnell-Navigation")
        for i in range(-2, 5):
            nav_week = week_start + timedelta(days=i*7)
            nav_week_end = nav_week + timedelta(days=6)
            nav_kw = get_iso_calendar_week(nav_week)
            
            if st.button(
                f"KW {nav_kw}: {nav_week.strftime('%d.%m')} - {nav_week_end.strftime('%d.%m')}", 
                key=f"nav_week_{i}"
            ):
                st.session_state.current_week_start = nav_week
                st.rerun()
    
    st.markdown("---")
    
    # Legende
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("🟢 **Verfügbar**")
    with col2:
        st.markdown("🔵 **Ihre Buchung**")
    with col3:
        st.markdown("🟡 **Belegt**")
    with col4:
        st.markdown("🔴 **Gesperrt/Feiertag**")
    
    st.markdown("---")
    
    # Slots für die Woche anzeigen
    for slot in WEEKLY_SLOTS:
        slot_date = get_slot_date(week_start, slot['day'])
        
        # Prüfe Feiertage
        if is_holiday(slot_date):
            holiday_name = get_holiday_name(slot_date)
            st.markdown(f"""
            <div class="warning-card">
                <h4>🎄 {slot['day_name']}, {format_german_date(slot_date)}</h4>
                <p><strong>Feiertag:</strong> {holiday_name}</p>
                <p>❌ Keine Schichten an diesem Tag</p>
            </div>
            """, unsafe_allow_html=True)
            continue
        
        # Prüfe Sperrzeit
        if is_closed_period(slot_date):
            st.markdown(f"""
            <div class="warning-card">
                <h4>🏊 {slot['day_name']}, {format_german_date(slot_date)}</h4>
                <p><strong>Hallenbad geschlossen - Sommerpause</strong></p>
                <p>❌ Keine Buchungen möglich (Juni - September)</p>
            </div>
            """, unsafe_allow_html=True)
            continue
        
        # Lade Buchungsinformationen
        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], slot_date)
        is_favorite = st.session_state.db.is_favorite(user['id'], slot['id'], slot_date)
        
        # Container für Slot-Karte
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if bookings:
                # Slot ist belegt
                booking = bookings[0]
                is_own_booking = booking['user_id'] == user['id']
                
                if is_own_booking:
                    st.markdown(f"""
                    <div class="info-card">
                        <h4>✅ {slot['day_name']}, {format_german_date(slot_date)}</h4>
                        <p><strong>Gebucht von Ihnen</strong></p>
                        <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                        <p>📝 Gebucht am: {datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="warning-card">
                        <h4>📋 {slot['day_name']}, {format_german_date(slot_date)}</h4>
                        <p><strong>Gebucht von:</strong> {booking['user_name']}</p>
                        <p>⚠️ Schicht bereits vergeben</p>
                        <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                # Slot ist frei
                st.markdown(f"""
                <div class="success-card">
                    <h4>✨ {slot['day_name']}, {format_german_date(slot_date)}</h4>
                    <p><strong>Verfügbar</strong></p>
                    <p>💡 Klicken Sie auf "Buchen" um diese Schicht zu übernehmen</p>
                    <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            # Favoriten-Stern
            star_text = "⭐ Favorit" if is_favorite else "☆ Favorit"
            if st.button(star_text, key=f"fav_{slot['id']}_{slot_date}"):
                if is_favorite:
                    st.session_state.db.remove_favorite(user['id'], slot['id'], slot_date)
                    st.success("Aus Favoriten entfernt")
                else:
                    st.session_state.db.add_favorite(user['id'], slot['id'], slot_date)
                    st.success("Zu Favoriten hinzugefügt")
                st.rerun()
            
            if bookings:
                booking = bookings[0]
                if booking['user_id'] == user['id']:
                    # Storno-Button für eigene Buchungen
                    if st.button("❌ Stornieren", key=f"cancel_{booking['id']}"):
                        st.session_state.db.cancel_booking(booking['id'], user['id'])
                        st.session_state.db.log_action(user['id'], 'booking_cancelled', f'Cancelled booking {booking["id"]}')
                        st.success("✅ Buchung storniert")
                        st.rerun()
                elif user['role'] == 'admin':
                    # Admin-Umbuchen
                    st.markdown("**Admin: Umbuchen**")
                    all_users = st.session_state.db.get_all_users()
                    user_options = [f"{u['name']} ({u['email']})" for u in all_users if u['id'] != booking['user_id']]
                    
                    if user_options:
                        selected_user = st.selectbox(
                            "Umbuchen auf:", 
                            user_options, 
                            key=f"reassign_user_{booking['id']}"
                        )
                        
                        if st.button("🔄 Umbuchen", key=f"reassign_{booking['id']}"):
                            # Finde neuen User
                            new_user = next(u for u in all_users if f"{u['name']} ({u['email']})" == selected_user)
                            
                            # E-Mail Absage an alten User
                            old_user_email = booking['user_email']
                            old_user_name = booking['user_name']
                            
                            cancel_subject = f"[Dienstplan+] Absage: {slot['day_name']} - {format_german_date(slot_date)}"
                            cancel_body = f"""Hallo {old_user_name},

die Schicht am {format_german_date(slot_date)} von {slot['start_time']} bis {slot['end_time']} wurde storniert/umgebucht.

Diese Nachricht dient zur Information.

Viele Grüße
Ihr Dienstplan+ Team"""

                            st.session_state.email_service.send_email(old_user_email, cancel_subject, cancel_body)
                            
                            # Umbuchung durchführen
                            if st.session_state.db.transfer_booking(booking['id'], new_user['id']):
                                # E-Mail Einladung an neuen User
                                invite_subject = f"[Dienstplan+] Einladung: {slot['day_name']} - {format_german_date(slot_date)}"
                                invite_body = f"""Hallo {new_user['name']},

Ihnen wurde eine Schicht zugewiesen:

📅 Datum: {format_german_date(slot_date)}
⏰ Zeit: {slot['start_time']} - {slot['end_time']} Uhr
📍 Tag: {slot['day_name']}

Viele Grüße
Ihr Dienstplan+ Team"""

                                st.session_state.email_service.send_email(new_user['email'], invite_subject, invite_body)
                                
                                st.session_state.db.log_action(
                                    user['id'], 
                                    'booking_transferred', 
                                    f'Transferred booking {booking["id"]} from {old_user_name} to {new_user["name"]}'
                                )
                                
                                st.success(f"✅ Schicht erfolgreich umgebucht auf {new_user['name']}")
                                st.rerun()
                            else:
                                st.error("❌ Umbuchung fehlgeschlagen")
            else:
                # Buchungs-Button
                if st.button("📝 Buchen", key=f"book_{slot['id']}_{slot_date}", type="primary"):
                    success, result = st.session_state.db.create_booking(user['id'], slot['id'], slot_date)
                    if success:
                        st.session_state.db.log_action(user['id'], 'booking_created', f'Booked slot {slot["id"]} for {slot_date}')
                        st.success(f"✅ Schicht erfolgreich gebucht für {format_german_date(slot_date)}")
                        
                        # Favorit entfernen falls vorhanden
                        if is_favorite:
                            st.session_state.db.remove_favorite(user['id'], slot['id'], slot_date)
                        
                        st.rerun()
                    else:
                        st.error(f"❌ Buchung fehlgeschlagen: {result}")

def show_my_shifts_tab():
    """Meine Schichten mit Watchlist"""
    st.markdown("### 👤 Meine Schichten")
    
    user = st.session_state.current_user
    
    # Meine aktuellen Buchungen
    user_bookings = st.session_state.db.get_user_bookings(user['id'])
    
    if user_bookings:
        # Filtere zukünftige Schichten
        today = datetime.now().date()
        future_bookings = [b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= today]
        
        if future_bookings:
            st.markdown("#### 🔮 Zukünftige Schichten")
            for booking in future_bookings[:10]:  # Zeige maximal 10
                slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"""
                    <div class="info-card">
                        <h5>{slot['day_name']}, {format_german_date(booking['date'])}</h5>
                        <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                        <p>📝 Gebucht am: {datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    if st.button("❌ Stornieren", key=f"cancel_my_{booking['id']}"):
                        st.session_state.db.cancel_booking(booking['id'], user['id'])
                        st.session_state.db.log_action(user['id'], 'booking_cancelled', f'Cancelled own booking {booking["id"]}')
                        st.success("✅ Schicht storniert")
                        st.rerun()
        else:
            st.info("📝 Keine zukünftigen Schichten gebucht")
    else:
        st.info("📝 Noch keine Schichten gebucht")
    
    st.markdown("---")
    
    # Watchlist / Favoriten
    st.markdown("### ⭐ Watchlist / Favoriten")
    
    favorites = st.session_state.db.get_user_favorites(user['id'])
    
    if favorites:
        st.markdown("**Ihre beobachteten Termine:**")
        
        for fav in favorites:
            slot = next(s for s in WEEKLY_SLOTS if s['id'] == fav['slot_id'])
            
            # Prüfe ob Slot noch frei ist
            bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], fav['date'])
            is_booked = len(bookings) > 0
            is_own = is_booked and bookings[0]['user_id'] == user['id']
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if is_own:
                    card_class = "info-card"
                    status = "✅ Von Ihnen gebucht"
                elif is_booked:
                    card_class = "warning-card"
                    status = f"🟡 Belegt von {bookings[0]['user_name']}"
                else:
                    card_class = "success-card"
                    status = "🟢 Verfügbar"
                
                st.markdown(f"""
                <div class="{card_class}">
                    <h5>⭐ {slot['day_name']}, {format_german_date(fav['date'])}</h5>
                    <p><strong>{status}</strong></p>
                    <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                if st.button("🗑️ Entfernen", key=f"remove_fav_{fav['slot_id']}_{fav['date']}"):
                    st.session_state.db.remove_favorite(user['id'], fav['slot_id'], fav['date'])
                    st.success("Aus Favoriten entfernt")
                    st.rerun()
                
                if not is_booked:
                    if st.button("📝 Buchen", key=f"book_fav_{fav['slot_id']}_{fav['date']}", type="primary"):
                        success, result = st.session_state.db.create_booking(user['id'], fav['slot_id'], fav['date'])
                        if success:
                            st.session_state.db.log_action(user['id'], 'booking_created', f'Booked favorited slot {fav["slot_id"]} for {fav["date"]}')
                            st.session_state.db.remove_favorite(user['id'], fav['slot_id'], fav['date'])  # Favorit entfernen
                            st.success("✅ Schicht gebucht!")
                            st.rerun()
                        else:
                            st.error(f"❌ Buchung fehlgeschlagen: {result}")
    else:
        st.info("📝 Noch keine Favoriten. Im Terminplan mit ⭐ Favorit hinzufügen.")

def show_team_tab():
    """Team-Management für Admins"""
    st.markdown("### 👥 Team-Management")
    
    # Team-Statistiken
    all_users = st.session_state.db.get_all_users()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Team-Mitglieder", len(all_users))
    
    with col2:
        admin_count = len([u for u in all_users if u['role'] == 'admin'])
        st.metric("Administratoren", admin_count)
    
    with col3:
        # Zähle aktive Buchungen
        today = datetime.now().date()
        active_bookings = 0
        for user in all_users:
            user_bookings = st.session_state.db.get_user_bookings(user['id'])
            active_bookings += len([b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= today])
        st.metric("Aktive Buchungen", active_bookings)
    
    with col4:
        # Buchungen diese Woche
        week_start = st.session_state.current_week_start
        week_end = week_start + timedelta(days=6)
        week_bookings = 0
        for user in all_users:
            user_bookings = st.session_state.db.get_user_bookings(user['id'])
            for booking in user_bookings:
                booking_date = datetime.strptime(booking['date'], '%Y-%m-%d').date()
                if week_start <= booking_date <= week_end:
                    week_bookings += 1
        st.metric("Diese Woche", week_bookings)
    
    st.markdown("---")
    
    # Team-Mitglieder als Expander
    with st.expander("👤 Team-Mitglieder", expanded=False):
        for user in all_users:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"""
                <div class="info-card">
                    <h5>{user['name']} ({user['role'].title()})</h5>
                    <p>📧 {user['email']}</p>
                    <p>📱 {user['phone']}</p>
                    <p>📅 Registriert: {user['created_at'][:10] if user['created_at'] else 'Unbekannt'}</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                # User-Buchungen zählen
                user_bookings = st.session_state.db.get_user_bookings(user['id'])
                future_bookings = len([b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= today])
                
                st.markdown(f"**Schichten:** {future_bookings}")
                
                # Favoriten zählen
                favorites = st.session_state.db.get_user_favorites(user['id'])
                st.markdown(f"**Favoriten:** {len(favorites)}")
    
    # Aktuelle Woche Übersicht als Expander
    with st.expander("📊 Aktuelle Woche (Übersicht)", expanded=False):
        week_start = st.session_state.current_week_start
        week_end = week_start + timedelta(days=6)
        kw = get_iso_calendar_week(week_start)
        
        st.markdown(f"**KW {kw}: {format_german_date(week_start.strftime('%Y-%m-%d'))} bis {format_german_date(week_end.strftime('%Y-%m-%d'))}**")
        
        for slot in WEEKLY_SLOTS:
            slot_date = get_slot_date(week_start, slot['day'])
            bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], slot_date)
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**{slot['day_name']}, {format_german_date(slot_date)}**")
                st.markdown(f"{slot['start_time']} - {slot['end_time']} Uhr")
            
            with col2:
                if bookings:
                    st.success(f"✅ {bookings[0]['user_name']}")
                elif is_holiday(slot_date):
                    st.info("🎄 Feiertag")
                elif is_closed_period(slot_date):
                    st.warning("🏊 Geschlossen")
                else:
                    st.error("❌ UNBESETZT")

def show_admin_tab():
    """Admin-Panel"""
    st.markdown("### ⚙️ Admin-Panel")
    
    # System-Status
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🔧 System-Status")
        
        if st.session_state.sms_service.enabled:
            st.success("🟢 **SMS Service** - Konfiguriert und aktiv")
        else:
            st.error("🔴 **SMS Service** - Nicht konfiguriert")
        
        if st.session_state.email_service.enabled:
            st.success("🟢 **E-Mail Service** - Konfiguriert und aktiv")
        else:
            st.error("🔴 **E-Mail Service** - Nicht konfiguriert")
        
        if st.session_state.backup_service.scheduler_running:
            st.success("🟢 **Auto-Backup** - Täglich 20:00 Uhr aktiv")
        else:
            st.error("🔴 **Auto-Backup** - Nicht aktiv")
    
    with col2:
        st.markdown("#### ⚡ Admin-Aktionen")
        
        if st.button("💾 Sofort-Backup erstellen"):
            if st.session_state.backup_service.send_backup_email():
                st.success("✅ Backup erfolgreich erstellt und versendet")
                st.session_state.db.log_action(
                    st.session_state.current_user['id'], 
                    'manual_backup', 
                    'Manual backup triggered by admin'
                )
            else:
                st.error("❌ Backup-Erstellung fehlgeschlagen")
        
        if st.button("📧 Test-E-Mail senden"):
            if st.session_state.email_service.enabled:
                success, message = st.session_state.email_service.send_email(
                    st.session_state.current_user['email'],
                    "Dienstplan+ Admin Test-E-Mail",
                    f"Test-E-Mail vom Admin-Panel.\n\nVersendet am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                if success:
                    st.success("✅ Test-E-Mail gesendet")
                else:
                    st.error(f"❌ E-Mail-Fehler: {message}")
            else:
                st.error("❌ E-Mail-Service nicht verfügbar")
        
        if st.button("📱 Test-SMS senden"):
            if st.session_state.sms_service.enabled:
                success, message = st.session_state.sms_service.send_sms(
                    st.session_state.current_user['phone'],
                    f"Test-SMS vom Dienstplan+ Admin-Panel. Zeit: {datetime.now().strftime('%H:%M')}"
                )
                if success:
                    st.success("✅ Test-SMS gesendet")
                else:
                    st.error(f"❌ SMS-Fehler: {message}")
            else:
                st.error("❌ SMS-Service nicht verfügbar")
    
    st.markdown("---")
    
    # Backup-Verwaltung
    st.markdown("#### 💾 Backup-Verwaltung")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📥 Backup erstellen")
        
        if st.button("📥 Vollständiges Backup herunterladen", type="primary"):
            try:
                backup_data = st.session_state.db.create_backup()
                
                # ZIP erstellen
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    zip_file.writestr(backup_filename, backup_data)
                    
                    # Info-Datei
                    info_content = f"""Dienstplan+ Cloud v{VERSION} - Backup

Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Zeitzone: {TIMEZONE_STR}

Dieses Backup enthält alle App-Daten:
- Benutzer und Buchungen
- Favoriten/Watchlist  
- Audit-Logs
- Info-Seiten
- E-Mail-Templates

Zum Wiederherstellen die ZIP-Datei im Admin-Panel hochladen.
"""
                    zip_file.writestr("README.txt", info_content)
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label="💾 Backup herunterladen",
                    data=zip_buffer.getvalue(),
                    file_name=f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip",
                    mime="application/zip"
                )
                
                st.success("✅ Backup erstellt und bereit zum Download")
                
            except Exception as e:
                st.error(f"❌ Backup-Fehler: {str(e)}")
    
    with col2:
        st.markdown("##### 📤 Backup wiederherstellen")
        st.warning("⚠️ **WARNUNG:** Überschreibt alle aktuellen Daten!")
        
        uploaded_file = st.file_uploader(
            "Backup-ZIP-Datei auswählen:",
            type=['zip'],
            key="restore_backup"
        )
        
        if uploaded_file is not None:
            if st.button("⚠️ RESTORE - Alle Daten ersetzen", type="secondary"):
                st.error("🚧 Restore-Funktion in dieser Demo-Version nicht implementiert")
                st.info("💡 Für Restore-Funktionalität wenden Sie sich an den Administrator")

def show_profile_page():
    """Profil-Seite mit Service-Tests"""
    user = st.session_state.current_user
    
    st.markdown("# 👤 Mein Profil")
    
    # Profil-Informationen
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📝 Profil-Daten")
        
        with st.form("profile_form"):
            new_name = st.text_input("👤 Name", value=user['name'])
            new_phone = st.text_input(
                "📱 Telefonnummer", 
                value=user['phone'],
                help="Wird für Notfälle und automatische Erinnerungen verwendet"
            )
            sms_opt_in = st.checkbox(
                "📱 SMS-Erinnerungen erhalten", 
                value=user.get('sms_opt_in', False),
                help="Sie erhalten automatische Erinnerungen 24h und 1h vor Ihren Schichten"
            )
            
            if st.form_submit_button("💾 Speichern", type="primary"):
                if new_name and new_phone:
                    success = st.session_state.db.update_user_profile(
                        user['id'], new_name, new_phone, sms_opt_in
                    )
                    
                    if success:
                        # Session State aktualisieren
                        st.session_state.current_user['name'] = new_name
                        st.session_state.current_user['phone'] = new_phone
                        st.session_state.current_user['sms_opt_in'] = sms_opt_in
                        
                        st.session_state.db.log_action(
                            user['id'], 'profile_updated', 'User updated profile data'
                        )
                        
                        st.success("✅ Profil erfolgreich aktualisiert!")
                    else:
                        st.error("❌ Fehler beim Aktualisieren")
                else:
                    st.error("❌ Name und Telefonnummer sind erforderlich")
    
    with col2:
        st.markdown("### 🔒 Passwort ändern")
        
        with st.form("password_form"):
            current_password = st.text_input("Aktuelles Passwort", type="password")
            new_password = st.text_input("Neues Passwort", type="password")
            confirm_password = st.text_input("Neues Passwort bestätigen", type="password")
            
            if st.form_submit_button("🔑 Passwort ändern", type="primary"):
                if not all([current_password, new_password, confirm_password]):
                    st.error("❌ Bitte alle Felder ausfüllen")
                elif new_password != confirm_password:
                    st.error("❌ Neue Passwörter stimmen nicht überein")
                elif len(new_password) < 6:
                    st.error("❌ Neues Passwort muss mindestens 6 Zeichen lang sein")
                else:
                    # Aktuelles Passwort prüfen
                    current_user_check = st.session_state.db.authenticate_user(user['email'], current_password)
                    if current_user_check:
                        success = st.session_state.db.update_user_password(user['id'], new_password)
                        if success:
                            st.session_state.db.log_action(user['id'], 'password_changed', 'Password changed by user')
                            st.success("✅ Passwort erfolgreich geändert!")
                        else:
                            st.error("❌ Fehler beim Ändern des Passworts")
                    else:
                        st.error("❌ Aktuelles Passwort ist falsch")
    
    st.markdown("---")
    
    # Account-Informationen
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📊 Account-Informationen")
        st.markdown(f"""
        **👤 Name:** {user['name']}
        
        **📧 E-Mail:** {user['email']}
        
        **📱 Telefon:** {user['phone']}
        
        **🎭 Rolle:** {user['role'].title()}
        
        **📱 SMS-Erinnerungen:** {'✅ Aktiv' if user.get('sms_opt_in') else '❌ Deaktiviert'}
        """)
    
    with col2:
        st.markdown("### 📤 Daten-Export")
        
        if st.button("📥 Meine Daten exportieren (JSON)", type="secondary"):
            user_bookings = st.session_state.db.get_user_bookings(user['id'])
            favorites = st.session_state.db.get_user_favorites(user['id'])
            
            export_data = {
                'profile': {
                    'name': user['name'],
                    'email': user['email'],
                    'phone': user['phone'],
                    'role': user['role']
                },
                'bookings': user_bookings,
                'favorites': favorites,
                'export_date': datetime.now().isoformat()
            }
            
            json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📥 JSON herunterladen",
                data=json_data,
                file_name=f"meine_daten_{user['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    
    st.markdown("---")
    
    # Service-Tests (alle Benutzer wenn aktiviert, Admins immer)
    if user['role'] == 'admin' or st.secrets.get("ENABLE_USER_SERVICE_TESTS", False):
        st.markdown("### 🧪 Service-Tests")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📱 SMS-Test")
            if st.session_state.sms_service.enabled:
                st.success("🟢 SMS-Service verfügbar")
                if st.button("📤 Test-SMS an meine Nummer senden"):
                    success, message = st.session_state.sms_service.send_sms(
                        user['phone'], 
                        f"Test-SMS vom Dienstplan+ System. Zeit: {datetime.now().strftime('%H:%M')}"
                    )
                    
                    if success:
                        st.success("✅ Test-SMS gesendet")
                        st.session_state.db.log_action(user['id'], 'test_sms_sent', 'Profile SMS test successful')
                    else:
                        st.error(f"❌ SMS-Fehler: {message}")
                        if user['role'] == 'admin':
                            st.warning(f"**[Admin Log]** SMS-Fehler: {message}")
                        st.session_state.db.log_action(user['id'], 'test_sms_failed', f'Profile SMS test failed: {message}')
            else:
                st.error("🔴 SMS-Service nicht konfiguriert")
        
        with col2:
            st.markdown("#### 📧 E-Mail-Test")
            if st.session_state.email_service.enabled:
                st.success("🟢 E-Mail-Service verfügbar")
                if st.button("📤 Test-E-Mail an meine Adresse senden"):
                    success, message = st.session_state.email_service.send_email(
                        user['email'],
                        "Dienstplan+ Test-E-Mail",
                        f"""Hallo {user['name']},

dies ist eine Test-E-Mail von Ihrem Dienstplan+ System.

Versendet am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Mit freundlichen Grüßen
Ihr Dienstplan+ Team"""
                    )
                    
                    if success:
                        st.success("✅ Test-E-Mail gesendet")
                        st.session_state.db.log_action(user['id'], 'test_email_sent', 'Profile email test successful')
                    else:
                        st.error(f"❌ E-Mail-Fehler: {message}")
                        if user['role'] == 'admin':
                            st.warning(f"**[Admin Log]** E-Mail-Fehler: {message}")
                        st.session_state.db.log_action(user['id'], 'test_email_failed', f'Profile email test failed: {message}')
            else:
                st.error("🔴 E-Mail-Service nicht konfiguriert")

def show_main_app():
    """Hauptanwendung"""
    user = st.session_state.current_user
    
    # Header mit Navigation
    col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
    
    with col1:
        st.markdown(f"👋 **{user['name']}**  \n📧 {user['email']}")
    
    with col2:
        st.markdown("# 📅 Dienstplan+ Cloud")
    
    with col3:
        if st.button("ℹ️ Info"):
            st.session_state.show_info = True
            st.rerun()
    
    with col4:
        if st.button("👤 Profil"):
            st.session_state.show_profile = True
            st.rerun()
    
    # Logout Button in der Sidebar
    with st.sidebar:
        st.markdown("---")
        if st.button("🚪 Abmelden", type="secondary", use_container_width=True):
            st.session_state.db.log_action(user['id'], 'logout', 'User logged out')
            
            # Session State bereinigen
            for key in ['current_user', 'show_profile', 'show_info', 'current_week_start']:
                if key in st.session_state:
                    del st.session_state[key]
            
            st.rerun()
    
    st.markdown("---")
    
    # Prüfe ob Info-Seite angezeigt werden soll
    if st.session_state.get('show_info', False):
        show_information_tab()
        
        if st.button("⬅️ Zurück zum Terminplan"):
            st.session_state.show_info = False
            st.rerun()
        return
    
    # Prüfe ob Profil-Seite angezeigt werden soll
    if st.session_state.get('show_profile', False):
        show_profile_page()
        
        if st.button("⬅️ Zurück zum Terminplan"):
            st.session_state.show_profile = False
            st.rerun()
        return
    
    # Tab Navigation - Admins haben zusätzliche Tabs
    if user['role'] == 'admin':
        tabs = st.tabs(["📅 Terminplan", "👤 Meine Schichten", "👥 Team", "⚙️ Admin"])
        
        with tabs[0]:
            show_schedule_tab()
        
        with tabs[1]:
            show_my_shifts_tab()
        
        with tabs[2]:
            show_team_tab()
        
        with tabs[3]:
            show_admin_tab()
    
    else:
        tabs = st.tabs(["📅 Terminplan", "👤 Meine Schichten"])
        
        with tabs[0]:
            show_schedule_tab()
        
        with tabs[1]:
            show_my_shifts_tab()

# ===== Main App =====
def main():
    """Haupteinstiegspunkt der Anwendung"""
    if "current_user" not in st.session_state:
        show_login()
    else:
        show_main_app()

if __name__ == "__main__":
    main()