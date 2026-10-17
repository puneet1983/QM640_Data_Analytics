"""CSV input, company identity normalization, and output checkpoints."""

import csv

FIELDS = ["NSE_SYMBOL", "COMPANY_NAME", "INDUSTRY", "SECTOR", "TAXONOMY",
          "STATUS", "REASON", "SOURCE_URLS", "CLASSIFIED_AT_UTC", "MODEL", "AGENT_VERSION"]


def company_key(row):
    return (row["NSE_SYMBOL"].strip().upper(), " ".join(row["COMPANY_NAME"].split()).casefold())


def read_companies(path):
    """Deduplicate repeated financial rows; retain different identities for review."""
    companies = {}
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"NSE_SYMBOL", "COMPANY_NAME"}.issubset(reader.fieldnames or []):
            raise ValueError("Input CSV requires NSE_SYMBOL and COMPANY_NAME columns")
        for row in reader:
            count += 1
            company = {"NSE_SYMBOL": row["NSE_SYMBOL"].strip().upper(),
                       "COMPANY_NAME": " ".join(row["COMPANY_NAME"].split())}
            companies.setdefault(company_key(company), company)
    return count, list(companies.values())


def save_results(path, rows):
    """Replace the checkpoint atomically after each company."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
