"""
Glassmorphism style sheet and color tokens for Apple Glass UI on Windows 11.
"""

GLASS_THEME_QSS = """
/* Global Font & Smoothness */
QWidget {
    font-family: "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, "Noto Sans KR", sans-serif;
    color: #F5F5F7;
    outline: none;
}

/* Base Window Background (Translucent for Acrylic/Mica) */
#MainWindowContainer {
    background-color: rgba(18, 18, 24, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 18px;
}

/* Custom Glass Title Bar */
#GlassTitleBar {
    background: transparent;
}

#TitleLabel {
    font-size: 13px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.85);
    letter-spacing: 0.2px;
}

/* (The round / pill buttons are painted by ui/glass_button.py and get no rules here: a class rule for
   them once leaked its font into every pill.) */

/* Glass OSD Notification Badge */
#GlassOSD {
    background-color: rgba(20, 20, 28, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 16px;
    color: #FFFFFF;
    font-size: 16px;
    font-weight: 600;
    padding: 8px 18px;
}

/* Empty Video Viewport placeholder */
#EmptyNoticeLabel {
    font-size: 16px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.88);
}

#EmptyNoticeSubLabel {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.62);
}
"""
