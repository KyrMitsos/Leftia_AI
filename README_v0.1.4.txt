Leftia_AI v0.1.4

Separate experimental version of the original Leftia collector.
The existing 25 output columns are unchanged.

Collection and recovery:
- Betfair website JSON remains the primary price source and DelayAppKey remains the normal API key.
- KO is the last kosher customer-facing price immediately before/at first-half kick-off. If no clean pre-KO observation is available, a bounded 120-second post-kick-off recovery window accepts the first kosher price very close to kick-off instead of immediately freezing 0.
- A match first rediscovered materially late is never assigned current late-match prices as KO.
- HT is the first kosher customer-facing price immediately after second-half kick-off.
- HT focused polling normally starts 10 minutes after FirstHalfEnd.
- If FirstHalfEnd is missed, a recovery HT watch can start from the persisted actual first-half kick-off time.
- A pre-SecondHalfKickOff price can never itself become HT.
- Strong fallback second-half-start evidence is accepted when the explicit event is missing: timestamped later second-half evidence or a clean suspend/reopen pattern around the remembered half-time window.
- Old 1970 Betfair transition timestamps are never replaced with the current time when the match is already well past the transition.
- Tracked event IDs continue to be queried even after the match disappears from the current market catalogue.
- Remembered market IDs continue to be used for KO/HT/minute-window price capture when catalogue discovery disappears.
- Missing intermediate match states do not block later valid states such as SecondHalfKickOff or Finished.
- A populated Betfair fullTimeScore is also accepted as strong final-state evidence.
- Complete broadly plausible first price snapshots are accepted even when no recent clean-book history yet exists.
- Rapid website recovery is capped at one immediate retry per focused cycle; further recovery uses the normal 15-second focused cycle instead of a five-request burst.

Restart safety:
- YYYYMMDD_run_dump.json remains in use.
- YYYYMMDD_checkpoint.json stores DA_TEAMS plus active price history, KO/HT transition times, latest timelines, remembered catalogues and active capture state.
- KO capture phase/deadline is persisted so a restart inside the recovery window resumes rather than converting the match to 0.
- The checkpoint is atomically replaced and keeps a .bak copy of the previous successful checkpoint.
- State is checkpointed after collection-state changes and immediately after KO, HT and finalisation.
- Ctrl+C, SIGTERM and handled exceptions save state before exit.
- On restart the newest current/previous-day checkpoint is restored; legacy run_dump.json remains supported as a fallback.
- Result writing is duplicate-safe after a restart.
- Finalised markets cannot be reinitialised from a lingering Betfair catalogue entry.

Problem matches:
- YYYYMMDD_dump.csv and YYYYMMDD_dump.json are retained.
- YYYYMMDD_dump_state.json is a compact exceptional-evidence sidecar only for unresolved, missing or reconstructed captures.
- It stores only small KO/HT evidence windows, essential transition/goal evidence, scores and source-failure flags; it does not duplicate full catalogue/team objects.
- Existing oversized v0.1.3 dump_state files are compacted on startup and duplicate records for the same event/market are reduced to the richer record.
- Catalogue/timeline disappearance and return are logged once per state change rather than every polling cycle.

Odds handling:
- Match Odds use inverse-price book plausibility and recent clean market behaviour.
- A complete plausible first snapshot is not rejected simply because its book is wider than the default target when no historical anchor exists.
- Cross-poll repair is constrained by runner history.
- Missing BACK values can be inferred from recent stable BACK/LAY tick spread.
- If recovery is not reliable the existing odds field remains 0.
- Optional minute-based focused windows remain available through FOCUSED_MINUTE_WINDOWS in main.py.

Two-decimal output:
- HT_1/X, HT_2/X, HT_1/2, MULTI_DT1, P/L_DT1, MULTI_ZZCX and P/L_ZZCX are written with at most two decimal places.

Run:
    python main.py

Closed-day state retention
--------------------------
- YYYYMMDD_checkpoint.json and YYYYMMDD_run_dump.json are runtime recovery files, not permanent evidence files.
- After the 04:00 next-day close has safely written the retained dump files and current-day recovery state, the closed day's checkpoint/run-dump files (including checkpoint backup/temp files) are removed.
- Useful exceptional collector evidence is promoted before runtime cleanup into the compact YYYYMMDD_dump_state.json sidecar.
- If a match is finalised into YYYYMMDD_results.csv but still has missing KO/HT/HT-score data, used MIX/INF reconstruction or required a strong fallback second-half signal, its compact collector evidence is written before the live state is discarded.
- Normal fully captured result rows do not retain redundant runtime history after finalisation.
