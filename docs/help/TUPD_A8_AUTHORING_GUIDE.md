# Tupd Authoring Guide — A8a3 Complete Isolated Workflow

## 1. What Tupd authoring produces

A Tupd recipe is a data-only instruction that combines a base item, parts, interfaces, sockets, validation rules, costs, penalties, and a result definition. A committed sandbox result becomes a portable `.tupdinstance`. Neither file contains executable code.

The A8 workflow proves authoring and testing. It does **not** install the result into the player's live inventory.

## 2. Recipe identity

Use a stable `recipe_id` such as:

```text
user.signal-grip-wide-r2
```

Use **Duplicate Recipe** when starting from a shipped recipe. It creates a new identity at revision 1 and records `authoring_parent_recipe`. Use **Bump Revision** when publishing a new version of the same recipe. A result instance stores the recipe revision used to create it.

## 3. Inputs and consumption

Every recipe lists `inputs`. The base item normally remains retained. Tupd Tape must be present and consumed. Parts may be consumed or retained depending on the design.

Typical patterns:

```text
weapon + compatible part + Tupd Tape
weapon + forced improvised part + Tupd Tape
weapon + Tupd Tape
weapon + matching duplicate + Tupd Tape
object parts + Tupd Tape
```

A failed graph check, preview, or commit consumes nothing.

## 4. Interfaces and sockets

An interface describes what a part provides. A socket describes where it can connect. The A8 starter palette provides guidance:

| Part | Interface | Suggested sockets |
|---|---|---|
| Signal Grip | `socket.grip` | `grip`, `body` |
| Office Bracket | `object.office` | `body`, `mount` |
| Stability Upgrade | `upgrade.stability` | `signal`, `body` |
| Wall Panel | `object.barrier` | `anchor`, `mount` |
| Universal Mount Bracket | `socket.body` | `mount`, `body`, `anchor` |
| Matching duplicate weapon | `weapon.duplicate.match` | `duplicate`, `body` |

Connections are encoded as:

```text
source-item > target-item @ socket
```

The Workbench writes this form for you.

## 5. Normal versus forced connections

A normal connection must use a compatible socket. A forced connection is deliberately improvised and must:

- be listed in `forced_connections`;
- include `allow_forced_connection` in validation rules;
- carry a visible stability and/or weight penalty;
- expose the warning before commit.

Auto Connect never creates a forced connection.

## 6. Graph Check tab

The deterministic analyzer reports:

- `base.missing`
- `tape.missing` or `tape.not-consumed`
- `consumed.not-input`
- `connection.malformed`
- `connection.duplicate`
- `connection.source-missing` / `target-missing`
- `connection.self`
- `connection.incompatible`
- `graph.cycle`
- `graph.orphan`
- `forced.rule-missing`
- `forced.penalty-missing`
- result/test metadata warnings

Click an issue to select its node when possible. Red graph nodes need attention. The report signature changes only when the graph contract changes.

## 7. Result definition

Define:

- result ID and display name;
- result kind;
- ghost shape;
- interfaces, sockets, and discovery tags;
- point budget;
- declared tests;
- condition, weight, stability, cost, and malfunction behavior.

Keep point budgets bounded. The result must fit existing dynamic/viewmodel pools rather than creating a new persistent environment cloud.

## 8. Preview, commit, equip/spawn, test

**Preview/Compare** checks the recipe against isolated test resources. **Commit Sandbox** creates a result and consumes only test resources. Commit does not equip it. **Equip/Spawn** activates it in a separate sandbox slot or proving ground. **Test Result** runs only declared actions.

Result states:

```text
COMMITTED / NOT EQUIPPED
EQUIPPED
SPAWNED
BROKEN
```

## 9. Native visual inspection

Use the standalone native stage or F5 in a protected room.

- Assembled view shows the compact result.
- Exploded view separates part nodes around the body and adds guide axes.
- Result view shows lifecycle state.
- Interfaces view highlights interface relationships.
- Sockets view highlights attachment locations.
- Penalties view emphasizes forced/stability costs.

These are inspection views of the same data; they do not alter the recipe.

## 10. Drafts and managed export

**Save Draft** writes an unindexed working file. It is safe for incomplete work. **Export & Reload** requires a valid graph and committed result, then writes a self-contained package under `content/user/tupd`, including recipe, compiled evidence, `.tupdinstance`, test history, and Asset Doctor envelopes.

Run Asset Doctor after export. A clean package has no machine-specific absolute paths and no executable fields.

## 11. Troubleshooting

**Preview valid but commit blocked:** Graph Check found a structural error that the resource preview does not understand. Resolve the graph error.

**Result says NOT EQUIPPED:** This is expected immediately after commit. Use Equip/Spawn.

**Test blocked:** Equip/spawn first and select an action declared by the recipe.

**Native stage closes with `result none | tests 0`:** The stage was closed while still in preview state. This is not an error.

**User recipe appears as an extra catalog entry:** Managed user recipes are intentionally discovered alongside the five shipped starters.

## 12. A8 closure and next boundary

A8a3 completes the isolated recipe-authoring, result-instance, test, export, versioning, graph-validation, and inspection contracts. Live loadout ownership, durability, repair economy, and save migration remain deferred to their dedicated gate. The next Alpha Integration phase is A9 machine profiling and automatic protected-profile promotion.
