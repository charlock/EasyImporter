"""复用 test_core 的 env 夹具（SQLite 元数据库 + TestClient），供新增测试模块使用。

test_core.py 自身定义了同名夹具，模块内定义优先，不受这里影响。
"""

from test_core import env  # noqa: F401  (pytest 靠导入注册夹具)
