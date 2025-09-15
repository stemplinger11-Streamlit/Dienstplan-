"""
Dienstplan+ Cloud v3.0 - CSS Styling
Kompaktes, responsives Design mit hohen Kontrasten
"""
import streamlit as st

def apply_css():
    """Anwenden des kompletten App-Stylings"""
    
    css = """
    <style>
    /* ===== GLOBAL RESET ===== */
    .stApp > header { display: none; }
    div[data-testid="stToolbar"] { visibility: hidden; height: 0%; position: fixed; }
    div[data-testid="stDecoration"] { visibility: hidden; height: 0%; position: fixed; }
    div[data-testid="stStatusWidget"] { visibility: hidden; height: 0%; position: fixed; }
    #MainMenu { visibility: hidden; height: 0%; }
    header[data-testid="stHeader"] { visibility: hidden; height: 0%; }
    footer { visibility: hidden; height: 0%; }
    
    /* ===== LAYOUT ===== */
    .main > div { padding-top: 1rem; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    
    /* ===== BUTTONS ===== */
    .stButton > button {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 600;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(30, 64, 175, 0.2);
        font-size: 0.95rem;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
        transform: translateY(-1px);
    }
    
    .stButton > button:active {
        transform: translateY(0);
        box-shadow: 0 2px 4px rgba(30, 64, 175, 0.2);
    }
    
    /* ===== WOCHENKOPF ===== */
    .week-header {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin: 1.5rem 0;
        box-shadow: 0 8px 32px rgba(30, 64, 175, 0.3);
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    
    .week-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, rgba(255,255,255,0.1) 25%, transparent 25%, transparent 75%, rgba(255,255,255,0.1) 75%), 
                    linear-gradient(45deg, rgba(255,255,255,0.1) 25%, transparent 25%, transparent 75%, rgba(255,255,255,0.1) 75%);
        background-size: 20px 20px;
        background-position: 0 0, 10px 10px;
        opacity: 0.5;
    }
    
    .week-header h2 {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        position: relative;
        z-index: 1;
    }
    
    .week-header .calendar-week {
        font-size: 1.3rem;
        font-weight: 600;
        margin-top: 0.5rem;
        opacity: 0.95;
        position: relative;
        z-index: 1;
    }
    
    /* ===== KARTEN-SYSTEM ===== */
    .shift-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1rem 0;
        box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        position: relative;
        border-left: 6px solid transparent;
    }
    
    .shift-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    }
    
    .shift-card h4 {
        margin: 0 0 0.5rem 0;
        font-size: 1.2rem;
        font-weight: 700;
        color: #1e293b;
    }
    
    .available-slot {
        border-left-color: #16a34a;
        background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
    }
    
    .available-slot h4 { color: #15803d; }
    
    .booked-slot {
        border-left-color: #f59e0b;
        background: linear-gradient(135deg, #fefbf2 0%, #ffffff 100%);
    }
    
    .booked-slot h4 { color: #d97706; }
    
    .user-slot {
        border-left-color: #2563eb;
        background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
    }
    
    .user-slot h4 { color: #1d4ed8; }
    
    .holiday-card {
        border-left-color: #dc2626;
        background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
        color: #991b1b;
    }
    
    .holiday-card h4 { color: #991b1b; }
    
    .closed-card {
        border-left-color: #6b7280;
        background: linear-gradient(135deg, #f9fafb 0%, #ffffff 100%);
        color: #374151;
        text-align: center;
        padding: 2rem;
    }
    
    .closed-card h4 { color: #374151; }
    
    /* ===== FAVORITEN-STERN ===== */
    .favorite-star {
        position: absolute;
        top: 1rem;
        right: 1rem;
        font-size: 1.5rem;
        cursor: pointer;
        transition: all 0.3s ease;
        z-index: 10;
    }
    
    .favorite-star:hover { transform: scale(1.3); }
    
    .favorite-star.active {
        color: #fbbf24;
        text-shadow: 0 0 8px rgba(251, 191, 36, 0.6);
        filter: drop-shadow(0 0 4px rgba(251, 191, 36, 0.8));
    }
    
    .favorite-star.inactive {
        color: #d1d5db;
        opacity: 0.7;
    }
    
    /* ===== INFO-KARTEN ===== */
    .info-card {
        padding: 1.25rem;
        border-radius: 8px;
        margin: 0.75rem 0;
        font-weight: 500;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-left: 4px solid;
    }
    
    .info-card h4 {
        margin: 0 0 0.5rem 0;
        font-size: 1.1rem;
        font-weight: 700;
    }
    
    .info-card p {
        margin: 0.25rem 0;
        line-height: 1.4;
    }
    
    .info-card.primary {
        background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
        border-left-color: #3b82f6;
        color: #1e40af;
    }
    
    .info-card.success {
        background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
        border-left-color: #16a34a;
        color: #15803d;
    }
    
    .info-card.warning {
        background: linear-gradient(135deg, #fefbf2 0%, #ffffff 100%);
        border-left-color: #f59e0b;
        color: #d97706;
    }
    
    .info-card.danger {
        background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
        border-left-color: #dc2626;
        color: #991b1b;
    }
    
    /* ===== WATCHLIST ===== */
    .watchlist-item {
        background: linear-gradient(135deg, #fffbeb 0%, #ffffff 100%);
        border: 2px solid #fbbf24;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        position: relative;
        transition: all 0.3s ease;
    }
    
    .watchlist-item:hover {
        box-shadow: 0 4px 12px rgba(251, 191, 36, 0.2);
        transform: translateY(-1px);
    }
    
    .watchlist-item.available {
        border-color: #16a34a;
        background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
    }
    
    .watchlist-item.booked {
        border-color: #dc2626;
        background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
    }
    
    .watchlist-item h5 {
        margin: 0 0 0.25rem 0;
        font-weight: 700;
        color: #1e293b;
    }
    
    /* ===== ADMIN-BEREICHE ===== */
    .admin-section {
        background: linear-gradient(135deg, #fef7cd 0%, #fbbf24 20%, #ffffff 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 2px solid #f59e0b;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.2);
    }
    
    .admin-section h4 {
        color: #92400e;
        margin: 0 0 1rem 0;
        font-weight: 700;
    }
    
    /* ===== SPEZIELLE BUTTONS ===== */
    .sick-button button {
        background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%) !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    .sick-button button:hover {
        background: linear-gradient(135deg, #b91c1c 0%, #dc2626 100%) !important;
        transform: translateY(-1px);
    }
    
    .admin-action-button button {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%) !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    .admin-action-button button:hover {
        background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%) !important;
    }
    
    .test-button button {
        background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    .test-button button:hover {
        background: linear-gradient(135deg, #047857 0%, #059669 100%) !important;
    }
    
    /* ===== KALENDER-LEGENDE ===== */
    .calendar-legend {
        display: flex;
        gap: 1rem;
        margin: 1rem 0;
        flex-wrap: wrap;
        justify-content: center;
    }
    
    .legend-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: white;
        border-radius: 8px;
        border: 2px solid #e5e7eb;
        font-size: 0.875rem;
        font-weight: 500;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        box-shadow: 0 0 4px rgba(0,0,0,0.2);
    }
    
    .free-dot { background-color: #16a34a; }
    .partial-dot { background-color: #f59e0b; }
    .booked-dot { background-color: #dc2626; }
    .holiday-dot { background-color: #7c2d12; }
    .closed-dot { background-color: #6b7280; }
    
    /* ===== NACHRICHTEN ===== */
    .success-message {
        padding: 1rem;
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border: 2px solid #16a34a;
        border-radius: 8px;
        color: #15803d;
        font-weight: 500;
        margin: 1rem 0;
    }
    
    .error-message {
        padding: 1rem;
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        border: 2px solid #dc2626;
        border-radius: 8px;
        color: #991b1b;
        font-weight: 500;
        margin: 1rem 0;
    }
    
    .warning-message {
        padding: 1rem;
        background: linear-gradient(135deg, #fefbf2 0%, #fef3c7 100%);
        border: 2px solid #f59e0b;
        border-radius: 8px;
        color: #d97706;
        font-weight: 500;
        margin: 1rem 0;
    }
    
    /* ===== TABS ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #f8fafc;
        padding: 0.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: white;
        border-radius: 8px;
        color: #64748b;
        font-weight: 600;
        border: 2px solid #e2e8f0;
        padding: 0.75rem 1.5rem;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white;
        border-color: #1e40af;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
    }
    
    /* ===== FORMULARE ===== */
    .stTextInput > div > div > input {
        border: 2px solid #e5e7eb;
        border-radius: 8px;
        padding: 0.75rem;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
    
    .stSelectbox > div > div > div {
        border: 2px solid #e5e7eb;
        border-radius: 8px;
    }
    
    /* ===== MOBILE RESPONSIVE ===== */
    @media (max-width: 768px) {
        .week-header {
            padding: 1.5rem 1rem;
        }
        
        .week-header h2 {
            font-size: 1.5rem;
        }
        
        .shift-card {
            padding: 1rem;
            margin: 0.75rem 0;
        }
        
        .info-card {
            padding: 1rem;
        }
        
        .calendar-legend {
            flex-direction: column;
            align-items: center;
        }
        
        .legend-item {
            min-width: 150px;
            justify-content: center;
        }
        
        .favorite-star {
            font-size: 1.25rem;
            top: 0.75rem;
            right: 0.75rem;
        }
    }
    
    /* ===== EXPANDER STYLING ===== */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border-radius: 8px;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border: 2px solid #cbd5e1;
        font-weight: 600;
    }
    
    .streamlit-expanderContent {
        background: #fefefe;
        border: 2px solid #e2e8f0;
        border-top: none;
        border-radius: 0 0 8px 8px;
        padding: 1rem;
    }
    
    /* ===== KALENDER CONTAINER ===== */
    .calendar-container {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        margin: 1rem 0;
        border: 2px solid #e5e7eb;
    }
    
    /* ===== AUDIT LOG ===== */
    .audit-entry {
        background: #f8fafc;
        border-left: 4px solid #64748b;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        font-family: monospace;
        font-size: 0.875rem;
    }
    
    .audit-entry.admin-action {
        border-left-color: #f59e0b;
        background: #fefbf2;
    }
    
    .audit-entry.user-action {
        border-left-color: #3b82f6;
        background: #eff6ff;
    }
    
    .audit-entry.system-action {
        border-left-color: #6b7280;
        background: #f9fafb;
    }
    
    /* ===== SCROLLBARS ===== */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f5f9;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #94a3b8;
    }
    
    /* ===== DARK MODE SUPPORT ===== */
    @media (prefers-color-scheme: dark) {
        .shift-card, .info-card, .watchlist-item {
            background: #1e293b;
            color: #f1f5f9;
            border-color: #475569;
        }
        
        .calendar-container {
            background: #1e293b;
            border-color: #475569;
        }
        
        .legend-item {
            background: #334155;
            border-color: #475569;
            color: #f1f5f9;
        }
        
        .audit-entry {
            background: #334155;
            color: #e2e8f0;
        }
    }
    </style>
    """
    
    st.markdown(css, unsafe_allow_html=True)