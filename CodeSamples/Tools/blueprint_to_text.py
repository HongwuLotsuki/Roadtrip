import re, sys, os

PIN_RE = re.compile(r'CustomProperties Pin \((.*)\)\s*$')


def unq(s):
    return s.replace('\\"', '"').replace('\\n', '\n')


def get_str(attrs, key):
    m = re.search(r'(?:^|,)' + re.escape(key) + r'="((?:[^"\\]|\\.)*)"', attrs)
    return unq(m.group(1)) if m else None


def short(path):
    if not path:
        return ''
    m = re.search(r"[.'/]([A-Za-z0-9_]+)'?\"?$", path)
    return m.group(1) if m else path


def parse_pin(attrs):
    p = {}
    p['id'] = re.search(r'PinId=([0-9A-F]+)', attrs).group(1)
    p['name'] = get_str(attrs, 'PinName') or ''
    p['out'] = 'Direction="EGPD_Output"' in attrs
    m = re.search(r'PinType\.PinCategory="([^"]*)"', attrs)
    p['cat'] = m.group(1) if m else ''
    p['hidden'] = 'bHidden=True' in attrs
    p['default'] = get_str(attrs, 'DefaultValue')
    m = re.search(r'DefaultObject="?([^",)]*)"?', attrs)
    p['defobj'] = m.group(1) if m and m.group(1) not in ('None', '') else None
    m = re.search(r'DefaultTextValue=(?:NSLOCTEXT\("[^"]*", "[^"]*", "((?:[^"\\]|\\.)*)"\)|INVTEXT\("((?:[^"\\]|\\.)*)"\))', attrs)
    p['text'] = unq(m.group(1) or m.group(2) or '') if m else None
    p['links'] = []
    m = re.search(r'LinkedTo=\(([^)]*)\)', attrs)
    if m:
        for part in m.group(1).split(','):
            a = part.strip().split(' ')
            if len(a) == 2:
                p['links'].append((a[0], a[1]))
    return p


def parse_file(text):
    graphs = {}
    cur = None
    node = None
    for line in text.split('\n'):
        s = line.strip()
        m = re.match(r'Begin Object Class=/Script/Engine\.EdGraph Name="([^"]+)"', s)
        if m:
            cur = m.group(1)
            graphs.setdefault(cur, {'nodes': {}})
            continue
        m = re.match(r'Begin Object Name="([^"]+)" ExportPath="([^"]*)"', s)
        if m:
            ep = m.group(2)
            mm = re.search(r"'/Game/[^:]+:([^.']+)\.([^']+)'", ep)
            if mm and mm.group(1) in graphs:
                node = {'name': mm.group(2), 'class': short(ep.split("'")[0]), 'props': {}, 'pins': []}
                graphs[mm.group(1)]['nodes'][node['name']] = node
            else:
                node = None
            continue
        if node is not None:
            pm = PIN_RE.match(s)
            if pm:
                node['pins'].append(parse_pin(pm.group(1)))
            elif '=' in s and not s.startswith('CustomProperties') and not s.startswith('Begin') and not s.startswith('End'):
                k, v = s.split('=', 1)
                node['props'][k] = v
    return graphs


OPS = {'Add': '+', 'Subtract': '-', 'Multiply': '*', 'Divide': '/', 'Less': '<', 'Greater': '>',
       'LessEqual': '<=', 'GreaterEqual': '>=', 'EqualEqual': '==', 'NotEqual': '!=',
       'BooleanAND': 'and', 'BooleanOR': 'or'}


def member(node, prop):
    m = re.search(r'MemberName="([^"]+)"', node['props'].get(prop, ''))
    return m.group(1) if m else None


def fname(n):
    return member(n, 'FunctionReference') or n['class']


def varname(n):
    return member(n, 'VariableReference') or '?'


def nice(n):
    return re.sub(r'^K2_', '', n)


def is_exec(p):
    return p['cat'] == 'exec'


def label(n):
    c = n['class']
    if c == 'K2Node_CallFunction':
        return nice(fname(n))
    if c == 'K2Node_DynamicCast':
        return 'CastTo' + short(n['props'].get('TargetType', ''))
    return c.replace('K2Node_', '') + '_' + n['name'].split('_')[-1]


class R:
    def __init__(self, g):
        self.nodes = g['nodes']
        self.lines = []
        self.visited = set()
        self.pinmap = {}
        for n in self.nodes.values():
            for p in n['pins']:
                self.pinmap[(n['name'], p['id'])] = (n, p)

    def lit(self, p):
        if p.get('text') is not None:
            return '"' + p['text'] + '"'
        if p['defobj']:
            return short(p['defobj'])
        d = p['default']
        if d is None or d == '':
            if p['cat'] in ('string', 'text', 'name'):
                return '""'
            return None
        if p['cat'] in ('string', 'text', 'name'):
            return '"' + d + '"'
        return d

    def expr(self, pin, depth=0):
        if pin['links']:
            nn, pid = pin['links'][0]
            r = self.pinmap.get((nn, pid))
            if r:
                return self.out_expr(r[0], r[1], depth + 1)
        v = self.lit(pin)
        if v is None:
            if pin['name'] in ('self', 'Target', 'Object'):
                return 'self'
            return 'false' if pin['cat'] == 'bool' else '<unset>'
        return v

    def has_exec(self, n):
        return any(is_exec(p) for p in n['pins'])

    def args(self, n):
        out = []
        for p in n['pins']:
            if p['out'] or is_exec(p) or p['name'] in ('self', 'WorldContextObject', 'ReturnValue'):
                continue
            if p['hidden'] and not p['links']:
                continue
            out.append(f"{p['name']}={self.expr(p)}")
        return out

    def target_prefix(self, n):
        t = [p for p in n['pins'] if p['name'] == 'self' and p['links']]
        return (self.expr(t[0]) + '.') if t else ''

    def out_expr(self, n, p, depth):
        if depth > 12:
            return '...'
        c = n['class']
        if c == 'K2Node_VariableGet':
            return self.target_prefix(n) + varname(n)
        if c in ('K2Node_PromotableOperator', 'K2Node_CommutativeAssociativeBinaryOperator', 'K2Node_CallFunction') and not self.has_exec(n):
            fn = fname(n)
            base = fn.split('_')[0]
            ins = [q for q in n['pins'] if not q['out'] and q['name'] not in ('self', 'WorldContextObject')]
            if base in OPS and len(ins) >= 2:
                if base in ('Less', 'Greater', 'LessEqual', 'GreaterEqual', 'EqualEqual', 'NotEqual'):
                    ins = ins[:2]
                return '(' + f' {OPS[base]} '.join(self.expr(q, depth) for q in ins) + ')'
            if fn == 'Not_PreBool' and ins:
                return 'not ' + self.expr(ins[0], depth)
            if fn.startswith('MakeLiteral') and ins:
                return self.expr(ins[0], depth)
            a = [self.expr(q, depth) for q in ins]
            outs = [q for q in n['pins'] if q['out']]
            sfx = ''
            if len(outs) > 1 and p['name'] != 'ReturnValue':
                sfx = '.' + p['name']
            return f"{self.target_prefix(n)}{nice(fn)}({', '.join(a)}){sfx}"
        if c == 'K2Node_DynamicCast':
            obj = [q for q in n['pins'] if q['name'] == 'Object']
            return f"CastTo{short(n['props'].get('TargetType', ''))}({self.expr(obj[0], depth) if obj else '?'})"
        if c == 'K2Node_Self':
            return 'self'
        if c in ('K2Node_MakeStruct', 'K2Node_MakeArray', 'K2Node_MakeLiteral'):
            ins = [q for q in n['pins'] if not q['out']]
            return '{' + ', '.join(f"{q['name']}={self.expr(q, depth)}" for q in ins) + '}'
        if c == 'K2Node_BreakStruct':
            ins = [q for q in n['pins'] if not q['out']]
            return f"{self.expr(ins[0], depth)}.{p['name']}" if ins else p['name']
        if c == 'K2Node_GetArrayItem':
            ins = [q for q in n['pins'] if not q['out']]
            if len(ins) >= 2:
                return f"{self.expr(ins[0], depth)}[{self.expr(ins[1], depth)}]"
        if c in ('K2Node_FunctionEntry', 'K2Node_Event', 'K2Node_CustomEvent', 'K2Node_ComponentBoundEvent', 'K2Node_InputKeyEvent'):
            return p['name']
        return f"{label(n)}.{p['name']}"


ENTRY = ('K2Node_Event', 'K2Node_CustomEvent', 'K2Node_FunctionEntry', 'K2Node_ComponentBoundEvent', 'K2Node_InputKeyEvent')


def entry_title(n, gname):
    c = n['class']
    if c == 'K2Node_Event':
        return 'Event ' + (member(n, 'EventReference') or '?')
    if c == 'K2Node_CustomEvent':
        return 'Custom Event ' + n['props'].get('CustomFunctionName', '?').strip('"')
    if c == 'K2Node_FunctionEntry':
        return 'Function ' + gname
    if c == 'K2Node_ComponentBoundEvent':
        return 'Event ' + n['props'].get('DelegatePropertyName', '?').strip('"') + ' (' + n['props'].get('ComponentPropertyName', '?').strip('"') + ')'
    if c == 'K2Node_InputKeyEvent':
        m = re.search(r'KeyName="?([^",)]*)', n['props'].get('InputKey', ''))
        return 'Input Key ' + (m.group(1) if m else '?')
    return c


def succ(r, n):
    out = []
    for p in n['pins']:
        if p['out'] and is_exec(p):
            for nn, _ in p['links']:
                if nn in r.nodes:
                    out.append(nn)
    return out


def reach(r, pin):
    seen = []
    stack = [l[0] for l in pin['links'] if l[0] in r.nodes][::-1]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.append(n)
        stack.extend(succ(r, r.nodes[n])[::-1])
    return seen


def walk(r, pin, ind, stop=None):
    pad = '    ' * ind
    if not pin['links']:
        return
    cur = r.nodes.get(pin['links'][0][0])
    guard = 0
    while cur is not None and guard < 300:
        guard += 1
        if stop is not None and cur['name'] == stop:
            return
        if cur['name'] in r.visited:
            r.lines.append(f"{pad}-> continues at {label(cur)}")
            return
        r.visited.add(cur['name'])
        c = cur['class']
        execout = [p for p in cur['pins'] if p['out'] and is_exec(p)]
        nxt = None
        if c == 'K2Node_IfThenElse':
            cond = [p for p in cur['pins'] if p['name'] == 'Condition']
            r.lines.append(f"{pad}if {r.expr(cond[0]) if cond else '?'}:")
            t = [p for p in execout if p['name'] == 'then']
            f = [p for p in execout if p['name'] == 'else']
            join = None
            if t and f and t[0]['links'] and f[0]['links']:
                fr = set(reach(r, f[0]))
                for x in reach(r, t[0]):
                    if x in fr:
                        join = x
                        break
            if t and t[0]['links']:
                walk(r, t[0], ind + 1, join)
            else:
                r.lines.append(pad + '    pass')
            if f and f[0]['links']:
                mark = len(r.lines)
                r.lines.append(f"{pad}else:")
                walk(r, f[0], ind + 1, join)
                if len(r.lines) == mark + 1:
                    r.lines.pop()
            if join and join not in r.visited:
                cur = r.nodes[join]
                continue
            return
        if c == 'K2Node_ExecutionSequence':
            for i, p in enumerate(execout):
                if p['links']:
                    r.lines.append(f"{pad}sequence {i}:")
                    walk(r, p, ind + 1)
            return
        if c.startswith('K2Node_Switch'):
            sel = [p for p in cur['pins'] if p['name'] == 'Selection']
            r.lines.append(f"{pad}switch {r.expr(sel[0]) if sel else '?'}:")
            for p in execout:
                if p['links']:
                    r.lines.append(f"{pad}    case {p['name']}:")
                    walk(r, p, ind + 2)
            return
        if c == 'K2Node_MacroInstance':
            mg = cur['props'].get('MacroGraphReference', '')
            m = re.search(r'MacroGraph="[^"]*:([^."\']+)', mg) or re.search(r"MacroGraph=\"[^\"]*[.:/]([A-Za-z0-9_ ]+)'?\"", mg)
            mname = m.group(1) if m else 'Macro'
            ins = [p for p in cur['pins'] if not p['out'] and not is_exec(p)]
            r.lines.append(f"{pad}{mname}({', '.join(r.expr(p) for p in ins)}):")
            for p in execout:
                if p['links']:
                    r.lines.append(f"{pad}    on {p['name']}:")
                    walk(r, p, ind + 2)
            return
        if c == 'K2Node_DynamicCast':
            obj = [p for p in cur['pins'] if p['name'] == 'Object']
            r.lines.append(f"{pad}cast {r.expr(obj[0]) if obj else '?'} to {short(cur['props'].get('TargetType', ''))}:")
            for p in execout:
                if p['name'] == 'then' and p['links']:
                    walk(r, p, ind + 1)
            for p in execout:
                if p['name'] == 'CastFailed' and p['links']:
                    r.lines.append(f"{pad}else (cast failed):")
                    walk(r, p, ind + 1)
            return
        if c == 'K2Node_VariableSet':
            val = [p for p in cur['pins'] if not p['out'] and not is_exec(p) and p['name'] == varname(cur)]
            r.lines.append(f"{pad}{r.target_prefix(cur)}{varname(cur)} = {r.expr(val[0]) if val else '?'}")
            nxt = [p for p in execout if p['name'] == 'then']
        elif c in ('K2Node_CallFunction', 'K2Node_CallFunctionOnMember', 'K2Node_AddDelegate', 'K2Node_CallDelegate'):
            r.lines.append(f"{pad}{r.target_prefix(cur)}{nice(fname(cur))}({', '.join(r.args(cur))})")
            nxt = [p for p in execout if p['name'] == 'then']
        elif c == 'K2Node_FunctionResult':
            ins = [p for p in cur['pins'] if not p['out'] and not is_exec(p)]
            r.lines.append(f"{pad}return ({', '.join(p['name'] + '=' + r.expr(p) for p in ins)})")
            return
        elif c == 'K2Node_Knot':
            nxt = execout
        else:
            ins = [p for p in cur['pins'] if not p['out'] and not is_exec(p) and not (p['hidden'] and not p['links'])]
            r.lines.append(f"{pad}{c.replace('K2Node_', '')}({', '.join(p['name'] + '=' + r.expr(p) for p in ins)})")
            if len(execout) > 1:
                for p in execout:
                    if p['links']:
                        r.lines.append(f"{pad}    on {p['name']}:")
                        walk(r, p, ind + 2)
                return
            nxt = execout
        if nxt and nxt[0]['links']:
            cur = r.nodes.get(nxt[0]['links'][0][0])
        else:
            return


def render_graph(g, gname):
    r = R(g)
    out = []
    for e in [n for n in g['nodes'].values() if n['class'] in ENTRY]:
        outs = [p for p in e['pins'] if p['out'] and not is_exec(p) and p['cat'] != 'delegate']
        sig = ', '.join(p['name'] for p in outs)
        hdr = entry_title(e, gname) + (f"({sig})" if e['class'] == 'K2Node_FunctionEntry' else (f" ({sig})" if sig else ''))
        r.visited = set()
        r.lines = []
        for p in [p for p in e['pins'] if p['out'] and is_exec(p)]:
            walk(r, p, 1)
        if r.lines:
            out.append(hdr)
            out.extend(r.lines)
            out.append('')
    return out


def render_bp(path):
    graphs = parse_file(open(path, encoding='utf-8').read())
    name = os.path.basename(path)[:-4]
    out = [f"// {name}", "// Generated from the Unreal Engine Blueprint graphs as readable pseudo-code.", ""]
    for gname, g in graphs.items():
        if gname.endswith('_MERGED') or gname.startswith('ExecuteUbergraph') or gname.startswith('BndEvt__') or gname == 'UserConstructionScript':
            continue
        lines = render_graph(g, gname)
        if lines and not any('ExecuteUbergraph' in l for l in lines):
            out.append(f"## Graph: {gname}")
            out.append('')
            out.extend(lines)
    return '\n'.join(out)


if __name__ == '__main__':
    os.makedirs(sys.argv[1], exist_ok=True)
    for f in sys.argv[2:]:
        s = render_bp(f)
        open(os.path.join(sys.argv[1], os.path.basename(f)[:-4] + '.txt'), 'w', encoding='utf-8', newline='\n').write(s)
        print(f, len(s.split('\n')), 'lines')
