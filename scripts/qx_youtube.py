"""Validate the reviewed response-only Maasea YouTube integration.

No network I/O or script evaluation occurs here. The existing upstream QuanX
bodyBytes bridge and background/PiP and ad-removal logic remain unchanged.
"""
from __future__ import annotations

import hashlib
import re


NATIVE_SOURCE = "https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/config/qx-youtube-player.conf"
RESPONSE_SCRIPT = "https://raw.githubusercontent.com/Maasea/sgmodule/master/Script/Youtube/youtube.response.js"
NATIVE_PATTERN = r"^https:\/\/youtubei\.googleapis\.com\/youtubei\/v1\/(browse|next|player|search|reel\/reel_watch_sequence|guide|account\/get_setting|get_watch|log_event|config)(\?(.*))?$"
PINNED_SCRIPT = re.compile(r"https://raw\.githubusercontent\.com/Maasea/sgmodule/[0-9a-f]{40}/Script/Youtube/youtube\.response\.js\Z")

# These context checks deliberately stop publication when minified upstream
# behavior changes, so background support is not silently replaced by an ad-only
# handler. Review changes together with the binary-response regression fixture.
REQUIRED_MARKERS = {
    "player_background_and_pip": "function Si(l){let e=l.playabilityStatus;e.pictureInPictureRender=me.create({pictureInPictureAbility:{active:!0,f4:0,f6:0,f8:1}}),e.backgroundPlayerRender=ge.create({backgroundAbility:{active:!0}})}",
    "player_ad_removal": "function Ni(l){l.adPlacements?.length&&(l.adPlacements.length=0),l.adSlots?.length&&(l.adSlots.length=0),delete l?.playbackTracking?.pageadViewthroughconversion}",
    "player_pipeline": "function Br(l,e){Ni(l),Si(l),Pi(l,e)}",
    "player_dispatch": '{path:"player",msgType:oe,handler:Ai}',
    "setting_background": "backgroundPlayBackSettingRenderer:{backgroundPlayback:!0,download:!0,downloadQualitySelection:!0,smartDownload:!0,icon:{iconType:1093}}",
    "quanx_response_bytes": 't==="bodyBytes"&&(r=G.transferBodyBytes(r,"Uint8Array"))',
    "quanx_done_bytes": 'done(e){let t=e.response??e,n={};for(let[i,r]of Object.entries(t))i==="status"?n.status=`HTTP/1.1 ${r}`:i==="bodyBytes"?n.bodyBytes=G.transferBodyBytes(r,"ArrayBuffer"):n[i]=r;$done(n)}',
}


def prepare_response_script(body: str, pinned_url: str):
    """Return self-hostable unchanged logic plus a provenance comment/report."""
    if not isinstance(body, str) or not body.strip() or re.match(r"\s*(?:<!doctype|<html)", body, re.I):
        raise ValueError("YouTube response dependency is empty or HTML")
    if not isinstance(pinned_url, str) or not PINNED_SCRIPT.fullmatch(pinned_url):
        raise ValueError("YouTube response dependency must have an immutable reviewed GitHub URL")
    missing = [name for name, marker in REQUIRED_MARKERS.items() if body.count(marker) != 1]
    if missing:
        raise ValueError("YouTube response behavior changed; review required: " + ", ".join(missing))
    if "workers.dev" in body or "init-stream.maasea" in body or "workerUrl" in body:
        raise ValueError("YouTube response integration must not include Worker forwarding")
    prefix = ("// Maasea YouTube response integration, Apache-2.0.\n"
              "// License: /licenses/Maasea-sgmodule-APACHE-2.0.txt\n"
              "// The upstream response logic is unchanged; request Worker hooks are omitted.\n")
    report = {
        "upstream": pinned_url,
        "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_logic_unchanged": True,
        "response_only": True,
        "external_worker_imported": False,
        "validated_features": list(REQUIRED_MARKERS),
        "scope": "Restores the removed player/get_watch/settings response processing; not an iPhone runtime proof.",
    }
    return prefix + body, report
