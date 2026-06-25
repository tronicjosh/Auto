"""Expand the model's extraction JSON into one Descriptions row per section."""

from .util import normalize_ports, normalize_tilt, parse_ports, to_cell_str


def sections_to_rows(data: dict, manufacturer: str = "", model_name: str = "",
                     source: str = "") -> list[dict]:
    """One row dict (keyed by the 18 column headers) per section in the JSON.

    `manufacturer` / `model_name` / `source` are optional values supplied by the caller
    (override box or workflow default); when blank, the manufacturer/model fall back to the
    extraction JSON. `source` is an organisational tag (not on the datasheet), so it is only
    ever taken from the caller — there is no hard-coded default here.
    """
    manufacturer = (manufacturer or to_cell_str(data.get("manufacturer"))).strip()
    # '/' has special meaning to the downstream file-path program, so store it as '-'.
    model = (model_name or to_cell_str(data.get("model"))).strip().replace("/", "-")
    ant_type = to_cell_str(data.get("type"))
    height = to_cell_str(data.get("height_m"))
    width = to_cell_str(data.get("width_m"))
    depth = to_cell_str(data.get("depth_m"))

    rows = []
    for sec in data.get("sections", []):
        ports = normalize_ports(to_cell_str(sec.get("ports")))
        freq = to_cell_str(sec.get("frequency"))
        is_custom = freq.strip().lower() == "custom"
        rows.append({
            "Antenna Source": source,
            "Antenna manufacturer": manufacturer,
            "Model": model,
            "Type": ant_type,
            "Frequency": freq,
            # Min/Max Freq are blank for every named band; only Custom carries Hz values.
            "Min Freq [Hz]": to_cell_str(sec.get("minFreqHz")) if is_custom else "",
            "Max Freq [Hz]": to_cell_str(sec.get("maxFreqHz")) if is_custom else "",
            "Tilts [0,1,2,3]": normalize_tilt(to_cell_str(sec.get("tilts"))),
            "Number of Ports": str(len(parse_ports(ports))),
            "Section Ports": ports,
            "Azimuth Rotation": to_cell_str(sec.get("azimuth")),
            "Gain [dBi]": to_cell_str(sec.get("gain_dbi")),
            "Horizontal HPBW [deg]": to_cell_str(sec.get("hbw_deg")),
            "Vertical HPBW [deg]": to_cell_str(sec.get("vbw_deg")),
            "Height [m]": height,
            "Width/ Diameter [m]": width,
            "Depth/ Spacing [m]": depth,
            "Aperture Diameter [m]": "",  # always blank (parabolic/aperture antennas only)
        })
    return rows
