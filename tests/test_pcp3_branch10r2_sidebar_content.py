from __future__ import annotations

import unittest

from tools.pcp3.editor_branch10r2 import PCP3Editor
from tools.pcp3.editor_branch10r1 import PCP3Editor as Branch10R1Editor


class Branch10R2SidebarContentTests(unittest.TestCase):
    def test_r2_extends_the_accepted_sidebar_revision(self) -> None:
        self.assertTrue(issubclass(PCP3Editor, Branch10R1Editor))

    def test_r2_overrides_the_geometry_sensitive_paths(self) -> None:
        self.assertIn('_layout_sidebar_content', PCP3Editor.__dict__)
        self.assertIn('_make_notebook_tabless', PCP3Editor.__dict__)
        self.assertIn('_reserve_bottom_status_bar', PCP3Editor.__dict__)
        self.assertIn('_restack_sidebar_content', PCP3Editor.__dict__)


if __name__ == '__main__':
    unittest.main()
