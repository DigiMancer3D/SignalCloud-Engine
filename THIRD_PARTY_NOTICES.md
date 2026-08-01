# Third-party notices

SignalCloud Engine `v0.1.0-alpha.1` does not vendor external dependency source
trees or prebuilt third-party binaries in the public source archives.

## Build/runtime dependencies

- **SDL3 3.4.10** — pinned fallback source archive in `CMakeLists.txt`; upstream
  zlib License. SDL3 is downloaded only when a compatible installation is not
  found.
- **OpenGL / Mesa or vendor driver stack** — supplied by the operating system or
  GPU vendor; licensing is determined by the installed distribution packages.
- **Python 3, Tk, CMake, Ninja, GCC/Clang, X11, Wayland, and related system
  libraries** — supplied by the user's operating system; each retains its
  upstream/distribution license.

The project does not copy those license texts into the source archive because it
does not redistribute their code or binaries. Any future binary/AppImage/package
release must include the exact notices required by the libraries actually
bundled in that package.

## Project-authored assets

Showcase starter assets with provenance records declaring `CC0-1.0` are released
under CC0 1.0 Universal. The complete text is included at
`LICENSES/CC0-1.0.txt`.

Managed content marked `LicenseRef-SignalCloud-User-Authored` is covered by the
repository MIT license in this public release unless the asset itself declares a
different license.

## User-imported content

Importers can load user-provided fonts, images, point clouds, models, scripts as
data, and other assets. Inclusion in a local project does not grant redistribution
rights. Contributors and redistributors are responsible for verifying the rights
for any content they add.
