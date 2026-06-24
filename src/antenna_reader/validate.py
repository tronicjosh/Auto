"""Validation rules. Vocabularies are passed in (read live from the workbook),
not hard-coded. Returns one flag dict per row: {column: message}. Empty dict = clean.
"""

import math

from .util import parse_ports, parse_tilt_range, to_float


def validate_rows(rows: list[dict], vocab: dict) -> list[dict]:
    """Flag cells that fail validation. Non-blocking — flags are advisory.

    `vocab` must provide "frequency" and "type" lists (from vocab.read_vocabularies).
    """
    freq_vocab = set(vocab.get("frequency", []))
    type_vocab = set(vocab.get("type", []))

    flags = [dict() for _ in rows]
    freq_ports = {}  # Frequency value -> [(row_index, ports), ...]

    for i, row in enumerate(rows):
        flag = flags[i]

        freq = row.get("Frequency", "").strip()
        if freq and freq not in freq_vocab:
            flag["Frequency"] = "Not in Frequency vocabulary"

        ant_type = row.get("Type", "").strip()
        if ant_type and ant_type not in type_vocab:
            flag["Type"] = "Not in Type vocabulary"

        # Number of Ports must equal the count in Section Ports.
        ports = parse_ports(row.get("Section Ports", ""))
        declared = row.get("Number of Ports", "").strip()
        if declared != str(len(ports)):
            flag["Number of Ports"] = f"Expected {len(ports)} (count of Section Ports)"

        # Min/Max Freq only meaningful when Frequency == Custom.
        if freq != "Custom":
            if row.get("Min Freq [Hz]", "").strip():
                flag["Min Freq [Hz]"] = "Only used when Frequency = Custom"
            if row.get("Max Freq [Hz]", "").strip():
                flag["Max Freq [Hz]"] = "Only used when Frequency = Custom"

        # Tilt range: low <= high, both >= 0.
        tilts_raw = row.get("Tilts [0,1,2,3]", "").strip()
        if tilts_raw and "," in tilts_raw:  # discrete tilt options, e.g. "2,6,10"
            vals = [to_float(v) for v in tilts_raw.split(",")]
            if any(v is None for v in vals):
                flag["Tilts [0,1,2,3]"] = "Unparseable tilt value"
            elif any(v < 0 for v in vals):
                flag["Tilts [0,1,2,3]"] = "Tilt must be >= 0"
        elif tilts_raw:
            rng = parse_tilt_range(tilts_raw)
            if rng is None:
                flag["Tilts [0,1,2,3]"] = "Unparseable tilt value"
            else:
                lo, hi = rng
                if lo < 0 or hi < 0:
                    flag["Tilts [0,1,2,3]"] = "Tilt must be >= 0"
                elif lo > hi:
                    flag["Tilts [0,1,2,3]"] = "Low tilt exceeds high tilt"

        # Plausibility (non-blocking): 10*log10(41253/(HBW*VBW)) - gain in [-1, 6].
        hbw = to_float(row.get("Horizontal HPBW [deg]", ""))
        vbw = to_float(row.get("Vertical HPBW [deg]", ""))
        gain = to_float(row.get("Gain [dBi]", ""))
        if hbw and vbw and gain is not None and hbw > 0 and vbw > 0:
            ideal = 10 * math.log10(41253.0 / (hbw * vbw))
            diff = ideal - gain
            if not (-1.0 <= diff <= 6.0):
                flag["Gain [dBi]"] = (
                    f"Implausible gain (directivity-gain delta {diff:.1f} dB outside -1..+6)"
                )

        if freq:
            # Two "Custom" rows with different Min/Max Freq are different bands, so a shared
            # port between them is not a clash — include the range in the grouping key.
            key = (freq, row.get("Min Freq [Hz]", "").strip(), row.get("Max Freq [Hz]", "").strip())
            freq_ports.setdefault(key, []).append((i, ports))

    # No port number may appear in two sections of the same Frequency value.
    for entries in freq_ports.values():
        seen = {}  # port -> first row index
        clashing = set()
        for row_idx, ports in entries:
            for p in ports:
                if p in seen and seen[p] != row_idx:
                    clashing.add(row_idx)
                    clashing.add(seen[p])
                else:
                    seen.setdefault(p, row_idx)
        for row_idx in clashing:
            existing = flags[row_idx].get("Section Ports")
            msg = "Port shared with another section of the same Frequency"
            flags[row_idx]["Section Ports"] = f"{existing}; {msg}" if existing else msg

    return flags
