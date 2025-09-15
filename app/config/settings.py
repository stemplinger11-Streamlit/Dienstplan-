"""
Dienstplan+ Cloud v3.0 - Einstellungen und Secrets-Verwaltung
Zentrale Verwaltung aller Konfigurationsparameter mit Fallbacks
"""
import streamlit as st

class AppSettings:
    """Zentrale Einstellungsklasse für alle App-Konfigurationen"""
    
    def __init__(self):
        """Lade alle Einstellungen aus Streamlit Secrets mit Fallbacks"""
        self._load_settings()
    
    def _load_settings(self):
        """Lade Einstellungen aus st.secrets mit sicheren Fallbacks"""
        
        # Admin-Konfiguration
        self.admin_email = st.secrets.get("ADMIN_EMAIL", "")
        self.admin_password = st.secrets.get("ADMIN_PASSWORD", "")
        self.admin_emails = st.secrets.get("ADMIN_EMAILS", [])
        self.admin_sms_list = st.secrets.get("ADMIN_SMS_LIST", [])
        
        # SMS-Service (Twilio)
        self.twilio_account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
        self.twilio_phone_number = st.secrets.get("TWILIO_PHONE_NUMBER", "")
        
        # E-Mail-Service (Gmail)
        self.gmail_user = st.secrets.get("GMAIL_USER", "")
        self.gmail_app_password = st.secrets.get("GMAIL_APP_PASSWORD", "")
        self.from_name = st.secrets.get("FROM_NAME", "Dienstplan+ Cloud")
        self.backup_email = st.secrets.get("BACKUP_EMAIL", self.gmail_user)
        
        # Feature-Flags
        self.enable_sms = st.secrets.get("ENABLE_SMS", True)
        self.enable_email = st.secrets.get("ENABLE_EMAIL", True)
        self.enable_calendar_invites = st.secrets.get("ENABLE_CALENDAR_INVITES", True)
        self.enable_7_day_warnings = st.secrets.get("ENABLE_7_DAY_WARNINGS", True)
        self.enable_sms_booking_confirmation = st.secrets.get("ENABLE_SMS_BOOKING_CONFIRMATION", False)
        self.enable_daily_backup = st.secrets.get("ENABLE_DAILY_BACKUP", True)
        self.enable_whatsapp = st.secrets.get("ENABLE_WHATSAPP", False)
        self.enable_audit_log = st.secrets.get("ENABLE_AUDIT_LOG", True)
        
        # App-Konfiguration
        self.app_name = st.secrets.get("APP_NAME", "Dienstplan+ Cloud")
        self.timezone = st.secrets.get("TIMEZONE", "Europe/Berlin")
        self.debug_mode = st.secrets.get("DEBUG_MODE", False)
        
        # WhatsApp (für zukünftige Erweiterungen)
        self.whatsapp_api_key = st.secrets.get("WHATSAPP_API_KEY", "")
        self.whatsapp_base_url = st.secrets.get("WHATSAPP_BASE_URL", "")
        
        # Limits
        self.max_bookings_per_user = st.secrets.get("MAX_BOOKINGS_PER_USER", 0)
        self.max_booking_days_ahead = st.secrets.get("MAX_BOOKING_DAYS_AHEAD", 60)
        self.cancellation_hours_before = st.secrets.get("CANCELLATION_HOURS_BEFORE", 2)
    
    @property
    def sms_enabled(self):
        """Prüfe ob SMS-Service vollständig konfiguriert und aktiviert ist"""
        return (
            self.enable_sms and
            self.twilio_account_sid and
            self.twilio_auth_token and
            self.twilio_phone_number
        )
    
    @property
    def email_enabled(self):
        """Prüfe ob E-Mail-Service vollständig konfiguriert und aktiviert ist"""
        return (
            self.enable_email and
            self.gmail_user and
            self.gmail_app_password
        )
    
    @property
    def calendar_invites_enabled(self):
        """Prüfe ob Kalender-Einladungen möglich sind"""
        return self.email_enabled and self.enable_calendar_invites
    
    @property
    def daily_backup_enabled(self):
        """Prüfe ob tägliche Backups möglich sind"""
        return self.email_enabled and self.enable_daily_backup and self.backup_email
    
    @property
    def warnings_enabled(self):
        """Prüfe ob 7-Tage-Warnungen möglich sind"""
        return self.sms_enabled and self.enable_7_day_warnings
    
    def get_admin_emails(self):
        """Erhalte Liste der Admin-E-Mail-Adressen"""
        if isinstance(self.admin_emails, list) and self.admin_emails:
            return self.admin_emails
        elif self.admin_email:
            return [self.admin_email]
        else:
            return []
    
    def get_admin_sms_numbers(self):
        """Erhalte Liste der Admin-SMS-Nummern"""
        if isinstance(self.admin_sms_list, list) and self.admin_sms_list:
            return self.admin_sms_list
        else:
            return []
    
    def is_admin_email(self, email):
        """Prüfe ob E-Mail-Adresse Admin-Rechte hat"""
        admin_emails = self.get_admin_emails()
        return email in admin_emails
    
    def get_smtp_config(self):
        """Erhalte SMTP-Konfiguration für Gmail"""
        return {
            "server": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
            "username": self.gmail_user,
            "password": self.gmail_app_password
        }
    
    def get_twilio_config(self):
        """Erhalte Twilio-Konfiguration"""
        return {
            "account_sid": self.twilio_account_sid,
            "auth_token": self.twilio_auth_token,
            "phone_number": self.twilio_phone_number
        }
    
    def get_app_info(self):
        """Erhalte App-Informationen"""
        return {
            "name": self.app_name,
            "version": "3.0",
            "timezone": self.timezone,
            "debug": self.debug_mode
        }
    
    def validate_configuration(self):
        """Validiere Konfiguration und gebe Warnungen/Fehler zurück"""
        issues = []
        warnings = []
        
        # Kritische Validierungen
        if not self.admin_email or not self.admin_password:
            issues.append("ADMIN_EMAIL und ADMIN_PASSWORD müssen gesetzt sein")
        
        # Feature-spezifische Validierungen
        if self.enable_sms and not self.sms_enabled:
            warnings.append("SMS aktiviert aber Twilio nicht vollständig konfiguriert")
        
        if self.enable_email and not self.email_enabled:
            warnings.append("E-Mail aktiviert aber Gmail nicht vollständig konfiguriert")
        
        if self.enable_calendar_invites and not self.calendar_invites_enabled:
            warnings.append("Kalender-Einladungen aktiviert aber E-Mail nicht funktionsfähig")
        
        if self.enable_daily_backup and not self.daily_backup_enabled:
            warnings.append("Tägliche Backups aktiviert aber E-Mail/BACKUP_EMAIL nicht konfiguriert")
        
        if self.enable_7_day_warnings and not self.warnings_enabled:
            warnings.append("7-Tage-Warnungen aktiviert aber SMS nicht funktionsfähig")
        
        # Admin-Listen Validierung
        if not self.get_admin_emails():
            warnings.append("Keine Admin-E-Mail-Adressen konfiguriert")
        
        return {
            "critical_issues": issues,
            "warnings": warnings,
            "sms_available": self.sms_enabled,
            "email_available": self.email_enabled,
            "calendar_available": self.calendar_invites_enabled,
            "backup_available": self.daily_backup_enabled
        }
    
    def __str__(self):
        """String-Repräsentation für Debugging"""
        return f"AppSettings(sms={self.sms_enabled}, email={self.email_enabled}, backup={self.daily_backup_enabled})"