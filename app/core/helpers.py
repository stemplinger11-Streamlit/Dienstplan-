"""
Dienstplan+ Cloud v3.0 - Helper Funktionen
Zeit-/Datum-Utils, Validierungen und Abstraktionshelfer
"""
import streamlit as st
from datetime import datetime, timedelta
from app.config.constants import WEEKLY_SLOTS, BAVARIAN_HOLIDAYS_2025, CLOSED_PERIOD

# Zeit- und Kalender-Funktionen
def get_week_start(date_obj):
    """Gibt Montag der ISO-Kalenderwoche zurück"""
    return date_obj - timedelta(days=date_obj.weekday())

def get_current_week_start():
    """Gibt Montag der aktuellen ISO-Kalenderwoche zurück"""
    return get_week_start(datetime.now().date())

def get_iso_calendar_week(date_obj):
    """Gibt ISO-Kalenderwoche zurück"""
    return date_obj.isocalendar()[1]

def get_slot_date(week_start, day_name):
    """Berechne Datum für Slot basierend auf Wochenstart und Wochentag"""
    day_mapping = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    
    day_offset = day_mapping.get(day_name, 0)
    slot_date = week_start + timedelta(days=day_offset)
    return slot_date.strftime('%Y-%m-%d')

# Regel-Validierungen
def is_holiday(date_str):
    """Prüfe ob Datum ein Feiertag ist"""
    return any(h['date'] == date_str for h in BAVARIAN_HOLIDAYS_2025)

def get_holiday_name(date_str):
    """Erhalte Name des Feiertags"""
    for holiday in BAVARIAN_HOLIDAYS_2025:
        if holiday['date'] == date_str:
            return holiday['name']
    return None

def is_closed_period(date_str):
    """Prüfe ob Datum in Sperrzeit liegt (Juni-September)"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        start_month = CLOSED_PERIOD['start_month']
        start_day = CLOSED_PERIOD['start_day']
        end_month = CLOSED_PERIOD['end_month']
        end_day = CLOSED_PERIOD['end_day']
        
        # Sperrzeit: 1. Juni bis 30. September
        start_date = datetime(date_obj.year, start_month, start_day)
        end_date = datetime(date_obj.year, end_month, end_day)
        
        return start_date.date() <= date_obj.date() <= end_date.date()
        
    except Exception:
        return False

def can_book_slot(date_str):
    """Prüfe ob Slot buchbar ist (nicht Feiertag, nicht Sperrzeit)"""
    return not is_holiday(date_str) and not is_closed_period(date_str)

# Kalender-Status für Monatsansicht
def get_booking_status_for_calendar():
    """Ermittelt Buchungsstatus für Kalenderanzeige"""
    today = datetime.now().date()
    end_date = today + timedelta(days=60)
    
    booking_status = {}
    current_date = today
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Feiertag prüfen
        if is_holiday(date_str):
            booking_status[date_str] = 'holiday'
        elif is_closed_period(date_str):
            booking_status[date_str] = 'closed'
        else:
            # Prüfen ob an diesem Tag Slots frei oder belegt sind
            has_free_slots = False
            has_booked_slots = False
            
            for slot in WEEKLY_SLOTS:
                if _matches_slot_day(current_date, slot['day']):
                    try:
                        bookings = st.session_state.db.get_bookings_for_date_slot(slot['id'], date_str)
                        if bookings:
                            has_booked_slots = True
                        else:
                            has_free_slots = True
                    except:
                        has_free_slots = True  # Fallback
            
            if has_booked_slots and has_free_slots:
                booking_status[date_str] = 'partial'
            elif has_booked_slots:
                booking_status[date_str] = 'booked'
            elif has_free_slots:
                booking_status[date_str] = 'free'
        
        current_date += timedelta(days=1)
    
    return booking_status

def _matches_slot_day(date_obj, slot_day):
    """Hilfsfunktion: Prüfe ob Datum zum Slot-Wochentag passt"""
    day_mapping = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    return date_obj.weekday() == day_mapping.get(slot_day, -1)

# E-Mail/SMS Abstraktionen
def send_calendar_invite(user, booking, slot, method="REQUEST"):
    """Sende Kalendereinladung (Wrapper für EmailService)"""
    if not st.session_state.email_service.enabled:
        return False, "E-Mail Service nicht verfügbar"
    
    if not st.secrets.get("ENABLE_CALENDAR_INVITES", True):
        return False, "Kalendereinladungen deaktiviert"
    
    try:
        # Template aus Datenbank laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        
        template_type = 'booking_invite' if method == 'REQUEST' else 'booking_cancel'
        cursor.execute('''
            SELECT subject_template, body_template 
            FROM email_templates 
            WHERE template_type = ? AND active = 1
        ''', (template_type,))
        
        template = cursor.fetchone()
        conn.close()
        
        # Template-Variablen ersetzen
        if template:
            subject = template[0].replace('{{name}}', user['name']).replace('{{datum}}', booking['date']).replace('{{slot}}', f"{slot['start_time']}-{slot['end_time']}")
            body = template[1].replace('{{name}}', user['name']).replace('{{datum}}', booking['date']).replace('{{slot}}', f"{slot['start_time']}-{slot['end_time']}")
        else:
            # Fallback-Templates
            action = "Einladung" if method == 'REQUEST' else "Absage"
            subject = f"[Dienstplan+] {action}: {slot['day_name']} - {booking['date']}"
            body = f"Hallo {user['name']},\n\n{action} für Schicht am {booking['date']} von {slot['start_time']} bis {slot['end_time']}."
        
        # ICS generieren
        sequence = 1 if method == "CANCEL" else 0
        ics_content = st.session_state.email_service.generate_ics(
            booking, slot, user, method, sequence
        )
        
        # E-Mail senden
        success, result = st.session_state.email_service.send_calendar_invite(
            user['email'], subject, body, ics_content, method
        )
        
        # Logging
        if success:
            action = 'calendar_invite_sent' if method == 'REQUEST' else 'calendar_cancel_sent'
            st.session_state.db.log_action(
                user['id'], action, f'{method} sent to {user["email"]} for {booking["date"]}'
            )
        
        return success, result
        
    except Exception as e:
        return False, f"Kalender-Fehler: {str(e)}"

def send_sick_notification(user, slot_id, date_str):
    """Sende Krankmeldung an alle Admins"""
    if not st.session_state.sms_service.enabled:
        return []
    
    try:
        # Template aus Datenbank laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sms_template FROM reminder_templates 
            WHERE timing = 'sick_notification' AND active = 1
        ''')
        
        template = cursor.fetchone()
        conn.close()
        
        # Slot-Info laden
        slot_info = next((s for s in WEEKLY_SLOTS if s['id'] == slot_id), None)
        if not slot_info:
            return []
        
        # Nachricht erstellen
        if template:
            message = template[0].replace('{{name}}', user['name']).replace('{{datum}}', date_str).replace('{{slot}}', f"{slot_info['start_time']}-{slot_info['end_time']}")
        else:
            message = f"KRANKMELDUNG: {user['name']} hat sich krank gemeldet für {slot_info['day_name']}, {date_str} ({slot_info['start_time']}-{slot_info['end_time']}). Bitte Ersatz organisieren."
        
        # An alle Admins senden
        results = st.session_state.sms_service.send_admin_sms(message)
        
        # Logging
        successful_sends = sum(1 for r in results if r.get('success', False))
        if successful_sends > 0:
            st.session_state.db.log_action(
                user['id'], 'sick_notification_sent',
                f'Sick report sent to {successful_sends} admins for {date_str}'
            )
        
        return results
        
    except Exception as e:
        return [{'error': str(e)}]

def send_test_sms(user):
    """Sende Test-SMS mit Template"""
    if not st.session_state.sms_service.enabled:
        return False, "SMS Service nicht verfügbar"
    
    try:
        # Template laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sms_template FROM reminder_templates 
            WHERE timing = 'test_sms' AND active = 1
        ''')
        
        template = cursor.fetchone()
        conn.close()
        
        # Nachricht erstellen
        if template:
            message = template[0].replace('{{name}}', user['name']).replace('{{datum}}', datetime.now().strftime('%d.%m.%Y'))
        else:
            message = f"Test-SMS von Dienstplan+ Cloud für {user['name']} am {datetime.now().strftime('%d.%m.%Y')}. SMS-Service funktioniert korrekt!"
        
        # SMS senden
        return st.session_state.sms_service.send_sms(user['phone'], message)
        
    except Exception as e:
        return False, str(e)

def send_test_email(user):
    """Sende Test-E-Mail mit Template"""
    if not st.session_state.email_service.enabled:
        return False, "E-Mail Service nicht verfügbar"
    
    try:
        # Template laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT subject_template, body_template FROM email_templates 
            WHERE template_type = 'test_email' AND active = 1
        ''')
        
        template = cursor.fetchone()
        conn.close()
        
        # E-Mail erstellen
        if template:
            subject = template[0].replace('{{name}}', user['name']).replace('{{datum}}', datetime.now().strftime('%d.%m.%Y'))
            body = template[1].replace('{{name}}', user['name']).replace('{{datum}}', datetime.now().strftime('%d.%m.%Y'))
        else:
            subject = f"[Dienstplan+] Test-E-Mail für {user['name']}"
            body = f"""Hallo {user['name']},

dies ist eine Test-E-Mail von Dienstplan+ Cloud v3.0 vom {datetime.now().strftime('%d.%m.%Y %H:%M')}.

Wenn Sie diese E-Mail erhalten, funktioniert die E-Mail-Konfiguration korrekt.

Features die funktionieren:
✅ SMTP-Verbindung zu Gmail
✅ E-Mail-Versand
✅ Template-System

Als nächstes können Sie testen:
📧 Kalender-Einladungen (Schicht buchen)
💾 Backup-E-Mails (täglich 20:00 Uhr)

Viele Grüße
Ihr Dienstplan+ Team"""
        
        # E-Mail senden
        return st.session_state.email_service.send_email(user['email'], subject, body)
        
    except Exception as e:
        return False, str(e)

# 7-Tage-Warnungen
def check_7_day_warnings():
    """Prüfe und sende 7-Tage-Warnungen für unbelegte Schichten"""
    if not st.secrets.get("ENABLE_7_DAY_WARNINGS", True):
        return
    
    if not st.session_state.sms_service.enabled:
        return
    
    try:
        warnings = st.session_state.db.check_7_day_warnings()
        
        if not warnings:
            return
        
        # Template laden
        conn = st.session_state.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sms_template FROM reminder_templates 
            WHERE timing = '7_day_warning' AND active = 1
        ''')
        
        template = cursor.fetchone()
        conn.close()
        
        # Für jede Warnung SMS senden
        for warning in warnings:
            if template:
                message = template[0].replace('{{datum}}', warning['date']).replace('{{slot}}', warning['slot_name'])
            else:
                message = f"WARNUNG: Schicht am {warning['date']} ({warning['slot_name']}) ist 7 Tage vorher noch unbesetzt!"
            
            # An alle Admins senden
            results = st.session_state.sms_service.send_admin_sms(message)
            
            # Logging
            successful_sends = sum(1 for r in results if r.get('success', False))
            if successful_sends > 0:
                st.session_state.db.log_action(
                    1, '7_day_warning_sent',
                    f'Warning sent for {warning["date"]} {warning["slot_name"]} to {successful_sends} admins'
                )
        
    except Exception as e:
        print(f"7-day warning error: {e}")

# Export-Funktionen
def generate_ical_export(bookings):
    """Generiere iCal-Datei für Kalender-Export"""
    ical_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dienstplan+ Cloud v3.0//DE
CALSCALE:GREGORIAN
"""
    
    for booking in bookings:
        try:
            slot = next(s for s in WEEKLY_SLOTS if s['id'] == booking['slot_id'])
            
            # Datum formatieren
            date_str = booking['date'].replace('-', '')
            start_time = slot['start_time'].replace(':', '') + '00'
            end_time = slot['end_time'].replace(':', '') + '00'
            
            ical_content += f"""BEGIN:VEVENT
UID:{booking['id']}@dienstplan-cloud.local
DTSTART:{date_str}T{start_time}
DTEND:{date_str}T{end_time}
SUMMARY:Schicht - {slot['day_name']}
DESCRIPTION:Schicht am {slot['day_name']} von {slot['start_time']} bis {slot['end_time']} Uhr
LOCATION:Hallenbad
STATUS:CONFIRMED
END:VEVENT
"""
        except Exception:
            continue  # Fehlerhafte Buchungen überspringen
    
    ical_content += "END:VCALENDAR"
    return ical_content

# Validierungs-Funktionen
def validate_booking_request(user_id, slot_id, date_str):
    """Validiere Buchungsanfrage"""
    errors = []
    
    # Grundvalidierung
    if not user_id or not slot_id or not date_str:
        errors.append("Unvollständige Buchungsdaten")
        return errors
    
    # Datum-Validierung
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        errors.append("Ungültiges Datumsformat")
        return errors
    
    # Feiertag prüfen
    if is_holiday(date_str):
        holiday_name = get_holiday_name(date_str)
        errors.append(f"Feiertag: {holiday_name}")
    
    # Sperrzeit prüfen
    if is_closed_period(date_str):
        errors.append("Sperrzeit: Hallenbad geschlossen (Juni-September)")
    
    # Vergangenheit prüfen
    if booking_date < datetime.now().date():
        errors.append("Datum liegt in der Vergangenheit")
    
    # Slot existiert prüfen
    if not any(s['id'] == slot_id for s in WEEKLY_SLOTS):
        errors.append("Ungültiger Slot")
    
    # Wochentag passt zu Slot prüfen
    slot = next((s for s in WEEKLY_SLOTS if s['id'] == slot_id), None)
    if slot and not _matches_slot_day(booking_date, slot['day']):
        errors.append(f"Datum passt nicht zu {slot['day_name']}")
    
    return errors

def format_german_date(date_str):
    """Formatiere Datum deutsch (DD.MM.YYYY)"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%d.%m.%Y')
    except:
        return date_str

def format_german_weekday(date_str):
    """Erhalte deutschen Wochentag"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        weekdays = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
        return weekdays[date_obj.weekday()]
    except:
        return "Unbekannt"