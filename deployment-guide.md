# Dienstplan+ Cloud - Deployment Guide

Eine professionelle, plattformunabhängige Dienstplan-App für 20-30 Nutzer mit einfacher Bereitstellung.

## 🚀 Quick Start

### Demo testen
Öffnen Sie die App: [Dienstplan+ Cloud Demo](https://ppl-ai-code-interpreter-files.s3.amazonaws.com/web/direct-files/0ec9a5b286b2ab03fd277b1e0b9933eb/3f9c7ecd-1fb4-421c-a7a9-943a5c326b98/index.html)

**Demo-Zugänge:**
- **Admin:** Max Mustermann (max.admin@example.com)
- **User:** Anna Schmidt (anna@example.com)

### Features
- ✅ Wöchentliche Slots: Di/Fr 17-20h, Sa 14-17h
- ✅ Admin/User Rollen mit Rechteverwaltung
- ✅ Bayerische Feiertage automatisch gesperrt
- ✅ WhatsApp/SMS Erinnerungen (24h/1h vorher)
- ✅ Kalender Export (iCal/CSV)
- ✅ PWA - installierbar auf alle Geräte
- ✅ Dark/Light Mode
- ✅ Responsive Design

## 📱 Installation als App

### iOS/Android
1. App im Browser öffnen
2. **iOS:** "Teilen" → "Zum Home-Bildschirm"
3. **Android:** "Menü" → "App installieren"

### Desktop
- **Chrome/Edge:** Adressleiste → App-Symbol klicken
- **Safari:** Menü → "Zu Apps hinzufügen"

## 🐳 Docker Deployment

### Lokaler Start
```bash
# Repository klonen/downloaden
git clone <repo-url> oder ZIP entpacken

# Docker Container starten
docker build -t dienstplan-cloud .
docker run -d -p 8080:80 --name dienstplan dienstplan-cloud

# App öffnen
http://localhost:8080
```

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'
services:
  dienstplan:
    build: .
    ports:
      - "8080:80"
    environment:
      - NODE_ENV=production
    restart: unless-stopped
    
  # Optional: Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - dienstplan
```

**Starten:**
```bash
docker-compose up -d
```

## ☁️ Kostenlose Cloud-Bereitstellung

### Option 1: Streamlit Community Cloud (Empfohlen)
```python
# streamlit_app.py - Streamlit Version erstellen
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Dienstplan+ Cloud",
    page_icon="📅",
    layout="wide"
)

# Haupt-App Code hier...
```

**Deployment Schritte:**
1. Code in GitHub Repository pushen
2. [share.streamlit.io](https://share.streamlit.io) besuchen
3. "New app" → Repository/Branch wählen
4. App automatisch deployen lassen

**Requirements (requirements.txt):**
```
streamlit>=1.28.0
pandas>=1.5.0
plotly>=5.15.0
```

### Option 2: Render.com (Free Tier)
```yaml
# render.yaml
services:
  - type: web
    name: dienstplan-cloud
    env: node
    buildCommand: npm install && npm run build
    startCommand: npm run preview
    plan: free
```

**Deployment:**
1. Repository mit Render verbinden
2. Einstellungen konfigurieren
3. Automatisches Deployment

### Option 3: Netlify (Static Hosting)
```toml
# netlify.toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

**Deployment:**
1. ZIP-Datei auf netlify.com hochladen
2. Oder Git Repository verbinden
3. Automatisches Deployment

## 🔧 VPS/Server Deployment

### Nginx Konfiguration
```nginx
# /etc/nginx/sites-available/dienstplan
server {
    listen 80;
    server_name ihre-domain.de;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### SSL mit Certbot
```bash
# SSL Zertifikat installieren
sudo certbot --nginx -d ihre-domain.de
```

### Systemd Service
```ini
# /etc/systemd/system/dienstplan.service
[Unit]
Description=Dienstplan+ Cloud App
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/dienstplan
ExecStart=/usr/bin/docker run --rm -p 8080:80 dienstplan-cloud
Restart=always

[Install]
WantedBy=multi-user.target
```

**Service aktivieren:**
```bash
sudo systemctl enable dienstplan
sudo systemctl start dienstplan
```

## 📊 WhatsApp/SMS Integration (Produktiv)

### WhatsApp Business API
```javascript
// Beispiel BSP Integration
const whatsappConfig = {
  apiKey: process.env.WHATSAPP_API_KEY,
  baseUrl: 'https://api.messagebird.com/v1/',
  templates: {
    reminder_24h: 'reminder_24_hours_de',
    reminder_1h: 'reminder_1_hour_de'
  }
};
```

**Template Beispiele (zur Freigabe bei Meta):**
```
Name: reminder_24_hours_de
Text: Hallo {{1}}! Erinnerung: Du hast morgen eine Schicht am {{2}} von {{3}}. Bei Fragen antworte einfach.

Name: reminder_1_hour_de  
Text: Hi {{1}}! In einer Stunde beginnt deine Schicht: {{2}} {{3}}. Bis gleich!
```

### SMS Fallback (Twilio)
```javascript
const twilioConfig = {
  accountSid: process.env.TWILIO_ACCOUNT_SID,
  authToken: process.env.TWILIO_AUTH_TOKEN,
  messagingServiceSid: process.env.TWILIO_MSG_SERVICE_SID
};
```

## 🗄️ Datenbank Integration (Optional)

### PostgreSQL mit Prisma
```prisma
// schema.prisma
model User {
  id        Int      @id @default(autoincrement())
  name      String
  email     String   @unique
  phone     String
  role      Role
  active    Boolean  @default(true)
  bookings  Booking[]
  createdAt DateTime @default(now())
}

model Booking {
  id     Int    @id @default(autoincrement())
  userId Int
  user   User   @relation(fields: [userId], references: [id])
  slotId Int
  date   String
  status Status @default(CONFIRMED)
}
```

### Migration Commands
```bash
# Datenbank initialisieren
npx prisma migrate dev --name init

# Schema aktualisieren
npx prisma db push

# Seed-Daten laden
npx prisma db seed
```

## 🔍 Monitoring & Analytics

### Health Check Endpoint
```javascript
// /health Route
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    version: process.env.APP_VERSION || '1.0.0'
  });
});
```

### Einfache Metriken
```javascript
// Basis Logging
const metrics = {
  activeUsers: 0,
  totalBookings: 0,
  dailyBookings: 0,
  errorRate: 0
};
```

## 🛠️ Entwicklung & Anpassung

### Lokale Entwicklung
```bash
# Abhängigkeiten installieren
npm install

# Development Server starten
npm run dev

# Production Build testen
npm run build && npm run preview
```

### Umgebungsvariablen (.env)
```env
# App Konfiguration
NODE_ENV=production
PORT=3000
APP_VERSION=2.0.0

# WhatsApp API
WHATSAPP_API_KEY=your_api_key
WHATSAPP_BASE_URL=https://api.messagebird.com/v1/

# SMS Fallback
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token

# Optional: Datenbank
DATABASE_URL=postgresql://user:pass@localhost:5432/dienstplan

# Optional: Analytics
ANALYTICS_ENABLED=false
```

### Anpassungen
- **Farben:** CSS-Variablen in `style.css` anpassen
- **Zeitslots:** `weeklySlots` Array in `app.js` erweitern
- **Feiertage:** `bavarianHolidays` Array aktualisieren
- **Templates:** `reminderTemplates` Texte ändern

## 📋 Checkliste Produktiv-Deployment

- [ ] Domain registriert und DNS konfiguriert
- [ ] SSL-Zertifikat installiert (Let's Encrypt)
- [ ] Backup-Strategie implementiert
- [ ] WhatsApp Business API Account erstellt
- [ ] Templates bei Meta eingereicht und genehmigt
- [ ] SMS-Provider Account eingerichtet
- [ ] Monitoring/Logging aktiviert
- [ ] DSGVO-Dokumentation erstellt
- [ ] Nutzer-Onboarding vorbereitet
- [ ] Support-Kontakt definiert

## 🆘 Troubleshooting

### Häufige Probleme

**App lädt nicht:**
```bash
# Docker Logs prüfen
docker logs dienstplan

# Port-Konflikte prüfen
netstat -tulpn | grep :8080
```

**WhatsApp Templates nicht genehmigt:**
- Templates müssen exakt der Vorlage entsprechen
- Variablen {{1}}, {{2}}, {{3}} verwenden
- Business-Verifizierung abgeschlossen

**Performance bei 30+ Nutzern:**
- Redis für Session-Storage
- CDN für statische Assets
- Load Balancer bei Bedarf

### Support
- GitHub Issues für Bugs/Features
- E-Mail: support@ihre-domain.de
- Wiki/FAQ für häufige Fragen

## 📄 Lizenz

MIT License - Frei für kommerzielle und private Nutzung.

---

**Dienstplan+ Cloud v2.0** - Professionelle Dienstplanung leicht gemacht! 🚀