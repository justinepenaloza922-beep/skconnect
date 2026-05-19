#!/usr/bin/env python3
"""
Parse a raw INSERT ... VALUES(...) SQL file and upsert rows into Supabase `transactions` table.

Usage:
  python scripts/supabase_upsert_transactions.py raw_insert.sql [--apply]

By default the script runs in dry-run mode and prints a summary. Use `--apply` to perform the upsert.

Requires environment variables: SUPABASE_URL and SUPABASE_KEY (same as your `app.py`).
"""
import os
import re
import sys
import argparse
from supabase import create_client


def split_tuple(s):
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


def parse_insert_file(path):
    txt = open(path, 'r', encoding='utf-8').read()
    # find VALUES(...) block
    vm = re.search(r'VALUES\s*(\(.*\))\s*;?$', txt.strip(), flags=re.S)
    if not vm:
        # try looser match for whole VALUES (...) list
        m = re.search(r'VALUES\s*(\(.*\))\s*;?', txt, flags=re.S)
        if not m:
            raise ValueError('Could not locate VALUES(...) in input file')
        vals_block = m.group(1)
    else:
        vals_block = vm.group(1)

    s = vals_block.strip()
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
            if depth == 0:
                tuples.append(''.join(cur).strip())
                cur = []
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

    rows = []
    for t in tuples:
        inner = t[1:-1] if t.startswith('(') and t.endswith(')') else t
        fields = split_tuple(inner)
        if len(fields) < 9:
            raise ValueError(f'Expected 9 columns per tuple, got {len(fields)} for: {t[:60]}')
        # map expected columns
        id_val = unquote(fields[0])
        project_id_val = unquote(fields[1])
        title_val = unquote(fields[2])
        amount_val = unquote(fields[3]).replace(',','')
        type_val = unquote(fields[4]).strip().lower()
        category_val = unquote(fields[5]).strip().lower()
        date_val = unquote(fields[6])
        desc_val = unquote(fields[7])
        barangay_val = unquote(fields[8])

        # coerce types
        try:
            id_int = int(id_val)
        except Exception:
            id_int = None
        try:
            project_id_int = int(project_id_val) if project_id_val != '' else None
        except Exception:
            project_id_int = None
        try:
            amount_num = float(amount_val) if amount_val != '' else 0.0
        except Exception:
            amount_num = 0.0

        rows.append({
            'id': id_int,
            'project_id': project_id_int,
            'title': title_val,
            'amount': amount_num,
            'type': type_val,
            'category': category_val,
            'date': date_val,
            'description': desc_val,
            'barangay': barangay_val,
        })
    return rows


def upsert_to_supabase(rows, apply=False):
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set in environment')
    client = create_client(url, key)
    # report summary
    print(f'Parsed {len(rows)} rows. Sample:')
    for r in rows[:3]:
        print(' ', r)

    if not apply:
        print('\nDry-run mode: nothing was written. Use --apply to perform upsert.')
        return None

    # Perform upsert in chunks to avoid large payloads
    CHUNK = 200
    results = []
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i+CHUNK]
        res = client.table('transactions').upsert(chunk).execute()
        results.append(res)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Path to raw INSERT SQL file')
    parser.add_argument('--apply', action='store_true', help='Actually perform upsert (default is dry-run)')
    args = parser.parse_args()

    rows = parse_insert_file(args.input)
    try:
        res = upsert_to_supabase(rows, apply=args.apply)
        if args.apply:
            print('\nUpsert completed. Check Supabase table for inserted rows.')
            if res:
                print('Supabase responses (first chunk):', res[0])
    except Exception as e:
        print('Error:', e)
        sys.exit(1)

if __name__ == '__main__':
    main()
