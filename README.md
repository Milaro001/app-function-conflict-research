# App 功能冲突调研分析 V1.0

给出一个 App 名称，让 AI 整理用户反馈，找出具体的功能问题和相互冲突的需求，再提出有原文依据的改进方案。

结果先放在交互网页里。你可以查看数据、原话和分析，选择继续补采、整理设计任务，或制作原型与验证方案。需要向别人交付时，可以选 PPT、Word、Excel 或可点击的网页原型。

## 这套 Skill 做什么

- 采集或复用已有评论，保留日期、来源链接和回复上下文。
- 去重并筛选功能相关反馈，把情绪表达与具体问题分开看。
- 判断两种要求是否真的不能同时满足。不同设备、不同场景和同方向改进，不会自动算成冲突。
- 沿着用户旅程、前台界面、后台服务、原因假设和替代方案往下分析。
- 用图表展示数量和口径，让每个重要判断能回查原文。
- 用户觉得材料少时，按指定范围继续补采，可把累计原始评论目标扩充到2,000—5,000条或其他指定数量。原始数量与筛后有效数量分别显示。

它不会因为装好了就自动拥有平台账号，也不能保证每个平台都能完整采集。遇到登录、验证码、限制或材料不足时，会记录缺口。数据多不等于代表多数用户，未开展的测试也不会写成已验证。

## 直接下载

打开 [Releases](https://github.com/Milaro001/app-function-conflict-research/releases)，下载 `App功能冲突调研分析_V1.0.0_交付包.zip`。交付包包含主 Skill、固定版本的三个 PPT Skill、安装器、运行说明及示例网页。

只下载 GitHub 自动生成的 Source code 压缩包时，三个 PPT Skill 会由安装器按固定版本从其官方仓库取得。完整交付 ZIP 已附带这些源码，无需再次下载 Skill 源码；Python 依赖和浏览器仍在目标电脑安装。

## 安装

先解压交付包。在解压目录打开终端，选择自己的 Agent：

```bash
python3 install.py --agent codex --mirror china
python3 install.py --agent claude --mirror china
python3 install.py --agent workbuddy --mirror china
```

Windows 可使用 `py install.py --agent workbuddy --mirror china`。只复制文件、不配置环境，可加 `--no-setup`；查看安装位置、不执行安装，可加 `--dry-run`。已有同名主 Skill 不会被静默覆盖，明确更新时使用 `--replace` 保留备份。

安装器会安装独立的 `contradiction-review-v1`，不覆盖 V0.4。默认研究目录为 `~/app-research-workspace-v1.0`。各平台首次登录由使用者自己完成，后续尽量复用该电脑的独立登录资料。Cookie、浏览器用户目录和数据库不在交付包中。

完整参数见 `python3 install.py --help`。没有本地文件、代码执行、浏览器或网络能力的聊天平台，只能使用其能够执行的分析部分。

## 怎么调用

安装后可以说：

> 淘宝，帮我分析用户反馈，看看下一版哪些功能值得改。

也可以指定已有材料和后续动作：

> 只用这份评论分析，不要重新采集。
>
> 这些材料还少，继续补采到累计3,000条原始评论，保留原时间范围。
>
> 把支付异常恢复整理成原型与验证方案，用PPT交付。

## 四种交付怎么做

| 交付 | 实际流程 |
| --- | --- |
| PPT | `consulting-deck-expert` 梳理主线，`ppt-master` 实际制作和导出，`presentation-qa` 检查最终渲染。不会换个后端后仍声称由 PPT Master 制作。 |
| Word | 有相应能力的主机使用 `build-report`、`documents` 与 `validate-data`：先理清论证，再生成可编辑文档，检查依据并逐页核对排版。 |
| Excel | 有相应能力的主机使用 `spreadsheets` 与 `validate-data`：明确每行和每列的含义，核对公式、合计、单位与分母，检查实际显示。 |
| 网页原型 | 展示可操作流程与模拟状态，明确哪些是演示数据，配套提供验证计划。 |

Word、Excel 所列的主机插件没有复制进这个开源交付包。其他 Agent 需要具备相应文档/表格能力；缺少工具时会说明缺失项，不把“有流程说明”当成“工具已安装”。

## 示例与分享

- `docs/index.html`：示例入口。
- `docs/prototype/index.html`：淘宝支付异常恢复的A/B交互原型。
- 完整交付包中的 `docs/`：可离线打开的报告与原型，以及配套PPT。

本地网页可以发给别人离线打开。需要网址时，要发布到静态托管平台。发布成功、访问权限公开、匿名浏览器实际访问通过，是分别检查的状态。示例网页的按钮不会向作者的私人对话自动发送消息。

## 依赖与许可

- 主采集适配器内置固定版本 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)，其许可是 **NON-COMMERCIAL LEARNING LICENSE 1.1**。请按其学习研究用途和采集限制使用。
- PPT Master 来自 [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master)，两个演示辅助 Skill 来自 [hiamberhuang/presentation-agent-skills](https://github.com/hiamberhuang/presentation-agent-skills)，保留其 MIT 许可和原作者信息。
- 固定来源版本见 `DEPENDENCIES.json`，详情见 `THIRD_PARTY_NOTICES.md`。公开仓库不改变第三方许可；本项目整理部分未另行指定统一开源许可。

## 本次验证的范围

发布前检查安装目录隔离、源码语法、核心脚本测试、资源引用与示例网页交互。验证记录见 `VALIDATION.md`。跨 Agent 的格式兼容，不等于每个平台、每套操作系统的登录采集都已经端到端实测。
