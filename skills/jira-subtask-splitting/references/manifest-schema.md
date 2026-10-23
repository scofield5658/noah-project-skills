# 子任务 Manifest 模型

Manifest 是创建前唯一的待确认事实来源。可由用户表格、YAML 或对话信息整理而成；缺失值不得猜测。

```yaml
parents:
  - key: DEMO-100
    item_type_key: Product
    business_name: 库存管理
    module: 管理端
    frontend_change: 是
    performance_risk: 否
    test_advice: 按需求点测试
    children:
      - dimension: frontend
        subject: 库存查询
        scope: 查询面板与前端基础校验
        title_prefixes: ["【前端】", "【自测】"]
        reporter: current_user  # 草案标记，提交前解析为真实用户
        assignee: example-executor  # 用户指定
        issue_type: 前端开发子任务(Subtask)
      - dimension: documentation
        subject: 技术方案设计
        scope: 查询链路、接口边界与异常处理说明
        title_prefixes: ["【文档】"]
        reporter: current_user
        assignee: example-user
        issue_type: 技术方案子任务(Subtask)
        issue_type_key: jsfa
```

## 必填与可选字段

| 字段 | 要求 | 说明 |
| --- | --- | --- |
| `key` | 必填 | 父 Jira key。 |
| `module`、`subject`、`scope` | 创建前必填 | 不能可靠提取时向用户询问。`scope` 用于区分同主题的多个工作项。 |
| `dimension` | 必填 | 如 `frontend`、`backend`、`data`、`documentation`。 |
| `title_prefixes` | 可选 | 保持给定顺序；不从维度自动补充 `【自测】`、`【SQL】`。 |
| `assignee` | 创建前必填 | 用户指定的执行人或已明确的批量分配规则；不默认、不继承。 |
| `reporter` | 创建前必填 | 默认当前认证用户；用户指定时覆盖，记录来源并解析真实用户。 |
| `issue_type` | 创建前必填 | 根据实时类型及层级核验。 |
| `item_type_key` | 父事项核验必填 | 仅 Product、Task、Improvement。 |
| `issue_type_key`、`issue_type_id` | Team 创建前必填 | 根据当前空间层级和类型元数据解析；示例不预填 objectId。 |
| `type_selection_reason` | 使用替代时必填 | 记录首选类型、实际类型及替代原因，按 [子任务类型选择](subtask-types.md) 执行。 |
| `full_title` | 可选 | 提供时优先于标题模板。 |
| `frontend_change`、`performance_risk` | 主任务写入前必填 | 仅允许“是”或“否”。前者可由本次前端工作项建议，后者必须由用户确认。 |

## 标题、描述与幂等性

默认标题为 `{{title_prefixes}}{{business_name}}{{module}}{{subject}}`。新建子任务描述至少包含：

```text
所属模块：{{module}}
任务维度：{{dimension}}
工作主题：{{subject}}
工作范围：{{scope}}
```

完全重复：同一父任务且标题、任务类型、任务维度、主题和范围均一致。标记“已存在”。

疑似重复：同一父任务和任务维度一致，且标题或主题相近，但范围、类型或描述不能明确区分。标记“待用户决定”。

使用替代类型时仍按实际工作维度、主题和范围比对；已有工作相同但历史类型不同的事项也进入疑似重复检查，不能仅因类型不同就新建。`OT_Subtask` 不将 `data` 或 `documentation` 维度改为“其他”。

不同主题或范围的工作项允许同时创建，即使任务维度相同。

## 文档与 Wiki

`documentation` 仅在用户明确列入 Manifest 时创建。关联 Wiki 只能补充草案背景，不自动生成文档工作项，也不自动填充文档范围、标题或指派人。

## 关联缺陷

执行数据中，`parents.children` 保存原生子任务，`bugs` 保存通过关联纳入管理的缺陷，避免同一缺陷关联多个主任务时重复创建。业务预览与结果仍按主任务统一归组，通过 `related_main_keys` 将 Bug 列入对应组的子任务清单：

```yaml
bugs:
  - key: null  # 新建为空；维护已有缺陷时填写已核验 key
    issue_type_key: Bug
    full_title: <用户明确的缺陷标题>
    scope: <用户明确的缺陷范围>
    reporter: current_user
    assignee: <用户指定的执行人>
    test_owner: <用户指定的测试负责人>
    related_main_keys: [<用户指定的主任务key>]
    link_type: 缺陷关联
```

报告人、负责人规则与所有子任务一致；test_owner 和非空 related_main_keys 为缺陷写入前必填。执行时记录解析后的用户、事项及关系类型 ID。字段来源与关联顺序见 [人员与缺陷规则](people-and-bugs.md)。
