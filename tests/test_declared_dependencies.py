"""Every third-party module imported by the code is declared in pyproject.toml.

A module that only arrives as someone else's dependency (httpx via openai) works
in any environment built from pyproject.toml and fails in a hand-assembled one.
"""
import ast
import glob
import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# import name -> distribution name, where they differ
DIST_OF_MODULE = {
    'PIL': 'pillow',
    'cupy': 'cupy-cuda12x',
    'bs4': 'beautifulsoup4',
    'dotenv': 'python-dotenv',
    'sklearn': 'scikit-learn',
    'langchain_text_splitters': 'langchain-text-splitters',
}


def _dist(requirement):
    return re.split(r'[=<>\[;~! ]', requirement, maxsplit=1)[0].lower().replace('_', '-')


def _declared():
    with open(os.path.join(ROOT, 'pyproject.toml'), 'rb') as f:
        project = tomllib.load(f)['project']
    reqs = list(project['dependencies'])
    for extra in project.get('optional-dependencies', {}).values():
        reqs.extend(extra)
    return {_dist(r) for r in reqs}


def _imported_modules():
    modules = {}
    files = glob.glob(os.path.join(ROOT, 'src', '*.py')) + [os.path.join(ROOT, 'app.py')]
    for path in files:
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                modules.setdefault(name.split('.')[0], os.path.basename(path))
    return modules


def test_imported_third_party_modules_are_declared():
    declared = _declared()
    missing = {
        module: path
        for module, path in _imported_modules().items()
        if module not in sys.stdlib_module_names
        and module not in ('src', 'app')
        and DIST_OF_MODULE.get(module, module.lower().replace('_', '-')) not in declared
    }
    assert not missing, f'imported but not declared in pyproject.toml: {missing}'
