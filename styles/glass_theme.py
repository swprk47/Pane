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
    background-color: rgba(22, 22, 28, 0.70);
    border-top-left-radius: 18px;
    border-top-right-radius: 18px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

#TitleLabel {
    font-size: 13px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.85);
    letter-spacing: 0.2px;
}

#SubTitleLabel {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.45);
}

/* Title Bar Window Action Buttons */
.TitleButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.75);
    font-size: 13px;
    min-width: 34px;
    min-height: 28px;
    max-width: 34px;
    max-height: 28px;
}

.TitleButton:hover {
    background-color: rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
}

.TitleButton:pressed {
    background-color: rgba(255, 255, 255, 0.20);
}

#CloseButton:hover {
    background-color: #E81123;
    color: #FFFFFF;
}

#CloseButton:pressed {
    background-color: #BF0F1D;
}

/* Floating Glass Capsule & Popups */
.GlassCapsule {
    background-color: rgba(24, 24, 32, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 24px;
}

/* Glass Buttons */
.GlassButton {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    color: #F5F5F7;
    font-size: 12px;
    font-weight: 500;
    padding: 6px 12px;
}

.GlassButton:hover {
    background-color: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.25);
    color: #FFFFFF;
}

.GlassButton:pressed {
    background-color: rgba(255, 255, 255, 0.25);
}

.GlassButton:checked {
    background-color: rgba(10, 132, 255, 0.45);
    border: 1px solid rgba(10, 132, 255, 0.8);
    color: #FFFFFF;
}

/* Accent Badge / Speed Button */
#SpeedButton {
    background-color: rgba(10, 132, 255, 0.22);
    border: 1px solid rgba(10, 132, 255, 0.45);
    border-radius: 10px;
    color: #70B4FF;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
}

#SpeedButton:hover {
    background-color: rgba(10, 132, 255, 0.35);
    border: 1px solid rgba(10, 132, 255, 0.75);
    color: #FFFFFF;
}

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

/* Dropdown / Popups */
#SpeedPopupWidget {
    background-color: rgba(28, 28, 36, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 14px;
}

/* Empty Video Viewport placeholder */
#EmptyNoticeLabel {
    font-size: 15px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.55);
}

#EmptyNoticeSubLabel {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.35);
}
"""
