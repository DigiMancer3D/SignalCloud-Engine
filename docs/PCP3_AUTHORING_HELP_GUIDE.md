# PCP3 Authoring Help Guide

The authoring guide connects quick-start tasks, nine environment modes, troubleshooting, and safe export.

## Navigation

- Use the Help Center search to jump directly to a topic.
- Context help prefers the current editor tab, mode, and tool.
- All examples are data-only and remain inside the project root.

## 1. Editor mental model

- A PCP3 document stores authored points, layers, metadata, runtime intent, and protected extension fields.
- The editor changes the document; the renderer previews the current document without inventing hidden source data.
- Undo history is local to the editing session, while explicit saves create durable revisions.

### Checkpoint 1

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 2. Canvas and camera

- Pan and zoom change only the editor view.
- Selection coordinates remain in document space.
- Reset View recenters the document without changing point positions.

### Checkpoint 2

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 3. Layers

- Use layers to separate shape, collision hints, labels, and diagnostic guides.
- Opacity is non-destructive and may be previewed before committing.
- Layer order matters when points overlap in the same projection.

### Checkpoint 3

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 4. Selection

- Drag a bounded selection rectangle around intended points.
- Moving selection preserves relative spacing.
- Duplicate before destructive transforms when exploring alternatives.

### Checkpoint 4

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 5. Saving and revision

- Use Save for the active project and Save As for a branch.
- Keep paths relative when a project belongs to a distributable pack.
- Validate after export so manifest and sidecar metadata remain synchronized.

### Checkpoint 5

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 6. Mode Guide overview

- A mode defines authoring behavior, not an executable script.
- Template application is idempotent: applying the same template twice must not silently duplicate protected structures.
- Switching modes preserves unknown fields and authored layers.

### Checkpoint 6

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 7. Room mode

- Room mode authors bounded room surfaces, door portals, and navigation intent.
- A room portal should connect declared spaces without embedding an absolute filesystem path.
- Use collision preview to find gaps before export.

### Checkpoint 7

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 8. Corridor mode

- Corridors connect room thresholds with a bounded width and height.
- Keep turns readable in both editor and world previews.
- Validate portal normals after mirroring.

### Checkpoint 8

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 9. Liquid mode

- Liquid mode marks a surface and bounded depth rather than simulating an unrestricted volume.
- Use preview waves only as diagnostics.
- Runtime budgets remain explicit.

### Checkpoint 9

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 10. Template behavior

- Templates provide safe starting values.
- Template idempotent behavior preserves user edits and extension fields.
- A template never enables runtime execution by itself.

### Checkpoint 10

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 11. Detailed Tools Guide overview

- Tools operate only on the active document and selection.
- Protected paths and unknown commands remain blocked.
- Tool previews are reversible until committed.

### Checkpoint 11

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 12. Pencil and brush

- Pencil places individual points.
- Brush stamps a bounded neighborhood.
- Strength and radius must remain visible in the HUD.

### Checkpoint 12

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 13. Eraser

- The hidden geometry eraser removes only points inside its bounded radius.
- Radius zero targets one point when supported.
- Preview selection before erasing dense layers.

### Checkpoint 13

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 14. Transform tools

- Move, rotate, flip, and scale operate around the shown pivot.
- Duplicate before large transforms.
- Check Z depth after flattening or mirroring.

### Checkpoint 14

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.

## 15. Window synchronization

- Window sync 1.3 keeps tool state, layer state, and preview state aligned.
- A detached preview must not write the project behind the editor.
- Reopen or reload when an external authoring tool changes a managed file.

### Checkpoint 15

- [ ] The intended tab or tool is active.
- [ ] The preview remains bounded and non-destructive.
- [ ] The project was saved to a repository-relative or user-managed path.
