# 个人 Quantumult X 资源

当前完整整理见 [QX-整理说明](QX-整理说明.md)，原配置逐项盘点见 [历史核对](QX-当前配置核对.md)。用户的完整可导入配置只在本机生成并通过聊天交付，未上传公开仓库。

## 远程广告资源

新配置将混合分流按原始连续顺序拆成六项，使拦截项能够明确使用 **REJECT**，同时保留必要放行。应按下表完整订阅，不交换顺序：

| 顺序 | 文件 | 强制策略 |
| --- | --- | --- |
| 1 | [ads-allow-first.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-first.list) | 不指定，保留逐条策略 |
| 2 | [ads-reject-main.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-main.list) | **REJECT** |
| 3 | [ads-allow-routing.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-routing.list) | 不指定，保留逐条策略 |
| 4 | [ads-reject-extra.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-extra.list) | **REJECT** |
| 5 | [ads-allow-services.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-allow-services.list) | 不指定，保留逐条策略 |
| 6 | [ads-reject-supplement.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads-reject-supplement.list) | **REJECT** |

拆分不改写、删除或重排任何有效规则行。更新时若连续策略段的数量、顺序或允许策略发生未审变化，构建会停止并保留旧快照。旧 `ads.list` 继续生成，供已有配置兼容使用；新 `import.snippet` 默认引用上述六项。

| 文件 | 用途 |
| --- | --- |
| [ads.list](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.list) | 原广告／追踪分流、必要放行和已审补充 |
| [ads.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.conf) | 综合 App 广告、贴吧、神机补充及 Collections 纯广告 |
| [miniapps.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/miniapps.conf) | 小程序广告／界面净化 |
| [mixed-web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/mixed-web.conf) | 豆瓣去广告与快捷观影 |
| [web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/web.conf) | 毒奶网页净化 |
| [youtube.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/youtube.conf) | YouTube 去广告、后台播放与画中画响应处理 |

上述个人原生资源使用 opt-parser=false。三项纯拦截资源明确使用 force-policy=reject；三项必要放行和兼容用的混合 ads.list 不加统一 force-policy，以保留微信等正常连接。主文件按用户原配置保留“全球加速”策略组；完整配置也需保留此组。

**保留原全局 KOP 解析器。** 原来的服务路由、字幕筛选、TestFlight JS 直引、Collections／cleanup 功能保留仍需要原解析设置。

[import.snippet](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/import.snippet) 是资源清单，不是完整 VPN 配置。没有节点、DNS、最终路由或证书。完整主配置需要保留原设置，不能用资源清单覆盖。

## 同类服务合并资源

Google 的 Gemini／YouTube／Drive／Voice 与通用规则合并为一份；Microsoft 的 OneDrive／Copilot／Bing 与通用规则合并为一份。其余服务也各有一份个人原生资源。新完整配置只引用以下 17 项服务资源，个人资源标签统一标注 `@SangShy`。

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

原作者、原始 URL、逐项筛选参数、去重记录和哈希保留在配置与 manifest。Google／Microsoft 内部仍按专用到通用的原有顺序合并；跨服务优先按已核实域名验证。任意构造的域名若同时包含多个宽泛品牌关键词，不承诺与旧的交错资源列表完全同序。

原 KOP 已丢弃的少量 Surge 选项仅按逐来源的已审兼容契约处理；原生 QX 选项保持。原有命名 GEOIP 标签也显式保留，仍依赖 QX 原来的相应数据库。

## YouTube 后台播放恢复

此前整合选择了 app2smile 的 browse／next 入口，漏掉原 fmz 资源内 Maasea 的 player／get_watch／settings 响应处理。现改为一套 Maasea 响应处理器，补回后台播放和画中画字段，同时保留广告清理、RuleGo 静态拦截与独立字幕资源。

脚本固定到已审不可变提交并自托管为 `scripts/youtube-background.js`；上游响应逻辑保持，Apache-2.0 归属及许可完整保留。二进制响应回归测试实际执行固定脚本，验证后台／画中画标记、广告字段清理、QX ArrayBuffer 输出、未知字段保留和异常响应放行。尚未在用户 iPhone 上实测；不将新版 UMP 请求转发加入本次整合。

新完整配置以用户最新导出为基准，仅更换资源引用和来源标签，保留最新策略组、节点、DNS、证书和本地规则。仍由外部作者提供的重写标注原作者。

## 原功能与优先级

原比价、字幕、评分、BoxJS、Sub-Store、查询任务与图标继续远程引用。混合来源通过精确筛选保留非广告功能；79 条本地分流与 3 条本地重写留在私有配置中，保护其优先级。当前完整配置保留原十份服务路由，不以可选 BM 列表冒充逐项等价替代。

可选 route-openai／telegram／streaming／wechat／apple／china.list 继续提供，资源清单里默认禁用。新完整配置不额外启用它们。

## 维护与验证

[自动更新任务](https://github.com/SangShy4You/Anti-AD/actions/workflows/update-qx.yml) 每天北京时间 08:50 检查。客户端订阅间隔建议 86400 秒。新脚本、失败下载、规则数量突降、补丁上下文变化、混合功能筛选漂移或语法检查失败都会停止发布并保留旧快照。

脚本固定到不可变上游提交，并读取／语法解析；不会在构建机执行脚本业务。维护的少量修补有上游来源、改动说明和测试。源许可分别保留，见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。

[manifest.json](rules/quantumultx/manifest.json) 记录每份来源、去重、冲突、依赖及哈希。静态验证与下载核对不能替代 iPhone 上实际运行。
