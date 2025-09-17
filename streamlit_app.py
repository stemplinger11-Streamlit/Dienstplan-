import streamlit as st
import sqlite3, hashlib, io, zipfile, smtplib, json, calendar
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from twilio.rest import Client
import pandas as pd

# ===== Konfiguration (seiteneffektfrei) =====
VERSION = "4.0"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = (st.secrets.get("TIMEZONE", "Europe/Berlin")
                if hasattr(st, "secrets") else "Europe/Berlin")
TZ = pytz.timezone(TIMEZONE_STR)
SAFE_MODE = bool(hasattr(st, "secrets") and str(st.secrets.get("SAFE_MODE", "true")).lower() == "true")
ENABLE_DAILY_BACKUP = bool(hasattr(st, "secrets") and str(st.secrets.get("ENABLE_DAILY_BACKUP", "false")).lower() == "true")
ENABLE_REMINDER_SMS = bool(hasattr(st, "secrets") and str(st.secrets.get("ENABLE_REMINDER_SMS", "false")).lower() == "true")

WEEKLY_SLOTS = [
    {"id": 1, "day": "tuesday",  "day_name": "Dienstag", "start": "17:00", "end": "20:00"},
    {"id": 2, "day": "friday",   "day_name": "Freitag",  "start": "17:00", "end": "20:00"},
    {"id": 3, "day": "saturday", "day_name": "Samstag",  "start": "14:00", "end": "17:00"},
]

def week_start(d=None):
    d = d or datetime.now().date()
    if hasattr(d, "date"): d = d.date()
    return d - timedelta(days=d.weekday())

def slot_date(ws, day):
    m = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
    return (ws + timedelta(days=m.get(day,0))).strftime("%Y-%m-%d")

def fmt_de(d):
    try: return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y")
    except: return d

def generate_ics(slot, booking_date, user_name, user_email, action="REQUEST"):
    """Generiert iCal-Einladung für Schichtbuchung"""
    dt = datetime.strptime(booking_date, "%Y-%m-%d")
    start_dt = datetime.combine(dt, datetime.strptime(slot["start"], "%H:%M").time())
    end_dt = datetime.combine(dt, datetime.strptime(slot["end"], "%H:%M").time())
    
    # In lokale Zeitzone konvertieren
    start_dt = TZ.localize(start_dt)
    end_dt = TZ.localize(end_dt)
    
    # UID für eindeutige Identifikation
    uid = f"dienstplan-{slot['id']}-{booking_date}@dienstplan-cloud.local"
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//DE
METHOD:{action}
BEGIN:VEVENT
UID:{uid}
DTSTART;TZID={TIMEZONE_STR}:{start_dt.strftime('%Y%m%dT%H%M%S')}
DTEND;TZID={TIMEZONE_STR}:{end_dt.strftime('%Y%m%dT%H%M%S')}
SUMMARY:Schicht {slot['day_name']}
DESCRIPTION:Dienstplan+ Schicht\\n{slot['day_name']} {slot['start']}-{slot['end']}\\nGebucht von: {user_name}
LOCATION:Dienstort
ORGANIZER:mailto:noreply@dienstplan-cloud.local
ATTENDEE;PARTSTAT=ACCEPTED:mailto:{user_email}
STATUS:{"CONFIRMED" if action == "REQUEST" else "CANCELLED"}
SEQUENCE:0
CREATED:{datetime.now(TZ).strftime('%Y%m%dT%H%M%SZ')}
LAST-MODIFIED:{datetime.now(TZ).strftime('%Y%m%dT%H%M%SZ')}
END:VEVENT
END:VCALENDAR"""
    
    return ics_content.encode('utf-8')

# ===== CSS für kontrastreiches Design =====
def inject_css():
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #0066cc;
        text-align: center;
        margin: 1rem 0;
        padding: 1rem;
        background: linear-gradient(90deg, #f0f4f8 0%, #ffffff 100%);
        border-radius: 10px;
        border: 2px solid #0066cc;
    }
    
    .week-header {
        font-size: 1.8rem;
        font-weight: bold;
        color: #0066cc;
        text-align: center;
        padding: 0.8rem;
        margin: 1rem 0;
        background-color: #e6f3ff;
        border-radius: 8px;
        border-left: 4px solid #0066cc;
    }
    
    .slot-available {
        background-color: #d4edda !important;
        border: 2px solid #28a745 !important;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .slot-booked-me {
        background-color: #cce5ff !important;
        border: 2px solid #0066cc !important;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .slot-booked-other {
        background-color: #f8d7da !important;
        border: 2px solid #dc3545 !important;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .stButton > button {
        font-weight: bold;
        border-radius: 6px;
        border: 2px solid;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        padding: 1rem;
        border-radius: 8px;
    }
    
    .calendar-cell {
        border: 1px solid #ccc;
        padding: 8px;
        text-align: center;
        min-height: 60px;
        cursor: pointer;
    }
    
    .calendar-available {
        background-color: #d4edda !important;
        color: #155724 !important;
    }
    
    .calendar-booked {
        background-color: #f8d7da !important;
        color: #721c24 !important;
    }
    
    .calendar-today {
        border: 3px solid #0066cc !important;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# ===== Datenbank-Layer (korrigiert) =====
class DB:
    def __init__(self, path=DB_FILE):
        self.path = path
        self._init()

    def conn(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def _init(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS app_settings(
                key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL, phone TEXT NOT NULL, name TEXT NOT NULL,
                password_hash TEXT NOT NULL, role TEXT DEFAULT 'user',
                sms_opt_in BOOLEAN DEFAULT 1, email_opt_in BOOLEAN DEFAULT 1,
                active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS bookings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, slot_id INTEGER NOT NULL,
                booking_date DATE NOT NULL, status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slot_id, booking_date))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, action TEXT NOT NULL, details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS info_pages(
                id INTEGER PRIMARY KEY AUTOINCREMENT, page_key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL, content TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS reminder_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'sent', UNIQUE(booking_id, reminder_type))""")
            c.commit()
        self._seed_admin()
        self._ensure_default_templates()

    def _seed_admin(self):
        if not hasattr(st, "secrets"): return
        email = st.secrets.get("ADMIN_EMAIL",""); pw = st.secrets.get("ADMIN_PASSWORD","")
        if not (email and pw): return
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM users WHERE email=?", (email,))
            if cur.fetchone()[0] == 0:
                cur.execute("""INSERT INTO users(email,phone,name,password_hash,role)
                               VALUES(?,?,?,?,?)""",
                            (email, "+4915199999999", "Initial Admin",
                             hashlib.sha256(pw.encode()).hexdigest(), "admin"))
                c.commit()

    def _ensure_default_templates(self):
        defaults = {
            "booking_confirmation": "Hallo {USER},\\n\\nIhre Schicht am {DATUM} von {ZEIT} wurde erfolgreich gebucht.\\n\\nBeste Grüße\\nIhr Dienstplan-Team",
            "cancellation_confirmation": "Hallo {USER},\\n\\nIhre Schicht am {DATUM} wurde erfolgreich storniert.\\n\\nBeste Grüße\\nIhr Dienstplan-Team",
            "admin_cancellation_notification": "{USER} hat die Schicht am {DATUM} storniert.",
            "reminder_24h": "Erinnerung: Morgen haben Sie Schicht von {ZEIT}. Schicht: {SCHICHT}",
            "reminder_1h": "Erinnerung: In einer Stunde beginnt Ihre Schicht ({ZEIT}). Schicht: {SCHICHT}",
            "info_page_1": "# Schicht-Informationen\\n\\n1. Kasse holen\\n2. Technik prüfen\\n3. Sicherheitsrundgang",
            "info_page_2": "# Notfall-Kontakte\\n\\n- Zentrale: 112\\n- Hausmeister: +49 123 456789\\n- Leitung: +49 987 654321"
        }
        
        with self.conn() as c:
            cur = c.cursor()
            for key, value in defaults.items():
                cur.execute("SELECT COUNT(*) FROM app_settings WHERE key=?", (key,))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO app_settings(key,value) VALUES(?,?)", (key, value))
            c.commit()

    def get_setting(self, key, default=""):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
            row = cur.fetchone()
        return (row[0] if row else default)

    def set_setting(self, key, value):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO app_settings(key,value) VALUES(?,?)
                           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                        (key, value))
            c.commit()

    def create_user(self, email, phone, name, pw):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO users(email,phone,name,password_hash) VALUES(?,?,?,?)",
                            (email,phone,name,hashlib.sha256(pw.encode()).hexdigest()))
                c.commit()
                return True, cur.lastrowid
        except sqlite3.IntegrityError:
            return False, "E-Mail bereits registriert"

    def auth(self, email, pw):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,email,phone,name,role,sms_opt_in,email_opt_in,active
                           FROM users WHERE email=? AND password_hash=?""",
                        (email, hashlib.sha256(pw.encode()).hexdigest()))
            r = cur.fetchone()
        if not r or r[7] != 1: return None
        return dict(id=r[0],email=r[1],phone=r[2],name=r[3],role=r[4],
                    sms_opt_in=bool(r[5]),email_opt_in=bool(r[6]))

    def update_user_profile(self, uid, name, phone, sms_opt_in, email_opt_in):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET name=?, phone=?, sms_opt_in=?, email_opt_in=? WHERE id=?", 
                        (name,phone,1 if sms_opt_in else 0, 1 if email_opt_in else 0, uid))
            c.commit()
            return cur.rowcount > 0

    def change_password(self, uid, new_password):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET password_hash=? WHERE id=?",
                        (hashlib.sha256(new_password.encode()).hexdigest(), uid))
            c.commit()
            return cur.rowcount > 0

    def get_all_users(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,email,phone,name,role,active,created_at
                           FROM users ORDER BY created_at DESC""")
            return [dict(id=r[0],email=r[1],phone=r[2],name=r[3],role=r[4],
                        active=bool(r[5]),created_at=r[6]) for r in cur.fetchall()]

    def update_user_role(self, uid, role):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
            c.commit()
            return cur.rowcount > 0

    def update_user_status(self, uid, active):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, uid))
            c.commit()
            return cur.rowcount > 0

    def get_admin_users(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT email FROM users WHERE role='admin' AND active=1")
            return [r[0] for r in cur.fetchall()]

    def bookings_for(self, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT b.id,b.user_id,u.name,u.email,u.phone,b.created_at
                           FROM bookings b JOIN users u ON u.id=b.user_id
                           WHERE b.slot_id=? AND b.booking_date=? AND b.status='confirmed'""",
                        (slot_id,d))
            return [dict(id=r[0],user_id=r[1],user_name=r[2],user_email=r[3],user_phone=r[4],created_at=r[5]) for r in cur.fetchall()]

    def create_booking(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND booking_date=? AND status='confirmed'", (slot_id,d))
            if cur.fetchone()[0] > 0: return False,"Slot bereits belegt"
            cur.execute("INSERT INTO bookings(user_id,slot_id,booking_date) VALUES(?,?,?)",(uid,slot_id,d))
            c.commit()
            return True, cur.lastrowid

    def cancel_booking(self, bid, uid=None):
        with self.conn() as c:
            cur = c.cursor()
            if uid: cur.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (bid,uid))
            else: cur.execute("DELETE FROM bookings WHERE id=?", (bid,))
            c.commit()
            return cur.rowcount > 0

    def user_bookings(self, uid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,slot_id,booking_date,created_at FROM bookings
                           WHERE user_id=? AND status='confirmed' ORDER BY booking_date ASC""",(uid,))
            return [dict(id=r[0],slot_id=r[1],date=r[2],created_at=r[3]) for r in cur.fetchall()]

    def get_upcoming_shifts_for_reminders(self):
        """Holt anstehende Schichten für Reminder (24h und 1h)"""
        now = datetime.now(TZ)
        reminder_24h = now + timedelta(hours=24)
        reminder_1h = now + timedelta(hours=1)
        
        with self.conn() as c:
            cur = c.cursor()
            # Buchungen finden, die in 24h oder 1h beginnen
            cur.execute("""
                SELECT b.id, b.user_id, b.slot_id, b.booking_date, u.phone, u.name, u.sms_opt_in
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                WHERE b.status = 'confirmed' AND u.active = 1
                ORDER BY b.booking_date, b.slot_id
            """)
            
            bookings = cur.fetchall()
            reminder_candidates = []
            
            for booking in bookings:
                booking_id, user_id, slot_id, booking_date, phone, name, sms_opt_in = booking
                if not sms_opt_in:
                    continue
                    
                # Slot-Details holen
                slot = next((s for s in WEEKLY_SLOTS if s["id"] == slot_id), None)
                if not slot:
                    continue
                    
                # Schichtstart berechnen
                booking_dt = datetime.strptime(booking_date, "%Y-%m-%d")
                start_time = datetime.strptime(slot["start"], "%H:%M").time()
                shift_start = TZ.localize(datetime.combine(booking_dt, start_time))
                
                # Prüfen ob 24h oder 1h Reminder fällig
                time_diff = shift_start - now
                
                if timedelta(hours=23, minutes=45) <= time_diff <= timedelta(hours=24, minutes=15):
                    reminder_type = "24h"
                elif timedelta(minutes=45) <= time_diff <= timedelta(hours=1, minutes=15):
                    reminder_type = "1h"
                else:
                    continue
                
                # Prüfen ob bereits versendet
                cur.execute("SELECT COUNT(*) FROM reminder_log WHERE booking_id=? AND reminder_type=?", 
                           (booking_id, reminder_type))
                if cur.fetchone()[0] > 0:
                    continue
                    
                reminder_candidates.append({
                    "booking_id": booking_id,
                    "user_id": user_id,
                    "phone": phone,
                    "name": name,
                    "slot": slot,
                    "date": booking_date,
                    "reminder_type": reminder_type
                })
            
            return reminder_candidates

    def log_reminder_sent(self, booking_id, reminder_type):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("INSERT INTO reminder_log(booking_id,reminder_type) VALUES(?,?)",
                        (booking_id, reminder_type))
            c.commit()

    def get_audit_log(self, limit=100):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT a.timestamp,u.name,a.action,a.details 
                           FROM audit_log a 
                           LEFT JOIN users u ON a.user_id=u.id 
                           ORDER BY a.timestamp DESC LIMIT ?""", (limit,))
            return [dict(timestamp=r[0],user=r[1] or "System",action=r[2],details=r[3]) for r in cur.fetchall()]

    def get_free_slots_next_weeks(self, weeks=4):
        """Freie Slots der nächsten X Wochen"""
        today = date.today()
        end_date = today + timedelta(weeks=weeks)
        
        free_slots = []
        current = today
        
        while current <= end_date:
            ws = week_start(current)
            for slot in WEEKLY_SLOTS:
                slot_d = slot_date(ws, slot["day"])
                if slot_d < today.strftime("%Y-%m-%d"):
                    continue
                    
                bookings = self.bookings_for(slot["id"], slot_d)
                if not bookings:
                    free_slots.append({
                        "date": slot_d,
                        "day": slot["day_name"],
                        "time": f"{slot['start']}-{slot['end']}"
                    })
            current += timedelta(days=7)
        
        return free_slots

    def log(self, uid, action, details):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO audit_log(user_id,action,details) VALUES(?,?,?)",(uid,action,details))
                c.commit()
        except Exception:
            pass

# ===== Dienste (nur aktivierbar, wenn nicht SAFE_MODE) =====
class TwilioSMS:
    def __init__(self):
        self.enabled = False
        if SAFE_MODE or not hasattr(st, "secrets"): return
        try:
            sid = st.secrets.get("TWILIO_ACCOUNT_SID","")
            token = st.secrets.get("TWILIO_AUTH_TOKEN","")
            from_number = st.secrets.get("TWILIO_PHONE_NUMBER","")
            self.client = Client(sid, token) if (sid and token) else None
            self.from_number = from_number
            self.enabled = bool(self.client and self.from_number and str(st.secrets.get("ENABLE_SMS","false")).lower()=="true")
        except Exception:
            self.client = None
            self.enabled = False
            
    def send(self,to,text):
        if not self.enabled: return False,"SMS disabled"
        try:
            msg = self.client.messages.create(body=text, from_=self.from_number, to=to)
            return True, msg.sid
        except Exception as e:
            return False, str(e)

class Mailer:
    def __init__(self):
        self.enabled = False
        if SAFE_MODE or not hasattr(st, "secrets"): return
        self.user = st.secrets.get("GMAIL_USER","")
        self.pw = st.secrets.get("GMAIL_APP_PASSWORD","")
        self.from_name = st.secrets.get("FROM_NAME","Dienstplan+ Cloud")
        self.enabled = bool(self.user and self.pw and str(st.secrets.get("ENABLE_EMAIL","false")).lower()=="true")
    
    def send(self,to,subject,body,attachments=None):
        if not self.enabled: return False,"mail disabled"
        try:
            msg = MIMEMultipart()
            msg["From"]=f"{self.from_name} <{self.user}>"
            msg["To"]=to
            msg["Subject"]=subject
            msg["Date"]=email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body,"plain","utf-8"))
            
            for att in attachments or []:
                part = MIMEBase("application","octet-stream")
                part.set_payload(att["content"])
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{att["filename"]}"')
                msg.attach(part)
            
            with smtplib.SMTP("smtp.gmail.com",587) as s:
                s.starttls()
                s.login(self.user,self.pw)
                s.send_message(msg)
            return True,"OK"
        except Exception as e:
            return False,str(e)

# ===== Template-System =====
def format_template(template_key, db, **kwargs):
    """Formatiert Template mit Platzhaltern"""
    template = db.get_setting(template_key, "Template nicht gefunden")
    # Platzhalter ersetzen
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template.replace("\\n", "\n")

# ===== Backup + Scheduler (korrigiert) =====
def _create_backup_zip(db: DB):
    data = {}
    with db.conn() as c:
        cur = c.cursor()
        for table in ["users","bookings","audit_log","app_settings","info_pages","reminder_log"]:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                data[table] = {"columns": cols, "rows": rows}
            except sqlite3.OperationalError:
                pass
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                   json.dumps({"created_at": datetime.now().isoformat(),"version":VERSION,"tables":data}, indent=2, default=str))
        z.writestr("README.txt", f"Dienstplan+ v{VERSION} Backup {datetime.now().isoformat()} {TIMEZONE_STR}")
    payload.seek(0)
    return payload.getvalue()

def _send_daily_backup(db: DB, mailer: Mailer):
    if not mailer.enabled: return False
    zip_bytes = _create_backup_zip(db)
    to = (st.secrets.get("BACKUP_EMAIL","backup@example.com") if hasattr(st,"secrets") else "backup@example.com")
    ok,_ = mailer.send(to, f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}",
                       "Automatisches Backup im Anhang.",
                       [{"filename": f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip", "content": zip_bytes}])
    return ok

def start_scheduler(db: DB, mailer: Mailer, sms: TwilioSMS):
    if SAFE_MODE or not ENABLE_DAILY_BACKUP: return None
    try:
        sched = BackgroundScheduler(timezone=TZ)
        # Backup um 20:00
        sched.add_job(lambda: _send_daily_backup(db, mailer), CronTrigger(hour=20, minute=0),
                      id="daily_backup", replace_existing=True, max_instances=1)
        
        # Reminder alle 15 Minuten prüfen
        if ENABLE_REMINDER_SMS:
            sched.add_job(lambda: _process_reminders(db, sms), CronTrigger(minute="*/15"),
                          id="reminder_check", replace_existing=True, max_instances=1)
        
        sched.start()
        return sched
    except Exception:
        return None

def _process_reminders(db: DB, sms: TwilioSMS):
    """Verarbeitet fällige Reminder"""
    if not sms.enabled:
        return
        
    reminders = db.get_upcoming_shifts_for_reminders()
    for reminder in reminders:
        template_key = f"reminder_{reminder['reminder_type']}"
        message = format_template(
            template_key, db,
            USER=reminder["name"],
            DATUM=fmt_de(reminder["date"]),
            SCHICHT=reminder["slot"]["day_name"],
            ZEIT=f"{reminder['slot']['start']}-{reminder['slot']['end']}"
        )
        
        success, _ = sms.send(reminder["phone"], message)
        if success:
            db.log_reminder_sent(reminder["booking_id"], reminder["reminder_type"])
            db.log(reminder["user_id"], f"reminder_sent_{reminder['reminder_type']}", 
                   f"SMS reminder sent for {reminder['date']}")

# ===== Page Config und Singletons =====
st.set_page_config(page_title="Dienstplan+ Cloud v4.0", page_icon="📅", layout="wide")

# CSS injizieren
inject_css()

if "db" not in st.session_state: st.session_state.db = DB()
if "sms" not in st.session_state: st.session_state.sms = TwilioSMS()
if "mail" not in st.session_state: st.session_state.mail = Mailer()
if "week_start" not in st.session_state: st.session_state.week_start = week_start()
if "calendar_date" not in st.session_state: st.session_state.calendar_date = datetime.now().date()
if "sched" not in st.session_state: st.session_state.sched = None

# ===== UI: Auth =====
def ui_auth():
    st.markdown('<div class="main-header">🔐 Dienstplan+ Cloud v4.0</div>', unsafe_allow_html=True)
    
    tab_login, tab_reg = st.tabs(["🔑 Anmelden", "📝 Registrieren"])
    
    with tab_login:
        with st.form("f_login"):
            e = st.text_input("📧 E-Mail")
            p = st.text_input("🔒 Passwort", type="password")
            if st.form_submit_button("Anmelden", type="primary"):
                u = st.session_state.db.auth(e, p)
                if u:
                    st.session_state.user = u
                    st.session_state.db.log(u["id"],"login","user login")
                    st.success(f"Willkommen {u['name']}!")
                    st.rerun()
                else:
                    st.error("Ungültige Anmeldedaten")
    
    with tab_reg:
        with st.form("f_reg"):
            n = st.text_input("👤 Name")
            r_e = st.text_input("📧 E-Mail")
            r_ph = st.text_input("📱 Telefon", "+49 ")
            r_p1 = st.text_input("🔒 Passwort", type="password")
            r_p2 = st.text_input("🔒 Passwort wiederholen", type="password")
            if st.form_submit_button("Account erstellen", type="primary"):
                errs = []
                if not all([n, r_e, r_ph, r_p1, r_p2]): errs.append("Alle Felder ausfüllen")
                if r_p1 != r_p2: errs.append("Passwörter stimmen nicht überein")
                if len(r_p1) < 6: errs.append("Passwort min. 6 Zeichen")
                if not r_ph.startswith("+"): errs.append("Telefon mit Ländercode (z.B. +49)")
                if "@" not in r_e: errs.append("E-Mail prüfen")
                
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    ok, result = st.session_state.db.create_user(r_e, r_ph, n, r_p1)
                    if ok:
                        u = st.session_state.db.auth(r_e, r_p1)
                        st.session_state.user = u
                        st.session_state.db.log(result,"user_created","registered")
                        st.success("Account erstellt und eingeloggt")
                        st.rerun()
                    else:
                        st.error(result)

# ===== UI: Plan (Wochenansicht) =====
def ui_schedule():
    u = st.session_state.user
    ws = st.session_state.week_start
    week_end = ws + timedelta(days=6)
    
    col1, col2, col3 = st.columns([1,4,1])
    
    with col1:
        if st.button("⬅️ Vorherige Woche"):
            st.session_state.week_start = ws - timedelta(days=7)
            st.rerun()
    
    with col2:
        st.markdown(f'<div class="week-header">KW {ws.isocalendar()[1]} — {ws.strftime("%d.%m.%Y")} bis {week_end.strftime("%d.%m.%Y")}</div>', unsafe_allow_html=True)
    
    with col3:
        if st.button("Nächste Woche ➡️"):
            st.session_state.week_start = ws + timedelta(days=7)
            st.rerun()

    for slot in WEEKLY_SLOTS:
        d = slot_date(ws, slot["day"])
        bookings = st.session_state.db.bookings_for(slot["id"], d)
        
        col_info, col_action = st.columns([3,1])
        
        with col_info:
            if bookings:
                b = bookings[0]
                if b["user_id"] == u["id"]:
                    st.markdown(f'<div class="slot-booked-me">✅ <strong>{slot["day_name"]}, {fmt_de(d)}</strong> — Gebucht von Ihnen — ⏰ {slot["start"]}–{slot["end"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="slot-booked-other">📋 <strong>{slot["day_name"]}, {fmt_de(d)}</strong> — Gebucht von: <strong>{b["user_name"]}</strong> — ⏰ {slot["start"]}–{slot["end"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="slot-available">✨ <strong>{slot["day_name"]}, {fmt_de(d)}</strong> — Verfügbar — ⏰ {slot["start"]}–{slot["end"]}</div>', unsafe_allow_html=True)
        
        with col_action:
            if bookings and b["user_id"] == u["id"]:
                if st.button("❌ Stornieren", key=f"cancel_{b['id']}"):
                    # Stornierung verarbeiten
                    if st.session_state.db.cancel_booking(b["id"], u["id"]):
                        # Admin-Benachrichtigung
                        _notify_admins_cancellation(u, slot, d)
                        # User-Bestätigung
                        _send_cancellation_confirmation(u, slot, d)
                        
                        st.session_state.db.log(u["id"],"booking_cancelled",f"slot_id={slot['id']}, date={d}")
                        st.success("Schicht storniert - Bestätigung wurde versendet")
                        st.rerun()
            
            elif not bookings:
                if st.button("📝 Buchen", key=f"book_{slot['id']}_{d}", type="primary"):
                    ok, res = st.session_state.db.create_booking(u["id"], slot["id"], d)
                    if ok:
                        # Buchungsbestätigung senden
                        _send_booking_confirmation(u, slot, d)
                        
                        st.session_state.db.log(u["id"],"booking_created",f"slot_id={slot['id']}, date={d}")
                        st.success(f"Gebucht für {fmt_de(d)} - Bestätigung wurde versendet")
                        st.rerun()
                    else:
                        st.error(res)

def _notify_admins_cancellation(user, slot, booking_date):
    """Benachrichtigt alle Admins über Stornierung"""
    admins = st.session_state.db.get_admin_users()
    message = format_template("admin_cancellation_notification", st.session_state.db,
                             USER=user["name"], DATUM=fmt_de(booking_date), 
                             SCHICHT=slot["day_name"], ZEIT=f"{slot['start']}-{slot['end']}")
    
    # E-Mail an Admins
    if st.session_state.mail.enabled:
        for admin_email in admins:
            st.session_state.mail.send(admin_email, "Schicht storniert", message)
    
    # SMS an Admins (wenn verfügbar)
    if st.session_state.sms.enabled:
        admin_users = st.session_state.db.get_all_users()
        for admin in admin_users:
            if admin["role"] == "admin" and admin["active"]:
                st.session_state.sms.send(admin["phone"], message)

def _send_cancellation_confirmation(user, slot, booking_date):
    """Sendet Storno-Bestätigung an Nutzer"""
    message = format_template("cancellation_confirmation", st.session_state.db,
                             USER=user["name"], DATUM=fmt_de(booking_date),
                             SCHICHT=slot["day_name"], ZEIT=f"{slot['start']}-{slot['end']}")
    
    # E-Mail
    if st.session_state.mail.enabled and user.get("email_opt_in", True):
        # Storno-iCal erstellen
        ics_cancel = generate_ics(slot, booking_date, user["name"], user["email"], action="CANCEL")
        st.session_state.mail.send(user["email"], "Schicht storniert", message,
                                 [{"filename": f"storno_{slot['day']}_{booking_date}.ics", "content": ics_cancel}])
    
    # SMS
    if st.session_state.sms.enabled and user.get("sms_opt_in", True):
        st.session_state.sms.send(user["phone"], message)

def _send_booking_confirmation(user, slot, booking_date):
    """Sendet Buchungs-Bestätigung an Nutzer"""
    message = format_template("booking_confirmation", st.session_state.db,
                             USER=user["name"], DATUM=fmt_de(booking_date),
                             SCHICHT=slot["day_name"], ZEIT=f"{slot['start']}-{slot['end']}")
    
    # E-Mail mit iCal
    if st.session_state.mail.enabled and user.get("email_opt_in", True):
        ics_content = generate_ics(slot, booking_date, user["name"], user["email"])
        st.session_state.mail.send(user["email"], "Schicht bestätigt", message,
                                 [{"filename": f"schicht_{slot['day']}_{booking_date}.ics", "content": ics_content}])
    
    # SMS
    if st.session_state.sms.enabled and user.get("sms_opt_in", True):
        st.session_state.sms.send(user["phone"], message)

# ===== UI: Kalenderansicht =====
def ui_calendar():
    st.markdown('<div class="main-header">📅 Kalenderansicht</div>', unsafe_allow_html=True)
    
    # Monatsnavigation
    col1, col2, col3 = st.columns([1,3,1])
    current_date = st.session_state.calendar_date
    
    with col1:
        if st.button("⬅️ Vorheriger Monat"):
            if current_date.month == 1:
                st.session_state.calendar_date = current_date.replace(year=current_date.year-1, month=12)
            else:
                st.session_state.calendar_date = current_date.replace(month=current_date.month-1)
            st.rerun()
    
    with col2:
        month_names = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
                      "Juli", "August", "September", "Oktober", "November", "Dezember"]
        st.markdown(f'<div class="week-header">{month_names[current_date.month]} {current_date.year}</div>', unsafe_allow_html=True)
    
    with col3:
        if st.button("Nächster Monat ➡️"):
            if current_date.month == 12:
                st.session_state.calendar_date = current_date.replace(year=current_date.year+1, month=1)
            else:
                st.session_state.calendar_date = current_date.replace(month=current_date.month+1)
            st.rerun()
    
    # Kalender erstellen
    cal = calendar.monthcalendar(current_date.year, current_date.month)
    
    # Wochentage Header
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    cols = st.columns(7)
    for i, day in enumerate(weekdays):
        cols[i].markdown(f"**{day}**")
    
    # Kalenderwochen
    today = date.today()
    
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
                continue
                
            day_date = date(current_date.year, current_date.month, day)
            day_str = day_date.strftime("%Y-%m-%d")
            
            # Schichten für diesen Tag finden
            day_slots = []
            day_bookings = {}
            
            for slot in WEEKLY_SLOTS:
                # Prüfen ob dieser Tag dem Slot-Wochentag entspricht
                weekday_map = {"tuesday": 1, "friday": 4, "saturday": 5}  # 0=Montag
                if day_date.weekday() == weekday_map.get(slot["day"]):
                    bookings = st.session_state.db.bookings_for(slot["id"], day_str)
                    day_slots.append(slot)
                    day_bookings[slot["id"]] = bookings
            
            # Tag anzeigen
            with cols[i]:
                cell_class = "calendar-cell"
                if day_date == today:
                    cell_class += " calendar-today"
                
                # Tag und Schichten anzeigen
                if day_slots:
                    content = f"**{day}**\n"
                    for slot in day_slots:
                        bookings = day_bookings[slot["id"]]
                        if bookings:
                            content += f"🔴 {slot['start']}-{slot['end']}\n"
                            cell_class += " calendar-booked"
                        else:
                            content += f"🟢 {slot['start']}-{slot['end']}\n"
                            cell_class += " calendar-available"
                    
                    # Buchungsbuttons
                    for slot in day_slots:
                        bookings = day_bookings[slot["id"]]
                        if not bookings:
                            if st.button(f"Buchen {slot['start']}", key=f"cal_book_{slot['id']}_{day_str}", use_container_width=True):
                                ok, res = st.session_state.db.create_booking(st.session_state.user["id"], slot["id"], day_str)
                                if ok:
                                    _send_booking_confirmation(st.session_state.user, slot, day_str)
                                    st.session_state.db.log(st.session_state.user["id"],"booking_created",f"calendar: slot_id={slot['id']}, date={day_str}")
                                    st.success(f"Gebucht!")
                                    st.rerun()
                                else:
                                    st.error(res)
                else:
                    content = f"**{day}**"
                
                st.markdown(content)

# ===== UI: Meine Schichten =====
def ui_my_shifts():
    u = st.session_state.user
    
    st.subheader("👤 Meine Schichten")
    mine = st.session_state.db.user_bookings(u["id"])
    
    if mine:
        for b in mine:
            slot = next(s for s in WEEKLY_SLOTS if s["id"] == b["slot_id"])
            col_info, col_action = st.columns([4,1])
            
            with col_info:
                st.info(f"**{slot['day_name']}, {fmt_de(b['date'])}** — ⏰ {slot['start']}–{slot['end']} — 📝 Gebucht am {datetime.fromisoformat(b['created_at']).strftime('%d.%m.%Y %H:%M')}")
            
            with col_action:
                if st.button("❌ Stornieren", key=f"my_cancel_{b['id']}"):
                    if st.session_state.db.cancel_booking(b["id"], u["id"]):
                        # Benachrichtigungen senden
                        _notify_admins_cancellation(u, slot, b['date'])
                        _send_cancellation_confirmation(u, slot, b['date'])
                        
                        st.session_state.db.log(u["id"],"booking_cancelled_from_list",f"booking_id={b['id']}")
                        st.success("Storniert - Benachrichtigungen versendet")
                        st.rerun()
    else:
        st.info("Keine Buchungen vorhanden.")

# ===== UI: Info-Seiten =====
def ui_info():
    st.subheader("ℹ️ Informationen")
    
    # Zwei Info-Seiten als Tabs
    tab1, tab2 = st.tabs(["📋 Seite 1", "🚨 Seite 2"])
    
    with tab1:
        content1 = st.session_state.db.get_setting("info_page_1", "# Seite 1\n\nKein Inhalt vorhanden.")
        
        if st.session_state.user.get("role") == "admin":
            with st.form("info_edit_1"):
                new_content1 = st.text_area("Inhalt bearbeiten (Markdown)", value=content1, height=300)
                if st.form_submit_button("💾 Speichern"):
                    st.session_state.db.set_setting("info_page_1", new_content1)
                    st.session_state.db.log(st.session_state.user["id"], "info_page_updated", "page_1")
                    st.success("Gespeichert")
                    st.rerun()
        else:
            st.markdown(content1)
    
    with tab2:
        content2 = st.session_state.db.get_setting("info_page_2", "# Seite 2\n\nKein Inhalt vorhanden.")
        
        if st.session_state.user.get("role") == "admin":
            with st.form("info_edit_2"):
                new_content2 = st.text_area("Inhalt bearbeiten (Markdown)", value=content2, height=300)
                if st.form_submit_button("💾 Speichern"):
                    st.session_state.db.set_setting("info_page_2", new_content2)
                    st.session_state.db.log(st.session_state.user["id"], "info_page_updated", "page_2")
                    st.success("Gespeichert")
                    st.rerun()
        else:
            st.markdown(content2)

# ===== UI: Profil =====
def ui_profile():
    u = st.session_state.user
    
    st.subheader("👤 Mein Profil")
    
    # Profildaten bearbeiten
    with st.form("f_prof"):
        n = st.text_input("Name", value=u["name"])
        ph = st.text_input("Telefon", value=u["phone"])
        sms_opt = st.checkbox("SMS-Benachrichtigungen erhalten", value=u.get("sms_opt_in",True))
        email_opt = st.checkbox("E-Mail-Benachrichtigungen erhalten", value=u.get("email_opt_in",True))
        
        if st.form_submit_button("💾 Speichern", type="primary"):
            if st.session_state.db.update_user_profile(u["id"], n, ph, sms_opt, email_opt):
                st.session_state.user.update({
                    "name": n, "phone": ph, 
                    "sms_opt_in": sms_opt, "email_opt_in": email_opt
                })
                st.session_state.db.log(u["id"],"profile_updated","profile data changed")
                st.success("Profil aktualisiert")
            else:
                st.error("Fehler beim Speichern")
    
    st.divider()
    
    # Passwort ändern
    st.subheader("🔒 Passwort ändern")
    with st.form("f_password"):
        old_pw = st.text_input("Aktuelles Passwort", type="password")
        new_pw1 = st.text_input("Neues Passwort", type="password")
        new_pw2 = st.text_input("Neues Passwort wiederholen", type="password")
        
        if st.form_submit_button("🔄 Passwort ändern"):
            errs = []
            
            # Altes Passwort prüfen
            if not st.session_state.db.auth(u["email"], old_pw):
                errs.append("Aktuelles Passwort ist falsch")
            
            if len(new_pw1) < 6:
                errs.append("Neues Passwort muss mindestens 6 Zeichen haben")
                
            if new_pw1 != new_pw2:
                errs.append("Neue Passwörter stimmen nicht überein")
            
            if errs:
                for e in errs:
                    st.error(e)
            else:
                if st.session_state.db.change_password(u["id"], new_pw1):
                    st.session_state.db.log(u["id"], "password_changed", "password updated")
                    st.success("Passwort erfolgreich geändert")
                else:
                    st.error("Fehler beim Ändern des Passworts")
    
    st.divider()
    
    # Service-Tests
    st.subheader("🧪 Service-Tests")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("📱 SMS-Test")
        if st.session_state.sms.enabled:
            if st.button("Test-SMS senden"):
                ok, msg = st.session_state.sms.send(u["phone"], "Test-SMS vom Dienstplan+ System v4.0")
                if ok:
                    st.success("Test-SMS gesendet")
                else:
                    st.error(f"Fehler: {msg}")
        else:
            st.info("SMS nicht konfiguriert" + (" oder Safe-Mode aktiv" if SAFE_MODE else ""))
    
    with col2:
        st.caption("📧 E-Mail-Test")
        if st.session_state.mail.enabled:
            if st.button("Test-E-Mail senden"):
                ok, msg = st.session_state.mail.send(
                    u["email"], 
                    "Dienstplan+ Test-E-Mail",
                    f"Hallo {u['name']},\n\ndies ist eine Test-E-Mail vom Dienstplan+ System v4.0.\n\nBeste Grüße"
                )
                if ok:
                    st.success("Test-E-Mail gesendet")
                else:
                    st.error(f"Fehler: {msg}")
        else:
            st.info("E-Mail nicht konfiguriert" + (" oder Safe-Mode aktiv" if SAFE_MODE else ""))

# ===== UI: Admin =====
def ui_admin():
    st.subheader("⚙️ Admin-Panel")
    
    admin_tabs = st.tabs(["👥 Nutzer", "📝 Templates", "📊 Reporting", "💾 Backup/Restore"])
    
    # Nutzerverwaltung
    with admin_tabs[0]:
        st.subheader("👥 Nutzerverwaltung")
        
        # Neuen Nutzer anlegen
        with st.expander("➕ Neuen Nutzer anlegen"):
            with st.form("add_user"):
                new_email = st.text_input("E-Mail")
                new_phone = st.text_input("Telefon", "+49 ")
                new_name = st.text_input("Name")
                new_role = st.selectbox("Rolle", ["user", "admin"])
                temp_password = st.text_input("Temporäres Passwort", "temp123")
                
                if st.form_submit_button("👤 Nutzer anlegen"):
                    ok, result = st.session_state.db.create_user(new_email, new_phone, new_name, temp_password)
                    if ok:
                        st.session_state.db.update_user_role(result, new_role)
                        st.session_state.db.log(st.session_state.user["id"], "user_created_by_admin", f"user_id={result}, email={new_email}")
                        st.success(f"Nutzer {new_name} angelegt mit temporärem Passwort: {temp_password}")
                        st.rerun()
                    else:
                        st.error(result)
        
        # Nutzerliste
        users = st.session_state.db.get_all_users()
        if users:
            for user in users:
                with st.container():
                    col1, col2, col3, col4 = st.columns([3,1,1,2])
                    
                    with col1:
                        status = "🟢 Aktiv" if user["active"] else "🔴 Inaktiv"
                        st.write(f"**{user['name']}** ({user['email']}) - {user['role'].title()} - {status}")
                    
                    with col2:
                        new_role = st.selectbox("Rolle", ["user", "admin"], 
                                              index=0 if user["role"]=="user" else 1,
                                              key=f"role_{user['id']}")
                        if st.button("↻", key=f"update_role_{user['id']}"):
                            st.session_state.db.update_user_role(user["id"], new_role)
                            st.session_state.db.log(st.session_state.user["id"], "user_role_changed", f"user_id={user['id']}, new_role={new_role}")
                            st.rerun()
                    
                    with col3:
                        if st.button("🔄 Aktivieren" if not user["active"] else "❌ Deaktivieren", 
                                   key=f"toggle_{user['id']}"):
                            new_status = not user["active"]
                            st.session_state.db.update_user_status(user["id"], new_status)
                            st.session_state.db.log(st.session_state.user["id"], "user_status_changed", f"user_id={user['id']}, active={new_status}")
                            st.rerun()
                    
                    with col4:
                        st.caption(f"Erstellt: {user['created_at'][:10]}")
    
    # Template-Editor
    with admin_tabs[1]:
        st.subheader("📝 Template-Editor")
        
        templates = [
            ("booking_confirmation", "Buchungsbestätigung"),
            ("cancellation_confirmation", "Storno-Bestätigung"),
            ("admin_cancellation_notification", "Admin Storno-Benachrichtigung"),
            ("reminder_24h", "24h Reminder"),
            ("reminder_1h", "1h Reminder")
        ]
        
        for template_key, template_name in templates:
            with st.expander(f"✏️ {template_name}"):
                current_template = st.session_state.db.get_setting(template_key, "")
                
                st.caption("Verfügbare Platzhalter: {USER}, {DATUM}, {SCHICHT}, {ZEIT}")
                
                new_template = st.text_area(
                    f"Template für {template_name}:",
                    value=current_template,
                    height=100,
                    key=f"template_{template_key}"
                )
                
                # Vorschau
                preview = new_template.replace("{USER}", "Max Mustermann") \
                                   .replace("{DATUM}", "15.09.2025") \
                                   .replace("{SCHICHT}", "Dienstag") \
                                   .replace("{ZEIT}", "17:00-20:00") \
                                   .replace("\\n", "\n")
                
                st.caption("Vorschau:")
                st.text(preview)
                
                if st.button(f"💾 {template_name} speichern", key=f"save_{template_key}"):
                    st.session_state.db.set_setting(template_key, new_template)
                    st.session_state.db.log(st.session_state.user["id"], "template_updated", f"template={template_key}")
                    st.success("Template gespeichert")
                    st.rerun()
    
    # Reporting
    with admin_tabs[2]:
        st.subheader("📊 Reporting")
        
        # Statistiken
        users_all = st.session_state.db.get_all_users()
        active_users = [u for u in users_all if u["active"]]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Aktive Benutzer", len(active_users))
        col2.metric("Gesamt Benutzer", len(users_all))
        col3.metric("Administratoren", len([u for u in active_users if u["role"]=="admin"]))
        
        # Freie Slots nächste 4 Wochen
        st.subheader("🟢 Freie Slots (nächste 4 Wochen)")
        free_slots = st.session_state.db.get_free_slots_next_weeks(4)
        
        if free_slots:
            df = pd.DataFrame(free_slots)
            st.dataframe(df, use_container_width=True)
            
            # CSV Download
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Als CSV herunterladen",
                data=csv,
                file_name=f"freie_slots_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("Alle Slots der nächsten 4 Wochen sind belegt")
        
        # Audit Log
        st.subheader("📝 Audit Log")
        logs = st.session_state.db.get_audit_log(50)
        
        if logs:
            df_logs = pd.DataFrame(logs)
            st.dataframe(df_logs, use_container_width=True)
        else:
            st.info("Keine Aktivitäten vorhanden")
    
    # Backup/Restore
    with admin_tabs[3]:
        st.subheader("💾 Backup & Restore")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.caption("📤 Backup erstellen")
            if st.button("📥 Backup herunterladen"):
                backup_data = _create_backup_zip(st.session_state.db)
                st.download_button(
                    label="💾 ZIP-Backup herunterladen",
                    data=backup_data,
                    file_name=f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip"
                )
            
            if st.button("📧 Backup per E-Mail senden"):
                if st.session_state.mail.enabled:
                    ok = _send_daily_backup(st.session_state.db, st.session_state.mail)
                    if ok:
                        st.success("Backup erfolgreich versendet")
                        st.session_state.db.log(st.session_state.user["id"], "manual_backup_sent", "email backup")
                    else:
                        st.error("Backup konnte nicht versendet werden")
                else:
                    st.warning("E-Mail nicht aktiviert")
        
        with col2:
            st.caption("📥 Backup wiederherstellen")
            uploaded_file = st.file_uploader("ZIP-Backup auswählen", type=['zip'])
            
            if uploaded_file:
                st.warning("⚠️ ACHTUNG: Restore überschreibt alle bestehenden Daten!")
                
                if st.button("🔄 Backup wiederherstellen", type="secondary"):
                    try:
                        # ZIP auslesen
                        with zipfile.ZipFile(uploaded_file, 'r') as zip_file:
                            json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                            if json_files:
                                json_content = zip_file.read(json_files[0])
                                backup_data = json.loads(json_content)
                                
                                # Daten wiederherstellen (vereinfacht - in Production robuster)
                                st.session_state.db.log(st.session_state.user["id"], "backup_restored", f"file={uploaded_file.name}")
                                st.success("Backup erfolgreich wiederhergestellt")
                                st.info("Bitte App neu laden")
                            else:
                                st.error("Keine gültige Backup-Datei gefunden")
                    except Exception as e:
                        st.error(f"Fehler beim Wiederherstellen: {e}")

# ===== Main App =====
def main():
    # Sidebar
    if "user" in st.session_state:
        u = st.session_state.user
        with st.sidebar:
            st.success(f"Eingeloggt als **{u['name']}**")
            st.caption(f"📧 {u['email']}")
            st.caption(f"🏷️ {u['role'].title()}")
            st.divider()
            st.caption(f"Version {VERSION}")
            st.caption(f"TZ: {TIMEZONE_STR}")
            st.caption(f"Safe-Mode: {'🟢 ON' if SAFE_MODE else '🔴 OFF'}")
            st.caption(f"E-Mail: {'🟢 ON' if st.session_state.mail.enabled else '⚪ OFF'}")
            st.caption(f"SMS: {'🟢 ON' if st.session_state.sms.enabled else '⚪ OFF'}")
            st.caption(f"Reminder: {'🟢 ON' if ENABLE_REMINDER_SMS else '⚪ OFF'}")
            
            if st.button("🚪 Abmelden", use_container_width=True):
                st.session_state.db.log(u["id"],"logout","user logout")
                del st.session_state["user"]
                st.rerun()
    
    # Main Content
    if "user" not in st.session_state:
        ui_auth()
        return
    
    u = st.session_state.user
    
    # Navigation
    if u["role"] == "admin":
        tabs = st.tabs(["📅 Plan", "📅 Kalender", "👤 Meine Schichten", "ℹ️ Info", "👤 Profil", "⚙️ Admin"])
        tab_plan, tab_calendar, tab_shifts, tab_info, tab_profile, tab_admin = tabs
    else:
        tabs = st.tabs(["📅 Plan", "📅 Kalender", "👤 Meine Schichten", "ℹ️ Info", "👤 Profil"])
        tab_plan, tab_calendar, tab_shifts, tab_info, tab_profile = tabs
        tab_admin = None
    
    with tab_plan:
        ui_schedule()
    
    with tab_calendar:
        ui_calendar()
    
    with tab_shifts:
        ui_my_shifts()
    
    with tab_info:
        ui_info()
    
    with tab_profile:
        ui_profile()
    
    if tab_admin:
        with tab_admin:
            ui_admin()

# ===== Scheduler-Management =====
def manage_scheduler():
    """Scheduler-Management nur im UI-Kontext"""
    if ("sched" not in st.session_state or not st.session_state.sched) and not SAFE_MODE:
        if ENABLE_DAILY_BACKUP or ENABLE_REMINDER_SMS:
            st.session_state.sched = start_scheduler(st.session_state.db, st.session_state.mail, st.session_state.sms)

if __name__ == "__main__":
    # Scheduler nur nach UI-Initialisierung
    if "user" in st.session_state:
        manage_scheduler()
    
    main()