# New Eden Command v3.4.6 — EVE Skill Import + Performance Patch

New Eden Command v3.4.6 is a focused compatibility and responsiveness patch on top of v3.4.5. It keeps the responsive UI/sidebar work while fixing the Skill Planner clipboard output for EVE imports and reducing unnecessary heavy Command Center redraws.

## What changed in v3.4.6

### EVE-compatible Skill Planner clipboard

- **COPY PLAN** is now labelled **COPY FOR EVE**.
- Clipboard lines are exported as plain `Skill Name level` entries.
- Display-only list numbers such as `01.` are no longer copied.
- Training-time annotations are no longer copied into the EVE import text.
- Example clipboard output:

```text
Jump Drive Calibration 5
Jump Fuel Conservation 5
Jump Freighters 4
```

This leaves the human-readable ordering in the planner table while making the clipboard payload suitable for the EVE client importer.

### Faster page switching / Command Center loading

- The expensive Command Center asset/contract/industry/skill-queue render is now cached against the synced companion-data state.
- Switching away from and back to Command Center no longer rebuilds large asset inventories when the underlying synced ESI data has not changed.
- Startup no longer eagerly renders the full Command Center asset inventory while the user is on Flight Deck.
- Asset market-price refreshes no longer force a hidden Command Center asset regroup when that page is not visible.
- A completed character sync or SDE rebuild still forces a correct full refresh so data does not become stale.

### Preserved v3.4.5 UI fixes

- DPI-safe navigation width so full sidebar labels remain visible when expanded.
- Responsive icon-only sidebar on genuinely narrow windows.
- Scrollable major pages and horizontal scrolling for wide tables.
- Reflowing Flight Deck, Command Center and global hull/skill controls.
- New Eden Command branding and Windows icon/shortcut.

## Upgrade compatibility

The updater identity remains `eve-jump-planner` and the internal frozen executable filename remains `EVE Jump Planner.exe` deliberately. This keeps the v3.4.3+ onedir updater restart path compatible.

The installer keeps the existing Inno Setup AppId and `%LOCALAPPDATA%\Programs\EVE Jump Planner` installation directory so the release upgrades the current installation in place. Visible shortcuts remain branded **New Eden Command**.

User data remains under `%USERPROFILE%\.eve_jump_planner` and is not moved or deleted.

## Build

From PowerShell:

```powershell
cd "E:\eve_jump_planner"
.\BUILD_RELEASE.bat
```

The release output is written to `releases`:

- `New_Eden_Command_Setup_v3.4.6.exe`
- `New_Eden_Command_Update_v3.4.6.ejpupdate`
- `latest.json`
- `SHA256SUMS.txt`

Because the installed app is already using the onedir runtime, v3.4.6 can be installed through the in-app `.ejpupdate` path. The Setup EXE remains available for a normal reinstall or direct upgrade.

## Preserved features

- Capital jump calculator and systems-in-range search.
- Automatic multi-hop route planning with legal cyno and station-aware policies.
- Tactical route map and EVE destination/waypoint bridge.
- Multiple EVE characters through CCP SSO/PKCE with actual jump skills.
- Command Center telemetry, assets, contracts, industry, wallet, clones and skill queue.
- Capital Operations, fleet manifest and fuel logistics.
- Hunting / roam-intelligence tools using public CCP activity data.
- Skill Planner with prerequisite-aware ordering.
- Asset grouping by system, nested-root tracing, full ESI pagination, valuation and fitted-module exclusion.
- Verified format-2 `.ejpupdate` packages with SHA-256 checks, backups and rollback support.
