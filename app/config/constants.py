"""
Dienstplan+ Cloud v3.0 - Konstanten und Konfiguration
Zentrale Definition aller App-Konstanten
"""

# Wöchentliche Schicht-Slots
WEEKLY_SLOTS = [
    {
        "id": 1,
        "day": "tuesday",
        "day_name": "Dienstag",
        "start_time": "17:00",
        "end_time": "20:00",
        "color": "#3B82F6",
        "duration_hours": 3
    },
    {
        "id": 2,
        "day": "friday",
        "day_name": "Freitag",
        "start_time": "17:00",
        "end_time": "20:00",
        "color": "#10B981",
        "duration_hours": 3
    },
    {
        "id": 3,
        "day": "saturday",
        "day_name": "Samstag",
        "start_time": "14:00",
        "end_time": "17:00",
        "color": "#F59E0B",
        "duration_hours": 3
    }
]

# Bayerische Feiertage 2025
BAVARIAN_HOLIDAYS_2025 = [
    {"date": "2025-01-01", "name": "Neujahr"},
    {"date": "2025-01-06", "name": "Heilige Drei Könige"},
    {"date": "2025-04-18", "name": "Karfreitag"},
    {"date": "2025-04-21", "name": "Ostermontag"},
    {"date": "2025-05-01", "name": "Tag der Arbeit"},
    {"date": "2025-05-29", "name": "Christi Himmelfahrt"},
    {"date": "2025-06-09", "name": "Pfingstmontag"},
    {"date": "2025-06-19", "name": "Fronleichnam"},
    {"date": "2025-08-15", "name": "Mariä Himmelfahrt"},
    {"date": "2025-10-03", "name": "Tag der Deutschen Einheit"},
    {"date": "2025-11-01", "name": "Allerheiligen"},
    {"date": "2025-12-25", "name": "1. Weihnachtsfeiertag"},
    {"date": "2025-12-26", "name": "2. Weihnachtsfeiertag"}
]

# Sperrzeit-Konfiguration (Sommer-Pause)
CLOSED_PERIOD = {
    "start_month": 6,  # Juni
    "start_day": 1,
    "end_month": 9,    # September
    "end_day": 30,
    "reason": "Hallenbad geschlossen - Sommerpause"
}

# UI-Farben und Styling
COLORS = {
    "primary": "#1e40af",
    "secondary": "#3b82f6",
    "success": "#16a34a",
    "warning": "#f59e0b",
    "danger": "#dc2626",
    "info": "#0ea5e9",
    "light": "#f8fafc",
    "dark": "#1e293b",
    
    # Status-spezifische Farben
    "available": "#16a34a",
    "booked": "#f59e0b",
    "user_booked": "#2563eb",
    "holiday": "#dc2626",
    "closed": "#6b7280",
    "favorite": "#fbbf24"
}

# Wochentag-Mapping
WEEKDAY_MAPPING = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6
}

# App-Metadaten
APP_INFO = {
    "name": "Dienstplan+ Cloud",
    "version": "3.0",
    "description": "Professionelle Dienstplanung für Teams",
    "author": "Dienstplan+ Team",
    "support_email": "support@dienstplan-cloud.de"
}

# Standard-Templates für SMS/E-Mail
DEFAULT_SMS_TEMPLATES = {
    "24h_reminder": "Hallo {{name}}! Erinnerung: Du hast morgen eine Schicht am {{datum}} von {{slot}}. Bei Absage bitte melden.",
    "1h_reminder": "Hi {{name}}! Deine Schicht beginnt in 1 Stunde: {{datum}} {{slot}}. Bis gleich!",
    "sick_notification": "HINWEIS: {{name}} hat sich krank gemeldet und die Schicht am {{datum}} ({{slot}}) storniert. Bitte Ersatz organisieren.",
    "7_day_warning": "WARNUNG: Die Schicht am {{datum}} ({{slot}}) ist 7 Tage vorher noch unbesetzt. Bitte prüfen.",
    "test_sms": "Test-SMS von Dienstplan+ Cloud für {{name}} am {{datum}}. Diese Nachricht bestätigt, dass SMS korrekt funktioniert."
}

DEFAULT_EMAIL_TEMPLATES = {
    "booking_invite": {
        "subject": "[Dienstplan+] Einladung: {{slot}} - {{datum}}",
        "body": "Hallo {{name}},\n\nhier ist deine Kalender-Einladung für die Schicht am {{datum}} von {{slot}}.\n\nMit \"Annehmen\" im Kalender bestätigst du den Termin automatisch.\n\nViele Grüße\nDein Dienstplan+ Team"
    },
    "booking_cancel": {
        "subject": "[Dienstplan+] Absage: {{slot}} - {{datum}}",
        "body": "Hallo {{name}},\n\ndie Schicht am {{datum}} von {{slot}} wurde storniert.\n\nDiese Nachricht aktualisiert oder entfernt den Kalendereintrag automatisch.\n\nViele Grüße\nDein Dienstplan+ Team"
    },
    "booking_reschedule": {
        "subject": "[Dienstplan+] Umbuchung: {{slot}} - {{datum}}",
        "body": "Hallo {{name}},\n\ndeine Schicht wurde umgebucht auf: {{datum}} von {{slot}}.\n\nBitte prüfe deinen Kalender für die Aktualisierung.\n\nViele Grüße\nDein Dienstplan+ Team"
    },
    "test_email": {
        "subject": "[Dienstplan+] Test-E-Mail für {{name}}",
        "body": "Hallo {{name}},\n\ndies ist eine Test-E-Mail von Dienstplan+ Cloud vom {{datum}}.\n\nWenn Sie diese E-Mail erhalten, funktioniert die E-Mail-Verbindung korrekt.\n\nViele Grüße\nIhr Dienstplan+ Team"
    }
}

# Standard Schicht-Informationen
DEFAULT_SHIFT_INFO = """# Schicht-Checkliste

## Vor Schichtbeginn:
1. **Kasse holen** - Schlüssel im Büro abholen
2. **Hallenbad aufsperren** - 30 Minuten vor Öffnung
3. **Technik prüfen** - Beleuchtung, Heizung, Pumpen
4. **Sicherheit checken** - Erste-Hilfe-Kasten, AED-Gerät

## Während der Schicht:
- **Aufsichtspflicht** wahrnehmen
- **Badegäste** freundlich betreuen
- **Ordnung** im Bad aufrechterhalten
- **Kassierung** korrekt durchführen

## Nach Schichtende:
1. **Bad kontrollieren** - alle Bereiche prüfen
2. **Kasse abrechnen** - Einnahmen zählen
3. **Hallenbad abschließen** - alle Türen/Fenster
4. **Kasse zurückbringen** - sicher im Büro verstauen

## Ausnahmen:
- Bei **Feiertagen** gelten andere Öffnungszeiten
- Bei **Veranstaltungen** Sonderregelungen beachten
- Bei **Problemen** sofort Leitung kontaktieren"""

# Standard Rettungskette
DEFAULT_RESCUE_CHAIN = """# Rettungskette bei Notfällen im Hallenbad

## 🚨 Sofortmaßnahmen:

### 1. Situation erfassen
- **Ruhe bewahren**
- **Überblick verschaffen**
- **Gefahren erkennen**

### 2. Notruf absetzen
**📞 Notruf: 112**
- **Wo:** Hallenbad [Adresse]
- **Was:** Art des Notfalls beschreiben
- **Wie viele:** Anzahl Verletzte
- **Wer:** Name des Anrufers
- **Warten** auf Rückfragen

### 3. Erste Hilfe einleiten

#### Bei Bewusstlosigkeit:
1. **Ansprechen:** "Hören Sie mich?"
2. **Anfassen:** Leicht an den Schultern rütteln
3. **Atmung prüfen:** 10 Sekunden beobachten
4. **Stabile Seitenlage** bei normaler Atmung
5. **Herz-Lungen-Wiederbelebung** bei fehlender Atmung

#### Herz-Lungen-Wiederbelebung (HLW):
1. **Position:** Handballen auf Brustbeinmitte
2. **Drucktiefe:** 5-6 cm
3. **Frequenz:** 100-120/min
4. **Verhältnis:** 30 Druckmassagen : 2 Beatmungen
5. **Nicht aufhören** bis Rettungsdienst übernimmt

### 4. AED-Gerät nutzen
- **AED holen** (Standort: Eingangsbereich)
- **Einschalten** - Gerät gibt Anweisungen
- **Elektroden aufkleben** wie abgebildet
- **Anweisungen befolgen**
- **Bei Schock:** Alle zurücktreten

### 5. Weitere Maßnahmen
- **Badegäste evacuieren** bei Bedarf
- **Zugang freihalten** für Rettungsdienst
- **Angehörige benachrichtigen**
- **Leitung informieren**
- **Dokumentation** für Nachbereitung

## ⚠️ Besonderheiten Hallenbad:
- **Rutschgefahr** - Vorsicht bei Rettung
- **Wasserrettung** - Eigenschutz beachten
- **Hypothermie** - Patient warmhalten
- **Chlorgasvergiftung** möglich - Bereich lüften

## 📞 Wichtige Nummern:
- **Notruf:** 112
- **Giftnotruf:** 089 19240
- **Leitung:** [Telefonnummer eintragen]
- **Hausmeister:** [Telefonnummer eintragen]

## 🎯 Merksatz:
**"Prüfen - Rufen - Drücken - Schocken"**

*Diese Anleitung ersetzt keine Erste-Hilfe-Ausbildung!*"""

# Limits und Konfiguration
LIMITS = {
    "max_bookings_per_user": 0,  # 0 = unbegrenzt
    "max_booking_days_ahead": 60,
    "cancellation_hours_before": 2,
    "backup_retention_days": 30,
    "log_retention_days": 90
}