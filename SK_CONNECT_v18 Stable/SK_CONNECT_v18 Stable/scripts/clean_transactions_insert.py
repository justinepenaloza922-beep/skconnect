#!/usr/bin/env python3
"""
Take a raw INSERT ... VALUES (...) SQL file and produce a cleaned, numeric-valued,
lowercased-category upsert SQL for Postgres with `ON CONFLICT (id) DO UPDATE`.

Usage:
  python scripts/clean_transactions_insert.py input.sql > upsert_transactions.sql

Assumptions:
- The input SQL contains a single INSERT statement with a VALUES list.
- Tuples use single quotes for text and do not contain unescaped nested single quotes
  (the script will escape single quotes by doubling them).
- Columns order expected: id, project_id, title, amount, type, category, date, description, barangay

The script is conservative and aims to produce a safe upsert. Inspect output before running.
"""
import re
import sys


def split_tuple(s):
    """Split a tuple string into fields respecting single quotes."""
    fields = []
    cur = []
    in_quote = False
    esc = False
    quote_char = "'"
    for ch in s:
        if esc:
            cur.append(ch)
            esc = False
            continue
        if ch == "\\":
            # keep escape as part of value
            esc = True
            cur.append(ch)
            continue
        if ch == quote_char:
            in_quote = not in_quote
            cur.append(ch)
            continue
        if ch == ',' and not in_quote:
            fields.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        fields.append(''.join(cur).strip())
    return fields


def unquote(s):
    s = s.strip()
    if len(s) >= 2 and ((s[0] == "'" and s[-1] == "'") or (s[0] == '"' and s[-1] == '"')):
        return s[1:-1]
    return s


def sql_escape(s):
    return s.replace("'", "''")


def normalize_row(tokens):
    # expected order: id, project_id, title, amount, type, category, date, description, barangay
    if len(tokens) < 9:
        raise ValueError('Expected 9 columns per tuple, got {}'.format(len(tokens)))
    id_raw = tokens[0]
    project_id_raw = tokens[1]
    title_raw = tokens[2]
    amount_raw = tokens[3]
    type_raw = tokens[4]
    category_raw = tokens[5]
    date_raw = tokens[6]
    desc_raw = tokens[7]
    barangay_raw = tokens[8]

    # integers
    id_val = unquote(id_raw)
    project_id_val = unquote(project_id_raw)
    # title
    title_val = sql_escape(unquote(title_raw))
    # amount -> numeric literal (no quotes)
    amount_val = unquote(amount_raw)
    # try to convert to float
    try:
        if amount_val == '':
            amount_val = '0'
        # remove commas if any
        amount_val = amount_val.replace(',', '')
        float(amount_val)
    except Exception:
        # fallback to 0
        amount_val = '0'

    # type and category -> normalized lowercase
    type_val = sql_escape(unquote(type_raw).strip()).lower()
    category_val = sql_escape(unquote(category_raw).strip()).lower()

    # date -> keep as text (assume YYYY-MM-DD)
    date_val = sql_escape(unquote(date_raw))
    # description and barangay
    desc_val = sql_escape(unquote(desc_raw))
    barangay_val = sql_escape(unquote(barangay_raw))

    # Build SQL literal representations
    id_sql = id_val
    project_id_sql = project_id_val if project_id_val != '' else 'NULL'
    title_sql = "'{}'".format(title_val)
    amount_sql = amount_val
    type_sql = "'{}'".format(type_val)
    category_sql = "'{}'".format(category_val)
    date_sql = "'{}'".format(date_val)
    desc_sql = "'{}'".format(desc_val)
    barangay_sql = "'{}'".format(barangay_val)

    return [id_sql, project_id_sql, title_sql, amount_sql, type_sql, category_sql, date_sql, desc_sql, barangay_sql]


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/clean_transactions_insert.py input.sql', file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    txt = open(path, 'r', encoding='utf-8').read()

    # locate VALUES ( ... ); block
    m = re.search(r'VALUES\s*\((.*)\)\s*;?\s*$', txt.strip(), flags=re.S)
    if not m:
        # more tolerant: find first VALUES and then take parentheses contents to the last closing paren before semicolon
        vm = re.search(r'VALUES\s*(\(.*\))\s*;?', txt.strip(), flags=re.S)
        if not vm:
            print('Could not find VALUES(...) block in input', file=sys.stderr)
            sys.exit(1)
        vals_block = vm.group(1)
    else:
        vals_block = m.group(1)

    # split into tuples: this is naive but works for patterns like ( ... ), ( ... ), (...)
    # remove leading/trailing parens if the regex captured inner only
    s = vals_block.strip()
    # Now split top-level tuples by looking for '),\s*(' boundaries
    tuples = []
    depth = 0
    cur = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
            cur.append(ch)
            i += 1
            continue
        if ch == ')':
            depth -= 1
            cur.append(ch)
            i += 1
            # if depth == 0 and next non-space char is comma, it's a tuple separator
            if depth == 0:
                tuples.append(''.join(cur).strip())
                cur = []
                # skip following comma+spaces
                while i < len(s) and s[i] in ', \n\r\t':
                    i += 1
                continue
            continue
        cur.append(ch)
        i += 1
    if cur:
        remaining = ''.join(cur).strip()
        if remaining:
            tuples.append(remaining)

    cleaned_rows = []
    for t in tuples:
        # remove outer parentheses
        t2 = t.strip()
        if t2.startswith('(') and t2.endswith(')'):
            inner = t2[1:-1]
        else:
            inner = t2
        fields = split_tuple(inner)
        cleaned = normalize_row(fields)
        cleaned_rows.append(cleaned)

    # emit upsert SQL
    cols = ['id','project_id','title','amount','type','category','date','description','barangay']
    print('BEGIN;')
    print('CREATE TEMP TABLE __tmp_tx LIKE public.transactions ON COMMIT DROP;' )
    # the above is optional and may not work in all PG versions; keep it but it's okay if users ignore
    print('')
    print('INSERT INTO public.transactions ({}) VALUES'.format(','.join('"{}"'.format(c) for c in cols)))
    out_vals = []
    for r in cleaned_rows:
        out_vals.append('  ({})'.format(','.join(r)))
    print(',\n'.join(out_vals) + '\nON CONFLICT (id) DO UPDATE SET\n  project_id = EXCLUDED.project_id,\n  title = EXCLUDED.title,\n  amount = EXCLUDED.amount,\n  type = lower(EXCLUDED.type),\n  category = lower(EXCLUDED.category),\n  date = EXCLUDED.date,\n  description = EXCLUDED.description,\n  barangay = EXCLUDED.barangay;')
    print('COMMIT;')

if __name__ == '__main__':
    main()
