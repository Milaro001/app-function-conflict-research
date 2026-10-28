# 分析框架：按产品与证据选用

框架用于回答问题，不能为了画图而补分数。先识别产品类型、核心任务与服务边界：工具／内容产品通常先研究任务完成及需求差异；连接线下履约、客服和服务承诺的App可再用服务质量视角。RICE用于已经提出的候选改法，不替代冲突判定和证据检查。

## SERVQUAL视角

原作者的五维为有形性、可靠性、响应性、保障性、移情性。参考：[Parasuraman、Berry与Zeithaml，1991，Refinement and reassessment of the SERVQUAL scale](https://go.gale.com/ps/i.do?asid=6ecb0a38&id=GALE%7CA12417917&it=r&p=AONE&u=googlescholar&v=2.1)。

没有配对的期望／感知问卷时，做“维度—原文—待查问题”的内容映射，展示材料覆盖量，不生成1—5分质量雷达或缺口评分。数字服务的可用性映射应注明是分析应用，不声称已验证量表效度。参考图若修改了维度，先明确修改口径。

analytics.frameworks.service_quality.annotations逐条对应议题映射候选ID；每项含evidence_id、dimensions（key、逐字anchor、reason）、unmapped_reason、review_status。可跨维度，未能对应时写原因；不能把所有意见硬塞进五维。measurement_status设为not_conducted。图表按同文组去重；0表示没有材料，不表示质量为0。照片配图不作为设施评测证据。

## RICE排期草稿

参考：[Intercom原方法](https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers)。同一目标与周期下，用覆盖量R、单次影响I、估算信心C与团队总投入E比较候选方案。评论样本数不是实际覆盖人数；未知开发成本、影响和信心保持待估，不填造分。

网页工作表可从issues.options读取候选A/B，允许用户填估算，并明确标记为本地草稿。只对四项齐全、取值有效的方案计算R×I×C/E；缺项不排名，E不能为0。改成另一方案后清除旧估算。用户修改的数字不回写研究原文、G2/G3，不代表已验证效果或上线批准。RICE用于讨论排期，不覆盖法定要求、依赖关系或必须修复的故障。
