#!/usr/bin/env python3
"""Карточки-коллекции: мини-сервер на стандартной библиотеке.

    python3 server.py [порт]   →  http://127.0.0.1:8000
"""
import json
import os
import re
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
COLL = os.path.join(ROOT, 'collections')


def parse(text):
    """md -> (name, created, cards). Карточка = строка, начинающаяся с '# '."""
    name = created = ''
    m = re.search(r'^---\s*\n(.*?)\n---', text, re.S)
    if m:
        for line in m.group(1).split('\n'):
            k, _, v = line.partition(':')
            if k.strip() == 'name':
                name = v.strip()
            elif k.strip() == 'created':
                created = v.strip()

    cards = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('# '):
            cards.append({'title': s[2:].strip(), 'answer': '', 'remembered': False})
        elif not cards:
            continue
        elif 'Ответ:' in s:
            # shortcut: ответ не должен содержать ']', иначе обрежется
            a = s.split('Ответ:', 1)[1].strip().lstrip('*').strip()
            if a.startswith(']'):
                a = a[1:].strip()
            if a.startswith('['):
                a = a[1:]
            if a.endswith(']'):
                a = a[:-1]
            cards[-1]['answer'] = a.strip()
        elif 'Статус:' in s:
            cards[-1]['remembered'] = 'не запомнил' not in s.lower()
    return name, created, cards


def set_status(text, i, remembered):
    """Меняет строку статуса i-й карточки, не трогая остальной файл."""
    lines = text.split('\n')
    heads = [n for n, l in enumerate(lines) if l.strip().startswith('# ')]
    if not 0 <= i < len(heads):
        return text
    end = heads[i + 1] if i + 1 < len(heads) else len(lines)
    value = f"[**Статус:** {'Запомнил' if remembered else 'Не запомнил'}]"

    for n in range(heads[i] + 1, end):
        if 'Статус:' in lines[n]:
            lines[n] = value
            return '\n'.join(lines)

    at = heads[i] + 1
    for n in range(heads[i] + 1, end):
        if 'Ответ:' in lines[n]:
            at = n + 1
    lines.insert(at, value)
    return '\n'.join(lines)


def path_of(name):
    """Имя файла -> путь, либо None если имя подозрительное."""
    if not re.fullmatch(r'[\w\-. ]+\.md', name) or os.path.basename(name) != name:
        return None
    return os.path.join(COLL, name)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def fail(self, code, msg):
        self.json({'error': msg}, code)

    def body(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        return json.loads(raw or b'{}')

    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/api/collections':
            out = []
            for f in sorted(os.listdir(COLL)):
                if not f.endswith('.md'):
                    continue
                text = open(os.path.join(COLL, f), encoding='utf-8').read()
                name, created, cards = parse(text)
                out.append({'file': f, 'name': name or f[:-3], 'created': created,
                            'total': len(cards),
                            'remembered': sum(c['remembered'] for c in cards)})
            return self.json(out)

        if p.startswith('/api/collections/'):
            fp = path_of(unquote(p[len('/api/collections/'):]))
            if not fp or not os.path.exists(fp):
                return self.fail(404, 'not found')
            text = open(fp, encoding='utf-8').read()
            name, created, cards = parse(text)
            return self.json({'file': os.path.basename(fp), 'name': name or 'без имени',
                              'created': created, 'cards': cards, 'raw': text})

        return super().do_GET()

    def do_POST(self):
        p = unquote(urlparse(self.path).path)
        m = re.fullmatch(r'/api/collections/(.+)/status', p)
        if not m:
            return self.fail(404, 'not found')
        fp = path_of(m.group(1))
        if not fp or not os.path.exists(fp):
            return self.fail(404, 'not found')

        data = self.body()
        text = open(fp, encoding='utf-8').read()
        text = set_status(text, int(data['index']), bool(data['remembered']))
        open(fp, 'w', encoding='utf-8').write(text)
        return self.json({'remembered': bool(data['remembered'])})

    def do_PUT(self):
        p = unquote(urlparse(self.path).path)
        m = re.fullmatch(r'/api/collections/(.+)', p)
        if not m:
            return self.fail(404, 'not found')
        fp = path_of(m.group(1))
        if not fp or not os.path.exists(fp):
            return self.fail(404, 'not found')

        open(fp, 'w', encoding='utf-8').write(self.body()['raw'])
        return self.json({'ok': True})


if __name__ == '__main__':
    os.makedirs(COLL, exist_ok=True)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    url = f'http://127.0.0.1:{port}/'

    server = HTTPServer(('127.0.0.1', port), Handler)

    threading.Thread(
        target=lambda: (time.sleep(1), webbrowser.open(url)),
        daemon=True
    ).start()

    print(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
