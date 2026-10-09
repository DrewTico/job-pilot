"""Additive /ui delivery. No static mount, new listener, or authority policy.

Build artifacts are operator-packaged, immutable snapshots in memory. Missing,
corrupt or incomplete builds disable only /ui; the trusted root stays available.
"""
import hashlib
import json
import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

from job_agent.dashboard.approval_security import AdapterError

BUILD = Path(__file__).resolve().parent / "ui_build"
ASSET = re.compile(r"_next/static/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:js|css)\Z")
FONT = re.compile(
    r"_next/static/media/(?:bricolage-grotesque-latin-wght-normal|geist-latin-wght-normal|"
    r"geist-mono-latin-400-normal|newsreader-latin-400-normal)\.[0-9a-f]{8}\.woff2\Z"
)
MAX_FONT_BYTES = 100_000
MAX_FONT_TOTAL_BYTES = 250_000


def approved_asset(name):
    return ".." not in name and (ASSET.fullmatch(name) is not None or FONT.fullmatch(name) is not None)


def load_assets(root: Path = BUILD):
    """Validate the whole bounded manifest before serving any bytes."""
    try:
        if root.is_symlink():
            return {}
        manifest_path = root / "manifest.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 100_000:
            return {}
        manifest = json.loads(manifest_path.read_bytes())
        if set(manifest) != {"version", "assets"} or manifest["version"] != 1:
            return {}
        entries = manifest["assets"]
        if not isinstance(entries, dict) or not 1 <= len(entries) <= 500 or "index.html" not in entries:
            return {}
        assets, total, font_total = {}, 0, 0
        for name, metadata in entries.items():
            if name != "index.html" and not approved_asset(name):
                return {}
            is_font = FONT.fullmatch(name) is not None
            expected_type = ("text/html" if name == "index.html" else
                             "font/woff2" if is_font else
                             "text/css" if name.endswith(".css") else "text/javascript")
            if (set(metadata) != {"sha256", "size", "type"} or metadata["type"] != expected_type
                    or type(metadata["size"]) is not int
                    or not 0 < metadata["size"] <= (MAX_FONT_BYTES if is_font else 4_000_000)):
                return {}
            candidate = root / name
            if any(part.is_symlink() for part in (candidate, *candidate.parents)):
                return {}
            if not candidate.is_file() or candidate.stat().st_size != metadata["size"]:
                return {}
            content = candidate.read_bytes()
            if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                return {}
            if is_font:
                # WOFF2 fixed header and declared length, never arbitrary binary assets.
                if len(content) < 48 or content[:4] != b"wOF2" or int.from_bytes(content[8:12], "big") != len(content):
                    return {}
                font_total += len(content)
                if font_total > MAX_FONT_TOTAL_BYTES:
                    return {}
            total += len(content)
            if total > 15_000_000:
                return {}
            assets[name] = (content, expected_type)
        # A missing/undeclared font referenced by CSS disables the package too.
        referenced_fonts = set()
        for content, media_type in assets.values():
            if media_type != "text/css":
                continue
            css = content.decode("utf-8")
            if re.search(r"@import\b", css, re.I):
                return {}
            for match in re.finditer(r"url\(\s*[\"']?([^\s\"')]+)[\"']?\s*\)", css):
                url = match[1]
                if not url.startswith("/ui/") or FONT.fullmatch(url[4:]) is None or url[4:] not in assets:
                    return {}
                referenced_fonts.add(url[4:])
        if referenced_fonts != {name for name in assets if FONT.fullmatch(name)}:
            return {}
        return assets
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}


def register_frontend(app):
    assets = load_assets()

    def deliver(name, request):
        if request.query_params or name not in assets:
            raise AdapterError("not_found", 404)
        content, media_type = assets[name]
        return Response(content, media_type=media_type)

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def frontend_shell(request: Request):
        return deliver("index.html", request)

    @app.get("/ui/{asset:path}", include_in_schema=False)
    def frontend_asset(asset: str, request: Request):
        # Exact lookup only; a request never becomes a filesystem path.
        if not approved_asset(asset):
            raise AdapterError("not_found", 404)
        return deliver(asset, request)
