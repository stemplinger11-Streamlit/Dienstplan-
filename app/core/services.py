# app/core/services.py
"""
Dienstplan+ Cloud v3.0 - Services (SMS, E-Mail, Backup)
APScheduler-basierter Scheduler (ersetzt 'schedule'), Gmail SMTP und Twilio-SMS
"""
import smtplib
import zipfile
import io
import threading
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import streamlit as st

# Optional: TZ aus Secrets
try:
    import pytz  # wird transitive von APScheduler mitgebracht
    _TZ = pytz.timezone(st.secrets.get("TIMEZONE", "Europe/Berlin"))
except Exception:
    _TZ = None

# APScheduler statt 'schedule'
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    Client = None


class SMSService:
    """SMS-Service via Twilio mit graceful degradation"""

    def __init__(self):
        self.client = None
        self.from_number = ""
        self.enabled = False

        if TWILIO_AVAILABLE:
            try:
                account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
                auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
                self.from_number = st.secrets.get("TWILIO_PHONE_NUMBER", "")
                if account_sid and auth_token and self.from_number:
                    self.client = Client(account_sid, auth_token)
                    self.enabled = st.secrets.get("ENABLE_SMS", True)
            except Exception:
                self.enabled = False

    def send_sms(self, to_number, message):
        """Sende SMS an einzelne Nummer"""
        if not self.enabled or not self.client:
            return False, "SMS Service nicht verfügbar"
        try:
            message_obj = self.client.messages.create(
                body=message, from_=self.from_number, to=to_number
            )
            return True, message_obj.sid
        except Exception as e:
            return False, str(e)

    def send_admin_sms(self, message):
        """Sende SMS an alle Administratoren"""
        if not self.enabled:
            return []
        admin_sms_list = st.secrets.get("ADMIN_SMS_LIST", [])
        if not admin_sms_list:
            try:
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT phone FROM users WHERE role='admin' AND active=1 AND sms_opt_in=1"
                )
                admin_sms_list = [row for row in cursor.fetchall()]
                conn.close()
            except:
                admin_sms_list = []
        results = []
        for phone in admin_sms_list:
            success, result = self.send_sms(phone, message)
            results.append({"phone": phone, "success": success, "result": result})
        return results


class EmailService:
    """E-Mail via Gmail SMTP 587 STARTTLS + ICS"""

    def __init__(self):
        self.gmail_user = ""
        self.gmail_password = ""
        self.from_name = "Dienstplan+ Cloud"
        self.enabled = False
        try:
            self.gmail_user = st.secrets.get("GMAIL_USER", "")
            self.gmail_password = st.secrets.get("GMAIL_APP_PASSWORD", "")
            self.from_name = st.secrets.get("FROM_NAME", "Dienstplan+ Cloud")
            self.enabled = bool(self.gmail_user and self.gmail_password) and st.secrets.get(
                "ENABLE_EMAIL", True
            )
        except Exception:
            self.enabled = False

    def send_email(self, to_email, subject, body, attachments=None):
        """Sende einfache E-Mail"""
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.gmail_user}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            if attachments:
                for a in attachments:
                    if isinstance(a, dict) and "filename" in a and "content" in a:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(a["content"])
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition", f'attachment; filename="{a["filename"]}"'
                        )
                        msg.attach(part)
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            return True, "E-Mail erfolgreich gesendet"
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"

    def send_calendar_invite(self, to_email, subject, body, ics_content, method="REQUEST"):
        """Sende ICS-Einladung (REQUEST/CANCEL)"""
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
        if not st.secrets.get("ENABLE_CALENDAR_INVITES", True):
            return False, "Kalendereinladungen deaktiviert"
        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = f"{self.from_name} <{self.gmail_user}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            cal_part = MIMEText(ics_content, "calendar", "utf-8")
            cal_part.add_header("Content-Disposition", "inline")
            cal_part.add_header("method", method)
            msg.attach(cal_part)
            ics_part = MIMEBase("text", "calendar")
            ics_part.add_header("Content-Disposition", 'attachment; filename="invite.ics"')
            ics_part.set_payload(ics_content.encode("utf-8"))
            encoders.encode_base64(ics_part)
            msg.attach(ics_part)
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            return True, "Kalendereinladung erfolgreich gesendet"
        except Exception as e:
            return False, f"Kalendereinladung Fehler: {str(e)}"

    def generate_ics(self, booking, slot, user, method="REQUEST", sequence=0):
        """RFC‑5545 konforme ICS-Datei mit stabiler UID und SEQUENCE"""
        try:
            booking_date = datetime.strptime(booking["date"], "%Y-%m-%d")
            start_time = datetime.strptime(slot["start_time"], "%H:%M").time()
            end_time = datetime.strptime(slot["end_time"], "%H:%M").time()
            start_dt = datetime.combine(booking_date, start_time)
            end_dt = datetime.combine(booking_date, end_time)
            is_dst = 3 <= booking_date.month <= 10
            utc_offset = timedelta(hours=2 if is_dst else 1)
            start_utc = start_dt - utc_offset
            end_utc = end_dt - utc_offset
            uid = f"booking-{booking['id']}-{booking['date']}@dienstplan-cloud.local"
            ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud v3.0//DE
METHOD:{method}
BEGIN:VEVENT
UID:{uid}
DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}
DTSTART;TZID=Europe/Berlin:{start_dt.strftime('%Y%m%dT%H%M%S')}
DTEND;TZID=Europe/Berlin:{end_dt.strftime('%Y%m%dT%H%M%S')}
SUMMARY:Schicht - {slot['day_name']}
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']} Uhr
LOCATION:Hallenbad
ORGANIZER;CN={self.from_name}:mailto:{self.gmail_user}
ATTENDEE;CN={user['name']};RSVP=TRUE:mailto:{user['email']}
STATUS:CONFIRMED
SEQUENCE:{sequence}
CREATED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
LAST-MODIFIED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
END:VEVENT
END:VCALENDAR"""
            return ics.strip()
        except Exception as e:
            return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//DE
METHOD:{method}
BEGIN:VEVENT
UID:error-{booking.get('id', 'unknown')}@dienstplan-cloud.local
DTSTART:20250101T120000Z
DTEND:20250101T130000Z
SUMMARY:Schicht-Termin
DESCRIPTION:Fehler beim Generieren der Kalendereinladung: {str(e)}
END:VEVENT
END:VCALENDAR"""


class BackupService:
    """Tägliche Backups: 20:00 per E-Mail + Fallback “>24h” bei Admin-Aufruf"""

    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.scheduler = None
        self.scheduler_running = False
        self.scheduler_lock = threading.Lock()

    def start_scheduler(self):
        """Starte BackgroundScheduler einmalig (Cron 20:00, optional TZ)"""
        with self.scheduler_lock:
            if self.scheduler_running:
                return
            if not st.secrets.get("ENABLE_DAILY_BACKUP", True):
                return
            if not self.email_service.enabled:
                return
            self.scheduler = BackgroundScheduler(timezone=_TZ) if _TZ else BackgroundScheduler()
            trigger = CronTrigger(hour=20, minute=0, timezone=_TZ) if _TZ else CronTrigger(hour=20, minute=0)
            self.scheduler.add_job(self._daily_backup_job, trigger, id="daily_backup", replace_existing=True)
            self.scheduler.start()
            self.scheduler_running = True

    def _daily_backup_job(self):
        """Scheduler-Job: sende tägliches Backup einmal pro Tag"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM backup_log WHERE backup_date=? AND status='success'",
                (today,),
            )
            if cursor.fetchone() == 0:
                success = self.send_daily_backup()
                status = "success" if success else "failed"
                cursor.execute(
                    "INSERT INTO backup_log (backup_date, status, details) VALUES (?, ?, ?)",
                    (today, status, "Automated daily backup"),
                )
                conn.commit()
            conn.close()
        except Exception:
            pass  # Fehler nicht blockierend

    def send_daily_backup(self):
        """Erzeuge ZIP im Speicher und versende per E-Mail"""
        try:
            backup_json = self.db.create_backup()
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", backup_json)
                info = f"""Dienstplan+ Cloud - Tägliches Backup
Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Version: 3.0
"""
                zf.writestr("README.txt", info)
            zip_buffer.seek(0)
            backup_email = st.secrets.get("BACKUP_EMAIL", self.email_service.gmail_user)
            subject = f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}"
            body = f"Automatisches tägliches Backup, Größe: {len(zip_buffer.getvalue())/1024:.1f} KB"
            attachments = [{"filename": f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip",
                            "content": zip_buffer.getvalue()}]
            ok, _ = self.email_service.send_email(backup_email, subject, body, attachments)
            return ok
        except Exception:
            return False

    def check_and_send_fallback_backup(self):
        """Fallback: bei Admin-Seitenaufruf nach 20:00 prüfen und ggf. senden"""
        try:
            now = datetime.now()
            if now.hour < 20:
                return
            today = now.strftime("%Y-%m-%d")
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM backup_log WHERE backup_date=? AND status='success'",
                (today,),
            )
            if cursor.fetchone() == 0:
                success = self.send_daily_backup()
                status = "success" if success else "failed"
                cursor.execute(
                    "INSERT INTO backup_log (backup_date, status, details) VALUES (?, ?, ?)",
                    (today, status, "Fallback backup triggered by admin"),
                )
                conn.commit()
            conn.close()
        except Exception:
            pass
