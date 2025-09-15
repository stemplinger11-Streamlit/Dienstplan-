"""
Dienstplan+ Cloud v3.0 - Services (SMS, E-Mail, Backup)
VOLLSTÄNDIG ÜBERARBEITET: APScheduler statt schedule, verbesserte Thread-Safety
"""

import smtplib
import zipfile
import io
import time
import threading
import sqlite3
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import streamlit as st

# APScheduler statt schedule (verhindert Konflikte)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Twilio SMS mit graceful degradation
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
                    print(f"✅ SMS-Service initialisiert: {self.from_number}")
                else:
                    print("⚠️ SMS-Service: Credentials unvollständig")
            except Exception as e:
                print(f"❌ SMS-Service Fehler: {e}")
                self.enabled = False

    def send_sms(self, to_number, message):
        """Sende SMS an einzelne Nummer"""
        if not self.enabled or not self.client:
            return False, "SMS Service nicht verfügbar"
        
        try:
            # Bereinige Telefonnummer
            clean_number = self._clean_phone_number(to_number)
            
            message_obj = self.client.messages.create(
                body=message[:1600],  # SMS-Längen-Limit
                from_=self.from_number,
                to=clean_number
            )
            return True, message_obj.sid
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ SMS-Fehler an {to_number}: {error_msg}")
            return False, error_msg

    def _clean_phone_number(self, phone):
        """Bereinigt Telefonnummer für Twilio"""
        # Entferne Leerzeichen und Bindestriche
        clean = phone.replace(" ", "").replace("-", "")
        
        # Stelle sicher, dass + vorhanden ist
        if not clean.startswith("+"):
            if clean.startswith("0"):
                clean = "+49" + clean[1:]  # Deutsche Nummern
            else:
                clean = "+" + clean
                
        return clean

    def send_admin_sms(self, message):
        """Sende SMS an alle Administratoren mit de-duplication"""
        if not self.enabled:
            return []

        # Admin-SMS-Liste aus Secrets laden
        admin_sms_list = st.secrets.get("ADMIN_SMS_LIST", [])
        
        # Fallback: Aus Datenbank laden
        if not admin_sms_list:
            try:
                conn = sqlite3.connect('dienstplan.db', check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT phone FROM users 
                    WHERE role = 'admin' AND active = 1 AND sms_opt_in = 1
                ''')
                admin_sms_list = [row[0] for row in cursor.fetchall()]
                conn.close()
            except Exception as e:
                print(f"❌ Admin-SMS DB-Fehler: {e}")
                admin_sms_list = []

        # SMS an alle Admins senden
        results = []
        for phone in admin_sms_list:
            success, result = self.send_sms(phone, message)
            results.append({
                'phone': phone,
                'success': success,
                'result': result
            })
            
        return results


class EmailService:
    """E-Mail-Service via Gmail SMTP mit ICS-Kalender-Unterstützung"""
    
    def __init__(self):
        self.gmail_user = ""
        self.gmail_password = ""
        self.from_name = "Dienstplan+ Cloud"
        self.enabled = False
        
        try:
            self.gmail_user = st.secrets.get("GMAIL_USER", "")
            self.gmail_password = st.secrets.get("GMAIL_APP_PASSWORD", "")
            self.from_name = st.secrets.get("FROM_NAME", "Dienstplan+ Cloud")
            
            self.enabled = (
                bool(self.gmail_user and self.gmail_password) and 
                st.secrets.get("ENABLE_EMAIL", True)
            )
            
            if self.enabled:
                print(f"✅ E-Mail-Service initialisiert: {self.gmail_user}")
            else:
                print("⚠️ E-Mail-Service: Credentials fehlen")
                
        except Exception as e:
            print(f"❌ E-Mail-Service Fehler: {e}")
            self.enabled = False

    def send_email(self, to_email, subject, body, attachments=None):
        """Sende einfache E-Mail mit optionalen Anhängen"""
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
        
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.gmail_user}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = email.utils.formatdate(localtime=True)
            
            # Text-Teil hinzufügen
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # Anhänge hinzufügen
            if attachments:
                for attachment in attachments:
                    if isinstance(attachment, dict) and 'filename' in attachment and 'content' in attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment['content'])
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{attachment["filename"]}"'
                        )
                        msg.attach(part)
            
            # Via Gmail SMTP senden mit verbesserter Fehlerbehandlung
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
                
            return True, "E-Mail erfolgreich gesendet"
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "Gmail-Authentifizierung fehlgeschlagen - prüfe App-Password"
            print(f"❌ {error_msg}: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"E-Mail Fehler: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg

    def send_calendar_invite(self, to_email, subject, body, ics_content, method="REQUEST"):
        """Sende Kalendereinladung per E-Mail mit ICS-Anhang"""
        if not self.enabled:
            return False, "E-Mail Service nicht konfiguriert"
            
        if not st.secrets.get("ENABLE_CALENDAR_INVITES", True):
            return False, "Kalendereinladungen deaktiviert"
        
        try:
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{self.from_name} <{self.gmail_user}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Date'] = email.utils.formatdate(localtime=True)
            
            # Text-Teil
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # ICS als calendar MIME part (RFC-5545 konform)
            cal_part = MIMEText(ics_content, 'calendar', 'utf-8')
            cal_part.add_header('Content-Disposition', 'inline')
            cal_part.add_header('method', method)
            msg.attach(cal_part)
            
            # ICS auch als Datei-Anhang für bessere Kompatibilität
            ics_part = MIMEBase('text', 'calendar')
            ics_part.add_header('Content-Disposition', 'attachment; filename="invite.ics"')
            ics_part.set_payload(ics_content.encode('utf-8'))
            encoders.encode_base64(ics_part)
            msg.attach(ics_part)
            
            # Via Gmail SMTP senden
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
                
            return True, "Kalendereinladung erfolgreich gesendet"
            
        except Exception as e:
            error_msg = f"Kalendereinladung Fehler: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg

    def generate_ics(self, booking, slot, user, method="REQUEST", sequence=0):
        """Generiere RFC-5545 konforme ICS-Datei mit Timezone-Support"""
        try:
            # Datum und Zeit parsen
            booking_date = datetime.strptime(booking['date'], '%Y-%m-%d')
            start_time = datetime.strptime(slot['start_time'], '%H:%M').time()
            end_time = datetime.strptime(slot['end_time'], '%H:%M').time()
            
            # Kombiniere Datum und Zeit
            start_dt = datetime.combine(booking_date, start_time)
            end_dt = datetime.combine(booking_date, end_time)
            
            # Timezone-Handling mit pytz
            berlin_tz = pytz.timezone('Europe/Berlin')
            start_dt_tz = berlin_tz.localize(start_dt)
            end_dt_tz = berlin_tz.localize(end_dt)
            
            # UTC-Konvertierung
            start_utc = start_dt_tz.astimezone(pytz.UTC)
            end_utc = end_dt_tz.astimezone(pytz.UTC)
            
            # Stabile UID basierend auf Buchungs-ID und Datum
            uid = f"booking-{booking['id']}-{booking['date']}@dienstplan-cloud.local"
            
            # ICS-Content generieren (RFC-5545 konform)
            ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud v3.0//NONSGML Event//EN
METHOD:{method}
BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
DTSTART:20070325T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
TZNAME:CEST
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071028T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
TZNAME:CET
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:{uid}
DTSTART;TZID=Europe/Berlin:{start_dt.strftime('%Y%m%dT%H%M%S')}
DTEND;TZID=Europe/Berlin:{end_dt.strftime('%Y%m%dT%H%M%S')}
DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Schicht - {slot['day_name']}
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']} Uhr\\nHallenbad Dienstplan
LOCATION:Hallenbad
ORGANIZER;CN={self.from_name}:mailto:{self.gmail_user}
ATTENDEE;CN={user['name']};RSVP=TRUE:mailto:{user['email']}
STATUS:CONFIRMED
SEQUENCE:{sequence}
CREATED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
LAST-MODIFIED:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
END:VEVENT
END:VCALENDAR"""
            
            return ics_content.strip()
            
        except Exception as e:
            print(f"❌ ICS-Generation Fehler: {e}")
            # Fallback ICS bei Fehlern
            return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud//NONSGML Event//EN
METHOD:{method}
BEGIN:VEVENT
UID:error-{booking.get('id', 'unknown')}@dienstplan-cloud.local
DTSTART:20250101T120000Z
DTEND:20250101T130000Z
SUMMARY:Schicht-Termin
DESCRIPTION:Fehler beim Generieren der Kalendereinladung: {str(e)}
LOCATION:Hallenbad
END:VEVENT
END:VCALENDAR"""


class BackupService:
    """Backup-Service mit APScheduler für tägliche automatische Backups"""
    
    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.scheduler = None
        self.scheduler_running = False
        self.scheduler_lock = threading.Lock()
        
    def start_scheduler(self):
        """Starte APScheduler für tägliche Backups (Thread-sicher)"""
        with self.scheduler_lock:
            if self.scheduler_running:
                print("ℹ️ Backup-Scheduler läuft bereits")
                return
                
            if not st.secrets.get("ENABLE_DAILY_BACKUP", True):
                print("⚠️ Tägliche Backups deaktiviert")
                return
                
            if not self.email_service.enabled:
                print("⚠️ E-Mail-Service nicht verfügbar - Backup-Scheduler nicht gestartet")
                return
        
        try:
            # APScheduler konfigurieren
            self.scheduler = BackgroundScheduler(
                timezone=pytz.timezone('Europe/Berlin'),
                daemon=True
            )
            
            # Tägliches Backup um 20:00 Uhr
            self.scheduler.add_job(
                func=self._daily_backup_job,
                trigger=CronTrigger(hour=20, minute=0),
                id='daily_backup',
                name='Tägliches Dienstplan-Backup',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300  # 5 Minuten Toleranz
            )
            
            self.scheduler.start()
            
            with self.scheduler_lock:
                self.scheduler_running = True
                
            print("✅ Backup-Scheduler gestartet (APScheduler) - täglich um 20:00 Uhr")
            
        except Exception as e:
            print(f"❌ Backup-Scheduler Fehler: {e}")
            self.scheduler_running = False

    def stop_scheduler(self):
        """Stoppe Backup-Scheduler sauber"""
        with self.scheduler_lock:
            if self.scheduler and self.scheduler_running:
                try:
                    self.scheduler.shutdown(wait=False)
                    self.scheduler_running = False
                    print("✅ Backup-Scheduler gestoppt")
                except Exception as e:
                    print(f"⚠️ Scheduler-Stop Fehler: {e}")

    def _daily_backup_job(self):
        """Job-Funktion für tägliches Backup (wird von APScheduler aufgerufen)"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            print(f"🔄 Starte tägliches Backup für {today}")
            
            # Prüfe ob heute bereits Backup gesendet
            conn = sqlite3.connect('dienstplan.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM backup_log 
                WHERE backup_date = ? AND status = 'success'
            ''', (today,))
            
            if cursor.fetchone()[0] == 0:  # Noch kein Backup heute
                success = self.send_daily_backup()
                status = "success" if success else "failed"
                
                # Backup-Log aktualisieren
                cursor.execute('''
                    INSERT INTO backup_log (backup_date, status, details) 
                    VALUES (?, ?, ?)
                ''', (today, status, "Automated daily backup via APScheduler"))
                
                conn.commit()
                
                if success:
                    print(f"✅ Tägliches Backup erfolgreich gesendet: {today}")
                else:
                    print(f"❌ Tägliches Backup fehlgeschlagen: {today}")
            else:
                print(f"ℹ️ Backup für {today} bereits vorhanden - überspringe")
                
            conn.close()
            
        except Exception as e:
            print(f"❌ Daily Backup Job Fehler: {e}")

    def send_daily_backup(self):
        """Sende tägliches Backup per E-Mail"""
        try:
            print("📦 Erstelle Backup-Daten...")
            # Backup erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                # Backup-Datei
                backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Info-Datei
                info_content = f"""Dienstplan+ Cloud - Tägliches Backup
                
Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Version: 3.0
Backup-Methode: APScheduler (täglich 20:00 Uhr)

Dieses Backup enthält alle Daten der App:
- Benutzer und Buchungen
- Templates und Einstellungen  
- Audit-Logs und Favoriten
- System-Konfiguration

Zum Wiederherstellen:
1. Admin-Panel öffnen
2. Backup-Sektion wählen
3. "Backup wiederherstellen" klicken
4. Diese ZIP-Datei hochladen

Support: siehe README.md im Projekt
"""
                zip_file.writestr("README.txt", info_content)
            
            zip_buffer.seek(0)
            zip_size_kb = len(zip_buffer.getvalue()) / 1024
            
            # E-Mail-Konfiguration
            backup_email = st.secrets.get("BACKUP_EMAIL", self.email_service.gmail_user)
            subject = f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}"
            
            body = f"""Automatisches tägliches Backup der Dienstplan+ Cloud App.

📅 Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📦 Größe: {zip_size_kb:.1f} KB
🔧 Methode: APScheduler (v3.10.4)
⏰ Zeitplan: Täglich um 20:00 Uhr

Das Backup ist als ZIP-Datei angehängt und kann im Admin-Panel
der App wiederhergestellt werden.

System-Status:
- SMS-Service: {'✅ Aktiv' if st.session_state.get('sms_service', {}).get('enabled', False) else '❌ Inaktiv'}
- E-Mail-Service: {'✅ Aktiv' if self.email_service.enabled else '❌ Inaktiv'}
- Auto-Backup: ✅ Läuft

ℹ️ Diese E-Mail wird täglich automatisch versendet.
Bei Problemen siehe Admin-Panel > System-Status.

Mit freundlichen Grüßen
Ihr Dienstplan+ System v3.0"""
            
            # Anhang vorbereiten
            attachments = [{
                'filename': f"dienstplan_backup_{datetime.now().strftime('%Y%m%d')}.zip",
                'content': zip_buffer.getvalue()
            }]
            
            # E-Mail senden
            success, message = self.email_service.send_email(
                backup_email, subject, body, attachments
            )
            
            if success:
                print(f"✅ Daily backup sent successfully to {backup_email}")
            else:
                print(f"❌ Failed to send daily backup: {message}")
                
            return success
            
        except Exception as e:
            print(f"❌ Daily backup error: {e}")
            return False

    def create_manual_backup(self):
        """Erstelle manuelles Backup für Download"""
        try:
            print("📦 Erstelle manuelles Backup...")
            # Backup-Daten erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                backup_filename = f"manual_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Zusätzliche Info
                info_content = f"""Manuelles Backup - Dienstplan+ Cloud v3.0

Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Typ: Manueller Download (Admin-Panel)

Inhalt:
- Alle Benutzerdaten
- Buchungen und Schichten  
- Favoriten/Watchlists
- Templates und Konfiguration
- Audit-Logs
- System-Einstellungen

Wiederherstellung:
Über Admin-Panel > Backup-Verwaltung > "Backup wiederherstellen"

Technische Details:
- Format: JSON in ZIP-Archiv
- Komprimierung: DEFLATED Level 6
- Charset: UTF-8
- Kompatibilität: Dienstplan+ Cloud v3.0+
"""
                zip_file.writestr("backup_info.txt", info_content)
            
            zip_buffer.seek(0)
            print(f"✅ Manuelles Backup erstellt: {len(zip_buffer.getvalue()) / 1024:.1f} KB")
            return zip_buffer.getvalue()
            
        except Exception as e:
            print(f"❌ Manual backup error: {e}")
            return None

    def check_and_send_fallback_backup(self):
        """Fallback für Streamlit Cloud: Prüfe manuell auf fehlende Backups"""
        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            
            # Nur nach 20:00 Uhr prüfen
            if now.hour < 20:
                return
                
            print(f"🔄 Fallback-Backup-Check für {today}")
            
            # Prüfe ob Backup heute bereits gesendet
            conn = sqlite3.connect('dienstplan.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM backup_log 
                WHERE backup_date = ? AND status = 'success'
            ''', (today,))
            
            if cursor.fetchone()[0] == 0:  # Noch kein Backup heute
                print("⚠️ Kein Backup heute gefunden - triggere Fallback-Backup")
                success = self.send_daily_backup()
                status = "success" if success else "failed"
                
                cursor.execute('''
                    INSERT INTO backup_log (backup_date, status, details) 
                    VALUES (?, ?, ?)
                ''', (today, status, "Fallback backup triggered by admin"))
                
                conn.commit()
                
            conn.close()
            
        except Exception as e:
            print(f"❌ Fallback backup check error: {e}")

    def get_scheduler_status(self):
        """Gibt aktuellen Scheduler-Status zurück"""
        with self.scheduler_lock:
            if not self.scheduler_running:
                return {
                    'running': False,
                    'jobs': 0,
                    'next_run': None,
                    'error': 'Scheduler nicht gestartet'
                }
            
            try:
                jobs = self.scheduler.get_jobs()
                next_run = None
                if jobs:
                    job = jobs[0]  # daily_backup job
                    next_run = job.next_run_time.strftime('%d.%m.%Y %H:%M:%S') if job.next_run_time else None
                
                return {
                    'running': True,
                    'jobs': len(jobs),
                    'next_run': next_run,
                    'error': None
                }
                
            except Exception as e:
                return {
                    'running': False,
                    'jobs': 0, 
                    'next_run': None,
                    'error': str(e)
                }