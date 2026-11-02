# 个人去广告与防追踪规则

将原 Quantumult X 配置中的广告、追踪拦截与必要放行来源整合为少量可订阅文件，供 Apps Connect 的规则集入口使用。机场客户端原有的国内外分流保持由客户端配置管理。

## 在 Apps Connect 使用

使用“远程 URL”添加。图中的“本地文件”页列出客户端已经下载的资源，外部文件导入入口尚未确认。

| 文件 | 名称 | 行为 | 格式 | 出口 |
| --- | --- | --- | --- | --- |
| [ads-domain.yaml](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/ads-domain.yaml) | 个人去广告 | `domain` | `yaml` | `REJECT` |
| [ads-ip.yaml](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/ads-ip.yaml)（可选） | 个人去广告—IP 补充 | `ipcidr` | `yaml` | `REJECT` |

客户端检查间隔建议 `86400` 秒。拦截规则应位于宽泛的国内直连和最终兜底之前，已有手动放行例外按其实际优先级保留。

新订阅下载成功并启用后，停用之前单独添加、已被本仓库整合的 anti-AD 等广告／追踪列表，避免旧列表继续拦截新集合保留的例外。保留机场原有的国内外分流及个人手动例外。

仓库：[SangShy4You/Anti-AD](https://github.com/SangShy4You/Anti-AD)。上表链接均为 GitHub **Raw** 订阅地址；GitHub 文件浏览页的 `blob` 地址不能作为规则订阅地址。也可从 `data/subscriptions.json` 读取全部填写参数。

`data/report.json` 记录本次实际生成的文件、导入顺序、来源条目数与转换限制。若未来上游新增了不能由单一正向域名集合表达的放行例外，默认停止发布并保留上一版，防止手机只订阅主文件时悄悄漏掉后续阶段。只有先按报告配置完整客户端顺序后，才可显式启用 `allow_ordered_domain_stages`。

首次整合快照（2026-11-02）：11 个拦截来源的 377,253 条域名条目，经跨源去重及父域覆盖压缩后为 **195,913 条**；IP 补充为 **221 个前缀**。后续统计以报告为准。

## 整合方式

- 读取原配置中 11 个广告／追踪拦截来源与 4 个可能影响拦截优先级的放行来源；完整元数据见 `config/upstreams.json`。
- 按域名匹配语义去重：保留精确匹配与后缀匹配的区别，移除已经被父域名后缀覆盖的冗余项。
- 按原先后顺序计算放行与拒绝，避免把整份放行表前置而放过原来被优先拦截的广告域名。
- 合并、折叠可表达的 IPv4／IPv6 网段。域名和 IP 文件分开，以适配客户端的 `domain`／`ipcidr` 入口。
- 不下载或执行上游的 JavaScript，不把 URL 重写里的业务 API 域名抽出来整域拒绝。

旧 anti-AD 副本与当前原作者版本存在独有条目，因此保留来源并按实际内容去重；没有仅因项目名相同就删除整份来源。原作者声明停止维护的来源也会在清单中标注，后续可通过配置有意识地停用。

## 与原 QX 效果的边界

主域名文件和 IP 补充文件分别保留其可表达的匹配语义。关键词、User-Agent、GEOIP／ASN、域名与 IP 的交叉优先级，以及 URL／响应体重写，不能全部装进一个 `domain` 规则集。

`rules/advanced-fragment.yaml` 面向支持完整配置编辑的客户端，保留更多有序匹配表达；它是待合并片段，不是机场节点订阅。实际输出与依赖见报告。

知乎、京东开屏和 PokeHub 底部横幅不能仅凭“QX 能去掉”就断定只靠域名列表。用户原配置中确有 URL／响应级重写；本仓库没有移植重写或承诺恢复全部去广告效果。

## 个人增补

编辑 `config/personal.json`：

- `allow.domains`：只放行这个完整域名。
- `allow.suffixes`：放行这个域名及其子域。
- `allow.ipcidrs`：放行指定网段。
- `reject` 下的同名字段：增加个人拦截项。
- `disabled_sources`：填写希望停用的来源 ID。

个人显式放行优先于个人拦截，再计算上游规则。原文件为空数组，未猜测并添加 App 专属域名。

## 定期维护

GitHub Actions 每天北京时间 **08:20** 检查上游，也可在 Actions 中手动运行 **Update personal rules**。只在产物或上游状态有变化时提交，检查本身不会产生时间戳提交。

任何下载、解析或验证失败都会阻止发布并保留上一版。详细维护方式与 GitHub 调度限制见 `MAINTENANCE.txt`。

本地手动更新：

```sh
python -m unittest discover -s tests
python scripts/update.py
```

初次离线复现可指定已保存的上游目录：

```sh
python scripts/update.py --offline-dir /path/to/upstream-snapshots
```

需要 Python 3.12 或更新版本，运行代码只使用 Python 标准库。

## 来源与许可

上游规则的原作者、项目和可核实的许可链接均记录在 `config/upstreams.json`，归属说明见 `THIRD_PARTY_NOTICES.md`。生成文件不统一宣称拥有所有上游内容的版权或许可。维护代码的许可单独见 `LICENSE-CODE`。
