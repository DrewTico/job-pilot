"""Bounded private style DATA, with local cooperative locking and publication.

Callers that also need the packet build lock must acquire it FIRST. Acquire this
lock before short database transactions, and release it before provider work.
SQLite and the filesystem are separate resources: revision callers must commit
immutable base/target snapshots before calling recover_prepared(). This module
does not provide database idempotency or decide which feedback is authorized.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import unicodedata
from uuid import uuid4


CANONICALIZATION_VERSION = "style-nfc-lf-v1"
MAX_STYLE_BYTES = 65536
# Independently bound raw input before decoding/normalization. CRLF and common
# decomposed Unicode can be larger than their canonical representation.
MAX_RAW_BYTES = 2 * MAX_STYLE_BYTES
STYLE_FILENAME = "style_memory.md"
LOCK_FILENAME = "style_memory.lock"


class StyleMemoryError(ValueError):
    """Contains only a sanitized machine code; never private content."""


@dataclass(frozen=True)
class CanonicalStyle:
    canonical_content: str
    hash: str
    canonicalization_version: str = CANONICALIZATION_VERSION

    @property
    def utf8(self):
        return self.canonical_content.encode("utf-8", errors="strict")


def canonicalize_style(value: str | bytes) -> CanonicalStyle:
    """Strict UTF-8, all leading BOMs removed, LF, NFC; nothing else changed.

Andrew's approved amendment removes ALL consecutive leading U+FEFF characters.
U+FEFF after the first non-BOM character, NUL, whitespace, Markdown, and terminal
newline presence are preserved. The resulting transformation is idempotent.
"""
    try:
        if isinstance(value, str):
            raw = value.encode("utf-8", errors="strict")
        elif isinstance(value, bytes):
            raw = value
        else:
            raise StyleMemoryError("style_invalid_encoding")
        if len(raw) > MAX_RAW_BYTES:
            raise StyleMemoryError("style_too_large")
        text = raw.decode("utf-8", errors="strict")
        text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        text = unicodedata.normalize("NFC", text)
        body = text.encode("utf-8", errors="strict")
        if len(body) > MAX_STYLE_BYTES:
            raise StyleMemoryError("style_too_large")
        return CanonicalStyle(text, hashlib.sha256(body).hexdigest())
    except UnicodeError:
        raise StyleMemoryError("style_invalid_encoding") from None


def validate_canonical_style(style: CanonicalStyle) -> CanonicalStyle:
    """Recompute identity, including when a value came from retained storage."""
    if not isinstance(style, CanonicalStyle) or style.canonicalization_version != CANONICALIZATION_VERSION:
        raise StyleMemoryError("style_snapshot_invalid")
    checked = canonicalize_style(style.canonical_content)
    if checked != style:
        raise StyleMemoryError("style_snapshot_invalid")
    return checked


def load_style_snapshot(session, snapshot_hash: str) -> CanonicalStyle:
    """Load retained exact content, recomputing its hash on EVERY service load.

    Never substitute the editable file, normalize a damaged stored value, or
    trust a stored digest by itself. Private SQL diagnostics are redacted.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from job_agent.database import StyleMemorySnapshot
    from job_agent.packets import private_packet_logs
    with private_packet_logs():
        try:
            if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64 or any(
                    c not in "0123456789abcdef" for c in snapshot_hash):
                raise StyleMemoryError("style_snapshot_invalid")
            row = session.get(StyleMemorySnapshot, snapshot_hash, populate_existing=True)
            if row is None:
                raise StyleMemoryError("style_snapshot_unavailable")
            return validate_canonical_style(CanonicalStyle(
                row.canonical_content, row.hash, row.canonicalization_version))
        except SQLAlchemyError:
            raise StyleMemoryError("style_storage_error") from None


def ensure_style_snapshot(session, style: CanonicalStyle, *, created_at=None) -> CanonicalStyle:
    """Create/reuse a snapshot inside the caller's SHORT transaction; no commit.

    This intentionally stores private canonical content for historical prompt
    reconstruction. Timestamp is UTC provenance, not semantic identity.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from job_agent.database import StyleMemorySnapshot, _utc
    from job_agent.packets import private_packet_logs
    validate_canonical_style(style)
    with private_packet_logs():
        try:
            row = session.get(StyleMemorySnapshot, style.hash, populate_existing=True)
            if row is None:
                session.add(StyleMemorySnapshot(hash=style.hash,
                    canonical_content=style.canonical_content,
                    canonicalization_version=style.canonicalization_version, created_at=_utc(created_at)))
                session.flush()
            retained = load_style_snapshot(session, style.hash)
            if retained != style:
                raise StyleMemoryError("style_snapshot_invalid")
            return retained
        except SQLAlchemyError:
            raise StyleMemoryError("style_storage_error") from None


def append_feedback(base: CanonicalStyle, *, timestamp_utc: datetime, company: str,
                    title: str, source_packet_id: str, source_packet_version: int,
                    decision_id: str, feedback: str) -> CanonicalStyle:
    """Build one byte-framed entry; durable work, NOT Markdown scanning, dedupes.

    Feedback is canonicalized without trimming. Its byte count, not an end-marker
    search, separates the body from the outside separator. Original decision
    feedback remains untouched in the caller's immutable decision record.
    """
    validate_canonical_style(base)
    if (not isinstance(timestamp_utc, datetime) or timestamp_utc.tzinfo is None
            or timestamp_utc.utcoffset() is None
            or any(not isinstance(v, str) for v in (company, title, source_packet_id, decision_id, feedback))
            or type(source_packet_version) is not int or source_packet_version < 1):
        raise StyleMemoryError("style_entry_invalid")
    body = canonicalize_style(feedback)
    metadata = {
        "timestamp_utc": timestamp_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "company": company, "title": title, "source_packet_id": source_packet_id,
        "source_packet_version": source_packet_version, "decision_id": decision_id,
        "feedback_utf8_bytes": len(body.utf8),
    }
    envelope = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    # Prevent metadata from closing the HTML comment or injecting markup. JSON
    # decoding still returns exact metadata; controls and Unicode are escaped.
    envelope = envelope.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    entry = ("\n\n<!-- job-pilot-style-entry:v1 " + envelope + " -->\n"
             + body.canonical_content + "\n<!-- job-pilot-style-entry:end:v1 -->\n")
    return canonicalize_style(base.canonical_content + entry)


def _private_regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise StyleMemoryError("style_unsafe_path")


class LockedStyleMemory:
    """Descriptor-scoped operations available only while style_lock is held."""

    def __init__(self, directory_fd, exclusive):
        self._directory_fd, self._exclusive = directory_fd, exclusive
        self._active = True

    def _check_active(self):
        if not self._active:
            raise StyleMemoryError("style_lock_required")

    def read(self) -> CanonicalStyle:
        self._check_active()
        descriptor = None
        try:
            try:
                descriptor = os.open(STYLE_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=self._directory_fd)
            except FileNotFoundError:
                return canonicalize_style(b"")
            info = os.fstat(descriptor)
            _private_regular(info)
            if info.st_size > MAX_RAW_BYTES:
                raise StyleMemoryError("style_too_large")
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                raw = stream.read(MAX_RAW_BYTES + 1)
            after = os.fstat(descriptor)
            if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise StyleMemoryError("style_conflict")
            return canonicalize_style(raw)
        except OSError:
            raise StyleMemoryError("style_storage_error") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def publish(self, target: CanonicalStyle, *, expected_base_hash: str):
        """Fsync a private sibling, recheck base, replace atomically, fsync dir.

        Cooperating readers hold a shared lock and cannot see partial contents.
        An uncoordinated hostile writer remains outside the lock guarantee; a
        changed base detected before replacement is never overwritten.
        """
        self._check_active()
        if not self._exclusive:
            raise StyleMemoryError("style_exclusive_lock_required")
        validate_canonical_style(target)
        if self.read().hash != expected_base_hash:
            raise StyleMemoryError("style_conflict")
        temporary = ".style_memory-" + uuid4().hex + ".tmp"
        descriptor = None
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o600, dir_fd=self._directory_fd)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(os.dup(descriptor), "wb") as stream:
                stream.write(target.utf8)
                stream.flush()
                os.fsync(stream.fileno())
            # read() rechecks regular/private/no-follow state and exact semantics.
            if self.read().hash != expected_base_hash:
                raise StyleMemoryError("style_conflict")
            os.replace(temporary, STYLE_FILENAME, src_dir_fd=self._directory_fd,
                       dst_dir_fd=self._directory_fd)
            os.fsync(self._directory_fd)
        except OSError:
            raise StyleMemoryError("style_storage_error") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=self._directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                raise StyleMemoryError("style_storage_error") from None

    def recover_prepared(self, base: CanonicalStyle, target: CanonicalStyle):
        """Resolve committed base/target evidence without re-appending feedback.

        Caller marks style_persisted only AFTER this returns. If the process dies
        after replacement, the next invocation recognizes the retained target.
        """
        self._check_active()
        if not self._exclusive:
            raise StyleMemoryError("style_exclusive_lock_required")
        validate_canonical_style(base)
        validate_canonical_style(target)
        current = self.read()
        if current.hash == target.hash:
            # Also covers a replacement whose directory fsync was interrupted.
            try:
                os.fsync(self._directory_fd)
            except OSError:
                raise StyleMemoryError("style_storage_error") from None
            return target
        if current.hash != base.hash:
            raise StyleMemoryError("style_conflict")
        self.publish(target, expected_base_hash=base.hash)
        return target


@contextmanager
def style_lock(data_dir: Path, *, exclusive=False):
    """Shared readers, exclusive writers; exact sibling names, no path input.

    The configured existing directory and its ancestors must not be symlinks.
    An absent style file stays absent during reads. The sibling lock may be
    created with private permissions. Do not unlink a live lock file.
    """
    directory_fd = lock_fd = None
    locked = None
    try:
        directory = Path(data_dir).absolute()
        if directory.resolve() != directory:
            raise StyleMemoryError("style_unsafe_path")
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock_fd = os.open(LOCK_FILENAME, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=directory_fd)
        _private_regular(os.fstat(lock_fd))
        fcntl.flock(lock_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        locked = LockedStyleMemory(directory_fd, exclusive)
        yield locked
    except OSError:
        raise StyleMemoryError("style_storage_error") from None
    finally:
        if locked is not None:
            locked._active = False
        if lock_fd is not None:
            os.close(lock_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def read_style_memory(data_dir: Path) -> CanonicalStyle:
    with style_lock(data_dir) as locked:
        return locked.read()


def write_style_memory(data_dir: Path, target: CanonicalStyle, *, expected_base_hash: str):
    """Safe file half of a future Settings edit; snapshot persistence is separate."""
    with style_lock(data_dir, exclusive=True) as locked:
        locked.publish(target, expected_base_hash=expected_base_hash)
