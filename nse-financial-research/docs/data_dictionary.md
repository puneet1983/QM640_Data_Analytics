# Data dictionary

NSE_SYMBOL: filing's NSE company symbol; not necessarily a stable legal entity ID.
PERIOD_START / PERIOD_END: financial context reporting dates.
STANDALONE_CONSOLIDATED: reporting basis; this study selects Standalone.
PAT: mapped total profit/loss for the period, not automatically owners-only profit.
TOTAL_INCOME: mapped total income; distinct from REVENUE.
PROFIT_BEFORE_TAX / TAX_EXPENSE: mapped financial context amounts.
EPS_BASIC: mapped basic earnings per share.
SOURCE_FILE / CONTEXT_ID: traceability to the original XML context.
STRICT_QUARTER_CANDIDATE: extraction screening flag, not an accuracy guarantee.

Numeric strings are retained to preserve source precision. Consult *_TAG,
*_UNIT, *_DECIMALS, REPORTING_CURRENCY, and the raw facts before conversion.
