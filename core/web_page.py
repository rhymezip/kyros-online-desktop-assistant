"""Read web pages in a separate cancellable process without a visible browser."""

from html.parser import HTMLParser
import json
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.text.append(data.strip())


def fetch(url):
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are supported")
    request = Request(
        url,
        headers={
            "User-Agent": "Kyros/2.0 (personal assistant)",
            "Accept": "text/html,text/plain,application/json",
        },
    )
    with urlopen(request, timeout=20) as response:
        if urlparse(response.url).scheme not in ("http", "https"):
            raise ValueError("Unsupported redirect")
        content_type = response.headers.get_content_type()
        raw = response.read(2_000_001)
        text = raw[:2_000_000].decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )
        links = []
        if content_type == "text/html":
            parser = PageParser()
            parser.feed(text)
            text = "\n".join(parser.text)
            links = list(
                dict.fromkeys(urljoin(response.url, link) for link in parser.links)
            )[:100]
        elif not (
            content_type.startswith("text/") or content_type == "application/json"
        ):
            return {
                "ok": False,
                "error": "Non-text document; download and read with system tools",
                "content_type": content_type,
            }
        return {
            "ok": True,
            "url": response.url,
            "text": text[:24000],
            "links": links,
            "truncated": len(raw) > 2_000_000 or len(text) > 24000,
        }


if __name__ == "__main__":
    try:
        result = fetch(json.load(sys.stdin)["url"])
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
