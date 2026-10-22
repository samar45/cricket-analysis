# Work log: data refresh
MILESTONE: 00:25 branch overhaul created, CLAUDE.md committed (de8525a)
MILESTONE: 00:30 build done: 285.5s, 8 comps, 0 skipped, Blast 1571 matches loaded, teams migrated 884 cells
MILESTONE: 00:32 BUG: first build had doubled league deliveries (Kohli IPL 18692 vs old 8671). Cause: league zips contain all_matches.csv, ingest treated it as a match. Fixed (isdigit stem filter), first build moved to scratchpad, rebuilding from the already-downloaded raw files
MILESTONE: 00:35 stopped by Samar (going to sleep). Rebuild killed partway; new DB unverified. Resume: docs/JOURNEY.md section 6
