# 当前个人 QX 配置整理

根据 2026-11-23 提供的配置整理。完整配置只在本机生成，通过聊天单独交付；不上传节点、机场订阅、证书和私人本地规则。

## 2026-11-24 下午更新

服务分流已收敛为 17 个个人资源，Google／Microsoft 各一项；原始来源继续自动检查，标签统一标记来源。YouTube 改为单套播放器响应处理，补回此前整合漏掉的后台播放处理。具体接口、验证范围和使用条件见 [QUANTUMULT-X.md](QUANTUMULT-X.md)。下文保留旧整合盘点作为历史来源记录。

## 2026-11-24 接口更新

新增六项有序分流，将纯 REJECT 拦截与必要放行分开，原有效规则内容与先后顺序完全保留。新配置及 `import.snippet` 使用六项；旧混合 `ads.list` 仍保留兼容。纯拦截项统一 REJECT，放行项保持逐条策略，具体顺序见 [QUANTUMULT-X.md](QUANTUMULT-X.md)。下文的原整合来源盘点仍适用于混合资源及其六段拆分产物。

## 广告资源

| 个人资源 | 用途 | 当前规则数 |
| --- | --- | --- |
| ads.list | 去广告、防追踪与必要放行 | 252383 |
| [ads.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.conf) | 综合 App 广告、贴吧、神机补充及 Collections 纯广告 | 2099 |
| [miniapps.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/miniapps.conf) | 小程序广告／界面净化 | 60 |
| [mixed-web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/mixed-web.conf) | 豆瓣去广告与快捷观影 | 1 |
| [web.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/web.conf) | 毒奶网页净化 | 130 |
| [youtube.conf](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/youtube.conf) | 原 YouTube 去广告路线 | 7 |

主分流恢复原配置已有的“全球加速”策略组。它包含混合拒绝和必要放行，不加统一 force-policy。新完整配置已保留此策略组和原十份服务路由。

## 功能保留

- 原比价、字幕、Netflix 评分、BoxJS、Sub-Store、解析器、IP／流媒体查询和图标继续使用原远程引用。字幕的 #out=Hant 保留。
- Collections 精确排除迁出的四条纯广告规则，原远程保留其余 194 条；cleanup 原远程仅保留原来的三条非广告功能，广告／净化交个人 miniapps 处理。每日更新会检查这些精确筛选条件没有漂移。
- 不可安全拆开的混合广告／功能脚本仍保留原远程，避免丢失已启用的功能。豆瓣整条混合处理转为个人资源引用，保留原脚本。
- 保留原 79 条本地分流和 3 条本地重写，保护其优先级。十一条可证明为公开广告来源的规则同时纳入仓库；四条不确定的自定义拒绝保留在私有配置中。
- 原七个禁用资源保持禁用；额外停用旧 TestFlightDownload，保留 TestFlightAccount。
- 全局 KOP 解析器继续保留，新个人原生资源各自 opt-parser=false。原节点、DNS、策略、证书和非资源段逐字节保留。

## 已核实的修补

- 原知乎脚本回调变量笔误修正，保留 GPL 来源。
- 小程序原替换图片仓库不可读取，改用本仓库生成的 1×1 透明 PNG，避免坏图引用。
- 毒奶入口采用作者不可变提交的三个可读取网页引擎，CDN 返回 JavaScript 类型；移除作者 Git 树不存在的两个可选标签，修正 BODY 模板中缺失的 script 闭合标签。原作者部分交互 UI 仍可能访问作者网站；未逐站实测动态 CSS。
- 原神机 YouTube 的 UDP 逻辑规则不粗暴扩为全局拦截，私有配置保留原本的 UDP 设置。移除新旧两套重复的 YouTube protobuf 响应脚本，只使用原配置的 app2smile 路线。

每天北京时间 08:50 自动检查上游并生成，失败保留已发布快照。脚本固定版本并只做语法解析，不在构建机执行其业务代码。完整来源和去重证据见 [manifest](rules/quantumultx/manifest.json)、[整理清单](data/qx-consolidation.json)。实际 App 广告与兼容性仍需在 iPhone 上验证。
