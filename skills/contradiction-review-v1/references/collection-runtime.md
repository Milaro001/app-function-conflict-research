# 采集运行与停止规则

## 一条命令（推荐）

`<私有环境Python> scripts/collect_all.py --app <App> --feature <功能词> --feature <功能词> --competitor <竞品>`

首轮先发起`professional_sources.py`检索人人都是产品经理、优设、UI中国、站酷，再与应用宝、App Store及各社媒并行采集。结束后写`采集汇总.md`；专业任务的原始文章、待补检状态和质量审阅另列，不把正文候选当优质文章。按[专业社区规则](professional-communities.md)实际补检、逐篇选择并重新合并。用户评论的采集、登录复用与停止规则保持独立；验证码路径不自动重试。

语义标注用`scripts/label_batches.py split <corpus/evidence.jsonl> --app <App> --output <标注目录>`，同文只标一次；每批60条，子代理约1分钟一批，可全部并行；`merge`后得到quantification.py与research_gate.py的输入。

下面是分步命令，排查或只补某一步时使用。

首轮原始评论按约2,000条预算（参考1,500—2,500），按完整页/回复链/有界批次自然收尾；`collect_all.py`运行一批并保留实际数量，不在2,000处全局切片，`sampling_plan.py`在筛选后决定补采。有效数量不足时允许超过这个规划区间；不随机删减或制造数量。

## 分步顺序（首轮固定专业检索，商店免登录先于社媒登录处理）

0. **专业社区**：`professional_sources.py collect --app <App> --feature <议题>`。原生检索需要JS或受限时，按运行计划用主机搜索工具补检并取得原页；逐篇审阅后运行`review`。无篇数目标，未选中、未取得与未检索分别留痕。后续仅补单个来源时可显式`--skip-professional`，不要把跳过当完成。

1. **N2 关键词矩阵**：`scripts/keywords.py --app <App> --feature <功能1> --feature <功能2> --competitor <竞品> --output <研究目录>/keywords.json`。不要只用“<App> 功能”一个词；矩阵覆盖中性、问题、诉求、对比四类措辞并按平台调整。
2. **免登录公开来源（几十秒到几分钟）**：
   - 应用宝：`scripts/appbao.py collect --app <App> --since <12个月前ISO时间>`；名称有歧义时先`resolve`再传`--pkg --appid`。应用宝只公开有限的最新列表，近期量少属来源限制。
   - App Store：`scripts/appstore.py collect --app <App>`；最新+最有帮助各最多500条，带版本号，标记client=ios，不计入仅安卓范围。
3. **社媒批量**：先`auth --platform <平台> --interactive --wait 900`让用户一次登录（知乎、小红书、微博、B站可连续完成），之后后台运行：
   `scripts/recent_sample.py discover --platform <平台> --app <App> --keyword-plan keywords.json --pages 3`，
   再`sample --platform <平台> --app <App> --source-run <运行号> --auto-select 30 --since <时间> --comments`。`--auto-select`按“标题/正文含App名、从新到旧”快速选帖，不代替后续语义判定；需要精选时仍可用`--post-ids`。知乎已接入（搜索结果即回答全文+根评论+子评论），本机尚未登录实测。
4. **通道不通时的公开网页补证**：用主机检索找到黑猫投诉、贴吧、论坛、问答等公开页面，**用curl或浏览器取原始页面后摘录原文**（不得用模型摘要当原文），每条写成JSONL后运行`scripts/web_import.py <文件> --app <App>`。多次导入自动累积去重。
5. `scripts/sources.py --app <App>`自动合并该App最新的应用宝、App Store、公开网页导入及全部社媒批次。


## 本地采集

### 登录异常的用户通知顺序（2026-10-29用户确认）

后台遇到验证码、会话过期或无法确认登录态时，保存状态并暂停该平台；先在当前对话汇总具体平台与异常，询问“这些平台的登录态有问题，是否需要重新登录？”。用户同意后再弹出对应专用静音窗口，由用户完成登录或验证；未回复时继续其他可用来源，不自动弹窗或反复重试。若用户本轮已明确要求打开页面或重登，该授权继续有效，不再重复询问。完成后检查登录和实际检索/正文通路，不能仅凭Cookie存在或首页已登录宣布采集恢复。

环境由`scripts/setup.py`一次配好，`setup.py --check`就绪即可跳过`scripts/collect.py doctor`（排查问题时再运行）；运行路径来自同目录的runtime.json。不要使用或导出用户日常浏览器的Cookie。专用浏览器资料由采集脚本保存在本地持久目录，按平台隔离。

小规模实测：`scripts/collect.py pilot --platform bili --app <App> --keyword "<App> 改版"`，然后使用对应platform对其他已启用站点实测。脚本会自动使用配置的虚拟环境Python。默认后台运行，专用浏览器启动前静音，视频/音频元素也预设静音；不改系统音量或日常浏览器。首次需要登录时，用`auth --platform <平台> --interactive --wait 900`打开一次专用静音窗口。`auth --platform bili --wait 0`在后台新进程中验证已有会话，不以Cookie存在冒充登录有效。

正常启动在后台访问平台官网，扫码及验证码由用户处理。后台遇到登录失效或验证即落盘并返回needs_interactive_login/needs_interactive_verification，不自动弹窗或循环探测；由用户选择合适时间再打开交互窗口。日常批次不反复关闭重开，只有显式`--verify-reuse`才做一次重开测试。`--manual-start`须配合`--interactive`，仅用于受限后等待用户恢复正常访问。资料名称读取runtime.json；同一主机不自动切换账号，迁移后由用户在新主机按需登录。

读取输出的manifest.json、pages.jsonl和records.jsonl。每个请求记录分页与新增ID，每条回复保存根评论及可获得的直接回复目标。达到上限不标记完成，缺父节点不补写。访问拒绝时停止该路径，不自动切换身份、代理或绕过验证。进度与正文持续落盘，可在中断后审计。

详情结构修订后可用 `context --platform bili --app <当前App> --source-run <运行目录> --wait 0` 仅补读已有视频标题、简介和声明计数，另存关联记录，不重写原始试验文件。主评论与楼中楼已经返回来源结束，也仍可能引用不可得的回复；如实报告这类缺口，不补造文本或宣称全部上下文完整。

技术门槛按已启用站点验证登录态跨进程复用、搜索与评论翻页、楼中楼及可见回复结束状态。`gate`逐站给出ready/blocked/not_run与阻断项、提示项；某站未通过只暂停该站扩量，不影响已就绪的其他站。通过后仍按语义有效数与来源覆盖分批补采。测试数据与既有应用宝计数分开，历史技术样本不冒充近期研究证据。


多来源合并用`scripts/sources.py`；仅在用户明确暂缓某站时传`--defer <平台>`。它读取应用宝/App Store/公开网页的最新采集（或runtime.json中的既有缓存），并合并同一App各社媒平台全部已结束批次（试采与近期抽样，按来源ID去重）；帖子补读记录按来源运行号关联。输出`corpus/coverage.json`、`corpus/evidence.jsonl`和来源整合说明，同时写入本地SQLite的`corpus_entries_v2`表。缓存导入不是本轮重新抓取；不将论坛的楼层号误作全站唯一ID。

运行路径保存在runtime.json；适配器可用不等于当前账号/页面已验证。先检查最新manifest与实际采集模式；抖音纯后台登录状态尚未确认时保持auth_state_unconfirmed，不反复弹出窗口。

跨平台安装与路径初始化见[portability.md](portability.md)。上面登录复用和采集验证属于原主机实测，不向新平台自动继承通过状态。
