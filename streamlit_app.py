import streamlit as st
import sqlite3, hashlib, io, zipfile, smtplib, json
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from twilio.rest import Client

# ===== Konfiguration (seiteneffektfrei) =====
VERSION = "3.1"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = (st.secrets.get("TIMEZONE", "Europe/Berlin")
                if hasattr(st, "secrets") else "Europe/Berlin")
TZ = pytz.timezone(TIMEZONE_STR)
SAFE_MODE = bool(hasattr(st, "secrets") and str(st.secrets.get("SAFE_MODE", "true")).lower() == "true")
ENABLE_DAILY_BACKUP = bool(hasattr(st, "secrets") and str(st.secrets.get("ENABLE_DAILY_BACKUP", "false")).lower() == "true")

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

# ===== Datenbank-Layer =====
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
            c.commit()
        self._seed_admin()

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

    def get_setting(self, key, default="false"):
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
                return True
        except sqlite3.IntegrityError:
            return False

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

# ===== Backup + Scheduler (nur wenn erlaubt) =====
def _create_backup_zip(db: DB):
    data = {}
    with db.conn() as c:
        cur = c.cursor()
        for table in ["users","bookings","audit_log","app_settings"]:
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

def start_scheduler(db: DB, mailer: Mailer):
    if SAFE_MODE or not ENABLE_DAILY_BACKUP: return None
    try:
        sched = BackgroundScheduler(timezone=TZ)
        sched.add_job(lambda: _send_daily_backup(db, mailer), CronTrigger(hour=20, minute=0),
                      id="daily_backup", replace_existing=True, max_instances=1)
        sched.start()
        return sched
    except Exception:
        return None

# ===== Page Config und Singletons =====
st.set_page_config(page_title="Dienstplan+ Cloud", page_icon="📅", layout="wide")

if "db" not in st.session_state: st.session_state.db = DB()
if "sms" not in st.session_state: st.session_state.sms = TwilioSMS()
if "mail" not in st.session_state: st.session_state.mail = Mailer()
if "week_start" not in st.session_state: st.session_state.week_start = week_start()
if "sched" not in st.session_state: st.session_state.sched = None

# ===== UI: Auth =====
def ui_auth():
    st.title("🔐 Dienstplan+ Cloud")
    st.caption(f"Version {VERSION}")
    
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
                    ok = st.session_state.db.create_user(r_e, r_ph, n, r_p1)
                    if ok:
                        u = st.session_state.db.auth(r_e, r_p1)
                        st.session_state.user = u
                        st.session_state.db.log(u["id"],"user_created","registered")
                        st.success("Account erstellt und eingeloggt")
                        st.rerun()
                    else:
                        st.error("E-Mail bereits registriert")

# ===== UI: Setup & Checks =====
def ui_setup():
    st.title("🔧 Setup & Checks")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("System Status")
        st.write(f"**Version:** {VERSION}")
        st.write(f"**Zeitzone:** {TIMEZONE_STR}")
        st.write(f"**Safe-Mode:** {'🟢 Aktiv' if SAFE_MODE else '🔴 Inaktiv'}")
        
        # DB Check
        try:
            with st.session_state.db.conn() as c:
                c.execute("SELECT COUNT(*) FROM users")
                user_count = c.fetchone()[0]
            st.success(f"✅ Datenbank OK ({user_count} Benutzer)")
        except Exception as e:
            st.error(f"❌ Datenbankfehler: {e}")
    
    with col2:
        st.subheader("Dienste Status")
        
        # E-Mail Status
        if st.session_state.mail.enabled:
            st.success("✅ E-Mail aktiv")
        else:
            st.warning("⚠️ E-Mail inaktiv" + (" (Safe-Mode)" if SAFE_MODE else ""))
        
        # SMS Status  
        if st.session_state.sms.enabled:
            st.success("✅ SMS aktiv")
        else:
            st.warning("⚠️ SMS inaktiv" + (" (Safe-Mode)" if SAFE_MODE else ""))
        
        # Scheduler Status
        if st.session_state.sched:
            st.success("✅ Backup-Scheduler aktiv")
        else:
            st.warning("⚠️ Backup-Scheduler inaktiv")
            
            if not SAFE_MODE and ENABLE_DAILY_BACKUP and st.session_state.mail.enabled:
                if st.button("🚀 Scheduler starten"):
                    st.session_state.sched = start_scheduler(st.session_state.db, st.session_state.mail)
                    if st.session_state.sched:
                        st.success("Scheduler gestartet!")
                        st.rerun()
                    else:
                        st.error("Scheduler konnte nicht gestartet werden")
            else:
                st.caption("Für Scheduler: Safe-Mode aus, E-Mail aktiv, ENABLE_DAILY_BACKUP=true")

# ===== UI: Plan =====
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
        st.markdown(f"### KW {ws.isocalendar()[1]} — {ws.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}")
    
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
                    st.info(f"✅ **{slot['day_name']}, {fmt_de(d)}** — Gebucht von Ihnen — ⏰ {slot['start']}–{slot['end']}")
                else:
                    st.warning(f"📋 **{slot['day_name']}, {fmt_de(d)}** — Gebucht von: {b['user_name']} — ⏰ {slot['start']}–{slot['end']}")
            else:
                st.success(f"✨ **{slot['day_name']}, {fmt_de(d)}** — Verfügbar — ⏰ {slot['start']}–{slot['end']}")
        
        with col_action:
            if bookings and b["user_id"] == u["id"]:
                if st.button("❌ Stornieren", key=f"cancel_{b['id']}"):
                    if st.session_state.db.cancel_booking(b["id"], u["id"]):
                        st.session_state.db.log(u["id"],"booking_cancelled",f"slot_id={slot['id']}, date={d}")
                        
                        # Optional: Storno-E-Mail mit iCal senden
                        if st.session_state.mail.enabled and u.get("email_opt_in", True):
                            ics_cancel = generate_ics(slot, d, u["name"], u["email"], action="CANCEL")
                            st.session_state.mail.send(
                                u["email"],
                                f"Schicht storniert: {slot['day_name']} {fmt_de(d)}",
                                f"Ihre Schicht am {slot['day_name']}, {fmt_de(d)} von {slot['start']}-{slot['end']} wurde storniert.",
                                [{"filename": f"storno_{slot['day']}_{d}.ics", "content": ics_cancel}]
                            )
                        
                        st.success("Storniert")
                        st.rerun()
            
            elif not bookings:
                if st.button("📝 Buchen", key=f"book_{slot['id']}_{d}", type="primary"):
                    ok, res = st.session_state.db.create_booking(u["id"], slot["id"], d)
                    if ok:
                        st.session_state.db.log(u["id"],"booking_created",f"slot_id={slot['id']}, date={d}")
                        
                        # Optional: Buchungs-E-Mail mit iCal senden
                        if st.session_state.mail.enabled and u.get("email_opt_in", True):
                            ics_content = generate_ics(slot, d, u["name"], u["email"])
                            st.session_state.mail.send(
                                u["email"],
                                f"Schicht bestätigt: {slot['day_name']} {fmt_de(d)}",
                                f"Ihre Schicht am {slot['day_name']}, {fmt_de(d)} von {slot['start']}-{slot['end']} wurde gebucht.\n\nTermin wurde dem Kalender hinzugefügt.",
                                [{"filename": f"schicht_{slot['day']}_{d}.ics", "content": ics_content}]
                            )
                        
                        # Optional: SMS senden
                        if st.session_state.sms.enabled and u.get("sms_opt_in", True):
                            st.session_state.sms.send(
                                u["phone"], 
                                f"Schicht bestätigt: {slot['day_name']} {fmt_de(d)} {slot['start']}-{slot['end']}"
                            )
                        
                        st.success(f"Gebucht für {fmt_de(d)}")
                        st.rerun()
                    else:
                        st.error(res)

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
                        st.session_state.db.log(u["id"],"booking_cancelled_from_list",f"booking_id={b['id']}")
                        st.success("Storniert")
                        st.rerun()
    else:
        st.info("Keine Buchungen vorhanden.")

# ===== UI: Profil =====
def ui_profile():
    u = st.session_state.user
    
    st.subheader("👤 Mein Profil")
    
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
    
    st.subheader("🧪 Service-Tests")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("📱 SMS-Test")
        if st.session_state.sms.enabled:
            if st.button("Test-SMS senden"):
                ok, msg = st.session_state.sms.send(u["phone"], "Test-SMS vom Dienstplan+ System")
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
                    f"Hallo {u['name']},\n\ndies ist eine Test-E-Mail vom Dienstplan+ System.\n\nBeste Grüße"
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
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("💾 Backup")
        if SAFE_MODE:
            st.info("Safe-Mode aktiv — Backup-Funktionen eingeschränkt")
        
        if st.button("Backup jetzt senden"):
            if st.session_state.mail.enabled:
                ok = _send_daily_backup(st.session_state.db, st.session_state.mail)
                if ok:
                    st.success("Backup erfolgreich versendet")
                else:
                    st.error("Backup konnte nicht versendet werden")
            else:
                st.warning("E-Mail nicht aktiviert für Backup-Versand")
    
    with col2:
        st.caption("📊 Statistiken")
        try:
            with st.session_state.db.conn() as c:
                cur = c.cursor()
                cur.execute("SELECT COUNT(*) FROM users WHERE active=1")
                active_users = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'")
                total_bookings = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_date >= date('now')")
                future_bookings = cur.fetchone()[0]
                
            st.metric("Aktive Benutzer", active_users)
            st.metric("Buchungen gesamt", total_bookings)
            st.metric("Zukünftige Buchungen", future_bookings)
        except Exception as e:
            st.error(f"Statistiken konnten nicht geladen werden: {e}")

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
            st.caption(f"Safe-Mode: {'ON' if SAFE_MODE else 'OFF'}")
            
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
        tabs = st.tabs(["📅 Plan", "👤 Meine Schichten", "🔧 Setup", "👤 Profil", "⚙️ Admin"])
        tab_plan, tab_shifts, tab_setup, tab_profile, tab_admin = tabs
    else:
        tabs = st.tabs(["📅 Plan", "👤 Meine Schichten", "🔧 Setup", "👤 Profil"])
        tab_plan, tab_shifts, tab_setup, tab_profile = tabs
        tab_admin = None
    
    with tab_plan:
        ui_schedule()
    
    with tab_shifts:
        ui_my_shifts()
    
    with tab_setup:
        ui_setup()
    
    with tab_profile:
        ui_profile()
    
    if tab_admin:
        with tab_admin:
            ui_admin()

if __name__ == "__main__":
    main()