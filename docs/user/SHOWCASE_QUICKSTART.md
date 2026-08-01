# 3D Environment & Physics Showcase Quick Start

Launch the full desktop/Studio tool:

```bash
./scripts/launch_showcase.sh
```

The left catalog contains two five-object starter sets plus managed user exports. Select an asset to inspect it immediately. In the middle point preview:

- drag with the left mouse button to orbit;
- use the wheel to zoom;
- switch Source, Density, Material, or Light view;
- switch 100%, 50%, 25%, or 12.5% deterministic LOD;
- toggle the fitted collision outline;
- toggle bounded Actor/Playbook motion intent;
- save a portable PPM snapshot.

The Inspector edits `.scphysics`, including visible collision dimensions. **Auto-fit to points** restores the collision envelope from finite PCP3 positions. The five **Animate** buttons start visible, bounded Drop, Bounce, Slide, Throw, and Break motion in the desktop preview; the collision outline follows the same translation and yaw as the point object. **Stop Motion** returns to the static inspection view. Actor/Playbook preview continuously deforms the displayed geometry so animation intent is visible rather than report-only.

Launch the selected asset in the real native stage with **Native Stage**, or launch the default starter directly:

```bash
./scripts/launch_showcase_native.sh
```

Native controls:

```text
1–5     Drop, Bounce, Slide, Throw, Break
C       Toggle collision outline
L       Cycle LOD
V       Cycle Source/Density/Material/Light
P       Toggle Actor/Playbook preview
T       Toggle camera follow
O       Toggle automatic test looping
H       Toggle help/status board
S       Save native PPM snapshot
Space   Pause
R       Reset current test
F/Home  Reset to the fixed stage-space camera
Mouse   Orbit
Wheel   Zoom
Esc     Close
```

Managed export writes a self-contained package to `content/user/showcase/<asset_id>/`, including PCP3, cloud, certificate, `.scphysics`, `.scshowcase`, provenance, copied source data, and Asset Doctor envelopes. **Export & Reload** immediately selects the managed copy so portability can be tested without relying on the original import path. Absolute project/source paths are converted to project-relative metadata and envelope hashes are refreshed after repair.

The native stage starts with camera follow off so motion is visible against the bounded floor. Press `T` when a moving object should remain centered. Point radii are normalized for the real SignalCloud renderer; the native object should resemble the desktop preview rather than appearing as oversized overlapping discs.

The importer never executes `.script`, `.udata`, OBJ helpers, or external applications. FBX is not an Alpha import target; convert it to OBJ or a later audited glTF path outside the engine.
