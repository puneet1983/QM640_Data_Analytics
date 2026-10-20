"""Conservative NSE XBRL instance extraction; embedded into the Colab notebook."""
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

XBRLI = 'http://www.xbrl.org/2003/instance'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
XLINK = 'http://www.w3.org/1999/xlink'
KNOWN_FORMATS = {'INDAS', 'NBFC', 'BANKING', 'NONINDAS'}
BASE_MAP = {
    'PAT': ['ProfitLossForPeriod', 'ProfitLossForThePeriod'],
    'PAT_CONTINUING_OPERATIONS': ['ProfitLossForPeriodFromContinuingOperations', 'ProfitLossForThePeriodFromContinuingOperations'],
    'PAT_DISCONTINUED_OPERATIONS': ['ProfitLossFromDiscontinuedOperationsAfterTax', 'ProfitLossFromDiscontinuingOperationAfterTax'],
    'PAT_OWNERS_OF_PARENT': ['ProfitOrLossAttributableToOwnersOfParent'],
    'PAT_NONCONTROLLING_INTERESTS': ['ProfitOrLossAttributableToNonControllingInterests'],
    'REVENUE': ['RevenueFromOperations'],
    'TOTAL_INCOME': ['Income'],
    'OTHER_INCOME': ['OtherIncome'],
    'PROFIT_BEFORE_TAX': ['ProfitBeforeTax'],
    'TAX_EXPENSE': ['TaxExpense'],
    'EXPENSES': ['Expenses'],
    'FINANCE_COSTS': ['FinanceCosts'],
    'EPS_BASIC': ['BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations'],
    'EPS_DILUTED': ['DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations'],
    'ASSETS': ['Assets'], 'LIABILITIES': ['Liabilities'], 'EQUITY': ['Equity'],
    'BORROWINGS': ['Borrowings'],
}
FORMAT_MAPS = {kind: {k: list(v) for k, v in BASE_MAP.items()} for kind in KNOWN_FORMATS}
FORMAT_MAPS['NONINDAS']['TOTAL_INCOME'] = ['Revenue']
FORMAT_MAPS['BANKING'].update({
    'PROFIT_BEFORE_TAX': ['ProfitLossFromOrdinaryActivitiesBeforeTax'],
    'OPERATING_PROFIT_BEFORE_PROVISIONS': ['OperatingProfitBeforeProvisionAndContingencies'],
    'INTEREST_EARNED': ['InterestEarned'], 'INTEREST_EXPENDED': ['InterestExpended'],
    'PROVISIONS': ['ProvisionsOtherThanTaxAndContingencies'],
    'EPS_BASIC': ['BasicEarningsPerShareAfterExtraordinaryItems'],
    'EPS_DILUTED': ['DilutedEarningsPerShareAfterExtraordinaryItems'],
    'GROSS_NPA': ['GrossNonPerformingAssets'], 'NET_NPA': ['NonPerformingAssets'],
})
METADATA_MAP = {
    'NSE_SYMBOL': ['Symbol'], 'COMPANY_NAME': ['NameOfCompany', 'NameOfBank'],
    'STANDALONE_CONSOLIDATED': ['NatureOfReportStandaloneConsolidated'],
    'AUDITED_FLAG': ['WhetherResultsAreAuditedOrUnaudited'],
    'REPORTED_QUARTER_LABEL': ['ReportingQuarter'],
    'REPORTING_CURRENCY': ['DescriptionOfPresentationCurrency'],
    'ROUNDING': ['LevelOfRoundingUsedInFinancialStatements'],
    'REPORTED_START': ['DateOfStartOfReportingPeriod'],
    'REPORTED_END': ['DateOfEndOfReportingPeriod'],
    'FINANCIAL_YEAR_START': ['DateOfStartOfFinancialYear'],
    'FINANCIAL_YEAR_END': ['DateOfEndOfFinancialYear'],
}


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def namespace(tag):
    return tag[1:].split('}', 1)[0] if tag.startswith('{') else ''


def as_number(text):
    try:
        value = Decimal(text.strip())
        return value if value.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


def safe_date(text):
    try:
        return date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        return None


def detect_format(filename, root):
    prefix = re.split(r'[_\-.]', Path(filename).name.upper())[0]
    named = prefix if prefix in KNOWN_FORMATS else None
    concepts = {local_name(e.tag) for e in root.iter() if e.get('contextRef')}
    if 'OperatingProfitBeforeProvisionAndContingencies' in concepts:
        content = 'BANKING'
    elif 'ProfitLossForPeriodBeforeMinorityInterest' in concepts:
        content = 'NONINDAS'
    elif {'Loans', 'ImpairmentOnFinancialInstruments'} <= concepts:
        content = 'NBFC'
    elif 'ProfitLossForPeriod' in concepts:
        content = 'INDAS_OR_NBFC'
    else:
        content = 'UNKNOWN'
    conflict = bool(named and content in KNOWN_FORMATS and named != content)
    detected = 'UNKNOWN' if conflict else named or (content if content in KNOWN_FORMATS else 'UNKNOWN')
    return detected, f'filename={named or "unknown"}; content={content}', conflict


def parse_xbrl(filename, payload):
    # Preserve evidence rather than resolving ambiguous facts by document order.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', payload, flags=re.I):
        raise ValueError('DTD/entity declarations are unsupported.')
    ns = dict(pair for _, pair in ET.iterparse(io.BytesIO(payload), events=['start-ns']))
    root = ET.fromstring(payload)
    if root.tag != f'{{{XBRLI}}}xbrl':
        raise ValueError('Expected an XBRL instance XML. Inline XBRL/HTML is not supported.')
    def expand_qname(text):
        prefix, sep, name = (text or '').partition(':')
        return f'{{{ns.get(prefix, prefix)}}}{name}' if sep else f'{{{ns.get("", "")}}}{prefix}'
    fmt, evidence, conflict = detect_format(filename, root)
    issues = []
    def issue(kind, context='', field='', detail=''):
        issues.append({'SOURCE_FILE': filename, 'CONTEXT_ID': context,
                       'FIELD': field, 'ISSUE': kind, 'DETAIL': detail})
    if fmt == 'UNKNOWN':
        issue('UNKNOWN_OR_CONFLICTING_FORMAT', detail=evidence)
    contexts = {}
    for element in root.findall(f'{{{XBRLI}}}context'):
        cid = element.get('id')
        if cid in contexts:
            raise ValueError(f'Duplicate context ID: {cid}')
        def text_at(path):
            found = element.find(path)
            return found.text.strip() if found is not None and found.text else None
        dimensions = []
        for member in element.iter():
            if local_name(member.tag) in {'explicitMember', 'typedMember'}:
                dimensions.append({'dimension': member.get('dimension'),
                                   'member': ''.join(member.itertext()).strip()})
        containers = element.findall(f'.//{{{XBRLI}}}segment') + element.findall(f'.//{{{XBRLI}}}scenario')
        contexts[cid] = {
            'ENTITY_IDENTIFIER': text_at(f'{{{XBRLI}}}entity/{{{XBRLI}}}identifier'),
            'PERIOD_START': text_at(f'{{{XBRLI}}}period/{{{XBRLI}}}startDate'),
            'PERIOD_END': text_at(f'{{{XBRLI}}}period/{{{XBRLI}}}endDate'),
            'INSTANT': text_at(f'{{{XBRLI}}}period/{{{XBRLI}}}instant'),
            'DIMENSIONS': json.dumps(dimensions, sort_keys=True),
            'HAS_CONTEXT_DETAIL': any(len(c) > 0 for c in containers),
        }
    units = {}
    for element in root.findall(f'{{{XBRLI}}}unit'):
        uid = element.get('id')
        if uid in units:
            raise ValueError(f'Duplicate unit ID: {uid}')
        divide = element.find(f'{{{XBRLI}}}divide')
        if divide is None:
            numerator = [expand_qname(e.text) for e in element.findall(f'{{{XBRLI}}}measure')]
            denominator = []
        else:
            numerator = [expand_qname(e.text) for e in divide.findall(f'{{{XBRLI}}}unitNumerator/{{{XBRLI}}}measure')]
            denominator = [expand_qname(e.text) for e in divide.findall(f'{{{XBRLI}}}unitDenominator/{{{XBRLI}}}measure')]
        units[uid] = {'numerator': sorted(numerator), 'denominator': sorted(denominator)}
    facts = []
    for index, element in enumerate(root.iter()):
        cid = element.get('contextRef')
        if not cid:
            continue
        text = ''.join(element.itertext()).strip()
        nil = element.get(f'{{{XSI}}}nil', '').lower() in {'true', '1'}
        unit = element.get('unitRef')
        facts.append({'SOURCE_FILE': filename, 'FORMAT': fmt, 'FACT_INDEX': index,
                      'CONCEPT': local_name(element.tag), 'CONCEPT_QNAME': element.tag,
                      'NAMESPACE': namespace(element.tag), 'CONTEXT_ID': cid,
                      'RAW_VALUE': text, 'IS_NIL': nil, 'UNIT_REF': unit,
                      'UNIT_DEFINITION': json.dumps(units.get(unit), sort_keys=True),
                      'DECIMALS': element.get('decimals'),
                      'NUMERIC_VALUE': str(as_number(text)) if not nil and as_number(text) is not None else None,
                      'CONTEXT_DEFINED': cid in contexts})
    groups = {}
    for fact in facts:
        groups.setdefault(fact['CONTEXT_ID'], []).append(fact)
    rows = []
    known_namespace = lambda f: bool(re.search(r'https?://(?:www\.)?(?:bseindia|nseindia)\.com/', f['NAMESPACE']))
    def pick(group, aliases, cid, field, numeric=False):
        # Alias ordering expresses semantic preference, not a fuzzy tag match.
        for alias in aliases:
            matches = [f for f in group if f['CONCEPT'] == alias and not f['IS_NIL'] and known_namespace(f)]
            if not matches:
                continue
            comparable = {(f['NUMERIC_VALUE'] if numeric else f['RAW_VALUE'], f['CONCEPT_QNAME'],
                           f['UNIT_DEFINITION'] if numeric else '') for f in matches}
            if len(comparable) != 1:
                issue('CONFLICTING_FACTS', cid, field, alias)
                return None
            fact = matches[0]
            if numeric and fact['NUMERIC_VALUE'] is None:
                issue('NONNUMERIC_MAPPED_FACT', cid, field, fact['RAW_VALUE'])
                return None
            if len(matches) > 1:
                issue('IDENTICAL_DUPLICATE_FACTS', cid, field, alias)
            return fact
        return None
    for cid, group in groups.items():
        if not any(f['NUMERIC_VALUE'] is not None and f['UNIT_REF'] for f in group):
            continue
        ctx = contexts.get(cid)
        row = {'SOURCE_FILE': filename, 'FILING_FORMAT': fmt, 'FORMAT_EVIDENCE': evidence,
               'CONTEXT_ID': cid, 'CONTEXT_DEFINED': ctx is not None}
        row.update(ctx or {'ENTITY_IDENTIFIER': None, 'PERIOD_START': None, 'PERIOD_END': None,
                           'INSTANT': None, 'DIMENSIONS': 'UNKNOWN', 'HAS_CONTEXT_DETAIL': True})
        for field, aliases in METADATA_MAP.items():
            chosen = pick(group, aliases, cid, field)
            row[field] = chosen['RAW_VALUE'] if chosen else None
        # Only document-wide identity/currency/rounding are allowed to fall back.
        # Audit status and reporting basis are never borrowed from another period.
        for field in ['NSE_SYMBOL', 'COMPANY_NAME', 'REPORTING_CURRENCY', 'ROUNDING']:
            if row[field] is None:
                chosen = pick(facts, METADATA_MAP[field], cid, field)
                row[field] = chosen['RAW_VALUE'] if chosen else None
        for target, source in [('PERIOD_START', 'REPORTED_START'), ('PERIOD_END', 'REPORTED_END')]:
            if not row[target] and row[source]:
                row[target] = row[source]
                row[target + '_SOURCE'] = 'reporting-date fact; context missing or incomplete'
            elif row[target]:
                row[target + '_SOURCE'] = 'context'
            if row[target] and row[source] and row[target] != row[source]:
                issue('DATE_CONFLICT', cid, target, f"context={row[target]}; fact={row[source]}")
        if row['NSE_SYMBOL'] is None and ctx and ctx['ENTITY_IDENTIFIER']:
            # Identifier is retained separately; do not assume it is an NSE symbol.
            issue('SYMBOL_MISSING', cid, detail=ctx['ENTITY_IDENTIFIER'])
        if ctx is None:
            issue('UNDEFINED_CONTEXT', cid, detail='Values retained for inspection; excluded from strict quarterly output.')
        field_facts = {}
        for field, aliases in FORMAT_MAPS.get(fmt, {}).items():
            chosen = pick(group, aliases, cid, field, numeric=True)
            row[field] = None
            row[field + '_TAG'] = chosen['CONCEPT_QNAME'] if chosen else None
            row[field + '_UNIT'] = chosen['UNIT_DEFINITION'] if chosen else None
            row[field + '_DECIMALS'] = chosen['DECIMALS'] if chosen else None
            if chosen:
                expected_eps = field.startswith('EPS_')
                definition = units.get(chosen['UNIT_REF'])
                num = definition['numerator'] if definition else []
                den = definition['denominator'] if definition else []
                currency = (len(num) == 1 and re.fullmatch(r'\{http://www.xbrl.org/2003/iso4217\}[A-Z]{3}', num[0]))
                correct_unit = currency and ((den == [f'{{{XBRLI}}}shares']) if expected_eps else not den)
                if not correct_unit:
                    issue('UNSUPPORTED_OR_MISSING_UNIT', cid, field, chosen['UNIT_DEFINITION'])
                else:
                    row[field] = chosen['NUMERIC_VALUE']
                    field_facts[field] = chosen
        start, end = safe_date(row['PERIOD_START']), safe_date(row['PERIOD_END'])
        row['DURATION_DAYS'] = (end - start).days + 1 if start and end else None
        row['PERIOD_KIND'] = ('instant' if row['INSTANT'] else 'quarter_like' if row['DURATION_DAYS'] is not None
                              and 70 <= row['DURATION_DAYS'] <= 110 else 'duration_other_or_unknown')
        row['PAT_DEFINITION'] = 'Total profit/loss for period; not owners-only or comprehensive income'
        if row.get('PAT') is None and row.get('PROFIT_BEFORE_TAX') is not None:
            issue('TOTAL_PAT_UNAVAILABLE', cid, 'PAT', 'Review raw facts; no substitution from continuing operations or PBT minus tax.')
        if all(row.get(k) is not None for k in ['PROFIT_BEFORE_TAX', 'TAX_EXPENSE', 'PAT']):
            definitions = {row[k + '_UNIT'] for k in ['PROFIT_BEFORE_TAX', 'TAX_EXPENSE', 'PAT']}
            if len(definitions) == 1:
                difference = Decimal(row['PROFIT_BEFORE_TAX']) - Decimal(row['TAX_EXPENSE']) - Decimal(row['PAT'])
                row['PBT_MINUS_TAX_MINUS_PAT'] = str(difference)
                if difference:
                    issue('PAT_RECONCILIATION_DIFFERENCE', cid, 'PAT', str(difference))
        row['STRICT_QUARTER_CANDIDATE'] = bool(ctx is not None and not row['HAS_CONTEXT_DETAIL']
            and row['PERIOD_KIND'] == 'quarter_like' and fmt in KNOWN_FORMATS
            and (row['STANDALONE_CONSOLIDATED'] or '').strip().lower() in {'standalone', 'consolidated'}
            and row.get('PAT') is not None and row.get('NSE_SYMBOL'))
        if row['STRICT_QUARTER_CANDIDATE'] and any(i['CONTEXT_ID'] == cid and i['ISSUE'] in
            {'DATE_CONFLICT', 'CONFLICTING_FACTS'} for i in issues):
            row['STRICT_QUARTER_CANDIDATE'] = False
        rows.append(row)
    # Financial statement concepts that need mapping remain visible, never guessed.
    mapped = {a for aliases in FORMAT_MAPS.get(fmt, {}).values() for a in aliases}
    unmapped = sorted({f['CONCEPT'] for f in facts if f['NUMERIC_VALUE'] is not None and
                       any(t in f['CONCEPT'].lower() for t in ['profit', 'tax', 'revenue', 'earning'])
                       and f['CONCEPT'] not in mapped})
    summary = {'SOURCE_FILE': filename, 'FORMAT': fmt, 'FORMAT_EVIDENCE': evidence,
               'FACTS': len(facts), 'DEFINED_CONTEXTS': len(contexts), 'EXTRACTED_CONTEXT_ROWS': len(rows),
               'UNDEFINED_CONTEXT_REFS': len({f['CONTEXT_ID'] for f in facts if not f['CONTEXT_DEFINED']}),
               'PAT_CONTEXT_ROWS': sum(r.get('PAT') is not None for r in rows),
               'STRICT_QUARTER_CANDIDATES': sum(r['STRICT_QUARTER_CANDIDATE'] for r in rows),
               'UNMAPPED_RELATED_CONCEPTS': '|'.join(unmapped)}
    return rows, facts, issues, summary
