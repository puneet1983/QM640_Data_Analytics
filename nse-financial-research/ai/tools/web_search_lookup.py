"""Open-source metasearch plus extraction of literal labels from fetched pages."""

import re
from urllib.parse import urlparse

from ai.tools.company_lookup import CompanyLookup, LookupFailure


class WebSearchLookup(CompanyLookup):
    def __init__(self, config, session=None, search_client=None):
        super().__init__(config, session)
        self.web = config["web_search"]
        self.backend = config["backend"]
        self.search_client = search_client
        self.session.headers.pop("Referer", None)
        self.session.headers.update(self.web["headers"])

    def parse_page(self, html, url, search_title=""):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("sup, script, style, nav, footer"):
            node.decompose()
        fields = {}
        for row in soup.select("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) == 2:
                fields[self._label(cells[0].get_text(" ", strip=True))] = cells[1].get_text(" ", strip=True)
        for term in soup.select("dt"):
            definition = term.find_next_sibling("dd")
            if definition:
                fields[self._label(term.get_text(" ", strip=True))] = definition.get_text(" ", strip=True)
        # Additional per-site CSS extraction rules can be supplied in config.
        values = {}
        for name, labels in self.web["field_labels"].items():
            values[name] = next((fields[self._label(label)] for label in labels
                                 if fields.get(self._label(label))), "")
            for selector in self.web.get("value_selectors", {}).get(name, []):
                node = soup.select_one(selector)
                if not values[name] and node:
                    values[name] = node.get_text(" ", strip=True)
        heading = soup.select_one(self.web["company_name_selector"])
        name = heading.get_text(" ", strip=True) if heading else search_title
        contexts = " ".join(node.get_text(" ", strip=True)
                            for selector in self.web["symbol_context_selectors"]
                            for node in soup.select(selector))
        match = re.search(self.web["symbol_pattern"], contexts)
        symbol = match.group(1) if match else values.get("symbol", "")
        return {"symbol": symbol.strip(), "company_name": name,
                "industry": values.get("industry", ""), "sector": values.get("sector", ""),
                "taxonomy": self.web["taxonomy"], "source_url": url,
                # Generic web labels need human taxonomy review even when the LLM agrees.
                "identity_requires_review": True}

    @staticmethod
    def _label(text):
        return " ".join(text.split()).strip(" :").casefold()

    def search(self, company):
        from ddgs import DDGS
        query = self.web["query_template"].format(
            company_name=company["COMPANY_NAME"], symbol=company["NSE_SYMBOL"])
        try:
            client = self.search_client or DDGS(timeout=self.config["timeout_seconds"])
            hits = client.text(query, backend=self.backend, region=self.web["region"],
                               max_results=self.web["max_results"])
        except Exception as error:
            raise LookupFailure(f"Web search ({self.backend}): {type(error).__name__}") from error
        best = None
        fetched = set()
        for hit in list(hits)[:self.web["max_results"]]:
            url = hit.get("href") or hit.get("url") or ""
            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or url in fetched:
                continue
            fetched.add(url)
            try:
                response = self._get(url)
            except LookupFailure:
                continue
            if "html" not in response.headers.get("Content-Type", "").lower():
                continue
            candidate = self.parse_page(response.text, response.url or url, hit.get("title", ""))
            symbol = candidate["symbol"].upper()
            if symbol and symbol != company["NSE_SYMBOL"].upper():
                continue
            if candidate["company_name"] and (candidate["industry"] or candidate["sector"]):
                score = (bool(symbol), bool(candidate["industry"]) + bool(candidate["sector"]))
                if best is None or score > best[0]:
                    best = (score, candidate)
                if symbol and candidate["industry"] and candidate["sector"]:
                    break
        return best[1] if best else {"symbol": "", "company_name": "", "industry": "", "sector": "",
                                    "taxonomy": self.web["taxonomy"], "source_url": "",
                                    "identity_requires_review": True}
