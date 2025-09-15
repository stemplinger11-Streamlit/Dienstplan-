# streamlit_app.py
import streamlit as st
from datetime import datetime, timedelta
import sqlite3, hashlib, io, zipfile, threading, pytz, time
import requests, email.utils, json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ----------- KONSTANTEN & DB-SCHEMA ----------
DB_NAME = "dienstplan.db"
TIMEZONE = "Europe/Berlin"
WEEK_DAYS = [
    {"id": 1, "day_name": "Montag", "day": "monday", "start_time": "17:00", "end_time": "20:00"},
    {"id": 2, "day_name": "Freitag", "day": "friday", "start_time": "17:00", "end_time": "20:00"},
]
DEFAULT_ROLE = "user"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def ensure_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, phone TEXT, name TEXT, password_hash TEXT,
            role TEXT DEFAULT 'user', sms_opt_in BOOLEAN DEFAULT 1, email_opt_in BOOLEAN DEFAULT 1, active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, slot_id INTEGER, booking_date DATE, status TEXT DEFAULT 'confirmed', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(slot_id, booking_date)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, slot_id INTEGER NOT NULL, date TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, slot_id, date)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, details TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()

ensure_db()

# ----------- HELPER/UTILS ----------
def user_exists(email):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        return c.fetchone() is not None

def add_user(email, phone, name, password, role=DEFAULT_ROLE):
    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO users (email, phone, name, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (email, phone, name, hash_pw(password), role),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def validate_login(email, pw):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, email, phone, role FROM users WHERE email=? AND password_hash=? AND active=1",
                  (email, hash_pw(pw)))
        return c.fetchone()

def add_audit(user_id, action, details):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO audit_log (user_id, action, details) VALUES (?, ?, ?)",
                  (user_id, action, details))
        conn.commit()

def add_booking(user_id, slot_id, booking_date):
    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO bookings (user_id, slot_id, booking_date) VALUES (?, ?, ?)",
                (user_id, slot_id, booking_date),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def cancel_booking(booking_id, user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id))
        conn.commit()

def get_bookings(slot_id, day):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT b.id, u.name, u.email FROM bookings b JOIN users u ON b.user_id = u.id WHERE b.slot_id=? AND b.booking_date=?", (slot_id, day))
        return c.fetchall()

# ------ SMS/E-Mail/ICS DEMO STUBS (WebSMS API + Gmail SMTP) ------
def send_sms_websms(number, msg):
    url = st.secrets["WEB_SMS_BASE_URL"].rstrip("/") + st.secrets.get("WEB_SMS_ENDPOINT", "/rest/smsmessaging/simple")
    payload = {
        "recipientAddressList": [number], "messageContent": msg,
        "senderAddress": st.secrets["WEB_SMS_SENDER"]
    }
    r = requests.post(url, json=payload, auth=(st.secrets["WEB_SMS_USERNAME"], st.secrets["WEB_SMS_PASSWORD"]), timeout=12)
    return r.ok

def send_email(to, subject, body):
    try:
        m = MIMEMultipart()
        m["From"] = st.secrets["GMAIL_USER"]
        m["To"] = to
        m["Subject"] = subject
        m.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(st.secrets["GMAIL_USER"], st.secrets["GMAIL_APP_PASSWORD"])
            server.send_message(m)
        return True
    except Exception as e:
        return False

def backup_db():
    with get_connection() as conn:
        c = conn.cursor()
        names = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        zipbuf = io.BytesIO()
        with zipfile.ZipFile(zipbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for t in names:
                data = list(c.execute(f"SELECT * FROM {t}"))
                z.writestr(f"{t}.json", json.dumps(data))
        zipbuf.seek(0)
        return zipbuf.read()

def backup_cron():
    while True:
        now = datetime.now(pytz.timezone(TIMEZONE))
        # Run every day at 20:00
        if now.hour == 20 and now.minute < 2:
            buf = backup_db()
            send_email(st.secrets["BACKUP_EMAIL"], "[Backup] Dienstplan+ DB", "Backup im Anhang.", [{"filename": "backup.zip", "content": buf}])
        time.sleep(120)

# Start APScheduler Cron-Thread (Simplified)
threading.Thread(target=backup_cron, daemon=True).start()

# ----------- STREAMLIT UI ----------
st.set_page_config(page_title="Dienstplan+ Cloud", layout="wide")
st.header("Dienstplan+ Cloud v3.0 (Streamlit.io Ready)")

menu = st.sidebar.radio("Menü", ["Login / Registrierung", "Schichten", "Admin", "Profil", "Backup/Log"])

if menu == "Login / Registrierung":
    st.subheader("Login")
    with st.form("loginf"):
        email = st.text_input("E-Mail")
        pw = st.text_input("Passwort", type="password")
        login = st.form_submit_button("Anmelden")
    if login:
        u = validate_login(email, pw)
        if u:
            st.session_state["user"] = u
            st.success(f"Willkommen {u[1]}")
            add_audit(u[0], "login", "Login erfolgreich")
        else:
            st.error("Falsche Anmeldedaten oder Account inaktiv.")
    st.subheader("Registrieren")
    with st.form("registerf"):
        n = st.text_input("Name")
        r_email = st.text_input("Neue E-Mail")
        r_phone = st.text_input("Telefon")
        r_pw = st.text_input("Passwort (min 6 Zeichen)", type="password")
        r_conf = st.text_input("Passwort wiederholen", type="password")
        reg = st.form_submit_button("Account anlegen")
    if reg:
        if len(r_pw) < 6:
            st.warning("Passwort zu kurz.")
        elif r_pw != r_conf:
            st.warning("Passwörter stimmen nicht überein.")
        elif user_exists(r_email):
            st.warning("E-Mail existiert schon.")
        else:
            add_user(r_email, r_phone, n, r_pw)
            st.success("Account erstellt.")
elif menu == "Schichten":
    st.subheader("Dienstplan")
    user = st.session_state.get("user", None)
    week_start = datetime.now() - timedelta(days=datetime.now().weekday())
    days = [(week_start+timedelta(i)).date() for i in range(7)]
    for day in days:
        st.write(f"--- {day} ---")
        for slot in WEEK_DAYS:
            slot_status = get_bookings(slot['id'], str(day))
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{slot['day_name']}** {slot['start_time']} - {slot['end_time']}")
                if slot_status:
                    usr = slot_status[0][1]
                    st.info(f"Belegt: {usr}")
                elif user:
                    if st.button("Buchen", key=f"book{slot['id']}{day}"):
                        if add_booking(user[0], slot["id"], str(day)):
                            st.success(f"Gebucht ({slot['day_name']})")
                            add_audit(user[0], "booking", f"Slot {slot['id']} {day}")
                        else:
                            st.error("Slot bereits belegt!")
            with col2:
                if slot_status and user and slot_status[0][2] == user[2]:
                    if st.button("Stornieren", key=f"cancel{slot['id']}{day}"):
                        cancel_booking(slot_status[0][0], user[0])
                        st.success("Storniert.")
elif menu == "Profil":
    st.subheader("Profilmanagement")
    user = st.session_state.get("user", None)
    if user:
        st.write(f"Name: {user[1]}")
        st.write(f"E-Mail: {user[2]}")
        st.write(f"Telefon: {user[3]}")
    else:
        st.warning("Bitte zuerst anmelden!")

elif menu == "Admin":
    st.subheader("Admin-Funktionen")
    st.write("Benutzer Rollen-/Statusverwaltung, Mail/Test, Audits, Backup, Templates etc. – demnächst hier.")
    st.write("Für mehr Features bitte die Beispiel-Dateien modular gegliedert hinzufügen.")

elif menu == "Backup/Log":
    st.subheader("Backup-Download")
    if st.button("Backup jetzt erstellen und anzeigen"):
        buf = backup_db()
        st.download_button("Backup laden", buf, "backup.zip")

# Hinweis: Alle Features können modular als pages/*.py oder app/*.py erweitert werden!
