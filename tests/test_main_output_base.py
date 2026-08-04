"""D1-fix: output_base must stay defined in main() — EPUB writer and the
FB2 fallback path reference it after the D1 refactor."""
import ast
import os


def test_main_assigns_output_base():
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    main_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == 'main'
    )
    assigned = set()
    for n in ast.walk(main_fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            assigned.add(n.id)
    assert 'output_base' in assigned, \
        "main() uses output_base (EPUB/fallback writers) but never assigns it"
