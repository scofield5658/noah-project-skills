# 设计原则与危险信号索引

## 15 条设计原则

英文列按第一版书末的 “Summary of Design Principles” 核对并保留原句；中文列是面向团队评审的理解，不替代英文原文。

| # | English original | 中文理解 | 用于团队评审时可以问 |
| --- | --- | --- | --- |
| 1 | Complexity is incremental: you have to sweat the small stuff. | 复杂性渐进累积，小问题不能长期放任 | 这次改动新增了哪些依赖、模糊性或特殊情况？ |
| 2 | Working code isn’t enough. | 能工作的代码还不够 | 除了当前正确性，未来修改者的成本是否下降？ |
| 3 | Make continual small investments to improve system design. | 持续做小额设计投资，随每次变更改善系统设计 | 本次交付是否同步修正了遇到的局部设计问题？ |
| 4 | Modules should be deep. | 用简单接口封装大量能力（deep module，原书常译“深模块”） | 该接口封装的能力是否明显大于使用接口的成本？ |
| 5 | Interfaces should be designed to make the most common usage as simple as possible. | 接口应让最常见用法尽可能简单 | 主流调用是否不需要了解罕见选项和内部机制？ |
| 6 | It’s more important for a module to have a simple interface than a simple implementation. | 模块的简单接口比简单实现更重要 | 是否为了让实现省事，把复杂性转嫁给所有调用者？ |
| 7 | General-purpose modules are deeper. | 适度通用的模块通常能用更少接口封装更多能力 | 接口是否用基础概念表达，同时仍直接支持当前需求？ |
| 8 | Separate general-purpose and special-purpose code. | 分离通用机制与专用策略 | 哪些是稳定机制，哪些是业务/场景策略，责任方是否清楚？ |
| 9 | Different layers should have different abstractions. | 不同层应提供不同抽象 | 每穿过一层，抽象是否发生了有价值的变化？ |
| 10 | Pull complexity downward. | 由最合适的责任模块集中处理复杂性（pull complexity downward） | 能否由一个模块解决一次，避免多个上层重复承担？ |
| 11 | Define errors (and special cases) out of existence. | 在操作契约允许且保留关键失败信号的前提下，调整语义或表示，把无价值异常纳入正常路径 | 该操作是否本来就在“确保达到目标状态”；若是，目标已达到能否作为正常结果，同时保留真正无法完成和业务冲突的错误？ |
| 12 | Design it twice. | 至少设计两次，比较实质不同的候选 | 关键决策是否比较了两个实质不同的候选？ |
| 13 | Comments should describe things that are not obvious from the code. | 注释应描述无法从代码直接看出的信息 | 文档是否记录契约、意图和理由，而不是复述语句？ |
| 14 | Software should be designed for ease of reading, not ease of writing. | 软件应为阅读者设计，不为书写者省事 | 这个捷径节省的是一次输入，还是整个团队的长期理解成本？ |
| 15 | The increments of software development should be abstractions, not features. | 每次增量应形成职责完整、可以独立理解的模块能力，而非功能碎片 | 当前迭代是否形成了一项职责完整、可以独立理解的模块能力？ |

第二版新增的总括原则是“决定什么重要”：减少必须被全局理解的事项；真正重要的内容放在接口、名称和系统中心，并保持高可见。

## 14 个危险信号

| 危险信号（English original） | 直白理解 | 常见影响 | 优先检查的修正方向 |
| --- | --- | --- | --- |
| 低收益模块（Shallow Module，原书直译“浅模块”） | 接口和文档成本接近甚至超过封装的能力 | 新增概念却没有隐藏多少知识 | 合并能力、提高接口层级、删除无价值包装 |
| 设计知识分散（Information Leakage） | 多个模块分别解释同一格式、规则或状态含义 | 多点修改、隐式依赖 | 指定一个模块统一维护，合并职责或抽出能让调用者不再理解内部细节的模块 |
| 按处理时序拆分（Temporal Decomposition） | 按执行先后拆类或服务，但每步依赖相同知识 | 相同知识在多个阶段重复 | 按知识和能力组织边界 |
| 暴露过多内部细节（Overexposure） | 常用功能也必须理解罕见选项 | 理解负担、误配置 | 默认处理主流技术场景，隔离高级入口；会改变业务结果的默认值仍要有产品需求或权威来源依据 |
| 纯透传层或方法（Pass-Through Method） | 只把相同参数转给下一层，没有提供新抽象 | 接口重复、多点修改 | 删除空层、重分职责或合并模块 |
| Repetition | 非平凡逻辑反复出现 | 多点修改、行为漂移 | 找共同抽象或重组流程到单一位置 |
| 通用机制与特定业务混杂（Special-General Mixture） | 通用机制直接了解特定用例 | 上下层一起变化、复用受限 | 通用机制留低层，专用策略交给合适责任方 |
| 方法相互依赖（Conjoined Methods） | 读懂其中一个方法时，必须同时查看另一个方法的实现 | 方法虽然分开，职责和上下文仍绑在一起 | 合并方法，或提取可以独立理解的完整子任务 |
| Comment Repeats Code | 注释可由相邻代码直接改写 | 噪声、维护成本、文档不可信 | 改写为契约、意图、单位、边界或理由 |
| Implementation Documentation Contaminates Interface | 接口文档解释内部 RPC/结构/算法 | 抽象泄露、模块过浅 | 分离接口和实现文档，重新审视接口 |
| Vague Name | 名称可以指代很多事物 | 错误推断、误用 | 使用精确领域词，区分不同语义 |
| 难以准确命名（Hard to Pick Name） | 无法找到简短准确名称 | 对象职责或数据含义混乱 | 拆分多重含义，重新定义对象 |
| 难以简洁说明（Hard to Describe） | 完整说明必须很长很绕 | 接口复杂、抽象不清 | 简化契约、减少前提和参数、重做分解 |
| 难以直接理解的代码（Nonobvious Code） | 首次阅读无法形成正确判断 | 理解负担、隐藏影响点 | 减少所需信息，遵循约定，补足名称和注释 |

## 第二版需要额外关注的信号

- Unnecessary specialization：每个具体场景、按钮或业务类型都有专用方法和分支。
- 太多事情都要求调用者关心（Too Many Things Matter）：调用者必须掌握大量参数、区分和配置，低收益模块往往由此产生。
- 重要事项被隐藏（Important Things Are Hidden）：真正决定行为的约束没有出现在接口、名称、中心文档或系统结构中。

## 使用边界

危险信号用于触发调查，不直接判定设计错误。评审者发现信号后，应继续比较整体依赖、设计知识封装（information hiding）、接口收益、兼容性和变更风险。任何单一原则走到极端，都可能增加复杂性。

“目标已达到是正常结果”只适用于契约本来就定义为确保目标状态的操作，例如清理临时状态。业务幂等仍要区分同一请求重试、新的重复业务和参数冲突，不能据此把重复提交一律返回成功。
