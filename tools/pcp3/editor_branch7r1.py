from __future__ import annotations

from pathlib import Path

from tools.pcp3 import editor_branch7 as branch7


class PCP3Editor(branch7.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch7_R1"
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 7 R1 Interaction Authoring Repair")
        self.update_status("Branch 7 R1 active · callback repair · direct trigger-authoring bridge · guarded runtime chain")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
