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

# Seite konfigurieren
st.set_page_config(
    page_title="Dienstplan+ Cloud",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS für professionelles Design
st.markdown("""
<style>
    .main > div {
        padding-top: 1rem;
    }
    .stButton > button {
        background-color: #21808d;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 500;
        width: 100%;
        transition: background-color 0.3s;
    }
    .stButton > button:hover {
        background-color: #1d6b75;
    }
    .shift-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #21808d;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .holiday-card {
        background: #fef2f2;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        margin: 0.5rem 0;
    }
    .available-slot {
        background: #f0fdf4;
        border-left: 4px solid #10b981;
    }
    .booked-slot {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
    }
    .user-slot {
        background: #e0f2fe;
        border-left: 4px solid #0369a1;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        text-align: center;
    }
    .success-message {
        padding: 1rem;
        background: #f0fdf4;
        border: 1px solid #10b981;
        border-radius: 8px;
        color: #065f46;
    }
    .error-message {
        padding: 1rem;
        background: #fef2f2;
        border: 1px solid #ef4444;
        border-radius: 8px;
        color: #991b1b;
    }
    .info-message {
        padding: 1rem;
        background: #eff6ff;
        border: 1px solid #3b82f6;
        border-radius: 8px;
        color: #1e40af;
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
        
        # Standard Admin User anlegen (falls nicht vorhanden)
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        if cursor.fetchone()[0] == 0:
            admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute('''
                INSERT INTO users (email, phone, name, password_hash, role, sms_opt_in)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('admin@dienstplan.local', '+49 151 12345678', 'Max Mustermann', admin_hash, 'admin', 1))
        
        # Standard Reminder Templates anlegen
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
                 'Liebe/r {{name}},\n\nin einer Stunde beginnt deine Schicht:\n{{datum}} {{slot}}\n\nViel Erfolg!')
            ]
            
            for template in templates:
                cursor.execute('''
                    INSERT INTO reminder_templates (name, timing, sms_template, whatsapp_template, email_template)
                    VALUES (?, ?, ?, ?, ?)
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
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in
            FROM users 
            WHERE email = ? AND password_hash = ? AND active = 1
        ''', (email, password_hash))
        
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
                'email_opt_in': user[7]
            }
        return None
    
    def get_user_by_id(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, phone, name, role, sms_opt_in, whatsapp_opt_in, email_opt_in
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
                'email_opt_in': user[7]
            }
        return None
    
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
    
    def cancel_booking(self, booking_id, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM bookings 
            WHERE id = ? AND user_id = ?
        ''', (booking_id, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def get_bookings_for_date_slot(self, slot_id, booking_date):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT b.id, b.user_id, u.name, u.phone
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.slot_id = ? AND b.booking_date = ? AND b.status = 'confirmed'
        ''', (slot_id, booking_date))
        
        bookings = cursor.fetchall()
        conn.close()
        
        return [{'id': b[0], 'user_id': b[1], 'user_name': b[2], 'phone': b[3]} for b in bookings]
    
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
            SELECT id, email, phone, name, role, active, created_at
            FROM users
            ORDER BY created_at DESC
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        return [{'id': u[0], 'email': u[1], 'phone': u[2], 'name': u[3], 'role': u[4], 'active': u[5], 'created_at': u[6]} for u in users]
    
    def log_action(self, user_id, action, details):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        ''', (user_id, action, details))
        
        conn.commit()
        conn.close()

# SMS Service
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
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            return True, message.sid
        except Exception as e:
            return False, str(e)

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

# Helper Functions
def get_week_start(date_obj):
    return date_obj - timedelta(days=date_obj.weekday())

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

def send_booking_confirmation(user, slot, date_str):
    if not user['sms_opt_in']:
        return
    
    slot_info = next(s for s in WEEKLY_SLOTS if s['id'] == slot)
    message = f"Bestätigung: Schicht gebucht für {date_str}, {slot_info['day_name']} {slot_info['start_time']}-{slot_info['end_time']}. Bei Fragen antworten Sie auf diese SMS."
    
    success, result = st.session_state.sms_service.send_sms(user['phone'], message)
    if success:
        st.session_state.db.log_action(user['id'], 'sms_sent', f'Booking confirmation sent to {user['phone']}')

def generate_ical(bookings):
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

# Authentication
def show_login():
    st.markdown("### 🔐 Anmeldung bei Dienstplan+ Cloud")
    
    tab1, tab2 = st.tabs(["🔑 Anmelden", "📝 Registrieren"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("📧 E-Mail", placeholder="ihre.email@beispiel.de")
            password = st.text_input("🔒 Passwort", type="password")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                submit = st.form_submit_button("Anmelden", type="primary")
            
            if submit:
                if email and password:
                    user = st.session_state.db.authenticate_user(email, password)
                    if user:
                        st.session_state.current_user = user
                        st.session_state.db.log_action(user['id'], 'login', f'User logged in from web')
                        st.success(f"Willkommen, {user['name']}!")
                        st.rerun()
                    else:
                        st.error("❌ Ungültige Anmeldedaten")
                else:
                    st.error("❌ Bitte alle Felder ausfüllen")
        
        # Demo-Logins anzeigen
        st.markdown("---")
        st.markdown("**🎯 Demo-Zugang:**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👑 Als Admin anmelden"):
                user = st.session_state.db.authenticate_user("admin@dienstplan.local", "admin123")
                if user:
                    st.session_state.current_user = user
                    st.rerun()
        with col2:
            st.markdown("**Admin:** admin@dienstplan.local  \n**Passwort:** admin123")
    
    with tab2:
        with st.form("register_form"):
            st.markdown("**👥 Neuen Account erstellen**")
            
            reg_name = st.text_input("👤 Vollständiger Name", placeholder="Max Mustermann")
            reg_email = st.text_input("📧 E-Mail Adresse", placeholder="max@beispiel.de")
            reg_phone = st.text_input("📱 Telefonnummer", placeholder="+49 151 12345678")
            reg_password = st.text_input("🔒 Passwort", type="password", help="Mindestens 6 Zeichen")
            reg_password_confirm = st.text_input("🔒 Passwort wiederholen", type="password")
            
            sms_consent = st.checkbox("📱 SMS-Erinnerungen erhalten (empfohlen)", value=True)
            
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
                        st.success("✅ Account erfolgreich erstellt! Sie können sich jetzt anmelden.")
                        st.session_state.db.log_action(user_id, 'account_created', f'New user registered: {reg_name}')
                        
                        # SMS-Opt-in aktualisieren
                        if sms_consent:
                            conn = st.session_state.db.get_connection()
                            cursor = conn.cursor()
                            cursor.execute('UPDATE users SET sms_opt_in = 1 WHERE id = ?', (user_id,))
                            conn.commit()
                            conn.close()
                        
                        st.balloons()
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
                st.session_state.active_page = 'profile'
                st.rerun()
        with col3b:
            if st.button("🚪 Abmelden"):
                st.session_state.db.log_action(user['id'], 'logout', 'User logged out')
                st.session_state.current_user = None
                st.rerun()
    
    st.markdown("---")
    
    # Tab Navigation
    if 'active_page' not in st.session_state:
        st.session_state.active_page = 'plan'
    
    if user['role'] == 'admin':
        tab_names = ["📅 Plan", "👤 Meine Schichten", "👥 Team", "⚙️ Admin"]
        tabs = st.tabs(tab_names)
        tab_keys = ['plan', 'my_shifts', 'team', 'admin']
    else:
        tab_names = ["📅 Plan", "👤 Meine Schichten", "👥 Team"]
        tabs = st.tabs(tab_names)
        tab_keys = ['plan', 'my_shifts', 'team']
    
    # Tab Content
    for i, (tab, key) in enumerate(zip(tabs, tab_keys)):
        with tab:
            if key == 'plan':
                show_schedule_tab()
            elif key == 'my_shifts':
                show_my_shifts_tab()
            elif key == 'team':
                show_team_tab()
            elif key == 'admin' and user['role'] == 'admin':
                show_admin_tab()
            elif key == 'profile':
                show_profile_tab()

def show_schedule_tab():
    st.markdown("### 📅 Wochenplan")
    
    # Woche auswählen
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Vorherige Woche"):
            if 'current_week_start' not in st.session_state:
                st.session_state.current_week_start = get_week_start(datetime.now())
            st.session_state.current_week_start -= timedelta(days=7)
    
    with col2:
        if 'current_week_start' not in st.session_state:
            st.session_state.current_week_start = get_week_start(datetime.now())
        
        week_end = st.session_state.current_week_start + timedelta(days=6)
        st.markdown(f"**📆 Woche vom {st.session_state.current_week_start.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}**")
    
    with col3:
        if st.button("Nächste Woche ➡️"):
            st.session_state.current_week_start += timedelta(days=7)
    
    st.markdown("---")
    
    # Schichten der Woche anzeigen
    for slot in WEEKLY_SLOTS:
        slot_date = get_slot_date(st.session_state.current_week_start, slot['day'])
        
        with st.container():
            # Prüfen ob Feiertag
            holiday_name = get_holiday_name(slot_date)
            
            if holiday_name:
                st.markdown(f"""
                <div class="holiday-card">
                    <h4>🚫 {slot['day_name']} - {slot['start_time']} bis {slot['end_time']}</h4>
                    <p><strong>📅 {slot_date}</strong></p>
                    <p>🎄 <strong>Feiertag:</strong> {holiday_name}</p>
                    <p>❌ Keine Schichten an diesem Tag</p>
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
                                
                                st.success("✅ Schicht erfolgreich gebucht! 📱 SMS-Bestätigung wird gesendet.")
                                st.rerun()
                            else:
                                st.error(f"❌ Fehler beim Buchen: {result}")
    
    # Feiertage der Woche anzeigen
    week_holidays = []
    for i in range(7):
        current_date = (st.session_state.current_week_start + timedelta(days=i)).strftime('%Y-%m-%d')
        holiday_name = get_holiday_name(current_date)
        if holiday_name:
            week_holidays.append({'date': current_date, 'name': holiday_name})
    
    if week_holidays:
        st.markdown("---")
        st.markdown("### 🎄 Feiertage dieser Woche")
        for holiday in week_holidays:
            date_obj = datetime.strptime(holiday['date'], '%Y-%m-%d')
            st.info(f"📅 {date_obj.strftime('%d.%m.%Y')} ({date_obj.strftime('%A')}) - {holiday['name']}")

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
                        if st.button(f"❌", key=f"cancel_my_{booking['id']}", help="Schicht stornieren"):
                            if st.session_state.db.cancel_booking(booking['id'], st.session_state.current_user['id']):
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
        
        if st.button("📅 Zum Schichtplan"):
            st.session_state.active_page = 'plan'
            st.rerun()

def show_team_tab():
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
    
    # Team-Mitglieder
    st.markdown("### 👥 Team-Mitglieder")
    
    for user in sorted(active_users, key=lambda x: x['name']):
        user_bookings = st.session_state.db.get_user_bookings(user['id'])
        future_bookings = [b for b in user_bookings if datetime.strptime(b['date'], '%Y-%m-%d') >= datetime.now()]
        
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        
        with col1:
            role_emoji = "👑" if user['role'] == 'admin' else "👤"
            st.markdown(f"**{role_emoji} {user['name']}**")
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
    st.markdown(f"**Woche vom {week_start.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}**")
    
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
            elif bookings:
                booking = bookings[0]
                st.success(f"👤 {booking['user_name']}")
            else:
                st.warning("🟡 Noch offen")

def show_admin_tab():
    st.markdown("### ⚙️ Administrator Panel")
    
    admin_tabs = st.tabs(["👥 Benutzer", "📝 Vorlagen", "📊 Statistiken", "📤 Export", "🔧 System"])
    
    # Benutzerverwaltung
    with admin_tabs[0]:
        st.markdown("#### 👥 Benutzerverwaltung")
        
        all_users = st.session_state.db.get_all_users()
        
        # Neue Benutzer hinzufügen
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
                status_emoji = "✅" if user['active'] else "❌"
                st.write(f"{role_emoji} {status_emoji} {user['name']}")
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
        st.markdown("#### 📝 SMS-Erinnerungs-Vorlagen")
        
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reminder_templates ORDER BY timing')
        templates = cursor.fetchall()
        conn.close()
        
        for template in templates:
            with st.expander(f"📝 {template[1]} ({template[2]})"):
                with st.form(f"template_form_{template[0]}"):
                    st.markdown(f"**{template[1]}**")
                    
                    new_sms_template = st.text_area(
                        "SMS-Vorlage:",
                        value=template[3] or "",
                        height=100,
                        help="Verfügbare Platzhalter: {{name}}, {{datum}}, {{slot}}"
                    )
                    
                    new_whatsapp_template = st.text_area(
                        "WhatsApp-Vorlage:",
                        value=template[4] or "",
                        height=100,
                        help="Verfügbare Platzhalter: {{name}}, {{datum}}, {{slot}}"
                    )
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.form_submit_button("💾 Speichern"):
                            conn = st.session_state.db.get_connection()
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE reminder_templates 
                                SET sms_template = ?, whatsapp_template = ? 
                                WHERE id = ?
                            ''', (new_sms_template, new_whatsapp_template, template[0]))
                            conn.commit()
                            conn.close()
                            
                            st.session_state.db.log_action(
                                st.session_state.current_user['id'],
                                'template_updated',
                                f"Updated template: {template[1]}"
                            )
                            st.success("✅ Vorlage gespeichert")
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
                    
                    with col3:
                        active = template[5]
                        if st.form_submit_button("🔄 Status ändern"):
                            conn = st.session_state.db.get_connection()
                            cursor = conn.cursor()
                            cursor.execute('UPDATE reminder_templates SET active = ? WHERE id = ?', (not active, template[0]))
                            conn.commit()
                            conn.close()
                            st.success(f"✅ Template {'aktiviert' if not active else 'deaktiviert'}")
                            st.rerun()
        
        # SMS Service Status
        st.markdown("---")
        st.markdown("#### 📱 SMS-Service Status")
        
        if st.session_state.sms_service.enabled:
            st.success("✅ SMS-Service aktiv")
            st.info(f"📞 Sender-Nummer: {st.session_state.sms_service.from_number}")
        else:
            st.error("❌ SMS-Service nicht konfiguriert")
            st.info("💡 Konfigurieren Sie TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN und TWILIO_PHONE_NUMBER in den Secrets")
    
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
        
        # Buchungen pro Wochentag/Slot
        cursor.execute('''
            SELECT b.slot_id, COUNT(*) as count
            FROM bookings b
            WHERE b.status = "confirmed"
            GROUP BY b.slot_id
        ''')
        slot_stats = cursor.fetchall()
        
        if slot_stats:
            slot_data = []
            for stat in slot_stats:
                slot = next(s for s in WEEKLY_SLOTS if s['id'] == stat[0])
                slot_data.append({
                    'Slot': f"{slot['day_name']} {slot['start_time']}-{slot['end_time']}",
                    'Buchungen': stat[1]
                })
            
            if slot_data:
                st.markdown("#### 📅 Beliebte Schichten")
                df_slot_stats = pd.DataFrame(slot_data)
                
                fig = px.pie(
                    df_slot_stats,
                    values='Buchungen',
                    names='Slot',
                    title="Verteilung der Buchungen nach Schichten"
                )
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
        
        # iCal Export für alle Schichten
        st.markdown("---")
        st.markdown("**📅 Kalender Export**")
        
        if st.button("📅 iCal Export - Alle kommenden Schichten"):
            conn = st.session_state.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT b.id, b.slot_id, b.booking_date, u.name
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                WHERE b.status = "confirmed" AND b.booking_date >= ?
                ORDER BY b.booking_date ASC
            ''', (datetime.now().strftime('%Y-%m-%d'),))
            
            future_bookings = cursor.fetchall()
            conn.close()
            
            if future_bookings:
                ical_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//ADMIN//DE
"""
                
                for booking in future_bookings:
                    slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking[1])
                    date_str = booking[2].replace('-', '')
                    start_time = slot['start_time'].replace(':', '') + '00'
                    end_time = slot['end_time'].replace(':', '') + '00'
                    
                    ical_content += f"""BEGIN:VEVENT
UID:{booking[0]}@dienstplan-cloud-admin
DTSTART:{date_str}T{start_time}
DTEND:{date_str}T{end_time}
SUMMARY:{booking[3]} - {slot['day_name']} Schicht
DESCRIPTION:Schicht von {booking[3]} am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']}
LOCATION:Arbeitsplatz
END:VEVENT
"""
                
                ical_content += "END:VCALENDAR"
                
                st.download_button(
                    label="📥 iCal herunterladen",
                    data=ical_content,
                    file_name=f"alle_schichten_{datetime.now().strftime('%Y%m%d')}.ics",
                    mime="text/calendar"
                )
            else:
                st.info("Keine kommenden Buchungen vorhanden")
    
    # System Tab
    with admin_tabs[4]:
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
        st.text(f"🏷️ Version: Dienstplan+ Cloud v2.0")
        st.text(f"📅 Aktuelles Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        st.text(f"🌍 Zeitzone: Europe/Berlin")
        
        # Feature Status
        st.markdown("---")
        st.markdown("**🎛️ Feature-Status:**")
        
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"📱 SMS Service: {'✅ Aktiv' if st.session_state.sms_service.enabled else '❌ Nicht konfiguriert'}")
            st.text("📅 Feiertage Bayern: ✅ Integriert")
            st.text("🗄️ Datenbank: ✅ SQLite")
        
        with col2:
            st.text("📤 Export Funktionen: ✅ Verfügbar")
            st.text("🔍 Audit Log: ✅ Aktiv")
            st.text("👥 Multi-User: ✅ Unterstützt")
        
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
            if st.button("📊 System-Statistiken"):
                st.info("System-Statistiken werden im 'Statistiken' Tab angezeigt")

def show_profile_tab():
    st.markdown("### 👤 Mein Profil")
    
    user = st.session_state.current_user
    
    # Profil-Informationen
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>👤 {user['name']}</h3>
            <p>📧 {user['email']}</p>
            <p>📱 {user['phone']}</p>
            <p>🎭 {user['role'].title()}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("#### ⚙️ Benachrichtigungseinstellungen")
        
        with st.form("notification_settings"):
            current_sms = user.get('sms_opt_in', False)
            current_whatsapp = user.get('whatsapp_opt_in', False)
            current_email = user.get('email_opt_in', False)
            
            new_sms = st.checkbox("📱 SMS-Erinnerungen erhalten", value=current_sms)
            new_whatsapp = st.checkbox("💬 WhatsApp-Erinnerungen erhalten", value=current_whatsapp, disabled=True, help="Noch nicht verfügbar")
            new_email = st.checkbox("📧 E-Mail-Benachrichtigungen erhalten", value=current_email, disabled=True, help="Noch nicht verfügbar")
            
            if st.form_submit_button("💾 Einstellungen speichern"):
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users 
                    SET sms_opt_in = ?, whatsapp_opt_in = ?, email_opt_in = ? 
                    WHERE id = ?
                ''', (new_sms, new_whatsapp, new_email, user['id']))
                
                conn.commit()
                conn.close()
                
                # Session State aktualisieren
                st.session_state.current_user['sms_opt_in'] = new_sms
                st.session_state.current_user['whatsapp_opt_in'] = new_whatsapp
                st.session_state.current_user['email_opt_in'] = new_email
                
                st.session_state.db.log_action(
                    user['id'],
                    'settings_updated',
                    f"Updated notification settings"
                )
                
                st.success("✅ Einstellungen gespeichert!")
                st.rerun()
    
    st.markdown("---")
    
    # Passwort ändern
    st.markdown("#### 🔒 Passwort ändern")
    
    with st.form("change_password"):
        current_password = st.text_input("Aktuelles Passwort", type="password")
        new_password = st.text_input("Neues Passwort", type="password")
        confirm_password = st.text_input("Neues Passwort bestätigen", type="password")
        
        if st.form_submit_button("🔑 Passwort ändern"):
            if not all([current_password, new_password, confirm_password]):
                st.error("❌ Bitte alle Felder ausfüllen")
            elif new_password != confirm_password:
                st.error("❌ Neue Passwörter stimmen nicht überein")
            elif len(new_password) < 6:
                st.error("❌ Neues Passwort muss mindestens 6 Zeichen lang sein")
            else:
                # Aktuelles Passwort prüfen
                current_hash = hashlib.sha256(current_password.encode()).hexdigest()
                
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user['id'],))
                stored_hash = cursor.fetchone()[0]
                
                if current_hash == stored_hash:
                    # Neues Passwort setzen
                    new_hash = hashlib.sha256(new_password.encode()).hexdigest()
                    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user['id']))
                    conn.commit()
                    conn.close()
                    
                    st.session_state.db.log_action(user['id'], 'password_changed', 'Password changed by user')
                    st.success("✅ Passwort erfolgreich geändert!")
                else:
                    conn.close()
                    st.error("❌ Aktuelles Passwort ist falsch")
    
    st.markdown("---")
    
    # Daten-Export
    st.markdown("#### 📤 Meine Daten")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Meine Daten exportieren (JSON)", type="primary"):
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
    
    with col2:
        st.markdown("**🛡️ Datenschutz**")
        st.info("Sie können jederzeit eine Kopie Ihrer gespeicherten Daten anfordern oder Ihr Konto löschen lassen.")
        
        if st.button("🗑️ Account löschen", help="Unwiderruflich!"):
            if st.button("⚠️ Wirklich löschen? (Dieser Schritt kann nicht rückgängig gemacht werden)"):
                # Account deaktivieren statt löschen (DSGVO-konform)
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET active = 0 WHERE id = ?', (user['id'],))
                conn.commit()
                conn.close()
                
                st.session_state.db.log_action(user['id'], 'account_deleted', 'Account deleted by user')
                st.success("Account wurde deaktiviert. Sie werden automatisch abgemeldet.")
                
                st.session_state.current_user = None
                st.rerun()

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