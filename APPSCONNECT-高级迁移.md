# Apps Connect 的高级拦截迁移

主域名 MRS 已获用户确认可以联网。已有主订阅地址保持不变，点击更新即可取得本次四个模式的补漏。

## 可直接更新的部分

`ads-domain.mrs` 新增 `fc-video.cdn.bcebos.com`、`sdk1xyajs.data.kuiniuca.com`、`stat.peopleapp.com` 及 `.kingsoft-office-service.com`。最后一项只拦子域，保留根域。它覆盖了十个原有更窄模式，所以总数由 195,913 变为 195,907；覆盖核对证实旧范围没有减少。

这些模式来自 fmz200 原 `chongxie.txt` 的最后公开历史版本，并在作者当前 `rewrite.snippet` 中仍有全主机 plain reject。自动任务只提取明确审计过的七个模式，忽略未审计新条目；任何白名单证据改变都会停止发布，不会从业务 API 的某个广告路径推断整个域名都应拒绝。

## 补齐关键词与有序放行

[advanced-merge.yaml](https://raw.githubusercontent.com/SangShy4You/Anti-AD/main/rules/advanced-merge.yaml) 是**配置合并片段**，不能填入 `domain/ipcidr` 规则集入口，也不能单独替换机场配置。

它保留六个拦截／放行阶段，包含原先未进入域名文件的 97 个全局去重拒绝关键词、36 个放行关键词和一条 ASN 放行。每阶段域名与 IP 使用 MRS；其余表达式使用小型远程 classical/text 文件。两类文件都有远程更新间隔，因此合并后上游内容仍可自动更新。`no-resolve` 保留在对应 IP 引用上。

在 Apps Connect 的完整 YAML 配置编辑路径中，合并三部分：

1. 将片段的 `rule-providers` 条目加入原配置同名映射，保留原条目。
2. 将 `sub-rules.personal_ads` 加入原配置的 `sub-rules` 映射，保留原子规则。
3. 将片段 `rules` 中这一条放在机场原有宽泛分流之前，原有规则接在后面：

```yaml
- SUB-RULE,(OR,((NETWORK,tcp),(NETWORK,udp))),personal_ads
```

合并后停用界面中的聚合域名／IP广告列表，避免它们在子规则返回后再次拒绝本应放行的请求。不要删除机场节点、订阅、DNS、策略组或原有分流；不要重复创建同名顶层 YAML 字段。高级片段不含节点和私有订阅。

放行阶段使用 `PASS` 返回机场原有主规则，拒绝阶段使用 `REJECT`。这符合本项目保留机场国内外分流的目标；它不会强制复刻原 QX 中“全球加速”或 `DIRECT` 的出口。因此它是有序广告豁免配置，不宣称与旧策略强制出口完全一致。

ASN 放行依赖内核的 ASN 数据库。维护验证会从 MetaCubeX 官方发布获取数据库并核对官方 SHA256；手机端也必须能正常初始化对应数据。验证程序会拒绝仅返回成功、实际却警告跳过规则的情况。

原生测试已验证：前面的拒绝仍优先，关键词能被命中，放行会跳过后续广告阶段并回到机场主规则；仅子域通配符不会拦根域，也覆盖多级子域。尚未进行此高级片段的 Apps Connect 真机合并测试。

## 仍不能放进这些文件的功能

25 个原重写资源均已核查内容或可用状态；相关历史内容和当前替代版本分开记录。已确认包括京东接口响应修改、知乎开屏空 JSON／配置响应脚本、豆瓣网页去广告，以及混合集里的路径级净化。

标准 Mihomo 的域名、IP 和高级路由都没有 HTTPS URL 路径或响应体，因此这些处理不能写成同等效果的路由规则。官方 Apps Connect 说明支持完整 YAML，但未找到其外层另有 QX JS／重写／MITM 执行入口的证据；现有证据不足以认定这种入口绝不存在。往 YAML 填入未知 `rewrite`／`script` 字段，可能只被忽略，不能当成迁移成功。

本仓库不会整域封禁 `api.m.jd.com`、`api.zhihu.com`、`youtubei.googleapis.com` 等业务接口来冒充净化，也没有执行或导入付费解锁脚本。PokeHub 的具体广告 SDK 尚未由连接证据定位，因此没有编造专属域名。

逐项来源、HTTP 状态、原作者删除历史、恢复版本与转换边界见 [data/rewrite-audit.json](data/rewrite-audit.json)。当前完整 QX 去广告体验仍未在 Apps Connect 上复现。
