"""Select reviewed advertising/tracking filters from FMZ's mixed QX source.

The upstream file is not a pure ad list. App sections and advertising-network
vendor headings are an explicit reviewed allowlist. Within app sections only
literal ad/tracking labels are selected; licensing, safety, updates, generic
CDNs, push services and whole-business blocks are excluded first. New section
headings are reported, not automatically trusted.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .qx_filters import parse_filters
else:
    from qx_filters import parse_filters

# Section names were reviewed against the public rewrite.snippet snapshot.
APP_SECTIONS = frozenset(['12123', '17173（网络游戏门户网站）', '178游戏网', '18183游戏网', '1905电影网', '2345网址导航', '360', '365日历', '39健康网', '51CTO学堂', '58同城', '58汽车', '9to5Mac', 'AOL（美国在线）', 'Adobe', 'Adobe Flash China Special Edition', 'Akamai', 'Amazon', 'Apple', 'BBC', 'Bing', 'Braze', 'C&J Marketing', 'CNN', 'CSDN', 'Camera360', 'Dr.Peng', 'Facebook', 'Go.com', 'Google', 'Hao123', 'Huawei AspiegelBot', 'Keep', 'LinkWiFi', 'LinkedIn', 'Lycos', 'MacKeeper', 'Makeding (苏州思杰马克丁)', 'Microsoft', 'Naver', 'New Relic', 'OPPO', 'Openmultimedia', 'Optimix（奥迪美）', 'Oupeng (欧朋)', 'Outfit7（会说话的汤姆猫）', 'Outlook', 'PPTV', 'PeanutWiFi', 'Photoable', 'QQ音乐', 'Sape', 'Snapchat', 'Soul', 'Talkatone', 'Tanwan (贪玩)', 'TubeMax', 'Tumblr', 'Turn', 'Twitch', 'Twitter', 'UC浏览器', 'Unity Ads', 'Urban Airship', 'VIVO商城', 'Vivo', 'Waps（无线广告交易中心）', 'Whale Cloud (鲸云)', 'WiFi万能钥匙', 'Wostore (联通沃商店)', 'YY直播平台', 'Yahoo', 'ZAKER新闻', 'bshare', '一点资讯', '七猫小说', '世纪佳缘', '东方网', '东方财富', '两步路', '中关村', '中华万年历', '中华网', '中国平安', '中国日报', '中国电信', '中国移动', '中国联通', '乐居', '乐播投屏', '乐视', '九游', '书旗小说', '买单吧', '云之家', '云闪付', '互传', '亚信科技', '京东', '人人视频', '人民网', '什么值得买', '今日头条', '优酷', '会声会影', '作业帮', '元聚网络（漫画岛，追书神器，甜瓜小说）', '光大银行 阳光惠生活', '凤凰新媒体', '创维', '勾正数据（GozenData）', '华为商城', '华数TV', '叮咚买菜', '叮嗒出行', '同盾', '同花顺', '和讯网', '咪咕视频', '唯品会', '喜马拉雅', '团油', '国双 (Gridsum)', '国美电器', '墨迹天气', '多多视频', '天天看看', '天神', '太平洋电脑', '央视影音 (CBox)', '央视网', '奔图', '好游快爆', '妈妈网', '字节跳动', '宝宝树', '寻医问药', '小利生活', '小小影视', '小爱音箱', '小米', '小红书', '崩坏3', '巨潮资讯', '广州地铁乘车码', '建行生活', '当当网', '快乐广播', '快压zip', '快懂百科', '快手', '快速问医生', '悠易互通', '悠视网', '懂球帝', '懂车帝', '房天下 (Soufun)', '手机中国', '抖音', '搜狐', '搜狗', '搜狗输入法', '收钱吧', '数盟 (Shuzilm)', '斗鱼直播', '新华网', '新民网', '新浪', '易查', '易车', '晓晓优选', '暴风影音', '有米', '朵朵校友圈', '歪麦霸王餐', '民生银行', '汽车之家', '沪江网校', '淘宝', '淘淘搜', '深圳通', '游久网', '游民星空', '游迅网', '湖南卫视', '滴滴青桔', '澎湃新闻', '爆米花', '爱卡汽车网', '爱奇艺', '爱拍', '猫扑 (Mop)', '环球网', '电脑之家', '番茄小说', '百姓网', '百度', '百度地图', '百度贴吧', '百意', '百词斩', '皮皮虾', '盛趣游戏', '真不卡', '知乎', '笔趣阁', '米家', '网易', '美团', '美图秀秀', '美柚', '美颜相机', '联想', '腾讯智慧', '腾讯系', '艺龙', '芒果TV', '苏宁易购', '蓝基因', '蘑菇街', '虎扑', '虎牙直播', '蜻蜓FM', '讯飞输入法', '豆瓣', '豌豆荚', '财新网', '购物党', '赶集网', '车来了', '迅雷', '途虎养车', '酷6网', '酷我音乐', '酷狗音乐', '金山系 (Kingsoft)', '金山词霸', '金立 (Gionee)', '金融界', '闪萌', '阿里云', '雪球', '音悦Tai', '风行网', '飞常准', '饿了么', '驾校一点通', '高德地图', '魅族 (Meizu)', '黄油相机', '齐鲁网'])
NETWORK_VENDORS = frozenset(['Ad-Stir', 'Ad-m.asia', 'AdChina', 'AdColony', 'AdRoll', 'Adadapted', 'AddThis', 'Adform', 'Adhouyi (广告后台)', 'Adinall', 'Adition', 'Adjust', 'Admarvel', 'Adtaily', 'Adups', 'Adview', 'Adwo', 'Adzerk', 'AerServ', 'Airpush', 'App-Adforce', 'Appadhoc', 'Appdriver', 'AppsFlyer', 'CNZZ', 'Cacafly', 'Casale Media', 'Chartboost', 'Clicki', 'Criteo', 'Dianjoy', 'Dianru', 'Exoclick', 'Exosrv', 'Flurry', 'GrowingIO', 'Guomob (果盟)', 'InMobi', 'Innity', 'Inveno', 'IronSource', 'Jesgoo', 'JuicyAds', 'Kejet', 'Keyrun', 'Kissmetrics', 'Kochava', 'Krux', 'Leadbolt', 'Localytics', 'MGID', 'Marketgid', 'Mathtag', 'Millennial Media', 'Mixpanel', 'MoPub（Twitter 公司旗下的移动广告服务平台）', 'Moat', 'Mobfox', 'NetworkBench (听云)', 'NicoNico', 'Onetad', 'OpenX', 'Optimizely', 'Oracle', 'Pagechoice', 'Plista', 'PopAds', 'PubMatic', 'Pubnative', 'Qtmojo', 'Quantcast', 'Qumi (趣米)', 'Rayjump', 'Rubicon Project', 'Segment', 'Sigmob', 'Sizmek', 'Smaato', 'Smart AdServer', 'Snapmobile', 'StartApp', 'StatCounter', 'TGBus', 'TalkingData', 'Tapad', 'Tapjoy', 'Taptica', 'Touclick', 'Trafficfactory', 'Trafficjunky', 'VigLink', 'Voiceads', 'Vpon', 'Vungle', 'Yandex', 'Yengo', 'Zedo', 'comScore', 'dtscout', 'iClick', 'iPinYou (品友互动)', '亿动广告传媒', '亿起发', '优效平台', '创智汇聚', '指点传媒', '推啊 (Tuia)', '聚胜万合', '艾德思奇（adSage）', '诸葛智能', '酷云互动', '魔窗'])
NETWORK_DISALLOWED = {"Adups": "firmware/software-update service", "Touclick": "captcha service"}

INTRO_RULES = {
    ("host-suffix", "miaozhen.com"), ("host-suffix", "ad-sign.byteimg.com"),
    ("host-keyword", "asiad.byteactivity"), ("host-keyword", "pangolin-sdk-toutiao"),
    ("host-keyword", "pglstatp-toutiao"), ("host-suffix", "pangolin.snssdk.com"),
    ("host-suffix", "log.aliyuncs.com"), ("host-suffix", "zlsdk.1rtb.net"),
    ("host-keyword", "umeng"),
}
WHOLE_BUSINESS_OR_INFRASTRUCTURE = frozenset({
    "temu.com", "rumble.com", "1a-1791.com", "apple.com", "google.com", "baidu.com",
    "qq.com", "jd.com", "zhihu.com", "taobao.com", "alicdn.com", "aliyuncs.com",
    "snssdk.com", "pstatp.com", "byteimg.com", "amemv.com", "musical.ly", "tiktokv.com",
    "tos.pstatp.com", "video-cn.snssdk.com", "cdntips.net", "tfogc.com",
    "getui.com", "getui.net", "gepush.com", "igexin.com", "pan.baidu.com",
    "api.m.jd.com", "api.zhihu.com", "appcloud2.zhihu.com", "tiebac.baidu.com",
    "youtubei.googleapis.com", "googlevideo.com",
})
AD_LABEL = re.compile(r"(?:ad|ads|adv|advert|advertise|advertising|adserver|adservice|adservices|adapi|adproxy|adx|adlog|adsdk|adstat|adtrack|adtracker|adimg|adui|adunion|adnet|adpush|ssp|dsp)(?:[-_0-9].*)?\Z")
TRACKING_LABELS = frozenset({"analytics", "telemetry", "tracker", "tracking", "log", "logs", "logger", "logservice", "stats", "statistic", "statistics", "stat", "beacon", "apm"})
FILTER_LIKE = re.compile(r"^[A-Za-z][\w-]*\s*,")
SOURCE_URL = "https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/rewrite/rewrite.snippet"
REVIEWED_TAIL_PATH = Path(__file__).resolve().parents[1] / "config/qx-extra-tail-reviewed.json"


def _deny_value(value):
    labels = value.lower().split(".")
    if any("safebrowsing" in label for label in labels):
        return "security/safe-browsing service"
    if any(label.startswith(("license", "lmlicense", "activate", "practivate")) or label == "ereg" for label in labels):
        return "software activation or licensing"
    if any("update" in label or "fota" in label for label in labels):
        return "software/firmware update service"
    if value.lower() in WHOLE_BUSINESS_OR_INFRASTRUCTURE:
        return "whole business site, generic CDN, or push infrastructure"
    return None


def _reviewed_rows(decisions):
    """Validate explicit supplements; upstream app headings alone are not proof."""
    if not isinstance(decisions, dict) or decisions.get("schema_version") != 1 or decisions.get("source_url") != SOURCE_URL:
        raise ValueError("Invalid reviewed FMZ tail specification")
    entries = decisions.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Reviewed FMZ tail entries must be a list")
    approved = {}
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("reason"), str)
                or not entry["reason"].strip() or not isinstance(entry.get("source_section"), str)
                or type(entry.get("source_line_at_review")) is not int or entry["source_line_at_review"] < 1):
            raise ValueError("Reviewed FMZ entry needs provenance and a reason")
        if entry.get("decision") != "include":
            continue
        rules, _ = parse_filters({"id": "reviewed-fmz-tail", "source_format": "qx", "force_policy": None}, entry.get("normalized_rule", ""))
        if len(rules) != 1:
            raise ValueError("Reviewed FMZ supplement must identify one exact rule")
        rule = rules[0]
        if (rule.policy != "reject" or rule.kind not in {"host", "host-suffix", "host-keyword"}
                or rule.options or _deny_value(rule.value)
                or entry["source_section"] not in APP_SECTIONS):
            raise ValueError("Unsafe or unreviewed FMZ tail supplement")
        key = (entry["source_section"], rule.render())
        if key in approved:
            raise ValueError("Duplicate reviewed FMZ tail supplement")
        approved[key] = entry
    return approved


def extract_fmz_ad_filters(sourcebody: str, *, reviewed_decisions=None) -> tuple[str, dict]:
    """Return native QX rows plus full, deterministic classification evidence."""
    if not isinstance(sourcebody, str) or not sourcebody.strip():
        raise ValueError("FMZ source is empty")
    if re.match(r"\s*(?:<!doctype|<html)", sourcebody, re.I):
        raise ValueError("FMZ source is HTML")
    if reviewed_decisions is None:
        reviewed_decisions = json.loads(REVIEWED_TAIL_PATH.read_bytes())
    approved = _reviewed_rows(reviewed_decisions)
    applied = set()
    section, vendor, network = "", "__intro__", False
    records, selected, reasons, sections = [], [], Counter(), Counter()
    marker_seen = False
    unknown_sections, unknown_vendors = set(), set()
    for number, raw in enumerate(sourcebody.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if line.startswith("# > ") and not line.startswith("# >>"):
            section = line[4:].strip()
            network = section == "广告联盟"
            marker_seen |= network
            vendor = "__intro__"
            continue
        if network and line.startswith("# ") and not line.startswith(("# 若有问题", "# 去重后的hostname")):
            vendor = line[2:].strip()
        if not line or line.startswith(("#", ";", "//")) or not FILTER_LIKE.match(line):
            continue
        parsed, _ = parse_filters({"id": "fmz_ad_filter_tail", "source_format": "qx", "force_policy": None}, line)
        if len(parsed) != 1:
            raise ValueError(f"Unexpected FMZ filter structure at line {number}")
        rule = parsed[0]
        reason = _deny_value(rule.value)
        include = False
        if reason:
            reason = "excluded: " + reason
        elif rule.policy != "reject":
            reason = "not selected: non-reject policy"
        elif (section, rule.render()) in approved:
            # An exact reviewed row supplements the old label predicate. Keep
            # the upstream match type and scope; no suffix/keyword widening.
            include, reason = True, "selected: explicitly reviewed ad/tracking supplement"
            applied.add((section, rule.render()))
        elif network:
            if vendor == "__intro__":
                include = (rule.kind, rule.value) in INTRO_RULES
                reason = "selected: reviewed ad-network intro rule" if include else "not selected: unreviewed intro value"
            elif vendor in NETWORK_DISALLOWED:
                reason = "excluded: " + NETWORK_DISALLOWED[vendor]
            elif vendor not in NETWORK_VENDORS:
                unknown_vendors.add(vendor)
                reason = "not selected: unknown advertising-network vendor heading"
            elif rule.kind not in {"host", "host-suffix", "host-keyword"}:
                reason = "not selected: unreviewed network rule type"
            else:
                include, reason = True, "selected: reviewed advertising/analytics vendor section"
        elif section not in APP_SECTIONS:
            unknown_sections.add(section)
            reason = "not selected: unknown app section"
        elif rule.kind in {"host", "host-suffix"}:
            labels = rule.value.split(".")
            if any(AD_LABEL.fullmatch(label) or label in TRACKING_LABELS for label in labels):
                include, reason = True, "selected: explicit ad/tracking host label in reviewed app section"
            else:
                reason = "not selected: mixed business host without an explicit ad/tracking label"
        elif section == "百度贴吧" and rule.kind == "ip-cidr" and rule.value == "180.76.76.200/32":
            include, reason = True, "selected: separately audited Tieba DNS endpoint dependency"
        else:
            reason = "not selected: keyword, user-agent or IP rule needs separate review"
        records.append({"line": number, "section": section, "network_vendor": vendor if network else None,
                        "original_rule": line, "normalized_rule": rule.render(), "selected": include, "reason": reason})
        reasons[reason] += 1
        sections[section] += 1
        if include:
            selected.append(rule.render())
    if not marker_seen or not records or not selected:
        raise ValueError("FMZ advertising/filter structure changed or selected no rules")
    text = "# Reviewed FMZ ad/tracking filter selection; mixed non-ad entries are not imported wholesale.\n"
    text += "\n".join(selected) + "\n"
    return text, {"schema_version": 1, "source_url": SOURCE_URL,
                  "source_sha256": hashlib.sha256(sourcebody.encode()).hexdigest(),
                  "input_filter_rows": len(records), "selected_filter_rows": len(selected),
                  "not_selected_filter_rows": len(records) - len(selected),
                  "reason_counts": dict(sorted(reasons.items())), "section_counts": dict(sorted(sections.items())),
                  "unknown_app_sections": sorted(unknown_sections), "unknown_network_vendors": sorted(unknown_vendors),
                  "reviewed_supplement_count": len(approved),
                  "reviewed_supplements_selected": len(applied),
                  "reviewed_supplements_not_present": [approved[key] for key in sorted(set(approved)-applied)],
                  "reviewed_supplement_decisions_sha256": hashlib.sha256(json.dumps(reviewed_decisions, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                  "classification": records,
                  "selection_policy": "Explicit reviewed section/vendor headings plus app host-label predicate; deny list takes priority. Unknown headings are recorded and not selected. No blanket REJECT conversion.",
                  "validation": "Native QX static parsing only; not an on-device QX behavior test."}
