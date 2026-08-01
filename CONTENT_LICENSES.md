# Content licensing and starter-pack policy

SignalCloud Engine uses a mixed-license repository. The license attached to a
specific file or managed asset controls that material.

## Default license: MIT

Unless a file or managed asset explicitly declares another license, the engine,
tools, project-authored documentation, schemas, and original ALMOND SIGNAL:
LIVE TAPE material in this repository are released under the root `LICENSE`
(MIT).

## Public starter data: CC0 where explicitly marked

Original starter-pack data is dedicated under CC0 1.0 Universal only when its
provenance or managed metadata declares:

```text
license_id: CC0-1.0
```

The complete CC0 text is included at `LICENSES/CC0-1.0.txt`. The folder notice
at `content/starter/LICENSE.md` explains the starter-pack boundary.

An asset being stored under `content/starter/` does not, by itself, override an
asset-specific license declaration. The provenance or source record is the
authoritative scope marker.

## Third-party and imported material

Third-party dependencies and externally sourced assets retain their upstream
licenses. They are not converted to MIT or CC0 by being referenced or imported
by SignalCloud. See `THIRD_PARTY_NOTICES.md`.

User-imported fonts, images, models, point clouds, sounds, and other files remain
the responsibility of the person importing or redistributing them. Local use
does not automatically grant permission to publish those files.

## Branding and endorsement

The CC0 starter-data dedication does not grant permission to claim endorsement
by DigiMancer3D or the SignalCloud Engine project. Project names, logos, and
other branding are not starter data and are not included in the CC0 dedication
unless a specific file says otherwise.

## Adding a new public starter asset

A public starter asset should include a provenance or source record with, at
minimum:

```text
asset_id or recipe_id
origin
creator
license_id
source_kind
data_only
redistribution_allowed
```

Use `CC0-1.0` only for material you created or have authority to dedicate under
CC0. Preserve a third-party asset's original license and required attribution.
Do not publish material with unknown or unclear redistribution rights.
