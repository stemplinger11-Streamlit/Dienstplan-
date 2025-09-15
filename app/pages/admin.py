"""
Dienstplan+ Cloud v3.0 - Admin Pages
Team-Verwaltung, Umbuchungen, Backups und System-Management
"""
import streamlit as st
import json
from datetime import datetime, timedelta
from app.config.constants import WEEKLY_SLOTS
from app.core.helpers import (
    format_german_date, format_german_weekday, send_calendar_invite,
    is_holiday, is_closed_period, validate_booking_request
)
from app.ui.components import (
    admin_expander_header, info_card, render_stats_card, render_user_badge,
    success_message, error_message, warning_message
)

def show_team_tab():
    """Team-Übersicht für Admins"""
    
    user = st.session_state.current_user
    
    if user['role'] != 'admin':
        st.error("❌ Zugriff verweigert - Admin-Berechtigung erforderlich")
        return
    
    st.markdown("# 👥 Team-Verwaltung")
    
    # Team-Statistiken
    show_team_statistics()
    
    st.markdown("---")
    
    # Team-Mitglieder
    show_team_members()
    
    st.markdown("---")
    
    # Aktuelle Woche Übersicht
    show_current_week_overview()
    
    st.markdown("---")
    
    # Admin-Aktionen
    show_admin_actions()

def show_admin_tab():
    """Admin-Panel mit System-Funktionen"""
    
    user = st.session_state.current_user
    
    if user['role'] != 'admin':
        st.error("❌ Zugriff verweigert - Admin-Berechtigung erforderlich")
        return
    
    st.markdown("# ⚙️ System-Administration")
    
    # System-Status
    show_system_status()
    
    st.markdown("---")
    
    # Template-Editor
    show_template_editor()
    
    st.markdown("---")
    
    # Backup-Verwaltung
    show_backup_management()
    
    st.markdown("---")
    
    # Audit-Log
    show_audit_log()

def show_team_statistics():
    """Team-Statistiken Dashboard"""
    
    # Lade Team-Daten
    all_users = st.session_state.db.get_all_users()
    all_bookings = st.session_state.db.get_all_bookings()
    
    # Berechne Statistiken
    total_users = len(all_users)
    admin_users = len([u for u in all_users if u['role'] == 'admin'])
    active_bookings = len([b for b in all_bookings if datetime.strptime(b['date'], '%Y-%m-%d').date() >= datetime.now().date()])
    
    # Statistik-Karten
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        render_stats_card("Team-Mitglieder", str(total_users), f"{admin_users} Admins", "👥")
    
    with col2:
        render_stats_card("Aktive Buchungen", str(active_bookings), "Zukünftige Termine", "📅")
    
    with col3:
        # Buchungen diese Woche
        week_start = st.session_state.current_week_start
        week_end = week_start + timedelta(days=6)
        week_bookings = [
            b for b in all_bookings 
            if week_start <= datetime.strptime(b['date'], '%Y-%m-%d').date() <= week_end
        ]
        render_stats_card("Diese Woche", str(len(week_bookings)), "Gebuchte Termine", "📊")
    
    with col4:
        # SMS-Service Status
        sms_status = "Aktiv" if st.session_state.sms_service.enabled else "Inaktiv"
        email_status = "Aktiv" if st.session_state.email_service.enabled else "Inaktiv"
        render_stats_card("Services", f"{sms_status}", f"E-Mail: {email_status}", "🔧")

def show_team_members():
    """Team-Mitglieder Verwaltung"""
    
    all_users = st.session_state.db.get_all_users()
    
    header_text = admin_expander_header("👥 Team-Mitglieder", len(all_users))
    
    with st.expander(header_text, expanded=True):
        # Mitglieder-Liste
        for user in all_users:
            with st.container():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    render_user_badge(user['name'], user['role'], False)
                    st.markdown(f"""
📧 {user['email']}  
📱 {user['phone']}  
📅 Registriert: {user['created_at'][:10] if user['created_at'] else 'Unbekannt'}
""")
                
                with col2:
                    # SMS/E-Mail Status
                    sms_icon = "✅" if user.get('sms_opt_in', False) else "❌"
                    email_icon = "✅" if user.get('email_opt_in', True) else "❌"
                    st.markdown(f"""
**Benachrichtigungen:**  
📱 SMS: {sms_icon}  
📧 E-Mail: {email_icon}
""")
                
                with col3:
                    # Admin-Aktionen
                    if user['role'] != 'admin':
                        if st.button(
                            "👑 Zu Admin machen", 
                            key=f"promote_{user['id']}",
                            help="Benutzer zu Administrator ernennen"
                        ):
                            promote_user(user)
                    else:
                        if not user.get('is_initial_admin', False):
                            if st.button(
                                "👤 Admin entziehen", 
                                key=f"demote_{user['id']}",
                                help="Admin-Berechtigung entfernen"
                            ):
                                demote_user(user)
                
                st.markdown("---")

def show_current_week_overview():
    """Übersicht der aktuellen Woche"""
    
    week_start = st.session_state.current_week_start
    week_end = week_start + timedelta(days=6)
    kw = week_start.isocalendar()[1]
    
    header_text = admin_expander_header(
        f"📊 Aktuelle Woche (KW {kw})", 
        len(WEEKLY_SLOTS) * 1  # Dummy count
    )
    
    with st.expander(header_text, expanded=True):
        st.markdown(f"**Woche vom {format_german_date(week_start.strftime('%Y-%m-%d'))} bis {format_german_date(week_end.strftime('%Y-%m-%d'))}**")
        
        # Alle Slots für diese Woche prüfen
        for slot in WEEKLY_SLOTS:
            from app.core.helpers import get_slot_date
            date_str = get_slot_date(week_start, slot['day'])
            
            bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
            
            if bookings:
                booking = bookings[0]
                status = f"✅ {booking['user_name']}"
            elif is_holiday(date_str):
                status = "🎄 Feiertag"
            elif is_closed_period(date_str):
                status = "🏊‍♂️ Geschlossen"
            else:
                status = "❌ UNBESETZT"
            
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f"**{slot['day_name']}, {format_german_date(date_str)}**")
                st.markdown(f"{slot['start_time']} - {slot['end_time']} Uhr")
            
            with col2:
                st.markdown(f"**Status:** {status}")
            
            with col3:
                if bookings and not is_holiday(date_str) and not is_closed_period(date_str):
                    if st.button(
                        "🔄 Umbuchen", 
                        key=f"reschedule_{booking['id']}",
                        help="Schicht auf anderen User umbuchen"
                    ):
                        show_reschedule_dialog(booking, slot, date_str)

def show_admin_actions():
    """Admin-Aktionen Bereich"""
    
    header_text = admin_expander_header("⚡ Schnell-Aktionen", 0)
    
    with st.expander(header_text):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 7-Tage-Warnungen prüfen", help="Sofortige Prüfung auf unbelegte Schichten"):
                check_warnings_manually()
        
        with col2:
            if st.button("💾 Sofort-Backup erstellen", help="Backup erstellen und per E-Mail senden"):
                create_immediate_backup()
        
        with col3:
            if st.button("📊 System-Check", help="Vollständige System-Diagnose"):
                run_system_check()

def show_system_status():
    """System-Status Dashboard"""
    
    st.markdown("### 🔧 System-Status")
    
    # Service-Status prüfen
    validation = st.session_state.settings.validate_configuration()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ✅ Verfügbare Services")
        if validation['sms_available']:
            st.markdown("🟢 **SMS-Service** - Twilio verbunden")
        else:
            st.markdown("🔴 **SMS-Service** - Nicht konfiguriert")
        
        if validation['email_available']:
            st.markdown("🟢 **E-Mail-Service** - Gmail verbunden")
        else:
            st.markdown("🔴 **E-Mail-Service** - Nicht konfiguriert")
        
        if validation['backup_available']:
            st.markdown("🟢 **Auto-Backup** - Täglich 20:00 Uhr")
        else:
            st.markdown("🔴 **Auto-Backup** - Nicht verfügbar")
        
        if validation['calendar_available']:
            st.markdown("🟢 **Kalender-Einladungen** - Aktiv")
        else:
            st.markdown("🔴 **Kalender-Einladungen** - Deaktiviert")
    
    with col2:
        st.markdown("#### ⚠️ Warnungen & Probleme")
        
        if validation['warnings']:
            for warning in validation['warnings']:
                st.warning(f"⚠️ {warning}")
        
        if validation['critical_issues']:
            for issue in validation['critical_issues']:
                st.error(f"🚨 {issue}")
        
        if not validation['warnings'] and not validation['critical_issues']:
            st.success("✅ Alle Systeme funktional")

def show_template_editor():
    """Template-Editor für SMS/E-Mail"""
    
    st.markdown("### 📝 Nachrichten-Vorlagen")
    
    tab1, tab2 = st.tabs(["📱 SMS-Templates", "📧 E-Mail-Templates"])
    
    with tab1:
        edit_sms_templates()
    
    with tab2:
        edit_email_templates()

def edit_sms_templates():
    """SMS-Template Editor"""
    
    # Lade aktuelle SMS-Templates
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM reminder_templates WHERE active = 1 ORDER BY name')
    templates = cursor.fetchall()
    conn.close()
    
    for template in templates:
        template_id, name, timing, sms_template, _, _, active = template
        
        with st.expander(f"📱 {name}", expanded=False):
            new_template = st.text_area(
                "SMS-Text:",
                value=sms_template or "",
                key=f"sms_template_{template_id}",
                help="Verfügbare Variablen: {{name}}, {{datum}}, {{slot}}"
            )
            
            if st.button(f"💾 Speichern", key=f"save_sms_{template_id}"):
                save_sms_template(template_id, new_template)

def edit_email_templates():
    """E-Mail-Template Editor"""
    
    # Lade aktuelle E-Mail-Templates
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM email_templates WHERE active = 1 ORDER BY name')
    templates = cursor.fetchall()
    conn.close()
    
    for template in templates:
        template_id, name, template_type, subject_template, body_template, active = template
        
        with st.expander(f"📧 {name}", expanded=False):
            new_subject = st.text_input(
                "Betreff:",
                value=subject_template or "",
                key=f"email_subject_{template_id}",
                help="Verfügbare Variablen: {{name}}, {{datum}}, {{slot}}"
            )
            
            new_body = st.text_area(
                "E-Mail-Text:",
                value=body_template or "",
                key=f"email_body_{template_id}",
                height=150,
                help="Verfügbare Variablen: {{name}}, {{datum}}, {{slot}}"
            )
            
            if st.button(f"💾 Speichern", key=f"save_email_{template_id}"):
                save_email_template(template_id, new_subject, new_body)

def show_backup_management():
    """Backup-Verwaltung"""
    
    st.markdown("### 💾 Backup-Verwaltung")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📥 Backup erstellen")
        
        if st.button("🔽 Vollständiges Backup herunterladen", type="primary"):
            create_download_backup()
    
    with col2:
        st.markdown("#### 📤 Backup wiederherstellen")
        
        uploaded_file = st.file_uploader(
            "Backup-ZIP-Datei auswählen:",
            type=['zip'],
            key="restore_backup_file",
            help="⚠️ WARNUNG: Überschreibt alle aktuellen Daten!"
        )
        
        if uploaded_file is not None:
            if st.button("⚠️ RESTORE - Alle Daten ersetzen", type="secondary"):
                restore_from_upload(uploaded_file)

def show_audit_log():
    """Audit-Log Ansicht"""
    
    st.markdown("### 📋 Audit-Log (Letzte 100 Einträge)")
    
    logs = st.session_state.db.get_audit_log(100)
    
    if not logs:
        st.info("📝 Noch keine Log-Einträge vorhanden")
        return
    
    # Log-Einträge anzeigen
    for log in logs:
        timestamp = datetime.fromisoformat(log['timestamp']).strftime('%d.%m.%Y %H:%M:%S')
        user_name = log['user_name'] or "System"
        
        # CSS-Klasse basierend auf Action-Typ
        if log['action'].startswith('admin'):
            css_class = "admin-action"
        elif log['action'].startswith('system'):
            css_class = "system-action"
        else:
            css_class = "user-action"
        
        log_html = f"""
        <div class="audit-entry {css_class}">
            <strong>{timestamp}</strong> | {user_name} | {log['action']}
            <br><small>{log['details']}</small>
        </div>
        """
        
        st.markdown(log_html, unsafe_allow_html=True)

# Helper Functions
def promote_user(user):
    """Benutzer zu Admin ernennen"""
    success = st.session_state.db.update_user_role(user['id'], 'admin')
    if success:
        success_message(f"✅ {user['name']} wurde zu Administrator ernannt")
        st.rerun()
    else:
        error_message("❌ Fehler beim Ernennen")

def demote_user(user):
    """Admin-Berechtigung entziehen"""
    success = st.session_state.db.update_user_role(user['id'], 'user')
    if success:
        success_message(f"✅ {user['name']} ist jetzt normaler Benutzer")
        st.rerun()
    else:
        error_message("❌ Fehler beim Entziehen der Berechtigung")

def save_sms_template(template_id, new_template):
    """SMS-Template speichern"""
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'UPDATE reminder_templates SET sms_template = ? WHERE id = ?',
        (new_template, template_id)
    )
    conn.commit()
    conn.close()
    
    success_message("✅ SMS-Template gespeichert")

def save_email_template(template_id, new_subject, new_body):
    """E-Mail-Template speichern"""
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'UPDATE email_templates SET subject_template = ?, body_template = ? WHERE id = ?',
        (new_subject, new_body, template_id)
    )
    conn.commit()
    conn.close()
    
    success_message("✅ E-Mail-Template gespeichert")

def create_download_backup():
    """Backup für Download erstellen"""
    backup_data = st.session_state.backup_service.create_manual_backup()
    
    if backup_data:
        filename = f"dienstplan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        st.download_button(
            label="📥 Backup-Datei herunterladen",
            data=backup_data,
            file_name=filename,
            mime="application/zip"
        )
        
        success_message("✅ Backup erfolgreich erstellt")
    else:
        error_message("❌ Fehler beim Erstellen des Backups")

def restore_from_upload(uploaded_file):
    """Backup wiederherstellen"""
    warning_message("⚠️ Diese Funktion würde alle Daten überschreiben - aus Sicherheitsgründen nur über Admin-Konsole verfügbar")

def check_warnings_manually():
    """Manuelle 7-Tage-Warnungen prüfen"""
    from app.core.helpers import check_7_day_warnings
    
    try:
        check_7_day_warnings()
        success_message("✅ 7-Tage-Warnungen geprüft - SMS gesendet falls nötig")
    except Exception as e:
        error_message(f"❌ Fehler beim Prüfen: {str(e)}")

def create_immediate_backup():
    """Sofortiges Backup erstellen"""
    try:
        success = st.session_state.backup_service.send_daily_backup()
        if success:
            success_message("✅ Backup erstellt und per E-Mail gesendet")
        else:
            error_message("❌ Backup-Fehler - E-Mail nicht gesendet")
    except Exception as e:
        error_message(f"❌ Backup-Fehler: {str(e)}")

def run_system_check():
    """Vollständige System-Diagnose"""
    validation = st.session_state.settings.validate_configuration()
    
    issues_found = len(validation['critical_issues']) + len(validation['warnings'])
    
    if issues_found == 0:
        success_message("✅ System-Check bestanden - Alle Services funktionsfähig")
    else:
        warning_message(f"⚠️ System-Check: {issues_found} Problem(e) gefunden - Details siehe System-Status")

def show_reschedule_dialog(booking, slot, date_str):
    """Dialog für Admin-Umbuchung"""
    st.markdown("### 🔄 Schicht umbuchen")
    
    # Alle Users laden (außer dem aktuellen)
    all_users = st.session_state.db.get_all_users()
    available_users = [u for u in all_users if u['id'] != booking['user_id']]
    
    if not available_users:
        error_message("❌ Keine anderen Benutzer verfügbar")
        return
    
    # Ziel-User auswählen
    user_options = [f"{u['name']} ({u['email']})" for u in available_users]
    selected_user_index = st.selectbox(
        "Neuen Benutzer auswählen:",
        range(len(user_options)),
        format_func=lambda x: user_options[x],
        key=f"reschedule_user_{booking['id']}"
    )
    
    target_user = available_users[selected_user_index]
    
    # Optional: Neues Datum/Slot
    change_date = st.checkbox("📅 Datum/Slot ändern", key=f"change_date_{booking['id']}")
    
    new_slot_id = slot['id']
    new_date = date_str
    
    if change_date:
        new_date = st.date_input(
            "Neues Datum:",
            value=datetime.strptime(date_str, '%Y-%m-%d').date(),
            key=f"new_date_{booking['id']}"
        ).strftime('%Y-%m-%d')
        
        slot_options = [f"{s['day_name']} {s['start_time']}-{s['end_time']}" for s in WEEKLY_SLOTS]
        selected_slot_index = st.selectbox(
            "Neuer Slot:",
            range(len(WEEKLY_SLOTS)),
            format_func=lambda x: slot_options[x],
            key=f"new_slot_{booking['id']}"
        )
        
        new_slot_id = WEEKLY_SLOTS[selected_slot_index]['id']
        new_slot = WEEKLY_SLOTS[selected_slot_index]
    else:
        new_slot = slot
    
    # Umbuchung ausführen
    if st.button(f"✅ Umbuchen auf {target_user['name']}", key=f"confirm_reschedule_{booking['id']}", type="primary"):
        perform_admin_reschedule(booking, target_user, new_slot, new_date)

def perform_admin_reschedule(old_booking, target_user, new_slot, new_date):
    """Führt Admin-Umbuchung durch"""
    
    # 1. Validierung
    validation_errors = validate_booking_request(target_user['id'], new_slot['id'], new_date)
    
    if validation_errors:
        for error in validation_errors:
            error_message(error)
        return
    
    # 2. ICS CANCEL an alten User
    old_user = st.session_state.db.get_user_by_id(old_booking['user_id'])
    if old_user and st.session_state.email_service.enabled:
        cancel_success, _ = send_calendar_invite(
            old_user, old_booking, new_slot, method="CANCEL"
        )
    
    # 3. Alte Buchung löschen
    delete_success = st.session_state.db.cancel_booking(old_booking['id'])
    
    if not delete_success:
        error_message("❌ Fehler beim Löschen der alten Buchung")
        return
    
    # 4. Neue Buchung erstellen
    create_success, new_booking_id = st.session_state.db.create_booking(
        target_user['id'], new_slot['id'], new_date
    )
    
    if not create_success:
        error_message(f"❌ Fehler beim Erstellen der neuen Buchung: {new_booking_id}")
        return
    
    # 5. ICS REQUEST an neuen User
    if st.session_state.email_service.enabled:
        new_booking_data = {
            'id': new_booking_id,
            'date': new_date,
            'user_id': target_user['id']
        }
        
        invite_success, _ = send_calendar_invite(
            target_user, new_booking_data, new_slot, method="REQUEST"
        )
    
    # 6. Audit-Log
    details = f"Rescheduled from {old_user['name'] if old_user else 'Unknown'} to {target_user['name']} for {new_date}"
    st.session_state.db.log_action(
        st.session_state.current_user['id'], 
        'admin_rescheduled', 
        details
    )
    
    success_message(f"✅ Schicht erfolgreich umgebucht auf {target_user['name']}")
    st.rerun()