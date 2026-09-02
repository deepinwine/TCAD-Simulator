"""M12：桌面启动器冒烟测试。"""
import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")


class LauncherTests(unittest.TestCase):
    def test_import_and_find_port(self):
        from tcad_studio import find_free_port
        port = find_free_port(18765)
        self.assertTrue(18765 <= port < 18865)

    def test_py_compile(self):
        import py_compile
        py_compile.compile("tcad_studio.py", doraise=True)
        py_compile.compile("tcad_studio.spec", doraise=True,
                           cfile="/tmp/_spec.pyc")  # spec 不是 .py，但语法兼容


if __name__ == "__main__":
    unittest.main()
