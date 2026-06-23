# Antenna Reader

Reads an EMSS base-station antenna **datasheet PDF** with the Claude API, transcribes the
electrical-spec / port-layout / dimensions into rows, validates them, and writes a
**populated copy** of the IXUS batch workbook (`IXUS_antenna_batch_processor2 1.xlsx`) —
into its `Descriptions` sheet, with the workbook's dropdowns and hidden business sheets
preserved.

## Install

Python 3.10+.

```bash
pip install -e .            # runtime
pip install -e ".[dev]"     # + pytest for the test suite
pip install -e ".[dotenv]"  # optional: load ANTHROPIC_API_KEY from a .env file
```

## API key

The key is read from the `ANTHROPIC_API_KEY` environment variable. **Never commit a key.**

```bash
# PowerShell (this session)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
# or copy .env.example -> .env (gitignored) and fill it in
```

## Usage

```bash
# one datasheet -> output/<name>_populated.xlsx
antenna-reader extract "data/datasheets/commscope_2NN2HH-33B-R4.pdf" --manufacturer CommScope

# a folder of PDFs (one populated workbook each)
antenna-reader extract data/datasheets/

# see the rows + validation flags without writing a file
antenna-reader extract "data/datasheets/commscope_2NN2HH-33B-R4.pdf" --dry-run

# print the vocabularies read live from the workbook (no API call)
antenna-reader vocab
```

Useful flags: `--out PATH` (single PDF), `--model-name` (override the antenna model),
`--model` (default `claude-sonnet-4-6`), `--template PATH` (alternate workbook).

## How it works

```
PDF bytes
  -> extract.py    Claude messages.create, PDF as a base64 document block -> strict JSON
  -> rows.py       sections_to_rows: JSON -> one row per (band x beam)
  -> validate.py   6 advisory rules (vocab, port counts, tilt range, plausibility, ...)
  -> workbook.py   surgical zip-patch of the Descriptions sheet -> output/*.xlsx
```

`vocab.py` reads the controlled vocabularies (manufacturers, Frequency, Type, Source) **live**
from the workbook's `Data_Validation` sheet, feeding both the prompt and the validator so they
never drift from the spreadsheet.

**Why the workbook is written by hand:** the Descriptions dropdowns are Excel *x14 extension*
data validations. `openpyxl` doesn't model them and silently strips them (and other parts) on
save. So `workbook.py` copies every zip member byte-for-byte except the one Descriptions
worksheet XML, into which it injects values — leaving the dropdowns and all hidden sheets
intact. The template is only ever read, never modified.

## Layout

```
src/antenna_reader/   config schema util prompt extract rows validate vocab workbook pipeline cli
data/template/        the IXUS workbook (template; read-only)
data/datasheets/      sample datasheet PDFs
reference/            antennaModelVerification.pdf (ground-truth reference)
output/               generated populated workbooks (gitignored)
tests/                offline unit + acceptance tests, fixtures, opt-in live test
legacy/               the old FastAPI v1 (app.py + web UI), kept for reference
```

## Tests

```bash
pytest            # offline unit + acceptance (no API key needed)
pytest -m live    # also run the real-extraction test (needs ANTHROPIC_API_KEY)
```

The offline acceptance test expands the saved CommScope extraction JSON
(`tests/fixtures/2NN2HH-33B-R4.extraction.json`) and checks it reproduces the golden
`tests/fixtures/frequency_band_data.csv` (12 rows). `test_workbook` confirms the output keeps
its dropdowns and hidden sheets and never mutates the master.

> **Data caveat:** the golden CSV's 1800 MHz row is gain 18.3 / HBW 33 / VBW 7.3. An earlier
> note quoted 17.7 / 35 / 7.7. The CSV is treated as authoritative for tests — confirm the true
> datasheet values before trusting the oracle.
