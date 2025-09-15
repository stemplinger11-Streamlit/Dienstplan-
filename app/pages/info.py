"""
Dienstplan+ Cloud v3.0 - Information Pages
Schicht-Informationen (editierbar) und Rettungskette (statisch)
"""
import streamlit as st
from datetime import datetime
from app.config.constants import DEFAULT_RESCUE_CHAIN
from app.ui.components import success_message, error_message

def show_information_tab():
    """Informationen-Tab mit editierbaren und statischen Inhalten"""
    
    user = st.session_state.current_user
    
    st.markdown("# ℹ️ Informationen")
    
    # Toggle zwischen Schicht-Info und Rettungskette
    info_mode = st.radio(
        "📋 Informations-Bereich wählen:",
        ["📋 Schicht-Informationen", "🚨 Rettungskette"],
        horizontal=True,
        key="info_mode"
    )
    
    if info_mode == "📋 Schicht-Informationen":
        show_shift_information(user)
    else:
        show_rescue_chain(user)

def show_shift_information(user):
    """Schicht-Informationen (editierbar für Admins)"""
    
    st.markdown("### 📋 Schicht-Informationen")
    
    # Lade aktuelle Schicht-Info aus Datenbank
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT content, last_updated, updated_by 
        FROM info_pages 
        WHERE page_key = 'schicht_info'
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        current_content, last_updated, updated_by = result
    else:
        # Fallback zu Default-Content
        current_content = """# Schicht-Checkliste

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

## Besonderheiten:
- Bei **Feiertagen** gelten andere Öffnungszeiten
- Bei **Veranstaltungen** Sonderregelungen beachten
- Bei **Problemen** sofort Leitung kontaktieren"""
        last_updated = None
        updated_by = None
    
    # Admin-Bereich für Bearbeitung
    if user['role'] == 'admin':
        show_admin_editor(current_content, last_updated, updated_by)
    else:
        show_readonly_content(current_content, last_updated, updated_by)

def show_admin_editor(current_content, last_updated, updated_by):
    """Editierbare Ansicht für Admins"""
    
    st.info("🔧 **Admin-Modus:** Sie können die Schicht-Informationen bearbeiten")
    
    with st.form("edit_shift_info"):
        st.markdown("#### ✏️ Inhalt bearbeiten")
        st.markdown("*Unterstützt Markdown-Formatierung*")
        
        new_content = st.text_area(
            "Schicht-Informationen:",
            value=current_content,
            height=400,
            help="""
Markdown-Formatierung unterstützt:
- # Überschrift 1
- ## Überschrift 2  
- **Fett** und *Kursiv*
- - Aufzählungen
- 1. Nummerierte Listen
"""
        )
        
        # Vorschau-Toggle
        show_preview = st.checkbox("👁️ Live-Vorschau anzeigen", key="show_preview")
        
        if show_preview and new_content:
            st.markdown("#### 📝 Vorschau:")
            with st.container():
                st.markdown(new_content)
        
        # Speichern-Button
        save_submitted = st.form_submit_button("💾 Änderungen speichern", type="primary")
        
        if save_submitted:
            save_shift_information(new_content, st.session_state.current_user['id'])
    
    # Letzte Änderung anzeigen
    if last_updated:
        show_last_updated_info(last_updated, updated_by)

def show_readonly_content(content, last_updated, updated_by):
    """Nur-Lese-Ansicht für normale Benutzer"""
    
    # Content anzeigen
    st.markdown(content)
    
    # Letzte Änderung anzeigen
    if last_updated:
        show_last_updated_info(last_updated, updated_by)
    
    # Hinweis für Admin-Bearbeitung
    st.markdown("---")
    st.info("💡 **Hinweis:** Diese Informationen können von Administratoren bearbeitet werden.")

def show_rescue_chain(user):
    """Rettungskette (statischer Inhalt)"""
    
    st.markdown("### 🚨 Rettungskette Hallenbad")
    
    st.info("⚠️ **Wichtig:** Diese Informationen sind als Notfall-Referenz gedacht und ersetzen keine Erste-Hilfe-Ausbildung!")
    
    # Statischer Content aus constants.py
    st.markdown(DEFAULT_RESCUE_CHAIN)
    
    # Zusätzliche Hinweise
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
### 📞 Wichtige Notrufnummern

**🚨 Notruf:** 112  
**🏥 Rettungsdienst:** 112  
**👮 Polizei:** 110  
**☠️ Giftnotruf:** 089 19240

### 🏊‍♂️ Hallenbad-spezifische Nummern
**📞 Leitung:** [Nummer eintragen]  
**🔧 Hausmeister:** [Nummer eintragen]  
**🏥 Nächstes Krankenhaus:** [Nummer eintragen]
""")
    
    with col2:
        st.markdown("""
### 📍 AED-Gerät Standorte

**🚨 Hauptgerät:** Eingangsbereich  
**🔋 Ersatzbatterien:** Erste-Hilfe-Schrank  
**📖 Anleitung:** Am Gerät befestigt

### 🩹 Erste-Hilfe-Material
**🎒 Hauptkasten:** Büro  
**🚑 Notfallkoffer:** Pool-Bereich  
**🧊 Kühlpacks:** Büro-Kühlschrank
""")
    
    # Ausdruckbare Version
    st.markdown("---")
    
    if st.button("🖨️ Druckversion erstellen", help="Optimiert für Aushang im Hallenbad"):
        create_printable_rescue_chain()

def save_shift_information(new_content, user_id):
    """Speichert neue Schicht-Informationen"""
    
    if not new_content.strip():
        error_message("❌ Inhalt darf nicht leer sein")
        return
    
    conn = st.session_state.db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Aktualisiere oder erstelle Eintrag
        cursor.execute('''
            INSERT OR REPLACE INTO info_pages 
            (page_key, title, content, last_updated, updated_by)
            VALUES ('schicht_info', 'Schicht-Informationen', ?, ?, ?)
        ''', (new_content, datetime.now().isoformat(), user_id))
        
        conn.commit()
        
        # Audit-Log
        st.session_state.db.log_action(
            user_id,
            'shift_info_updated',
            f'Shift information updated by {st.session_state.current_user["name"]}'
        )
        
        success_message("✅ Schicht-Informationen erfolgreich gespeichert!")
        st.rerun()
        
    except Exception as e:
        error_message(f"❌ Fehler beim Speichern: {str(e)}")
        
    finally:
        conn.close()

def show_last_updated_info(last_updated, updated_by):
    """Zeigt Info über letzte Änderung"""
    
    # Lade Benutzername falls ID vorhanden
    if updated_by:
        user = st.session_state.db.get_user_by_id(updated_by)
        updater_name = user['name'] if user else "Unbekannter Benutzer"
    else:
        updater_name = "System"
    
    # Datum formatieren
    try:
        updated_date = datetime.fromisoformat(last_updated).strftime('%d.%m.%Y %H:%M')
    except:
        updated_date = last_updated
    
    st.markdown("---")
    st.markdown(f"""
📅 **Zuletzt aktualisiert:** {updated_date}  
👤 **Bearbeitet von:** {updater_name}
""")

def create_printable_rescue_chain():
    """Erstellt druckoptimierte Version der Rettungskette"""
    
    printable_content = f"""# 🚨 RETTUNGSKETTE HALLENBAD - NOTFALL-AUSHANG

## SOFORT-MASSNAHMEN:

### 1. 📞 NOTRUF ABSETZEN
**NOTRUF: 112**
- **WO:** Hallenbad [Adresse eintragen]
- **WAS:** Art des Notfalls beschreiben  
- **WIE VIELE:** Anzahl Verletzte
- **WER:** Name des Anrufers
- **WARTEN** auf Rückfragen!

### 2. 🫁 ERSTE HILFE
**Bei Bewusstlosigkeit:**
1. Ansprechen und anfassen
2. Atmung 10 Sekunden prüfen
3. Bei normaler Atmung: Stabile Seitenlage
4. Keine Atmung: Herz-Lungen-Wiederbelebung

**Herz-Lungen-Wiederbelebung:**
- 30 Druckmassagen : 2 Beatmungen
- Frequenz: 100-120/min
- Tiefe: 5-6 cm
- **NICHT AUFHÖREN** bis Hilfe da ist

### 3. ⚡ AED-GERÄT NUTZEN
**Standort:** Eingangsbereich
1. Einschalten (gibt Anweisungen)
2. Elektroden aufkleben  
3. Bei Schock: ALLE ZURÜCKTRETEN

### 4. 🚨 NOTRUF-NUMMERN
- **Notruf:** 112
- **Giftnotruf:** 089 19240
- **Leitung:** [Nummer eintragen]
- **Hausmeister:** [Nummer eintragen]

## ⚠️ MERKSATZ: "PRÜFEN - RUFEN - DRÜCKEN - SCHOCKEN"

*Erstellt: {datetime.now().strftime('%d.%m.%Y')} | Dienstplan+ Cloud v3.0*
"""
    
    # Download-Button für druckbare Version
    st.download_button(
        label="📄 Rettungskette als Textdatei herunterladen",
        data=printable_content,
        file_name=f"rettungskette_aushang_{datetime.now().strftime('%Y%m%d')}.txt",
        mime="text/plain",
        help="Optimiert für Aushang an Pinnwand oder Laminierung"
    )
    
    success_message("📋 Druckversion erstellt - bereit zum Download")

# Zusätzliche Info-Funktionen für Erweiterbarkeit
def show_contact_information():
    """Kontakt-Informationen (erweiterbar)"""
    
    st.markdown("### 📞 Kontakt-Informationen")
    
    # Diese könnten später auch editierbar gemacht werden
    st.markdown("""
**👥 Team-Leitung:**
- Name: [Bitte eintragen]
- E-Mail: [Bitte eintragen]
- Telefon: [Bitte eintragen]

**🏊‍♂️ Schwimmmeister:**
- Name: [Bitte eintragen]
- E-Mail: [Bitte eintragen]
- Telefon: [Bitte eintragen]

**🔧 Technischer Service:**
- Name: [Bitte eintragen]
- E-Mail: [Bitte eintragen]
- Telefon: [Bitte eintragen]

**🏢 Verwaltung:**
- Öffnungszeiten: [Bitte eintragen]
- E-Mail: [Bitte eintragen]
- Telefon: [Bitte eintragen]
""")

def show_operational_hours():
    """Öffnungszeiten und Betriebsinfos (erweiterbar)"""
    
    st.markdown("### 🕐 Öffnungszeiten & Betrieb")
    
    st.markdown("""
**📅 Reguläre Öffnungszeiten:**
- Montag: [Bitte eintragen]
- Dienstag: 17:00 - 20:00 Uhr *(Schichtdienst)*
- Mittwoch: [Bitte eintragen]  
- Donnerstag: [Bitte eintragen]
- Freitag: 17:00 - 20:00 Uhr *(Schichtdienst)*
- Samstag: 14:00 - 17:00 Uhr *(Schichtdienst)*
- Sonntag: [Bitte eintragen]

**🏊‍♂️ Sommerpause:**
- 1. Juni bis 30. September: Geschlossen
- Grund: Wartung und Instandhaltung

**🎄 Feiertage:**
- An bayerischen Feiertagen geschlossen
- Sonderöffnungen nach Ankündigung

**🚨 Notfall-Kontakt:**
- Außerhalb der Öffnungszeiten: 112
""")
    
    st.info("💡 **Hinweis:** Diese Zeiten können sich ändern - aktuelle Infos an der Eingangstür")

# Info-Tab Router (für zukünftige Erweiterungen)
def show_extended_information_tab(user):
    """Erweiterte Informations-Tabs (für zukünftige Versionen)"""
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Schicht-Info", 
        "🚨 Rettungskette", 
        "📞 Kontakte", 
        "🕐 Öffnungszeiten"
    ])
    
    with tab1:
        show_shift_information(user)
    
    with tab2:
        show_rescue_chain(user)
    
    with tab3:
        show_contact_information()
    
    with tab4:
        show_operational_hours()