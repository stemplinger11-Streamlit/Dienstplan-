"""
Dienstplan+ Cloud v3.0 - Authentication Pages
Login, Registrierung und Profil-Management
"""
import streamlit as st
from datetime import datetime
from app.core.helpers import get_current_week_start, send_test_sms, send_test_email

def show_login():
    """Zeigt Login- und Registrierungs-Interface"""
    
    st.markdown("# 🔐 Willkommen bei Dienstplan+ Cloud")
    st.markdown("**Professionelle Dienstplanung für Ihr Team**")
    
    tab1, tab2 = st.tabs(["🔑 Anmelden", "📝 Registrieren"])
    
    with tab1:
        show_login_form()
    
    with tab2:
        show_registration_form()

def show_login_form():
    """Login-Formular"""
    
    with st.form("login_form", clear_on_submit=False):
        st.markdown("### 🔑 Anmelden")
        
        email = st.text_input(
            "📧 E-Mail Adresse", 
            placeholder="ihre.email@beispiel.de",
            key="login_email"
        )
        
        password = st.text_input(
            "🔒 Passwort", 
            type="password",
            key="login_password"
        )
        
        # Login-Button zentriert
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            login_submitted = st.form_submit_button("Anmelden", type="primary", use_container_width=True)
        
        if login_submitted:
            if not email or not password:
                st.error("❌ Bitte alle Felder ausfüllen")
                return
            
            # Authentifizierung versuchen
            user = st.session_state.db.authenticate_user(email, password)
            
            if user:
                # Erfolgreiche Anmeldung
                st.session_state.current_user = user
                
                # Session-State initialisieren
                st.session_state.current_week_start = get_current_week_start()
                st.session_state.show_profile = False
                
                # Audit-Log
                st.session_state.db.log_action(
                    user['id'], 
                    'login', 
                    f'User logged in from web interface'
                )
                
                st.success(f"✅ Willkommen, {user['name']}! 🎉")
                st.rerun()
                
            else:
                st.error("❌ Ungültige Anmeldedaten")

def show_registration_form():
    """Registrierungs-Formular"""
    
    with st.form("register_form", clear_on_submit=False):
        st.markdown("### 👥 Neuen Account erstellen")
        
        reg_name = st.text_input(
            "👤 Vollständiger Name", 
            placeholder="Max Mustermann",
            key="reg_name"
        )
        
        reg_email = st.text_input(
            "📧 E-Mail Adresse", 
            placeholder="max@beispiel.de",
            key="reg_email"
        )
        
        reg_phone = st.text_input(
            "📱 Telefonnummer", 
            placeholder="+49 151 12345678",
            help="Diese Nummer wird für Notfälle und automatische Erinnerungen verwendet.",
            key="reg_phone"
        )
        
        reg_password = st.text_input(
            "🔒 Passwort", 
            type="password",
            help="Mindestens 6 Zeichen",
            key="reg_password"
        )
        
        reg_password_confirm = st.text_input(
            "🔒 Passwort wiederholen", 
            type="password",
            key="reg_password_confirm"
        )
        
        # SMS-Opt-in
        sms_consent = st.checkbox(
            "📱 SMS-Erinnerungen erhalten (empfohlen)",
            value=True,
            help="Sie erhalten automatische Erinnerungen 24h und 1h vor Ihren Schichten.",
            key="reg_sms_consent"
        )
        
        # Registrierung-Button zentriert
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            register_submitted = st.form_submit_button("Account erstellen", type="primary", use_container_width=True)
        
        if register_submitted:
            # Validierung
            validation_errors = []
            
            if not all([reg_name, reg_email, reg_phone, reg_password, reg_password_confirm]):
                validation_errors.append("Bitte alle Felder ausfüllen")
            
            if reg_password != reg_password_confirm:
                validation_errors.append("Passwörter stimmen nicht überein")
            
            if len(reg_password) < 6:
                validation_errors.append("Passwort muss mindestens 6 Zeichen lang sein")
            
            if not reg_phone.startswith('+'):
                validation_errors.append("Telefonnummer muss mit Ländercode beginnen (z.B. +49)")
            
            if '@' not in reg_email or '.' not in reg_email:
                validation_errors.append("Ungültige E-Mail-Adresse")
            
            # Fehler anzeigen
            if validation_errors:
                for error in validation_errors:
                    st.error(f"❌ {error}")
                return
            
            # Benutzer erstellen
            user_id = st.session_state.db.create_user(
                email=reg_email,
                phone=reg_phone,
                name=reg_name,
                password=reg_password
            )
            
            if user_id:
                # SMS-Opt-in aktualisieren
                if sms_consent:
                    conn = st.session_state.db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET sms_opt_in = 1 WHERE id = ?', (user_id,))
                    conn.commit()
                    conn.close()
                
                # Automatisches Login nach Registrierung
                user = st.session_state.db.authenticate_user(reg_email, reg_password)
                if user:
                    st.session_state.current_user = user
                    st.session_state.current_week_start = get_current_week_start()
                    st.session_state.show_profile = False
                    
                    # Audit-Log
                    st.session_state.db.log_action(
                        user_id, 
                        'account_created', 
                        f'New user registered and auto-logged in: {reg_name}'
                    )
                    
                    st.success("✅ Account erfolgreich erstellt! Sie sind automatisch eingeloggt.")
                    st.balloons()
                    st.rerun()
            else:
                st.error("❌ E-Mail bereits registriert")

def show_profile_page():
    """Profil-Management-Seite"""
    
    user = st.session_state.current_user
    
    # Header mit Zurück-Button
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.button("⬅️ Zurück", key="profile_back"):
            st.session_state.show_profile = False
            st.rerun()
    
    with col2:
        st.markdown("# 👤 Mein Profil")
    
    st.markdown("---")
    
    # Profil-Informationen in zwei Spalten
    col1, col2 = st.columns([1, 1])
    
    with col1:
        show_profile_editor(user)
    
    with col2:
        show_password_changer(user)
    
    st.markdown("---")
    
    # Test-Funktionen
    show_service_tests(user)
    
    st.markdown("---")
    
    # Account-Informationen
    show_account_info(user)

def show_profile_editor(user):
    """Profil-Editor Bereich"""
    
    st.markdown("### 📝 Profil-Daten")
    
    with st.form("profile_form"):
        new_name = st.text_input("👤 Name", value=user['name'])
        
        new_phone = st.text_input(
            "📱 Telefonnummer", 
            value=user['phone'],
            help="Wird für Notfälle und automatische Erinnerungen verwendet"
        )
        
        sms_opt_in = st.checkbox(
            "📱 SMS-Erinnerungen erhalten", 
            value=user.get('sms_opt_in', False),
            help="Sie erhalten automatische Erinnerungen 24h und 1h vor Ihren Schichten"
        )
        
        profile_submitted = st.form_submit_button("💾 Profil speichern", type="primary")
        
        if profile_submitted:
            if not new_name or not new_phone:
                st.error("❌ Name und Telefonnummer sind erforderlich")
                return
            
            if not new_phone.startswith('+'):
                st.error("❌ Telefonnummer muss mit Ländercode beginnen")
                return
            
            # Profil aktualisieren
            success = st.session_state.db.update_user_profile(
                user['id'], new_name, new_phone, sms_opt_in
            )
            
            if success:
                # Session State aktualisieren
                st.session_state.current_user['name'] = new_name
                st.session_state.current_user['phone'] = new_phone
                st.session_state.current_user['sms_opt_in'] = sms_opt_in
                
                st.success("✅ Profil erfolgreich aktualisiert!")
                st.rerun()
            else:
                st.error("❌ Fehler beim Aktualisieren des Profils")

def show_password_changer(user):
    """Passwort-Änderung Bereich"""
    
    st.markdown("### 🔒 Passwort ändern")
    
    with st.form("password_form"):
        current_password = st.text_input("Aktuelles Passwort", type="password")
        new_password = st.text_input("Neues Passwort", type="password")
        confirm_password = st.text_input("Neues Passwort bestätigen", type="password")
        
        password_submitted = st.form_submit_button("🔑 Passwort ändern", type="primary")
        
        if password_submitted:
            # Validierung
            if not all([current_password, new_password, confirm_password]):
                st.error("❌ Bitte alle Felder ausfüllen")
                return
            
            if new_password != confirm_password:
                st.error("❌ Neue Passwörter stimmen nicht überein")
                return
            
            if len(new_password) < 6:
                st.error("❌ Neues Passwort muss mindestens 6 Zeichen lang sein")
                return
            
            # Aktuelles Passwort prüfen
            current_user_check = st.session_state.db.authenticate_user(user['email'], current_password)
            
            if not current_user_check:
                st.error("❌ Aktuelles Passwort ist falsch")
                return
            
            # Passwort ändern
            success = st.session_state.db.update_user_password(user['id'], new_password)
            
            if success:
                st.success("✅ Passwort erfolgreich geändert!")
                
                # Admin-Fehlerlogging deaktiviert (kein Fehler)
                st.session_state.db.log_action(
                    user['id'], 
                    'password_changed_profile', 
                    'User successfully changed password via profile'
                )
            else:
                st.error("❌ Fehler beim Ändern des Passworts")
                
                # Admin-Fehlerlogging
                st.session_state.db.log_action(
                    user['id'], 
                    'password_change_failed', 
                    'Password change failed in profile'
                )

def show_service_tests(user):
    """Service-Test Bereich"""
    
    st.markdown("### 🧪 Service-Tests")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📱 SMS-Test")
        
        if st.session_state.sms_service.enabled:
            sms_status = "🟢 SMS-Service verfügbar"
        else:
            sms_status = "🔴 SMS-Service nicht konfiguriert"
        
        st.markdown(f"**Status:** {sms_status}")
        
        if st.button("📤 Test-SMS senden", key="test_sms_btn", use_container_width=True):
            if not st.session_state.sms_service.enabled:
                st.error("❌ SMS-Service ist nicht verfügbar")
                
                # Admin-Fehlerlogging
                st.session_state.db.log_action(
                    user['id'], 
                    'test_sms_failed', 
                    'User tried to send test SMS but service disabled'
                )
                
            else:
                success, result = send_test_sms(user)
                
                if success:
                    st.success(f"✅ Test-SMS gesendet an {user['phone']}")
                    st.session_state.db.log_action(
                        user['id'], 
                        'test_sms_sent', 
                        f'Test SMS sent successfully to {user["phone"]}'
                    )
                else:
                    st.error(f"❌ SMS-Fehler: {result}")
                    
                    # Admin-Fehlerlogging
                    st.session_state.db.log_action(
                        user['id'], 
                        'test_sms_error', 
                        f'Test SMS failed: {result}'
                    )
    
    with col2:
        st.markdown("#### 📧 E-Mail-Test")
        
        if st.session_state.email_service.enabled:
            email_status = "🟢 E-Mail-Service verfügbar"
        else:
            email_status = "🔴 E-Mail-Service nicht konfiguriert"
        
        st.markdown(f"**Status:** {email_status}")
        
        if st.button("📤 Test-E-Mail senden", key="test_email_btn", use_container_width=True):
            if not st.session_state.email_service.enabled:
                st.error("❌ E-Mail-Service ist nicht verfügbar")
                
                # Admin-Fehlerlogging
                st.session_state.db.log_action(
                    user['id'], 
                    'test_email_failed', 
                    'User tried to send test email but service disabled'
                )
                
            else:
                success, result = send_test_email(user)
                
                if success:
                    st.success(f"✅ Test-E-Mail gesendet an {user['email']}")
                    st.session_state.db.log_action(
                        user['id'], 
                        'test_email_sent', 
                        f'Test email sent successfully to {user["email"]}'
                    )
                else:
                    st.error(f"❌ E-Mail-Fehler: {result}")
                    
                    # Admin-Fehlerlogging
                    st.session_state.db.log_action(
                        user['id'], 
                        'test_email_error', 
                        f'Test email failed: {result}'
                    )

def show_account_info(user):
    """Account-Informationen anzeigen"""
    
    st.markdown("### ℹ️ Account-Informationen")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
**👤 Name:** {user['name']}

**📧 E-Mail:** {user['email']}

**📱 Telefon:** {user['phone']}

**🎭 Rolle:** {user['role'].title()}
""")
    
    with col2:
        # SMS/E-Mail Einstellungen
        sms_status = "✅ Aktiviert" if user.get('sms_opt_in', False) else "❌ Deaktiviert"
        email_status = "✅ Aktiviert" if user.get('email_opt_in', True) else "❌ Deaktiviert"
        
        st.markdown(f"""
**📱 SMS:** {sms_status}

**📧 E-Mail:** {email_status}

**🕒 Registriert:** {user.get('created_at', 'Unbekannt')}

**🎯 Status:** {'🟢 Aktiv' if user.get('active', True) else '🔴 Inaktiv'}
""")
    
    # Service-Status-Übersicht
    st.markdown("#### 🔧 Service-Status")
    
    services_status = []
    
    if st.session_state.sms_service.enabled:
        services_status.append("🟢 SMS-Service")
    else:
        services_status.append("🔴 SMS-Service")
    
    if st.session_state.email_service.enabled:
        services_status.append("🟢 E-Mail-Service")
    else:
        services_status.append("🔴 E-Mail-Service")
    
    if st.session_state.backup_service.scheduler_running:
        services_status.append("🟢 Auto-Backup")
    else:
        services_status.append("🔴 Auto-Backup")
    
    st.markdown(" | ".join(services_status))