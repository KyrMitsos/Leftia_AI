Leftia_AI v0.2.0

Major internal-state, persistence and scheduler redesign. The existing 25-column
YYYYMMDD_results.csv schema and the KO/HT market-selection rules remain unchanged.

Persistent files
----------------
- live_state.json is the only live crash/restart state file.
- live_state.json.bak is the previous successfully written live state.
- YYYYMMDD_results.csv remains the normal final output.
- YYYYMMDD_dump.json is the single rich archive for unresolved/problematic matches.
- YYYYMMDD_log.txt is the event/state-change log.
- codes.csv is the compact-code legend.

There are no new YYYYMMDD_checkpoint.json, YYYYMMDD_run_dump.json,
YYYYMMDD_dump.csv or YYYYMMDD_dump_state.json files.

Canonical match state
---------------------
- Active state and dump state use the same compact schema-v2 MatchRecord.
- A MatchRecord stores fixture identity, immutable Betfair start date, result/output
  fields, compact goal/boundary timeline evidence, KO/HT selected evidence, a small
  amount of best price context, problem flags and only the runtime data needed to
  resume safely.
- Rolling price histories are not persisted. Only selected/best useful snapshots are
  retained across a restart. The running process may use short transient histories.
- Timeline evidence keeps only Goal/KickOff/FirstHalfEnd/SecondHalfKickOff/Finished
  information rather than unrelated cards and repeated full Betfair objects.
- Compact archive/problem codes are documented in codes.csv.

Write minimisation / SSD behaviour
----------------------------------
- State lives in RAM during normal operation.
- A dirty flag is raised only when collector state changes.
- Before writing, the canonical JSON is hashed. If it is identical to the last
  successfully saved representation, no disk write occurs even when persistence is
  requested.
- Polling that returns no meaningful state change therefore causes no live-state write.
- Actual writes use compact JSON and an atomic tmp -> live_state.json replacement.
- The previous good live_state.json is retained as live_state.json.bak. This is a
  rename/rotation safeguard, not a second routine full-state write.
- On restart the main file is tried first, then .bak.

Restart and old-file migration
------------------------------
- A restart can occur hours or days later. The collector reloads live_state.json and
  resumes matches whose match day is still open.
- Records whose original match day is already closed are moved to that original
  YYYYMMDD_dump.json, never to today's files.
- On first upgrade from the old architecture, legacy YYYYMMDD_checkpoint.json and
  YYYYMMDD_run_dump.json are accepted as live-state sources.
- Legacy YYYYMMDD_dump.json and YYYYMMDD_dump_state.json are merged by event and
  converted to the new schema-v2 YYYYMMDD_dump.json representation.
- Old rolling forensic histories are reduced during migration rather than copied
  indefinitely into the new format.
- The collector writes only the new format after migration.

Result and dump routing
-----------------------
- Each match is permanently associated with the UTC date of its Betfair start datetime.
- As soon as a Finished result is established it is appended exactly once to that
  start-date's YYYYMMDD_results.csv, even when it finishes after midnight.
- The four-hour rule is only the match-day close grace: at 04:00 UTC the next day,
  unresolved matches for that start date become eligible for that date's dump.
- If the timeline endpoint is unavailable during normal day-close housekeeping, closing
  is deferred rather than discarding recoverable matches.
- A finished row with missing/reconstructed evidence can also keep a compact archive
  record with archive code P so later Data Consolidation can improve it.
- Dump archive codes: U=unresolved, P=finalized/problematic, R=stale record archived
  after a later restart.

Scheduler
---------
The scheduler is relative to this collector instance, not PC wall-clock :00/:10/:20.
If a Standard cycle starts at 14:22:03, opportunities are:

    14:22:03  STANDARD
    14:22:13  INTERMEDIATE opportunity
    14:22:23  INTERMEDIATE opportunity
    14:22:33  STANDARD

- STANDARD interval: 30 seconds. Full catalogue/timeline/finalisation processing.
- INTERMEDIATE opportunities: +10 and +20 seconds inside each Standard frame.
- An Intermediate opportunity does nothing unless there is boundary-sensitive or
  temporarily bad/missing information requiring extra attention.
- Important transitions still trigger their immediate price request in the processing
  cycle that observes the transition.
- A failed HT boundary request remains pending and can retry at the next +10/+20
  opportunity. No separate 5-second loop and no tight retry burst exists.
- Missed scheduler opportunities after a slow/network-stalled cycle are skipped rather
  than fired as a catch-up request burst.

Logging
-------
- Log rows now contain AtUTC separately from MatchDate. The old Timestamp field was the
  fixture start date and therefore made repeated polling diagnostics look simultaneous.
- Price diagnostics are edge-triggered: the same Code/Point/Details state for a match
  is not written repeatedly on every poll. A changed condition is logged once and can
  be logged again if the state later changes away and returns.

KO / HT capture
---------------
- Existing KO boundary selection from v0.1.8 is preserved.
- FirstHalfEnd enables HT boundary attention but its price is not itself labelled HT.
- SecondHalfKickOff triggers an immediate fresh Match Odds request.
- If the fresh HT book is missing/incoherent, HT remains pending and retries only on
  scheduled Intermediate/Standard opportunities within the short restart window.
- Retries require fresh safe timeline evidence: unchanged HT score and no second-half
  goal. Later second-half prices are never backfilled as HT.
- Match Odds boundary repair remains conservative, including defensible 1.01/1000
  exchange-limit cases.

Run
---
    python main.py
