"""Apple/macOS-style CSS constants and style injection for NiceGUI."""
from __future__ import annotations

from nicegui import ui


def add_styles() -> None:
    """Inject global CSS styles into the NiceGUI app."""
    ui.add_css("""
        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
        }

        body {
            background: #F5F5F7;
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
            margin-bottom: 16px;
        }

        .section-header {
            color: #1D1D1F;
            font-size: 17px;
            font-weight: 600;
        }

        .sublabel {
            color: #86868B;
            font-size: 13px;
        }

        .chip-blue {
            background: #E3F0FF;
            color: #007AFF;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            display: inline-block;
        }

        .chip-green {
            background: #E3F9E5;
            color: #28A745;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            display: inline-block;
        }

        .chip-orange {
            background: #FFF3E0;
            color: #FF9500;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            display: inline-block;
        }

        .chip-red {
            background: #FFEBEB;
            color: #FF3B30;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            display: inline-block;
        }

        .file-box {
            background: #F2F2F7;
            border-radius: 8px;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .btn-primary {
            background: #007AFF;
            color: white;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-family: inherit;
        }

        .btn-secondary {
            border: 1px solid #007AFF;
            color: #007AFF;
            border-radius: 8px;
            background: transparent;
            cursor: pointer;
            font-family: inherit;
        }

        .progress-label {
            color: #86868B;
            font-size: 13px;
        }
    """)
