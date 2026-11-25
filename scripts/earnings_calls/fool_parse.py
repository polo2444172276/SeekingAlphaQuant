"""Parse a Motley Fool earnings-call transcript page into turns (same shape as zcyeee turns)."""
import re, html

def _txt(s):
    s = re.sub(r'<br\s*/?>', '\n', s)
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()

QA_RE = re.compile(r'(first question|question[s]? (today )?(comes|will come|is from)|open (up )?the (line|floor|call) for questions|begin (the )?(question|q&a)|question-and-answer|our first question|take (our|your) (first )?question)', re.I)

def parse(page):
    out = {}
    m = re.search(r'<h2 id="date"[^>]*>[^<]*</h2>\s*<p>(.*?)</p>', page)
    out['date_text'] = _txt(m.group(1)) if m else None
    parts = []
    m = re.search(r'<h2 id="call-participants"[^>]*>.*?</h2>(.*?)<h2', page, re.S)
    if m:
        for li in re.findall(r'<(?:li|p)>(.*?)</(?:li|p)>', m.group(1), re.S):
            t = _txt(li)
            if not t or '@' in t or 'Need a quote' in t:
                continue
            sp = re.split(r'\s+[-\u2014\u2013]\s+', t)
            if len(sp) >= 2:
                a, b = sp[0], sp[-1]
                # "Title — Name" (usual) or "Name — Title"
                if re.search(r'Officer|President|Chair|Director|Head|Vice|Investor|Treasurer|Counsel|CEO|CFO|COO|Founder|Manager|Executive|Relations', a):
                    title, name = a, b
                else:
                    name, title = a, b
            else:
                title, name = None, t
            parts.append({'name': name.strip(), 'title': title.strip() if title else None})
    out['participants'] = parts
    i = page.find('<h2 id="full-conference-call-transcript"')
    if i < 0:
        out['turns'] = []; return out
    body = page[i:]
    e = min([x for x in (body.find('<aside'), body.find('id="promobox_container"')) if x > 0] or [len(body)])
    body = body[:e]
    mgmt = {p['name'].lower() for p in parts}
    turns, cur = [], None
    for p in re.findall(r'<p>(.*?)</p>', body, re.S):
        m = re.match(r'\s*<strong>([^<]{1,80}?):\s*</strong>(.*)', p, re.S)
        if m:
            cur = {'speaker': _txt(m.group(1)), 'text': _txt(m.group(2))}
            turns.append(cur)
        elif cur is not None:
            cur['text'] += '\n' + _txt(p)
    def ln(n):
        w = re.sub(r'[^a-z ]', '', (n or '').lower()).split()
        return w[-1] if w else ''
    mgmt = {ln(p['name']) for p in parts}
    # where Q&A starts: first operator/management turn (after the opening) announcing questions
    qa_start = next((k for k, t in enumerate(turns) if k > 0 and t['speaker'].lower() == 'operator' and QA_RE.search(t['text'])), None)
    if qa_start is None:
        qa_start = next((k for k, t in enumerate(turns) if k > 0 and QA_RE.search(t['text'])), None)
    if not mgmt:
        end = qa_start if qa_start is not None else len(turns)
        mgmt = {ln(t['speaker']) for t in turns[:end] if t['speaker'].lower() != 'operator'}
    for k, t in enumerate(turns):
        sp = t['speaker']; low = sp.lower()
        if low == 'operator':
            role = 'operator'
        elif ln(sp) in mgmt:
            role = 'management'
        elif 'unknown' in low or 'unidentified' in low:
            role = 'unknown'
        else:
            role = 'analyst'
        if qa_start is None:
            first_analyst = next((j for j, x in enumerate(turns) if ln(x['speaker']) not in mgmt and x['speaker'].lower() != 'operator'), len(turns))
            qa_start = first_analyst
        t.update(i=k, role=role, section='qa' if k >= qa_start else 'prepared',
                 title=next((p['title'] for p in parts if ln(p['name']) == ln(sp)), None))
    out['turns'] = turns
    return out
