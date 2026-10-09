# New Eden Command v3.5.1

## Name Resolution & Data Integrity

This maintenance release keeps all v3.5.0 Hunting / Roam Command features and fixes the remaining unresolved EVE item and location labels.

### Fixed

- Full CCP SDE item/type-name validation; an incomplete type index is no longer considered healthy.
- Universe-wide solar-system display index for current/special system ID ranges while keeping capital navigation restricted to its existing supported system set.
- Exact ESI station/location names now take priority over reconstructed SDE labels.
- Missing system metadata can be repaired from public ESI and cached with the character snapshot.
- Accessible player structures continue to resolve through authenticated ESI and now map more reliably to readable system names.
- Cached asset/ship/skill names are primed in bulk, reducing large-inventory render delays.
- Failed/partial type-name imports no longer replace an existing working EVE database.

### One-time action after update

v3.5.1 increments the local EVE database schema. On first launch, allow the automatic EVE data rebuild to complete. Then sync the affected character(s) once so authenticated structure/location names can be refreshed.
