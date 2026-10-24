"""Put the QTimeZone API that needs Qt's `timezone` feature (off in Qt for
WebAssembly) behind a PyQt_TimeZone sip feature."""
import re
import sys

p = sys.argv[1]
s = open(p).read()
head, body = s.split('public:\n', 1)
cls, tail = body.split('\n};\n', 1)
keep_patterns = [r'QTimeZone\(QTimeZone::Initialization spec\)', r'QTimeZone\(const QTimeZone &other\)', r'^\s*QTimeZone\(\);',
    r'~QTimeZone\(\)', r'void swap', r'operator[=!]=', r'bool isValid\(\)', r'enum Initialization',
    r'fromSecondsAheadOfUtc', r'timeSpec\(\)', r'fixedSecondsAheadOfUtc', r'isUtcOrFixedOffset', r'M(in|ax)UtcOffsetSecs']
lines = cls.split('\n')
units = []
i = 0
while i < len(lines):
    st = lines[i].strip()
    if st.startswith('%If'):
        buf = [lines[i]]; i += 1; depth = 1
        while depth:
            t = lines[i].strip()
            if t.startswith('%If'): depth += 1
            if t == '%End': depth -= 1
            buf.append(lines[i]); i += 1
        units.append(buf)
    elif st == '':
        units.append([lines[i]]); i += 1
    else:
        buf = [lines[i]]; i += 1
        while True:
            text = '\n'.join(buf)
            if text.count('{') == text.count('}') and buf[-1].strip().endswith(';'):
                break
            buf.append(lines[i]); i += 1
        units.append(buf)
res = []
for u in units:
    text = '\n'.join(u)
    if not text.strip() or any(re.search(k, text, re.M) for k in keep_patterns):
        res.append(text)
    else:
        res.append('%If (PyQt_TimeZone)\n' + text + '\n%End')
open(p, 'w').write(head + 'public:\n' + '\n'.join(res) + '\n};\n' + tail)
