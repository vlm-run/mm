"""mm Gradio theme — VLM Run brand.

Brand tokens are routed through Gradio's native theme variables so they
propagate into every component without ``!important`` overrides. Light
and ``_dark`` variants are pinned to the same values to lock the
appearance regardless of the user's system theme.
"""

from __future__ import annotations

import gradio as gr

BG = "#F5FAFF"  # page background — very pale blue
SURFACE = "#FFFFFF"  # cards / panels
SURFACE_TINT = "#E6EDFC"  # subtle fill (chips, zebra rows)
BORDER = "#D5E2F7"
BORDER_STRONG = "#AAC2EC"
TEXT_PRIMARY = "#010917"  # near-black navy
TEXT_SECONDARY = "#596983"
TEXT_MUTED = "#A29F9F"
ACCENT = "#1E5ACA"  # primary brand blue
ACCENT_DEEP = "#102955"
ACCENT_HOVER = "#2756A8"
ACCENT_BRIGHT = "#4E8CFF"
ACCENT_SOFT = "#749ADF"


def build_theme() -> gr.themes.Base:
    """Return the mm theme — a tuned ``gr.themes.Soft`` in the brand palette."""
    return gr.themes.Soft(
        primary_hue=gr.themes.Color(
            c50=BG,
            c100=SURFACE_TINT,
            c200=BORDER,
            c300=BORDER_STRONG,
            c400=ACCENT_SOFT,
            c500=ACCENT_BRIGHT,
            c600=ACCENT,
            c700=ACCENT_HOVER,
            c800=ACCENT_DEEP,
            c900=ACCENT_DEEP,
            c950=TEXT_PRIMARY,
        ),
        neutral_hue=gr.themes.Color(
            c50=BG,
            c100=SURFACE_TINT,
            c200=BORDER,
            c300=BORDER_STRONG,
            c400=TEXT_MUTED,
            c500=TEXT_SECONDARY,
            c600=TEXT_SECONDARY,
            c700=TEXT_PRIMARY,
            c800=TEXT_PRIMARY,
            c900=TEXT_PRIMARY,
            c950=TEXT_PRIMARY,
        ),
        radius_size=gr.themes.sizes.radius_md,
        font=[
            gr.themes.GoogleFont("Geist"),
            gr.themes.GoogleFont("Inter"),
            "system-ui",
            "-apple-system",
            "BlinkMacSystemFont",
            "Segoe UI",
            "sans-serif",
        ],
    ).set(
        # body
        body_background_fill=BG,
        body_background_fill_dark=BG,
        body_text_color=TEXT_PRIMARY,
        body_text_color_dark=TEXT_PRIMARY,
        body_text_color_subdued=TEXT_SECONDARY,
        body_text_color_subdued_dark=TEXT_SECONDARY,
        background_fill_primary=BG,
        background_fill_primary_dark=BG,
        background_fill_secondary=SURFACE_TINT,
        background_fill_secondary_dark=SURFACE_TINT,
        # blocks / panels — white surfaces on the pale-blue page
        block_background_fill=SURFACE,
        block_background_fill_dark=SURFACE,
        block_border_color=BORDER,
        block_border_color_dark=BORDER,
        block_border_width="1px",
        block_radius="14px",
        block_label_background_fill="transparent",
        block_label_background_fill_dark="transparent",
        block_label_text_color=TEXT_PRIMARY,
        block_label_text_color_dark=TEXT_PRIMARY,
        block_title_background_fill="transparent",
        block_title_background_fill_dark="transparent",
        block_title_text_color=TEXT_PRIMARY,
        block_title_text_color_dark=TEXT_PRIMARY,
        block_title_text_weight="500",
        block_info_text_color=TEXT_SECONDARY,
        block_info_text_color_dark=TEXT_SECONDARY,
        panel_background_fill=SURFACE,
        panel_background_fill_dark=SURFACE,
        panel_border_color=BORDER,
        panel_border_color_dark=BORDER,
        # inputs (text colour comes from body_text_color)
        input_background_fill=SURFACE,
        input_background_fill_dark=SURFACE,
        input_background_fill_focus=SURFACE,
        input_background_fill_focus_dark=SURFACE,
        input_placeholder_color=TEXT_MUTED,
        input_placeholder_color_dark=TEXT_MUTED,
        input_border_color=BORDER,
        input_border_color_dark=BORDER,
        input_border_color_focus=ACCENT,
        input_border_color_focus_dark=ACCENT,
        input_radius="10px",
        # primary buttons (brand blue → darker blue on hover)
        button_primary_background_fill=ACCENT,
        button_primary_background_fill_dark=ACCENT,
        button_primary_background_fill_hover=ACCENT_HOVER,
        button_primary_background_fill_hover_dark=ACCENT_HOVER,
        button_primary_text_color=SURFACE,
        button_primary_text_color_dark=SURFACE,
        button_primary_text_color_hover=SURFACE,
        button_primary_text_color_hover_dark=SURFACE,
        button_primary_border_color=ACCENT,
        button_primary_border_color_dark=ACCENT,
        # secondary buttons (tint → border on hover)
        button_secondary_background_fill=SURFACE_TINT,
        button_secondary_background_fill_dark=SURFACE_TINT,
        button_secondary_background_fill_hover=BORDER,
        button_secondary_background_fill_hover_dark=BORDER,
        button_secondary_text_color=TEXT_PRIMARY,
        button_secondary_text_color_dark=TEXT_PRIMARY,
        button_secondary_text_color_hover=TEXT_PRIMARY,
        button_secondary_text_color_hover_dark=TEXT_PRIMARY,
        button_secondary_border_color=BORDER,
        button_secondary_border_color_dark=BORDER,
        # cancel / destructive
        button_cancel_background_fill=SURFACE_TINT,
        button_cancel_background_fill_dark=SURFACE_TINT,
        button_cancel_background_fill_hover="#FDECEC",
        button_cancel_background_fill_hover_dark="#FDECEC",
        button_cancel_text_color=TEXT_PRIMARY,
        button_cancel_text_color_dark=TEXT_PRIMARY,
        button_cancel_text_color_hover="#B00020",
        button_cancel_text_color_hover_dark="#B00020",
        button_cancel_border_color=BORDER,
        button_cancel_border_color_dark=BORDER,
        # rounded buttons
        button_large_radius="10px",
        button_small_radius="8px",
        # borders
        border_color_primary=BORDER,
        border_color_primary_dark=BORDER,
        border_color_accent=ACCENT,
        border_color_accent_dark=ACCENT,
        # accent
        color_accent=ACCENT,
        color_accent_soft=ACCENT_SOFT,
        link_text_color=ACCENT,
        link_text_color_dark=ACCENT,
        link_text_color_hover=ACCENT_HOVER,
        link_text_color_hover_dark=ACCENT_HOVER,
        link_text_color_active=ACCENT_DEEP,
        link_text_color_active_dark=ACCENT_DEEP,
        link_text_color_visited=ACCENT_DEEP,
        link_text_color_visited_dark=ACCENT_DEEP,
    )
