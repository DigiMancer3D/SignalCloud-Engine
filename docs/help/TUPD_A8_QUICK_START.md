# Tupd A8 Quick Start — A8a3

A8a3 closes the isolated Tupd authoring track. The full reference is in `docs/help/TUPD_A8_AUTHORING_GUIDE.md`.

## Safe starter workflow

1. Open **Compatible Signal Grip**.
2. Press **Duplicate Recipe** before editing a shipped starter.
3. Add or select graph inputs, mark each extra input retained or consumed, and connect parts to a target socket.
4. Press **Validate Graph**. Red nodes are orphans or blocked subjects. The **Graph Check** tab explains every issue.
5. Use **Auto Connect** only for deterministic starter-safe suggestions.
6. Press **Preview/Compare**.
7. Press **Commit Sandbox**. The result should read `COMMITTED / NOT EQUIPPED`.
8. Press **Equip/Spawn Result**, select a declared action, and press **Test Result**.
9. Use **Export & Reload** only after the graph is valid and a result has been committed.

## Native inspection controls

```text
Left / Right   change recipe
P              preview / compare
C              commit result (not equipped)
E              equip or spawn
A              cycle declared test action
X              run selected test
G              assembled / exploded ghost
V              Result / Interfaces / Sockets / Penalties view
I              information overlay on / off
D              clear committed result
R              reset sandbox
F or Home      reset camera
```

## Recipe versions

- **Duplicate Recipe**: new user recipe ID, revision 1, parent history retained.
- **Bump Revision**: same recipe identity, next revision.
- **Save Draft**: unindexed working copy in `user_data/studio/tupd_drafts`.
- **Export & Reload**: managed, Asset Doctor-visible package in `content/user/tupd`.

## Safety boundary

Preview and graph validation consume nothing. Commit, equip/spawn, and tests use only test inventory and test XAR. Normal inventory, live weapon state, live XAR, and normal save data remain unchanged.
