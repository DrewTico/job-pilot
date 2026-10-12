"""Shared inert README parser. Run 6A has no network transport or live enablement.

Only explicitly supplied offline snapshots can be fetched. A validated HTML
shape and an asserted complete input envelope do not prove live-source quality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from bisect import bisect_right
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import json
import re
import unicodedata
from typing import Literal
from urllib.parse import urlsplit, urlunsplit, unquote

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from job_agent.http import SourceError
from job_agent.models import (
    IntakeEvidence, IntakeIssue, IntakeLink, IntakeObservation, IntakeOccurrence,
    IntakeParseResult, IntakeTransformation, Job,
)
from job_agent.research import CompanyFact, packet_content_flags
from job_agent.sources.base import JobSource

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_ROWS = 10_000
MAX_RECORD_CHARS = 16_384
MAX_FIELD_CHARS = 512
MAX_LOCATION_CHARS = 2048
MAX_URL_CHARS = 2048
MAX_AGE_CHARS = 128
PARSER_VERSION = 'simplify-readme-v1'
REPOSITORIES = {
    'simplify-newgrad': 'SimplifyJobs/New-Grad-Positions',
    'simplify-internships': 'SimplifyJobs/Summer2027-Internships',
}
COLUMNS = ('company', 'role', 'location', 'application', 'age')
TRACKING_KEYS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid'}
MARKERS = ('🚀', '🔒', '🛂', '🇺🇸')
FailureCode = Literal[
    'timeout', 'rate_limit', 'malformed_envelope', 'document_limit', 'row_limit',
    'record_limit', 'field_limit', 'url_limit', 'format_drift', 'malformed_html',
    'control_character', 'identity_conflict', 'interrupted_fetch',
    'source_unavailable', 'offline_snapshot_required',
]


class SimplifyFailure(SourceError):
    """Stable typed code, never source bodies, URLs or transport error strings."""
    def __init__(self, code: FailureCode):
        self.code: FailureCode = code
        super().__init__(f'Simplify source failure: {code}')


class OfflineSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    body: bytes
    observed_at: datetime
    revision: str | None = Field(default=None, max_length=128)
    complete: bool = True
    failure_code: Literal['timeout', 'rate_limit', 'interrupted_fetch', 'source_unavailable'] | None = None


def _bad_controls(text: str) -> bool:
    return any((unicodedata.category(c).startswith('C') and c not in '\n\r\t')
               or c == '\ufffd' for c in text)


def _clean(text: str) -> str:
    # Markdown inline decoration is inert; do not parse commands or embedded code.
    text = re.sub(r'\*\*|__|`', '', unicodedata.normalize('NFC', text))
    return ' '.join(text.split())


def _bounded(text: str, limit: int) -> str:
    if len(text) > limit:
        raise SimplifyFailure('field_limit')
    return text


def _url(original: str) -> str:
    if not isinstance(original, str):
        raise ValueError('unsafe_url')
    if len(original) > MAX_URL_CHARS:
        raise SimplifyFailure('url_limit')
    if not original or any(c.isspace() for c in original) or _bad_controls(unquote(original)):
        raise ValueError('unsafe_url')
    try:
        p = urlsplit(original)
        if p.scheme.lower() not in ('http', 'https') or p.username is not None or p.password is not None:
            raise ValueError('unsafe_url')
        CompanyFact.public_url(original)  # Existing offline public-destination policy.
        host = (p.hostname or '').lower().rstrip('.')
        if not host or not re.fullmatch(r'[a-z0-9.:-]+', host):
            raise ValueError('unsafe_url')
        # Match the existing research boundary for embedded private IP labels.
        for literal in re.findall(r'(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])', host):
            address = ipaddress.ip_address(literal)
            if not address.is_global or address.is_multicast or address.is_reserved:
                raise ValueError('unsafe_url')
        port = p.port
        netloc = f'[{host}]' if ':' in host else host
        if port is not None and (p.scheme.lower(), port) not in (('http', 80), ('https', 443)):
            netloc += f':{port}'
        # Preserve byte spelling, order, duplicates and identity-bearing values.
        # Only these explicitly recognized tracking keys are removed.
        query = '&'.join(part for part in p.query.split('&')
                         if unquote(part.split('=', 1)[0]).lower() not in TRACKING_KEYS)
        return urlunsplit((p.scheme.lower(), netloc, p.path, query, p.fragment))
    except (ValueError, ValidationError):
        raise ValueError('unsafe_url') from None


@dataclass
class _Cell:
    tag: str
    attrs: dict
    start: int
    raw: str = ''
    text: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)


@dataclass
class _Row:
    raw: str
    cells: list[_Cell]
    locator: str
    category: str | None
    active: bool


class _Tables(HTMLParser):
    """Strict table envelope, permissive inert inline formatting."""
    def __init__(self, document: str):
        super().__init__(convert_charrefs=True)
        self.document = document
        self.offsets = [0]
        for match in re.finditer('\n', document):
            self.offsets.append(match.end())
        self.tables: list[list[_Row]] = []
        self.table = None
        self.cells = None
        self.cell = None
        self.row_start = 0
        self.row_number = 0
        self.total_rows = 0
        self.active = False
        self.hidden = []
        self.link = None
        self.category = None
        # One document scan, rather than rescanning every growing prefix for
        # documents containing many small tables.
        headings = list(re.finditer(r'^#{1,6}\s+(.+)$', document, re.M))
        self.heading_positions = [match.start() for match in headings]
        self.heading_texts = [match.group(1) for match in headings]

    def source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if len({key for key, _ in attrs}) != len(attrs):
            raise SimplifyFailure('malformed_html')
        attrs = dict(attrs)
        if tag == 'table':
            if self.table is not None:
                raise SimplifyFailure('malformed_html')
            self.table = []
            self.row_number = 0
            heading = bisect_right(self.heading_positions, self.source_offset()) - 1
            self.category = _bounded(_clean(self.heading_texts[heading]), MAX_FIELD_CHARS) if heading >= 0 else None
        elif tag == 'tr' and self.table is not None:
            if self.cells is not None:
                raise SimplifyFailure('malformed_html')
            self.total_rows += 1
            if self.total_rows > MAX_ROWS:
                raise SimplifyFailure('row_limit')
            self.cells = []
            self.row_start = self.source_offset()
            self.row_number += 1
            self.active = False
        elif tag in ('td', 'th') and self.table is not None:
            if self.cells is None or self.cell is not None:
                raise SimplifyFailure('malformed_html')
            self.cell = _Cell(tag, attrs, self.source_offset())
            self.cells.append(self.cell)
        if self.cell is not None:
            if tag in ('script', 'style', 'iframe', 'object'):
                self.hidden.append(tag)
                self.active = True
            if any(k.startswith('on') for k in attrs):
                self.active = True
            if self.hidden:
                return
            if tag in ('br', 'li', 'p', 'div'):
                self.cell.text.append('\n')
            if tag == 'img' and attrs.get('alt'):
                self.cell.text.append(attrs['alt'])
            if tag == 'a':
                if self.link is not None:
                    raise SimplifyFailure('malformed_html')
                self.link = {'url': attrs.get('href', ''), 'text': []}
                self.cell.links.append(self.link)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('br', 'img', 'hr', 'input', 'meta', 'link'):
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.cell is not None and not self.hidden:
            self.cell.text.append(data)
            if self.link is not None:
                self.link['text'].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == 'a':
            self.link = None
        elif tag in ('td', 'th') and self.table is not None:
            if self.cell is None or self.cell.tag != tag or self.link is not None:
                raise SimplifyFailure('malformed_html')
            end = self.document.find('>', self.source_offset()) + 1
            self.cell.raw = self.document[self.cell.start:end]
            self.cell = None
        elif tag == 'tr' and self.table is not None:
            if self.cells is None or self.cell is not None:
                raise SimplifyFailure('malformed_html')
            end = self.document.find('>', self.source_offset()) + 1
            raw = self.document[self.row_start:end]
            if len(raw) > MAX_RECORD_CHARS:
                raise SimplifyFailure('record_limit')
            self.table.append(_Row(raw, self.cells,
                f'table:{len(self.tables) + 1}/row:{self.row_number}/offset:{self.row_start}',
                self.category, self.active))
            self.cells = None
        elif tag == 'table':
            if self.table is None or self.cells is not None:
                raise SimplifyFailure('malformed_html')
            self.tables.append(self.table)
            self.table = None
        elif tag in ('li', 'p', 'div') and self.cell is not None:
            self.cell.text.append('\n')

    def finish(self):
        self.feed(self.document)
        self.close()
        if self.table is not None or self.cells is not None or self.hidden:
            raise SimplifyFailure('malformed_html')


def _links(cells: dict[str, _Cell]) -> tuple[IntakeLink, ...]:
    result = []
    for column, cell in cells.items():
        for link in cell.links:
            original = link['url']
            normalized = _url(original)
            p = urlsplit(normalized)
            simplify = p.hostname == 'simplify.jobs' or p.hostname.endswith('.simplify.jobs')
            uuid = re.search(r'/(?:j|p)/([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?:/|$)', p.path) if simplify else None
            kind = ('source_role' if uuid else 'source_navigation') if simplify else (
                'employer_application' if column == 'application' else
                'employer_posting' if column == 'role' else 'other')
            result.append(IntakeLink(cell=column, original_url=original, normalized_url=normalized,
                label=_bounded(_clean(''.join(link['text'])), MAX_FIELD_CHARS), kind=kind,
                link_identity_evidence=uuid.group(1) if uuid else None))
    return tuple(result)


def _one(links, kind):
    values = sorted({link.normalized_url for link in links if link.kind == kind})
    if len(values) > 1:
        raise ValueError('ambiguous_links')
    return values[0] if values else None


def parse_readme(snapshot: OfflineSnapshot, *, namespace: str, lane: str) -> IntakeParseResult:
    """Validate, normalize and prepare source identities before any filtering."""
    if not isinstance(snapshot, OfflineSnapshot) or namespace not in REPOSITORIES:
        raise SimplifyFailure('malformed_envelope')
    if (snapshot.observed_at.tzinfo is None or snapshot.observed_at.utcoffset() is None
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', lane)
            or (snapshot.revision and _bad_controls(snapshot.revision))):
        raise SimplifyFailure('malformed_envelope')
    if snapshot.failure_code or not snapshot.complete:
        raise SimplifyFailure(snapshot.failure_code or 'interrupted_fetch')
    if len(snapshot.body) > MAX_DOCUMENT_BYTES:
        raise SimplifyFailure('document_limit')
    try:
        document = snapshot.body.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        raise SimplifyFailure('malformed_envelope') from None
    if _bad_controls(document):
        raise SimplifyFailure('control_character')
    parser = _Tables(document)
    parser.finish()
    snapshot_hash = sha256(snapshot.body).hexdigest()
    observations = {}
    issues = []
    validated_tables = 0
    for table in parser.tables:
        header = None
        company = None
        company_locator = None
        category = None
        for raw in table:
            texts = [_clean(''.join(cell.text)).lower() for cell in raw.cells]
            if len(texts) == len(COLUMNS) and set(texts) == set(COLUMNS):
                header = texts
                company = None
                company_locator = None
                category = raw.category
                validated_tables += 1
                continue
            if len(set(texts) & set(COLUMNS)) >= 3:
                raise SimplifyFailure('format_drift')
            if header is None:
                continue
            if len(raw.cells) == 1 and raw.cells[0].attrs.get('colspan') == str(len(header)):
                category = _bounded(_clean(''.join(raw.cells[0].text)), MAX_FIELD_CHARS)
                company = None
                company_locator = None
                continue
            if len(raw.cells) != len(header) or any(cell.attrs.get('colspan', '1') != '1'
                    or cell.attrs.get('rowspan', '1') != '1' for cell in raw.cells):
                issues.append(IntakeIssue(code='invalid_row', locator=raw.locator))
                company = None
                company_locator = None
                continue
            cells = dict(zip(header, raw.cells))
            values = {}
            transformations = []
            labels = []
            for name, cell in cells.items():
                original = ''.join(cell.text)
                limit = MAX_LOCATION_CHARS if name in ('location', 'application') else MAX_AGE_CHARS if name == 'age' else MAX_FIELD_CHARS
                _bounded(original, limit)
                normalized = _clean(original)
                _bounded(normalized, limit)
                if name in ('company', 'role'):
                    for marker in MARKERS:
                        if marker in normalized:
                            labels.append(marker)
                            normalized = normalized.replace(marker, '').strip()
                values[name] = normalized
                if name != 'application':
                    transformations.append(IntakeTransformation(field=name, operation='html_to_text', original=cell.raw, normalized=normalized))
                if normalized != original:
                    transformations.append(IntakeTransformation(field=name, operation='plain_text_normalization', original=original, normalized=normalized))
            inherited = ()
            inherited_from = {}
            inherited_company = values['company'] in ('', '↳')
            if inherited_company:
                if not company:
                    issues.append(IntakeIssue(code='invalid_row', locator=raw.locator))
                    continue
                inherited = ('company',)
                inherited_from = {'company': company_locator}
                transformations.append(IntakeTransformation(field='company', operation='inherit_same_table', original=values['company'], normalized=company))
                values['company'] = company
            if not values['company'] or not values['role']:
                issues.append(IntakeIssue(code='invalid_row', locator=raw.locator))
                company = None
                company_locator = None
                continue
            try:
                links = _links(cells)
                posting = _one(links, 'employer_posting')
                application = _one(links, 'employer_application')
                source_role = _one(links, 'source_role')
                basis = posting or application or source_role
                if not basis:
                    raise ValueError('missing_link')
            except ValueError as exc:
                issues.append(IntakeIssue(code=str(exc), locator=raw.locator))
                company = None
                company_locator = None
                continue
            for link in links:
                if link.normalized_url != link.original_url:
                    transformations.append(IntakeTransformation(field='url', operation='safe_url_normalization', original=link.original_url, normalized=link.normalized_url))
            company = values['company']
            if not inherited_company:
                company_locator = raw.locator
            locations = tuple(dict.fromkeys(_clean(part) for part in ''.join(cells['location'].text).split('\n') if _clean(part)))
            location = '; '.join(locations)
            _bounded(location, MAX_LOCATION_CHARS)
            if len(locations) > 1:
                transformations.append(IntakeTransformation(field='location', operation='multi_location_display',
                    original=''.join(cells['location'].text), normalized=location))
            # The strongest validated role-specific URL, scoped and versioned.
            identity_input = json.dumps(['simplify-link-v1', namespace, basis], separators=(',', ':'))
            external_id = 'derived:v1:' + sha256(identity_input.encode()).hexdigest()
            job = Job(id=external_id, source=namespace, title=values['role'], company=company,
                      location=location or 'Unknown', url=posting or application or source_role,
                      apply_url=application)
            signal_text = raw.raw + '\n' + ' '.join(values.values())
            flags = packet_content_flags(job.model_copy(update={'description': signal_text}))
            if raw.active:
                flags = tuple(sorted(set(flags) | {'active_html'}))
            family = 'newgrad' if namespace == 'simplify-newgrad' else 'internships'
            normalized_fields = job.model_dump(mode='json')
            normalized_fields['location'] = location or None
            occurrence = IntakeOccurrence(locator=raw.locator, raw_record=raw.raw, category=category,
                lane=lane, observed_at=snapshot.observed_at, snapshot_sha256=snapshot_hash,
                revision=snapshot.revision, normalized_fields=normalized_fields, relative_age=values['age'] or None,
                links=links, inherited_fields=inherited, inherited_from=inherited_from,
                transformations=tuple(transformations), labels=tuple(labels))
            evidence = IntakeEvidence(source_namespace=namespace, repository=REPOSITORIES[namespace],
                source_url=f'https://github.com/{REPOSITORIES[namespace]}/blob/HEAD/README.md',
                lane=lane, source_family=family, observed_at=snapshot.observed_at, revision=snapshot.revision,
                parser_version=PARSER_VERSION, snapshot_sha256=snapshot_hash, identity_basis=basis,
                source_external_id=external_id, occurrences=(occurrence,), links=links,
                normalized_fields=normalized_fields, transformations=tuple(transformations),
                inherited_fields=inherited, locations=locations, labels=tuple(labels),
                source_classifications=(family,), content_flags=flags, relative_age=values['age'] or None)
            item = IntakeObservation(job=job, evidence=evidence)
            previous = observations.get(external_id)
            if previous:
                # Formatting/occurrence/link decoration can vary; source claims cannot.
                if (previous.job != job or previous.evidence.relative_age != evidence.relative_age
                        or previous.evidence.locations != evidence.locations
                        or set(previous.evidence.labels) != set(evidence.labels)
                        or previous.evidence.occurrences[0].category != category):
                    raise SimplifyFailure('identity_conflict')
                merged = previous.evidence.merge_occurrences(evidence)
                observations[external_id] = IntakeObservation(job=job, evidence=merged)
            else:
                observations[external_id] = item
    if not validated_tables:
        raise SimplifyFailure('format_drift')
    if issues:
        for identity, item in observations.items():
            evidence = item.evidence.model_copy(update={
                'snapshot_completeness': 'partial',
                'occurrences': tuple(o.model_copy(update={'snapshot_completeness': 'partial'})
                                     for o in item.evidence.occurrences),
            })
            observations[identity] = IntakeObservation(job=item.job, evidence=evidence)
    return IntakeParseResult(observations=tuple(observations.values()), issues=tuple(issues),
        completeness='partial' if issues else 'complete', rows_observed=parser.total_rows,
        snapshot_sha256=snapshot_hash)


class _SimplifySource(JobSource):
    def __init__(self, board: str, *, snapshot: OfflineSnapshot | None = None):
        super().__init__(board)
        self.snapshot = snapshot
        self.parse_result: IntakeParseResult | None = None

    @property
    def intake_evidence(self) -> tuple[IntakeEvidence, ...]:
        return tuple(item.evidence for item in self.parse_result.observations) if self.parse_result else ()

    def fetch(self) -> list[Job]:
        self.parse_result = None
        if self.snapshot is None:
            raise SimplifyFailure('offline_snapshot_required')
        self.parse_result = parse_readme(self.snapshot, namespace=self.ats, lane=self.board)
        return [item.job for item in self.parse_result.observations]


class SimplifyNewGradSource(_SimplifySource):
    ats = 'simplify-newgrad'


class SimplifyInternshipsSource(_SimplifySource):
    ats = 'simplify-internships'
