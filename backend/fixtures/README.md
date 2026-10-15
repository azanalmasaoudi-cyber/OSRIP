# Fixtures

`booklet_synthetic_fixtures_v1.csv` contains **synthetic demonstration inputs**
transcribed from the OSRIP booklet: Table 4.1 and Sections 4.3–4.4. They are not
Omani statistics.

- The years 2001 and 2002 are arbitrary placeholders (SPEC_CONFLICTS C11).
- `SYNTH_COMMODITY` is an invented commodity (`synthetic_only`).
- `PARTNER_A/B/C` are fictional partners, never real countries.

`python -m app.cli seed-synthetic` loads the file into a `synthetic` source (no
publisher) through the normal upload → validate → approve → publish workflow. The
actor is the service account `fixture-loader@osrip.invalid`, which cannot sign in.
Seeding is idempotent: a second run finds the published version and does nothing.
