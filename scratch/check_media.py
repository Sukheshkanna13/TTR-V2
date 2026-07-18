import re

with open('static/css/style.css') as f:
    text = f.read()

lines = text.split('\n')
stack = []
for i, line in enumerate(lines):
    if '{' in line:
        if '@media' in line:
            stack.append(('media', i+1))
        else:
            stack.append(('rule', i+1))
    if '}' in line:
        if stack:
            typ, start = stack.pop()
            if typ == 'media':
                print(f"Media query from {start} to {i+1}")

