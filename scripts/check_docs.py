"""Check repository Markdown paths and heading anchors without network access."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def headings(text):
    counts, result = {}, set()
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', text, re.M):
        heading = re.sub(r'[^\w\- ]', '', heading.replace('`', '').lower()).replace(' ', '-')
        count = counts.get(heading, 0)
        counts[heading] = count+1
        result.add(heading+('-'+str(count) if count else ''))
    return result


def documents(root=ROOT):
    # Tracked documentation locations only: never enumerate uploads, dependency
    # caches, worktrees or generated reports.
    yield from root.glob('*.md')
    for folder in ('docs', '.github'):
        yield from (root/folder).rglob('*.md')


def broken_links(root=ROOT):
    root = root.resolve()
    for path in documents(root):
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'^```.*?^```\s*$', '', text, flags=re.M | re.S)
        for target in re.findall(r'\[[^\]]*\]\(<?([^\s)>]+)>?(?:\s+"[^"]*")?\)', text):
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            resolved = (path.parent/unquote(url.path)).resolve() if url.path else path.resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                yield f'{path.relative_to(root)}: missing path {target}'
            elif url.fragment and resolved.suffix == '.md' and unquote(url.fragment) not in headings(resolved.read_text(encoding='utf-8')):
                yield f'{path.relative_to(root)}: missing heading {target}'


if __name__ == '__main__':
    errors = list(broken_links())
    print('\n'.join(errors) if errors else 'All internal Markdown links are valid.')
    raise SystemExit(bool(errors))
