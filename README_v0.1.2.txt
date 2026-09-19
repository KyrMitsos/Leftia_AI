Leftia_AI v0.1.2

Separate experimental version of the original Leftia collector.
The existing 25 output columns are unchanged.

Main collection changes:
- DelayAppKey remains the normal Betfair API key used by the existing API layer.
- Betfair website JSON remains the primary price source.
- KO is the last clean customer-facing price before the match turns in-play.
- A match first found well after KO is not given a false KO price.
- HT is the first clean customer-facing price immediately after SecondHalfKickOff.
- HT focused polling starts 10 minutes after FirstHalfEnd so recent clean pre-restart prices are already available for validation, runner anchors and BACK/LAY spread inference.
- A pre-SecondHalfKickOff price can never itself be frozen as HT. Post-restart collection stops as soon as the first reliable HT price is obtained, with up to 5 minutes available for recovery if necessary.
- Optional minute-based focused windows can be added through FOCUSED_MINUTE_WINDOWS in main.py.
- Normal loop is 30 seconds. Focused collection is approximately 15 seconds.
- Bad focused snapshots can trigger five 0.5-second targeted retries.
- Match Odds are checked using inverse-price book plausibility and recent clean book behaviour.
- Cross-poll repair is constrained by runner history.
- Missing BACK values can be inferred from recent observed BACK/LAY tick spread when stable.
- If recovery is not reliable the existing odds field remains 0.
- DA_TEAMS, run dumps, daily dump CSV/JSON and results CSV remain in use.
- Run dumps use atomic replacement and are refreshed after important state changes.
- One daily YYYYMMDD_log.txt records collection quirks/recovery.
- Short log codes are editable in log_codes.csv.
- Existing generic API/trading functions remain available.
- Command-window catalogue, timeline, focused-capture and KO/HT reporting remains enabled.

Run:
    python main.py
