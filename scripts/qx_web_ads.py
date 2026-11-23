"""Maintain the reviewed Limbo entry-point without executing browser code."""
import re
from urllib.parse import urlsplit

ASSETS = ("Adblock4limbo.user.js", "Adblock4limbo.function.js", "elementBlocker.user.js")


def patch_limbo_entry(text, pinned_url):
    identity = urlsplit(pinned_url)
    if identity.scheme != "https" or identity.netloc != "raw.githubusercontent.com" or identity.query or identity.fragment:
        raise ValueError("Expected the public HTTPS upstream Limbo entry-point")
    parts = urlsplit(pinned_url).path.strip("/").split("/")
    if (len(parts) != 5 or parts[:2] != ["limbopro", "Adblock4limbo"]
            or parts[3:] != ["Adguard", "Adblock4limbo.js"] or not re.fullmatch(r"[0-9a-f]{40}", parts[2])):
        raise ValueError("Expected a pinned upstream Limbo entry-point")
    sha = parts[2]
    base = f"https://cdn.jsdelivr.net/gh/limbopro/Adblock4limbo@{sha}/"
    for filename in ASSETS:
        if text.count("https://limbopro.com/Adguard/" + filename) != 1:
            raise ValueError("Limbo asset declaration changed; review required: " + filename)
    text = text.replace("https://limbopro.com/Adguard/", base + "Adguard/")
    text = text.replace("https://limbopro.com/CSS/", base + "CSS/")
    # These two optional declarations point at files absent from the author's
    # published Git tree. Remove their tags, not the three functioning engines.
    removed = []
    lines = text.splitlines()
    for name in ("agent_JS_URL", "autoAdDetector_JS_URL"):
        declarations = [line for line in lines if line.startswith("const " + name + " = ")]
        references = [line for line in lines if 'src="${' + name + '}"' in line]
        if len(declarations) != 1 or len(references) != 2:
            raise ValueError("Limbo optional asset structure changed; review required")
        remove = set(declarations + references)
        lines = [line for line in lines if line not in remove]
        removed.append(name)
    text = "\n".join(lines) + "\n"
    if any(name in text for name in removed):
        raise ValueError("Limbo optional dependency has additional references; review required")
    old = '<script type="text/javascript" defer src="${JS_URL}">'
    if text.count(old + "\n") != 1:
        raise ValueError("Limbo BODY script element changed; review required")
    text = text.replace(old + "\n", old + "</script>\n")
    assets = [base + "Adguard/" + name for name in ASSETS]
    report = {"upstream_commit": sha, "browser_assets": assets,
              "dynamic_css_base": base + "CSS/", "missing_optional_tags_removed": removed,
              "body_script_tag_closed": True,
              "scope": "Entry-point assets and original per-domain CSS use an immutable upstream CDN revision. Interactive UI assets inside upstream engines may still use original author endpoints."}
    return text, report
