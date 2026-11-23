# 个人 Quantumult X 规则

这是 QX 原生分流和重写资源，适用于现有 AnyTLS 配置。默认以去广告、防追踪和必要放行为主；微信、Apple、OpenAI、Telegram、国际媒体、国内网站作为独立可选路由。没有节点、订阅密码或证书。

## 添加两个主要订阅

分流规则资源地址：

```text
https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.list
```

重写规则资源地址：

```text
https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.conf
```

也可以将下面两行分别添加到现有配置的同名段。不要下载它们覆盖完整配置。

```ini
[filter_remote]
https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.list, tag=个人去广告与防追踪, update-interval=86400, opt-parser=false, enabled=true

[rewrite_remote]
https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/ads.conf, tag=个人去广告重写（含脚本）, update-interval=86400, opt-parser=false, enabled=true
```

**分流是混合策略文件，不添加统一 `force-policy=reject`。** 文件内部保留拒绝和必要放行。原先个性化策略名“全球加速”映射到 QX 内置 `proxy`；其余使用 `direct`、`reject`，不要求额外新建策略组。文件内优先放行安全浏览相关的四个具体主机，以及知乎响应净化需要的 `appcloud2.zhihu.com`。

备份原配置后，将主分流放在宽泛的国内、国外路由之前；个人更高优先级的例外继续按实际需求保留。先下载并启用这两个资源，再停用被其替代的旧广告／追踪列表和旧去广告重写合集，避免旧规则重新拦截已放行主机或重复处理响应。原有功能性重写（如字幕、比价、BoxJS、Sub-Store）按实际需要保留，本次没有合并这些功能。

路径／响应体去广告需要启用 QX 的重写和 MitM，以及现有已安装并信任的个人证书。订阅自身包含去重后的必要主机名；没有公开证书或更改证书校验设置。主重写中保留京东启动与营销接口、知乎开屏及响应清理、贴吧 JSON／protobuf 脚本，并补齐贴吧配套分流和第二个精确 MitM 主机。PokeHub 未找到可确认的专属规则；不能承诺通用 SDK 拦截能覆盖其当前版本。

## 可选资源

[import.snippet](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/quantumultx/import.snippet) 列出全部可合并条目。它是导入清单，不是完整配置；可选条目默认 `enabled=false`。

| 文件（均位于 `rules/quantumultx/`） | 用途 | 文件内默认策略 |
| --- | --- | --- |
| `miniapps.conf` | 小程序界面净化，可能隐藏用户想保留的活动入口 | 重写，默认不启用 |
| `route-openai.list` | OpenAI 服务路由 | proxy |
| `route-telegram.list` | Telegram 路由 | proxy |
| `route-streaming.list` | 国际媒体路由，原集合也包含部分 AI 服务 | proxy |
| `route-wechat.list` | 微信直连 | direct |
| `route-apple.list` | Apple 服务，地区相关服务可能需要单独覆盖 | direct |
| `route-china.list` | 国内网站直连 | direct |

可选服务路由不要同时叠加已在使用的同类整包。需要特定国家节点的服务，导入时在 QX 中选择已有策略组。顺序建议为个人例外 → 主广告集合 → OpenAI／Telegram等具体服务 → 国际媒体 → 国内直连 → 现有最终兜底。没有替换 DNS、AnyTLS 参数、最终兜底或机场订阅。

## 已做的整合和核查

- 实读原十五个分流来源，补入 anti-AD 当前原生 QX 版和贴吧官方配套；保留关键词、User-Agent、ASN、IPv4／IPv6 与原有 qualifier。按相同匹配条件和附加选项去重，保留来源顺序；不跨不同策略粗暴合并父子域。
- 实读 fmz200 的综合重写、小程序净化及 blackmatrix7 的 Advertising／AdvertisingScript，并核对 app2smile 贴吧资源。按完整匹配条件、动作和处理阶段去重；`url-and-header`、不同 `reject` 返回类型、请求与响应阶段均有保留。表达式冲突使用配置中明确的首个来源，逐条记录。
- 排除已发现的会员／付费权限修改、软件激活阻断、更新检查屏蔽、缺本地资源或失效脚本引用。原作者明确禁止转载的集合不复制进公开聚合。fmz 混合文件的分流尾部未整包纳入，避免额外整站、授权和安全服务屏蔽。
- 实读引用的 JavaScript，用 `node --check` 只做语法解析，不执行脚本。脚本固定到上游完整提交 SHA；重写的 JSON 静态响应也实读、校验并固定版本。新脚本 URL 需要先审查再加入允许清单。
- 修正原作者知乎脚本一个明确的变量笔误：回调变量为 `i`，取视频 ID 时误用 `item`。保留原作者代码和许可证，个人修改只有这一处及来源说明。上游修改附近代码后，补丁不再匹配时停止发布，等待复核。
- 对入口脚本做静态外部资源扫描。贴吧、YouTube、百度地图相关 protobuf／schema 已打包在脚本内；部分脚本仍会访问各 App 原有接口或图片。巴哈姆特脚本会等待广告计时并重试，不能保证秒跳。

这是原生文件的静态结构、依赖可用性、语法和更新事务验证。没有在你的 iPhone 上实际执行 QX，也没有断言所有当前 App 版本的广告均已消失。完整来源、行号、重复／冲突、内容哈希和脚本固定版本见 [manifest.json](rules/quantumultx/manifest.json)；可调整来源及个人例外见 [config/qx-sources.json](config/qx-sources.json)。

## 自动维护

[QX 更新任务](https://github.com/SangShy4You/Anti-AD/actions/workflows/update-qx.yml) 每天北京时间 08:50 检查，也可以手动运行。QX 客户端订阅建议每 86400 秒更新。任一来源下载、规则数量门槛、未知语法、依赖或补丁校验失败，任务停止，保留已发布文件；没有变化就不创建提交。

脚本内容变化后由任务重新读取、语法核对并更新固定版本。固定提交可以防止手机直接拉到生成清单之后发生变化的移动分支脚本，但静态核对不等于证明第三方代码行为正确。来源清单和脚本内容仍需要维护者在上游变化时复核。

## 来源和许可证

规则来自各作者公开原始文件，保留来源及相应许可证归属；本仓库的 MIT 原创代码许可不替代第三方规则许可。见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。生成后的 QX 文件不包含账户、节点或证书。原有 Apps Connect MRS 订阅继续按原路径维护。
