"""
Dienstplan+ Cloud v3.0 - Modularer App-Starter
Haupteinstiegspunkt für die Streamlit-App mit Routing und Session-Management
"""
import streamlit as st
import sys
import os

# App-Konfiguration
st.set_page_config(
    page_title="Dienstplan+ Cloud v3.0",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Modulpfade hinzufügen
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Imports der Module
try:
    from app.config.constants import WEEKLY_SLOTS, BAVARIAN_HOLIDAYS_2025
    from app.config.settings import AppSettings
    from app.core.db import DatabaseManager
    from app.core.services import SMSService, EmailService, BackupService
    from app.core.helpers import get_week_start, get_current_week_start, check_7_day_warnings
    from app.ui.css import apply_css
    from app.pages.auth import show_login
    from app.pages.schedule import show_schedule_tab
    from app.pages.my_shifts import show_my_shifts_tab
    from app.pages.admin import show_admin_tab
    from app.pages.info import show_information_tab
except ImportError as e:
    st.error(f"❌ Modul-Import-Fehler: {e}")
    st.error("Bitte stellen Sie sicher, dass alle Module im app/ Ordner vorhanden sind.")
    st.stop()

def init_session_state():
    """Initialisiere Session State mit allen benötigten Variablen"""
    
    # App-Services initialisieren (nur einmal)
    if 'app_initialized' not in st.session_state:
        try:
            st.session_state.db = DatabaseManager()
            st.session_state.sms_service = SMSService()
            st.session_state.email_service = EmailService()
            st.session_state.backup_service = BackupService(
                st.session_state.db, 
                st.session_state.email_service
            )
            st.session_state.settings = AppSettings()
            st.session_state.app_initialized = True
            
            # Scheduler für tägliche Backups starten (nur einmal)
            if 'scheduler_started' not in st.session_state:
                st.session_state.backup_service.start_scheduler()
                st.session_state.scheduler_started = True
            
        except Exception as e:
            st.error(f"❌ App-Initialisierung fehlgeschlagen: {e}")
            st.stop()
    
    # Session State Defaults
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    
    if 'show_profile' not in st.session_state:
        st.session_state.show_profile = False
    
    # Aktuelle Woche auf Montag der ISO-Kalenderwoche setzen
    if 'current_week_start' not in st.session_state:
        st.session_state.current_week_start = get_current_week_start()
    
    # 7-Tage-Warnungen prüfen (nur einmal beim App-Start)
    if 'warnings_checked' not in st.session_state:
        st.session_state.warnings_checked = True
        try:
            check_7_day_warnings()
        except:
            pass  # Fehler beim ersten Start ignorieren
    
    # Fallback-Backup prüfen (nur einmal)
    if 'backup_checked' not in st.session_state:
        st.session_state.backup_checked = True
        try:
            st.session_state.backup_service.check_and_send_fallback_backup()
        except:
            pass  # Fehler ignorieren

def show_main_app():
    """Hauptanwendung mit Navigation und Tabs"""
    user = st.session_state.current_user
    
    # Header mit Benutzer-Info und Navigation
    col1, col2, col3 = st.columns([2, 3, 2])
    
    with col1:
        st.markdown(f"👋 **{user['name']}**")
        st.markdown(f"📧 {user['email']}")
    
    with col2:
        st.markdown("# 📅 Dienstplan+ Cloud v3.0")
    
    with col3:
        col3a, col3b = st.columns(2)
        with col3a:
            if st.button("👤 Profil", key="profile_btn"):
                st.session_state.show_profile = True
                st.rerun()
        
        with col3b:
            if st.button("🚪 Abmelden", key="logout_btn"):
                # Session bereinigen
                st.session_state.db.log_action(user['id'], 'logout', 'User logged out')
                st.session_state.current_user = None
                if 'show_profile' in st.session_state:
                    del st.session_state.show_profile
                st.rerun()
    
    st.markdown("---")
    
    # Profil-Overlay prüfen
    if st.session_state.get('show_profile', False):
        show_profile_page()
        return
    
    # Tab-Navigation (Team nur für Admins)
    if user['role'] == 'admin':
        tab_names = ["📅 Plan", "👤 Meine Schichten", "👥 Team", "⚙️ Admin", "ℹ️ Informationen"]
        tabs = st.tabs(tab_names)
    else:
        tab_names = ["📅 Plan", "👤 Meine Schichten", "ℹ️ Informationen"]
        tabs = st.tabs(tab_names)
    
    # Tab-Inhalte anzeigen
    with tabs[0]:
        show_schedule_tab()
    
    with tabs[1]:
        show_my_shifts_tab()
    
    if user['role'] == 'admin':
        with tabs[2]:
            show_team_tab()
        
        with tabs[3]:
            show_admin_tab()
        
        with tabs[4]:
            show_information_tab()
    else:
        with tabs[2]:
            show_information_tab()

def show_profile_page():
    """Profilseite mit Tests und Einstellungen"""
    from app.pages.auth import show_profile_page as show_profile_impl
    show_profile_impl()

def show_team_tab():
    """Team-Tab für Admins"""
    from app.pages.admin import show_team_tab as show_team_impl
    show_team_impl()

def main():
    """Hauptfunktion - App-Einstiegspunkt"""
    
    # CSS anwenden
    apply_css()
    
    # Session State initialisieren
    init_session_state()
    
    # Routing: Login oder Hauptapp
    if st.session_state.current_user is None:
        show_login()
    else:
        show_main_app()

if __name__ == "__main__":
    main()