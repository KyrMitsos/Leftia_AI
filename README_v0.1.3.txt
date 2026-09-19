Leftia_AI v0.1.3 (revised checkpoint cleanup)

Separate experimental version of the original Leftia collector.
The existing 25 output columns are unchanged.

Collection and recovery:
- Betfair website JSON remains the primary price source and DelayAppKey remains the normal API key.
- KO is the last kosher customer-facing price immediately before/at first-half kick-off.
- HT is the first kosher customer-facing price immediately after second-half kick-off.
- HT focused polling normally starts 10 minutes after FirstHalfEnd.
- If FirstHalfEnd is missed, a recovery HT watch can start from the persisted actual first-half kick-off time.
- A pre-SecondHalfKickOff price can never itself become HT.
- Strong fallback second-half-start evidence is accepted when the explicit event is missing: later second-half timeline evidence or a clean suspend/reopen pattern around the remembered half-time window.
- Tracked event IDs continue to be queried even after the match disappears from the current market catalogue.
- Remembered market IDs continue to be used for KO/HT/minute-window price capture when catalogue discovery disappears.
- Missing intermediate match states do not block later valid states such as SecondHalfKickOff or Finished.
- A populated Betfair fullTimeScore is also accepted as strong final-state evidence.

Restart safety:
- YYYYMMDD_run_dump.json remains in use.
- YYYYMMDD_checkpoint.json now stores DA_TEAMS plus active price history, KO/HT transition times, latest timelines, remembered catalogues and missing-source/capture state.
- The checkpoint is atomically replaced and keeps a .bak copy of the previous successful checkpoint.
- State is checkpointed after collection-state changes and immediately after KO, HT and finalisation.
- Ctrl+C, SIGTERM and handled exceptions save state before exit.
- On restart the newest current/previous-day checkpoint is restored; legacy run_dump.json remains supported as a fallback.
- Result writing is duplicate-safe after a restart.

Problem matches:
- YYYYMMDD_dump.csv and YYYYMMDD_dump.json are retained.
- YYYYMMDD_dump_state.json additionally preserves the unresolved match's collector state for later forensic/consolidation work.
- Catalogue/timeline disappearance and return are logged once per state change rather than every polling cycle.

Odds handling:
- Match Odds use inverse-price book plausibility and recent clean market behaviour.
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
- Useful collector evidence is promoted before runtime cleanup. YYYYMMDD_dump_state.json is the retained forensic sidecar and includes price history, KO/HT capture evidence, observed transition times/sources, latest timeline and source-presence state for unresolved dumped matches.
- If a match is finalised into YYYYMMDD_results.csv but still has missing KO/HT/HT-score data or used a MIX/INF reconstruction, its collector evidence is written immediately to YYYYMMDD_dump_state.json before the live state is discarded.
- Normal fully captured result rows do not retain redundant runtime history after finalisation.
