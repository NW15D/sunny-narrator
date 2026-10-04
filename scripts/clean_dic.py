"""Clean a .dic: normalise fields, merge case/gender duplicates, drop junk."""
import csv, sys, collections
import spacy

src_path, out_path, report_path = sys.argv[1:4]
GENDER = {'он': 'he', 'она': 'she', 'оно': 'it', 'они': 'they'}
nlp = spacy.load('en_core_web_lg', disable=['ner', 'parser', 'tagger', 'lemmatizer', 'attribute_ruler'])
vocab = nlp.vocab


def ordinary(word):
    return len(word.split()) == 1 and (vocab.has_vector(word) or vocab.has_vector(word.lower()))


rows, report = [], collections.defaultdict(list)
for line in open(src_path, encoding='utf-8-sig'):
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    s, rest = line.split('=', 1)
    f = next(csv.reader([rest.strip()]))
    f = [x.strip() for x in f] + [''] * 4
    t, cat, g, notes = f[0], f[1].upper(), f[2], ','.join(f[3:]).strip(', ')
    g = GENDER.get(g.casefold(), g.casefold())
    if g not in ('he', 'she', 'it', 'they'):
        g = ''
    s = s.strip()
    if not s or not t:
        report['empty'].append(line)
        continue
    rows.append(dict(s=s, t=t, cat=cat, g=g, notes=notes))

# 1. merge duplicates by casefolded source
groups = collections.OrderedDict()
for r in rows:
    groups.setdefault(r['s'].casefold(), []).append(r)
merged = []
for k, g in groups.items():
    if len(g) > 1:
        report['merged'].append(' | '.join(f"{r['s']}={r['t']}/{r['cat']}/{r['g']}" for r in g))
    g.sort(key=lambda r: (not r['cat'], not r['s'][0].isupper(), ))
    best = dict(g[0])
    for r in g[1:]:
        best['g'] = best['g'] or r['g']
        if len(r['notes']) > len(best['notes']):
            best['notes'] = r['notes']
    merged.append(best)

# 2. drop ordinary words (lowercase, spaCy has a vector) and junk
RESCUE = {'runcible','autogun','comlink','biomech','netlink','downlink','hooper','hooder'}
kept = []
for r in merged:
    s = r['s']
    if s in RESCUE:
        r['cat'] = r['cat'] or 'TERM'
        kept.append(r)
        continue
    if s[0].islower() and ordinary(s):
        report['ordinary'].append(f"{s} = {r['t']}")
        continue
    if s[0].islower() and not r['cat']:
        r['cat'] = 'TERM'
    if s[0].islower() and r['cat'] in ('PERSON', 'ORG', 'GPE', 'LOC') and len(s.split()) == 1 and ordinary(s):
        continue
    kept.append(r)

# 3. broken variants: same translation, source differs by a cut/extra tail from another entry
by_t = collections.defaultdict(list)
for r in kept:
    by_t[r['t'].casefold()].append(r)
drop = set()
for t, g in by_t.items():
    for a in g:
        for b in g:
            if a is not b and b['s'].casefold().startswith(a['s'].casefold()) and 0 < len(b['s']) - len(a['s']) <= 2:
                bad = b if not ordinary(b['s']) and ordinary(a['s']) or a['s'][-1] not in 'es' and False else b
                # keep the shorter stem, drop the longer variant only if the longer is not a known word
                if not ordinary(b['s']):
                    drop.add(id(b))
                    report['variant'].append(f"{b['s']} (≈ {a['s']}) = {t}")
kept = [r for r in kept if id(r) not in drop]

with open(out_path, 'w', encoding='utf-8') as out:
    out.write('# Vocabulary for series (cleaned)\n# Format: source = target, category, gender, notes\n\n')
    for cat in ['PERSON', 'GPE', 'LOC', 'FAC', 'ORG', 'PRODUCT', 'EVENT', 'TERM']:
        grp = [r for r in kept if r['cat'] == cat]
        if not grp:
            continue
        out.write(f'# {cat} ({len(grp)} terms)\n')
        for r in grp:
            tgt = f'"{r["t"]}"' if ',' in r['t'] else r['t']
            out.write(f"{r['s']} = {tgt}, {r['cat']}, {r['g']}, {r['notes']}\n")
        out.write('\n')
    rest = [r for r in kept if r['cat'] not in ('PERSON', 'GPE', 'LOC', 'FAC', 'ORG', 'PRODUCT', 'EVENT', 'TERM')]
    if rest:
        out.write('# OTHER\n')
        for r in rest:
            out.write(f"{r['s']} = {r['t']}, {r['cat']}, {r['g']}, {r['notes']}\n")

with open(report_path, 'w', encoding='utf-8') as rp:
    for k, v in report.items():
        rp.write(f'## {k} ({len(v)})\n' + '\n'.join(v) + '\n\n')
print(len(rows), '->', len(kept), {k: len(v) for k, v in report.items()})
