# Dienstplan+ Cloud — Streamlit Cloud Ready (Safe-Mode, Python 3.13)
# Features: Login/Registrierung, Wochenplan, Buchen/Storno, Watchlist/Favoriten,
# Info-Seiten (editierbar), Profil (SMS/E-Mail Tests), Admin (Backup senden),
# Scheduler optional (20:00) — nur wenn ENABLE_DAILY_BACKUP=true und nicht SAFE_MODE.

import streamlit as st
import sqlite3, hashlib, json, io, zipfile, smtplib
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

# ===== Konfiguration (deploy-sicher) =====
VERSION = "3.0"
DB_FILE = "dienstplan.db"
TIMEZONE_STR = (st.secrets.get("TIMEZONE", "Europe/Berlin")
                if hasattr(st, "secrets") else "Europe/Berlin")
TZ = pytz.timezone(TIMEZONE_STR)

SAFE_MODE = bool(hasattr(st, "secrets") and str(st.secrets.get("SAFE_MODE", "false")).lower() == "true")
ENABLE_DAILY_BACKUP = bool(hasattr(st, "secrets") and str(st.secrets.get("ENABLE_DAILY_BACKUP", "false")).lower() == "true")

WEEKLY_SLOTS = [
    {"id": 1, "day": "tuesday",  "day_name": "Dienstag", "start_time": "17:00", "end_time": "20:00"},
    {"id": 2, "day": "friday",   "day_name": "Freitag",  "start_time": "17:00", "end_time": "20:00"},
    {"id": 3, "day": "saturday", "day_name": "Samstag",  "start_time": "14:00", "end_time": "17:00"},
]
HOLIDAYS = {
    "2025-01-01":"Neujahr","2025-01-06":"Heilige Drei Könige","2025-04-18":"Karfreitag",
    "2025-04-21":"Ostermontag","2025-05-01":"Tag der Arbeit","2025-05-29":"Christi Himmelfahrt",
    "2025-06-09":"Pfingstmontag","2025-06-19":"Fronleichnam","2025-08-15":"Mariä Himmelfahrt",
    "2025-10-03":"Tag der Deutschen Einheit","2025-11-01":"Allerheiligen",
    "2025-12-25":"1. Weihnachtsfeiertag","2025-12-26":"2. Weihnachtsfeiertag"
}
CLOSED_MONTHS = {6,7,8,9}

def is_holiday(d): return d in HOLIDAYS
def holiday_name(d): return HOLIDAYS.get(d, "Feiertag")
def is_closed(d):
    try: return int(d[5:7]) in CLOSED_MONTHS
    except: return False
def fmt_de(d):
    try: return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y")
    except: return d
def week_start(d=None):
    d = d or datetime.now().date()
    if hasattr(d, "date"): d = d.date()
    return d - timedelta(days=d.weekday())
def slot_date(ws, day):
    m = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
    return (ws + timedelta(days=m.get(day,0))).strftime("%Y-%m-%d")

# ===== DB-Layer =====
class DB:
    def __init__(self):
        self._init()

    def conn(self):
        return sqlite3.connect(DB_FILE, check_same_thread=False)

    def _init(self):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL, name TEXT NOT NULL, password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user', sms_opt_in BOOLEAN DEFAULT 1,
                email_opt_in BOOLEAN DEFAULT 1, is_initial_admin BOOLEAN DEFAULT 0,
                active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS bookings(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL, booking_date DATE NOT NULL,
                status TEXT DEFAULT 'confirmed', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slot_id, booking_date))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS favorites(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL, date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, slot_id, date))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL,
                details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS info_pages(
                id INTEGER PRIMARY KEY AUTOINCREMENT, page_key TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL, content TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS backup_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, backup_date DATE NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL, details TEXT)""")
            c.commit()
        self._ensure_admin()
        self._ensure_info_pages()

    def _ensure_admin(self):
        if not hasattr(st, "secrets"): return
        email = st.secrets.get("ADMIN_EMAIL",""); pw = st.secrets.get("ADMIN_PASSWORD","")
        if not (email and pw): return
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM users WHERE email=? AND is_initial_admin=1", (email,))
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO users(email,phone,name,password_hash,role,sms_opt_in,is_initial_admin) VALUES(?,?,?,?,?,?,1)",
                            (email,"+4915199999999","Initial Admin",hashlib.sha256(pw.encode()).hexdigest(),"admin",1))
                c.commit()

    def _ensure_info_pages(self):
        defaults = {
            "schicht_info": ("Schicht-Informationen",
                "# Schicht-Checkliste\n\n1. Kasse holen\n2. Technik\n3. Sicherheit\n"),
            "rettungskette": ("Rettungskette Hallenbad",
                "# Rettungskette\n\n1. Notruf 112\n2. Reanimation 30:2\n3. AED\n")
        }
        with self.conn() as c:
            cur = c.cursor()
            for k,(t,content) in defaults.items():
                cur.execute("SELECT COUNT(*) FROM info_pages WHERE page_key=?", (k,))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO info_pages(page_key,title,content) VALUES(?,?,?)", (k,t,content))
            c.commit()

    # Kernmethoden (KORRIGIERT - richtige Array-Indizierung)
    def auth(self, email, password):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT id,email,phone,name,role,sms_opt_in,email_opt_in,is_initial_admin,active
                           FROM users WHERE email=? AND password_hash=?""",
                        (email, hashlib.sha256(password.encode()).hexdigest()))
            r = cur.fetchone()
        if not r or r[8] != 1: return None  # KORRIGIERT: r[8] statt r[5]
        return dict(id=r[0],email=r[1],phone=r[2],name=r[3],role=r[4],  # KORRIGIERT: richtige Indices
                    sms_opt_in=bool(r[5]),email_opt_in=bool(r[6]),is_initial_admin=bool(r[7]))

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
            return cur.rowcount > 0

    def bookings_for(self, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT b.id,b.user_id,u.name,u.email,u.phone,b.created_at
                           FROM bookings b JOIN users u ON u.id=b.user_id
                           WHERE b.slot_id=? AND b.booking_date=? AND b.status='confirmed'""", (slot_id,d))
            return [dict(id=r[0],user_id=r[1],user_name=r[2],user_email=r[3],user_phone=r[4],created_at=r[5]) for r in cur.fetchall()]  # KORRIGIERT

    def create_booking(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND booking_date=? AND status='confirmed'", (slot_id,d))
            if cur.fetchone()[0] > 0: return False,"Slot bereits belegt"  # KORRIGIERT: [0] hinzugefügt
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
            return [dict(id=r[0],slot_id=r[1],date=r[2],created_at=r[3]) for r in cur.fetchall()]  # KORRIGIERT

    def is_favorite(self, uid, slot_id, d):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id=? AND slot_id=? AND date=?", (uid,slot_id,d))
            return cur.fetchone()[0] > 0  # KORRIGIERT: [0] hinzugefügt

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
            return cur.rowcount > 0

    def user_favorites(self, uid):
        with self.conn() as c:
            cur = c.cursor()
            cur.execute("""SELECT slot_id,date,created_at FROM favorites
                           WHERE user_id=? ORDER BY date ASC""",(uid,))
            return [dict(slot_id=r[0],date=r[1],created_at=r[2]) for r in cur.fetchall()]  # KORRIGIERT

    def log(self, uid, action, details):
        try:
            with self.conn() as c:
                cur = c.cursor()
                cur.execute("INSERT INTO audit_log(user_id,action,details) VALUES(?,?,?)",(uid,action,details))
                c.commit()
        except Exception:
            pass

# ===== Services (nur aktiv, wenn nicht SAFE_MODE) =====
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
            self.enabled = bool(self.client and self.from_number and st.secrets.get("ENABLE_SMS", True))
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
        self.enabled = bool(self.user and self.pw and st.secrets.get("ENABLE_EMAIL", True))
    def send(self,to,subject,body,attachments=None):
        if not self.enabled: return False,"mail disabled"
        try:
            msg = MIMEMultipart(); msg["From"]=f"{self.from_name} <{self.user}>"
            msg["To"]=to; msg["Subject"]=subject; msg["Date"]=email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body,"plain","utf-8"))
            for att in attachments or []:
                part = MIMEBase("application","octet-stream"); part.set_payload(att["content"])
                encoders.encode_base64(part); part.add_header("Content-Disposition", f'attachment; filename="{att["filename"]}"'); msg.attach(part)
            with smtplib.SMTP("smtp.gmail.com",587) as s:
                s.starttls(); s.login(self.user,self.pw); s.send_message(msg)
            return True,"OK"
        except Exception as e:
            return False,str(e)

# ===== Backup + Scheduler (nur wenn erlaubt) =====
def _create_backup_zip(db: DB):
    data = {}
    with db.conn() as c:
        cur = c.cursor()
        for table in ["users","bookings","favorites","audit_log","info_pages","backup_log"]:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]  # KORRIGIERT: d[0] statt nur d
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
    to = (st.secrets.get("BACKUP_EMAIL","backup@example.com")
          if hasattr(st,"secrets") else "backup@example.com")
    ok,_ = mailer.send(to, f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}",
                       "Automatisches Backup im Anhang.",
                       [{"filename": f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip", "content": zip_bytes}])
    with db.conn() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO backup_log(backup_date,status,details) VALUES(?,?,?)",
                    (datetime.now().strftime("%Y-%m-%d"), "success" if ok else "failed", "auto/daily or manual"))
        c.commit()
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

def backup_fallback_check(db: DB, mailer: Mailer):
    if SAFE_MODE or not ENABLE_DAILY_BACKUP: return
    today = datetime.now().strftime("%Y-%m-%d")
    with db.conn() as c:
        cur = c.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM backup_log WHERE backup_date=? AND status='success'", (today,))
            if cur.fetchone()[0] == 0:  # KORRIGIERT: [0] hinzugefügt
                _send_daily_backup(db, mailer)
        except sqlite3.OperationalError:
            pass

# ===== UI =====
st.set_page_config(page_title="Dienstplan+ Cloud", page_icon="📅", layout="wide")

# Singletons
if "db" not in st.session_state: st.session_state.db = DB()
if "sms" not in st.session_state: st.session_state.sms = TwilioSMS()
if "mail" not in st.session_state: st.session_state.mail = Mailer()
if "week_start" not in st.session_state: st.session_state.week_start = week_start()
if "sched" not in st.session_state: st.session_state.sched = start_scheduler(st.session_state.db, st.session_state.mail)

def ui_auth():
    st.markdown("# 🔐 Willkommen bei Dienstplan+ Cloud")
    t1,t2 = st.tabs(["🔑 Anmelden","📝 Registrieren"])
    with t1:
        with st.form("f_login"):
            e = st.text_input("📧 E-Mail"); p = st.text_input("🔒 Passwort", type="password")
            if st.form_submit_button("Anmelden", type="primary"):
                u = st.session_state.db.auth(e,p)
                if u:
                    st.session_state.user = u
                    st.session_state.db.log(u["id"],"login","user login")
                    backup_fallback_check(st.session_state.db, st.session_state.mail)
                    st.success(f"Willkommen {u['name']}"); st.rerun()
                else:
                    st.error("Ungültige Anmeldedaten")
    with t2:
        with st.form("f_reg"):
            n = st.text_input("👤 Name"); r_e = st.text_input("📧 E-Mail")
            r_ph = st.text_input("📱 Telefon","+49 "); r_p1 = st.text_input("🔒 Passwort", type="password")
            r_p2 = st.text_input("🔒 Passwort wiederholen", type="password")
            if st.form_submit_button("Account erstellen", type="primary"):
                errs=[]
                if not all([n,r_e,r_ph,r_p1,r_p2]): errs.append("Alle Felder ausfüllen")
                if r_p1!=r_p2: errs.append("Passwörter stimmen nicht überein")
                if len(r_p1)<6: errs.append("Passwort min. 6 Zeichen")
                if not r_ph.startswith("+"): errs.append("Telefon mit Ländercode (z.B. +49)")
                if "@" not in r_e: errs.append("E-Mail prüfen")
                if errs:
                    for e in errs: st.error(e); return
                uid = st.session_state.db.create_user(r_e,r_ph,n,r_p1)
                if uid:
                    u = st.session_state.db.auth(r_e,r_p1); st.session_state.user = u
                    st.session_state.db.log(uid,"user_created","registered")
                    st.success("Account erstellt und eingeloggt"); st.rerun()
                else:
                    st.error("E-Mail bereits registriert")

def ui_info():
    st.markdown("# ℹ️ Informationen")
    tab1,tab2 = st.tabs(["📋 Schicht-Info","🚨 Rettungskette"])
    with tab1:
        with st.session_state.db.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT title,content FROM info_pages WHERE page_key='schicht_info'")
            rec = cur.fetchone()
        title,content = (rec[0],rec[1]) if rec else ("Schicht-Informationen","Noch keine Inhalte.")  # KORRIGIERT
        if st.session_state.user.get("role")=="admin":
            with st.form("f_edit"):
                nt = st.text_input("Titel", value=title)
                nc = st.text_area("Inhalt (Markdown)", value=content, height=300)
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
                    st.success("Gespeichert"); st.rerun()
        else:
            st.markdown(f"### {title}"); st.markdown(content)
    with tab2:
        with st.session_state.db.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT title,content FROM info_pages WHERE page_key='rettungskette'")
            rec = cur.fetchone()
        title,content = (rec[0],rec[1]) if rec else ("Rettungskette Hallenbad","Noch keine Inhalte.")  # KORRIGIERT
        st.markdown(f"### {title}"); st.markdown(content)

def ui_schedule():
    u = st.session_state.user
    ws = st.session_state.week_start
    week_end = ws + timedelta(days=6)
    colA,colB,colC = st.columns([1,4,1])
    with colA:
        if st.button("⬅️ Vorherige Woche"): st.session_state.week_start = ws - timedelta(days=7); st.rerun()
    with colB:
        st.markdown(f"### KW {ws.isocalendar()[1]} — {ws.strftime('%d.%m.%Y')} bis {week_end.strftime('%d.%m.%Y')}")  # KORRIGIERT: [1] statt [6]
    with colC:
        if st.button("Nächste Woche ➡️"): st.session_state.week_start = ws + timedelta(days=7); st.rerun()

    for slot in WEEKLY_SLOTS:
        d = slot_date(ws, slot["day"])
        if is_holiday(d):
            st.warning(f"🎄 {slot['day_name']}, {fmt_de(d)} — Feiertag: {holiday_name(d)} — keine Schichten"); continue
        if is_closed(d):
            st.warning(f"🏊 {slot['day_name']}, {fmt_de(d)} — Hallenbad geschlossen (Sommerpause)"); continue
        bookings = st.session_state.db.bookings_for(slot["id"], d)
        c1,c2 = st.columns([3,1])
        with c1:
            if bookings:
                b = bookings[0]  # KORRIGIERT: erstes Element der Liste nehmen
                if b["user_id"] == u["id"]:
                    st.info(f"✅ {slot['day_name']}, {fmt_de(d)} — Gebucht von Ihnen — ⏰ {slot['start_time']}–{slot['end_time']} — 📝 {datetime.fromisoformat(b['created_at']).strftime('%d.%m.%Y %H:%M')}")
                else:
                    st.warning(f"📋 {slot['day_name']}, {fmt_de(d)} — Gebucht von: {b['user_name']} — ⏰ {slot['start_time']}–{slot['end_time']}")
            else:
                st.success(f"✨ {slot['day_name']}, {fmt_de(d)} — Verfügbar — ⏰ {slot['start_time']}–{slot['end_time']}")
        with c2:
            is_fav = st.session_state.db.is_favorite(u["id"], slot["id"], d)
            if st.button("⭐ Beobachten" if not is_fav else "★ Beobachtet", key=f"fav_{slot['id']}_{d}"):
                (st.session_state.db.remove_favorite if is_fav else st.session_state.db.add_favorite)(u["id"],slot["id"],d)
                st.rerun()
            if bookings and b["user_id"] == u["id"]:
                if st.button("❌ Stornieren", key=f"cancel_{b['id']}"):
                    st.session_state.db.cancel_booking(b["id"], u["id"]); st.success("Storniert"); st.rerun()
            elif not bookings:
                if st.button("📝 Buchen", key=f"book_{slot['id']}_{d}", type="primary"):
                    ok,res = st.session_state.db.create_booking(u["id"], slot["id"], d)
                    if ok: st.success(f"Gebucht für {fmt_de(d)}"); st.rerun()
                    else: st.error(res)

def ui_my_shifts():
    u = st.session_state.user
    st.markdown("### 👤 Meine Schichten")
    mine = st.session_state.db.user_bookings(u["id"])
    if mine:
        for b in mine[:20]:
            slot = next(s for s in WEEKLY_SLOTS if s["id"] == b["slot_id"])
            st.info(f"{slot['day_name']}, {fmt_de(b['date'])} — ⏰ {slot['start_time']}–{slot['end_time']} — 📝 {datetime.fromisoformat(b['created_at']).strftime('%d.%m.%Y %H:%M')}")
            if st.button("❌ Stornieren", key=f"my_cancel_{b['id']}"):
                st.session_state.db.cancel_booking(b["id"], u["id"]); st.success("Storniert"); st.rerun()
    else:
        st.info("Keine Buchungen vorhanden.")

    st.markdown("---")
    st.markdown("### ⭐ Watchlist / Favoriten")
    favs = st.session_state.db.user_favorites(u["id"])
    if favs:
        for f in favs:
            slot = next(s for s in WEEKLY_SLOTS if s["id"] == f["slot_id"])
            bookings = st.session_state.db.bookings_for(slot["id"], f["date"])
            status = f"Belegt von {bookings[0]['user_name']}" if bookings else "Verfügbar"  # KORRIGIERT: [0] hinzugefügt
            st.success(f"⭐ {slot['day_name']}, {fmt_de(f['date'])} — {status} — ⏰ {slot['start_time']}–{slot['end_time']}")
            c1,c2 = st.columns(2)
            with c1:
                if st.button("🗑️ Entfernen", key=f"rm_{f['slot_id']}_{f['date']}"):
                    st.session_state.db.remove_favorite(u["id"], f["slot_id"], f["date"]); st.rerun()
            with c2:
                if not bookings and st.button("📝 Buchen", key=f"bookfav_{f['slot_id']}_{f['date']}", type="primary"):
                    ok,res = st.session_state.db.create_booking(u["id"], f["slot_id"], f["date"])
                    if ok:
                        st.session_state.db.remove_favorite(u["id"], f["slot_id"], f["date"])
                        st.success("Gebucht"); st.rerun()
                    else:
                        st.error(res)
    else:
        st.info("Noch keine Favoriten. Im Plan mit ⭐ hinzufügen.")

def ui_profile():
    u = st.session_state.user
    st.markdown("# 👤 Mein Profil")
    with st.form("f_prof"):
        n = st.text_input("Name", value=u["name"])
        ph = st.text_input("Telefon", value=u["phone"])
        sms = st.checkbox("SMS-Erinnerungen erhalten", value=u.get("sms_opt_in",True))
        if st.form_submit_button("💾 Speichern", type="primary"):
            if st.session_state.db.update_user_profile(u["id"], n, ph, sms):
                st.session_state.user.update({"name":n,"phone":ph,"sms_opt_in":sms})
                st.success("Profil aktualisiert")
            else:
                st.error("Fehler beim Speichern")

    st.markdown("### 🧪 Service-Tests")
    c1,c2 = st.columns(2)
    with c1:
        st.caption("📱 SMS-Test")
        if st.session_state.sms.enabled:
            if st.button("Test-SMS an meine Nummer senden"):
                ok,msg = st.session_state.sms.send(u["phone"], "Test-SMS vom Dienstplan+ System")
                st.success("Gesendet") if ok else st.error(f"Fehler: {msg}")
        else:
            st.info("SMS nicht konfiguriert oder Safe-Mode aktiv")
    with c2:
        st.caption("📧 E-Mail-Test")
        if st.session_state.mail.enabled:
            if st.button("Test-E-Mail an meine Adresse senden"):
                ok,msg = st.session_state.mail.send(u["email"], "Dienstplan+ Test-E-Mail",
                                                    f"Hallo {u['name']},\n\ndies ist eine Test-E-Mail.")
                st.success("Gesendet") if ok else st.error(f"Fehler: {msg}")
        else:
            st.info("E-Mail nicht konfiguriert oder Safe-Mode aktiv")

def ui_admin():
    st.markdown("# ⚙️ Admin-Panel")
    with st.expander("💾 Backup"):
        if SAFE_MODE: st.info("Safe-Mode aktiv — E-Mail/Backup deaktiviert")
        if st.button("Backup jetzt senden"):
            ok = _send_daily_backup(st.session_state.db, st.session_state.mail)
            st.success("Backup versendet" if ok else "Backup fehlgeschlagen")

def main():
    st.sidebar.write(f"Version {VERSION} · TZ {TIMEZONE_STR} · SafeMode={'ON' if SAFE_MODE else 'OFF'}")
    if "user" not in st.session_state:
        ui_auth(); return
    u = st.session_state.user
    tabs = st.tabs(["📅 Plan","👤 Meine Schichten","ℹ️ Infos","👤 Profil","⚙️ Admin"] if u.get("role")=="admin"
                   else ["📅 Plan","👤 Meine Schichten","ℹ️ Infos","👤 Profil"])
    with tabs[0]: ui_schedule()  # KORRIGIERT: tabs[0] statt tabs
    with tabs[1]: ui_my_shifts()  # KORRIGIERT: tabs[1] statt tabs[6]
    with tabs[2]: ui_info()      # KORRIGIERT: tabs[2] statt tabs[7]
    with tabs[3]: ui_profile()   # KORRIGIERT: tabs[3] statt tabs[8]
    if u.get("role")=="admin":
        with tabs[4]: ui_admin()  # KORRIGIERT: tabs[4] statt tabs[9]

if __name__ == "__main__":
    main()
