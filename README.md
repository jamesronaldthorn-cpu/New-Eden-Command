# New Eden Command v3.5.3 — Live Skill Queue Import Fix

New Eden Command is a Windows desktop companion for EVE Online capital navigation, character management, logistics, hunting and route planning.

Version **3.5.3** keeps the v3.5.2 SDE type-name import fix and the full Hunting / Roam Command feature set, while changing Skill Planner so **Refresh + Import Queue** fetches the selected character's current queue directly from CCP ESI instead of relying on an older cached Command Center snapshot.

## Hunting / Roam Command

### Activity trends

- CCP public last-hour jumps, NPC kills, ship kills and pod kills are still the primary activity inputs.
- The app now stores a small local history of systems you scan.
- Each target can show **HEATING**, **STEADY** or **COOLING** compared with the previous saved public snapshot.
- Rising activity can contribute to the hunting score; cooling activity can reduce it.
- History is kept outside the install folder in the existing user-data area and is pruned automatically.

### System dossier

Selecting a hunting target now opens a dossier with:

- security and region
- gate distance from the hunting origin
- last-hour public activity
- hunt score and the reasons behind it
- trend direction
- stargate topology and number of exits
- nearest low-sec / high-sec escape found on the SDE gate graph
- NPC station presence
- sovereignty / ESS context
- manual intel and expiry
- visit history
- optional cached zKill context
- Black Ops jump range, fuel and possible NPC-station staging systems when a Black Ops hull is selected

### Chokepoints and escape context

- Systems are classified from the real SDE stargate graph as **Dead-end**, **Pipe**, **Junction** or **Hub**.
- Dead-ends expose single-exit targets clearly.
- The dossier shows the nearest low-sec and high-sec escape systems and their gate distances.
- Stargate graph data is cached in memory so repeated Hunting scans and route work do not repeatedly reload the whole graph from SQLite.

### Automatic roam routes

- Choose a desired roam length from **5 to 60 gate jumps**.
- **BUILD ROAM ROUTE** builds a route through high-value systems from the current hunting scan.
- The route favours hunt score, rising activity and active manual intel.
- Repeated systems and repeated gates are penalised so the route avoids backtracking where the gate topology allows it.
- Copy the route to the clipboard or send it to the selected EVE character as autopilot waypoints.

### Manual intel with expiry

Targets can be tagged with timestamped observations such as:

- Ishtar seen
- Marauders
- Gate camp
- Cyno active
- Empty
- ESS

Each observation has a user-selected expiry from 1 to 168 hours. Expired observations stop affecting the ranking automatically.

### Visit history

- Mark a system visited and optionally record the result.
- The app stores visit count, last-visited time, note, hunt score and the public activity values present when the visit was recorded.
- This is local user history; it is not shared or uploaded.

### Optional zKillboard context

For a selected target, **FETCH zKILL** can retrieve public historical killmail context for that system.

- Up to seven days / 200 killmails are summarised.
- Common victim hulls and attacker hulls are shown.
- The dossier can classify the recent public history as ratter losses, mining losses, gang/camp activity, PvP hotspot or general recent kills.
- zKill results are cached locally for at least one hour to avoid repeatedly querying the service.
- zKill history is treated as historical context, never as live-local information.

### Ratter / mining signal

The optional zKill summary recognises common ratting, marauder, carrier and mining hull losses and feeds that historical context into the selected target's dossier and score.

### ESS Hunt improvements

The existing **ESS Hunt** profile now benefits from:

- activity trends
- topology / escape context
- manual ESS observations with their age
- manual intel
- optional zKill historical context

New Eden Command still does **not** invent a live ESS balance. Unobserved systems remain labelled as ESS potential only.

### Black Ops Hunt

A new **Blops Hunt** profile ties Hunting into the existing jump calculator.

When a Black Ops hull is selected, the target board can show:

- LY distance from the hunting origin
- whether the target is inside the selected hull/JDC jump envelope
- basic legality checks
- isotope fuel requirement
- nearby NPC-station staging candidates that can reach the selected target

**PLAN BLOPS** transfers the selected target and hunting origin into the Jump Calculator for the full jump calculation.

### Tactical hunting map

The Hunting page now includes an interactive map using real SDE solar-system coordinates and stargate links.

- higher-ranked systems are emphasised
- heating systems are visually distinct
- strong PvP signals and ESS targets receive their own treatment
- clicking a map node selects the same target in the target board and opens its dossier
- the map intentionally remains a tactical projection rather than pretending to be the in-game map

## Data honesty

New Eden Command does not claim access to information that is not publicly available.

- CCP ESI public activity is delayed aggregate data, not live local.
- Exact pilots currently in a system are not supplied by the public system-kills/jumps endpoints.
- Exact live ESS Main/Reserve Bank balances are not inferred. ESS values displayed as observed are values the user recorded from the EVE client.
- zKillboard data is historical third-party public killmail data and is labelled accordingly.

## Other preserved features

- Capital, Jump Freighter and Black Ops jump calculator.
- Systems-in-range search.
- Automatic multi-hop capital routing with cyno legality and station-aware policies.
- Tactical jump-route map.
- Multiple EVE characters through CCP SSO/PKCE.
- Send destinations and routes to the EVE client.
- Command Center with location, ship, online state, wallet, skill queue, clones, contracts, industry and assets.
- Asset grouping by system, value estimates, nested-root tracing, pagination and fitted-module exclusion.
- Capital Operations, fleet manifest and fuel logistics.
- Skill Planner.
- Responsive UI, scrollable pages and DPI-safe navigation.
- Verified format-2 `.ejpupdate` packages with backups and SHA-256 validation.

## Download

Latest public release:

https://github.com/jamesronaldthorn-cpu/New-Eden-Command/releases/latest

For a first installation, download the **Setup EXE**. Existing v3.4.3+ onedir installs can use the in-app Update Center / `.ejpupdate` package.

The default online update feed is:

https://github.com/jamesronaldthorn-cpu/New-Eden-Command/releases/latest/download/latest.json

## v3.5.3 SDE importer fix

- Selects CCP SDE datasets by exact ZIP-member basename instead of a loose suffix match.
- Guarantees the item-name importer opens the canonical `types.jsonl` dataset.
- Supports both the current direct JSONL object layout and a defensive `_value` object wrapper.
- Reports the selected SDE member, records scanned and names found if validation ever fails again.
- Keeps the 10,000-name integrity threshold; the safety check is not weakened.
- Bumps the local SDE schema to force one clean rebuild after upgrading from v3.5.1.

After installing v3.5.3, let **Refresh Data / EVE Data Update** complete. A healthy current SDE import should index tens of thousands of item, ship and skill names rather than three.

## v3.5.1 name-resolution fixes

- Rebuilds the local CCP SDE cache with a complete item/type-name integrity check instead of accepting an almost-empty type table.
- Adds a universe-wide solar-system display index separate from the capital-navigation system set, so character/assets/contracts can show names for special/new system ID ranges without changing cyno-route legality.
- Uses exact ESI-resolved station/location names before locally reconstructed fallback labels.
- Keeps authenticated player-structure resolution and maps accessible structures back to their solar system.
- Repairs missing solar-system details from public ESI when the current SDE/display cache does not contain them.
- Bulk-primes item/ship/skill type names for cached character data, removing the old one-SQLite-query-per-row slowdown on large inventories.
- Refuses to replace a healthy local database if a new SDE import contains fewer than 10,000 type names.

After installing v3.5.1, the first launch intentionally rebuilds EVE static data once because the local schema version has changed. Let that data update finish, then refresh/sync the affected character(s) once so structure and owner/location names are re-resolved.

## Build

From PowerShell:

```powershell
cd "E:\eve_jump_planner"
.\BUILD_RELEASE.bat
```

Expected v3.5.3 output:

- `New_Eden_Command_Setup_v3.5.3.exe`
- `New_Eden_Command_Update_v3.5.3.ejpupdate`
- `latest.json`
- `SHA256SUMS.txt`

The internal updater identity remains `eve-jump-planner`, the frozen executable remains `EVE Jump Planner.exe`, the Inno Setup AppId is unchanged, and the existing install directory is preserved intentionally so v3.5.3 upgrades existing installations in place. User data remains under `%USERPROFILE%\.eve_jump_planner`.
