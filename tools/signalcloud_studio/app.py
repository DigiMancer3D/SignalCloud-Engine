from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .context import ToolContext
from .documents import DocumentContextBus, DocumentContextStore
from .plugin_api import PluginCatalog
from .plugins import FontStudioPlugin, JitterTexturePlugin, LightLabPlugin, PCP3Plugin, PlaybookPlugin, ShowcasePlugin, TupdWorkbenchPlugin


def build_catalog() -> PluginCatalog:
    return PluginCatalog([PCP3Plugin(), LightLabPlugin(), JitterTexturePlugin(), PlaybookPlugin(), FontStudioPlugin(), ShowcasePlugin(), TupdWorkbenchPlugin()])


def build_context(
    root_path: Path,
    tool_key: str = "studio-host",
    *,
    document: Path | None = None,
) -> ToolContext:
    root = Path(root_path).expanduser().resolve()
    store = DocumentContextStore.for_project(root)
    document_context = store.read()
    if document is not None:
        document_context = store.publish(
            document_context,
            active_document=document,
            owner_tool=tool_key,
            dirty=False,
        )
    bus = DocumentContextBus(document_context)
    return ToolContext(
        project_root=root,
        active_tool_key=tool_key,
        document_context=document_context,
        document_store=store,
        document_bus=bus,
    )


def launch_tool(
    root_path: Path,
    tool_key: str = "pcp3",
    *,
    document: Path | None = None,
) -> int:
    context = build_context(root_path, tool_key, document=document)
    return build_catalog().get(tool_key).launch(context)


def launch_host(root_path: Path) -> int:
    from .host import launch_host as run_host

    context = build_context(root_path, "studio-host")
    return run_host(context, build_catalog())


def main(root_path: Path | None = None, argv: Sequence[str] | None = None) -> int:
    # Historical in-process callers intentionally continue to receive PCP3.
    if root_path is not None:
        return launch_tool(Path(root_path), "pcp3")

    parser = argparse.ArgumentParser(description="SignalCloud Studio")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--tool", default=None)
    parser.add_argument("--document", type=Path)
    parser.add_argument("--list-tools", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    catalog = build_catalog()
    if args.list_tools:
        for info in catalog.infos():
            host_mode = "embedded" if info.can_embed else "standalone"
            print(f"{info.key}\t{info.display_name}\t{info.category}\t{host_mode}\t{info.description}")
        return 0
    if args.tool:
        return launch_tool(args.root, args.tool, document=args.document)
    return launch_host(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
