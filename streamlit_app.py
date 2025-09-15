"""
Dienstplan+ Cloud v3.0 - Production-Ready Single-File Application
WebSMS Edition - Vollständige Dienstbuchungs-App für Streamlit Cloud
Entwickelt für: GitHub → Streamlit.io Deployment
"""

import streamlit as st
import sqlite3
import hashlib
import json
import io
import zipfile
import threading
import time
import smtplib
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

# =============================================================================
# KONFIGURATION & KONSTANTEN
# =============================================================================

VERSION = "3.0"
APP_NAME = "Dienstplan+ Cloud"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = "Europe/Berlin"
TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Wöchentliche Slots (Standard-Dienstplan)
WEEKLY_SLOTS = [
    {"id": 1, "day_name": "Dienstag", "day": "tuesday", "start_time": "17:00", "end_time": "20:00"},
    {"id": 2, "day_name": "Freitag", "day": "friday", "start_time": "17:00", "end_time": "20:00"},
    {"id": 3, "day_name": "Samstag", "day": "saturday", "start_time": "14:00", "end_time": "17:00"},
]

# Feiertage (Deutschland 2024-2026)
HOLIDAYS = {
    "2024-12-25": "1. Weihnachtsfeiertag",
    "2024-12-26": "2. Weihnachtsfeiertag",
    "2025-01-01": "Neujahr",
    "2025-04-18": "Karfreitag", 
    "2025-04-21": "Ostermontag",
    "2025-05-01": "Tag der Arbeit",
    "2025-05-29": "Christi Himmelfahrt",
    "2025-06-09": "Pfingstmontag",
    "2025-10-03": "Tag der Deutschen Einheit",
    "2025-12-25": "1. Weihnachtsfeiertag",
    "2025-12-26": "2. Weihnachtsfeiertag",
    "2026-01-01": "Neujahr",
}

# Sommer-Schließzeit (Hallenbad)
CLOSED_PERIODS = [
    {"start": "2024-06-01", "end": "2024-09-30", "reason": "Sommerpause"},
    {"start": "2025-06-01", "end": "2025-09-30", "reason": "Sommerpause"},
    {"start": "2026-06-01", "end": "2026-09-30", "reason": "Sommerpause"},
]

# =============================================================================
# DATENBANKMANAGEMENT
# =============================================================================

class DatabaseManager:
    """Zentrale Datenbankklasse mit allen CRUD-Operationen"""
    
    def __init__(self):
        self.init_database()
    
    def get_connection(self):
        """Thread-sichere SQLite-Verbindung"""
        return sqlite3.connect(DB_FILE, check_same_thread=False)
    
    def init_database(self):
        """Erstelle alle Tabellen und Standarddaten"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                sms_opt_in BOOLEAN DEFAULT 1,
                email_opt_in BOOLEAN DEFAULT 1,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Bookings Table
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
        
        # Favorites/Watchlist Table
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
        
        # Audit Log Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Backup Log Table
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
        
        # Initial Admin erstellen
        self._create_initial_admin()
        conn.close()
    
    def _create_initial_admin(self):
        """Erstelle Initial-Admin aus Secrets"""
        try:
            admin_email = st.secrets.get("ADMIN_EMAIL", "")
            admin_password = st.secrets.get("ADMIN_PASSWORD", "")
            
            if admin_email and admin_password:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('SELECT COUNT(*) FROM users WHERE email = ?', (admin_email,))
                if cursor.fetchone()[0] == 0:
                    password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
                    cursor.execute('''
                        INSERT INTO users (email, phone, name, password_hash, role, sms_opt_in)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (admin_email, "+49151999999", "Initial Admin", password_hash, "admin", 1))
                    conn.commit()
                    self.log_action(None, 'admin_created', 'Initial admin created from secrets')
                
                conn.close()
        except Exception:
            pass  # Secrets nicht verfügbar oder Fehler
    
    def authenticate_user(self, email, password):
        """Benutzer authentifizieren"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, email_opt_in, active
            FROM users WHERE email = ? AND password_hash = ? AND active = 1
        ''', (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user[0], 'email': user[1], 'phone': user[2], 'name': user[3],
                'role': user[4], 'sms_opt_in': user[5], 'email_opt_in': user[6], 'active': user[7]
            }
        return None
    
    def create_user(self, email, phone, name, password):
        """Neuen Benutzer erstellen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        try:
            cursor.execute('''
                INSERT INTO users (email, phone, name, password_hash)
                VALUES (?, ?, ?, ?)
            ''', (email, phone, name, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            self.log_action(user_id, 'user_created', f'User {name} registered')
            return user_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    def create_booking(self, user_id, slot_id, date_str):
        """Neue Buchung erstellen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO bookings (user_id, slot_id, booking_date)
                VALUES (?, ?, ?)
            ''', (user_id, slot_id, date_str))
            
            booking_id = cursor.lastrowid
            conn.commit()
            self.log_action(user_id, 'booking_created', f'Booked slot {slot_id} for {date_str}')
            return True, booking_id
        except sqlite3.IntegrityError:
            return False, "Slot bereits belegt"
        finally:
            conn.close()
    
    def cancel_booking(self, booking_id, user_id):
        """Buchung stornieren"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM bookings WHERE id = ? AND user_id = ?', (booking_id, user_id))
        success = cursor.rowcount > 0
        conn.commit()
        
        if success:
            self.log_action(user_id, 'booking_cancelled', f'Cancelled booking {booking_id}')
        
        conn.close()
        return success
    
    def get_bookings_for_date_slot(self, slot_id, date_str):
        """Buchungen für spezifischen Slot und Datum"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.user_id, u.name, u.email, b.created_at
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.slot_id = ? AND b.booking_date = ?
        ''', (slot_id, date_str))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0], 'user_id': row[1], 'user_name': row[2],
                'user_email': row[3], 'created_at': row[4]
            })
        
        conn.close()
        return bookings
    
    def get_user_bookings(self, user_id):
        """Alle Buchungen eines Benutzers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.slot_id, b.booking_date, b.status, b.created_at
            FROM bookings b WHERE b.user_id = ?
            ORDER BY b.booking_date DESC
        ''', (user_id,))
        
        bookings = []
        for row in cursor.fetchall():
            bookings.append({
                'id': row[0], 'slot_id': row[1], 'date': row[2],
                'status': row[3], 'created_at': row[4]
            })
        
        conn.close()
        return bookings
    
    def add_favorite(self, user_id, slot_id, date_str):
        """Favorit hinzufügen"""
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
            return False
        finally:
            conn.close()
    
    def remove_favorite(self, user_id, slot_id, date_str):
        """Favorit entfernen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM favorites WHERE user_id = ? AND slot_id = ? AND date = ?',
                      (user_id, slot_id, date_str))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def is_favorite(self, user_id, slot_id, date_str):
        """Prüfen ob Favorit"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ? AND slot_id = ? AND date = ?',
                      (user_id, slot_id, date_str))
        result = cursor.fetchone()[0] > 0
        conn.close()
        return result
    
    def get_all_users(self):
        """Alle Benutzer laden"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, email_opt_in, created_at, active
            FROM users WHERE active = 1 ORDER BY name
        ''')
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0], 'email': row[1], 'phone': row[2], 'name': row[3],
                'role': row[4], 'sms_opt_in': row[5], 'email_opt_in': row[6],
                'created_at': row[7], 'active': row[8]
            })
        
        conn.close()
        return users
    
    def get_all_bookings(self):
        """Alle Buchungen laden"""
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
                'id': row[0], 'user_id': row[1], 'slot_id': row[2], 'date': row[3],
                'status': row[4], 'created_at': row[5], 'user_name': row[6], 'user_email': row[7]
            })
        
        conn.close()
        return bookings
    
    def log_action(self, user_id, action, details):
        """Audit-Log-Eintrag erstellen"""
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
    
    def get_audit_log(self, limit=100):
        """Audit-Log laden"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id, a.user_id, a.action, a.details, a.timestamp, u.name
            FROM audit_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC LIMIT ?
        ''', (limit,))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'id': row[0], 'user_id': row[1], 'action': row[2],
                'details': row[3], 'timestamp': row[4], 'user_name': row[5] or 'System'
            })
        
        conn.close()
        return logs
    
    def create_backup(self):
        """Vollständiges JSON-Backup erstellen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        backup_data = {
            'created_at': datetime.now().isoformat(),
            'version': VERSION,
            'tables': {}
        }
        
        tables = ['users', 'bookings', 'favorites', 'audit_log', 'backup_log']
        
        for table in tables:
            cursor.execute(f'SELECT * FROM {table}')
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            backup_data['tables'][table] = {
                'columns': columns,
                'rows': rows
            }
        
        conn.close()
        return json.dumps(backup_data, indent=2, default=str)

# =============================================================================
# WEBSMS SERVICE
# =============================================================================

class WebSMSService:
    """WebSMS REST-Client für SMS-Versand"""
    
    def __init__(self):
        self.base_url = st.secrets.get("WEB_SMS_BASE_URL", "https://api.websms.com").rstrip("/")
        self.username = st.secrets.get("WEB_SMS_USERNAME", "")
        self.password = st.secrets.get("WEB_SMS_PASSWORD", "")
        self.sender = st.secrets.get("WEB_SMS_SENDER", "Dienstplan")
        self.endpoint = st.secrets.get("WEB_SMS_ENDPOINT", "/rest/smsmessaging/simple")
        self.test_flag = st.secrets.get("WEB_SMS_TEST", False)
        self.enabled = bool(
            st.secrets.get("ENABLE_SMS", True) and 
            self.username and self.password
        )
    
    def send_sms(self, to_number, message):
        """SMS senden"""
        if not self.enabled:
            return False, "SMS Service nicht konfiguriert"
        
        try:
            url = f"{self.base_url}{self.endpoint}"
            if "simple" in self.endpoint:
                url += f"?test={'true' if self.test_flag else 'false'}"
            
            # Telefonnummer bereinigen
            clean_number = to_number.replace(" ", "").replace("-", "")
            if not clean_number.startswith("+") and clean_number.startswith("0"):
                clean_number = "+49" + clean_number[1:]
            
            payload = {
                "recipientAddressList": [clean_number],
                "messageContent": message[:918],
                "senderAddress": self.sender
            }
            
            headers = {"Content-Type": "application/json"}
            auth = (self.username, self.password)
            
            response = requests.post(
                url, json=payload, headers=headers, auth=auth, timeout=10
            )
            
            if 200 <= response.status_code < 300:
                return True, "SMS erfolgreich gesendet"
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}"
                
        except Exception as e:
            return False, f"SMS-Fehler: {str(e)}"

# =============================================================================
# EMAIL SERVICE
# =============================================================================

class EmailService:
    """Gmail SMTP Service mit ICS-Unterstützung"""
    
    def __init__(self):
        self.gmail_user = st.secrets.get("GMAIL_USER", "")
        self.gmail_password = st.secrets.get("GMAIL_APP_PASSWORD", "")
        self.from_name = st.secrets.get("FROM_NAME", "Dienstplan+ Cloud")
        self.enabled = bool(
            self.gmail_user and self.gmail_password and 
            st.secrets.get("ENABLE_EMAIL", True)
        )
    
    def send_email(self, to_email, subject, body, attachments=None):
        """E-Mail senden"""
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
            
            # Via Gmail SMTP senden
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            return True, "E-Mail erfolgreich gesendet"
            
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"

# =============================================================================
# BACKUP SERVICE
# =============================================================================

class BackupService:
    """Automatischer Backup-Service mit APScheduler"""
    
    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.scheduler = None
        self.scheduler_running = False
        self.lock = threading.Lock()
    
    def start_scheduler(self):
        """Starte Backup-Scheduler"""
        with self.lock:
            if self.scheduler_running:
                return
            
            if not st.secrets.get("ENABLE_DAILY_BACKUP", True):
                return
                
            if not self.email_service.enabled:
                return
        
        try:
            self.scheduler = BackgroundScheduler(
                timezone=TIMEZONE,
                daemon=True
            )
            
            # Tägliches Backup um 20:00
            self.scheduler.add_job(
                func=self._daily_backup_job,
                trigger=CronTrigger(hour=20, minute=0),
                id="daily_backup",
                replace_existing=True,
                max_instances=1
            )
            
            self.scheduler.start()
            
            with self.lock:
                self.scheduler_running = True
                
        except Exception:
            with self.lock:
                self.scheduler_running = False
    
    def _daily_backup_job(self):
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
            
            if cursor.fetchone()[0] == 0:
                success = self._send_daily_backup()
                status = "success" if success else "failed"
                
                cursor.execute('''
                    INSERT INTO backup_log (backup_date, status, details)
                    VALUES (?, ?, ?)
                ''', (today, status, "Automated daily backup"))
                conn.commit()
            
            conn.close()
            
        except Exception as e:
            print(f"Daily backup error: {e}")
    
    def _send_daily_backup(self):
        """Tägliches Backup per E-Mail senden"""
        try:
            # Backup erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Info-Datei
                info_content = f"""Dienstplan+ Cloud v{VERSION} - Tägliches Backup

Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Zeitzone: {TIMEZONE_STR}

Dieses Backup enthält alle App-Daten:
- Benutzer und Buchungen
- Favoriten/Watchlist
- Audit-Logs
- System-Konfiguration

Zum Wiederherstellen die ZIP-Datei im Admin-Panel hochladen.
"""
                zip_file.writestr("README.txt", info_content)
            
            zip_buffer.seek(0)
            
            # E-Mail senden
            backup_email = st.secrets.get("BACKUP_EMAIL", self.email_service.gmail_user)
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
            print(f"Backup creation error: {e}")
            return False

# =============================================================================
# HELPER FUNKTIONEN
# =============================================================================

def get_week_start(target_date=None):
    """Wochenstart (Montag) berechnen"""
    if target_date is None:
        target_date = datetime.now().date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()
    
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    return week_start

def get_slot_date(week_start, day_name):
    """Datum für Slot basierend auf Wochentag"""
    day_mapping = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    day_offset = day_mapping.get(day_name, 0)
    slot_date = week_start + timedelta(days=day_offset)
    return slot_date.strftime('%Y-%m-%d')

def is_holiday(date_str):
    """Prüfen ob Feiertag"""
    return date_str in HOLIDAYS

def get_holiday_name(date_str):
    """Feiertagsname laden"""
    return HOLIDAYS.get(date_str, "Feiertag")

def is_closed_period(date_str):
    """Prüfen ob Sperrzeit"""
    check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    for period in CLOSED_PERIODS:
        start_date = datetime.strptime(period['start'], '%Y-%m-%d').date()
        end_date = datetime.strptime(period['end'], '%Y-%m-%d').date()
        
        if start_date <= check_date <= end_date:
            return True
    
    return False

def format_german_date(date_str):
    """Datum deutsch formatieren"""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except:
        return date_str

# =============================================================================
# STREAMLIT APP KONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Dienstplan+ Cloud v3.0",
    page_icon="🏊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
}
.warning-card {
    background-color: #fff3cd;
    border: 1px solid #ffeeba;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
}
.info-card {
    background-color: #d1ecf1;
    border: 1px solid #bee5eb;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# SESSION STATE INITIALISIERUNG
# =============================================================================

# Services initialisieren
if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

if "sms_service" not in st.session_state:
    st.session_state.sms_service = WebSMSService()

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

# UI State
if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "current_week_start" not in st.session_state:
    st.session_state.current_week_start = get_week_start()

# =============================================================================
# MAIN APP
# =============================================================================

def main():
    """Hauptanwendung"""
    
    # Sidebar Navigation
    st.sidebar.title("🏊 Dienstplan+ Cloud")
    st.sidebar.markdown(f"**Version {VERSION}** (WebSMS Edition)")
    
    # Service Status in Sidebar
    if st.sidebar.checkbox("🔧 Service Status"):
        sms_status = "🟢" if st.session_state.sms_service.enabled else "🔴"
        email_status = "🟢" if st.session_state.email_service.enabled else "🔴"
        backup_status = "🟢" if st.session_state.backup_service.scheduler_running else "🔴"
        
        st.sidebar.markdown(f"""
        **Services:**
        - {sms_status} WebSMS
        - {email_status} Gmail SMTP
        - {backup_status} Auto-Backup
        """)
    
    # Hauptnavigation
    if st.session_state.current_user is None:
        show_auth_page()
    else:
        # Angemeldete Benutzer
        user = st.session_state.current_user
        
        # Logout Button in Sidebar
        if st.sidebar.button("🚪 Abmelden"):
            st.session_state.db.log_action(user['id'], 'logout', 'User logged out')
            st.session_state.current_user = None
            st.rerun()
        
        st.sidebar.markdown(f"**Angemeldet als:** {user['name']}")
        st.sidebar.markdown(f"**Rolle:** {user['role'].title()}")
        
        # Navigation Tabs
        if user['role'] == 'admin':
            tabs = st.sidebar.radio(
                "Navigation",
                ["📅 Terminplan", "👥 Team-Management", "⚙️ Admin-Panel", "👤 Profil", "ℹ️ Informationen"],
                key="main_nav"
            )
        else:
            tabs = st.sidebar.radio(
                "Navigation", 
                ["📅 Terminplan", "👤 Profil", "ℹ️ Informationen"],
                key="main_nav"
            )
        
        # Seiten routing
        if tabs == "📅 Terminplan":
            show_schedule_page()
        elif tabs == "👥 Team-Management" and user['role'] == 'admin':
            show_team_management_page()
        elif tabs == "⚙️ Admin-Panel" and user['role'] == 'admin':
            show_admin_panel_page()
        elif tabs == "👤 Profil":
            show_profile_page()
        elif tabs == "ℹ️ Informationen":
            show_information_page()

def show_auth_page():
    """Authentifizierungsseite (Login/Register)"""
    st.markdown("# 🔐 Willkommen bei Dienstplan+ Cloud")
    st.markdown("**Professionelle Dienstplanung für Ihr Team**")
    
    tab1, tab2 = st.tabs(["🔑 Anmelden", "📝 Registrieren"])
    
    with tab1:
        st.markdown("### 🔑 Anmelden")
        
        with st.form("login_form"):
            email = st.text_input("📧 E-Mail Adresse", placeholder="ihre.email@beispiel.de")
            password = st.text_input("🔒 Passwort", type="password")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                login_submitted = st.form_submit_button("Anmelden", type="primary", use_container_width=True)
            
            if login_submitted:
                if not email or not password:
                    st.error("❌ Bitte alle Felder ausfüllen")
                    return
                
                user = st.session_state.db.authenticate_user(email, password)
                if user:
                    st.session_state.current_user = user
                    st.session_state.current_week_start = get_week_start()
                    st.session_state.db.log_action(user['id'], 'login', 'User logged in')
                    st.success(f"✅ Willkommen, {user['name']}! 🎉")
                    st.rerun()
                else:
                    st.error("❌ Ungültige Anmeldedaten")
    
    with tab2:
        st.markdown("### 👥 Neuen Account erstellen")
        
        with st.form("register_form"):
            reg_name = st.text_input("👤 Vollständiger Name", placeholder="Max Mustermann")
            reg_email = st.text_input("📧 E-Mail Adresse", placeholder="max@beispiel.de")
            reg_phone = st.text_input("📱 Telefonnummer", placeholder="+49 151 12345678",
                                    help="Diese Nummer wird für SMS-Erinnerungen verwendet.")
            reg_password = st.text_input("🔒 Passwort", type="password", help="Mindestens 6 Zeichen")
            reg_password_confirm = st.text_input("🔒 Passwort wiederholen", type="password")
            
            sms_consent = st.checkbox("📱 SMS-Erinnerungen erhalten (empfohlen)", value=True)
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                register_submitted = st.form_submit_button("Account erstellen", type="primary", use_container_width=True)
            
            if register_submitted:
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
                        st.session_state.current_week_start = get_week_start()
                        st.session_state.db.log_action(user_id, 'account_created', f'New user registered: {reg_name}')
                        st.success("✅ Account erfolgreich erstellt! Sie sind automatisch eingeloggt.")
                        st.balloons()
                        st.rerun()
                else:
                    st.error("❌ E-Mail bereits registriert")

def show_schedule_page():
    """Terminplan-Seite"""
    user = st.session_state.current_user
    week_start = st.session_state.current_week_start
    week_end = week_start + timedelta(days=6)
    kw = week_start.isocalendar()[1]
    
    # Header
    st.markdown("# 📅 Terminplan")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Vorherige Woche"):
            st.session_state.current_week_start = week_start - timedelta(days=7)
            st.rerun()
    
    with col2:
        st.markdown(f"### KW {kw} — {format_german_date(week_start.strftime('%Y-%m-%d'))} bis {format_german_date(week_end.strftime('%Y-%m-%d'))}")
    
    with col3:
        if st.button("Nächste Woche ➡️"):
            st.session_state.current_week_start = week_start + timedelta(days=7)
            st.rerun()
    
    # Heute Button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("📍 Aktuelle Woche"):
            st.session_state.current_week_start = get_week_start()
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
    
    # Slot-Karten für die Woche
    for slot in WEEKLY_SLOTS:
        date_str = get_slot_date(week_start, slot['day'])
        
        # Prüfe Feiertag
        if is_holiday(date_str):
            holiday_name = get_holiday_name(date_str)
            st.markdown(f"""
            <div class="warning-card">
                <h4>🎄 {slot['day_name']}, {format_german_date(date_str)}</h4>
                <p><strong>Feiertag:</strong> {holiday_name}</p>
                <p>❌ Keine Schichten an diesem Tag</p>
            </div>
            """, unsafe_allow_html=True)
            continue
        
        # Prüfe Sperrzeit
        if is_closed_period(date_str):
            st.markdown(f"""
            <div class="warning-card">
                <h4>🏊♂️ {slot['day_name']}, {format_german_date(date_str)}</h4>
                <p><strong>Hallenbad geschlossen - Sommerpause</strong></p>
                <p>❌ Keine Buchungen möglich (Juni - September)</p>
            </div>
            """, unsafe_allow_html=True)
            continue
        
        # Lade Buchungsinformationen
        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
        is_favorite = st.session_state.db.is_favorite(user['id'], slot['id'], date_str)
        
        # Container für Slot-Karte
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if bookings:
                    # Slot ist belegt
                    booking = bookings[0]
                    is_own_booking = booking['user_id'] == user['id']
                    
                    if is_own_booking:
                        st.markdown(f"""
                        <div class="info-card">
                            <h4>✅ {slot['day_name']}, {format_german_date(date_str)}</h4>
                            <p><strong>Gebucht von Ihnen</strong></p>
                            <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div style="background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 0.375rem; padding: 1rem; margin: 1rem 0;">
                            <h4>📋 {slot['day_name']}, {format_german_date(date_str)}</h4>
                            <p><strong>Gebucht von:</strong> {booking['user_name']}</p>
                            <p>⚠️ Schicht bereits vergeben</p>
                            <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Slot ist frei
                    st.markdown(f"""
                    <div class="success-card">
                        <h4>✨ {slot['day_name']}, {format_german_date(date_str)}</h4>
                        <p><strong>Verfügbar</strong></p>
                        <p>💡 Klicken Sie auf "Buchen" um diese Schicht zu übernehmen</p>
                        <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            with col2:
                # Favoriten-Stern
                star_text = "⭐ Favorit" if is_favorite else "☆ Favorit"
                if st.button(star_text, key=f"fav_{slot['id']}_{date_str}"):
                    if is_favorite:
                        st.session_state.db.remove_favorite(user['id'], slot['id'], date_str)
                        st.success("Aus Favoriten entfernt")
                    else:
                        st.session_state.db.add_favorite(user['id'], slot['id'], date_str)
                        st.success("Zu Favoriten hinzugefügt")
                    st.rerun()
                
                if bookings:
                    booking = bookings[0]
                    if booking['user_id'] == user['id']:
                        # Storno-Button für eigene Buchungen
                        if st.button("❌ Stornieren", key=f"cancel_{booking['id']}"):
                            st.session_state.db.cancel_booking(booking['id'], user['id'])
                            st.success("✅ Buchung storniert")
                            st.rerun()
                else:
                    # Buchungs-Button
                    if st.button("📝 Buchen", key=f"book_{slot['id']}_{date_str}", type="primary"):
                        success, result = st.session_state.db.create_booking(user['id'], slot['id'], date_str)
                        if success:
                            st.success(f"✅ Schicht erfolgreich gebucht für {format_german_date(date_str)}")
                            # Favorit entfernen falls vorhanden
                            if is_favorite:
                                st.session_state.db.remove_favorite(user['id'], slot['id'], date_str)
                            st.rerun()
                        else:
                            st.error(f"❌ Buchung fehlgeschlagen: {result}")

def show_team_management_page():
    """Team-Management-Seite (nur Admin)"""
    st.markdown("# 👥 Team-Management")
    
    # Team-Statistiken
    all_users = st.session_state.db.get_all_users()
    all_bookings = st.session_state.db.get_all_bookings()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Team-Mitglieder", len(all_users))
    
    with col2:
        admin_count = len([u for u in all_users if u['role'] == 'admin'])
        st.metric("Administratoren", admin_count)
    
    with col3:
        active_bookings = len([b for b in all_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= datetime.now().date()])
        st.metric("Aktive Buchungen", active_bookings)
    
    with col4:
        week_start = st.session_state.current_week_start
        week_end = week_start + timedelta(days=6)
        week_bookings = [b for b in all_bookings if week_start <= datetime.strptime(b['date'], '%Y-%m-%d').date() <= week_end]
        st.metric("Diese Woche", len(week_bookings))
    
    st.markdown("---")
    
    # Team-Mitglieder
    st.markdown("## 👤 Team-Mitglieder")
    
    for user in all_users:
        with st.expander(f"{user['name']} ({user['role'].title()})", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"""
                **📧 E-Mail:** {user['email']}
                
                **📱 Telefon:** {user['phone']}
                
                **📅 Registriert:** {user['created_at'][:10] if user['created_at'] else 'Unbekannt'}
                """)
            
            with col2:
                sms_status = "✅ Aktiviert" if user.get('sms_opt_in', False) else "❌ Deaktiviert"
                email_status = "✅ Aktiviert" if user.get('email_opt_in', True) else "❌ Deaktiviert"
                
                st.markdown(f"""
                **📱 SMS:** {sms_status}
                
                **📧 E-Mail:** {email_status}
                
                **🎯 Status:** {'🟢 Aktiv' if user.get('active', True) else '🔴 Inaktiv'}
                """)
    
    st.markdown("---")
    
    # Aktuelle Woche Übersicht
    week_start = st.session_state.current_week_start
    week_end = week_start + timedelta(days=6)
    kw = week_start.isocalendar()[1]
    
    st.markdown(f"## 📊 Aktuelle Woche (KW {kw})")
    st.markdown(f"**{format_german_date(week_start.strftime('%Y-%m-%d'))} bis {format_german_date(week_end.strftime('%Y-%m-%d'))}**")
    
    for slot in WEEKLY_SLOTS:
        date_str = get_slot_date(week_start, slot['day'])
        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown(f"**{slot['day_name']}, {format_german_date(date_str)}**")
            st.markdown(f"{slot['start_time']} - {slot['end_time']} Uhr")
        
        with col2:
            if bookings:
                st.success(f"✅ {bookings[0]['user_name']}")
            elif is_holiday(date_str):
                st.info("🎄 Feiertag")
            elif is_closed_period(date_str):
                st.warning("🏊♂️ Geschlossen")
            else:
                st.error("❌ UNBESETZT")

def show_admin_panel_page():
    """Admin-Panel-Seite"""
    st.markdown("# ⚙️ System-Administration")
    
    # System-Status
    st.markdown("## 🔧 System-Status")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ✅ Services")
        
        if st.session_state.sms_service.enabled:
            st.success("🟢 **WebSMS Service** - Konfiguriert und aktiv")
        else:
            st.error("🔴 **WebSMS Service** - Nicht konfiguriert")
        
        if st.session_state.email_service.enabled:
            st.success("🟢 **Gmail SMTP Service** - Konfiguriert und aktiv")
        else:
            st.error("🔴 **Gmail SMTP Service** - Nicht konfiguriert")
        
        if st.session_state.backup_service.scheduler_running:
            st.success("🟢 **Auto-Backup** - Täglich 20:00 Uhr aktiv")
        else:
            st.error("🔴 **Auto-Backup** - Nicht aktiv")
    
    with col2:
        st.markdown("### ⚡ Schnell-Aktionen")
        
        if st.button("💾 Sofort-Backup erstellen"):
            if st.session_state.backup_service._send_daily_backup():
                st.success("✅ Backup erfolgreich erstellt und versendet")
            else:
                st.error("❌ Backup-Erstellung fehlgeschlagen")
        
        if st.button("📧 Test-E-Mail senden"):
            if st.session_state.email_service.enabled:
                success, message = st.session_state.email_service.send_email(
                    st.session_state.current_user['email'],
                    "Dienstplan+ Test-E-Mail",
                    "Dies ist eine Test-E-Mail vom Dienstplan+ System."
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
                    "Test-SMS vom Dienstplan+ System"
                )
                if success:
                    st.success("✅ Test-SMS gesendet")
                else:
                    st.error(f"❌ SMS-Fehler: {message}")
            else:
                st.error("❌ SMS-Service nicht verfügbar")
    
    st.markdown("---")
    
    # Backup-Verwaltung
    st.markdown("## 💾 Backup-Verwaltung")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📥 Backup erstellen")
        
        if st.button("🔽 Vollständiges Backup herunterladen", type="primary"):
            try:
                backup_data = st.session_state.db.create_backup()
                
                # ZIP erstellen
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    zip_file.writestr(backup_filename, backup_data)
                
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
        st.markdown("### 📤 Backup wiederherstellen")
        st.warning("⚠️ **WARNUNG:** Überschreibt alle aktuellen Daten!")
        
        uploaded_file = st.file_uploader(
            "Backup-ZIP-Datei auswählen:",
            type=['zip'],
            key="restore_backup"
        )
        
        if uploaded_file is not None:
            if st.button("⚠️ RESTORE - Alle Daten ersetzen", type="secondary"):
                st.error("🚧 Restore-Funktion in dieser Demo-Version nicht implementiert")
    
    st.markdown("---")
    
    # Audit-Log
    st.markdown("## 📋 Audit-Log (Letzte 50 Einträge)")
    
    logs = st.session_state.db.get_audit_log(50)
    
    if logs:
        # DataFrame für bessere Darstellung
        df = pd.DataFrame(logs)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%d.%m.%Y %H:%M:%S')
        
        # Nur relevante Spalten anzeigen
        display_df = df[['timestamp', 'user_name', 'action', 'details']].copy()
        display_df.columns = ['Zeitstempel', 'Benutzer', 'Aktion', 'Details']
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("📝 Noch keine Log-Einträge vorhanden")

def show_profile_page():
    """Profil-Seite"""
    user = st.session_state.current_user
    
    st.markdown("# 👤 Mein Profil")
    
    # Profil-Informationen
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("## 📝 Profil-Daten")
        st.markdown(f"""
        **👤 Name:** {user['name']}
        
        **📧 E-Mail:** {user['email']}
        
        **📱 Telefon:** {user['phone']}
        
        **🎭 Rolle:** {user['role'].title()}
        """)
    
    with col2:
        st.markdown("## ⚙️ Einstellungen")
        
        sms_status = "✅ Aktiviert" if user.get('sms_opt_in', False) else "❌ Deaktiviert"
        email_status = "✅ Aktiviert" if user.get('email_opt_in', True) else "❌ Deaktiviert"
        
        st.markdown(f"""
        **📱 SMS-Benachrichtigungen:** {sms_status}
        
        **📧 E-Mail-Benachrichtigungen:** {email_status}
        
        **🎯 Account-Status:** {'🟢 Aktiv' if user.get('active', True) else '🔴 Inaktiv'}
        """)
    
    st.markdown("---")
    
    # Meine Buchungen
    st.markdown("## 📅 Meine Buchungen")
    
    user_bookings = st.session_state.db.get_user_bookings(user['id'])
    
    if user_bookings:
        future_bookings = [b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= datetime.now().date()]
        
        if future_bookings:
            st.markdown("### 🔮 Zukünftige Schichten")
            for booking in future_bookings[:10]:  # Letzte 10
                slot = next((s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id']), None)
                if slot:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{slot['day_name']}, {format_german_date(booking['date'])}**")
                        st.markdown(f"{slot['start_time']} - {slot['end_time']} Uhr")
                    with col2:
                        if st.button("❌ Stornieren", key=f"cancel_profile_{booking['id']}"):
                            st.session_state.db.cancel_booking(booking['id'], user['id'])
                            st.success("✅ Buchung storniert")
                            st.rerun()
        else:
            st.info("📝 Keine zukünftigen Buchungen vorhanden")
    else:
        st.info("📝 Noch keine Buchungen vorhanden")
    
    st.markdown("---")
    
    # Service-Tests (falls Services aktiv)
    if user['role'] == 'admin' or st.secrets.get("ENABLE_USER_SERVICE_TESTS", False):
        st.markdown("## 🧪 Service-Tests")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📱 SMS-Test")
            if st.session_state.sms_service.enabled:
                st.success("🟢 SMS-Service verfügbar")
                if st.button("📤 Test-SMS senden", key="profile_test_sms"):
                    success, message = st.session_state.sms_service.send_sms(
                        user['phone'], "Test-SMS vom Dienstplan+ System"
                    )
                    if success:
                        st.success("✅ Test-SMS gesendet")
                        st.session_state.db.log_action(user['id'], 'test_sms_sent', 'Profile SMS test successful')
                    else:
                        st.error(f"❌ SMS-Fehler: {message}")
                        st.session_state.db.log_action(user['id'], 'test_sms_failed', f'Profile SMS test failed: {message}')
            else:
                st.error("🔴 SMS-Service nicht konfiguriert")
        
        with col2:
            st.markdown("### 📧 E-Mail-Test")
            if st.session_state.email_service.enabled:
                st.success("🟢 E-Mail-Service verfügbar")
                if st.button("📤 Test-E-Mail senden", key="profile_test_email"):
                    success, message = st.session_state.email_service.send_email(
                        user['email'],
                        "Dienstplan+ Test-E-Mail",
                        f"Hallo {user['name']},\n\ndies ist eine Test-E-Mail von Ihrem Dienstplan+ System.\n\nMit freundlichen Grüßen\nIhr Dienstplan+ Team"
                    )
                    if success:
                        st.success("✅ Test-E-Mail gesendet")
                        st.session_state.db.log_action(user['id'], 'test_email_sent', 'Profile email test successful')
                    else:
                        st.error(f"❌ E-Mail-Fehler: {message}")
                        st.session_state.db.log_action(user['id'], 'test_email_failed', f'Profile email test failed: {message}')
            else:
                st.error("🔴 E-Mail-Service nicht konfiguriert")

def show_information_page():
    """Informations-Seite"""
    st.markdown("# ℹ️ Informationen")
    
    tab1, tab2 = st.tabs(["📋 Schicht-Informationen", "🚨 Rettungskette"])
    
    with tab1:
        st.markdown("## 📋 Schicht-Checkliste")
        
        st.markdown("""
        ### Vor Schichtbeginn:
        1. **Kasse holen** - Schlüssel im Büro abholen
        2. **Hallenbad aufsperren** - 30 Minuten vor Öffnung
        3. **Technik prüfen** - Beleuchtung, Heizung, Pumpen
        4. **Sicherheit checken** - Erste-Hilfe-Kasten, AED-Gerät
        
        ### Während der Schicht:
        - **Aufsichtspflicht** wahrnehmen
        - **Badegäste** freundlich betreuen
        - **Ordnung** im Bad aufrechterhalten
        - **Kassierung** korrekt durchführen
        
        ### Nach Schichtende:
        1. **Bad kontrollieren** - alle Bereiche prüfen
        2. **Kasse abrechnen** - Einnahmen zählen
        3. **Hallenbad abschließen** - alle Türen/Fenster
        4. **Kasse zurückbringen** - sicher im Büro verstauen
        
        ### Besonderheiten:
        - Bei **Feiertagen** gelten andere Öffnungszeiten
        - Bei **Veranstaltungen** Sonderregelungen beachten
        - Bei **Problemen** sofort Leitung kontaktieren
        """)
    
    with tab2:
        st.markdown("## 🚨 Rettungskette Hallenbad")
        
        st.warning("⚠️ **Wichtig:** Diese Informationen ersetzen keine Erste-Hilfe-Ausbildung!")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            ### 📞 Notrufnummern
            **🚨 Notruf:** 112
            
            **🏥 Rettungsdienst:** 112
            
            **👮 Polizei:** 110
            
            **☠️ Giftnotruf:** 089 19240
            
            ### 🏊♂️ Hallenbad-Kontakte
            **📞 Leitung:** [Nummer eintragen]
            
            **🔧 Hausmeister:** [Nummer eintragen]
            
            **🏥 Nächstes Krankenhaus:** [Nummer eintragen]
            """)
        
        with col2:
            st.markdown("""
            ### 🚨 Rettungsablauf
            1. **Situation sichern** - Gefahren beseitigen
            2. **Notruf absetzen** - 112 wählen
            3. **Erste Hilfe leisten** - bis Hilfe eintrifft
            4. **AED einsetzen** - falls verfügbar
            
            ### 📍 Notfall-Equipment
            **🚨 AED-Gerät:** Eingangsbereich
            
            **🎒 Erste-Hilfe-Kasten:** Büro
            
            **🚑 Notfallkoffer:** Pool-Bereich
            
            **🧊 Kühlpacks:** Büro-Kühlschrank
            """)
        
        st.markdown("---")
        st.info("💡 **Wichtig:** Regelmäßige Erste-Hilfe-Schulungen sind für alle Mitarbeiter empfohlen!")

# App starten
if __name__ == "__main__":
    main()
