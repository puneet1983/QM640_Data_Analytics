"""Search Wikipedia and extract explicit infobox fields without an LLM."""

import re
from urllib.parse import quote, urlencode

from ai.tools.company_lookup import CompanyLookup, LookupFailure


class WikipediaLookup(CompanyLookup):
    def __init__(self, config, session=None):
        super().__init__(config, session)
        self.wiki = config["wikipedia"]
        self.session.headers.pop("Referer", None)
        self.session.headers.update(self.wiki["headers"])

    def parse_page(self, html, title, url):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("sup, script, style"):
            node.decompose()
        box = soup.select_one(self.wiki["infobox_selector"])
        fields = {}
        if box:
            for row in box.select("tr"):
                header, value = row.find("th"), row.find("td")
                if header and value:
                    label = " ".join(header.get_text(" ", strip=True).split()).casefold()
                    fields[label] = value.get_text(" ", strip=True)
        def read_field(name):
            for label in self.wiki["field_labels"][name]:
                if fields.get(label.casefold()):
                    return fields[label.casefold()]
            return ""
        traded_as = read_field("traded_as")
        match = re.search(self.wiki["symbol_pattern"], traded_as)
        symbol = match.group(1) if match else ""
        return {"symbol": symbol, "company_name": title,
                "industry": read_field("industry"), "sector": read_field("sector"),
                "taxonomy": self.wiki["taxonomy"], "source_url": url,
                "identity_requires_review": not bool(symbol)}

    def search(self, company):
        query = self.wiki["query_template"].format(
            company_name=company["COMPANY_NAME"], symbol=company["NSE_SYMBOL"])
        url = self.wiki["search_endpoint"] + "?" + urlencode({
            "q": query, "limit": self.wiki["search_limit"]})
        response = self._get(url)
        try:
            data = response.json()
        except ValueError as error:
            raise LookupFailure("Wikipedia search: non-JSON response") from error
        if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
            raise LookupFailure("Wikipedia search: unexpected response structure")
        fallback = None
        for page in data["pages"][:self.wiki["search_limit"]]:
            title = page.get("title", "")
            key = page.get("key") or title.replace(" ", "_")
            if not title:
                continue
            encoded = quote(key, safe="")
            html_url = self.wiki["html_endpoint"].format(title=encoded)
            source_url = self.wiki["page_url"].format(title=encoded)
            record = self.parse_page(self._get(html_url).text, title, source_url)
            if record["symbol"].upper() == company["NSE_SYMBOL"].upper():
                return record
            if not record["symbol"] and record["industry"] and fallback is None:
                fallback = record
        return fallback or {"symbol": "", "company_name": "", "industry": "", "sector": "",
                            "taxonomy": self.wiki["taxonomy"], "source_url": url,
                            "identity_requires_review": True}
