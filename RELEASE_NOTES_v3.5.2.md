# New Eden Command v3.5.2

## SDE type-name import fix

This release fixes the EVE Data Update failure introduced by the stricter v3.5.1 name-index validation.

### Fixed

- SDE ZIP members are now selected by exact basename rather than loose suffix matching.
- The item/ship/skill name importer now explicitly requires CCP's canonical `types.jsonl`.
- Defensive support was added for `_value`-wrapped JSONL object records.
- Failed imports now report the selected member, records scanned and names found.
- The database integrity guard still refuses to replace a healthy local database with an incomplete type-name index.
- Local SDE schema version bumped so v3.5.2 performs one clean rebuild.

### Expected result

A successful data rebuild should import tens of thousands of type names and retain readable item, ship, skill and system names throughout the application.

User data remains outside the install directory under `%USERPROFILE%\.eve_jump_planner`.
