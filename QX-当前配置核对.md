# 2026-11-23 原始 QX 配置核对快照

核对日期：2026-11-23。没有修改原配置，也没有发布其中的节点、订阅凭据、证书或本地规则值。

当前文件直接引用 22 个 GitHub 仓库，另有毒奶网站对应的作者仓库，共 23 个来源对象。25 项远程分流全部启用；25 项远程重写中 18 启用、7 禁用；另有 79 条本地分流、3 条本地重写。

**仓库对象已经列全，不代表该仓库的每项资源都迁入了两份广告聚合。** 本报告逐资源记录已整合、替代、可选、原样保留和尚未完整迁移的状态。

## 全部直接仓库对象

| 仓库 | 当前配置用途／位置 | 聚合关系 |
| --- | --- | --- |
| [app2smile/rules](https://github.com/app2smile/rules) | rewrite_remote | direct |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | filter_remote | direct |
| [chavyleung/scripts](https://github.com/chavyleung/scripts) | rewrite_remote | not-in-current-aggregate |
| [chxm1023/Script_X](https://github.com/chxm1023/Script_X) | rewrite_remote | not-in-current-aggregate |
| [ConnersHua/RuleGo](https://github.com/ConnersHua/RuleGo) | filter_remote, rewrite_remote | partial: original ad filters selected; ten routes and two modules not completely migrated |
| [ddgksf2013/Rewrite](https://github.com/ddgksf2013/Rewrite) | rewrite_remote | not-in-current-aggregate |
| [DivineEngine/Profiles](https://github.com/DivineEngine/Profiles) | rewrite_remote | not-in-current-aggregate |
| [DoracisMu/quanX_rewirte](https://github.com/DoracisMu/quanX_rewirte) | rewrite_remote | not-in-current-aggregate |
| [fmz200/wool_scripts](https://github.com/fmz200/wool_scripts) | rewrite_remote | current author ad collection selected; miniapp profile is optional; old cache not compared |
| [id77/QuantumultX](https://github.com/id77/QuantumultX) | rewrite_remote | not-in-current-aggregate |
| [KOP-XIAO/QuantumultX](https://github.com/KOP-XIAO/QuantumultX) | general, task_local | not-in-current-aggregate |
| [limbopro/Adblock4limbo](https://github.com/limbopro/Adblock4limbo) | filter_remote, rewrite_remote | filter-author-mirror-only; original website rewrite not selected |
| [mieqq/mieqq](https://github.com/mieqq/mieqq) | filter_remote | direct |
| [NobyDa/ND-AD](https://github.com/NobyDa/ND-AD) | filter_remote | direct |
| [NobyDa/Script](https://github.com/NobyDa/Script) | rewrite_remote | an unrelated script dependency is selected; the two original TestFlight resources are standalone |
| [Orz-3/mini](https://github.com/Orz-3/mini) | policy | not-in-current-aggregate |
| [Orz-3/Orz-3](https://github.com/Orz-3/Orz-3) | general | not-in-current-aggregate |
| [Orz-3/QuantumultX](https://github.com/Orz-3/QuantumultX) | rewrite_remote | not-in-current-aggregate |
| [Peng-YM/Sub-Store](https://github.com/Peng-YM/Sub-Store) | rewrite_remote | not-in-current-aggregate |
| [privacy-protection-tools/anti-AD](https://github.com/privacy-protection-tools/anti-AD) | filter_remote | direct |
| [RuCu6/QuanX](https://github.com/RuCu6/QuanX) | rewrite_remote | not-in-current-aggregate |
| [sve1r/Rules-For-Quantumult-X](https://github.com/sve1r/Rules-For-Quantumult-X) | filter_remote | direct |
| [zZPiglet/Task](https://github.com/zZPiglet/Task) | rewrite_remote | not-in-current-aggregate |

## 已确认的额外功能脚本仓库

- [chxm1023/Rewrite](https://github.com/chxm1023/Rewrite)
- [ddgksf2013/Scripts](https://github.com/ddgksf2013/Scripts)
- [sub-store-org/Sub-Store](https://github.com/sub-store-org/Sub-Store)
- [wf021325/qx](https://github.com/wf021325/qx)
- [yichahucha/surge](https://github.com/yichahucha/surge)

这些包括比价、Netflix 评分、Google／豆瓣增强、Collections 及 Sub-Store 的实际脚本来源。NobyDa 旧 TestFlight 区域脚本另引用一个公开 Gist。解析器、工具和图标也已入表，不把它们误当广告规则。

## 需要保留或处理的事项

1. 保留全局 KOP 解析器。新两份原生订阅使用 `opt-parser=false`；原 Surge 模块、TestFlight JS 直引和字幕筛选按原设置处理。
2. 当前同时启用 TestFlightAccount 与旧 TestFlightDownload。[作者说明](https://raw.githubusercontent.com/NobyDa/Script/master/TestFlight/TestFlightAccount.js)要求使用已合并的 Account 时停用旧区域脚本，否则可能安装异常。这是建议，本次没有替你改开关。
3. 保留字幕地址的 `#out=Hant`，由原解析器按原方式筛选。不能丢弃参数后把两条不同字幕处理一起合并。
4. 原 RuleGo 后十份路由均可读取，保持原来的美国节点、电报代理、国际媒体、港台番剧、苹果服务等策略。BM 可选列表的范围和出口并非逐项等价。
5. 原 RuleGo YouTubeAds、Advertising，以及毒奶网页重写，尚未完整迁入当前原生重写。神机广告模块 113 条 plain reject 中有 78 条逐字重合、35 条不同；正则之间的包含关系未作推断。
6. 当前仍启用的旧 `chongxie.txt` 地址是 404，且原配置设为不自动更新。新的聚合使用作者当前 `rewrite.snippet`；旧的本地缓存不能从此配置文本恢复，不能宣称字节等价。
7. 六份当前已禁用的原 raw 是 404，继续保持禁用。旧 Orz-3 比价 wrapper 虽可读取，外部脚本本次下载失败；当前启用的是另一份比价 wrapper。
8. 保留 79 条本地分流和 3 条本地重写。一个本地记录有 `-url` 标记，未证实其启用语义，原样保留。
9. Collections 混有广告处理和权益修改，且禁止转载；本次记录对象、功能和依赖，不复制整包公开。

## 原分流与重写逐项清单

| 段／原行号 | 资源 | 当前启用 | 当前来源状态 | 整合关系 |
| --- | --- | --- | --- | --- |
| filter_remote:47 | [sve1r-AntiAD-V4](https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/refs/heads/main/Rules/Advertising/antiAD-V4.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:48 | [sve1r分流](https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/refs/heads/main/Rules/Advertising/AdReject.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:49 | [毒奶分流](https://limbopro.com/Adblock4limbo.list) | 启用 | 403 | author-github-alternative-not-original-website-byte-proof |
| filter_remote:50 | [野比分流](https://raw.githubusercontent.com/NobyDa/ND-AD/master/QuantumultX/AD_Block.txt) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:51 | [野比分流Plus](https://raw.githubusercontent.com/NobyDa/ND-AD/master/QuantumultX/AD_Block_Plus.txt) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:52 | [规则修正@blackmatrix7](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Direct/Direct.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:53 | [本地局域网@blackmatrix7](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Lan/Lan.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:54 | [广告终结者@anti-ad](https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-surge2.txt) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:55 | [隐私保护@blackmatrix7](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Privacy/Privacy.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:56 | [反劫持@blackmatrix7](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Hijacking/Hijacking.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:57 | [应用内防追踪@mieqq](https://raw.githubusercontent.com/mieqq/mieqq/master/In-AppTracker.txt) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:58 | [微信直连@blackmatrix7](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/WeChat/WeChat.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:59 | [直连修正](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Direct+.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:60 | [广告拦截](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Reject/Advertising.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:61 | [隐私保护](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Reject/Tracking.list) | 启用 | 200 | direct-source-present-with-documented-scope-exclusions |
| filter_remote:62 | [海外抖音](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Streaming/Video/TikTok.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:63 | [谷歌语音](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Google/GoogleVoice.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:64 | [电报代理](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Telegram.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:65 | [国际媒体](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Streaming/!CN.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:66 | [港台番剧](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Streaming/CN.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:67 | [全球加速](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Proxy.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:68 | [苹果服务](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Apple/Apple.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:69 | [国内网站](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Direct.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:70 | [微信直连](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/WeChat.list) | 启用 | 200 | not-in-current-source-selection |
| filter_remote:71 | [代理修正](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Proxy+.list) | 启用 | 200 | not-in-current-source-selection |
| rewrite_remote:74 | [购物比价](https://raw.githubusercontent.com/DoracisMu/quanX_rewirte/master/JdTb.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:75 | [app解锁合集@chxm1023](https://raw.githubusercontent.com/chxm1023/Script_X/main/Collections.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:76 | [去广告合集@chxm1023](https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/rewrite/chongxie.txt) | 启用 | 404 | current-author-replacement |
| rewrite_remote:77 | [App&小程序净化合集@fmz200](https://raw.githubusercontent.com/fmz200/wool_scripts/main/QuantumultX/rewrite/cleanup.snippet) | 启用 | 200 | selected-native-resource |
| rewrite_remote:78 | [百度地图净化[卸载重装]@RuCu6](https://raw.githubusercontent.com/RuCu6/QuanX/main/Rewrites/Cube/bdmap.snippet) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:79 | [影视网站去广告@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Html/WebAdBlock.conf) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:80 | [神机重定向@DivineEngine](https://raw.githubusercontent.com/DivineEngine/Profiles/master/Quantumult/Rewrite/General.conf) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:81 | [Safari超级搜索@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Html/Q-Search.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:82 | [Google自动翻页@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Html/EndlessGoogle.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:83 | [油管字幕翻译@id77](https://raw.githubusercontent.com/id77/QuantumultX/master/rewrite/Youtube_CC.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:84 | [Netflix评分@Orz-3](https://raw.githubusercontent.com/Orz-3/QuantumultX/master/Netflix_ratings.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:85 | [比价脚本@Orz-3](https://raw.githubusercontent.com/Orz-3/QuantumultX/master/JD_TB_price.conf) | 禁用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:86 | [Testflight解锁限制@NobyDa](https://raw.githubusercontent.com/NobyDa/Script/master/TestFlight/TestFlightAccount.js) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:87 | [解除微信链接屏蔽@zZPiglet](https://raw.githubusercontent.com/zZPiglet/Task/master/UnblockURLinWeChat.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:88 | [百度网盘倍速@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Function/BaiduCloud.conf) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:89 | [B站换区脚本[不会配置boxjs请勿勾选]@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Function/BilibiliAutoRegion.conf) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:90 | [豆瓣电影网页快捷跳转@ddgksf2013](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/Html/Douban.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:91 | [boxjs@chavyleung](https://raw.githubusercontent.com/chavyleung/scripts/master/box/rewrite/boxjs.rewrite.quanx.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:92 | [Sub-Store@Peng-YM](https://raw.githubusercontent.com/Peng-YM/Sub-Store/master/config/QX.snippet) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:93 | [毒奶重写](https://limbopro.com/Adblock4limbo.conf) | 启用 | 403 | not-selected-web-rewrite |
| rewrite_remote:94 | [TestFlight区域限制解除](https://raw.githubusercontent.com/NobyDa/Script/master/QuantumultX/TestFlightDownload.conf) | 启用 | 200 | independent-original-functional-or-disabled-resource |
| rewrite_remote:95 | [YouTube去广告](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Module/Block/YouTubeAds.sgmodule) | 启用 | 200 | not-completely-migrated |
| rewrite_remote:96 | [墨鱼去开屏](https://raw.githubusercontent.com/ddgksf2013/Rewrite/master/AdBlock/StartUp.conf) | 禁用 | 404 | independent-original-functional-or-disabled-resource |
| rewrite_remote:97 | [贴吧去广告](https://raw.githubusercontent.com/app2smile/rules/master/module/tieba-qx.conf) | 启用 | 200 | selected-native-resource |
| rewrite_remote:98 | [神机去广告](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Module/Block/Advertising.sgmodule) | 启用 | 200 | not-completely-migrated |

详细的原参数、策略映射、依赖、状态及处理理由见 [机器可读审计](data/qx-current-config-audit.json)。原有聚合来源仍见 [config/qx-sources.json](config/qx-sources.json)。本次没有新增启用资源，也没有用这份公开清单覆盖你的完整配置。
