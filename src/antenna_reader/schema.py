"""The output contract: the 18 Descriptions columns, their order, and types.

These must match `Descriptions` row 1 in the workbook exactly (verbatim text/order).
"""

COLUMNS = [
    "Antenna Source",          # A  from the source vocabulary (e.g. EMSS / NAD), user-selectable
    "Antenna manufacturer",    # B
    "Model",                   # C
    "Type",                    # D  controlled vocab
    "Frequency",               # E  controlled vocab
    "Min Freq [Hz]",           # F  numeric, only when Frequency = Custom
    "Max Freq [Hz]",           # G  numeric, only when Frequency = Custom
    "Tilts [0,1,2,3]",         # H  text, e.g. "2 to 20"
    "Number of Ports",         # I  numeric (count of Section Ports)
    "Section Ports",           # J  text, e.g. "1,2,5,6"
    "Azimuth Rotation",        # K  numeric (may be negative)
    "Gain [dBi]",              # L  numeric
    "Horizontal HPBW [deg]",   # M  numeric
    "Vertical HPBW [deg]",     # N  numeric
    "Height [m]",              # O  numeric
    "Width/ Diameter [m]",     # P  numeric
    "Depth/ Spacing [m]",      # Q  numeric
    "Aperture Diameter [m]",   # R  numeric, normally blank
]

# Columns whose values are written as real numbers (<v>) rather than inline strings.
# Everything else is text. Blank values are written as an empty cell regardless.
NUMERIC_COLUMNS = frozenset({
    "Min Freq [Hz]",
    "Max Freq [Hz]",
    "Number of Ports",
    "Azimuth Rotation",
    "Gain [dBi]",
    "Horizontal HPBW [deg]",
    "Vertical HPBW [deg]",
    "Height [m]",
    "Width/ Diameter [m]",
    "Depth/ Spacing [m]",
    "Aperture Diameter [m]",
})

def column_letter(index_1based: int) -> str:
    """1 -> 'A', 2 -> 'B', ... (only needs to cover the 18 columns A..R)."""
    return chr(ord("A") + index_1based - 1)
