# 个人 Quantumult X 资源

2026-11-24 已对原 25 项分流和 25 项重写逐项复查。此前整合存在遗漏：把不同动作当作重复、整组删除混合脚本功能、遗漏比价和部分广告追踪来源。本轮已修复已证实的缺口；逐项去向与限制见 [公开审计清单](data/qx-integration-reaudit.json)。不能据此声称与不可获得的旧手机缓存绝对等价。

完整可导入配置通过聊天在本机交付。公开仓库不包含节点、机场订阅、证书、私人本地规则或私人配置哈希。[import.snippet](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/import.snippet) 是资源清单，不能覆盖完整 VPN 配置。

## 有序广告分流

混合分流按原始连续顺序拆成六项。三项纯拦截明确使用 **REJECT**，必要放行保留逐条策略，不能把六项都强制为 REJECT。

| 顺序 | 文件 | 强制策略 |
| --- | --- | --- |
| 1 | [ads-allow-first.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-first.list) | 不指定，保留逐条策略 |
| 2 | [ads-reject-main.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-main.list) | **REJECT** |
| 3 | [ads-allow-routing.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-routing.list) | 不指定，保留逐条策略 |
| 4 | [ads-reject-extra.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-extra.list) | **REJECT** |
| 5 | [ads-allow-services.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-services.list) | 不指定，保留逐条策略 |
| 6 | [ads-reject-supplement.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-supplement.list) | **REJECT** |

六项须保持顺序。旧 [ads.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.list) 继续生成用于兼容；它含混合策略，不加统一 force-policy。本轮为原尾部分流补选 62 项有证据的广告／追踪来源，并将四项已有更前拒绝的 IP 兼容副本归入去重，合并后为 **252441** 条。必要放行仍先于相应后续拒绝；新增来源不等于每项都强制改成拒绝。

## 个人重写与原功能补充

| 文件 | 用途 | 本轮规则数 |
| --- | --- | --- |
| [ads.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.conf) | 综合 App 广告、贴吧、神机及 Collections 纯广告 | 2205 |
| [miniapps.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/miniapps.conf) | 小程序广告与界面净化 | 60 |
| [mixed-web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/mixed-web.conf) | 豆瓣广告净化与快捷观影 | 1 |
| [web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/web.conf) | 毒奶网页净化 | 130 |
| [youtube.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/youtube.conf) | YouTube 广告、后台播放与画中画响应处理 | 7 |

个人原生资源使用 `opt-parser=false`。保留全局 KOP 解析器：字幕筛选、TestFlight JS 直引及上游功能补集仍需要原解析设置。`import.snippet` 固定将必需的 FMZ 精准补充放在广泛的个人广告重写之前；不要删掉它后仅导入个人广告文件。

FMZ 补充保留 39 项混合广告／功能处理和 28 项原功能，共 67 条，包含原来的升级提示处理和知乎外链等。实际执行原 KOP 后，67 条处理、原顺序和 49 个来源 hostname 均一致；脚本仍由上游提供。已从个人配置和每日检查中移除京东／淘宝历史比价。上游已划去两项功能，本次用公开示例查询时价格接口证书校验失败。[上游说明](https://github.com/yichahucha/surge#quan-x)

字幕的 `#out=Hant`、BoxJS、Sub-Store、查询任务和图标继续使用原引用。Collections 的四项纯广告处理转入个人资源，其余功能保留外链。cleanup 同样保留原三项非广告功能。豆瓣原脚本保留广告净化与快捷观影两部分。

按个人使用偏好移除了 Netflix 评分和 Google 自动翻页。两项原先均由 QX 直接订阅原作者，仓库的每日任务从未单独追踪这两份重写或其脚本。Google 与 Netflix 仍可分别选择节点，Safari 超级搜索仍可使用。

原来禁用的七项资源继续不启用，包括 WebAdBlock 和 StartUp。单独的 TestFlightDownload 不恢复，因为 [作者说明](https://raw.githubusercontent.com/NobyDa/Script/master/TestFlight/TestFlightAccount.js)及 install 分支代码确认，其区域安装处理已合并进保留的 TestFlightAccount；同时启用会产生冲突。

## 同类服务合并

Google 的 Gemini／YouTube／Drive／Voice 与通用规则合并为一份；Microsoft 的 OneDrive／Copilot／Bing 与通用规则合并为一份。其余服务也各有一份个人原生资源，共 17 项。个人资源显示 `@SangShy`，继续引用上游的资源显示原作者；原始作者、来源及筛选条件仍记录在仓库中。

| 文件 | 显示名 | 策略 |
| --- | --- | --- |
| [service-nintendo.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-nintendo.list) | Nintendo @SangShy | Nintendo |
| [service-claude.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-claude.list) | Claude @SangShy | Claude |
| [service-openai.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-openai.list) | OpenAI @SangShy | OpenAI |
| [service-google.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-google.list) | Google @SangShy | Google |
| [service-github.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-github.list) | GitHub @SangShy | GitHub |
| [service-microsoft.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-microsoft.list) | Microsoft @SangShy | Microsoft |
| [service-spotify.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-spotify.list) | Spotify @SangShy | Spotify |
| [service-netflix.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-netflix.list) | Netflix @SangShy | Netflix |
| [service-tiktok.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-tiktok.list) | TikTok @SangShy | TikTok |
| [service-telegram.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-telegram.list) | 电报代理 @SangShy | 电报代理 |
| [service-streaming.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-streaming.list) | 国际媒体 @SangShy | 国际媒体 |
| [service-cn-media.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-cn-media.list) | 港台番剧 @SangShy | 港台番剧 |
| [service-global.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-global.list) | 全球加速 @SangShy | 全球加速 |
| [service-apple.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-apple.list) | 苹果服务 @SangShy | 苹果服务 |
| [service-china.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-china.list) | 国内网站 @SangShy | direct |
| [service-wechat.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-wechat.list) | 微信直连 @SangShy | direct |
| [service-proxy-fix.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/service-proxy-fix.list) | 代理修正 @SangShy | proxy |

原 KOP 已丢弃的少量 Surge 选项按逐来源的兼容契约处理；原生 QX 选项保持，命名 GEOIP 标签显式保留。同一条流量以客户端实际加载顺序及匹配规则为准。同类服务合并会改变人为构造、同时命中多个宽泛品牌关键词的名称顺序；这类合成样例不是实际连接故障记录，也不证明所有跨服务条件都严格等价。

## 去重边界与 YouTube

分流只对相同匹配、相同策略和相同限定项去重。重写只删除完整操作相同的重复项；同一表达式出现不同动作、响应内容或脚本参数时，按原输入顺序保留并记录重叠，不再擅自丢掉后者。本轮 ads.conf 保留 105 项不等价重叠，删除 225 项完全重复，另补一条经原 KOP 验证可转换的 PSBC 图片规则。与上一版相比净增 106 条；旧审计中的 121 次冲突不是 121 条独有增量。

YouTube 维持单套自托管 Maasea 响应处理，覆盖播放器、get_watch 和设置接口，保留广告清理及后台／画中画字段；不加入外部 Worker 请求转发。二进制测试验证这些字段、QX ArrayBuffer、未知字段保留和异常放行。独立字幕资源继续保留。手机实际息屏播放尚未验证。

## 自动维护与可复核证据

[自动更新任务](https://github.com/SangShy4You/Anti-AD/actions/workflows/update-qx.yml)每天北京时间 08:50 检查。来源筛选基数、已审补充项、精确语法转换、六段策略顺序、脚本依赖和补丁上下文都有守卫；失败保留已发布快照。个人编译产物中的脚本依赖固定到不可变提交，保留原功能的外链继续由上游维护。

本页数字是本轮审计快照；后续实时数量见 [manifest](rules/quantumultx/manifest.json)。原 50 项资源去向、修复证据、去重契约与明确排除项见 [审计 JSON](data/qx-integration-reaudit.json)，许可见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。

旧 chongxie 的冻结缓存不可获得；38 项尾部候选的用途或 IP 独占性尚未证实，未盲目整域封锁。静态构建、真实 KOP 解析和脚本样例测试均不能替代具体 iPhone、App 版本和账号的运行验证。
