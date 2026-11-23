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
| [youtube.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/youtube.conf) | 原 YouTube 去广告路线 |

上述个人原生资源使用 opt-parser=false。三项纯拦截资源明确使用 force-policy=reject；三项必要放行和兼容用的混合 ads.list 不加统一 force-policy，以保留微信等正常连接。主文件按用户原配置保留“全球加速”策略组；完整配置也需保留此组。

**保留原全局 KOP 解析器。** 原来的服务路由、字幕筛选、TestFlight JS 直引、Collections／cleanup 功能保留仍需要原解析设置。

[import.snippet](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/import.snippet) 是资源清单，不是完整 VPN 配置。没有节点、DNS、最终路由或证书。完整主配置需要保留原设置，不能用资源清单覆盖。

## 原功能与优先级

原比价、字幕、评分、BoxJS、Sub-Store、查询任务与图标继续远程引用。混合来源通过精确筛选保留非广告功能；79 条本地分流与 3 条本地重写留在私有配置中，保护其优先级。当前完整配置保留原十份服务路由，不以可选 BM 列表冒充逐项等价替代。

可选 route-openai／telegram／streaming／wechat／apple／china.list 继续提供，资源清单里默认禁用。新完整配置不额外启用它们。

## 维护与验证

[自动更新任务](https://github.com/SangShy4You/Anti-AD/actions/workflows/update-qx.yml) 每天北京时间 08:50 检查。客户端订阅间隔建议 86400 秒。新脚本、失败下载、规则数量突降、补丁上下文变化、混合功能筛选漂移或语法检查失败都会停止发布并保留旧快照。

脚本固定到不可变上游提交，并读取／语法解析；不会在构建机执行脚本业务。维护的少量修补有上游来源、改动说明和测试。源许可分别保留，见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。

[manifest.json](rules/quantumultx/manifest.json) 记录每份来源、去重、冲突、依赖及哈希。静态验证与下载核对不能替代 iPhone 上实际运行。
