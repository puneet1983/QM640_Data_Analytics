"""Try independent lookup tools and choose one record without merging evidence."""

from ai.tools.company_lookup import LookupFailure


class FallbackLookup:
    def __init__(self, tools):
        self.tools = tools

    def search(self, company):
        best = None
        failures = []
        succeeded = False
        for name, tool in self.tools:
            try:
                candidate = tool.search(company)
                succeeded = True
            except LookupFailure as error:
                failures.append(str(error))
                continue
            symbol = candidate.get("symbol", "").upper()
            if symbol and symbol != company["NSE_SYMBOL"].upper():
                continue
            if not candidate.get("company_name") or not (candidate.get("industry") or candidate.get("sector")):
                continue
            score = (bool(symbol), bool(candidate.get("industry")) + bool(candidate.get("sector")))
            if best is None or score > best[0]:
                best = (score, candidate)
            if symbol and candidate.get("industry") and candidate.get("sector"):
                break
        if best:
            return best[1]
        if not succeeded:
            raise LookupFailure("All lookup tools failed: " + "; ".join(failures))
        return {"symbol": "", "company_name": "", "industry": "", "sector": "",
                "taxonomy": "", "source_url": "", "identity_requires_review": True}
