"""
Global stylesheet and palette for the app.
Steam-adjacent dark theme: deep charcoal base, steel-blue accents,
clean Inter/system sans-serif throughout.
"""

PALETTE = {
    "bg_deep": "#0f1114",
    "bg_surface": "#1a1d23",
    "bg_card": "#21252e",
    "bg_card_hover": "#272c37",
    "bg_card_sel": "#1e3a5f",
    "accent": "#4a90d9",
    "accent_dim": "#2d5f99",
    "text_primary": "#e8eaf0",
    "text_secondary": "#8b93a7",
    "text_muted": "#525a6b",
    "border": "#2e3340",
    "border_accent": "#4a90d9",
    "success": "#4caf7d",
    "warning": "#e8a838",
    "danger": "#e05252",
}

APP_STYLESHEET = f"""
    QWidget {{
        background-color: {PALETTE['bg_deep']};
        color: {PALETTE['text_primary']};
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 13px;
        outline: none;  /* Remove focus outline for a cleaner look */
    }}

    QScrollArea {{
        border: none;
        background: transparent;
        outline: none;  /* Remove focus outline for a cleaner look */
    }}

    QScrollBar:vertical {{
        background-color: {PALETTE['bg_surface']};
        width: 12px;
        margin: 0px;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background-color: {PALETTE['text_muted']};
        border-radius: 3px; 
        min-height: 40px;
        margin: 2px 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {PALETTE['text_secondary']};
    }}


    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QPushButton {{
        background-color: {PALETTE['accent']};
        color: {PALETTE['text_primary']};
        border: none;
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 13px;
        font-weight: 600;
        outline: none;  /* Remove focus outline for a cleaner look */
    }}

    QPushButton:hover {{
        background-color: #5aa0e8;
    }}

    QPushButton:pressed {{
        background-color: {PALETTE['accent_dim']};
    }}

    
    QPushButton:disabled {{
        background-color: {PALETTE['bg_card']};
        color: {PALETTE['text_muted']};
    }}

    QPushButton#secondary {{
        background-color: {PALETTE['bg_card']};
        color: {PALETTE['text_secondary']};
        border: 1px solid {PALETTE['border']};
        padding: 4px 15px;
    }}

    QPushButton#secondary:hover {{
        background-color: {PALETTE['bg_card_hover']};
        color: {PALETTE['text_primary']};
    }}

    QLineEdit {{
        background-color: {PALETTE['bg_surface']};
        color: {PALETTE['text_primary']};
        border: 1px solid {PALETTE['border']};
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: {PALETTE['accent']};
    }}

    QLineEdit:focus {{
        border-color: {PALETTE['accent']};
    }}

    QLabel#heading {{
        font-size: 22px;
        font-weight: 700;
        color: {PALETTE['text_primary']};
    }}

    QLabel#subheading {{
        font-size: 14px;
        color: {PALETTE['text_secondary']};
    }}

    QLabel#muted {{
        font-size: 12px;
        color: {PALETTE['text_muted']};
    }}

    QCheckBox {{
        color: {PALETTE['text_secondary']};
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid {PALETTE['border']};
        background-color: {PALETTE['bg_surface']};
    }}

    QCheckBox::indicator:hover {{
        border: 1px solid {PALETTE['accent']};
    }}

    QCheckBox::indicator:checked {{
        background-color: {PALETTE['accent']};
        border: 1px solid {PALETTE['accent']};
        /* We'll use a simple Unicode-like checkmark style via border/background */
    }}
"""
