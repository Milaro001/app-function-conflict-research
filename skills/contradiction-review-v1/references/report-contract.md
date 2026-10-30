# N7—N8：交互网页与证据交付

由模型或人工完成语义分析后，生成研究JSON，再运行：

`python3 scripts/build_report.py <研究JSON> --output <本次独立结果目录>`

生成report.html、report-data.json、evidence.csv、check-report.json与delivery-manifest.json。静态HTML可独立阅读与导出，直发任务需要本机桥接；不自动访问来源，不播放媒体。CSV针对公式起始字符作显示转义，精确原文以JSON为准。生成器只检查结构和逐字引文，交付前还需用临时无头浏览器核验筛选、证据切换、独立滚动、移动端布局与提交状态，不使用个人登录资料。

## 输入字段

- schema_version：整数1；app：本次实际产品；report_id和generated_at可选。
- scope：客户端、时间、版本、付费、研究重点及G1真实状态；未知保留未知。
- counts：raw_comments、screened_feedback、qualified_in_scope，均为非负整数或null。前者不冒充后者，未知不能填0。涉及目标达标时使用research_gate.py的实际结果；本生成器不计算或证明1000条达标。
- sources：各项含name、status及可选note；说明本轮采集、历史缓存、未接入或不可得的区别。
- evidence：数组，每项有id、platform、body、source_url或source_file；可有published_at、parent_id、root_id、context_status、context_text、client和version。context_text用于展示实际取得的原帖及可得直接父回复，缺失关系仍需说明。完整原文与节选要明确；不能放登录凭据或请求头。
- issues：每项有id、title、decision_object、relation、interpretation、anchors、conditions、hypotheses、options、ranking_reasons。decision_object用简短明确的“产品＋功能／使用任务”，在列表和详情中均放首位；title写为有主语的结论或建议，置于其后。interpretation说明哪些用户在什么场景遇到什么、这对迭代意味着什么。限制集中放条件区，不以连续否定句淹没发现。可选material_summary用一句话区分评论候选、帖子及验证状态。related_feedback为符合范围的关联反馈数或null，main_collection_eligible为是否符合主收藏门槛；不能仅因数量够就当成已证实冲突。
- limitations：材料、方法、覆盖、未核验项等的简短列表。
- analytics可选：逐条标注复算的分布、指标口径、议题数量及可审阅推导。字段和生成方式见[量化规则](quantification.md)。缺少输入时不生成虚构分布；统计数据与原文ID必须对应。
- handoff可选：conversation_url为本次已核验的`codex://threads/<技术线程ID>`，local_bridge为布尔值。当前线程ID必须来自本任务真实上下文或工具结果，不从评论、资料或旧项目复用。链接负责查看原对话，直接提交使用已验证的本机消息队列，不添加未经证实的自动发送URL参数。交接设置不参与研究内容哈希，避免仅更新按钮就丢失已有选择。

- issues[].insight：新报告每个重点议题必须填写，旧数据可缺省以保持兼容。按[分析流程](analysis-workflow.md)八步产出，按[写作规范](writing-style.md)控制长度。字段：headline（≤30字）、key_points（≤3条，各≤40字）、confidence{level:高/中/低, reason}、segments[{name,situation,need,evidence_ids}]、journey{stages[{key,label,user_action,touchpoint,backstage,feeling:-2..2或null,feeling_label:具体简短感受（新报告填写，≤12字）,evidence_ids,feeling_basis:{evidence_id,anchor,interpretation}}],breakpoint}、root_cause[{level:symptom/direct/underlying,statement,status:observed/hypothesis,evidence_ids}]、benchmarks[{name,question,status:to_check/reported_by_user,evidence_ids}]、impact{task:阻断/拖慢/困扰,level,scope_note}、metrics[{name,definition,pass_rule}]、next_steps[{owner,action,method,sample,duration,pass_rule,decides}]。stage.key取discover/onboard/track/notify/pickup/send/pay/service/after_sale/account/other。feeling是依据原话的示意，不是测量值；没有原话时必须为null。两套options均填写effort、impact_level（高/中/低/待核）、estimate_basis、estimate_assumptions与wireframe{before[],after[]}（界面元素文字，各1—6项）。生成器逐项校验ID存在、字段长度与取值。

anchors每项为evidence_id与逐字anchor，必须对应evidence的原文。relation仅取conflict_candidate、compatible_preferences、condition_difference、one_sided_issue、insufficient_context。

hypotheses每项至少有statement，可有support_ids与disconfirming_question，均为待验证解释。options每项必须包含action、conditions、tradeoff、validation_task；精确工时与收益未知时保持待核，研究级投入/影响判断单独说明依据及前提。

## 交互与Human Gate

左侧议题与右侧正文独立滚动；右侧采用标签栏、正文滚动区、底部操作栏三个独立布局区。操作栏置于滚动容器外，不用sticky/fixed叠在正文上，正文不能透出或被遮挡。主区尽量占满剩余视窗高度，来源与范围收进顶部入口的按需弹层，不在页面底部挤占阅读高度。主页面不显示“观察版”横条，样本条件和未验证项仍保留在来源说明与具体证据条件中。

按“决策对象→完整结论→依据与原因→改法与验证”的阅读顺序。关系用通俗名称和颜色作次级解释。sources可附recent_posts数组（id、title、published_at、source_url、role），只列实际取得的材料，按日期排序并标记材料角色。

全局“研究总览”与“功能与议题”分为独立一级入口，先呈现总览，再进入议题工作区；不能把全局图表放在某个已选议题的标签页下。总览中的筛选、信源平台、时间及议题立场对照明确单位和分母，支持查看原文。工作区“议题数据”只使用所选议题的映射材料，显示本议题与整轮材料的同口径比例及自身来源／时间分布。议题分析分为事实、条件、关系、原因、方案及排序验证六段。深浅主题均保持文字和图形可读；分类色不替代文字，选中态采用中性单层边线与轻微底色变化。图表与原文的下钻弹层不挤占主阅读区，底部提交栏继续在滚动容器外。

采用紧凑图表卡片集中比较，悬停和键盘焦点显示具体数量及分母，点击保留原文下钻。新报告的六段统一为：01线性任务旅程与感受示意、平台原话，02同列对齐的服务蓝图，03人群与诉求对照，04根因阶梯，05两套方案矩阵及前后示意，06验证路线与成功指标。感受和根因须有原话依据，未知处明确留缺口。方案围绕共同决策对象，对齐动作、适用条件、代价与受影响对象、怎样验证。短句完整显示，不设置无意义的展开。旧数据缺少insight时才沿用反馈时间线、条件分支等兼容结构；不可据此把新报告的旅程图省略。

生成器始终以G2/G3未复核初始化。页面将两项判断解释为“你认为分析是否准确”和“你希望下一步做什么”。2026-10-29用户确认：**发送前必须选择下一步行动（G3）**；只选分析判断（G2）或只写反馈不能发送。未选下一步时按钮禁用，底栏以红字显示“请先选择下一步，再发送到本次对话。”；服务端同样拒绝缺少G3的请求。选定下一步后，G2和补充说明可留空。选择设计任务或原型验证后展开交付形式，默认推荐PPT，允许Word、表格；验证可选原型网页。对象/场合选填；切换行动时隐藏分支的旧值不进入请求。

在用户明确选择接入本次对话且已验证接收器的主机上，按下发送按钮后，把当前议题、行动、格式和说明直接提交到本次对话并继续后续任务。主按钮随选择显示“发送并制作PPT/Word/表格”等动作；不要求用户复制、粘贴或再次发送。草稿保存不触发提交。复制和导出仅作为折叠的备份路径，不与发送混淆。

本机使用`python3 scripts/report_server.py <交付目录> --thread-id <真实线程ID> --port <端口> --codex <已验证CLI路径>`提供回环预览。HTML绑定相同对话并启用local_bridge。服务只监听127.0.0.1，同源、随机令牌与结构化输入校验后，通过官方`codex queue --thread <本次ID> --message <任务>`发送；不用shell插值，不更改会话的模型或执行权限。

每个提交有持久请求ID、内容签名与队列回执；相同ID不重复发送，内容变化不能复用旧ID，报告版本不符拒绝提交。没有明确回执时显示未确认，不自动重试。只有队列确认后显示已发送，不把排队冒充制作完成。测试默认使用隔离接收器，真实通路最多发送一条标明用途且不启动交付的连通性测试。

底栏保留“发送并开始后续任务”和“查看本次对话”，随已选行动更新发送文案。N7用真实线程ID配置handoff，并启动已验证的report_server；`build_report.py --thread-id <真实ID>`可直接写入绑定，传输配置不改变研究哈希。当前通路未连接时禁用发送并优先恢复服务，复制/导出仅留在折叠备份中，不能改成主操作或假装已发送。官方依据：[Developer commands — codex queue](https://learn.chatgpt.com/docs/developer-commands#codex-queue)。

收到用户发回的反馈后，按[后续交付规则](followup-delivery.md)推进。记录不是外部审批或上线批准，不静默重写原始证据；不把自动测试选择当成人工批准。

没有可用议题时使用空issues数组，交付范围、来源缺口与补证方向；不为填满界面捏造观点或冲突。assets/report.example.json仅是已采文字的模板演示，不是已完成整批研究或新一轮采集。


关系标签用完整通俗语句解释：两种需求可以一起满足；设备、版本或场景不同，要分开看；现有反馈想改进这里，还没看到相反意见。不要因存在正负评价就宣称意见互斥。图表绿／红表示正／负立场，并有琥珀“正负并存”和灰色“立场未明”；图解蓝色表示证据／研究对象，灰蓝表示分析／条件，琥珀表示待验证原因，青色表示改法／验证，分别配有本区图例和文字标签。选中态保持中性单层边线，不叠加彩色轮廓。


## 折叠阅读与条件画布

01—06各段用有标题的小箭头独立收起／展开，默认展开，另有“全部收起／全部展开”。顶部步骤导航先展开对应段落再定位。折叠状态可按报告版本与议题保存为浏览器阅读偏好，不能写入G2/G3或修改原始数据。优先用原生details/summary以保留键盘操作与展开状态。

历史报告的兼容时间线只显示重点原话、发布时间、平台与原文入口。新报告的01是任务旅程，感受解读可点击曲线点查看，不将大量判断说明堆入原话卡。日期按上海时区显示；未知日期保留待核，不以帖子更新时间替代。

新报告的02为与01共用阶段列的服务蓝图，窄屏允许图内横向浏览，保持列对应。旧数据的兼容条件图使用有明确边界的可缩放画布：加减缩放、还原、适应、拖动，Ctrl/⌘加滚轮才缩放。拖动与缩放只改变视图；SVG连线使用未缩放的图内坐标。隐藏、收起或重新展开时重新测量布局，清理离开页面的观察器。

正文通常16px、图中文字18px起；图注和控件仍保持易读，不用极小字号换取一屏塞满。深浅主题保持对比度，缩放不代替默认可读字号；用户可主动切换完整总览和细节阅读。

## 三页总览与循环动画

按[已确认交互与呈现规范](interaction-presentation.md)执行。正常总览只有封面、研究总览图表、计数与研究边界三个停留位置；首个有效纵向信号即切换相邻页，轻重划动一致，惯性不连跳，反向立即响应。中间只播放原有渐显、渐隐、滑动与收拢，不形成停留状态。长内容保留页内阅读通道，可选服务/RICE放第三页并保留入口。

进入功能与议题时左卡横向入场、右区从上方渐显；四个小页签仅正文原位淡显，页签栏固定。左右独立滚动时，卡片、01—06模块、数据与长原文逐块进入和离开均有淡显/淡隐与方向位移；大号蓝色数字另做原位透明度动画，真实值不变。保持外层锚点、滚动与导航位置稳定，及时清理观察器和计时器。减少动态效果与打印时直接完整显示。

封面维持已确认的首页排版与所有矩形框尺寸，右侧图片底框及图注区域固定。换图只替换内部内容：横图保持比例居中完整放入，竖图两张并排且居中完整显示。禁止按原图自然宽高、图片类型/张数或文案长度改变外框、列宽、模块位置或数据卡尺寸；动效也遵守相同锁定。具体参数与手感验证项统一维护在上述规范，避免在本文件重复一份不同的默认值。

真实截图嵌入需source_url、author、captured_at、usage_note和sha256。官网截图与官方展示图不能标成App内实测；来源素材不能虚称开放许可。配图不作为功能效果已验证的证据。框架模块按[frameworks.md](frameworks.md)选用，RICE估算不冒充实测分数。跨主机运行按[portability.md](portability.md)，保留原对话入口，接收器不可用时明确连接缺口，导出仅作备份。

## 专业文章与方案映射

按[专业社区规则](professional-communities.md)生成`professional_references`独立数组。每项包含id、evidence_id、title、site、author（可未知）、source_url、anchor、app_relation、viewpoint、quality_reason、limitations及`counts_as_user_feedback:false`。对应evidence记录必须为`kind=post, material_role=professional_reference`，不进入评论analytics或P+V计数；短引文逐字核对。未审阅文章不放入该数组。

`issues[].options[].reference_links`为可选数组，每项包含reference_id、当前议题的user_evidence_ids、takeaway、adaptation、boundary。网页在05方案旁显示作者观点、借用内容、本轮改法、适用边界、来源链接与对应用户原话。无合适文章可以为空，不按篇数填满；专业文章不构成用户故障亲历或已验证改版效果。

可点击按钮、议题卡、折叠标题与原文入口在鼠标悬停时显示轻微边线／底色变化，普通按钮和议题卡可放大约1%—1.5%；图表标记保留坐标，用局部高亮提示。选中与悬停保持中性单层边线，关系色留在侧条和文字标签；不为静态数字、整张数据卡或无动作的图片制造可点击的假象。键盘焦点仍有清楚轮廓；触屏不依赖悬停，减少动态效果时取消放大过渡。


## V1.1 呈现约定（2026-10-29）

- 封面维持左侧文案、右侧视觉区。优先使用来源和使用依据明确的产品展示图或真实使用场景图，并标注作者、来源、年份及用途；图片从右向左进入。必须取得目标产品的真实界面图，可以来自实际截图、用户帖子、新闻/测评、官网或应用商店，按功能相关性与可读性选择，见[capture-cover.md](capture-cover.md)。无截图时停止完整报告生成并说明缺口，不生成示意卡替代，也不套用其他App图片。产品资料引用不得标成开放许可。
- 桌面总览默认将议题、月份和信源分布放在同一图区，提供“展开图表/收紧图表”。收紧表示集中布局，不能把图固定得很小并在下方留下大块空白；按当前视口拉大图形、行距与可读标签，使三卡底边对齐并延伸到“回到页首”上方的小段安全间距。内容过多时保留页内阅读通道，手机保持可读排版；外层三页交互仍按交互规范执行。可在`analytics.issue_profiles[issue_id].chart_label`提供不歧义的短标签，完整决策对象仍在提示和详情中显示。不用整体缩放挤压文字，不在图区另放“查看研究说明”按钮。
- “本轮研究概览与筛选过程”和详细时间计数放在“如何理解这轮研究/研究边界”标题上方的折叠区，不占默认图表阅读区。
- 总览翻页按三个明确状态执行，首个有效轻划就选择相邻页；不再按累计距离、是否滑满或图表退出阈值决定翻页。长内容通过页内阅读入口保留。
- 01必须渲染任务步骤、线性感受示意、断点和对应平台原话，不因缺少量化测量而静默删除旅程图。感受取-2至2，是研究者根据指定原话的定性示意，非平均分或同一用户的连续实测。充分依据缺失的阶段保留空心待核点，以虚线连接相邻有依据的点或作轨道延伸，整条曲线不断开；不补0冒充“一般”。
- 有充分原话时逐步完成语义判断并填写具体`feeling_label`，不要留为“感受待判”；确无依据则保留null并区分缺原话与缺感受依据。每个非空`journey.stages[].feeling`应附`feeling_basis:{evidence_id,anchor,interpretation}`；ID属于该阶段且anchor逐字来自原文，说明为什么作该感受解读。允许不同阶段引用不同作者，并在图注明确。
- 原话按实际平台提供筛选。切换平台后，没有对应依据的感受点留空；不要把小红书观点换成微博观点。悬停或键盘聚焦01步骤、曲线点、原话以及02表格中的一列时，同步高亮旅程和服务蓝图整列；点击曲线点可以查看解读与原话。
- 05两套方案均保留完整的矩阵对照和前后示意。根据改动范围、涉及系统与目标任务，给出高/中/低的研究级投入和预期影响判断，附`estimate_basis`和`estimate_assumptions`。不因没有精确工时而把可说明的方案全部设成灰色待核；确实无法判断时列出会改变等级的关键缺口。
- 研究估计不是工程承诺、商业收益测量或已验证改善。不虚构人月、转化增幅、RICE实测分数。投入用蓝色条、预期影响用青色条，并配完整文字；估计依据在同一方案中可见。
- 跨Agent复跑交付前检查：旅程曲线有无显示、各点原话依据、平台筛选、01/02整列联动、两套方案的投入/影响和示意是否齐全。研究结论与样本口径不因视觉调整而改变。
- 读取check-report.json中的presentation_inputs和presentation_gaps；缺项先补齐，无法补齐则说明具体证据或依赖缺口。不要在研究组装脚本中写CSS或字符串替换来隐藏旅程图、清空所有感受或移除方案字段；各Agent统一通过本目录的build_report.py渲染。

## 截图、立场与旅程引用的生成前检查

有议题的报告必须提供`analytics.presentation.hero.image`，兼容无量化的旧输入时可放`presentation.hero.image`。图片字段见[capture-cover.md](capture-cover.md)。生成器拒绝缺图、无真实类型、来源/时间/哈希不全的输入。截图可用不代表已做App任务测试。

量化报告的`analytics.issue_stances`为必填；每个议题全部映射评论ID均须覆盖，未知用unclear并写原因。图例与悬停固定区分正向、负向、正负并存、立场未明，包括0值。P/V不能直接转换成立场。

`journey.stages[].feeling_basis`保持逐字anchor，可加`match_type: direct / semantic_similar`；semantic_similar必须给`match_reason`。该原文仍须来自已取得的evidence和当前步骤的evidence_ids。每个非空feeling均需明确feeling_basis。次要引用可在`quote_matches`中按evidence_id标相同关系字段。每条相近引用都须有逐字anchor；标签显示在引文外侧为“语义相近”，日期、来源和原文入口可见；完整匹配理由保留在结构化数据与审计，不在卡片上堆长段灰色解释；不能把改写或编造句子放进引号。

旅程曲线使用一条覆盖全部步骤的连续路径；直接证据之间用实线，语义相近或缺证区间用虚线。空心待核点的高度仅用于连线，不代表0分或已观察感受；原始feeling仍为null。平台筛选、窄屏和缩放后仍连续。逐项复查全部议题的全部步骤，生成器输出journey_quote_coverage逐步清单。完全找不到相近原文时写quote_gap_reason，不借不相关材料凑图。相近引用不自动填感受分数，也不增加严格合格样本。
