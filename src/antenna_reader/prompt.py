"""The extraction prompt. Vocabularies are injected at call time so the model maps
band columns and antenna type to the live lists read from the workbook."""

_TEMPLATE = """You are transcribing a base-station antenna datasheet for RF-EMF compliance modelling.
Read the electrical specifications table, the array layout / port configuration, and
the dimensions section.

Rules:
- Output one section entry per (frequency-band column) x (beam / port group). A
  single-beam antenna has one port group per band column; a multibeam antenna has one
  entry per beam with its azimuth offset (from "Beam Centers", e.g. +/-27 -> two
  entries, az 27 and az -27).
- Transcribe gain, horizontal HPBW, vertical HPBW and tilt range EXACTLY as printed in
  that band column. Never merge, average, or take values from a neighbouring column.
- frequency: map each datasheet band column to the closest entry in the Frequency
  vocabulary (provided). Fill minFreqHz/maxFreqHz (in Hz) ONLY when frequency is
  "Custom"; for any standard band leave BOTH minFreqHz and maxFreqHz as "".
- tilts: write an electrical tilt RANGE as "low to high" using the word "to"
  (e.g. "2 to 20"), not a hyphen. A single fixed tilt is just the number (e.g. "6").
- ports: from the array layout / port configuration, the connector numbers feeding
  that band + beam, comma-separated with no spaces (e.g. "1,2,5,6").
- type: closest entry in the Type vocabulary (provided). e.g. a multibeam panel -> panel.
- Dimensions in metres: height = the long axis (often called Length), plus width, depth.
- Use "" for anything genuinely absent. Do not guess.

Frequency vocabulary: {freq_vocab}

Type vocabulary: {type_vocab}

Respond ONLY with JSON, no markdown fences:
{{"manufacturer": str, "model": str, "type": str,
 "height_m": num, "width_m": num, "depth_m": num,
 "sections": [{{"frequency": str, "minFreqHz": str, "maxFreqHz": str, "tilts": str,
               "ports": str, "azimuth": num, "gain_dbi": num,
               "hbw_deg": num, "vbw_deg": num}}]}}"""


def build_extraction_prompt(freq_vocab, type_vocab) -> str:
    """Render the prompt with the live Frequency and Type vocabularies."""
    return _TEMPLATE.format(
        freq_vocab=", ".join(freq_vocab),
        type_vocab=", ".join(type_vocab),
    )
