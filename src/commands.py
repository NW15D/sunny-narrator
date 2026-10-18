"""
The commands of `app.py` / `sunny-narrator` besides a translation:

    app.py dict clean DIC                    duplicates, gender spellings, ordinary words
    app.py dict review BOOK --dic DIC        categories and genders against the book
    app.py dict extend DIC --book BOOK ...   a series dictionary carried over to new books / dictionaries
    app.py dict convert DIC fr es ...        the .dic into other target languages (LLM)
    app.py audit TRANSLATION --dic DIC --lang russian
                                             words in two alphabets, gender errors
    app.py eval BOOK --dic DIC --out RUN.json
                                             passages through the real pipeline (A/B)
    app.py clean-calibre FILE [--inplace]    Calibre markers out of a FB2/HTML file

Every command writes its result next to its input and never changes the
input itself (except clean-calibre --inplace). See docs/DICTIONARY_FORMAT.md.
"""
import argparse
import sys
from pathlib import Path

COMMANDS = ('dict', 'audit', 'eval', 'clean-calibre')


def _dict_clean(argv):
    from src import dict_clean
    ap = argparse.ArgumentParser(prog='app.py dict clean', description=dict_clean.__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dic', type=Path, help='the .dic to clean')
    ap.add_argument('-o', '--output', type=Path, help='result (default <name>.clean.dic)')
    ap.add_argument('--report', type=Path, help='report (default <result>.report.txt)')
    ap.add_argument('--model', help='spaCy model for ordinary words (default NERMODEL)')
    ap.add_argument('--keep', default='', help='comma-separated words not to drop as ordinary')
    args = ap.parse_args(argv)
    try:
        result = dict_clean.clean_file(args.dic, args.output, args.report, args.model, args.keep)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{result['before']} -> {result['after']} entries: {result['output']}")
    for name, n in result['counts'].items():
        print(f"  {name}: {n}")
    print(f"report: {result['report']}")
    return 0


def _dict_review(argv):
    from src import dict_review
    from src.config import Config
    config = Config()
    ap = argparse.ArgumentParser(prog='app.py dict review', description=dict_review.__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book', type=Path, help='the source book (.fb2, .epub, .txt)')
    ap.add_argument('--dic', type=Path, required=True, help='the .dic to review')
    ap.add_argument('-o', '--output', type=Path, help='result (default <name>.reviewed.dic)')
    ap.add_argument('--report', type=Path, help='report (default <result>.report.txt)')
    ap.add_argument('--model', default=config.nermodel,
                    help=f'spaCy model of the source language (default {config.nermodel})')
    ap.add_argument('--min-votes', type=int, default=dict_review.MIN_VOTES,
                    help=f'evidence needed for a decision (default {dict_review.MIN_VOTES})')
    ap.add_argument('--ratio', type=float, default=dict_review.RATIO,
                    help=f'share of the evidence for one side (default {dict_review.RATIO})')
    args = ap.parse_args(argv)
    try:
        result = dict_review.review_file(args.book, args.dic, args.output, args.report, args.model,
                                         args.min_votes, args.ratio, config.target_lang)
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{result['entries']} entries, {result['paragraphs']} paragraphs: "
          f"{result['changed']} change(s) in {result['output']}")
    for name, n in result['counts'].items():
        print(f"  {name}: {n}")
    print(f"report: {result['report']}")
    return 0


def _dict_extend(argv):
    from src import dict_extend, dict_review, ner
    ap = argparse.ArgumentParser(prog='app.py dict extend', description=dict_extend.__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dic', type=Path, help='the dictionary to extend')
    ap.add_argument('--book', type=Path, action='append', default=[],
                    help='a new book (.fb2, .epub, .txt); repeatable')
    ap.add_argument('--books-dir', type=Path, help='a folder of new books')
    ap.add_argument('--merge', type=Path, action='append', default=[],
                    help='another .dic whose missing entries are added; repeatable')
    ap.add_argument('-o', '--output-dir', type=Path,
                    help='folder of the result (default <name>.extended/ next to the dictionary)')
    ap.add_argument('--model', help='spaCy model of the source language (default NERMODEL)')
    ap.add_argument('--min-count-ner', type=int, default=3,
                    help='mentions in all the new books for an entity to be added (default 3)')
    ap.add_argument('--min-count-word', type=int, default=5,
                    help='mentions for an ordinary word (only with --frequent-words)')
    ap.add_argument('--frequent-words', action='store_true', help='also add frequent ordinary words')
    ap.add_argument('--keep', default='', help='comma-separated words not to skip as ordinary')
    ap.add_argument('--min-votes', type=int, default=dict_review.MIN_VOTES)
    ap.add_argument('--ratio', type=float, default=dict_review.RATIO)
    args = ap.parse_args(argv)
    import openai
    try:
        books = list(args.book)
        if args.books_dir:
            books += [Path(p) for p in ner.series_book_files(str(args.books_dir))]
        result = dict_extend.extend_file(
            args.dic, books, args.merge, args.output_dir, args.model, args.min_count_ner,
            args.min_count_word, args.frequent_words or None, args.keep, args.min_votes, args.ratio)
    except (ValueError, RuntimeError, OSError, openai.OpenAIError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{result['base']} entries + {result['added']} added, "
          f"{result['changed']} changed in the base: {result['output']}")
    for name, n in result['counts'].items():
        print(f"  {name}: {n}")
    print(f"report: {result['report']}")
    return 0


def _dict(argv):
    actions = {'clean': _dict_clean, 'review': _dict_review, 'extend': _dict_extend}
    if argv and argv[0] == 'convert':
        from src import dict_convert
        return dict_convert.main(argv[1:])
    if not argv or argv[0] not in actions:
        print("usage: app.py dict {clean,review,extend,convert} ...  (app.py dict <action> -h)", file=sys.stderr)
        return 2
    return actions[argv[0]](argv[1:])


def _clean_calibre(argv):
    from src.calibre_pipeline import _clean_calibre_markers
    ap = argparse.ArgumentParser(prog='app.py clean-calibre',
                                 description='Calibre markers (:::{#calibre_link-*}, .calibreN, '
                                             'calibre_link ids) out of a FB2/HTML/Markdown file: the '
                                             'cleanup the Calibre pipeline does on every book.')
    ap.add_argument('file', type=Path)
    ap.add_argument('--inplace', action='store_true', help='rewrite the file (default: print the result)')
    args = ap.parse_args(argv)
    cleaned = _clean_calibre_markers(args.file.read_text(encoding='utf-8'))
    if args.inplace:
        args.file.write_text(cleaned, encoding='utf-8')
        print(f"cleaned: {args.file}")
    else:
        sys.stdout.write(cleaned)
    return 0


def run(argv) -> int:
    """argv: the arguments after app.py, starting with the command."""
    command, rest = argv[0], argv[1:]
    if command == 'dict':
        return _dict(rest)
    if command == 'audit':
        from src import translation_audit
        return translation_audit.main(rest) or 0
    if command == 'eval':
        from src import prompt_eval
        return prompt_eval.main(rest) or 0
    if command == 'clean-calibre':
        return _clean_calibre(rest)
    raise ValueError(command)
