"""Platform-independent panel placement helpers."""


def top_attached_panel_positions(
    screen_x, screen_y, screen_width, panel_width, panel_height
):
    """Return hidden and visible coordinates for a top-attached centered panel."""
    x = screen_x + (screen_width - panel_width) // 2
    return (x, screen_y - panel_height), (x, screen_y)
