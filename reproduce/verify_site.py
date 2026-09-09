"""公開前の機械検証。標準ライブラリのみで実行できる。"""
from __future__ import annotations

import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "index.html", ROOT / "method.html", ROOT / "out-of-sample.html", ROOT / "revision.html", ROOT / "facts.html", ROOT / "limits.html", ROOT / "en" / "index.html"]
EXPECTED = PAGES + [
    ROOT / "assets" / "site.css", ROOT / "assets" / "minute-ranges.png",
    ROOT / "assets" / "surprise-distribution.png", ROOT / "assets" / "oos-comparison.png",
    ROOT / "llms.txt", ROOT / ".well-known" / "llms.txt", ROOT / "robots.txt",
    ROOT / "sitemap.xml", ROOT / "feed.xml", ROOT / ".nojekyll",
]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.json_scripts: list[str] = []
        self._json_parts: list[str] | None = None
        self.h1_count = 0
        self.images: list[dict[str, str | None]] = []
        self.canonical = 0
        self.canonical_hrefs: list[str] = []
        self.hreflangs: set[str] = set()
        self.alternates: dict[str, str] = {}
        self.references: list[str] = []
        self.external_loads: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "h1": self.h1_count += 1
        elif tag == "script" and attr.get("type") == "application/ld+json": self._json_parts = []
        elif tag == "img":
            self.images.append(attr)
        elif tag == "a" and attr.get("href"):
            self.references.append(str(attr["href"]))
        elif tag == "link" and attr.get("rel") == "canonical":
            self.canonical += 1
            if attr.get("href"): self.canonical_hrefs.append(str(attr["href"]))
        elif tag == "link" and attr.get("rel") == "alternate" and attr.get("hreflang"):
            language = str(attr["hreflang"])
            self.hreflangs.add(language)
            if attr.get("href"): self.alternates[language] = str(attr["href"])
        if tag == "script" and str(attr.get("src", "")).startswith(("http://", "https://")):
            self.external_loads.append(str(attr["src"]))
        resource_attributes = {"img": "src", "iframe": "src", "video": "src", "audio": "src", "source": "src", "object": "data", "embed": "src", "script": "src"}
        if tag in resource_attributes and attr.get(resource_attributes[tag]):
            resource = str(attr[resource_attributes[tag]])
            if resource.startswith(("http://", "https://")): self.external_loads.append(resource)
            elif not resource.startswith("data:"): self.references.append(resource)
        if tag == "link" and attr.get("rel") in {"stylesheet", "preload", "modulepreload", "icon", "manifest", "prefetch", "preconnect", "dns-prefetch"}:
            href = str(attr.get("href", ""))
            if href.startswith(("http://", "https://")): self.external_loads.append(href)
            elif href: self.references.append(href)

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None: self._json_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_parts is not None:
            self.json_scripts.append("".join(self._json_parts))
            self._json_parts = None


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition: errors.append(message)


def main() -> int:
    errors: list[str] = []
    for path in EXPECTED: require(path.exists(), f"missing: {path.relative_to(ROOT)}", errors)
    forbidden = [p for p in ROOT.rglob("*") if p.suffix.lower() in {".csv", ".zip", ".pdf"}]
    require(not forbidden, f"forbidden extensions: {forbidden}", errors)
    banned_terms = ("勝" + "てる", "有" + "利", "お" + "すすめ")
    canonical_by_page = {
        ROOT / "index.html": "https://naporit0742.github.io/nfp-event-study/",
        ROOT / "out-of-sample.html": "https://naporit0742.github.io/nfp-event-study/out-of-sample.html",
        ROOT / "revision.html": "https://naporit0742.github.io/nfp-event-study/revision.html",
        ROOT / "method.html": "https://naporit0742.github.io/nfp-event-study/method.html",
        ROOT / "facts.html": "https://naporit0742.github.io/nfp-event-study/facts.html",
        ROOT / "limits.html": "https://naporit0742.github.io/nfp-event-study/limits.html",
        ROOT / "en" / "index.html": "https://naporit0742.github.io/nfp-event-study/en/",
    }
    alternate_by_page = {
        ROOT / "index.html": {"ja": canonical_by_page[ROOT / "index.html"], "en": canonical_by_page[ROOT / "en" / "index.html"]},
        ROOT / "out-of-sample.html": {"ja": canonical_by_page[ROOT / "out-of-sample.html"], "en": canonical_by_page[ROOT / "en" / "index.html"] + "#out-of-sample"},
        ROOT / "revision.html": {"ja": canonical_by_page[ROOT / "revision.html"], "en": canonical_by_page[ROOT / "en" / "index.html"]},
        ROOT / "method.html": {"ja": canonical_by_page[ROOT / "method.html"], "en": canonical_by_page[ROOT / "en" / "index.html"] + "#method"},
        ROOT / "facts.html": {"ja": canonical_by_page[ROOT / "facts.html"], "en": canonical_by_page[ROOT / "en" / "index.html"] + "#facts"},
        ROOT / "limits.html": {"ja": canonical_by_page[ROOT / "limits.html"], "en": canonical_by_page[ROOT / "en" / "index.html"] + "#limits"},
        ROOT / "en" / "index.html": {"ja": canonical_by_page[ROOT / "index.html"], "en": canonical_by_page[ROOT / "en" / "index.html"]},
    }
    numeric_evidence = {
        ROOT / "index.html": ("計159回", "+1.135R", "+0.139R", "88%減", "+0.537R", "+0.290R", "46%減"),
        ROOT / "out-of-sample.html": ("2013〜2019年（83回）", "+1.135R", "+0.139R", "88%減", "+0.537R", "+0.290R", "46%減", "−0.040R"),
        ROOT / "revision.html": ("+4.568ドル", "+18.681pips", "−0.893ドル", "+0.505ドル", "+3.381ドル", "+0.251", "+2.798ドル", "+12.580pips"),
        ROOT / "facts.html": ("34.0 pips", "9.85ドル", "12.1 pips", "4.18ドル", "相関 +0.50", "40回（78%）"),
    }
    for page in PAGES:
        if not page.exists(): continue
        text = page.read_text(encoding="utf-8")
        parser = PageParser(); parser.feed(text)
        require(parser.h1_count == 1, f"{page.name}: h1 count={parser.h1_count}", errors)
        require(bool(re.search(r"</h1>\s*<p class=[\"']definition[\"']>", text)), f"{page.name}: definition paragraph is not immediately after h1", errors)
        require(parser.canonical == 1, f"{page.name}: canonical count={parser.canonical}", errors)
        require({"ja", "en"}.issubset(parser.hreflangs), f"{page.name}: missing reciprocal hreflang", errors)
        require(parser.canonical_hrefs == [canonical_by_page[page]], f"{page.name}: canonical target mismatch", errors)
        for language, expected_url in alternate_by_page[page].items():
            require(parser.alternates.get(language) == expected_url, f"{page.name}: {language} alternate target mismatch", errors)
        require("過去データの統計分析" in text or "historical statistical analysis" in text, f"{page.name}: disclaimer missing", errors)
        require(bool(parser.json_scripts), f"{page.name}: JSON-LD missing", errors)
        nodes: list[dict] = []
        for block in parser.json_scripts:
            try:
                payload = json.loads(block)
                graph = payload.get("@graph", [payload]) if isinstance(payload, dict) else []
                nodes.extend(node for node in graph if isinstance(node, dict))
            except json.JSONDecodeError as exc: errors.append(f"{page.name}: invalid JSON-LD: {exc}")
        article = next((node for node in nodes if node.get("@type") == "ScholarlyArticle"), None)
        breadcrumb = next((node for node in nodes if node.get("@type") == "BreadcrumbList"), None)
        require(article is not None, f"{page.name}: ScholarlyArticle missing", errors)
        require(breadcrumb is not None, f"{page.name}: BreadcrumbList missing", errors)
        if article:
            require(isinstance(article.get("headline"), str) and bool(article["headline"].strip()), f"{page.name}: invalid headline", errors)
            require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(article.get("datePublished", "")))), f"{page.name}: invalid datePublished", errors)
            author = article.get("author")
            require(isinstance(author, dict) and author.get("@type") == "Person" and author.get("name") == "NaporiT", f"{page.name}: invalid author", errors)
            require(article.get("inLanguage") in {"ja", "en"}, f"{page.name}: invalid inLanguage", errors)
            require(article.get("isAccessibleForFree") is True, f"{page.name}: isAccessibleForFree must be true", errors)
            require(article.get("mainEntityOfPage") == canonical_by_page[page], f"{page.name}: mainEntityOfPage mismatch", errors)
        if breadcrumb:
            items = breadcrumb.get("itemListElement")
            require(isinstance(items, list) and bool(items), f"{page.name}: invalid breadcrumbs", errors)
            if isinstance(items, list) and items:
                require(items[-1].get("item") == canonical_by_page[page], f"{page.name}: final breadcrumb target mismatch", errors)
        if page == ROOT / "index.html":
            faq = next((node for node in nodes if node.get("@type") == "FAQPage"), None)
            require(faq is not None, "index.html: FAQPage missing", errors)
            if faq:
                questions = faq.get("mainEntity")
                valid_questions = isinstance(questions, list) and len(questions) >= 4 and all(
                    isinstance(item, dict) and item.get("@type") == "Question" and bool(item.get("name"))
                    and isinstance(item.get("acceptedAnswer"), dict)
                    and item["acceptedAnswer"].get("@type") == "Answer"
                    and bool(item["acceptedAnswer"].get("text")) for item in questions
                )
                require(valid_questions, "index.html: invalid FAQPage questions", errors)
        for image in parser.images: require(bool(image.get("alt")), f"{page.name}: image without alt", errors)
        for term in banned_terms: require(term not in text, f"{page.name}: banned term {term}", errors)
        require(not parser.external_loads, f"{page.name}: external resource loads {parser.external_loads}", errors)
        require(not re.search(r"@import\s+(?:url\()?\s*[\"']?https?://", text, re.I), f"{page.name}: external CSS import", errors)
        require(not re.search(r"url\(\s*[\"']?https?://", text, re.I), f"{page.name}: external CSS URL", errors)
        for reference in parser.references:
            target = reference.split("#", 1)[0].split("?", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "tel:")): continue
            resolved = (page.parent / target).resolve()
            if target.endswith("/"): resolved = resolved / "index.html"
            require(resolved.is_file(), f"{page.name}: broken local reference {reference}", errors)
        for token in numeric_evidence.get(page, ()):
            require(token in text, f"{page.name}: expected REPORT value missing: {token}", errors)
    if (ROOT / "llms.txt").exists() and (ROOT / ".well-known" / "llms.txt").exists():
        require((ROOT / "llms.txt").read_bytes() == (ROOT / ".well-known" / "llms.txt").read_bytes(), "llms.txt copies differ", errors)
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8") if (ROOT / "robots.txt").exists() else ""
    for agent in ("GPTBot", "OAI-SearchBot", "PerplexityBot", "ClaudeBot", "Google-Extended", "CCBot"):
        require(bool(re.search(rf"User-agent:\s*{re.escape(agent)}\s*\nAllow:\s*/", robots)), f"robots.txt missing Allow for {agent}", errors)
    require("Sitemap:" in robots, "robots.txt missing Sitemap", errors)
    parsed_xml: dict[str, ET.ElementTree] = {}
    for name in ("sitemap.xml", "feed.xml"):
        try: ET.parse(ROOT / name)
        except (ET.ParseError, OSError) as exc: errors.append(f"{name}: invalid XML: {exc}")
        else: parsed_xml[name] = ET.parse(ROOT / name)
    expected_urls = set(canonical_by_page.values())
    if "sitemap.xml" in parsed_xml:
        actual = {node.text for node in parsed_xml["sitemap.xml"].getroot().findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        require(actual == expected_urls, f"sitemap.xml URL set mismatch: {expected_urls ^ actual}", errors)
    if "feed.xml" in parsed_xml:
        actual = {node.text for node in parsed_xml["feed.xml"].getroot().findall("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id")}
        require(actual == expected_urls, f"feed.xml entry set mismatch: {expected_urls ^ actual}", errors)
    raw_signatures = (
        ",".join(("release_date", "minute_offset", "open", "high", "low", "close")),
        ",".join(("nfp_forecast", "ur_forecast")),
    )
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".txt", ".py", ".xml", ".css"}:
            text = path.read_text(encoding="utf-8")
            for signature in raw_signatures: require(signature not in text, f"raw-data signature in {path.relative_to(ROOT)}", errors)
            if path.suffix.lower() == ".css":
                require(not re.search(r"@import\s+(?:url\()?\s*[\"']?https?://", text, re.I), f"external import in {path.relative_to(ROOT)}", errors)
                require(not re.search(r"url\(\s*[\"']?https?://", text, re.I), f"external URL in {path.relative_to(ROOT)}", errors)
    for image in (ROOT / "assets").glob("*.png"):
        try:
            content = image.read_bytes()
            require(content[:8] == b"\x89PNG\r\n\x1a\n", f"{image.name}: invalid PNG signature", errors)
            offset, chunks, idat = 8, [], bytearray()
            while offset + 12 <= len(content):
                length = struct.unpack(">I", content[offset:offset + 4])[0]
                kind = content[offset + 4:offset + 8]
                data = content[offset + 8:offset + 8 + length]
                crc = content[offset + 8 + length:offset + 12 + length]
                require(len(data) == length and len(crc) == 4, f"{image.name}: truncated PNG chunk", errors)
                if len(data) != length or len(crc) != 4: break
                require(struct.unpack(">I", crc)[0] == zlib.crc32(kind + data) & 0xFFFFFFFF, f"{image.name}: bad PNG CRC", errors)
                chunks.append((kind, data))
                if kind == b"IDAT": idat.extend(data)
                offset += 12 + length
                if kind == b"IEND": break
            require(chunks and chunks[0][0] == b"IHDR" and len(chunks[0][1]) == 13, f"{image.name}: invalid IHDR", errors)
            require(chunks and chunks[-1][0] == b"IEND" and offset == len(content), f"{image.name}: invalid IEND or trailing bytes", errors)
            width, height = struct.unpack(">II", chunks[0][1][:8]) if chunks and len(chunks[0][1]) >= 8 else (0, 0)
            require(width >= 1000 and height >= 600, f"{image.name}: unexpectedly small {width}x{height}", errors)
            zlib.decompress(bytes(idat))
        except (OSError, struct.error, zlib.error) as exc:
            errors.append(f"{image.name}: unreadable PNG: {exc}")
    if errors:
        print("FAIL")
        for error in errors: print(f"- {error}")
        return 1
    print(f"PASS: {len(PAGES)} pages, {len(EXPECTED)} required artifacts, 0 validation errors")
    return 0


if __name__ == "__main__": sys.exit(main())
