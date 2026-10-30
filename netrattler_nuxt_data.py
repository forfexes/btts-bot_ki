"""Decode Nuxt/devalue data literals without executing website JavaScript.

Only a literal-returning IIFE, literal arguments, data assignments and sparse
Array(n) literals are accepted. Other calls/operators and computed keys fail closed.
"""
from dataclasses import dataclass
import json
import re

_TOKEN = re.compile(r'\s*("(?:[^"\\]|\\.)*"|-?(?:(?:0|[1-9]\d*)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z_$][\w$]*|[{}\[\]():,;.=])')
_IDENT = re.compile(r'[A-Za-z_$][\w$]*\Z')

@dataclass(frozen=True)
class Ref:
    name: str

class Decoder:
    def __init__(self, source):
        if len(source) > 8_000_000:
            raise ValueError('Nuxt payload too large')
        self.tokens = []
        pos = 0
        while pos < len(source):
            m = _TOKEN.match(source, pos)
            if not m:
                if not source[pos:].strip():
                    break
                raise ValueError('unsupported Nuxt syntax')
            self.tokens.append(m.group(1)); pos = m.end()
            if len(self.tokens) > 1_000_000:
                raise ValueError('too many Nuxt tokens')
        self.i = 0
    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None
    def take(self, expected=None):
        value = self.peek()
        if value is None or (expected is not None and value != expected):
            raise ValueError('expected '+str(expected)+' got '+str(value)+' near '+repr(self.tokens[max(0,self.i-4):self.i+5]))
        self.i += 1
        return value
    def value(self, depth=0):
        if depth > 100:
            raise ValueError('Nuxt nesting too deep')
        t = self.take()
        if t == '{':
            out = {}
            while self.peek() != '}':
                key = self.take()
                if key.startswith('"'):
                    key = json.loads(key)
                elif not (_IDENT.fullmatch(key) or key.isdigit()):
                    raise ValueError('invalid literal key')
                if key in {'__proto__', 'prototype', 'constructor'}:
                    raise ValueError('unsafe object key')
                self.take(':'); out[key] = self.value(depth+1)
                if self.peek() != ',': break
                self.take(',')
            self.take('}'); return out
        if t == '[':
            out = []
            while self.peek() != ']':
                out.append(self.value(depth+1))
                if self.peek() != ',': break
                self.take(',')
            self.take(']'); return out
        if t.startswith('"'): return json.loads(t)
        if t == 'Array' and self.peek() == '(':
            self.take('('); n = self.take(); self.take(')')
            if not n.isdigit() or int(n)>10000: raise ValueError('invalid sparse array')
            return [None]*int(n)
        if t == 'void':
            self.take('0'); return None
        if t in ('null', 'undefined'): return None
        if t == 'true': return True
        if t == 'false': return False
        if _IDENT.fullmatch(t): return Ref(t)
        try: return float(t) if t.startswith((".", "-.")) else json.loads(t)
        except (ValueError, TypeError): raise ValueError('unsupported literal: '+repr(t)+' near '+repr(self.tokens[max(0,self.i-5):self.i+5]))


def decode_nuxt(source):
    d = Decoder(source)
    for t in ('window', '.', '__NUXT__', '=', '(', 'function', '('): d.take(t)
    names = []
    while d.peek() != ')':
        name = d.take()
        if not _IDENT.fullmatch(name) or name in names: raise ValueError('invalid argument')
        names.append(name)
        if d.peek() != ',': break
        d.take(',')
    d.take(')'); d.take('{')
    assignments = []
    while d.peek() != 'return':
        root = d.take(); path = []
        if root not in names: raise ValueError('assignment outside data arguments')
        while d.peek() in {'.', '['}:
            bracket = d.take() == '['
            key = d.take()
            if bracket:
                if key.isdigit(): key = int(key)
                elif key.startswith(chr(34)): key = json.loads(key)
                else: raise ValueError('computed property unsupported')
                d.take(']')
            if isinstance(key,int):
                path.append(key); continue
            if not _IDENT.fullmatch(key) or key in {'__proto__','prototype','constructor'}: raise ValueError('unsafe property')
            path.append(key)
        d.take('='); assignments.append((root,path,d.value())); d.take(';')
    d.take('return'); result = d.value()
    if d.peek() == ';': d.take(';')
    d.take('}'); d.take('(')
    args = []
    while d.peek() != ')':
        args.append(d.value())
        if d.peek() != ',': break
        d.take(',')
    d.take(')'); d.take(')')
    if d.peek() == ';': d.take(';')
    if d.peek() is not None or len(args) != len(names): raise ValueError('invalid IIFE tail')
    env = dict(zip(names,args))
    def resolve(x, trail=None):
        trail = set() if trail is None else trail
        if isinstance(x,Ref):
            if x.name in trail or x.name not in env: raise ValueError('cyclic/unknown reference')
            return resolve(env[x.name],trail|{x.name})
        if isinstance(x,dict): return {k:resolve(v,trail) for k,v in x.items()}
        if isinstance(x,list): return [resolve(v,trail) for v in x]
        return x
    # Nuxt arguments that receive properties are mutable literal objects.
    for root,path,value in assignments:
        if not path:
            env[root] = value
            continue
        target = env[root]
        for key in path[:-1]:
            if not isinstance(target,dict) or key not in target: raise ValueError('invalid property path')
            target = target[key]
        if isinstance(target,list) and isinstance(path[-1],int) and 0 <= path[-1] <= len(target):
            if path[-1] == len(target): target.append(value)
            else: target[path[-1]] = value
        elif isinstance(target,dict): target[path[-1]] = value
        else: raise ValueError('property on non-object')
    return resolve(result)
