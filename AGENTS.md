# Anti-Fate Engine — invariants for future changes

Read this file before changing `gui.py`, `bot.py`, `lcu_watcher.py`, or `utils/lcu.py`.

## Safety invariants

1. **Automatic dimmer is fail-closed.** Every automatic brightness or mode write must pass both gates:
   - `auto_dimmer_switch_enabled` is `True`.
   - `dimmer_enabled` is `True`.
   Manual slider and manual mode changes may still work when auto-switch is off.
   `reset_dimmer()` is an automatic callback and must never bypass these gates.

2. **LCU connection is not champion roster state.** A successful gameflow/LCU request proves connection. A roster request can fail or return an empty valid list. Never use `bool(owned_champions)` as the connection signal.

3. **One visible runtime status source.** Do not add a second status badge that repeats the beacon text. Use one status sentence with a dot/color. `LCU` connection and Arena configuration are separate state domains.

4. **Arena action state is explicit.** Pick Intent is not final Pick. Use action group order and explicit `isInProgress is True`. Missing `isInProgress` is unknown and must wait. Never use a default `True`.

5. **Arena champion IDs are canonical.** LCU inventory may expose `60000 + baseId` Arena/Jade aliases, while Champ Select actions use `baseId` (`60053` and `53` are Blitzcrank). Always pass IDs through `arena_config.champion_id()` before config, roster, ban-list, action, or read-back comparisons. Never compare raw IDs.

6. **No attempt-count or fixed-delay phase detection.** Do not wait for a magic fourth poll or a hard-coded sleep to infer Ban/Pick. Ban uses the local active ban action. Pick uses the local pick action after the Ban group. Ban IDs from the action group may be used when the client leaves the summary empty, but only after the real Pick group is active.

7. **Worker lifecycle is authoritative.** Do not clear the current bot or enable START until the worker has exited. Stale worker callbacks must be rejected by generation/state guards.

## Required verification

Run these commands before reporting a change complete:

```text
.venv/Scripts/python.exe _test_bot_lcu.py
.venv/Scripts/python.exe _test_arena_select.py
.venv/Scripts/python.exe _test_lcu.py
.venv/Scripts/python.exe _test_arena_config.py
.venv/Scripts/python.exe -m py_compile gui.py constants.py bot.py lcu_watcher.py utils/lcu.py
```

Mock tests do not prove live LCU behavior. Do not claim live success unless the user performs the live GUI test and provides the contiguous log block.

## Scope rules

- Keep the single scroll container.
- Do not reintroduce pixel input or champion locking.
- Do not change user config or runtime logs in a source commit.
- Add a focused regression test for every live bug.
