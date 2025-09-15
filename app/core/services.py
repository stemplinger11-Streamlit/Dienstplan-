"""
Dienstplan+ Cloud v3.0 - Services (SMS, E-Mail, Backup)
Vollständige Service-Implementierungen mit Fehlerbehandlung
"""
import smtplib
import zipfile
import io
import time
import threading
import schedule
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import streamlit as st

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
                body=message,
                from_=self.from_number,
                to=to_number
            )
            return True, message_obj.sid
            
        except Exception as e:
            return False, str(e)
    
    def send_admin_sms(self, message):
        """Sende SMS an alle Administratoren"""
        if not self.enabled:
            return []
        
        # Admin-SMS-Liste aus Secrets
        admin_sms_list = st.secrets.get("ADMIN_SMS_LIST", [])
        
        # Fallback: Aus Datenbank laden
        if not admin_sms_list:
            try:
                conn = st.session_state.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT phone FROM users 
                    WHERE role = 'admin' AND active = 1 AND sms_opt_in = 1
                ''')
                admin_sms_list = [row[0] for row in cursor.fetchall()]
                conn.close()
            except:
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
            
        except Exception:
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
            
            # Via Gmail SMTP senden
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.gmail_user, self.gmail_password)
                server.send_message(msg)
            
            return True, "E-Mail erfolgreich gesendet"
            
        except Exception as e:
            return False, f"E-Mail Fehler: {str(e)}"
    
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
            return False, f"Kalendereinladung Fehler: {str(e)}"
    
    def generate_ics(self, booking, slot, user, method="REQUEST", sequence=0):
        """Generiere RFC-5545 konforme ICS-Datei"""
        try:
            # Datum und Zeit parsen
            booking_date = datetime.strptime(booking['date'], '%Y-%m-%d')
            start_time = datetime.strptime(slot['start_time'], '%H:%M').time()
            end_time = datetime.strptime(slot['end_time'], '%H:%M').time()
            
            # Kombiniere Datum und Zeit
            start_dt = datetime.combine(booking_date, start_time)
            end_dt = datetime.combine(booking_date, end_time)
            
            # UTC-Konvertierung (vereinfacht für Europa/Berlin)
            # Sommerzeit: März-Oktober +2h, sonst +1h
            is_dst = 3 <= booking_date.month <= 10
            utc_offset = timedelta(hours=2 if is_dst else 1)
            
            start_utc = start_dt - utc_offset
            end_utc = end_dt - utc_offset
            
            # Stabile UID basierend auf Buchungs-ID und Datum
            uid = f"booking-{booking['id']}-{booking['date']}@dienstplan-cloud.local"
            
            # ICS-Content generieren
            ics_content = f"""BEGIN:VCALENDAR
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
            
            return ics_content.strip()
            
        except Exception as e:
            # Fallback ICS bei Fehlern
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
    """Backup-Service mit täglichen automatischen Backups"""
    
    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.scheduler_running = False
        self.scheduler_lock = threading.Lock()
    
    def start_scheduler(self):
        """Starte täglichen Backup-Scheduler (Thread-sicher)"""
        with self.scheduler_lock:
            if self.scheduler_running:
                return
            
            if not st.secrets.get("ENABLE_DAILY_BACKUP", True):
                return
            
            if not self.email_service.enabled:
                return
        
        def daily_backup_job():
            """Job-Funktion für tägliches Backup"""
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                
                # Prüfe ob heute bereits Backup gesendet
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM backup_log 
                    WHERE backup_date = ? AND status = 'success'
                ''', (today,))
                
                if cursor.fetchone()[0] == 0:  # Noch kein Backup heute
                    success = self.send_daily_backup()
                    status = "success" if success else "failed"
                    
                    cursor.execute('''
                        INSERT INTO backup_log (backup_date, status, details)
                        VALUES (?, ?, ?)
                    ''', (today, status, "Automated daily backup"))
                    conn.commit()
                
                conn.close()
                
            except Exception as e:
                print(f"Backup scheduler error: {e}")
        
        def run_scheduler():
            """Scheduler-Loop in separatem Thread"""
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(60)  # Prüfe jede Minute
                except Exception as e:
                    print(f"Scheduler loop error: {e}")
                    time.sleep(300)  # 5 Minuten warten bei Fehlern
        
        # Schedule für 20:00 Uhr täglich
        schedule.every().day.at("20:00").do(daily_backup_job)
        
        # Starte Scheduler in Daemon-Thread
        scheduler_thread = threading.Thread(
            target=run_scheduler, 
            daemon=True,
            name="BackupScheduler"
        )
        scheduler_thread.start()
        
        with self.scheduler_lock:
            self.scheduler_running = True
    
    def send_daily_backup(self):
        """Sende tägliches Backup per E-Mail"""
        try:
            # Backup erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Backup-Datei
                backup_filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Info-Datei
                info_content = f"""Dienstplan+ Cloud - Tägliches Backup
Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Version: 3.0

Dieses Backup enthält alle Daten der App:
- Benutzer und Buchungen
- Templates und Einstellungen
- Audit-Logs und Favoriten

Zum Wiederherstellen:
1. Admin-Panel öffnen
2. Backup-Sektion
3. "Backup wiederherstellen"
4. Diese ZIP-Datei hochladen
"""
                zip_file.writestr("README.txt", info_content)
            
            zip_buffer.seek(0)
            
            # E-Mail-Konfiguration
            backup_email = st.secrets.get("BACKUP_EMAIL", self.email_service.gmail_user)
            subject = f"[Dienstplan+] Tägliches Backup - {datetime.now().strftime('%d.%m.%Y')}"
            
            body = f"""Automatisches tägliches Backup der Dienstplan+ Cloud App.

📅 Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📦 Größe: {len(zip_buffer.getvalue()) / 1024:.1f} KB

Das Backup ist als ZIP-Datei angehängt und kann im Admin-Panel 
der App wiederhergestellt werden.

ℹ️ Diese E-Mail wird täglich um 20:00 Uhr automatisch versendet.

Mit freundlichen Grüßen
Ihr Dienstplan+ System"""
            
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
                print(f"Daily backup sent successfully to {backup_email}")
            else:
                print(f"Failed to send daily backup: {message}")
            
            return success
            
        except Exception as e:
            print(f"Daily backup error: {e}")
            return False
    
    def check_and_send_fallback_backup(self):
        """Fallback: Prüfe ob Backup heute schon gesendet (für Streamlit Cloud)"""
        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            
            # Nur nach 20:00 Uhr prüfen
            if now.hour < 20:
                return
            
            # Prüfe ob Backup heute bereits gesendet
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM backup_log 
                WHERE backup_date = ? AND status = 'success'
            ''', (today,))
            
            if cursor.fetchone()[0] == 0:  # Noch kein Backup heute
                success = self.send_daily_backup()
                status = "success" if success else "failed"
                
                cursor.execute('''
                    INSERT INTO backup_log (backup_date, status, details)
                    VALUES (?, ?, ?)
                ''', (today, status, "Fallback backup triggered by admin"))
                conn.commit()
            
            conn.close()
            
        except Exception as e:
            print(f"Fallback backup check error: {e}")
    
    def create_manual_backup(self):
        """Erstelle manuelles Backup für Download"""
        try:
            # Backup-Daten erstellen
            backup_data = self.db.create_backup()
            
            # ZIP im Speicher erstellen
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                backup_filename = f"manual_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                zip_file.writestr(backup_filename, backup_data)
                
                # Zusätzliche Info
                info_content = f"""Manuelles Backup - Dienstplan+ Cloud v3.0

Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
Typ: Manueller Download

Inhalt:
- Alle Benutzerdaten
- Buchungen und Schichten  
- Favoriten/Watchlists
- Templates und Konfiguration
- Audit-Logs

Wiederherstellung über Admin-Panel möglich.
"""
                zip_file.writestr("backup_info.txt", info_content)
            
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
            
        except Exception as e:
            print(f"Manual backup error: {e}")
            return None