"""
Dienstplan+ Cloud v3.0 - Schedule Pages
Wochenpläne und Monatskalender mit Buchungsfunktionen
"""
import streamlit as st
from datetime import datetime, timedelta
from app.config.constants import WEEKLY_SLOTS
from app.core.helpers import (
    get_week_start, get_iso_calendar_week, get_slot_date, 
    is_holiday, is_closed_period, get_holiday_name,
    send_calendar_invite, validate_booking_request,
    format_german_date
)
from app.ui.components import (
    week_header, info_card, legend, favorite_star,
    render_shift_card, render_navigation_buttons, success_message, error_message
)

# Streamlit-Calendar Import mit Fallback
try:
    from streamlit_calendar import calendar as st_calendar
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

def show_schedule_tab():
    """Hauptansicht für Terminplanung"""
    
    # View-Auswahl
    if CALENDAR_AVAILABLE:
        view_mode = st.radio(
            "📊 Ansicht wählen:",
            ["📅 Wochenansicht", "🗓️ Monatskalender"],
            horizontal=True,
            key="schedule_view_mode"
        )
        
        if view_mode == "🗓️ Monatskalender":
            show_monthly_calendar()
        else:
            show_weekly_schedule()
    else:
        st.info("ℹ️ Monatskalender nicht verfügbar - verwende Wochenansicht")
        show_weekly_schedule()

def show_weekly_schedule():
    """Wochenansicht mit Navigation und Slot-Karten"""
    
    user = st.session_state.current_user
    
    # Aktuelle Woche aus Session State
    week_start = st.session_state.current_week_start
    week_end = week_start + timedelta(days=6)
    kw = get_iso_calendar_week(week_start)
    
    # Wochenkopf anzeigen
    week_header(week_start, week_end, kw)
    
    # Navigation
    handle_week_navigation()
    
    st.markdown("---")
    
    # Legende
    legend()
    
    st.markdown("---")
    
    # Slot-Karten für die Woche
    for slot in WEEKLY_SLOTS:
        show_slot_card(slot, user)
    
    # Kalenderwochen-Sprung
    show_week_jump_selector()

def handle_week_navigation():
    """Behandelt Wochen-Navigation"""
    
    week_start = st.session_state.current_week_start
    
    # Navigation Buttons
    previous_clicked, next_clicked, date_changed, selected_date = render_navigation_buttons(week_start)
    
    # Navigation logik
    if previous_clicked:
        st.session_state.current_week_start = week_start - timedelta(days=7)
        st.rerun()
    
    elif next_clicked:
        st.session_state.current_week_start = week_start + timedelta(days=7)
        st.rerun()
    
    elif date_changed:
        # Springe zur Woche des gewählten Datums
        new_week_start = get_week_start(selected_date)
        st.session_state.current_week_start = new_week_start
        st.rerun()

def show_slot_card(slot, user):
    """Zeigt Karte für einen spezifischen Slot"""
    
    week_start = st.session_state.current_week_start
    date_str = get_slot_date(week_start, slot['day'])
    
    # Prüfe Feiertag
    if is_holiday(date_str):
        holiday_name = get_holiday_name(date_str)
        info_card(
            title=f"🎄 {slot['day_name']}, {format_german_date(date_str)}",
            lines=[
                f"**Feiertag:** {holiday_name}",
                "❌ Keine Schichten an diesem Tag"
            ],
            variant="danger"
        )
        return
    
    # Prüfe Sperrzeit
    if is_closed_period(date_str):
        info_card(
            title=f"🏊‍♂️ {slot['day_name']}, {format_german_date(date_str)}",
            lines=[
                "**Hallenbad geschlossen - Sommerpause**",
                "❌ Keine Buchungen möglich (Juni - September)"
            ],
            variant="warning"
        )
        return
    
    # Lade Buchungsinformationen
    bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
    
    if bookings:
        # Slot ist belegt
        booking = bookings[0]  # Es kann nur eine Buchung pro Slot geben
        show_booked_slot_card(slot, date_str, booking, user)
    else:
        # Slot ist frei
        show_available_slot_card(slot, date_str, user)

def show_available_slot_card(slot, date_str, user):
    """Zeigt Karte für verfügbaren Slot"""
    
    # Container für Slot-Karte
    with st.container():
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Favoriten-Status prüfen
            is_favorite = st.session_state.db.is_favorite(user['id'], slot['id'], date_str)
            star_unicode, star_class = favorite_star(is_favorite)
            
            info_card(
                title=f"✨ {slot['day_name']}, {format_german_date(date_str)}",
                lines=[
                    "**Verfügbar**",
                    "💡 Klicken Sie auf \"Buchen\" um diese Schicht zu übernehmen",
                    f"⏰ {slot['start_time']} - {slot['end_time']} Uhr"
                ],
                variant="success"
            )
        
        with col2:
            # Favoriten-Stern
            if st.button(
                f"{star_unicode} Favorit", 
                key=f"fav_{slot['id']}_{date_str}",
                help="Zu Watchlist hinzufügen/entfernen"
            ):
                toggle_favorite(user['id'], slot['id'], date_str)
            
            # Buchungs-Button
            if st.button(
                "📝 Buchen", 
                key=f"book_{slot['id']}_{date_str}",
                type="primary"
            ):
                book_slot(user, slot, date_str)

def show_booked_slot_card(slot, date_str, booking, user):
    """Zeigt Karte für belegten Slot"""
    
    is_own_booking = booking['user_id'] == user['id']
    
    # Container für Slot-Karte
    with st.container():
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if is_own_booking:
                # Eigene Buchung
                info_card(
                    title=f"✅ {slot['day_name']}, {format_german_date(date_str)}",
                    lines=[
                        "**Gebucht von Ihnen**",
                        f"⏰ {slot['start_time']} - {slot['end_time']} Uhr",
                        f"📝 Gebucht: {datetime.fromisoformat(booking['created_at']).strftime('%d.%m.%Y %H:%M')}"
                    ],
                    variant="info"
                )
            else:
                # Buchung von anderem User
                is_favorite = st.session_state.db.is_favorite(user['id'], slot['id'], date_str)
                star_unicode, star_class = favorite_star(is_favorite)
                
                info_card(
                    title=f"📋 {slot['day_name']}, {format_german_date(date_str)}",
                    lines=[
                        f"**Gebucht von:** {booking['user_name']}",
                        "⚠️ Schicht bereits vergeben",
                        f"⏰ {slot['start_time']} - {slot['end_time']} Uhr"
                    ],
                    variant="warning"
                )
        
        with col2:
            if is_own_booking:
                # Storno-Button für eigene Buchungen
                if st.button(
                    "❌ Stornieren", 
                    key=f"cancel_{booking['id']}",
                    help="Eigene Buchung stornieren"
                ):
                    cancel_booking(user, booking, slot, date_str)
            else:
                # Favoriten-Button für fremde Buchungen
                is_favorite = st.session_state.db.is_favorite(user['id'], slot['id'], date_str)
                star_unicode, star_class = favorite_star(is_favorite)
                
                if st.button(
                    f"{star_unicode} Favorit", 
                    key=f"fav_{slot['id']}_{date_str}",
                    help="Zu Watchlist hinzufügen - wird benachrichtigt wenn frei"
                ):
                    toggle_favorite(user['id'], slot['id'], date_str)

def show_monthly_calendar():
    """Monatskalender mit streamlit-calendar"""
    
    if not CALENDAR_AVAILABLE:
        st.error("❌ Monatskalender nicht verfügbar - streamlit-calendar fehlt")
        return
    
    st.markdown("### 🗓️ Monatskalender")
    
    # Legende
    legend()
    
    # Kalender-Events generieren
    events = generate_calendar_events()
    
    # Kalender anzeigen
    try:
        calendar_options = {
            "editable": False,
            "selectable": True,
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek"
            },
            "initialView": "dayGridMonth",
            "height": 600
        }
        
        selected = st_calendar(
            events=events,
            options=calendar_options,
            custom_css="""
            .fc-event-available { background-color: #16a34a !important; }
            .fc-event-partial { background-color: #f59e0b !important; }
            .fc-event-booked { background-color: #dc2626 !important; }
            .fc-event-holiday { background-color: #7c2d12 !important; }
            .fc-event-closed { background-color: #6b7280 !important; }
            """,
            key="monthly_calendar"
        )
        
        # Bei Klick auf Datum zur entsprechenden Woche springen
        if selected.get('dateClick'):
            clicked_date = datetime.fromisoformat(selected['dateClick']['date'].split('T')[0]).date()
            new_week_start = get_week_start(clicked_date)
            st.session_state.current_week_start = new_week_start
            st.rerun()
        
    except Exception as e:
        st.error(f"❌ Kalender-Fehler: {str(e)}")
        st.info("📅 Fallback: Verwende Wochenansicht")
        show_weekly_schedule()

def generate_calendar_events():
    """Generiert Events für den Monatskalender"""
    
    events = []
    current_date = datetime.now().date()
    end_date = current_date + timedelta(days=60)
    
    # Iteriere über alle Tage
    check_date = current_date
    while check_date <= end_date:
        date_str = check_date.strftime('%Y-%m-%d')
        
        # Prüfe Feiertage
        if is_holiday(date_str):
            holiday_name = get_holiday_name(date_str)
            events.append({
                'title': f'🎄 {holiday_name}',
                'start': date_str,
                'className': 'fc-event-holiday',
                'allDay': True
            })
        
        # Prüfe Sperrzeit
        elif is_closed_period(date_str):
            events.append({
                'title': '🏊‍♂️ Geschlossen',
                'start': date_str,
                'className': 'fc-event-closed',
                'allDay': True
            })
        
        else:
            # Prüfe Slot-Status für diesen Tag
            day_status = get_day_booking_status(check_date)
            
            if day_status['has_slots']:
                if day_status['all_booked']:
                    events.append({
                        'title': '📋 Alle Schichten belegt',
                        'start': date_str,
                        'className': 'fc-event-booked',
                        'allDay': True
                    })
                elif day_status['some_booked']:
                    events.append({
                        'title': f"📊 {day_status['booked_count']}/{day_status['total_count']} belegt",
                        'start': date_str,
                        'className': 'fc-event-partial',
                        'allDay': True
                    })
                else:
                    events.append({
                        'title': f"✨ {day_status['total_count']} Schichten verfügbar",
                        'start': date_str,
                        'className': 'fc-event-available',
                        'allDay': True
                    })
        
        check_date += timedelta(days=1)
    
    return events

def get_day_booking_status(date_obj):
    """Ermittelt Buchungsstatus für einen Tag"""
    
    date_str = date_obj.strftime('%Y-%m-%d')
    total_slots = 0
    booked_slots = 0
    
    # Prüfe alle Slots für diesen Wochentag
    weekday_mapping = {
        0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
        4: 'friday', 5: 'saturday', 6: 'sunday'
    }
    
    current_weekday = weekday_mapping[date_obj.weekday()]
    
    for slot in WEEKLY_SLOTS:
        if slot['day'] == current_weekday:
            total_slots += 1
            bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
            if bookings:
                booked_slots += 1
    
    return {
        'has_slots': total_slots > 0,
        'total_count': total_slots,
        'booked_count': booked_slots,
        'all_booked': total_slots > 0 and booked_slots == total_slots,
        'some_booked': booked_slots > 0 and booked_slots < total_slots
    }

def show_week_jump_selector():
    """Zeigt Kalenderwochen-Auswahl"""
    
    st.markdown("---")
    st.markdown("### 🗓️ Direkt zu Kalenderwoche springen")
    
    current_week = st.session_state.current_week_start
    
    # Generiere Wochen-Liste
    week_options = []
    week_dates = []
    
    for i in range(-4, 12):  # 4 Wochen zurück, 12 voraus
        week_date = current_week + timedelta(weeks=i)
        week_end = week_date + timedelta(days=6)
        kw = get_iso_calendar_week(week_date)
        
        label = f"KW {kw:02d} — {week_date.strftime('%d.%m.')} bis {week_end.strftime('%d.%m.%Y')}"
        week_options.append(label)
        week_dates.append(week_date)
    
    # Aktuelle Woche finden
    current_index = 4  # Offset für 4 Wochen zurück
    
    selected_index = st.selectbox(
        "Kalenderwoche auswählen:",
        range(len(week_options)),
        index=current_index,
        format_func=lambda x: week_options[x],
        key="week_selector"
    )
    
    if selected_index != current_index:
        st.session_state.current_week_start = week_dates[selected_index]
        st.rerun()

def toggle_favorite(user_id, slot_id, date_str):
    """Favoriten-Status umschalten"""
    
    is_favorite = st.session_state.db.is_favorite(user_id, slot_id, date_str)
    
    if is_favorite:
        success = st.session_state.db.remove_favorite(user_id, slot_id, date_str)
        if success:
            success_message("Aus Watchlist entfernt")
        else:
            error_message("Fehler beim Entfernen aus Watchlist")
    else:
        success = st.session_state.db.add_favorite(user_id, slot_id, date_str)
        if success:
            success_message("Zur Watchlist hinzugefügt")
        else:
            error_message("Bereits in Watchlist oder Fehler")
    
    st.rerun()

def book_slot(user, slot, date_str):
    """Bucht einen Slot für den User"""
    
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
        
        # Kalender-Einladung senden (optional)
        if st.session_state.email_service.enabled:
            booking_data = {
                'id': booking_id,
                'date': date_str,
                'user_id': user['id']
            }
            
            invite_success, invite_result = send_calendar_invite(
                user, booking_data, slot, method="REQUEST"
            )
            
            if invite_success:
                success_message("📧 Kalender-Einladung wurde gesendet")
        
        # Favorit entfernen falls vorhanden
        if st.session_state.db.is_favorite(user['id'], slot['id'], date_str):
            st.session_state.db.remove_favorite(user['id'], slot['id'], date_str)
        
        st.rerun()
        
    else:
        error_message(f"❌ Buchung fehlgeschlagen: {result}")

def cancel_booking(user, booking, slot, date_str):
    """Storniert eine Buchung"""
    
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
            
            cancel_success, cancel_result = send_calendar_invite(
                user, booking_data, slot, method="CANCEL"
            )
            
            if cancel_success:
                success_message("📧 Kalender-Absage wurde gesendet")
        
        st.rerun()
        
    else:
        error_message("❌ Stornierung fehlgeschlagen")