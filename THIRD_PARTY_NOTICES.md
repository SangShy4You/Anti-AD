# 第三方来源与许可记录

核对日期：2026-11-02。

本仓库聚合规则来自下列原作者项目。生成列表经过本仓库的解析、格式转换及去重，不代表原作者直接发布的版本。上游条目、署名及其许可仍归各自权利人；本文件不将所有聚合数据统一声明为 MIT，也不为未注明许可的来源编造授权。

本文件记录的是所用仓库分支的根许可证及可核实的作者声明。部分上游自身也聚合其他列表，根许可证记录不意味着本仓库已单独确认其所有更上游内容的授权。

## 原作者项目及许可证副本

| 原作者项目 | 所用分支 | 根许可证记录 | 随附原文 |
| --- | --- | --- | --- |
| [sve1r/Rules-For-Quantumult-X](https://github.com/sve1r/Rules-For-Quantumult-X) | `main` | [MIT](https://github.com/sve1r/Rules-For-Quantumult-X/blob/main/LICENSE) | [完整原文](licenses/sve1r-Rules-For-Quantumult-X-MIT.txt) |
| [limbopro/Adblock4limbo](https://github.com/limbopro/Adblock4limbo) | `main` | [MIT](https://github.com/limbopro/Adblock4limbo/blob/main/LICENSE) | [完整原文](licenses/limbopro-Adblock4limbo-MIT.txt) |
| [NobyDa/ND-AD](https://github.com/NobyDa/ND-AD) | `master` | [MIT](https://github.com/NobyDa/ND-AD/blob/master/LICENSE) | [完整原文](licenses/NobyDa-ND-AD-MIT.txt) |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | `master` | [GNU General Public License version 2](https://github.com/blackmatrix7/ios_rule_script/blob/master/LICENSE) | [完整原文](licenses/blackmatrix7-ios_rule_script-GPL-2.0.txt) |
| [privacy-protection-tools/anti-AD](https://github.com/privacy-protection-tools/anti-AD) | `master` | [MIT](https://github.com/privacy-protection-tools/anti-AD/blob/master/LICENSE) | [完整原文](licenses/privacy-protection-tools-anti-AD-MIT.txt) |
| [mieqq/mieqq](https://github.com/mieqq/mieqq) | `master` | 未在所用分支根目录发现 LICENSE/COPYING | 未生成替代许可证 |
| [ConnersHua/RuleGo](https://github.com/ConnersHua/RuleGo) | `master` | 未在所用分支根目录发现 LICENSE/COPYING | 未生成替代许可证 |
| [fmz200/wool_scripts](https://github.com/fmz200/wool_scripts) | `main` | [GNU General Public License version 3](https://github.com/fmz200/wool_scripts/blob/main/LICENSE) | [完整原文](licenses/fmz200-wool_scripts-GPL-3.0.txt) |

四份 MIT 副本分别保留以下原始版权署名；完整许可正文与免责声明均已随文件保存：

- [sve1r/Rules-For-Quantumult-X](https://github.com/sve1r/Rules-For-Quantumult-X)：Copyright (c) 2020 SVE1R。
- [limbopro/Adblock4limbo](https://github.com/limbopro/Adblock4limbo)：Copyright (c) 2022 毒奶博主。
- [NobyDa/ND-AD](https://github.com/NobyDa/ND-AD)：Copyright (c) 2020 NobyDa。
- [privacy-protection-tools/anti-AD](https://github.com/privacy-protection-tools/anti-AD)：Copyright (c) 2017-2019 gently。

blackmatrix7 的随附文件为其仓库原始 GNU GPL version 2 完整文本。本仓库未把该文本改为 MIT，亦未补造上游代码或规则中未出现的版权署名。

## 额外作者声明与未知许可

- sve1r 的根 LICENSE 为 MIT；其 [README「许可与说明」](https://github.com/sve1r/Rules-For-Quantumult-X/blob/main/README.md) 另外写有「请勿将本项目用于商业用途」「任何盈利活动都属于商业用途」。本文件同时保留这项作者声明与根 LICENSE，不删改或自行解释两者关系。
- blackmatrix7 的 [README](https://github.com/blackmatrix7/ios_rule_script/blob/master/README.md) 另声明禁止公众号、自媒体进行任何形式的转载、发布。该声明与根 GPL 文本均予以记录；本文件不把它扩大描述为原作者禁止所有个人 GitHub 仓库。
- [mieqq/mieqq 的 master 分支](https://github.com/mieqq/mieqq/tree/master) 根目录未发现 LICENSE/COPYING，未确认特定再发布许可；保留作者与原始来源，不将该文件标为 MIT 或 GPL。
- [ConnersHua/RuleGo 的 ASCII master 分支](https://github.com/ConnersHua/RuleGo/tree/master) 根目录未发现 LICENSE/COPYING，未确认特定再发布许可；不把同作者其他仓库或其他分支的许可套用到这些文件。

## 本集合引用的原始规则 URL

以下顺序对应用户原配置顺序。这里的「优先放行」仅表示本广告集合中的豁免来源；原配置策略照录，尤其 `06_filter` 的「全球加速」并未改写为 DIRECT。

| ID | 名称 | 用途 | 原配置策略 | 原始来源 |
| --- | --- | --- | --- | --- |
| `01_filter` | sve1r-AntiAD-V4 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/refs/heads/main/Rules/Advertising/antiAD-V4.list) |
| `02_filter` | sve1r分流 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/refs/heads/main/Rules/Advertising/AdReject.list) |
| `03_filter` | 毒奶分流 | 广告/隐私/反劫持拦截 | reject | [原文件](https://limbopro.com/Adblock4limbo.list) |
| `04_filter` | 野比分流 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/NobyDa/ND-AD/master/QuantumultX/AD_Block.txt) |
| `05_filter` | 野比分流Plus | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/NobyDa/ND-AD/master/QuantumultX/AD_Block_Plus.txt) |
| `06_filter` | 规则修正@blackmatrix7 | 优先放行 | 全球加速 | [原文件](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Direct/Direct.list) |
| `07_filter` | 本地局域网@blackmatrix7 | 优先放行 | direct | [原文件](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Lan/Lan.list) |
| `08_filter` | 广告终结者@anti-ad | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-surge2.txt) |
| `09_filter` | 隐私保护@blackmatrix7 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Privacy/Privacy.list) |
| `10_filter` | 反劫持@blackmatrix7 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/Hijacking/Hijacking.list) |
| `11_filter` | 应用内防追踪@mieqq | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/mieqq/mieqq/master/In-AppTracker.txt) |
| `12_filter` | 微信直连@blackmatrix7 | 优先放行 | direct | [原文件](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/QuantumultX/WeChat/WeChat.list) |
| `13_filter` | 直连修正 | 优先放行 | direct | [原文件](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Direct+.list) |
| `14_filter` | 广告拦截 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Reject/Advertising.list) |
| `15_filter` | 隐私保护 | 广告/隐私/反劫持拦截 | reject | [原文件](https://raw.githubusercontent.com/ConnersHua/RuleGo/master/Surge/Ruleset/Extra/Reject/Tracking.list) |

完整来源元信息见 [config/upstreams.json](config/upstreams.json)。非广告用途的其余路由来源仅在该文件的 `excluded` 内留档，不属于本集合的聚合输入。重写、解锁、内容修改脚本未纳入本集合。

## 维护状态与来源关系

- 新增 fmz200 来源仅从原作者当前 `rewrite.snippet` 中提取 7 个已审计的全主机 plain reject 模式，并与既有域名列表去重；不分发或执行其 JavaScript。原作者署名、原地址、历史删除提交和当前替代文件分别保留在 `data/rewrite-audit.json`。这不是对旧 QX 缓存的复现，也不将该来源改标为 MIT。

- [NobyDa/ND-AD README](https://github.com/NobyDa/ND-AD/blob/master/README.md) 明确宣布于 2022/9 停止维护；其中 AD_Block 整合 anti-AD、ConnersHua 等来源，Plus 的具体来源列为未知并提示可能误杀。保留来源不表示该列表仍在更新。
- sve1r 的 antiAD-V4 文件头注明来源为 anti-AD，但它与本集合直接引用的 anti-AD 原作者文件属于不同快照，不能当成内容完全相同的副本。来源未因这项说明自动删改；生成阶段只进行可确认的规则去重。

## 许可证副本校验

下列文件按公开 LICENSE 响应原始字节保存，包含原始换行、版权署名与完整许可正文。SHA-256 对应本次存档：

| 文件 | 上游原始 LICENSE | SHA-256 |
| --- | --- | --- |
| [licenses/sve1r-Rules-For-Quantumult-X-MIT.txt](licenses/sve1r-Rules-For-Quantumult-X-MIT.txt) | [上游原文](https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/LICENSE) | `63814d59a40b61e1090074dac3bbda145d4c0f6a37486b2ef225075880ea2bac` |
| [licenses/limbopro-Adblock4limbo-MIT.txt](licenses/limbopro-Adblock4limbo-MIT.txt) | [上游原文](https://raw.githubusercontent.com/limbopro/Adblock4limbo/main/LICENSE) | `56a1b62e3d3638beecb0bb8f38bfd696afafd885c46b9e7bdc07e59ce6a96b52` |
| [licenses/NobyDa-ND-AD-MIT.txt](licenses/NobyDa-ND-AD-MIT.txt) | [上游原文](https://raw.githubusercontent.com/NobyDa/ND-AD/master/LICENSE) | `c8ed6510961a32a955526d9dc2f577cd448fdc91f744c0788bdd9425418aa64c` |
| [licenses/blackmatrix7-ios_rule_script-GPL-2.0.txt](licenses/blackmatrix7-ios_rule_script-GPL-2.0.txt) | [上游原文](https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/LICENSE) | `8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643` |
| [licenses/privacy-protection-tools-anti-AD-MIT.txt](licenses/privacy-protection-tools-anti-AD-MIT.txt) | [上游原文](https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/LICENSE) | `e38459549a64f11ecf1477053768ef89eb2939a9aa5573f51a31461086357a34` |
