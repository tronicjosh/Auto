# AutoBulkSheet

A desktop tool that reads a base-station antenna **datasheet PDF** with the Claude API and
writes the electrical spec, ports, tilts and dimensions into the **IXUS batch workbook** — into
its `Descriptions` sheet, with the workbook's dropdowns and hidden sheets preserved.

You pick a datasheet, the tool identifies the antenna type, extracts the values, and populates
the batch sheet in place. A human reviews the result (uncertain fields are flagged).

## Setup

Python 3.10+.

```bash
pip install -e ".[gui,dotenv]"   # run the tool
pip install -e ".[dev]"          # + pytest for the test suite
```

Configuration is via environment variables. Copy `.env.example` to `.env` (gitignored) and fill
it in:

```
ANTHROPIC_API_KEY=sk-ant-...                                  # required
IXUS_TEMPLATE=C:\path\to\IXUS_template.xlsx                   # required: the EMPTY source workbook
IXUS_BATCH_SHEET=C:\path\to\IXUS_antenna_batch_processor.xlsx # required: the output, populated in place
# IXUS_DATASHEET_ROOT=C:\Users\you\Desktop                    # optional: where the file picker opens
```

`IXUS_TEMPLATE` and `IXUS_BATCH_SHEET` must be **two different files**: the template is the empty
master (read-only, the source of the dropdowns); the batch sheet is the output, fully rebuilt
from the template on every run.

## Run

```bash
python run.py
```

It loads `.env`, prints a config summary (and warns if the key or template is missing), then
opens the GUI. In the window:

1. **Browse for a datasheet (PDF)** → the tool classifies the antenna type (router pass) and
   then extracts (you watch step 1 → step 2).
2. The result is **written to the batch sheet**, with a per-pass **cost** breakdown and a count
   of any **flagged** fields.
3. **Open batch sheet** to review. If the type was wrong, pick the correct one and **Re-extract**
   (no extra classify cost). If the file was open in Excel, close it and **Retry save**.

Supported types: **Panel, Omni, Parabolic reflector**. Lens antennas (e.g. Matsing) are detected
but not yet supported — the tool says so instead of producing a poor result.

## Configuring / tuning

Everything the engineers tune lives in config, not code:

| To change… | Edit |
|---|---|
| The AI models | `config/meta.json` → `"model"` (extract), `"classify_model"` (router) |
| Universal extraction rules | `config/base_prompt.txt` |
| Per-type rules | `config/profiles/{panel,omni,parabolic,lens}.txt` |
| How types are classified | `config/router_prompt.txt` |
| IXUS frequency bands (min/max) | `config/bands.json` |
| Column mapping / validation / guardrails | `meta.json` → `mapping_spec`, `rules_spec`, `type_guardrails`, `band_gain_spec` |
| Paths + API key | `.env` |

## How it works

```
datasheet PDF
  -> classify.py     cheap router model -> antenna type (you confirm/correct)
  -> extract.py      Claude reads the PDF -> strict JSON (datasheet_bands + sections)
  -> engine.py       config-driven, DETERMINISTIC:
                       • band inclusion + gain/beamwidth selection from the overlapping
                         datasheet columns (highest gain; ties -> wider horizontal beamwidth)
                       • decimal-comma -> dot, column mapping, validation flags, type guardrails
  -> workbook.py     surgical zip-patch of the Descriptions sheet -> the batch sheet
```

The split matters: the **model** transcribes the datasheet (its judgement is reviewed by a
human), while the **code** does the band overlap, gain selection and validation that the model is
unreliable at. `vocab.py` reads the controlled vocabularies (manufacturers, Frequency, Type,
Source) **live** from the template so the prompt and validator never drift from the spreadsheet.

**Why the workbook is written by hand:** the Descriptions dropdowns are Excel *x14 extension*
validations that `openpyxl` silently strips on save. So `workbook.py` copies every zip member
byte-for-byte except the one worksheet XML it injects values into — leaving the dropdowns and
hidden sheets intact. The template is only ever read, never modified.

## Tests

```bash
pytest
```

No API key or network needed — the tests replay a saved extraction and check the deterministic
pipeline. `tests/fixtures/` holds the inputs: a captured AI output
(`2NN2HH-33B-R4.extraction.json`), the known-correct rows (`frequency_band_data.csv`), and an
empty workbook (`ixus_template.xlsx`) for the writer tests. The models and the live API are not
tested — that's what the human review and prompt-tuning cover.

## Layout

```
run.py                       launcher (loads .env, preflight, opens the GUI)
src/autobulksheet/
  gui.py                     PyQt5 desktop UI
  session.py                 GUI-agnostic core: one datasheet's extract + write
  settings.py                env-driven config (paths, key)
  classify.py extract.py     the AI passes (router + extraction)
  engine.py                  config-driven mapping, validation, band-gain selection
  workbook.py vocab.py       the zip-patch writer + live vocab reader
  rows.py validate.py        frozen "oracle" the engine is regression-tested against
  workflows/                 the Workflow abstraction + the config loader
config/    meta.json + prompts + profiles + bands.json
tests/                       offline tests + fixtures
```
