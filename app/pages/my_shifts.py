"""
Dienstplan+ Cloud v3.0 - My Shifts Pages  
Watchlist, eigene Schichten und Export-Funktionen
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.config.constants import WEEKLY_SLOTS
from app.core.helpers import (
    format_german_date, format_german_weekday, send_sick_notification, 
    send_calendar_invite, generate_ical_export
)
from app.ui.components import (
    info_card, admin_expander_header, success_message, error_message, warning_message
)

def show_my_shifts_tab():
    """Hauptansicht für Meine Schichten"""
    
    user = st.session_state.current_user
    
    st.markdown("# 👤 Meine Schichten")
    
    # Watchlist-Bereich
    show_watchlist_section(user)
    
    st.markdown("---")
    
    # Meine Schichten
    show_my_bookings_section(user)

def show_watchlist_section(user):
    """Watchlist/Favoriten-Bereich"""
    
    favorites = st.session_state.db.get_user_favorites(user['id'])
    
    header_text = admin_expander_header("⭐ Meine Watchlist", len(favorites))
    
    with st.expander(header_text, expanded=len(favorites) > 0):
        if not favorites:
            st.info("🔍 **Keine Termine in der Watchlist**")
            st.markdown("""
💡 **So funktioniert die Watchlist:**
1. Gehen Sie zum **📅 Plan**-Tab
2. Klicken Sie auf den **⭐ Stern** bei interessanten Terminen
3. Termine erscheinen hier mit Status-Updates
4. Buchen Sie direkt aus der Watchlist wenn verfügbar
""")
            return
        
        st.markdown("**📋 Beobachtete Termine:**")
        
        # Sortiere Favoriten nach Datum
        favorites_sorted = sorted(favorites, key=lambda x: x['date'])
        
        for favorite in favorites_sorted:
            show_watchlist_item(favorite, user)

def show_watchlist_item(favorite, user):
    """Einzelner Watchlist-Eintrag"""
    
    # Slot-Info laden
    slot = next((s for s in WEEKLY_SLOTS if s['id'] == favorite['slot_id']), None)
    if not slot:
        return
    
    date_str = favorite['date']
    
    # Prüfe aktuellen Status
    bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
    is_booked = len(bookings) > 0
    
    # Status-spezifisches Styling
    if is_booked:
        status_text = "❌ Belegt"
        status_variant = "warning"
        booking_user = bookings[0]['user_name'] if bookings else "Unbekannt"
        status_detail = f"von {booking_user}"
    else:
        # Prüfe ob noch buchbar (nicht in Vergangenheit)
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        if date_obj < datetime.now().date():
            status_text = "⏰ Vorbei"
            status_variant = "info"
            status_detail = "Termin liegt in der Vergangenheit"
        else:
            status_text = "✅ Verfügbar"
            status_variant = "success"
            status_detail = "Kann jetzt gebucht werden!"
    
    # Container für Watchlist-Item
    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"""
**{format_german_weekday(date_str)}, {format_german_date(date_str)}**  
🕒 {slot['start_time']} - {slot['end_time']} Uhr  
📍 {slot['day_name']}-Schicht  
📊 Status: {status_text} {status_detail}
""")
        
        with col2:
            # Action-Button je nach Status
            if not is_booked and datetime.strptime(date_str, '%Y-%m-%d').date() >= datetime.now().date():
                if st.button(
                    "📝 Jetzt buchen",
                    key=f"book_from_watchlist_{favorite['id']}",
                    type="primary",
                    use_container_width=True
                ):
                    book_from_watchlist(user, slot, date_str, favorite['id'])
            else:
                if st.button(
                    "👁️ In Plan zeigen",
                    key=f"show_from_watchlist_{favorite['id']}",
                    use_container_width=True
                ):
                    jump_to_week(date_str)
        
        with col3:
            # Entfernen-Button
            if st.button(
                "🗑️ Entfernen",
                key=f"remove_watchlist_{favorite['id']}",
                help="Aus Watchlist entfernen",
                use_container_width=True
            ):
                remove_from_watchlist(user, favorite)

def show_my_bookings_section(user):
    """Meine gebuchten Schichten"""
    
    bookings = st.session_state.db.get_user_bookings(user['id'])
    
    st.markdown("## 📅 Meine Schichten")
    
    if not bookings:
        info_card(
            title="📝 Noch keine Schichten gebucht",
            lines=[
                "Gehen Sie zum **📅 Plan**-Tab um Schichten zu buchen",
                "Oder fügen Sie interessante Termine zur **⭐ Watchlist** hinzu"
            ],
            variant="info"
        )
        return
    
    # Filter-Optionen
    filter_mode = st.radio(
        "📊 Anzeigen:",
        ["🔮 Kommende", "📋 Alle", "📜 Vergangene"],
        horizontal=True,
        key="booking_filter"
    )
    
    # Filtere Buchungen
    today = datetime.now().date()
    filtered_bookings = []
    
    for booking in bookings:
        booking_date = datetime.strptime(booking['date'], '%Y-%m-%d').date()
        
        if filter_mode == "🔮 Kommende" and booking_date >= today:
            filtered_bookings.append(booking)
        elif filter_mode == "📜 Vergangene" and booking_date < today:
            filtered_bookings.append(booking)
        elif filter_mode == "📋 Alle":
            filtered_bookings.append(booking)
    
    if not filtered_bookings:
        st.info(f"🔍 Keine Schichten in Kategorie '{filter_mode}' gefunden")
        return
    
    # Export-Buttons
    show_export_buttons(filtered_bookings, user, filter_mode.split()[1])
    
    st.markdown("---")
    
    # Buchungen anzeigen
    for booking in filtered_bookings:
        show_booking_card(booking, user)

def show_export_buttons(bookings, user, filter_type):
    """Export-Optionen für Schichten"""
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        # iCal Export
        if st.button("📅 iCal Export", help="Für Kalender-Apps (Outlook, Apple, Google)"):
            export_ical(bookings, user, filter_type)
    
    with col2:
        # CSV Export
        if st.button("📊 CSV Export", help="Für Excel und Spreadsheets"):
            export_csv(bookings, user, filter_type)

def show_booking_card(booking, user):
    """Einzelne Buchungs-Karte"""
    
    # Slot-Info laden
    slot = next((s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id']), None)
    if not slot:
        return
    
    date_str = booking['date']
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    is_past = date_obj < datetime.now().date()
    is_today = date_obj == datetime.now().date()
    
    # Status-Badge
    if is_past:
        status_badge = "✅ Erledigt"
        card_variant = "info"
    elif is_today:
        status_badge = "🕐 Heute"
        card_variant = "warning"
    else:
        days_until = (date_obj - datetime.now().date()).days
        status_badge = f"📅 In {days_until} Tag{'en' if days_until != 1 else ''}"
        card_variant = "success"
    
    # Container für Buchung
    with st.container():
        col1, col2 = st.columns([2, 1])
        
        with col1:
            info_card(
                title=f"{format_german_weekday(date_str)}, {format_german_date(date_str)}",
                lines=[
                    f"**{slot['day_name']}-Schicht:** {slot['start_time']} - {slot['end_time']} Uhr",
                    f"**Status:** {status_badge}",
                    f"**Gebucht:** {datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M')}"
                ],
                variant=card_variant
            )
        
        with col2:
            # Action-Buttons
            if not is_past:
                # Krankmeldung nur für zukünftige Termine
                if st.button(
                    "🤒 Krank melden",
                    key=f"sick_{booking['id']}",
                    help="Schicht stornieren und Team benachrichtigen",
                    use_container_width=True
                ):
                    report_sick(user, booking, slot)
                
                # Storno-Button
                if st.button(
                    "❌ Stornieren",
                    key=f"cancel_{booking['id']}",
                    help="Normale Stornierung ohne Krankmeldung",
                    use_container_width=True
                ):
                    cancel_booking_normal(user, booking, slot, date_str)
            else:
                st.markdown("*Schicht abgeschlossen*")

def book_from_watchlist(user, slot, date_str, favorite_id):
    """Bucht Schicht direkt aus der Watchlist"""
    
    from app.core.helpers import validate_booking_request
    
    # Validierung
    validation_errors = validate_booking_request(user['id'], slot['id'], date_str)
    
    if validation_errors:
        for error in validation_errors:
            error_message(error)
        return
    
    # Buchung erstellen
    success, result = st.session_state.db.create_booking(user['id'], slot['id'], date_str)
    
    if success:
        booking_id = result
        success_message(f"✅ Schicht erfolgreich gebucht für {format_german_date(date_str)}")
        
        # Kalender-Einladung senden
        if st.session_state.email_service.enabled:
            booking_data = {
                'id': booking_id,
                'date': date_str,
                'user_id': user['id']
            }
            
            invite_success, _ = send_calendar_invite(user, booking_data, slot, method="REQUEST")
            if invite_success:
                success_message("📧 Kalender-Einladung wurde gesendet")
        
        # Favorit entfernen (automatisch nach Buchung)
        st.session_state.db.remove_favorite(user['id'], slot['id'], date_str)
        
        st.rerun()
    else:
        error_message(f"❌ Buchung fehlgeschlagen: {result}")

def remove_from_watchlist(user, favorite):
    """Entfernt Termin aus Watchlist"""
    
    success = st.session_state.db.remove_favorite(
        user['id'], favorite['slot_id'], favorite['date']
    )
    
    if success:
        success_message("🗑️ Aus Watchlist entfernt")
        st.rerun()
    else:
        error_message("❌ Fehler beim Entfernen")

def jump_to_week(date_str):
    """Springt zur Woche des angegebenen Datums"""
    
    from app.core.helpers import get_week_start
    
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    week_start = get_week_start(date_obj)
    
    st.session_state.current_week_start = week_start
    success_message(f"🗓️ Zur Woche vom {week_start.strftime('%d.%m.%Y')} gewechselt")
    
    # Kurze Verzögerung und dann zur Plan-Tab
    st.info("💡 Wechseln Sie zum **📅 Plan**-Tab um die Woche zu sehen")

def report_sick(user, booking, slot):
    """Krankmeldung - storniert und benachrichtigt Admins"""
    
    date_str = booking['date']
    
    # Bestätigungsdialog
    if f"confirm_sick_{booking['id']}" not in st.session_state:
        st.session_state[f"confirm_sick_{booking['id']}"] = False
    
    if not st.session_state[f"confirm_sick_{booking['id']}"]:
        warning_message("""
⚠️ **Krankmeldung bestätigen**

Dies wird folgende Aktionen ausführen:
- ❌ Ihre Buchung stornieren
- 📧 Kalender-Absage senden  
- 📱 Admin-Team per SMS benachrichtigen
- 📋 Kollegen können die Schicht wieder buchen

Diese Aktion kann nicht rückgängig gemacht werden.
""")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "✅ Krankmeldung bestätigen",
                key=f"confirm_sick_yes_{booking['id']}",
                type="primary"
            ):
                st.session_state[f"confirm_sick_{booking['id']}"] = True
                st.rerun()
        
        with col2:
            if st.button(
                "❌ Abbrechen", 
                key=f"confirm_sick_no_{booking['id']}"
            ):
                st.info("Krankmeldung abgebrochen")
        
        return
    
    # Krankmeldung durchführen
    # 1. Buchung stornieren
    cancel_success = st.session_state.db.cancel_booking(booking['id'], user['id'])
    
    if not cancel_success:
        error_message("❌ Fehler beim Stornieren der Buchung")
        return
    
    # 2. ICS CANCEL senden
    if st.session_state.email_service.enabled:
        booking_data = {
            'id': booking['id'],
            'date': date_str,
            'user_id': user['id']
        }
        
        cancel_success, _ = send_calendar_invite(user, booking_data, slot, method="CANCEL")
        
        if cancel_success:
            success_message("📧 Kalender-Absage wurde gesendet")
    
    # 3. Admin-SMS senden
    sms_results = send_sick_notification(user, slot['id'], date_str)
    
    if sms_results:
        successful_sms = sum(1 for result in sms_results if result.get('success', False))
        if successful_sms > 0:
            success_message(f"📱 {successful_sms} Administratoren wurden per SMS benachrichtigt")
        else:
            warning_message("⚠️ SMS-Benachrichtigung fehlgeschlagen - Admins wurden nicht informiert")
    
    # 4. Session State bereinigen
    if f"confirm_sick_{booking['id']}" in st.session_state:
        del st.session_state[f"confirm_sick_{booking['id']}"]
    
    success_message(f"🤒 Krankmeldung erfolgreich für {format_german_date(date_str)}")
    st.rerun()

def cancel_booking_normal(user, booking, slot, date_str):
    """Normale Stornierung ohne Krankmeldung"""
    
    # Buchung stornieren
    success = st.session_state.db.cancel_booking(booking['id'], user['id'])
    
    if success:
        success_message(f"✅ Buchung storniert für {format_german_date(date_str)}")
        
        # ICS CANCEL senden
        if st.session_state.email_service.enabled:
            booking_data = {
                'id': booking['id'],
                'date': date_str,
                'user_id': user['id']
            }
            
            cancel_success, _ = send_calendar_invite(user, booking_data, slot, method="CANCEL")
            
            if cancel_success:
                success_message("📧 Kalender-Absage wurde gesendet")
        
        st.rerun()
    else:
        error_message("❌ Stornierung fehlgeschlagen")

def export_ical(bookings, user, filter_type):
    """iCal-Export für Kalender-Apps"""
    
    if not bookings:
        warning_message("Keine Schichten zum Exportieren")
        return
    
    # iCal-Content generieren
    ical_content = generate_ical_export(bookings)
    
    # Download-Button
    filename = f"meine_schichten_{filter_type.lower()}_{datetime.now().strftime('%Y%m%d')}.ics"
    
    st.download_button(
        label="📥 iCal-Datei herunterladen",
        data=ical_content,
        file_name=filename,
        mime="text/calendar",
        help="Für Import in Outlook, Apple Calendar, Google Calendar etc."
    )
    
    success_message(f"📅 iCal-Export bereit: {len(bookings)} Termine")

def export_csv(bookings, user, filter_type):
    """CSV-Export für Spreadsheets"""
    
    if not bookings:
        warning_message("Keine Schichten zum Exportieren")
        return
    
    # DataFrame erstellen
    export_data = []
    
    for booking in bookings:
        slot = next((s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id']), None)
        if not slot:
            continue
        
        date_obj = datetime.strptime(booking['date'], '%Y-%m-%d')
        
        export_data.append({
            'Datum': date_obj.strftime('%d.%m.%Y'),
            'Wochentag': format_german_weekday(booking['date']),
            'Schicht': slot['day_name'],
            'Beginn': slot['start_time'],
            'Ende': slot['end_time'],
            'Dauer (Stunden)': slot['duration_hours'],
            'Status': booking['status'],
            'Gebucht am': datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M'),
            'Booking-ID': booking['id']
        })
    
    df = pd.DataFrame(export_data)
    
    # CSV generieren
    csv_content = df.to_csv(index=False, encoding='utf-8-sig')
    
    # Download-Button
    filename = f"meine_schichten_{filter_type.lower()}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    st.download_button(
        label="📥 CSV-Datei herunterladen",
        data=csv_content,
        file_name=filename,
        mime="text/csv",
        help="Für Excel, Google Sheets, Numbers etc."
    )
    
    success_message(f"📊 CSV-Export bereit: {len(bookings)} Termine")