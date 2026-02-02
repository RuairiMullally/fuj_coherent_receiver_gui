"""CSS styles and theme constants for the Dash UI."""

# Color scheme
COLORS = {
    "primary": "#0066cc",
    "secondary": "#6c757d",
    "success": "#28a745",
    "danger": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8",
    "light": "#f8f9fa",
    "dark": "#343a40",
}

# Component styles
SLIDER_STYLE = {
    "marginBottom": "10px",
}

VALUE_DISPLAY_STYLE = {
    "fontFamily": "monospace",
    "fontSize": "1.2em",
    "fontWeight": "bold",
    "textAlign": "right",
    "paddingRight": "10px",
}

CHANNEL_LABEL_STYLE = {
    "fontWeight": "bold",
    "paddingLeft": "10px",
}

HEADER_STYLE = {
    "textAlign": "center",
    "marginTop": "20px",
    "marginBottom": "30px",
    "color": COLORS["dark"],
}

CONTAINER_STYLE = {
    "maxWidth": "900px",
    "marginTop": "20px",
}
