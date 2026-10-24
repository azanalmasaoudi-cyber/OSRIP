# Demonstration script (about 10 minutes)

For the university presentation. The numbers shown come from the curated **reference pack**
(published NCSI tables, each record with its source and page), loaded as verified-source data.
OSRIP is an academic prototype, not an official statistics service: say so at the start.

The same scenario runs automatically, with assertions and screenshots, as test 9 of
`frontend/e2e-demo/integrated.demo.spec.ts` (see `docs/ACADEMIC_EVALUATION.md` §8).

## Before the session (15 minutes earlier)

1. Start the database, API and interface (README → *Start*), with the reference pack published
   (`python -m app.cli import-reference-pack --publish` in `backend`, once; idempotent). Open
   `http://localhost:5173` in a maximised window; zoom 110–125 % for the room.
2. Without an AI key the assistant answers with a labelled **data-based report** instead of an
   AI interpretation; say so if it happens. With `OSRIP_ASSISTANT_PROVIDER=gemini` and a key in
   `backend/.env`, check Settings › Services first.
3. Fallback if the API fails: the recorded run's screenshots in `docs/evidence/integrated/`
   (20–27).

## Script

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Overview | Scroll once | "OSRIP helps an analyst check electricity, water, food and trade figures and see where each number comes from. It is an academic prototype, not an official service." |
| 0:45 | Electricity | Point at the empty results area | "Nothing is shown until a period is chosen. Each sector keeps its own choice." |
| 1:15 | Electricity form | Gross electricity generation · Oman · Monthly · June 2026 → August 2026 | "Only periods the bulletin publishes are offered. The months are preliminary." |
| 2:00 | *Show results* | Point at the table and the summary | "5,755.4, 5,676.9 and 5,743.9 GWh, in time order. The total, 17,176.2 GWh, is given because generation is a flow and every month is published." |
| 3:00 | *Show chart* | — | "The chart appears only when asked for, from the same rows." |
| 3:30 | *Request analysis* | Point at the selection chip; *Send* | "The question carries the applied selection: the assistant must answer for exactly these months and this area." |
| 4:30 | The reply | Click a citation chip | "Each figure is cited; the citation names the Monthly Statistical Bulletin, its link and the dataset version." |
| 5:30 | Electricity, Annual, 2022 → 2026 | *Show results* | "The 2026 full year is not published: the row says so and is never zero. January–August 2026 is shown apart, and no total is given over a gap." |
| 6:30 | Quarterly | — | "No quarterly figures are published for this indicator, so no period can be chosen; quarters are never split from annual totals." |
| 7:00 | Language → العربية | Point at the same numbers | "Arabic changes the labels and direction, not the data." |
| 7:30 | Data Management (data manager) | *Official statistics feeds* | "The NCSI bulletin feed: last checked, last release found, last data imported are three different moments. A new release is staged for approval, never published silently." |
| 8:30 | Results › *Listen* | Only if Azure Speech is configured | "A few sentences from the summary, in Al Mulhim's or Ilham's Omani voice; nothing plays by itself." |
| 9:15 | (Slide) Evaluation | `docs/ACADEMIC_EVALUATION.md` §9 | Read the measured outcomes; say which services were not configured. |

## Likely questions

| Question | Answer |
|---|---|
| Is this real Omani data? | The verified mode shows the reference pack: figures transcribed from NCSI publications with page references. It is not an official release of OSRIP's own; the publication is the authority. |
| Does the AI calculate the numbers? | No. Totals, changes and the table come from the server's deterministic calculations; the model may only cite figures it was given, and a number without evidence is withheld. |
| What happens without an AI key? | A labelled data-based report: the same cited figures, no interpretation, not charged against the guest allowance. |
| Why no quarterly electricity? | The bulletin publishes monthly and annual figures; quarters are not derived silently. |
| How fast is it? | See `docs/ACADEMIC_EVALUATION.md` §9: measured on this laptop, single user. No claim is made for concurrent use. |
