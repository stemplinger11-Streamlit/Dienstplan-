# streamlit_app.py — Dienstplan+ Cloud v3.0 (Twilio Enterprise Edition, Cloud-Fixes)
# Wichtige Punkte:
# - Alle "..." Fragmente entfernt (SQL, ICS, HTML)
# - ICS-Mail korrekt (MIMEBase payload)
# - SQL Queries vollständig und syntaktisch korrekt
# - UI-String-Blöcke nur in passenden Kontexten (keine losen f-Strings)
# - APScheduler optional: Fallback-Trigger bei Nutzeraufruf, wenn Scheduler nicht lief
# - Secrets ausschließlich via st.secrets (Cloud-UI), KEINE secrets.toml im Repo

import streamlit as st
import sqlite3, hashlib, json, io, zipfile, time, smtplib, os
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas as pd
from twilio.rest import Client  # Twilio SMS

# ===== Konfiguration =====
VERSION = "3.0"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = st.secrets.get("TIMEZONE", "Europe/Berlin") if hasattr(st, 'secrets') else "Europe/Berlin"
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
CLOSED_MONTHS = set([6,7,8,9])  # Juni–September

def is_holiday(date_str): 
    return date_str in HOLIDAYS

def holiday_name(date_str): 
    return HOLIDAYS.get(date_str, "Feiertag")

def is_closed_period(date_str):
    try:
        m = datetime.strptime(date_str, "%Y-%m-%d").month
        return m in CLOSED_MONTHS
    except: 
        return False

def fmt_de(date_str):
    try: 
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except: 
        return date_str

def week_start(d=None):
    d = d or datetime.now().date()
    if isinstance(d, datetime): 
        d = d.date()
    return d - timedelta(days=d.weekday())

def slot_date(week_start_date, slot_day):
    mapping = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
    return (week_start_date + timedelta(days=mapping.get(slot_day,0))).strftime("%Y-%m-%d")

# ===== DB-Layer =====
class DB:
    def __init__(self):
        self.init()

    def conn(self):
        return sqlite3.connect(DB_FILE, check_same_thread=False)

    def init(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                sms_opt_in BOOLEAN DEFAULT 1,
                email_opt_in BOOLEAN DEFAULT 1,
                is_initial_admin BOOLEAN DEFAULT 0,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slot_id, booking_date)
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS favorites(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, slot_id, date)
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS info_pages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS backup_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_date DATE NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                details TEXT
            )""")
            c.commit()
        self.ensure_admin()
        self.ensure_info_pages()
        self.ensure_email_templates()

    def ensure_admin(self):
        if not hasattr(st, 'secrets'):
            return
        email = st.secrets.get("ADMIN_EMAIL","")
        pw = st.secrets.get("ADMIN_PASSWORD","")
        if not (email and pw): 
            return
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM users WHERE email=? AND is_initial_admin=1", (email,))
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO users(email,phone,name,password_hash,role,sms_opt_in,is_initial_admin) VALUES(?,?,?,?,?,?,1)",
                            (email, "+4915199999999", "Initial Admin", hashlib.sha256(pw.encode()).hexdigest(), "admin", 1))
                c.commit()

    def ensure_info_pages(self):
        defaults = {
            "schicht_info": ("Schicht-Informationen",
                "# Schicht-Checkliste\n\n1. Kasse holen\n2. Hallenbad 30min vor Öffnung aufsperren\n3. Technik prüfen\n4. Sicherheit prüfen\n\nWährend der Schicht:\n- Aufsichtspflicht\n- Gäste betreuen\n- Ordnung\n- Kasse führen\n\nNach Schicht:\n1. Kontrolle\n2. Kasse abrechnen\n3. Abschließen\n4. Kasse zurückbringen\n"),
            "rettungskette": ("Rettungskette Hallenbad",
                "# Offizieller Ablaufplan – Rettungskette\n\n1. Notruf 112 (WO, WAS, WIE VIELE, WER)\n2. Ansprechen, Bewusstsein prüfen\n3. Atmung 10s prüfen\n4. Keine Atmung: 30:2 Reanimation (100–120/min)\n5. AED holen und anwenden\n6. Bei Atmung: Stabile Seitenlage\n7. Bis Rettungsdienst weitermachen\n")
        }
        with self.conn() as c:
            cur = c.cursor()
            for key,(title,content) in defaults.items():
                cur.execute("SELECT COUNT(*) FROM info_pages WHERE page_key=?", (key,))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO info_pages(page_key,title,content) VALUES(?,?,?)",(key,title,content))
            c.commit()

    def ensure_email_templates(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS email_templates(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,template_type TEXT,subject_template TEXT,body_template TEXT,active BOOLEAN DEFAULT 1)")
            cur.execute("SELECT COUNT(*) FROM email_templates")
            if cur.fetchone()[0] == 0:
                rows = [
                    ('Einladung','booking_invite','[Dienstplan+] Einladung: {{slot}} - {{datum}}',
                     'Hallo {{name}},\n\nhier ist deine Kalender-Einladung für die Schicht am {{datum}} von {{slot}}.\n\nViele Grüße\nDienstplan+'),
                    ('Absage','booking_cancel','[Dienstplan+] Absage: {{slot}} - {{datum}}',
                     'Hallo {{name}},\n\ndie Schicht am {{datum}} von {{slot}} wurde storniert.\n\nViele Grüße\nDienstplan+'),
                    ('Umbuchung','booking_reschedule','[Dienstplan+] Umbuchung: {{slot}} - {{datum}}',
                     'Hallo {{name}},\n\ndeine Schicht wurde umgebucht auf {{datum}} von {{slot}}.\n\nViele Grüße\nDienstplan+')
                ]
                for r in rows:
                    cur.execute("INSERT INTO email_templates(name,template_type,subject_template,body_template) VALUES(?,?,?,?)", r)
            c.commit()

    # Users
    def auth(self, email, password):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,email,phone,name,role,sms_opt_in,email_opt_in,is_initial_admin,active
                           FROM users WHERE email=? AND password_hash=?""",
                        (email, hashlib.sha256(password.encode()).hexdigest()))
            r = cur.fetchone()
        if not r or r[8] != 1: 
            return None
        return dict(id=r[0],email=r[1],phone=r[2],name=r[3],role=r[4],sms_opt_in=bool(r[5]),email_opt_in=bool(r[6]),is_initial_admin=bool(r[7]))

    def create_user(self, email, phone, name, pw):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO users(email,phone,name,password_hash) VALUES(?,?,?,?)",
                            (email,phone,name,hashlib.sha256(pw.encode()).hexdigest()))
                c.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def update_user_profile(self, uid, name, phone, sms_opt_in):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET name=?, phone=?, sms_opt_in=? WHERE id=?", (name,phone,1 if sms_opt_in else 0,uid))
            c.commit()
            return cur.rowcount>0

    def update_password(self, uid, new_pw):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE users SET password_hash=? WHERE id=?", (hashlib.sha256(new_pw.encode()).hexdigest(), uid))
            c.commit()
            return cur.rowcount>0

    def all_users(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT id,name,email,phone,role,created_at FROM users WHERE active=1 ORDER BY name")
            return [dict(id=r[0],name=r[1],email=r[2],phone=r[3],role=r[4],created_at=r[5]) for r in cur.fetchall()]

    # Bookings
    def create_booking(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND booking_date=? AND status='confirmed'", (slot_id,d))
            if cur.fetchone()[0]>0:
                return False,"Slot bereits belegt"
            cur.execute("INSERT INTO bookings(user_id,slot_id,booking_date) VALUES(?,?,?)",(uid,slot_id,d))
            c.commit()
            return True,cur.lastrowid

    def cancel_booking(self, bid, uid=None):
        with self.conn() as c:
            cur = c.cursor()
            if uid:
                cur.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (bid,uid))
            else:
                cur.execute("DELETE FROM bookings WHERE id=?", (bid,))
            c.commit()
            return cur.rowcount>0

    def bookings_for(self, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT b.id,b.user_id,u.name,u.email,u.phone,b.created_at
                           FROM bookings b JOIN users u ON u.id=b.user_id
                           WHERE b.slot_id=? AND b.booking_date=? AND b.status='confirmed'""", (slot_id,d))
            return [dict(id=r[0],user_id=r[1],user_name=r[2],user_email=r[3],user_phone=r[4],created_at=r[5]) for r in cur.fetchall()]

    def user_bookings(self, uid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,slot_id,booking_date,created_at FROM bookings
                           WHERE user_id=? AND status='confirmed' ORDER BY booking_date ASC""",(uid,))
            return [dict(id=r[0],slot_id=r[1],date=r[2],created_at=r[3]) for r in cur.fetchall()]

    def user_favorites(self, uid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT slot_id,date,created_at FROM favorites
                           WHERE user_id=? ORDER BY date ASC""",(uid,))
            return [dict(slot_id=r[0],date=r[1],created_at=r[2]) for r in cur.fetchall()]

    def get_booking(self, bid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT b.id,b.user_id,b.slot_id,b.booking_date,u.name,u.email
                           FROM bookings b JOIN users u ON u.id=b.user_id WHERE b.id=?""",(bid,))
            r = cur.fetchone()
            if not r: return None
            return dict(id=r[0],user_id=r[1],slot_id=r[2],date=r[3],user_name=r[4],user_email=r[5])

    def transfer_booking(self, bid, new_uid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE bookings SET user_id=? WHERE id=?", (new_uid,bid))
            c.commit()
            return cur.rowcount>0

    # Favorites
    def is_favorite(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id=? AND slot_id=? AND date=?", (uid,slot_id,d))
            return cur.fetchone()[0]>0

    def add_favorite(self, uid, slot_id, d):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO favorites(user_id,slot_id,date) VALUES(?,?,?)",(uid,slot_id,d))
                c.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_favorite(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM favorites WHERE user_id=? AND slot_id=? AND date=?", (uid,slot_id,d))
            c.commit()
            return cur.rowcount>0

    def log(self, uid, action, details):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO audit_log(user_id,action,details) VALUES(?,?,?)",(uid,action,details))
                c.commit()
        except Exception:
            pass

# ===== Services =====
class TwilioSMS:
    def __init__(self):
        try:
            if hasattr(st, 'secrets'):
                self.sid = st.secrets.get("TWILIO_ACCOUNT_SID","")
                self.token = st.secrets.get("TWILIO_AUTH_TOKEN","")
                self.from_number = st.secrets.get("TWILIO_PHONE_NUMBER","")
                self.client = Client(self.sid,self.token) if (self.sid and self.token) else None
                self.enabled = bool(self.client and self.from_number and st.secrets.get("ENABLE_SMS", True))
            else:
                self.client = None
                self.enabled = False
        except Exception:
            self.client = None
            self.enabled = False
    
    def send(self,to,text):
        if not self.enabled: 
            return False,"SMS disabled"
        try:
            msg = self.client.messages.create(body=text, from_=self.from_number, to=to)
            return True,msg.sid
        except Exception as e:
            return False,str(e)

class Mailer:
    def __init__(self):
        if hasattr(st, 'secrets'):
            self.user = st.secrets.get("GMAIL_USER","")
            self.pw = st.secrets.get("GMAIL_APP_PASSWORD","")
            self.from_name = st.secrets.get("FROM_NAME","Dienstplan+ Cloud")
            self.enabled = bool(self.user and self.pw and st.secrets.get("ENABLE_EMAIL", True))
        else:
            self.user = ""
            self.pw = ""
            self.from_name = "Dienstplan+ Cloud"
            self.enabled = False

    def send(self,to,subject,body,attachments=None):
        if not self.enabled: 
            return False,"mail disabled"
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.user}>"
            msg["To"] = to
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
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

    def send_calendar(self,to,subject,body,ics,method="REQUEST"):
        if not self.enabled: 
            return False,"mail disabled"
        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = f"{self.from_name} <{self.user}>"
            msg["To"] = to
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body,"plain","utf-8"))
            ics_part = MIMEBase("text","calendar")
            ics_part.add_header("Content-Disposition",'attachment; filename="invite.ics"')
            ics_part.add_header("method", method)
            ics_part.set_payload(ics.encode("utf-8"))
            encoders.encode_base64(ics_part)
            msg.attach(ics_part)
            cal_part = MIMEText(ics,"calendar","utf-8")
            cal_part.add_header("Content-Disposition", "inline")
            cal_part.add_header("method", method)
            msg.attach(cal_part)
            with smtplib.SMTP("smtp.gmail.com",587) as s:
                s.starttls()
                s.login(self.user,self.pw)
                s.send_message(msg)
            return True,"OK"
        except Exception as e:
            return False,str(e)

def generate_ics(booking, slot, user, method="REQUEST", sequence=0):
    dt = datetime.strptime(booking["date"], "%Y-%m-%d")
    stime = datetime.strptime(slot["start_time"], "%H:%M").time()
    etime = datetime.strptime(slot["end_time"], "%H:%M").time()
    start_dt = datetime.combine(dt, stime)
    end_dt = datetime.combine(dt, etime)
    # Vereinfachte TZ-Umrechnung: Europe/Berlin zu UTC
    is_dst = dt.month>=3 and dt.month<=10
    offset = timedelta(hours=2 if is_dst else 1)
    start_utc = start_dt - offset
    end_utc = end_dt - offset
    uid = f"booking-{booking['id']}-{booking['date']}@dienstplan-cloud"
    ics = f"""BEGIN:VCALENDAR
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
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']}
LOCATION:Hallenbad
STATUS:CONFIRMED
SEQUENCE:{sequence}
CREATED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
LAST-MODIFIED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
END:VEVENT
END:VCALENDAR""".strip()
    return ics

# ===== App Setup =====
st.set_page_config(page_title="Dienstplan+ Cloud", page_icon="📅", layout="wide")

if "db" not in st.session_state: 
    st.session_state.db = DB()
if "sms" not in st.session_state: 
    st.session_state.sms = TwilioSMS()
if "mail" not in st.session_state: 
    st.session_state.mail = Mailer()
if "week_start" not in st.session_state: 
    st.session_state.week_start = week_start()

# Optionaler Scheduler + Fallback bei App-Aufruf
def _send_daily_backup():
    data = _create_backup_zip()
    to = st.secrets.get("BACKUP_EMAIL","wasserwachthauzenberg@gmail.com") if hasattr(st, 'secrets') else "wasserwachthauzenberg@gmail.com"
    ok,_ = st.session_state.mail.send(to, f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}",
                                      "Automatisches Backup im Anhang.",
                                      [{"filename": f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip", "content": data}])
    with st.session_state.db.conn() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO backup_log(backup_date,status,details) VALUES(?,?,?)",
                    (datetime.now().strftime("%Y-%m-%d"), "success" if ok else "failed", "auto/daily or fallback"))
        c.commit()
    return ok

def _create_backup_zip():
    backup_json = create_backup_json()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", backup_json)
        z.writestr("README.txt", f"Dienstplan+ Cloud v{VERSION} – Backup {datetime.now().isoformat()} TZ {TIMEZONE_STR}")
    buf.seek(0)
    return buf.getvalue()

def create_backup_json():
    with st.session_state.db.conn() as c:
        cur = c.cursor()
        data = {}
        for table in ["users","bookings","favorites","audit_log","info_pages","backup_log","email_templates"]:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                data[table] = {"columns": cols, "rows": rows}
            except sqlite3.OperationalError:
                # Table doesn't exist, skip
                pass
    return json.dumps({"created_at": datetime.now().isoformat(),"version":VERSION,"tables":data}, indent=2, default=str)

# Scheduler starten wenn möglich
if "sched" not in st.session_state:
    try:
        st.session_state.sched = BackgroundScheduler(timezone=TZ)
        if hasattr(st, 'secrets') and st.secrets.get("ENABLE_DAILY_BACKUP", True):
            st.session_state.sched.add_job(_send_daily_backup, CronTrigger(hour=20, minute=0), id="daily_backup", replace_existing=True, max_instances=1)
        st.session_state.sched.start()
    except Exception:
        pass

# Fallback-Backup-Trigger: Wenn Scheduler evtl. schlafend war, prüfe bei Aufruf
def backup_fallback_check():
    if not hasattr(st, 'secrets') or not st.secrets.get("ENABLE_DAILY_BACKUP", True): 
        return
    today = datetime.now().strftime("%Y-%m-%d")
    with st.session_state.db.conn() as c:
        cur = c.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM backup_log WHERE backup_date=? AND status='success'", (today,))
            if cur.fetchone()[0] == 0:
                _send_daily_backup()
        except sqlite3.OperationalError:
            # backup_log table doesn't exist yet
            pass

# ===== UI =====
def ui_auth():
    st.markdown("# 🔐 Willkommen bei Dienstplan+ Cloud")
    t1,t2 = st.tabs(["🔑 Anmelden","📝 Registrieren"])
    with t1:
        with st.form("f_login"):
            e = st.text_input("📧 E-Mail")
            p = st.text_input("🔒 Passwort", type="password")
            if st.form_submit_button("Anmelden", type="primary"):
                u = st.session_state.db.auth(e,p)
                if u:
                    st.session_state.user = u
                    st.session_state.db.log(u["id"],"login","user login")
                    backup_fallback_check()
                    st.success(f"Willkommen {u['name']}")
                    st.rerun()
                else:
                    st.error("Ungültige Anmeldedaten")
    with t2:
        with st.form("f_reg"):
            n = st.text_input("👤 Name")
            r_e = st.text_input("📧 E-Mail")
            r_ph = st.text_input("📱 Telefon","+49 ")
            r_p1 = st.text_input("🔒 Passwort", type="password")
            r_p2 = st.text_input("🔒 Passwort wiederholen", type="password")
            if st.form_submit_button("Account erstellen", type="primary"):
                errs=[]
                if not all([n,r_e,r_ph,r_p1,r_p2]): 
                    errs.append("Alle Felder ausfüllen")
                if r_p1!=r_p2: 
                    errs.append("Passwörter stimmen nicht überein")
                if len(r_p1)<6: 
                    errs.append("Passwort min. 6 Zeichen")
                if not r_ph.startswith("+"): 
                    errs.append("Telefon mit Ländercode (z.B. +49)")
                if "@" not in r_e: 
                    errs.append("E-Mail prüfen")
                if errs:
                    for e in errs: 
                        st.error(e)
                    return
                uid = st.session_state.db.create_user(r_e,r_ph,n,r_p1)
                if uid:
                    u = st.session_state.db.auth(r_e,r_p1)
                    st.session_state.user = u
                    st.session_state.db.log(uid,"user_created","registered")
                    st.success("Account erstellt und eingeloggt")
                    st.rerun()
                else:
                    st.error("E-Mail bereits registriert")

def ui_info():
    st.markdown("# ℹ️ Informationen")
    tab1,tab2 = st.tabs(["📋 Schicht-Info","🚨 Rettungskette"])
    with tab1:
        title, content = "",""
        rec = None
        with st.session_state.db.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT title,content FROM info_pages WHERE page_key='schicht_info'")
            rec = cur.fetchone()
        if rec:
            title,content = rec[0],rec[1]
        if st.session_state.user["role"]=="admin":
            with st.form("f_edit"):
                nt = st.text_input("Titel", value=title)
                nc = st.text_area("Inhalt (Markdown)", value=content, height=280)
                if st.form_submit_button("💾 Speichern", type="primary"):
                    with st.session_state.db.conn() as c:
                        cur = c.cursor()
                        cur.execute("""INSERT INTO info_pages(page_key,title,content,last_updated,updated_by)
                                       VALUES('schicht_info',?,?,?,?)
                                       ON CONFLICT(page_key) DO UPDATE SET
                                       title=excluded.title, content=excluded.content,
                                       last_updated=excluded.last_updated, updated_by=excluded.updated_by
                                    """, (nt, nc, datetime.now().isoformat(), st.session_state.user["id"]))
                        c.commit()
                    st.success("Gespeichert")
                    st.rerun()
        else:
            st.markdown(f"### {title or 'Schicht-Informationen'}")
            st.markdown(content or "Noch keine Inhalte.")

    with tab2:
        title, content = "",""
        with st.session_state.db.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT title,content FROM info_pages WHERE page_key='rettungskette'")
            rec = cur.fetchone()
            if rec: 
                title,content = rec[0],rec[1]
        st.markdown(f"### {title or 'Rettungskette Hallenbad'}")
        st.markdown(content or "Noch keine Inhalte.")

def ui_schedule():
    u = st.session_state.user
    ws = st.session_state.week_start
    week_end = ws + timedelta(days=6)
    colA,colB,colC = st.columns([1,4,1])
    with colA:
        if st.button("⬅️ Vorherige Woche"):
            st.session_state.week_start = ws - timedelta(days=7)
            st.rerun()
    with colB:
        st.markdown(f"### KW {ws.isocalendar()[1]} — {ws.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}")
    with colC:
        if st.button("Nächste Woche ➡️"):
            st.session_state.week_start = ws + timedelta(days=7)
            st.rerun()

    for slot in WEEKLY_SLOTS:
        d = slot_date(ws, slot["day"])
        if is_holiday(d):
            st.warning(f"🎄 {slot['day_name']}, {fmt_de(d)} — Feiertag: {holiday_name(d)} — keine Schichten")
            continue
        if is_closed_period(d):
            st.warning(f"🏊 {slot['day_name']}, {fmt_de(d)} — Hallenbad geschlossen (Sommerpause)")
            continue
        
        bookings = st.session_state.db.bookings_for(slot["id"], d)
        c1,c2 = st.columns([3,1])
        with c1:
            if bookings:
                b = bookings[0]
                if b["user_id"] == u["id"]:
                    created_str = datetime.fromisoformat(b['created_at']).strftime('%d.%m.%Y %H:%M')
                    st.info(f"✅ {slot['day_name']}, {fmt_de(d)} — Gebucht von Ihnen — ⏰ {slot['start_time']}–{slot['end_time']} — 📝 {created_str}")
                else:
                    st.warning(f"📋 {slot['day_name']}, {fmt_de(d)} — Gebucht von: {b['user_name']} — ⏰ {slot['start_time']}–{slot['end_time']}")
            else:
                st.success(f"✨ {slot['day_name']}, {fmt_de(d)} — Verfügbar — ⏰ {slot['start_time']}–{slot['end_time']}")
                
        with c2:
            is_fav = st.session_state.db.is_favorite(u["id"], slot["id"], d)
            if st.button("⭐ Beobachten" if not is_fav else "★ Beobachtet", key=f"fav_{slot['id']}_{d}"):
                if is_fav: 
                    st.session_state.db.remove_favorite(u["id"],slot["id"],d)
                else: 
                    st.session_state.db.add_favorite(u["id"],slot["id"],d)
                st.rerun()
            
            if bookings:
                b = bookings[0]
                if b["user_id"] == u["id"]:
                    if st.button("❌ Stornieren", key=f"cancel_{b['id']}"):
                        st.session_state.db.cancel_booking(b["id"], u["id"])
                        st.success("Storniert")
                        st.rerun()
                elif u["role"]=="admin":
                    st.caption("Admin: Umbuchen auf Nutzer")
                    users = [x for x in st.session_state.db.all_users() if x["id"] != b["user_id"]]
                    if users:
                        sel = st.selectbox("Zielnutzer", [f"{x['name']} ({x['email']})" for x in users], key=f"sel_{slot['id']}_{d}")
                        if st.button("🔁 Umbuchen", key=f"re_{b['id']}"):
                            new_uid = next(x["id"] for x in users if f"{x['name']} ({x['email']})" == sel)
                            # Absage-Mail an alten
                            st.session_state.mail.send(b["user_email"],
                                f"[Dienstplan+] Absage: {slot['day_name']} - {fmt_de(d)}",
                                f"Hallo {b['user_name']},\n\ndie Schicht am {fmt_de(d)} {slot['start_time']}-{slot['end_time']} wurde storniert/umgebucht.\n")
                            ok = st.session_state.db.transfer_booking(b["id"], new_uid)
                            if ok:
                                new_user = next(x for x in users if x["id"] == new_uid)
                                st.session_state.mail.send(new_user["email"],
                                    f"[Dienstplan+] Einladung: {slot['day_name']} - {fmt_de(d)}",
                                    f"Hallo {new_user['name']},\n\nIhnen wurde die Schicht am {fmt_de(d)} {slot['start_time']}-{slot['end_time']} zugewiesen.\n")
                                st.success("Umbuchung erfolgreich")
                                st.rerun()
                            else:
                                st.error("Umbuchung fehlgeschlagen")
            else:
                if st.button("📝 Buchen", key=f"book_{slot['id']}_{d}", type="primary"):
                    ok,res = st.session_state.db.create_booking(u["id"], slot["id"], d)
                    if ok:
                        if is_fav: 
                            st.session_state.db.remove_favorite(u["id"],slot["id"],d)
                        st.success(f"Gebucht für {fmt_de(d)}")
                        st.rerun()
                    else:
                        st.error(res)

def ui_my_shifts():
    u = st.session_state.user
    st.markdown("### 👤 Meine Schichten")
    mine = st.session_state.db.user_bookings(u["id"])
    if mine:
        for b in mine[:20]:
            slot = next(s for s in WEEKLY_SLOTS if s["id"] == b["slot_id"])
            created_str = datetime.fromisoformat(b['created_at']).strftime('%d.%m.%Y %H:%M')
            st.info(f"{slot['day_name']}, {fmt_de(b['date'])} — ⏰ {slot['start_time']}–{slot['end_time']} — 📝 {created_str}")
            if st.button("❌ Stornieren", key=f"my_cancel_{b['id']}"):
                st.session_state.db.cancel_booking(b["id"], u["id"])
                st.success("Storniert")
                st.rerun()
    else:
        st.info("Keine Buchungen vorhanden.")

    st.markdown("---")
    st.markdown("### ⭐ Watchlist / Favoriten")
    favs = st.session_state.db.user_favorites(u["id"])
    if favs:
        for f in favs:
            slot = next(s for s in WEEKLY_SLOTS if s["id"] == f["slot_id"])
            bookings = st.session_state.db.bookings_for(slot["id"], f["date"])
            if bookings:
                status = f"Belegt von {bookings[0]['user_name']}"
            else:
                status = "Verfügbar"
            st.success(f"⭐ {slot['day_name']}, {fmt_de(f['date'])} — {status} — ⏰ {slot['start_time']}–{slot['end_time']}")
            c1,c2 = st.columns(2)
            with c1:
                if st.button("🗑️ Entfernen", key=f"rm_{f['slot_id']}_{f['date']}"):
                    st.session_state.db.remove_favorite(u["id"], f["slot_id"], f["date"])
                    st.rerun()
            with c2:
                if not bookings and st.button("📝 Buchen", key=f"bookfav_{f['slot_id']}_{f['date']}", type="primary"):
                    ok,res = st.session_state.db.create_booking(u["id"], f["slot_id"], f["date"])
                    if ok:
                        st.session_state.db.remove_favorite(u["id"], f["slot_id"], f["date"])
                        st.success("Gebucht")
                        st.rerun()
                    else:
                        st.error(res)
    else:
        st.info("Noch keine Favoriten. Im Plan mit ⭐ hinzufügen.")

def ui_profile():
    u = st.session_state.user
    st.markdown("# 👤 Mein Profil")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("### 📝 Profil-Daten")
        with st.form("f_prof"):
            n = st.text_input("Name", value=u["name"])
            ph = st.text_input("Telefon", value=u["phone"])
            sms = st.checkbox("SMS-Erinnerungen erhalten", value=u.get("sms_opt_in",True))
            if st.form_submit_button("💾 Speichern", type="primary"):
                if st.session_state.db.update_user_profile(u["id"], n, ph, sms):
                    st.session_state.user["name"]=n
                    st.session_state.user["phone"]=ph
                    st.session_state.user["sms_opt_in"]=sms
                    st.success("Profil aktualisiert")
                else:
                    st.error("Fehler beim Speichern")
    with c2:
        st.markdown("### 🔒 Passwort ändern")
        with st.form("f_pwd"):
            p1 = st.text_input("Neues Passwort", type="password")
            p2 = st.text_input("Passwort bestätigen", type="password")
            if st.form_submit_button("🔑 Ändern", type="primary"):
                if p1 and p1==p2 and len(p1)>=6:
                    if st.session_state.db.update_password(u["id"], p1): 
                        st.success("Passwort geändert")
                    else: 
                        st.error("Fehler")
                else:
                    st.error("Eingaben prüfen")

    st.markdown("---")
    st.markdown("### 🧪 Service-Tests")
    colA, colB = st.columns(2)
    with colA:
        st.markdown("#### 📱 SMS-Test")
        if st.session_state.sms.enabled:
            if st.button("Test-SMS an meine Nummer senden"):
                ok, msg = st.session_state.sms.send(u["phone"], "Test-SMS vom Dienstplan+ System")
                if ok: 
                    st.success("Gesendet")
                else:
                    st.error(f"Fehler: {msg}")
        else:
            st.error("SMS nicht konfiguriert")
    with colB:
        st.markdown("#### 📧 E-Mail-Test")
        if st.session_state.mail.enabled:
            if st.button("Test-E-Mail an meine Adresse senden"):
                ok, msg = st.session_state.mail.send(u["email"], "Dienstplan+ Test-E-Mail",
                    f"Hallo {u['name']},\n\ndies ist eine Test-E-Mail vom Dienstplan+ System.")
                if ok: 
                    st.success("Gesendet")
                else:
                    st.error(f"Fehler: {msg}")
        else:
            st.error("E-Mail nicht konfiguriert")

def ui_admin():
    st.markdown("# ⚙️ Admin-Panel")
    
    with st.expander("👥 Team-Mitglieder", expanded=False):
        users = st.session_state.db.all_users()
        for x in users:
            st.markdown(f"- {x['name']} — {x['email']} — {x['phone']} — Rolle: {x['role']}")

    with st.expander("📊 Aktuelle Woche (Übersicht)", expanded=False):
        ws = st.session_state.week_start
        for slot in WEEKLY_SLOTS:
            d = slot_date(ws, slot["day"])
            bookings = st.session_state.db.bookings_for(slot["id"], d)
            if bookings:
                b = bookings[0]
                st.write(f"{slot['day_name']} {fmt_de(d)}: {b['user_name']} ({b['user_email']})")
            else:
                if is_holiday(d): 
                    st.info(f"{slot['day_name']} {fmt_de(d)}: Feiertag")
                elif is_closed_period(d): 
                    st.warning(f"{slot['day_name']} {fmt_de(d)}: Geschlossen")
                else: 
                    st.error(f"{slot['day_name']} {fmt_de(d)}: Unbesetzt")

    st.markdown("---")
    st.markdown("### 💾 Backup")
    if st.button("Backup jetzt senden"):
        if _send_daily_backup(): 
            st.success("Backup versendet")
        else: 
            st.error("Backup fehlgeschlagen")

# ===== Main Router =====
def main():
    if "user" not in st.session_state:
        ui_auth()
        return

    # Top-Bar
    u = st.session_state.user
    col1, col2, col3, col4 = st.columns([2,3,2,2])
    with col1: 
        st.markdown(f"👋 **{u['name']}**  \n📧 {u['email']}")
    with col2: 
        st.markdown("# 📅 Dienstplan+ Cloud")
    with col3:
        if st.button("ℹ️ Informationen"): 
            st.session_state.view="info"
            st.rerun()
        if st.button("👤 Profil"): 
            st.session_state.view="profile"
            st.rerun()
    with col4:
        if st.button("🚪 Abmelden"):
            st.session_state.db.log(u["id"],"logout","user logout")
            for k in ["user"]: 
                st.session_state.pop(k, None)
            st.rerun()
    st.markdown("---")

    view = st.session_state.get("view","plan")
    if view=="info":
        ui_info()
        if st.button("⬅️ Zurück"): 
            st.session_state.view="plan"
            st.rerun()
        return
    elif view=="profile":
        ui_profile()
        if st.button("⬅️ Zurück"): 
            st.session_state.view="plan"
            st.rerun()
        return

    if u["role"]=="admin":
        tabs = st.tabs(["📅 Plan","👤 Meine Schichten","⚙️ Admin"])
        with tabs[0]: 
            ui_schedule()
        with tabs[1]: 
            ui_my_shifts()
        with tabs[2]: 
            ui_admin()
    else:
        tabs = st.tabs(["📅 Plan","👤 Meine Schichten"])
        with tabs[0]: 
            ui_schedule()
        with tabs[1]: 
            ui_my_shifts()

if __name__ == "__main__":
    main()