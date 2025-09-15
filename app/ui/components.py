"""
Dienstplan+ Cloud v3.0 - UI Components
Wiederverwendbare UI-Komponenten für konsistentes Design
"""
import streamlit as st
from datetime import datetime, date

def week_header(week_start: date, week_end: date, kw: int):
    """Rendert formatierten Wochenkopf mit Datum und Kalenderwoche"""
    
    # Deutsche Datumsformatierung
    start_str = week_start.strftime('%d.%m.%Y')
    end_str = week_end.strftime('%d.%m.%Y')
    
    # HTML für gestylten Header
    header_html = f"""
    <div class="week-header">
        <h2>Woche vom {start_str} bis {end_str}</h2>
        <div class="calendar-week">Kalenderwoche {kw}</div>
    </div>
    """
    
    st.markdown(header_html, unsafe_allow_html=True)

def info_card(title: str, lines: list[str], variant: str = "info"):
    """
    Rendert Informationskarte mit verschiedenen Stilen
    
    Args:
        title: Titel der Karte
        lines: Liste von Textzeilen
        variant: Stil-Variante (info, success, warning, danger)
    """
    
    # Validiere Variante
    valid_variants = ["info", "success", "warning", "danger"]
    if variant not in valid_variants:
        variant = "info"
    
    # HTML für Info-Karte
    lines_html = "".join([f"<p>{line}</p>" for line in lines])
    
    card_html = f"""
    <div class="info-card {variant}">
        <h4>{title}</h4>
        {lines_html}
    </div>
    """
    
    st.markdown(card_html, unsafe_allow_html=True)

def legend():
    """Rendert Farbdot-Legende für Kalender-Status"""
    
    legend_html = """
    <div class="calendar-legend">
        <div class="legend-item">
            <div class="legend-dot free-dot"></div>
            <span>Verfügbar</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot partial-dot"></div>
            <span>Teilweise belegt</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot booked-dot"></div>
            <span>Belegt</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot holiday-dot"></div>
            <span>Feiertag</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot closed-dot"></div>
            <span>Geschlossen</span>
        </div>
    </div>
    """
    
    st.markdown(legend_html, unsafe_allow_html=True)

def favorite_star(active: bool) -> tuple[str, str]:
    """
    Gibt Unicode-Stern und CSS-Klasse für Favoriten zurück
    
    Args:
        active: True wenn Favorit aktiv ist
        
    Returns:
        Tuple von (unicode_stern, css_klasse)
    """
    
    if active:
        return "⭐", "favorite-star active"
    else:
        return "☆", "favorite-star inactive"

def admin_expander_header(title: str, badge_count: int) -> str:
    """
    Erstellt Header-Text für Admin-Expander mit Badge
    
    Args:
        title: Titel des Expanders
        badge_count: Anzahl für Badge
        
    Returns:
        Formatierter Header-String
    """
    
    if badge_count > 0:
        return f"{title} ({badge_count})"
    else:
        return title

def render_shift_card(slot, date_str, booking_status, user_id=None, show_favorite_star=True):
    """
    Rendert vollständige Schicht-Karte mit allen Status-Optionen
    
    Args:
        slot: Slot-Dictionary aus WEEKLY_SLOTS
        date_str: Datum als String (YYYY-MM-DD)
        booking_status: Dictionary mit Status-Informationen
        user_id: Aktuelle User-ID (optional)
        show_favorite_star: Ob Favoriten-Stern angezeigt werden soll
    """
    
    from app.core.helpers import is_holiday, get_holiday_name, is_closed_period
    
    # Prüfe Sperrzeiten und Feiertage
    if is_holiday(date_str):
        holiday_name = get_holiday_name(date_str)
        card_html = f"""
        <div class="shift-card holiday-card">
            <h4>🎄 {slot['day_name']}, {datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}</h4>
            <p><strong>Feiertag:</strong> {holiday_name}</p>
            <p>❌ Keine Schichten an diesem Tag</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        return
    
    if is_closed_period(date_str):
        card_html = f"""
        <div class="shift-card closed-card">
            <h4>🏊‍♂️ {slot['day_name']}, {datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}</h4>
            <p><strong>Hallenbad in dieser Zeit geschlossen</strong></p>
            <p>❌ Keine Buchung möglich (Juni - September)</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        return
    
    # Normale Schicht-Karte basierend auf Status
    status = booking_status.get('status', 'available')
    
    if status == 'user_booked':
        # Von aktuellem User gebucht
        card_html = f"""
        <div class="shift-card user-slot">
            <h4>✅ {slot['day_name']}, {datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}</h4>
            <p><strong>Gebucht von Ihnen</strong></p>
            <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        
    elif status == 'booked':
        # Von anderem User gebucht
        booker_name = booking_status.get('user_name', 'Unbekannt')
        
        # Favoriten-Stern positionieren
        star_html = ""
        if show_favorite_star and user_id:
            is_favorite = st.session_state.db.is_favorite(user_id, slot['id'], date_str)
            star_unicode, star_class = favorite_star(is_favorite)
            star_html = f'<div class="{star_class}">{star_unicode}</div>'
        
        card_html = f"""
        <div class="shift-card booked-slot" style="position: relative;">
            {star_html}
            <h4>📋 {slot['day_name']}, {datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}</h4>
            <p><strong>Gebucht von:</strong> {booker_name}</p>
            <p>⚠️ Schicht bereits vergeben</p>
            <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        
    else:
        # Verfügbarer Slot
        star_html = ""
        if show_favorite_star and user_id:
            is_favorite = st.session_state.db.is_favorite(user_id, slot['id'], date_str)
            star_unicode, star_class = favorite_star(is_favorite)
            star_html = f'<div class="{star_class}">{star_unicode}</div>'
        
        card_html = f"""
        <div class="shift-card available-slot" style="position: relative;">
            {star_html}
            <h4>✨ {slot['day_name']}, {datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}</h4>
            <p><strong>Verfügbar</strong></p>
            <p>💡 Klicken Sie auf "Buchen" um diese Schicht zu übernehmen</p>
            <p>⏰ {slot['start_time']} - {slot['end_time']} Uhr</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

def render_navigation_buttons(week_start: date):
    """
    Rendert Wochen-Navigation mit Previous/Next Buttons
    
    Args:
        week_start: Aktueller Wochenstart
        
    Returns:
        Tuple von (previous_clicked, next_clicked, date_changed, selected_date)
    """
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        previous_clicked = st.button("⬅️ Vorherige Woche", key="prev_week", use_container_width=True)
    
    with col3:
        next_clicked = st.button("Nächste Woche ➡️", key="next_week", use_container_width=True)
    
    with col2:
        # Datepicker für direkten Sprung
        selected_date = st.date_input(
            "Direkt zu Datum springen:",
            value=week_start,
            key="date_picker",
            help="Wählen Sie ein Datum - es wird automatisch zur entsprechenden Woche gesprungen"
        )
        
        date_changed = selected_date != week_start
    
    return previous_clicked, next_clicked, date_changed, selected_date

def render_week_jump_list(current_week_start: date):
    """
    Rendert Kalenderwochen-Sprungliste für schnelle Navigation
    
    Args:
        current_week_start: Aktueller Wochenstart
        
    Returns:
        Gewählter Wochenstart oder None
    """
    
    from app.core.helpers import get_iso_calendar_week
    
    # Generiere Liste der nächsten 12 Wochen
    week_options = []
    option_dates = []
    
    for i in range(-2, 10):  # 2 Wochen zurück, 10 Wochen voraus
        week_date = current_week_start + st.session_state.timedelta(weeks=i)
        week_end = week_date + st.session_state.timedelta(days=6)
        kw = get_iso_calendar_week(week_date)
        
        label = f"KW {kw:02d} — {week_date.strftime('%d.%m.')} bis {week_end.strftime('%d.%m.%Y')}"
        week_options.append(label)
        option_dates.append(week_date)
    
    # Finde aktuellen Index
    current_index = 2  # Standard: aktuelle Woche (Offset 0 + 2)
    
    # Selectbox für Wochen-Sprung
    selected_index = st.selectbox(
        "📅 Sprung zu Kalenderwoche:",
        range(len(week_options)),
        index=current_index,
        format_func=lambda x: week_options[x],
        key="week_jump_select"
    )
    
    if selected_index != current_index:
        return option_dates[selected_index]
    
    return None

def success_message(message: str):
    """Zeigt Erfolgs-Nachricht an"""
    st.markdown(f'<div class="success-message">✅ {message}</div>', unsafe_allow_html=True)

def error_message(message: str):
    """Zeigt Fehler-Nachricht an"""
    st.markdown(f'<div class="error-message">❌ {message}</div>', unsafe_allow_html=True)

def warning_message(message: str):
    """Zeigt Warnung an"""
    st.markdown(f'<div class="warning-message">⚠️ {message}</div>', unsafe_allow_html=True)

def render_stats_card(title: str, value: str, subtitle: str = "", icon: str = "📊"):
    """
    Rendert Statistik-Karte für Admin-Bereich
    
    Args:
        title: Titel der Statistik
        value: Hauptwert
        subtitle: Untertitel (optional)
        icon: Icon für die Karte
    """
    
    subtitle_html = f"<p style='margin:0; opacity:0.8; font-size:0.9rem;'>{subtitle}</p>" if subtitle else ""
    
    card_html = f"""
    <div class="shift-card" style="text-align: center; min-height: 120px; display: flex; flex-direction: column; justify-content: center;">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">{icon}</div>
        <h3 style="margin: 0; color: #1e40af;">{value}</h3>
        <p style="margin: 0.25rem 0 0 0; font-weight: 600; color: #64748b;">{title}</p>
        {subtitle_html}
    </div>
    """
    
    st.markdown(card_html, unsafe_allow_html=True)

def render_user_badge(user_name: str, user_role: str, is_online: bool = False):
    """
    Rendert Benutzer-Badge für Team-Übersicht
    
    Args:
        user_name: Name des Benutzers
        user_role: Rolle (admin/user)
        is_online: Online-Status (optional)
    """
    
    role_color = "#f59e0b" if user_role == "admin" else "#3b82f6"
    role_text = "👑 Admin" if user_role == "admin" else "👤 User"
    online_indicator = "🟢" if is_online else "⚪"
    
    badge_html = f"""
    <div style="
        display: inline-flex; 
        align-items: center; 
        gap: 0.5rem; 
        background: white; 
        border: 2px solid {role_color}; 
        border-radius: 8px; 
        padding: 0.5rem 1rem; 
        margin: 0.25rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    ">
        <span>{online_indicator}</span>
        <span style="font-weight: 600;">{user_name}</span>
        <span style="color: {role_color}; font-size: 0.875rem;">{role_text}</span>
    </div>
    """
    
    st.markdown(badge_html, unsafe_allow_html=True)