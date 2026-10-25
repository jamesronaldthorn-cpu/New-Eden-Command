# New Eden Command v3.5.3 — Live Skill Queue Import Fix

## Fixed

- Skill Planner no longer imports only the cached Command Center skill queue.
- **Refresh + Import Queue** now refreshes the selected character token and requests the current queue directly from CCP ESI.
- Completed queue rows are defensively removed before import.
- Current trained skills are refreshed at the same time when the character has the skills scope, improving prerequisite validation.
- The freshly fetched queue is written back into the local companion cache so Skill Planner and Command Center stay aligned.
- Queue refresh runs in a worker thread so the interface remains responsive.
- Clear permission/error messages are shown if the selected character needs to be re-authorized for the skill queue scope.

## Unchanged

- The planner remains local-only; CCP ESI does not provide a public endpoint for rewriting the in-game skill queue.
- COPY FOR EVE still outputs only `Skill Name Level`, with no list numbering or training-time suffixes.
