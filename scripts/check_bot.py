"""The upload rules the sandbox enforces: one file under 200 KB, standard library only, an Agent class."""
import ast
import os
import sys

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot.py")
source = open(path).read()
size = len(source.encode())
assert size <= 200_000, "bot.py is %d bytes; the limit is 200,000" % size
tree = ast.parse(source, feature_version=(3, 12))
for node in ast.walk(tree):
    names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
        [node.module] if isinstance(node, ast.ImportFrom) else []
    for name in names:
        assert name.split(".")[0] in sys.stdlib_module_names, "non-stdlib import: %s" % name
assert any(isinstance(n, ast.ClassDef) and n.name == "Agent" for n in tree.body), "no Agent class"
print("bot.py ok: %d bytes" % size)
