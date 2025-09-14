import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
from twilio.rest import Client
import uuid
import io
import smtplib
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import calendar
import os
import tempfile

# Seite konfigurieren
st.set_page_config(
    page_title="Dienstplan+ Cloud",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS für professionelles Design mit besseren Kontrasten
st.markdown("""
<style>
    /* Toolbar und Footer verstecken */
    .stApp > header {
        display: none;
    }
    
    .stApp > .main > div > div > div > section > .stVerticalBlock > div > div:nth-child(1) > div > div > div > .stMarkdown > div > p > a {
        display: none;
    }
    
    div[data-testid="stToolbar"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    
    div[data-testid="stDecoration"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    
    div[data-testid="stStatusWidget"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    
    #MainMenu {
        visibility: hidden;
        height: 0%;
    }
    
    header[data-testid="stHeader"] {
        visibility: hidden;
        height: 0%;
    }
    
    footer {
        visibility: hidden;
        height: 0%;
    }
    
    /* Modernes Design mit hohen Kontrasten */
    .main > div {
        padding-top: 1rem;
    }
    
    .stButton > button {
        background-color: #1e40af;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 600;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        background-color: #1e3a8a;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        transform: translateY(-1px);
    }
    
    /* Wochenkopf hervorheben */
    .week-header {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
        text-align: center;
    }
    
    .week-header h2 {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    .week-header .calendar-week {
        font-size: 1.2rem;
        font-weight: 600;
        margin-top: 0.5rem;
        opacity: 0.9;
    }
    
    /* Verbesserte Karten mit höheren Kontrasten */
    .shift-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 6px solid #1e40af;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transition: transform 0.2s ease;
    }
    
    .shift-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    }
    
    .holiday-card {
        background: #fef2f2;
        padding: 1rem;
        border-radius: 8px;
        border-left: 6px solid #dc2626;
        margin: 0.5rem 0;
        color: #7f1d1d;
        font-weight: 500;
    }
    
    .closed-card {
        background: #fef3c7;
        padding: 2rem;
        border-radius: 12px;
        border-left: 6px solid #f59e0b;
        margin: 1rem 0;
        color: #92400e;
        font-weight: 600;
        text-align: center;
        box-shadow: 0 4px 8px rgba(245, 158, 11, 0.2);
    }
    
    .available-slot {
        background: #f0fdf4;
        border-left: 6px solid #16a34a;
        color: #14532d;
    }
    
    .booked-slot {
        background: #fef3c7;
        border-left: 6px solid #d97706;
        color: #92400e;
    }
    
    .user-slot {
        background: #eff6ff;
        border-left: 6px solid #2563eb;
        color: #1e40af;
    }
    
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 2px solid #e5e7eb;
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 8px 16px rgba(0,0,0,0.15);
    }
    
    .success-message {
        padding: 1rem;
        background: #f0fdf4;
        border: 2px solid #16a34a;
        border-radius: 8px;
        color: #14532d;
        font-weight: 500;
    }
    
    .error-message {
        padding: 1rem;
        background: #fef2f2;
        border: 2px solid #dc2626;
        border-radius: 8px;
        color: #7f1d1d;
        font-weight: 500;
    }
    
    .info-message {
        padding: 1rem;
        background: #eff6ff;
        border: 2px solid #3b82f6;
        border-radius: 8px;
        color: #1e40af;
        font-weight: 500;
    }
    
    .warning-message {
        padding: 1rem;
        background: #fef3c7;
        border: 2px solid #f59e0b;
        border-radius: 8px;
        color: #92400e;
        font-weight: 500;
    }
    
    /* Dark Mode Anpassungen */
    @media (prefers-color-scheme: dark) {
        .shift-card {
            background: #1f2937;
            color: #f9fafb;
            border-left-color: #60a5fa;
        }
        
        .metric-card {
            background: #1f2937;
            color: #f9fafb;
            border-color: #374151;
        }
        
        .available-slot {
            background: #064e3b;
            color: #d1fae5;
        }
        
        .booked-slot {
            background: #451a03;
            color: #fed7aa;
        }
        
        .user-slot {
            background: #1e3a8a;
            color: #dbeafe;
        }
        
        .holiday-card {
            background: #7f1d1d;
            color: #fecaca;
        }
        
        .closed-card {
            background: #451a03;
            color: #fed7aa;
        }
    }
    
    /* Bessere Lesbarkeit für Formularelemente */
    .stTextInput > div > div > input {
        color: #1f2937;
        background-color: white;
        border: 2px solid #d1d5db;
        border-radius: 8px;
        font-weight: 500;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
    
    /* Tab-Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #f8fafc;
        border-radius: 8px;
        color: #475569;
        font-weight: 600;
        border: 2px solid #e2e8f0;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1e40af;
        color: white;
        border-color: #1e40af;
    }
    
    /* Calendar specific styling */
    .calendar-container {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    
    .calendar-legend {
        display: flex;
        gap: 1rem;
        margin: 1rem 0;
        flex-wrap: wrap;
    }
    
    .legend-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: #f8fafc;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        font-size: 0.875rem;
        font-weight: 500;
    }
    
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
    }
    
    .free-dot { background-color: #16a34a; }
    .booked-dot { background-color: #d97706; }
    .holiday-dot { background-color: #dc2626; }
    
    /* Admin-only sections styling */
    .admin-section {
        background: linear-gradient(135deg, #fef7cd 0%, #fbbf24 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 2px solid #f59e0b;
        box-shadow: 0 4px 8px rgba(245, 158, 11, 0.2);
    }
    
    .admin-section h4 {
        color: #92400e;
        margin: 0 0 1rem 0;
        font-weight: 700;
    }
    
    /* Sick Button Styling */
    .sick-button button {
        background-color: #dc2626 !important;
        color: white !important;
    }
    
    .sick-button button:hover {
        background-color: #b91c1c !important;
    }
    
    /* Admin Action Buttons */
    .admin-action-button button {
        background-color: #f59e0b !important;
        color: white !important;
    }
    
    .admin-action-button button:hover {
        background-color: #d97706 !important;
    }
</style>
""", unsafe_allow_html=True)

# Datenbank-Funktionen
class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def get_connection(self):
        return sqlite3.connect('dienstplan.db', check_same_thread=False)
    
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
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Audit Log Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
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
                slot_id INTEGER,
                notification_date DATE,
                notification_type TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slot_id, notification_date, notification_type)
            )
        ''')
        
        # Initial Admin aus Secrets erstellen
        self._create_initial_admin()
        
        # Standard Templates anlegen
        self._create_default_templates()
        
        conn.commit()
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
                    ''', (admin_email, "+49 151 99999999", "Toni Stemplinger", password_hash, "admin", 1, 1))
                    
                    conn.commit()
                    
                    # Einmalige Ausgabe der Admin-Daten (nur beim ersten Start)
                    if 'admin_credentials_shown' not in st.session_state:
                        st.session_state.admin_credentials_shown = True
                        st.success(f"""
                        🎯 **INITIAL-ADMIN ERFOLGREICH ERSTELLT:**
                        
                        👤 **Name:** Toni Stemplinger  
                        📧 **E-Mail:** {admin_email}  
                        🔒 **Passwort:** {admin_password}  
                        
                        ⚠️ **WICHTIG:** Diese Daten werden nur EINMAL angezeigt!  
                        Bitte sofort das Passwort im Profil ändern.
                        """)
            except Exception as e:
                pass  # Secrets nicht verfügbar, normaler Betrieb
        
        conn.close()
    
    def _create_default_templates(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # SMS Templates
        cursor.execute('SELECT COUNT(*) FROM reminder_templates')
        if cursor.fetchone()[0] == 0:
            templates = [
                ('24h Erinnerung', '24_hours', 
                 'Hallo {{name}}! Erinnerung: Du hast morgen eine Schicht am {{datum}} von {{slot}}. Bei Absage bitte melden.',
                 'Hallo {{name}}! 👋\n\nErinnerung: Du hast morgen eine Schicht:\n📅 {{datum}}\n⏰ {{slot}}\n\nBei Fragen antworte einfach auf diese Nachricht.',
                 'Liebe/r {{name}},\n\nwir erinnern dich an deine Schicht morgen:\n\nDatum: {{datum}}\nZeit: {{slot}}\n\nViele Grüße\nDein Team'),
                ('1h Erinnerung', '1_hour',
                 'Hi {{name}}! Deine Schicht beginnt in 1 Stunde: {{datum}} {{slot}}. Bis gleich!',
                 'Hi {{name}}! ⏰\n\nIn einer Stunde beginnt deine Schicht:\n{{datum}} {{slot}}\n\nBis gleich!',
                 'Liebe/r {{name}},\n\nin einer Stunde beginnt deine Schicht:\n{{datum}} {{slot}}\n\nViel Erfolg!'),
                ('Krankmeldung', 'sick_notification',
                 'HINWEIS: {{name}} hat sich krank gemeldet und die Schicht am {{datum}} ({{slot}}) storniert. Bitte Ersatz organisieren.',
                 'HINWEIS: {{name}} hat sich krank gemeldet und die Schicht am {{datum}} ({{slot}}) storniert. Bitte Ersatz organisieren.',
                 ''),
                ('Unbelegt Warnung', '7_day_warning',
                 'WARNUNG: Die Schicht am {{datum}} ({{slot}}) ist 7 Tage vorher noch unbesetzt. Bitte prüfen.',
                 'WARNUNG: Die Schicht am {{datum}} ({{slot}}) ist 7 Tage vorher noch unbesetzt. Bitte prüfen.',
                 '')
            ]
            
            for template in templates:
                cursor.execute('''
                    INSERT INTO reminder_templates (name, timing, sms_template, whatsapp_template, email_template)
                    VALUES (?, ?, ?, ?, ?)
                ''', template)
        
        # E-Mail Templates
        cursor.execute('SELECT COUNT(*) FROM email_templates')
        if cursor.fetchone()[0] == 0:
            email_templates = [
                ('Einladung', 'booking_invite',
                 '[Dienstplan+] Einladung: {{slot}} - {{datum}}',
                 'Hallo {{name}},\n\nhier ist deine Kalender-Einladung für die Schicht am {{datum}} von {{slot}}.\n\nMit "Annehmen" im Kalender bestätigst du den Termin automatisch.\n\nViele Grüße\nDein Dienstplan+ Team'),
                ('Absage', 'booking_cancel',
                 '[Dienstplan+] Absage: {{slot}} - {{datum}}',
                 'Hallo {{name}},\n\ndie Schicht am {{datum}} von {{slot}} wurde storniert.\n\nDiese Nachricht aktualisiert oder entfernt den Kalendereintrag automatisch.\n\nViele Grüße\nDein Dienstplan+ Team'),
                ('Umbuchung', 'booking_reschedule',
                 '[Dienstplan+] Umbuchung: {{slot}} - {{datum}}',
                 'Hallo {{name}},\n\ndeine Schicht wurde umgebucht auf: {{datum}} von {{slot}}.\n\nBitte prüfe deinen Kalender für die Aktualisierung.\n\nViele Grüße\nDein Dienstplan+ Team')
            ]
            
            for template in email_templates:
                cursor.execute('''
                    INSERT INTO email_templates (name, template_type, subject_template, body_template)
                    VALUES (?, ?, ?, ?)
                ''', template)
        
        conn.commit()
        conn.close()
    
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
    
    def authenticate_user(self, email, password):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin
            FROM users 
            WHERE email = ? AND password_hash = ? AND active = 1
        ''', (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Admin-Whitelist prüfen (falls konfiguriert)
            admin_emails = st.secrets.get("ADMIN_EMAILS", [])
            if admin_emails and isinstance(admin_emails, list):
                if user[4] == 'admin' and email not in admin_emails:
                    # Admin-Rolle entziehen falls nicht in Whitelist
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
                'is_initial_admin': user[8]
            }
        return None
    
    def update_user_role(self, user_id, new_role):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
        conn.commit()
        conn.close()
    
    def can_manage_admins(self, user_id):
        """Nur der Initial-Admin kann andere Admins verwalten"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_initial_admin FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def get_user_by_id(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in, is_initial_admin
            FROM users WHERE id = ?
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
                'is_initial_admin': user[8]
            }
        return None
    
    def update_user_profile(self, user_id, name, phone, sms_opt_in):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET name = ?, phone = ?, sms_opt_in = ?
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
        
        # Prüfen ob User bereits an dem Tag gebucht hat
        cursor.execute('''
            SELECT COUNT(*) FROM bookings 
            WHERE user_id = ? AND booking_date = ? AND status = 'confirmed'
        ''', (user_id, booking_date))
        
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False, "Sie haben bereits eine Schicht an diesem Tag"
        
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
            cursor.execute('''
                DELETE FROM bookings 
                WHERE id = ? AND user_id = ?
            ''', (booking_id, user_id))
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
            SELECT b.id, b.user_id, u.name, u.phone, u.email
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.slot_id = ? AND b.booking_date = ? AND b.status = 'confirmed'
        ''', (slot_id, booking_date))
        
        bookings = cursor.fetchall()
        conn.close()
        
        return [{'id': b[0], 'user_id': b[1], 'user_name': b[2], 'phone': b[3], 'email': b[4]} for b in bookings]
    
    def get_user_bookings(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, slot_id, booking_date, status, created_at
            FROM bookings 
            WHERE user_id = ? AND status = 'confirmed'
            ORDER BY booking_date ASC
        ''', (user_id,))
        
        bookings = cursor.fetchall()
        conn.close()
        
        return [{'id': b[0], 'slot_id': b[1], 'date': b[2], 'status': b[3], 'created_at': b[4]} for b in bookings]
    
    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, active, created_at, is_initial_admin
            FROM users
            ORDER BY created_at DESC
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        return [{'id': u[0], 'email': u[1], 'phone': u[2], 'name': u[3], 'role': u[4], 'active': u[5], 'created_at': u[6], 'is_initial_admin': u[7]} for u in users]
    
    def get_all_bookings(self):
        """Alle Buchungen für Admin-Übersicht"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.slot_id, b.booking_date, b.user_id, u.name, u.email, u.phone
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.status = 'confirmed'
            ORDER BY b.booking_date ASC
        ''')
        
        bookings = cursor.fetchall()
        conn.close()
        
        return [{'id': b[0], 'slot_id': b[1], 'date': b[2], 'user_id': b[3], 'user_name': b[4], 'user_email': b[5], 'user_phone': b[6]} for b in bookings]
    
    def get_unbooked_slots_next_60_days(self):
        """Alle freien Slots der nächsten 60 Tage für Admin-Übersicht"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        today = datetime.now()
        end_date = today + timedelta(days=60)
        
        unbooked_slots = []
        
        # Durchlaufe alle Tage der nächsten 60 Tage
        current_date = today
        while current_date <= end_date:
            for slot in WEEKLY_SLOTS:
                # Prüfe ob dieser Wochentag zu diesem Slot passt
                if self._matches_slot_day(current_date, slot['day']):
                    date_str = current_date.strftime('%Y-%m-%d')
                    
                    # Prüfe ob Feiertag oder Sperrzeit
                    if not is_holiday(date_str) and not is_closed_period(date_str):
                        # Prüfe ob Slot belegt
                        cursor.execute('''
                            SELECT COUNT(*) FROM bookings 
                            WHERE slot_id = ? AND booking_date = ? AND status = 'confirmed'
                        ''', (slot['id'], date_str))
                        
                        if cursor.fetchone()[0] == 0:  # Slot ist frei
                            unbooked_slots.append({
                                'date': date_str,
                                'slot_id': slot['id'],
                                'day_name': slot['day_name'],
                                'start_time': slot['start_time'],
                                'end_time': slot['end_time'],
                                'weekday': current_date.strftime('%A')
                            })
            
            current_date += timedelta(days=1)
        
        conn.close()
        return unbooked_slots
    
    def _matches_slot_day(self, date_obj, slot_day):
        """Prüfe ob das Datum zum Slot-Wochentag passt"""
        day_mapping = {
            'tuesday': 1,   # Dienstag
            'friday': 4,    # Freitag
            'saturday': 5   # Samstag
        }
        return date_obj.weekday() == day_mapping.get(slot_day, -1)
    
    def check_7_day_warnings(self):
        """Prüfe unbelegte Slots in den nächsten 7 Tagen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        today = datetime.now()
        end_date = today + timedelta(days=7)
        
        warnings_to_send = []
        
        current_date = today + timedelta(days=1)  # Ab morgen prüfen
        while current_date <= end_date:
            for slot in WEEKLY_SLOTS:
                if self._matches_slot_day(current_date, slot['day']):
                    date_str = current_date.strftime('%Y-%m-%d')
                    
                    # Prüfe ob nicht Feiertag/Sperrzeit und unbelegte
                    if not is_holiday(date_str) and not is_closed_period(date_str):
                        cursor.execute('''
                            SELECT COUNT(*) FROM bookings 
                            WHERE slot_id = ? AND booking_date = ? AND status = 'confirmed'
                        ''', (slot['id'], date_str))
                        
                        if cursor.fetchone()[0] == 0:  # Slot ist frei
                            # Prüfe ob bereits Warnung gesendet
                            cursor.execute('''
                                SELECT COUNT(*) FROM notifications_sent
                                WHERE slot_id = ? AND notification_date = ? AND notification_type = '7_day_warning'
                            ''', (slot['id'], date_str))
                            
                            if cursor.fetchone()[0] == 0:  # Noch keine Warnung gesendet
                                warnings_to_send.append({
                                    'slot_id': slot['id'],
                                    'date': date_str,
                                    'slot_name': f"{slot['day_name']} {slot['start_time']}-{slot['end_time']}"
                                })
                                
                                # Markiere als gesendet
                                cursor.execute('''
                                    INSERT OR IGNORE INTO notifications_sent (slot_id, notification_date, notification_type)
                                    VALUES (?, ?, ?)
                                ''', (slot['id'], date_str, '7_day_warning'))
            
            current_date += timedelta(days=1)
        
        conn.commit()
        conn.close()
        
        return warnings_to_send
    
    def create_backup(self):
        """Erstelle Vollbackup der Datenbank"""
        conn = self.get_connection()
        
        # Alle Tabellen und Daten exportieren
        backup_data = {}
        
        tables = ['users', 'bookings', 'audit_log', 'reminder_templates', 'email_templates', 'notifications_sent']
        
        for table in tables:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM {table}')
            rows = cursor.fetchall()
            
            # Schema auch exportieren
            cursor.execute(f'PRAGMA table_info({table})')
            schema = cursor.fetchall()
            
            backup_data[table] = {
                'schema': schema,
                'data': rows
            }
        
        conn.close()
        
        # Als JSON serialisieren
        return json.dumps(backup_data, indent=2, default=str)
    
    def restore_backup(self, backup_json):
        """Stelle Backup wieder her"""
        try:
            backup_data = json.loads(backup_json)
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Foreign Keys temporär deaktivieren
            cursor.execute('PRAGMA foreign_keys=OFF')
            
            # Alle bestehenden Tabellen leeren
            tables = ['notifications_sent', 'audit_log', 'bookings', 'email_templates', 'reminder_templates', 'users']
            for table in tables:
                cursor.execute(f'DELETE FROM {table}')
            
            # Daten wiederherstellen
            for table_name, table_data in backup_data.items():
                if table_name in tables and 'data' in table_data:
                    schema = table_data['schema']
                    column_names = [col[1] for col in schema]
                    
                    for row in table_data['data']:
                        placeholders = ','.join(['?' for _ in row])
                        cursor.execute(f'INSERT INTO {table_name} VALUES ({placeholders})', row)
            
            # Foreign Keys wieder aktivieren
            cursor.execute('PRAGMA foreign_keys=ON')
            
            conn.commit()
            conn.close()
            
            return True, "Backup erfolgreich wiederhergestellt"
            
        except Exception as e:
            return False, f"Fehler beim Wiederherstellen: {str(e)}"
    
    def log_action(self, user_id, action, details):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        ''', (user_id, action, details))
        
        conn.commit()
        conn.close()

# SMS und E-Mail Services
class SMSService:
    def __init__(self):
        try:
            self.client = Client(
                st.secrets.get("TWILIO_ACCOUNT_SID", ""),
                st.secrets.get("TWILIO_AUTH_TOKEN", "")
            )
            self.from_number = st.secrets.get("TWILIO_PHONE_NUMBER", "")
            self.enabled = bool(self.from_number and st.secrets.get("TWILIO_ACCOUNT_SID"))
        except:
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
            self.enabled = bool(self.gmail_user and self.gmail_password)
        except:
            self.enabled = False
    
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
            
            # Via Gmail SMTP senden
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.gmail_user, self.gmail_password)
            
            server.send_message(msg)
            server.quit()
            
            return True, "E-Mail erfolgreich gesendet"
            
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"
    
    def generate_ics(self, booking, slot, user, method="REQUEST", sequence=0):
        """Generiere RFC-5545 konforme ICS-Datei"""
        booking_date = datetime.strptime(booking['date'], '%Y-%m-%d')
        start_time = datetime.strptime(slot['start_time'], '%H:%M').time()
        end_time = datetime.strptime(slot['end_time'], '%H:%M').time()
        
        start_dt = datetime.combine(booking_date, start_time)
        end_dt = datetime.combine(booking_date, end_time)
        
        # UTC Conversion (Europa/Berlin)
        # Vereinfacht: +1h im Winter, +2h im Sommer
        is_dst = booking_date.month >= 3 and booking_date.month <= 10
        utc_offset = timedelta(hours=2 if is_dst else 1)
        
        start_utc = start_dt - utc_offset
        end_utc = end_dt - utc_offset
        
        uid = f"booking-{booking['id']}-{booking['date']}@dienstplan-cloud.local"
        
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//DE
METHOD:{method}
BEGIN:VEVENT
UID:{uid}
DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}
DTSTART;TZID=Europe/Berlin:{start_dt.strftime('%Y%m%dT%H%M%S')}
DTEND;TZID=Europe/Berlin:{end_dt.strftime('%Y%m%dT%H%M%S')}
SUMMARY:Schicht - {slot['day_name']}
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']} Uhr
LOCATION:Arbeitsplatz
ORGANIZER;CN={self.from_name}:mailto:{self.gmail_user}
ATTENDEE;CN={user['name']};RSVP=TRUE:mailto:{user['email']}
STATUS:CONFIRMED
SEQUENCE:{sequence}
CREATED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
LAST-MODIFIED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
END:VEVENT
END:VCALENDAR"""
        
        return ics_content.strip()

# App-Konfiguration
WEEKLY_SLOTS = [
    {"id": 1, "day": "tuesday", "day_name": "Dienstag", "start_time": "17:00", "end_time": "20:00", "color": "#3B82F6"},
    {"id": 2, "day": "friday", "day_name": "Freitag", "start_time": "17:00", "end_time": "20:00", "color": "#10B981"},
    {"id": 3, "day": "saturday", "day_name": "Samstag", "start_time": "14:00", "end_time": "17:00", "color": "#F59E0B"}
]

BAVARIAN_HOLIDAYS_2025 = [
    {"date": "2025-01-01", "name": "Neujahr"},
    {"date": "2025-01-06", "name": "Heilige Drei Könige"},
    {"date": "2025-04-18", "name": "Karfreitag"},
    {"date": "2025-04-21", "name": "Ostermontag"},
    {"date": "2025-05-01", "name": "Tag der Arbeit"},
    {"date": "2025-05-29", "name": "Christi Himmelfahrt"},
    {"date": "2025-06-09", "name": "Pfingstmontag"},
    {"date": "2025-06-19", "name": "Fronleichnam"},
    {"date": "2025-08-15", "name": "Mariä Himmelfahrt"},
    {"date": "2025-10-03", "name": "Tag der Deutschen Einheit"},
    {"date": "2025-11-01", "name": "Allerheiligen"},
    {"date": "2025-12-25", "name": "1. Weihnachtsfeiertag"},
    {"date": "2025-12-26", "name": "2. Weihnachtsfeiertag"}
]

# Globale Variablen
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager()

if 'sms_service' not in st.session_state:
    st.session_state.sms_service = SMSService()

if 'email_service' not in st.session_state:
    st.session_state.email_service = EmailService()

# Helper Functions
def get_week_start(date_obj):
    """Gibt Montag der ISO-Kalenderwoche zurück"""
    return date_obj - timedelta(days=date_obj.weekday())

def get_current_week_start():
    """Gibt Montag der aktuellen Kalenderwoche zurück"""
    return get_week_start(datetime.now())

def get_iso_calendar_week(date_obj):
    """Gibt ISO-Kalenderwoche zurück"""
    return date_obj.isocalendar()[1]

def get_slot_date(week_start, day_name):
    days = {"tuesday": 1, "friday": 4, "saturday": 5}
    day_offset = days.get(day_name, 0)
    return (week_start + timedelta(days=day_offset)).strftime('%Y-%m-%d')

def is_holiday(date_str):
    return any(h['date'] == date_str for h in BAVARIAN_HOLIDAYS_2025)

def get_holiday_name(date_str):
    for h in BAVARIAN_HOLIDAYS_2025:
        if h['date'] == date_str:
            return h['name']
    return None

def is_closed_period(date_str):
    """Prüft ob Datum in der Sperrzeit (Juni-September) liegt"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        month = date_obj.month
        # Juni (6) bis September (9) geschlossen
        return 6 <= month <= 9
    except:
        return False

def send_booking_confirmation(user, slot, date_str):
    """Sende SMS-Bestätigung bei Buchung"""
    if not user['sms_opt_in']:
        return
    
    slot_info = next(s for s in WEEKLY_SLOTS if s['id'] == slot)
    message = f"✅ Buchungsbestätigung: Schicht gebucht für {date_str}, {slot_info['day_name']} {slot_info['start_time']}-{slot_info['end_time']}. Bei Fragen antworten Sie auf diese SMS."
    
    success, result = st.session_state.sms_service.send_sms(user['phone'], message)
    if success:
        st.session_state.db.log_action(user['id'], 'sms_sent', f'Booking confirmation sent to {user["phone"]}')

def send_calendar_invite(user, booking, slot, method="REQUEST"):
    """Sende Kalendereinladung per E-Mail"""
    if not st.session_state.email_service.enabled:
        return False, "E-Mail Service nicht konfiguriert"
    
    # Template aus DB laden
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    template_type = 'booking_invite' if method == 'REQUEST' else 'booking_cancel'
    cursor.execute('SELECT subject_template, body_template FROM email_templates WHERE template_type = ? AND active = 1', (template_type,))
    template = cursor.fetchone()
    conn.close()
    
    if not template:
        subject = f"[Dienstplan+] {'Einladung' if method == 'REQUEST' else 'Absage'}: {slot['day_name']} - {booking['date']}"
        body = f"Hallo {user['name']},\n\nSchicht am {booking['date']} von {slot['start_time']} bis {slot['end_time']}."
    else:
        subject = template[0].replace('{{name}}', user['name']).replace('{{datum}}', booking['date']).replace('{{slot}}', f"{slot['start_time']}-{slot['end_time']}")
        body = template[1].replace('{{name}}', user['name']).replace('{{datum}}', booking['date']).replace('{{slot}}', f"{slot['start_time']}-{slot['end_time']}")
    
    # ICS generieren
    sequence = 0
    if method == "CANCEL":
        sequence = 1
    
    ics_content = st.session_state.email_service.generate_ics(booking, slot, user, method, sequence)
    
    # E-Mail senden
    success, result = st.session_state.email_service.send_calendar_invite(
        user['email'], subject, body, ics_content, method
    )
    
    if success:
        action = 'calendar_invite_sent' if method == 'REQUEST' else 'calendar_cancel_sent'
        st.session_state.db.log_action(user['id'], action, f'{method} sent to {user["email"]}')
    
    return success, result

def send_sick_notification(user, slot, date_str):
    """Sende Krankmeldung an alle Admins"""
    # Template aus DB laden
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT sms_template FROM reminder_templates WHERE timing = "sick_notification" AND active = 1')
    template = cursor.fetchone()
    conn.close()
    
    if template:
        slot_info = next(s for s in WEEKLY_SLOTS if s['id'] == slot)
        message = template[0].replace('{{name}}', user['name']).replace('{{datum}}', date_str).replace('{{slot}}', f"{slot_info['start_time']}-{slot_info['end_time']}")
    else:
        slot_info = next(s for s in WEEKLY_SLOTS if s['id'] == slot)
        message = f"HINWEIS: {user['name']} hat sich krank gemeldet und die Schicht am {date_str} ({slot_info['start_time']}-{slot_info['end_time']}) storniert. Bitte Ersatz organisieren."
    
    results = st.session_state.sms_service.send_admin_sms(message)
    
    # Logging
    successful_sends = sum(1 for _, success, _ in results if success)
    st.session_state.db.log_action(user['id'], 'sick_notification_sent', f'Sick report sent to {successful_sends} admins')
    
    return results

def check_7_day_warnings():
    """Prüfe und sende 7-Tage-Warnungen"""
    warnings = st.session_state.db.check_7_day_warnings()
    
    if warnings:
        # Template aus DB laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT sms_template FROM reminder_templates WHERE timing = "7_day_warning" AND active = 1')
        template = cursor.fetchone()
        conn.close()
        
        for warning in warnings:
            if template:
                message = template[0].replace('{{datum}}', warning['date']).replace('{{slot}}', warning['slot_name'])
            else:
                message = f"WARNUNG: Die Schicht am {warning['date']} ({warning['slot_name']}) ist 7 Tage vorher noch unbesetzt. Bitte prüfen."
            
            results = st.session_state.sms_service.send_admin_sms(message)
            
            # Logging
            successful_sends = sum(1 for _, success, _ in results if success)
            if successful_sends > 0:
                st.session_state.db.log_action(1, '7_day_warning_sent', f'Warning sent for {warning["date"]} {warning["slot_name"]} to {successful_sends} admins')

def generate_ical(bookings):
    """Generiere iCal für Export"""
    ical_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//DE
"""
    
    for booking in bookings:
        slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
        date_str = booking['date'].replace('-', '')
        start_time = slot['start_time'].replace(':', '') + '00'
        end_time = slot['end_time'].replace(':', '') + '00'
        
        ical_content += f"""BEGIN:VEVENT
UID:{booking['id']}@dienstplan-cloud
DTSTART:{date_str}T{start_time}
DTEND:{date_str}T{end_time}
SUMMARY:Schicht - {slot['day_name']}
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']}
END:VEVENT
"""
    
    ical_content += "END:VCALENDAR"
    return ical_content

# Prüfe Warnungen beim App-Start
if 'warnings_checked' not in st.session_state:
    st.session_state.warnings_checked = True
    try:
        check_7_day_warnings()
    except:
        pass  # Fehler ignorieren beim ersten Start

# Authentication
def show_login():
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
                submit = st.form_submit_button("Anmelden", type="primary")
            
            if submit:
                if email and password:
                    user = st.session_state.db.authenticate_user(email, password)
                    if user:
                        st.session_state.current_user = user
                        # Initialisiere aktuelle Woche
                        st.session_state.current_week_start = get_current_week_start()
                        st.session_state.active_tab = 0  # Plan Tab
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
                help="Diese Nummer wird für Notfälle und automatische Erinnerungen an Ihre Schichten verwendet."
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
                register = st.form_submit_button("Account erstellen", type="primary")
            
            if register:
                if not all([reg_name, reg_email, reg_phone, reg_password, reg_password_confirm]):
                    st.error("❌ Bitte alle Felder ausfüllen")
                elif reg_password != reg_password_confirm:
                    st.error("❌ Passwörter stimmen nicht überein")
                elif len(reg_password) < 6:
                    st.error("❌ Passwort muss mindestens 6 Zeichen lang sein")
                elif not reg_phone.startswith('+'):
                    st.error("❌ Telefonnummer muss mit Ländercode beginnen (z.B. +49)")
                else:
                    user_id = st.session_state.db.create_user(reg_email, reg_phone, reg_name, reg_password)
                    if user_id:
                        # SMS-Opt-in aktualisieren
                        if sms_consent:
                            conn = st.session_state.db.get_connection()
                            cursor = conn.cursor()
                            cursor.execute('UPDATE users SET sms_opt_in = 1 WHERE id = ?', (user_id,))
                            conn.commit()
                            conn.close()
                        
                        # Automatisches Login nach Registrierung
                        user = st.session_state.db.authenticate_user(reg_email, reg_password)
                        if user:
                            st.session_state.current_user = user
                            # Initialisiere aktuelle Woche
                            st.session_state.current_week_start = get_current_week_start()
                            st.session_state.active_tab = 0  # Plan Tab
                            st.session_state.db.log_action(user_id, 'account_created', f'New user registered and auto-logged in: {reg_name}')
                            st.success("✅ Account erfolgreich erstellt! Sie sind automatisch eingeloggt.")
                            st.balloons()
                            st.rerun()
                    else:
                        st.error("❌ E-Mail bereits registriert")

def show_main_app():
    user = st.session_state.current_user
    
    # Header mit Navigation
    col1, col2, col3 = st.columns([2, 3, 2])
    with col1:
        st.markdown(f"👋 **{user['name']}**  \n📧 {user['email']}")
    with col2:
        st.markdown("# 📅 Dienstplan+ Cloud")
    with col3:
        col3a, col3b = st.columns(2)
        with col3a:
            if st.button("👤 Profil"):
                st.session_state.show_profile = True
                st.rerun()
        with col3b:
            if st.button("🚪 Abmelden"):
                st.session_state.db.log_action(user['id'], 'logout', 'User logged out')
                st.session_state.current_user = None
                if 'show_profile' in st.session_state:
                    del st.session_state.show_profile
                if 'current_week_start' in st.session_state:
                    del st.session_state.current_week_start
                if 'active_tab' in st.session_state:
                    del st.session_state.active_tab
                st.rerun()
    
    st.markdown("---")
    
    # Profil-Overlay prüfen
    if st.session_state.get('show_profile', False):
        show_profile_page()
        return
    
    # Tab Navigation - Team nur für Admins
    if user['role'] == 'admin':
        tab_names = ["📅 Plan", "👤 Meine Schichten", "👥 Team", "⚙️ Admin"]
        tabs = st.tabs(tab_names)
    else:
        tab_names = ["📅 Plan", "👤 Meine Schichten"]
        tabs = st.tabs(tab_names)
    
    # Tab Content
    with tabs[0]:
        show_schedule_tab()
    
    with tabs[1]:
        show_my_shifts_tab()
    
    if user['role'] == 'admin':
        with tabs[2]:
            show_team_tab()
        
        with tabs[3]:
            show_admin_tab()

def show_profile_page():
    """Separate Profilseite"""
    user = st.session_state.current_user
    
    # Header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Zurück"):
            st.session_state.show_profile = False
            st.rerun()
    with col2:
        st.markdown("# 👤 Mein Profil")
    
    st.markdown("---")
    
    # Profil-Informationen bearbeiten
    col1, col2 = st.columns([1, 1])
    
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
            
            col1a, col1b = st.columns(2)
            with col1a:
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
    
    # Account-Informationen
    st.markdown("---")
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
            
            export_data = {
                'profile': {
                    'name': user['name'],
                    'email': user['email'],
                    'phone': user['phone'],
                    'role': user['role']
                },
                'bookings': user_bookings,
                'export_date': datetime.now().isoformat()
            }
            
            json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📥 JSON herunterladen",
                data=json_data,
                file_name=f"meine_daten_{user['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )

def show_schedule_tab():
    st.markdown("### 📅 Wochenplan")
    
    # Initialisiere aktuelle Woche falls noch nicht gesetzt
    if 'current_week_start' not in st.session_state:
        st.session_state.current_week_start = get_current_week_start()
    
    # Kalender-Navigation
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        # Vorherige Woche Button
        if st.button("⬅️ Vorherige Woche", key="prev_week"):
            st.session_state.current_week_start -= timedelta(days=7)
            st.rerun()
        
        # Kalenderelement zur Direktauswahl
        st.markdown("**📅 Datum wählen:**")
        selected_date = st.date_input(
            "Woche auswählen",
            value=st.session_state.current_week_start,
            key="calendar_date_picker"
        )
        
        if selected_date != st.session_state.current_week_start:
            selected_week_start = get_week_start(selected_date)
            st.session_state.current_week_start = selected_week_start
            st.rerun()
    
    with col2:
        # Hervorgehobener Wochenkopf
        week_end = st.session_state.current_week_start + timedelta(days=6)
        calendar_week = get_iso_calendar_week(st.session_state.current_week_start)
        
        st.markdown(f"""
        <div class="week-header">
            <h2>Woche vom {st.session_state.current_week_start.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}</h2>
            <div class="calendar-week">📅 KW {calendar_week}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        # Nächste Woche Button
        if st.button("Nächste Woche ➡️", key="next_week"):
            st.session_state.current_week_start += timedelta(days=7)
            st.rerun()
        
        # Kalender-Legende
        st.markdown("**📊 Legende:**")
        st.markdown("""
        <div class="calendar-legend">
            <div class="legend-item">
                <div class="legend-dot free-dot"></div>
                <span>Frei</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot booked-dot"></div>
                <span>Belegt</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot holiday-dot"></div>
                <span>Feiertag</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Schichten der Woche anzeigen
    for slot in WEEKLY_SLOTS:
        slot_date = get_slot_date(st.session_state.current_week_start, slot['day'])
        
        with st.container():
            # Prüfen ob Feiertag
            holiday_name = get_holiday_name(slot_date)
            
            # Prüfen ob Sperrzeit
            is_closed = is_closed_period(slot_date)
            
            if holiday_name:
                st.markdown(f"""
                <div class="holiday-card">
                    <h4>🚫 {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                    <p><strong>📅 {slot_date}</strong></p>
                    <p>🎄 <strong>Feiertag:</strong> {holiday_name}</p>
                    <p>❌ Keine Schichten an diesem Tag</p>
                </div>
                """, unsafe_allow_html=True)
            elif is_closed:
                st.markdown(f"""
                <div class="closed-card">
                    <h4>🏊‍♂️ {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                    <p><strong>📅 {slot_date}</strong></p>
                    <p>🚫 <strong>Hallenbad in dieser Zeit geschlossen</strong></p>
                    <p>❌ Keine Buchung möglich (Juni - September)</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Bestehende Buchungen prüfen
                bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], slot_date)
                user_booking = next((b for b in bookings if b['user_id'] == st.session_state.current_user['id']), None)
                
                if user_booking:
                    # User hat diesen Slot gebucht
                    st.markdown(f"""
                    <div class="shift-card user-slot">
                        <h4>✅ {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                        <p><strong>📅 {slot_date}</strong></p>
                        <p>👤 <strong>Gebucht von Ihnen</strong></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2, col3 = st.columns([2, 1, 2])
                    with col2:
                        if st.button(f"❌ Stornieren", key=f"cancel_{slot['id']}_{slot_date}"):
                            if st.session_state.db.cancel_booking(user_booking['id'], st.session_state.current_user['id']):
                                st.session_state.db.log_action(
                                    st.session_state.current_user['id'],
                                    'booking_cancelled',
                                    f"Cancelled {slot['day_name']} {slot_date}"
                                )
                                
                                # Kalender-Absage senden
                                booking_data = {'id': user_booking['id'], 'date': slot_date}
                                send_calendar_invite(st.session_state.current_user, booking_data, slot, method="CANCEL")
                                
                                st.success("✅ Schicht erfolgreich storniert!")
                                st.rerun()
                
                elif bookings:
                    # Slot ist von jemand anderem gebucht
                    other_booking = bookings[0]
                    st.markdown(f"""
                    <div class="shift-card booked-slot">
                        <h4>📍 {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                        <p><strong>📅 {slot_date}</strong></p>
                        <p>👤 <strong>Gebucht von:</strong> {other_booking['user_name']}</p>
                        <p>⚠️ Schicht bereits vergeben</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                else:
                    # Slot ist verfügbar
                    st.markdown(f"""
                    <div class="shift-card available-slot">
                        <h4>🟢 {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                        <p><strong>📅 {slot_date}</strong></p>
                        <p>✅ <strong>Verfügbar</strong></p>
                        <p>💡 Klicken Sie auf "Buchen" um diese Schicht zu übernehmen</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2, col3 = st.columns([2, 1, 2])
                    with col2:
                        if st.button(f"📝 Buchen", key=f"book_{slot['id']}_{slot_date}"):
                            success, result = st.session_state.db.create_booking(
                                st.session_state.current_user['id'], slot['id'], slot_date
                            )
                            
                            if success:
                                st.session_state.db.log_action(
                                    st.session_state.current_user['id'],
                                    'booking_created',
                                    f"Booked {slot['day_name']} {slot_date}"
                                )
                                
                                # SMS-Bestätigung senden
                                send_booking_confirmation(st.session_state.current_user, slot['id'], slot_date)
                                
                                # Kalendereinladung senden
                                booking_data = {'id': result, 'date': slot_date}
                                success_email, result_email = send_calendar_invite(st.session_state.current_user, booking_data, slot)
                                
                                if success_email:
                                    st.success("✅ Schicht erfolgreich gebucht! 📱 SMS-Bestätigung und 📧 Kalendereinladung werden gesendet.")
                                else:
                                    st.success("✅ Schicht erfolgreich gebucht! 📱 SMS-Bestätigung wird gesendet.")
                                    st.warning(f"⚠️ Kalendereinladung konnte nicht gesendet werden: {result_email}")
                                
                                st.rerun()
                            else:
                                st.error(f"❌ Fehler beim Buchen: {result}")

def show_my_shifts_tab():
    st.markdown("### 👤 Meine Schichten")
    
    user_bookings = st.session_state.db.get_user_bookings(st.session_state.current_user['id'])
    
    if user_bookings:
        # Statistiken
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📊 Gebuchte Schichten", len(user_bookings))
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            total_hours = len(user_bookings) * 3  # 3h pro Schicht
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("⏰ Gesamt Stunden", f"{total_hours}h")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col3:
            future_bookings = [b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d') >= datetime.now()]
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📅 Kommende Schichten", len(future_bookings))
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col4:
            if future_bookings:
                next_shift_date = min(future_bookings, key=lambda x: x['date'])['date']
                days_until = (datetime.strptime(next_shift_date, '%Y-%m-%d') - datetime.now()).days
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("⏭️ Nächste in", f"{days_until} Tagen")
                st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Schichtenliste
        st.markdown("### 📋 Alle meine Schichten")
        
        # Filter
        filter_option = st.selectbox(
            "🔍 Anzeigen:",
            ["Alle Schichten", "Nur kommende", "Nur vergangene"]
        )
        
        filtered_bookings = user_bookings.copy()
        today = datetime.now()
        
        if filter_option == "Nur kommende":
            filtered_bookings = [b for b in filtered_bookings if datetime.strptime(b['date'], '%Y-%m-%d') >= today]
        elif filter_option == "Nur vergangene":
            filtered_bookings = [b for b in filtered_bookings if datetime.strptime(b['date'], '%Y-%m-%d') < today]
        
        for booking in sorted(filtered_bookings, key=lambda x: x['date'], reverse=True):
            slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
            booking_date = datetime.strptime(booking['date'], '%Y-%m-%d')
            is_future = booking_date >= today
            
            card_class = "shift-card user-slot" if is_future else "shift-card"
            status_emoji = "📅" if is_future else "✅"
            
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"""
                    <div class="{card_class}">
                        <h5>{status_emoji} {slot['day_name']}, {booking_date.strftime('%d.%m.%Y')}</h5>
                        <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
                        <p>📝 Gebucht am: {datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    if is_future:
                        days_until = (booking_date - today).days
                        if days_until == 0:
                            st.success("🔥 Heute!")
                        elif days_until == 1:
                            st.info("📅 Morgen")
                        else:
                            st.info(f"📅 In {days_until} Tagen")
                    else:
                        st.success("✅ Erledigt")
                
                with col3:
                    if is_future:
                        col3a, col3b = st.columns(2)
                        
                        with col3a:
                            # Krank melden Button
                            st.markdown('<div class="sick-button">', unsafe_allow_html=True)
                            if st.button("🤒", key=f"sick_{booking['id']}", help="Krank melden"):
                                # Schicht stornieren
                                if st.session_state.db.cancel_booking(booking['id'], st.session_state.current_user['id']):
                                    # Krankmeldung an Admins senden
                                    send_sick_notification(st.session_state.current_user, booking['slot_id'], booking['date'])
                                    
                                    # Kalender-Absage senden
                                    send_calendar_invite(st.session_state.current_user, booking, slot, method="CANCEL")
                                    
                                    st.session_state.db.log_action(
                                        st.session_state.current_user['id'],
                                        'sick_reported',
                                        f"Reported sick for {slot['day_name']} {booking['date']}"
                                    )
                                    st.success("✅ Krankmeldung erfolgreich übermittelt! Administratoren wurden benachrichtigt.")
                                    st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)
                        
                        with col3b:
                            # Regulärer Stornieren Button
                            if st.button("❌", key=f"cancel_my_{booking['id']}", help="Schicht stornieren"):
                                if st.session_state.db.cancel_booking(booking['id'], st.session_state.current_user['id']):
                                    # Kalender-Absage senden
                                    send_calendar_invite(st.session_state.current_user, booking, slot, method="CANCEL")
                                    
                                    st.session_state.db.log_action(
                                        st.session_state.current_user['id'],
                                        'booking_cancelled',
                                        f"Cancelled {slot['day_name']} {booking['date']}"
                                    )
                                    st.success("✅ Schicht storniert!")
                                    st.rerun()
        
        # Export-Funktionen
        st.markdown("---")
        st.markdown("### 📤 Export")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📅 Kalender exportieren (iCal)", type="primary"):
                ical_data = generate_ical(user_bookings)
                st.download_button(
                    label="📥 iCal-Datei herunterladen",
                    data=ical_data,
                    file_name=f"meine_schichten_{datetime.now().strftime('%Y%m%d')}.ics",
                    mime="text/calendar"
                )
        
        with col2:
            if st.button("📊 CSV exportieren"):
                df_data = []
                for booking in user_bookings:
                    slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
                    df_data.append({
                        'Datum': booking['date'],
                        'Wochentag': slot['day_name'],
                        'Startzeit': slot['start_time'],
                        'Endzeit': slot['end_time'],
                        'Status': booking['status'],
                        'Gebucht am': booking['created_at']
                    })
                
                df = pd.DataFrame(df_data)
                csv = df.to_csv(index=False, encoding='utf-8')
                st.download_button(
                    label="📥 CSV-Datei herunterladen",
                    data=csv,
                    file_name=f"meine_schichten_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
    
    else:
        st.markdown("""
        <div class="info-message">
            <h4>📭 Noch keine Schichten gebucht</h4>
            <p>Sie haben noch keine Schichten in Ihrem Kalender. Besuchen Sie den "Plan" Tab, um verfügbare Schichten zu buchen.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Funktionsfähiger "Zum Schichtplan" Button
        if st.button("📅 Zum Schichtplan", type="primary"):
            st.session_state.active_tab = 0  # Plan Tab
            # Initialisiere aktuelle Woche
            if 'current_week_start' not in st.session_state:
                st.session_state.current_week_start = get_current_week_start()
            st.rerun()

def show_team_tab():
    """Team-Tab nur für Admins sichtbar"""
    st.markdown("### 👥 Team-Übersicht")
    
    all_users = st.session_state.db.get_all_users()
    active_users = [u for u in all_users if u['active']]
    
    # Team-Statistiken
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("👥 Team-Mitglieder", len(active_users))
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Aktuelle Woche Statistiken
    today = datetime.now()
    week_start = get_week_start(today)
    current_week_bookings = []
    
    for slot in WEEKLY_SLOTS:
        slot_date = get_slot_date(week_start, slot['day'])
        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], slot_date)
        current_week_bookings.extend(bookings)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📅 Diese Woche belegt", len(current_week_bookings))
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        free_slots = 3 - len(current_week_bookings)  # 3 Slots pro Woche
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("🟢 Freie Plätze", free_slots)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        admins = [u for u in active_users if u['role'] == 'admin']
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("👑 Administratoren", len(admins))
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Admin-Umbuchung/Stornierung
    if st.session_state.current_user['role'] == 'admin':
        st.markdown("### 🔧 Admin-Aktionen")
        
        all_bookings = st.session_state.db.get_all_bookings()
        future_bookings = [b for b in all_bookings if datetime.strptime(b['date'], '%Y-%m-%d') >= datetime.now()]
        
        if future_bookings:
            with st.expander("📝 Schichten verwalten (Stornieren/Umbuchen)"):
                for booking in sorted(future_bookings, key=lambda x: x['date'])[:10]:  # Nur nächste 10 anzeigen
                    slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
                    booking_date = datetime.strptime(booking['date'], '%Y-%m-%d')
                    
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                    
                    with col1:
                        st.write(f"**{booking['user_name']}**")
                        st.caption(f"{slot['day_name']}, {booking_date.strftime('%d.%m.%Y')} ({slot['start_time']}-{slot['end_time']})")
                    
                    with col2:
                        days_until = (booking_date - datetime.now()).days
                        if days_until == 0:
                            st.warning("Heute")
                        elif days_until == 1:
                            st.info("Morgen")
                        else:
                            st.info(f"In {days_until} Tagen")
                    
                    with col3:
                        # Admin-Stornierung
                        st.markdown('<div class="admin-action-button">', unsafe_allow_html=True)
                        if st.button("🗑️", key=f"admin_cancel_{booking['id']}", help="Als Admin stornieren"):
                            if st.session_state.db.cancel_booking(booking['id']):
                                # User über Stornierung informieren
                                user = st.session_state.db.get_user_by_id(booking['user_id'])
                                if user:
                                    # Kalender-Absage senden
                                    send_calendar_invite(user, booking, slot, method="CANCEL")
                                    
                                    # Optional: SMS-Info an User
                                    if user['sms_opt_in']:
                                        message = f"INFO: Ihre Schicht am {booking['date']} ({slot['start_time']}-{slot['end_time']}) wurde vom Administrator storniert. Bei Fragen melden Sie sich bitte."
                                        st.session_state.sms_service.send_sms(user['phone'], message)
                                
                                st.session_state.db.log_action(
                                    st.session_state.current_user['id'],
                                    'admin_cancelled_booking',
                                    f"Admin cancelled {booking['user_name']}'s booking for {booking['date']}"
                                )
                                st.success(f"✅ Schicht von {booking['user_name']} storniert")
                                st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with col4:
                        # Umbuchung (vereinfacht)
                        if st.button("↔️", key=f"admin_reschedule_{booking['id']}", help="Umbuchen"):
                            st.info("Umbuchung: Stornieren Sie die Schicht und buchen Sie manuell eine neue.")
        
        st.markdown("---")
    
    # Team-Mitglieder
    st.markdown("### 👥 Team-Mitglieder")
    
    for user in sorted(active_users, key=lambda x: x['name']):
        user_bookings = st.session_state.db.get_user_bookings(user['id'])
        future_bookings = [b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d') >= datetime.now()]
        
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        
        with col1:
            role_emoji = "👑" if user['role'] == 'admin' else "👤"
            initial_admin_badge = " 🔧" if user.get('is_initial_admin') else ""
            st.markdown(f"**{role_emoji} {user['name']}{initial_admin_badge}**")
            st.text(f"📧 {user['email']}")
        
        with col2:
            st.text(f"📱 {user['phone']}")
            st.text(f"📅 Seit {datetime.fromisoformat(user['created_at']).strftime('%d.%m.%Y')}")
        
        with col3:
            st.text(f"📊 Schichten gesamt: {len(user_bookings)}")
            st.text(f"📅 Kommend: {len(future_bookings)}")
        
        with col4:
            if future_bookings:
                next_shift = min(future_bookings, key=lambda x: x['date'])
                next_slot = next(s for s in WEEKLY_SLOTS if s['id'] == next_shift['slot_id'])
                st.success(f"⏭️ {next_shift['date']}")
                st.text(f"{next_slot['day_name']} {next_slot['start_time']}-{next_slot['end_time']}")
            else:
                st.info("📭 Keine kommenden Schichten")
        
        st.markdown("---")
    
    # Wochenübersicht
    st.markdown("### 📅 Aktuelle Wochenübersicht")
    
    week_end = week_start + timedelta(days=6)
    calendar_week = get_iso_calendar_week(week_start)
    st.markdown(f"**Woche vom {week_start.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')} (KW {calendar_week})**")
    
    for slot in WEEKLY_SLOTS:
        slot_date = get_slot_date(week_start, slot['day'])
        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], slot_date)
        
        col1, col2, col3 = st.columns([2, 2, 3])
        
        with col1:
            st.markdown(f"**{slot['day_name']}**")
            st.text(f"{slot_date}")
        
        with col2:
            st.text(f"{slot['start_time']} - {slot['end_time']}")
        
        with col3:
            if is_holiday(slot_date):
                holiday_name = get_holiday_name(slot_date)
                st.error(f"🎄 Feiertag: {holiday_name}")
            elif is_closed_period(slot_date):
                st.warning(f"🏊‍♂️ Hallenbad geschlossen")
            elif bookings:
                booking = bookings[0]
                st.success(f"👤 {booking['user_name']}")
            else:
                st.warning("🟡 Noch offen")

def show_admin_tab():
    st.markdown("### ⚙️ Administrator Panel")
    
    admin_tabs = st.tabs(["👥 Benutzer", "📝 Vorlagen", "📊 Statistiken", "📤 Export", "📅 Unbelegte Termine", "💾 Backup", "🔧 System"])
    
    # Benutzerverwaltung
    with admin_tabs[0]:
        st.markdown("#### 👥 Benutzerverwaltung")
        
        all_users = st.session_state.db.get_all_users()
        
        # Neue Benutzer hinzufügen (nur für Initial-Admin)
        if st.session_state.current_user.get('is_initial_admin'):
            with st.expander("➕ Neuen Benutzer hinzufügen"):
                with st.form("add_user_form"):
                    new_name = st.text_input("Name")
                    new_email = st.text_input("E-Mail")
                    new_phone = st.text_input("Telefon")
                    new_role = st.selectbox("Rolle", ["user", "admin"])
                    new_password = st.text_input("Temporäres Passwort", type="password", value="temp123")
                    
                    if st.form_submit_button("Benutzer erstellen"):
                        if all([new_name, new_email, new_phone, new_password]):
                            user_id = st.session_state.db.create_user(new_email, new_phone, new_name, new_password, new_role)
                            if user_id:
                                st.success(f"✅ Benutzer {new_name} erfolgreich erstellt")
                                st.session_state.db.log_action(
                                    st.session_state.current_user['id'],
                                    'user_created',
                                    f"Created user: {new_name} ({new_email})"
                                )
                                st.rerun()
                            else:
                                st.error("❌ E-Mail bereits registriert")
                        else:
                            st.error("❌ Bitte alle Felder ausfüllen")
        else:
            st.info("ℹ️ Nur der Initial-Administrator kann neue Benutzer anlegen.")
        
        # Bestehende Benutzer
        st.markdown("**Bestehende Benutzer:**")
        
        # Suchfunktion
        search = st.text_input("🔍 Benutzer suchen", placeholder="Name oder E-Mail eingeben...")
        
        filtered_users = all_users
        if search:
            filtered_users = [u for u in all_users if search.lower() in u['name'].lower() or search.lower() in u['email'].lower()]
        
        for user in filtered_users:
            user_bookings = st.session_state.db.get_user_bookings(user['id'])
            
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            
            with col1:
                role_emoji = "👑" if user['role'] == 'admin' else "👤"
                initial_badge = " 🔧" if user.get('is_initial_admin') else ""
                status_emoji = "✅" if user['active'] else "❌"
                st.write(f"{role_emoji} {status_emoji} {user['name']}{initial_badge}")
                st.caption(user['email'])
            
            with col2:
                st.write(user['phone'])
                st.caption(f"Seit {datetime.fromisoformat(user['created_at']).strftime('%d.%m.%Y')}")
            
            with col3:
                st.write(user['role'])
            
            with col4:
                st.write(f"{len(user_bookings)} Schichten")
            
            with col5:
                if user['id'] != st.session_state.current_user['id']:
                    # Rollen-Management nur für Initial-Admin
                    if st.session_state.current_user.get('is_initial_admin'):
                        if st.button(f"👑", key=f"promote_{user['id']}", help="Zu Admin befördern" if user['role'] == 'user' else "Zu User zurückstufen"):
                            new_role = 'admin' if user['role'] == 'user' else 'user'
                            st.session_state.db.update_user_role(user['id'], new_role)
                            st.session_state.db.log_action(
                                st.session_state.current_user['id'],
                                'role_changed',
                                f"Changed {user['name']} role to {new_role}"
                            )
                            st.success(f"Rolle von {user['name']} zu {new_role} geändert")
                            st.rerun()
                    
                    if st.button("🗑️", key=f"delete_{user['id']}", help="Benutzer deaktivieren"):
                        conn = st.session_state.db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE users SET active = 0 WHERE id = ?', (user['id'],))
                        conn.commit()
                        conn.close()
                        
                        st.session_state.db.log_action(
                            st.session_state.current_user['id'],
                            'user_deactivated',
                            f"Deactivated user: {user['name']}"
                        )
                        st.success(f"Benutzer {user['name']} deaktiviert")
                        st.rerun()
    
    # Vorlagen verwalten
    with admin_tabs[1]:
        st.markdown("#### 📝 Nachrichten-Vorlagen")
        
        # SMS Templates
        st.markdown("**SMS-Vorlagen:**")
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reminder_templates ORDER BY timing')
        templates = cursor.fetchall()
        
        for template in templates:
            with st.expander(f"📱 {template[1]} ({template[2]})"):
                with st.form(f"sms_template_form_{template[0]}"):
                    st.markdown(f"**{template[1]}**")
                    
                    new_sms_template = st.text_area(
                        "SMS-Vorlage:",
                        value=template[3] or "",
                        height=100,
                        help="Verfügbare Platzhalter: {{name}}, {{datum}}, {{slot}}"
                    )
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.form_submit_button("💾 Speichern"):
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE reminder_templates 
                                SET sms_template = ? 
                                WHERE id = ?
                            ''', (new_sms_template, template[0]))
                            conn.commit()
                            
                            st.session_state.db.log_action(
                                st.session_state.current_user['id'],
                                'template_updated',
                                f"Updated SMS template: {template[1]}"
                            )
                            st.success("✅ SMS-Vorlage gespeichert")
                            st.rerun()
                    
                    with col2:
                        if st.form_submit_button("📱 Test SMS"):
                            if st.session_state.current_user['sms_opt_in']:
                                test_message = new_sms_template.replace('{{name}}', st.session_state.current_user['name'])
                                test_message = test_message.replace('{{datum}}', datetime.now().strftime('%d.%m.%Y'))
                                test_message = test_message.replace('{{slot}}', '17:00-20:00')
                                
                                success, result = st.session_state.sms_service.send_sms(
                                    st.session_state.current_user['phone'],
                                    f"[TEST] {test_message}"
                                )
                                
                                if success:
                                    st.success("✅ Test-SMS gesendet")
                                else:
                                    st.error(f"❌ Fehler: {result}")
                            else:
                                st.warning("❌ SMS nicht aktiviert in Ihrem Profil")
        
        # E-Mail Templates
        st.markdown("---")
        st.markdown("**E-Mail-Vorlagen:**")
        cursor.execute('SELECT * FROM email_templates ORDER BY template_type')
        email_templates = cursor.fetchall()
        conn.close()
        
        for template in email_templates:
            with st.expander(f"📧 {template[1]} ({template[2]})"):
                with st.form(f"email_template_form_{template[0]}"):
                    st.markdown(f"**{template[1]}**")
                    
                    new_subject = st.text_input(
                        "Betreff:",
                        value=template[3] or "",
                        help="Verfügbare Platzhalter: {{name}}, {{datum}}, {{slot}}"
                    )
                    
                    new_body = st.text_area(
                        "E-Mail Text:",
                        value=template[4] or "",
                        height=150,
                        help="Verfügbare Platzhalter: {{name}}, {{datum}}, {{slot}}"
                    )
                    
                    if st.form_submit_button("💾 Speichern"):
                        conn = st.session_state.db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE email_templates 
                            SET subject_template = ?, body_template = ? 
                            WHERE id = ?
                        ''', (new_subject, new_body, template[0]))
                        conn.commit()
                        conn.close()
                        
                        st.session_state.db.log_action(
                            st.session_state.current_user['id'],
                            'email_template_updated',
                            f"Updated email template: {template[1]}"
                        )
                        st.success("✅ E-Mail-Vorlage gespeichert")
                        st.rerun()
        
        # Service Status
        st.markdown("---")
        st.markdown("#### 🔧 Service-Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📱 SMS-Service:**")
            if st.session_state.sms_service.enabled:
                st.success("✅ SMS-Service aktiv")
                st.info(f"📞 Sender-Nummer: {st.session_state.sms_service.from_number}")
            else:
                st.error("❌ SMS-Service nicht konfiguriert")
                st.info("💡 Konfigurieren Sie TWILIO_* in den Secrets")
        
        with col2:
            st.markdown("**📧 E-Mail-Service:**")
            if st.session_state.email_service.enabled:
                st.success("✅ E-Mail-Service aktiv")
                st.info(f"📧 Sender: {st.session_state.email_service.gmail_user}")
            else:
                st.error("❌ E-Mail-Service nicht konfiguriert")
                st.info("💡 Konfigurieren Sie GMAIL_* in den Secrets")
    
    # Statistiken
    with admin_tabs[2]:
        st.markdown("#### 📊 System-Statistiken")
        
        # Basis-Statistiken
        all_users = st.session_state.db.get_all_users()
        active_users = [u for u in all_users if u['active']]
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("👥 Gesamt Benutzer", len(all_users))
        with col2:
            st.metric("✅ Aktive Benutzer", len(active_users))
        with col3:
            admins = [u for u in active_users if u['role'] == 'admin']
            st.metric("👑 Administratoren", len(admins))
        with col4:
            regular_users = [u for u in active_users if u['role'] == 'user']
            st.metric("👤 Standard Benutzer", len(regular_users))
        
        # Buchungs-Statistiken
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        
        # Gesamtbuchungen
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "confirmed"')
        total_bookings = cursor.fetchone()[0]
        
        # Buchungen diese Woche
        today = datetime.now()
        week_start = get_week_start(today)
        week_end = week_start + timedelta(days=6)
        cursor.execute('''
            SELECT COUNT(*) FROM bookings 
            WHERE status = "confirmed" AND booking_date BETWEEN ? AND ?
        ''', (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
        week_bookings = cursor.fetchone()[0]
        
        # Kommende Buchungen
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "confirmed" AND booking_date >= ?', (today.strftime('%Y-%m-%d'),))
        future_bookings = cursor.fetchone()[0]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Gesamtbuchungen", total_bookings)
        with col2:
            st.metric("📅 Diese Woche", week_bookings)
        with col3:
            st.metric("⏭️ Kommende", future_bookings)
        
        # Buchungen pro Benutzer
        cursor.execute('''
            SELECT u.name, COUNT(b.id) as booking_count
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id AND b.status = "confirmed"
            WHERE u.active = 1
            GROUP BY u.id, u.name
            ORDER BY booking_count DESC
        ''')
        user_stats = cursor.fetchall()
        
        if user_stats:
            st.markdown("---")
            st.markdown("#### 👥 Buchungen pro Benutzer")
            
            df_user_stats = pd.DataFrame(user_stats, columns=['Benutzer', 'Buchungen'])
            
            if len(df_user_stats) > 0:
                fig = px.bar(
                    df_user_stats,
                    x='Benutzer',
                    y='Buchungen',
                    title="Buchungen pro Benutzer"
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
        
        conn.close()
    
    # Export Tab
    with admin_tabs[3]:
        st.markdown("#### 📤 Daten exportieren")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 Buchungsdaten**")
            
            # Datumsbereich auswählen
            date_from = st.date_input("Von Datum", value=datetime.now() - timedelta(days=30))
            date_to = st.date_input("Bis Datum", value=datetime.now() + timedelta(days=30))
            
            if st.button("📥 CSV Export - Alle Buchungen"):
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT b.id, u.name, u.email, u.phone, b.slot_id, b.booking_date, b.status, b.created_at
                    FROM bookings b
                    JOIN users u ON b.user_id = u.id
                    WHERE b.booking_date BETWEEN ? AND ?
                    ORDER BY b.booking_date ASC
                ''', (date_from.strftime('%Y-%m-%d'), date_to.strftime('%Y-%m-%d')))
                
                bookings_data = cursor.fetchall()
                conn.close()
                
                if bookings_data:
                    export_data = []
                    for booking in bookings_data:
                        slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking[4])
                        export_data.append({
                            'Buchungs-ID': booking[0],
                            'Name': booking[1],
                            'E-Mail': booking[2],
                            'Telefon': booking[3],
                            'Wochentag': slot['day_name'],
                            'Startzeit': slot['start_time'],
                            'Endzeit': slot['end_time'],
                            'Datum': booking[5],
                            'Status': booking[6],
                            'Gebucht am': booking[7]
                        })
                    
                    df = pd.DataFrame(export_data)
                    csv = df.to_csv(index=False, encoding='utf-8')
                    
                    st.download_button(
                        label="📥 CSV herunterladen",
                        data=csv,
                        file_name=f"buchungen_{date_from}_{date_to}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Keine Buchungen im gewählten Zeitraum")
        
        with col2:
            st.markdown("**👥 Benutzerdaten**")
            
            if st.button("📥 CSV Export - Alle Benutzer"):
                all_users = st.session_state.db.get_all_users()
                
                export_data = []
                for user in all_users:
                    user_bookings = st.session_state.db.get_user_bookings(user['id'])
                    export_data.append({
                        'Name': user['name'],
                        'E-Mail': user['email'],
                        'Telefon': user['phone'],
                        'Rolle': user['role'],
                        'Initial-Admin': 'Ja' if user.get('is_initial_admin') else 'Nein',
                        'Aktiv': 'Ja' if user['active'] else 'Nein',
                        'Registriert am': user['created_at'],
                        'Anzahl Buchungen': len(user_bookings)
                    })
                
                df = pd.DataFrame(export_data)
                csv = df.to_csv(index=False, encoding='utf-8')
                
                st.download_button(
                    label="📥 CSV herunterladen",
                    data=csv,
                    file_name=f"benutzer_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
    
    # Unbelegte Termine Tab
    with admin_tabs[4]:
        st.markdown("""
        <div class="admin-section">
            <h4>📅 Unbelegte Termine (Nächste 60 Tage)</h4>
        </div>
        """, unsafe_allow_html=True)
        
        unbooked_slots = st.session_state.db.get_unbooked_slots_next_60_days()
        
        if unbooked_slots:
            # Filter
            col1, col2, col3 = st.columns(3)
            
            with col1:
                day_filter = st.selectbox(
                    "🔍 Nach Wochentag filtern:",
                    ["Alle Tage", "Dienstag", "Freitag", "Samstag"]
                )
            
            with col2:
                weeks_ahead = st.slider("📅 Wochen voraus", 1, 8, 4)
            
            with col3:
                st.markdown(f"**📊 Gesamt unbelegte Slots:** {len(unbooked_slots)}")
            
            # Filtern
            filtered_slots = unbooked_slots.copy()
            
            if day_filter != "Alle Tage":
                filtered_slots = [s for s in filtered_slots if s['day_name'] == day_filter]
            
            end_filter_date = (datetime.now() + timedelta(weeks=weeks_ahead)).strftime('%Y-%m-%d')
            filtered_slots = [s for s in filtered_slots if s['date'] <= end_filter_date]
            
            # Anzeige
            st.markdown(f"**🔍 Gefilterte Ergebnisse: {len(filtered_slots)} unbelegte Slots**")
            
            # Gruppiert nach Woche
            weeks_dict = {}
            for slot in filtered_slots:
                slot_date = datetime.strptime(slot['date'], '%Y-%m-%d')
                week_start = get_week_start(slot_date)
                week_key = week_start.strftime('%Y-%m-%d')
                
                if week_key not in weeks_dict:
                    weeks_dict[week_key] = []
                weeks_dict[week_key].append(slot)
            
            for week_start_str, week_slots in sorted(weeks_dict.items()):
                week_start = datetime.strptime(week_start_str, '%Y-%m-%d')
                week_end = week_start + timedelta(days=6)
                calendar_week = get_iso_calendar_week(week_start)
                
                with st.expander(f"📅 KW {calendar_week}: {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')} ({len(week_slots)} frei)"):
                    for slot in sorted(week_slots, key=lambda x: x['date']):
                        slot_date = datetime.strptime(slot['date'], '%Y-%m-%d')
                        
                        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                        
                        with col1:
                            st.write(f"**{slot['day_name']}**")
                            st.write(slot_date.strftime('%d.%m.%Y'))
                        
                        with col2:
                            st.write(f"{slot['start_time']} - {slot['end_time']}")
                        
                        with col3:
                            days_until = (slot_date - datetime.now()).days
                            if days_until == 0:
                                st.warning("Heute")
                            elif days_until == 1:
                                st.warning("Morgen")
                            elif days_until <= 7:
                                st.error(f"In {days_until} Tagen ⚠️")
                            else:
                                st.info(f"In {days_until} Tagen")
                        
                        with col4:
                            st.success("🟢 Frei")
        else:
            st.success("🎉 Alle Slots der nächsten 60 Tage sind belegt!")
    
    # Backup Tab
    with admin_tabs[5]:
        st.markdown("""
        <div class="admin-section">
            <h4>💾 Backup & Wiederherstellung</h4>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📥 Backup erstellen")
            st.info("Erstellt ein vollständiges Backup aller App-Daten (Benutzer, Buchungen, Templates, etc.)")
            
            if st.button("💾 Backup jetzt erstellen", type="primary"):
                try:
                    backup_data = st.session_state.db.create_backup()
                    
                    # ZIP-Datei erstellen
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        zip_file.writestr(f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", backup_data)
                        
                        # Zusätzliche Info-Datei
                        info_content = f"""Dienstplan+ Cloud Backup
Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Version: 2.1
Benutzer: {st.session_state.current_user['name']} ({st.session_state.current_user['email']})

Dieses Backup enthält alle App-Daten:
- Benutzerkonten und Rollen
- Alle Buchungen und Schichten  
- SMS/E-Mail-Vorlagen
- Audit-Protokoll
- System-Einstellungen

Zum Wiederherstellen:
1. Backup-ZIP-Datei über "Backup einspielen" hochladen
2. Die App wird komplett auf diesen Stand zurückgesetzt
3. Alle aktuellen Daten gehen verloren!
"""
                        zip_file.writestr("README.txt", info_content)
                    
                    zip_buffer.seek(0)
                    
                    st.download_button(
                        label="📥 Backup herunterladen",
                        data=zip_buffer.getvalue(),
                        file_name=f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip"
                    )
                    
                    st.session_state.db.log_action(
                        st.session_state.current_user['id'],
                        'backup_created',
                        f"Full backup created and downloaded"
                    )
                    
                    st.success("✅ Backup erfolgreich erstellt und zum Download bereit!")
                    
                except Exception as e:
                    st.error(f"❌ Fehler beim Erstellen des Backups: {str(e)}")
        
        with col2:
            st.markdown("### 📤 Backup wiederherstellen")
            st.warning("⚠️ ACHTUNG: Alle aktuellen Daten gehen verloren!")
            
            uploaded_file = st.file_uploader(
                "Backup-Datei auswählen",
                type=['zip'],
                help="Wählen Sie eine zuvor erstellte Backup-ZIP-Datei"
            )
            
            if uploaded_file is not None:
                try:
                    # ZIP-Datei lesen
                    with zipfile.ZipFile(uploaded_file, 'r') as zip_file:
                        json_files = [name for name in zip_file.namelist() if name.endswith('.json')]
                        
                        if json_files:
                            backup_json = zip_file.read(json_files[0]).decode('utf-8')
                            
                            st.markdown("**📋 Backup-Inhalt gefunden:**")
                            st.success(f"✅ Backup-Datei: {json_files[0]}")
                            
                            if st.button("🔄 BACKUP JETZT EINSPIELEN", type="secondary"):
                                success, message = st.session_state.db.restore_backup(backup_json)
                                
                                if success:
                                    st.session_state.db.log_action(
                                        st.session_state.current_user['id'],
                                        'backup_restored',
                                        f"Backup restored from {uploaded_file.name}"
                                    )
                                    st.success("✅ Backup erfolgreich wiederhergestellt!")
                                    st.info("🔄 Die App wird in 3 Sekunden neu geladen...")
                                    time.sleep(3)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                        else:
                            st.error("❌ Keine gültige Backup-Datei gefunden")
                            
                except Exception as e:
                    st.error(f"❌ Fehler beim Lesen der Backup-Datei: {str(e)}")
        
        # Wiederherstellungsanleitung
        st.markdown("---")
        st.markdown("### 📖 Anleitung zur Wiederherstellung")
        
        st.markdown("""
        **🔧 Schritt-für-Schritt Wiederherstellung:**
        
        1. **Backup erstellen** - Laden Sie regelmäßig Backups herunter
        2. **Bei Problemen** - Gehen Sie zum Admin-Panel → Backup Tab
        3. **Backup hochladen** - Wählen Sie die letzte gute Backup-ZIP-Datei
        4. **Wiederherstellen** - Klicken Sie "BACKUP JETZT EINSPIELEN"
        5. **Neustart** - Die App lädt automatisch neu mit den wiederhergestellten Daten
        
        **⚠️ Wichtige Hinweise:**
        - Alle aktuellen Daten werden durch das Backup ersetzt
        - Laden Sie vor kritischen Änderungen immer ein Backup herunter
        - Backup-Dateien enthalten sensible Daten - sicher aufbewahren
        - Bei Streamlit-Neustart gehen alle Daten verloren, daher Backups wichtig
        
        **🎯 Empfehlung:**
        - Tägliche Backups vor wichtigen Ereignissen
        - Wöchentliche Backups für normalen Betrieb
        - Backup vor App-Updates oder größeren Änderungen
        """)
    
    # System Tab
    with admin_tabs[6]:
        st.markdown("#### 🔧 System-Information")
        
        # Database Info
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        st.markdown("**💾 Datenbank-Tabellen:**")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            st.text(f"📊 {table[0]}: {count} Einträge")
        
        conn.close()
        
        # App Info
        st.markdown("---")
        st.markdown("**📱 App-Information:**")
        st.text(f"🏷️ Version: Dienstplan+ Cloud v2.1")
        st.text(f"📅 Aktuelles Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        st.text(f"🌍 Zeitzone: Europe/Berlin")
        
        # Feature Status
        st.markdown("---")
        st.markdown("**🎛️ Feature-Status:**")
        
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"📱 SMS Service: {'✅ Aktiv' if st.session_state.sms_service.enabled else '❌ Nicht konfiguriert'}")
            st.text(f"📧 E-Mail Service: {'✅ Aktiv' if st.session_state.email_service.enabled else '❌ Nicht konfiguriert'}")
            st.text("📅 Feiertage Bayern: ✅ Integriert")
            st.text("🏊‍♂️ Sommer-Sperrzeit: ✅ Juni-September")
        
        with col2:
            st.text("🗄️ Datenbank: ✅ SQLite")
            st.text("📤 Export Funktionen: ✅ CSV/iCal")
            st.text("🔍 Audit Log: ✅ Aktiv")
            st.text("💾 Backup System: ✅ Verfügbar")
        
        # System Actions
        st.markdown("---")
        st.markdown("**🔧 System-Aktionen:**")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗂️ Audit Log anzeigen"):
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT al.timestamp, u.name, al.action, al.details
                    FROM audit_log al
                    JOIN users u ON al.user_id = u.id
                    ORDER BY al.timestamp DESC
                    LIMIT 50
                ''')
                audit_entries = cursor.fetchall()
                conn.close()
                
                if audit_entries:
                    st.markdown("**📋 Letzte 50 Audit-Einträge:**")
                    for entry in audit_entries:
                        timestamp = datetime.fromisoformat(entry[0]).strftime('%d.%m.%Y %H:%M')
                        st.text(f"⏰ {timestamp} | 👤 {entry[1]} | 🎬 {entry[2]} | 📝 {entry[3]}")
                else:
                    st.info("Keine Audit-Einträge vorhanden")
        
        with col2:
            if st.button("🔄 7-Tage-Warnungen prüfen"):
                try:
                    check_7_day_warnings()
                    st.success("✅ 7-Tage-Warnungen erfolgreich geprüft")
                except Exception as e:
                    st.error(f"❌ Fehler beim Prüfen: {str(e)}")

# Hauptanwendung
def main():
    # Session State initialisieren
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    
    # Routing
    if st.session_state.current_user is None:
        show_login()
    else:
        show_main_app()

if __name__ == "__main__":
    main()