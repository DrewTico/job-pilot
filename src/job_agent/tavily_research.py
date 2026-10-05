"""Opt-in, extractive public company research. No LLM or webpage fetching.

The injected transport is an offline test seam, not a configurable endpoint.
Cache writes happen only after all three selected facts pass the same checks
used for cache reads. A failed refresh never serves or replaces stale facts.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import re
from time import monotonic
import unicodedata
from urllib.parse import urlsplit

import httpx
from sqlmodel import Session

from job_agent.database import CompanyResearchCache, database_session, _utc
from job_agent.research import CompanyFact, canonical_source_url, packet_content_flags, usable_facts

ENDPOINT = "https://api.tavily.com/search"
RESEARCHER_VERSION = "tavily-v1-query1-extract1-sources1"
TIMEOUT_SECONDS = 12.0
MAX_BODY_BYTES = 2_000_000
MAX_RESULTS = 8
MAX_RAW_CHARS = 200_000
MAX_TITLE_CHARS = 300
MAX_URL_CHARS = 2048
MAX_SENTENCE_CHARS = 500
MAX_CONTEXT_CHARS = 160
BLOCKED_DOMAINS = frozenset((
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "reddit.com", "tiktok.com", "glassdoor.com", "indeed.com",
    "ziprecruiter.com", "monster.com", "simplyhired.com", "talent.com",
    "jooble.org", "jobgether.com", "jobs.lever.co", "boards.greenhouse.io",
    "job-boards.greenhouse.io", "jobs.ashbyhq.com", "myworkdayjobs.com",
    # Public-looking wildcard/loopback aliases are unsuitable provenance.
    "nip.io", "sslip.io", "localtest.me", "lvh.me",
))


class ResearchUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Company research unavailable; provider details omitted")


def normalize_context(value):
    """Bounded quoted search data: NFC, controls/quotes replaced, spaces folded.

    Oversize context fails closed rather than truncating two employers into the
    same cache identity. Only these public fields enter the network payload.
    """
    if not isinstance(value, str) or len(value) > 4096:
        raise ResearchUnavailable()
    value = unicodedata.normalize("NFC", value)
    value = "".join(" " if unicodedata.category(c).startswith("C") or c in '\\"' else c for c in value)
    value = " ".join(value.split())
    if not value or len(value) > MAX_CONTEXT_CHARS:
        raise ResearchUnavailable()
    return value


def research_queries(company, title):
    company, title = normalize_context(company), normalize_context(title)
    return (f'"{company}" "{title}" engineering product technology',
            f'"{company}" company product mission engineering recent')


def cache_fingerprint(company, title, version=RESEARCHER_VERSION):
    data = dict(provider="tavily", researcher_version=version,
                company=normalize_context(company).casefold(),
                title_context=normalize_context(title).casefold())
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def suitable_source(url):
    if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS:
        return False
    try:
        canonical_source_url(url)
        host = urlsplit(CompanyFact.public_url(url)).hostname.lower().rstrip(".")
        # Reject obvious embedded private-address labels without resolving DNS.
        import ipaddress
        for literal in re.findall(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])", host):
            try:
                address = ipaddress.ip_address(literal)
            except ValueError:
                continue
            if not address.is_global or address.is_multicast or address.is_reserved:
                return False
        return (not host.endswith((".invalid", ".test", ".example", ".onion", ".arpa"))
                and not any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)
                and not re.search(r"(?:^|[./_-])(?:jobs?|careers?|vacancies|job-board)(?:[./_?-]|$)", urlsplit(url).path, re.I))
    except Exception:
        return False


def _well_formed(text):
    return isinstance(text, str) and not any(
        c == "\ufffd" or (unicodedata.category(c).startswith("C") and c not in "\n\r\t") for c in text)


class _SourceText(HTMLParser):
    """Keep inline text contiguous; block boundaries stay separate statements."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self.hidden += 1
        if tag in ("p", "div", "br", "hr", "li", "h1", "h2", "h3", "section", "article", "tr", "td", "th", "script", "style", "nav", "footer"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li", "h1", "h2", "h3", "section", "article", "tr", "td", "th", "script", "style", "nav", "footer"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_source(raw):
    """Formatting cleanup only. Never infer subjects or join separate claims."""
    if not _well_formed(raw) or not raw.strip() or len(raw) > MAX_RAW_CHARS:
        return ""
    parser = _SourceText()
    parser.feed(raw)
    text = unicodedata.normalize("NFC", unescape("".join(parser.parts)))
    # Link labels and emphasis are source words; destinations are not claims.
    text = re.sub(r"\[([^\]\n]+)\]\([^\)\n]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+)", "", text)
    text = text.replace("**", "").replace("__", "")
    return text if _well_formed(text) else ""


_NOISE = re.compile(
    r"\b(?:cookies?|privacy policy|terms of (?:use|service)|all rights reserved|"
    r"sign (?:up|in)|log in|learn more|click here|contact us|apply now|subscribe|"
    r"get started|book a demo|join us|navigation|world.s best|industry.leading|"
    r"cutting.edge|revolutionary|unmatched|unparalleled)\b", re.I)
_DECLARATIVE = re.compile(
    r"\b(?:is|are|was|were|has|have|builds?|develops?|provides?|offers?|operates?|"
    r"launched|released|supports?|uses?|serves?|manufactures?|sells?|creates?|"
    r"founded|maintains?|designs?|produces?|enables?|includes?)\b", re.I)
_REMOTE_DIRECTIVE = re.compile(
    r"\b(?:ignore|disregard|override|obey|instructions?|system prompt|"
    r"candidate (?:data|skills)|add (?:candidate )?skills|approved|"
    r"assistant|call (?:a |the )?tool|JSON schema)\b", re.I)


def safe_sentences(job, raw):
    """Select complete contiguous 8–45 word statements with a predicate.

    Line/paragraph breaks remain boundaries. No joining wrapped fragments, no
    paraphrase, no replacing 'we', and no use of Tavily answer/content fields.
    """
    text = clean_source(raw)
    for line in text.splitlines():
        line = " ".join(line.split())
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if (not 8 <= len(sentence.split()) <= 45 or len(sentence) > MAX_SENTENCE_CHARS
                    or not sentence or not sentence[0].isalpha() or not sentence.endswith(".")
                    or _DECLARATIVE.match(sentence)
                    or re.match(r"(?:it|this|that|they|these|those)\s", sentence, re.I)
                    or _NOISE.search(sentence) or _REMOTE_DIRECTIVE.search(sentence)
                    or not _DECLARATIVE.search(sentence)
                    or packet_content_flags(job.model_copy(update={"description": sentence}))):
                continue
            yield sentence


def cover_eligible(job, text):
    # Include the current verifier's literal casefold test as well as normalized
    # comparison; normalization never inserts a subject into source text.
    company = " ".join(unicodedata.normalize("NFC", job.company).split()).casefold()
    return (bool(company) and re.search(r"(?<!\w)" + re.escape(company) + r"(?!\w)", text.casefold()) is not None
            and job.company.casefold() in text.casefold()
            and not re.search(r"\b(?:I|my|me)\b", text, re.I))


def company_context(job, text):
    company = " ".join(unicodedata.normalize("NFC", job.company).split()).casefold()
    normalized = " ".join(unicodedata.normalize("NFC", text).split()).casefold()
    return bool(company) and re.search(r"(?<!\w)" + re.escape(company) + r"(?!\w)", normalized) is not None


def source_priority(job, url):
    """Preference only, never evidence of ownership or factual accuracy."""
    host = urlsplit(url).hostname.lower().rstrip(".")
    company = re.sub(r"[^a-z0-9]", "", normalize_context(job.company).casefold())
    labels = host.split(".")
    if company and company in labels[:-1]:
        return 0
    if any(host == d or host.endswith("." + d) for d in (
            "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "ft.com", "wsj.com",
            "bloomberg.com", "nytimes.com", "theguardian.com", "techcrunch.com")):
        return 1
    if re.search(r"(?:^|[./])(?:docs|documentation|developer|developers|product)(?:[./]|$)", url, re.I):
        return 2
    if re.search(r"(?:^|[./])(?:engineering|blog)(?:[./]|$)", url, re.I):
        return 3
    return 4


def select_facts(job, candidates):
    """Deterministic cover-first selection, retaining the hardened dedupe gate."""
    # usable_facts caps at three, so choose a cover-eligible source before the
    # three-fact cap can hide it. Canonical URL/text identities still dedupe.
    ordered = sorted(candidates, key=lambda f: (
        not cover_eligible(job, f.text), source_priority(job, f.source_url),
        canonical_source_url(f.source_url), f.text, f.source_title))
    selected = []
    for fact in ordered:
        valid, _ = usable_facts(job, (*selected, fact))
        if len(valid) > len(selected):
            selected.append(fact)
        if len(selected) == 3:
            break
    if len(selected) != 3 or not cover_eligible(job, selected[0].text):
        return ()
    return tuple(selected)


class TavilyCompanyResearcher:
    def __init__(self, engine, settings, *, transport=None, clock=None):
        self.engine = engine
        self._api_key = settings.tavily_api_key
        self.cache_days = settings.company_research_cache_days
        self.transport = transport
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def research(self, job):
        # Reuse the existing context-local SDK/SQL redaction even when this
        # boundary is exercised directly rather than through PacketService.
        from job_agent.packets import private_packet_logs
        with private_packet_logs():
            try:
                return self._research(job)
            except Exception:
                raise ResearchUnavailable() from None

    def _research(self, job):
        key = self._api_key.get_secret_value().strip() if self._api_key is not None else ""
        # A missing key fails closed even with a preexisting cache entry.
        if not key:
            raise ResearchUnavailable()
        company, title = normalize_context(job.company), normalize_context(job.title)
        queries = research_queries(company, title)
        if any(key in q for q in queries):
            raise ResearchUnavailable()
        fp = cache_fingerprint(company, title)
        now = self.clock()
        utc_now = _utc(now)
        with Session(self.engine) as session:
            cached = session.get(CompanyResearchCache, fp)
            if cached is not None and cached.expires_at > utc_now:
                return self._cached_facts(job, cached, key, utc_now)
        candidates = []
        for query in queries:  # Exactly one or two searches; errors escape.
            data = self._search(query, key)
            candidates.extend(self._extract(job, data, now, key))
            facts = select_facts(job, candidates)
            if facts:
                # No transaction spans network IO. Preserve original created_at.
                with database_session(self.engine) as session:
                    row = session.get(CompanyResearchCache, fp)
                    if row is None:
                        row = CompanyResearchCache(fingerprint=fp, researcher_version=RESEARCHER_VERSION,
                            company=company.casefold(), title_context=title.casefold(), facts=[],
                            created_at=utc_now, refreshed_at=utc_now, expires_at=utc_now)
                    row.facts = [f.model_dump(mode="json") for f in facts]
                    row.refreshed_at = utc_now
                    row.expires_at = utc_now + timedelta(days=self.cache_days)
                    session.add(row)
                return facts
        return ()

    def _cached_facts(self, job, row, key, now):
        if (row.provider != "tavily" or row.researcher_version != RESEARCHER_VERSION
                or row.company != normalize_context(job.company).casefold()
                or row.title_context != normalize_context(job.title).casefold()
                or row.refreshed_at > now or row.created_at > row.refreshed_at
                or row.expires_at > row.refreshed_at + timedelta(days=30)
                or not isinstance(row.facts, list) or len(row.facts) != 3):
            raise ResearchUnavailable()
        facts = []
        for data in row.facts:
            if not isinstance(data, dict) or len(json.dumps(data)) > 12_000 or key in json.dumps(data):
                raise ResearchUnavailable()
            fact = CompanyFact.model_validate(data)
            if (not suitable_source(fact.source_url) or not _well_formed(fact.source_title)
                    or len(fact.source_title) > MAX_TITLE_CHARS
                    or packet_content_flags(job.model_copy(update={"description": fact.source_title}))
                    or _REMOTE_DIRECTIVE.search(fact.source_title)
                    or not company_context(job, fact.source_title + " " + fact.text)
                    or tuple(safe_sentences(job, fact.text)) != (fact.text,)):
                raise ResearchUnavailable()
            facts.append(fact)
        if not select_facts(job, facts):
            raise ResearchUnavailable()
        # Exact serialized objects and original provenance, never refreshed time.
        return tuple(facts)

    def _search(self, query, key):
        payload = dict(query=query, search_depth="advanced", topic="general", max_results=MAX_RESULTS,
                       include_answer=False, include_images=False, include_raw_content="text")
        transport = self.transport if self.transport is not None else httpx.HTTPTransport(retries=0, trust_env=False)
        started = monotonic()
        with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS,
                          follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", ENDPOINT, headers={"Authorization": "Bearer " + key,
                    "Content-Type": "application/json", "Accept-Encoding": "identity"}, json=payload) as response:
                # Never read error bodies, follow redirects, or decompress bombs.
                if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity":
                    raise ResearchUnavailable()
                length = response.headers.get("content-length")
                if length is not None and (not length.isdecimal() or int(length) > MAX_BODY_BYTES):
                    raise ResearchUnavailable()
                body = bytearray()
                for chunk in response.iter_raw():
                    if monotonic() - started > TIMEOUT_SECONDS or len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise ResearchUnavailable()
                    body.extend(chunk)
        if monotonic() - started > TIMEOUT_SECONDS:
            raise ResearchUnavailable()
        data = json.loads(body.decode("utf-8"))
        if (not isinstance(data, dict) or not isinstance(data.get("results"), list)
                or len(data["results"]) > MAX_RESULTS):
            raise ResearchUnavailable()
        return data

    @staticmethod
    def _extract(job, data, retrieved_at, key):
        facts = []
        for result in data["results"]:
            # The bounded response is valid; each row is independent untrusted data.
            if not isinstance(result, dict) or any(not isinstance(result.get(k), str)
                    for k in ("url", "title", "raw_content")):
                continue
            url, title, raw = (result[k] for k in ("url", "title", "raw_content"))
            if (not raw.strip() or not _well_formed(title) or len(title) > MAX_TITLE_CHARS
                    or len(raw) > MAX_RAW_CHARS or not suitable_source(url)
                    or any(key in v for v in (url, title, raw))
                    or _REMOTE_DIRECTIVE.search(title)
                    or packet_content_flags(job.model_copy(update={"description": title}))):
                continue
            for sentence in safe_sentences(job, raw):
                if not company_context(job, title + " " + sentence):
                    continue
                facts.append(CompanyFact(text=sentence, source_url=url, source_title=title,
                    retrieved_at=retrieved_at, company=job.company))
        return facts
