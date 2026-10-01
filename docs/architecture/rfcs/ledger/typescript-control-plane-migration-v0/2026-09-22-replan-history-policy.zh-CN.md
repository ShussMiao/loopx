# Replan 历史决策归属

目标来源为总纲 #4574 与 T3 消费侧 TS 迁移。原有 Python 历史扫描分别处理重试、
ACK、中性记账及 agent 归属，规则已经分叉。本次统一到一次 typed history
projection（inline 或 snapshot 传输），并在 TS 内直接复用 Todo resume planner。
Python 保留历史解码、指纹及 obligation 呈现；删除被替代的触发扫描和重复词表。

基线 `709734cd6` 上独立编写的四个反例失败：周期复盘重复累计重试、监控重复
累计重试、ACK 未截断进展停滞、记账打断同质进展。新实现修复这些问题，保持
阈值、优先级和 obligation 标识。280 行多 agent 交错 fixture 与边界负例验证
先归属后 ACK、重试、无效身份、输入拒绝及不修改源数据。File/SQLite 消费侧测试
使用真实持久化 provider，删除展示文件后读取状态并执行 quota CLI。

本机只读演练覆盖 345 条活动 Todo、600 条历史记录和五个 agent：五个历史投影
与基线一致，隔离 File/SQLite 读后核对及公开 quota CLI 通过，活动源未修改。
该证据仅限活动读模型，不证明完整 Goal 晋升。独立的完整捕获因归档依赖缺少或
不兼容的 role/task-class 事实而拒绝；这个迁移阻塞保留，没有绕过门禁或改写活动状态。

本次闭合历史触发决策族，不代表全部 T3 或默认切换。进展指纹解码、obligation
组装、frontier 结算及完整捕获资格仍有各自归属。没有加入模型观察器、provider
切换、前端配置项或可选 capability。

## 长历史传输修复

此前 600 行演练不足以证明长期运行的 Goal。即使去掉正文，所有紧凑事实仍随历史
增长而堆积在一次 RPC 中，导致 `refresh-state` 在写回前失败。12,000 次重试的
独立反例在旧边界失败；重试洪流之前的证据仍必须参与决策。

归属沿用内置 work-item replan owner，不新增 capability、provider、store 或可选
激活。Python codec 只按序列化字节数选择传输方式。本地 IO 适配器检查绝对路径、
同用户私有普通文件、精确长度和 SHA-256，再调用不变的 TS reducer。小请求保留
原方法，大请求改传紧凑快照引用。临时文件跨 runtime 重试保留，正常成功或失败后
清理；进程骤停可能遗留 OS 临时文件，但它没有回执/权限，也不会被当成 canonical
state 重用。既有同 UID runtime 是信任边界，不是远端上传服务或新增权限隔离。

验收覆盖超限后的历史证据、四种 operation 的 inline/snapshot 一致性、ACK/peer/
重试语义、摘要/长度/缺失/symlink/输入拒绝、私有文件清理，以及真实 CLI 的预览、
写回、重放和一次 quota 扣记。既有历史字节不变，返回结果、trigger identity 及
2 MiB RPC 上限不变。受影响入口是 CLI；前端和 Lark 通过既有入口消费不变的结果
及错误，因此无需新设置或展示协议。

本次只关闭已复现的传输故障，不代表全部规模化完成。编码、解析和求值仍有
O(history) 内存/时间成本。后续 S7/R7 容量切片应测量 bridge 字节、峰值内存和
p95 结算时间，再以完整历史为 oracle 验收 checkpoint/cursor 归约，覆盖较旧 ACK、
缺失归属和 Turn 去重。不能为使结算成功而归档/截断历史或提高阈值。
