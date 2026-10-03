"""
Single source of truth for the app's colors: soft "Serenity" blue.

The logo has its own colors (tools/make_icons.py) and no longer follows this accent.
Most QSS strings in ui/ spell the colors
out as literals; tests/test_branding.py fails if a legacy accent literal sneaks
back in, so a future color change is: edit this file and replace the literals
(LEGACY_ACCENT_LITERALS lists the previous sets).
"""
# ---- accent: Serenity (progress, pins, speed text, highlights)
ACCENT = "#B3CEE5"
ACCENT_RGB = "179, 206, 229"        # same, for rgba(...) in QSS
ACCENT_LIGHT = "#D0E1EF"            # lighter tone: text on tinted fills, rims
ACCENT_LIGHT_RGB = "208, 225, 239"
ACCENT_HOVER = "#C2D8EA"            # hover state of accent-filled elements
ACCENT_PALE = "#F0F6FB"             # very light tone (slider handle hover)
ON_ACCENT = "#16212E"               # text on a SOLID accent fill (white is unreadable on a pale accent)
MUTED_ICON = "#93A8BC"              # desaturated grey-blue for large decorative icons

# Literals of previous accents; the regression test asserts none is left in the source.
LEGACY_ACCENT_LITERALS = (
    # original blue
    "#0A84FF", "10, 132, 255", "#70B4FF", "112, 180, 255",
    "#5AA9FF", "#3D9BFF", "#8EC5FF", "#CFE6FF",
    # first violet (too saturated)
    "#8B7BFF", "139, 123, 255", "#B7ADFF", "183, 173, 255", "#A295FF", "#E8E5FF", "#9D98CF",
    # periwinkle
    "#B3B3FF", "179, 179, 255", "#D6D6FF", "214, 214, 255", "#C4C4FF", "#EEEEFF", "#A3A3C8", "#1C1C2B",
)
