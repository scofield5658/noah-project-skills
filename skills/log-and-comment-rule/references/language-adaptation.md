# Java、Python、Go 语言适配

按目标项目的语言版本、日志库和文档检查规则选用本页对应部分。以下均为独立编写的虚构文档处理示例，不要求引入新框架或采用示例中的分层。

## 共同边界

- 只补诊断上下文和说明，不新增捕获、重试、返回、异常包装或事务操作；沿用现有错误处理位置。
- 同一失败由承担诊断职责的位置记录，避免入口、业务层、适配层各打一份相同堆栈。不要为去重删除仍有独立诊断价值的记录。
- 只取必要且允许记录的标识和摘要；错误对象、异常消息与堆栈也可能包含敏感数据，沿用已有脱敏机制，不直接输出凭据或完整载荷。
- 不为构造日志执行额外查询、消费迭代器、调用有副作用的格式化方法或展开大集合；耗时计算沿用现有时钟约定。
- 文档语言跟随项目；本页中文示例不要求英文项目改用中文。公开符号或文档检查要求的覆盖优先于简单方法豁免。

## API 和文档格式速查

| 对象 | Java | Python | Go |
| --- | --- | --- | --- |
| 职责载体 | 类、接口、方法 | 模块、类、函数、方法 | package、类型、函数、方法 |
| 原生文档 | Javadoc | docstring；字段沿用属性文档或模型描述 | 声明前的 doc comment，通常以符号名起句 |
| 日志参数 | 按既有日志库；SLF4J 示例用 `{}` | 标准 `logging` 消息参数用 `%s` 等占位符 | `slog` 使用消息和键值属性，其他库沿用各自 API |
| 失败证据 | 保留 Throwable 参数和上下文 | 在已有异常处理位置保留异常信息 | 记录原始 `error` 和上下文；不假设有堆栈 |

该表只是映射，不表示 Python 必须有 Service 类、Go 必须有 Controller，或所有语言都要新增日志级别。

## Java

沿用已有日志门面。使用 SLF4J 时，将异常作为最后一个参数传入，不把它当作额外占位值，也不要只输出 `getMessage()` 而丢失异常信息。

```java
logger.error("文档复制失败, documentId={}", documentId, e);
```

使用 Javadoc 说明职责、契约和字段语义；已有等价注解说明时不重复。Java record 的组件说明可按项目文档工具约定放在类型 Javadoc 的 `@param` 中，不要求改变 DTO 类型。

```java
/**
 * 外部文档集合查询条件。
 *
 * @param collectionIds 文档集合标识，多个值的传参形式由下游契约确定
 */
public record DocumentCollectionQueryRequest(String collectionIds) {
}
```

版本条件：该 record 示例要求 Java 16+；旧版 Java 使用已有类模型，无需为注释升级。SLF4J 的异常尾参数示例要求 1.6+；使用其他日志 API 时先核对其签名。

## Python

使用标准 `logging` 时，将格式串和参数分开传入；不要照搬 Java `{}`。在已有 `except` 内使用 `logger.exception(...)`，或 `logger.error(..., exc_info=True)`。在异常处理上下文之外，不把 `exc_info=True` 当作仍能自动找回原异常；如需记录已保存的异常，按项目支持的 API 显式传入异常信息。

以下语句放在原有异常处理位置，示例不要求新增 `try/except` 或改变原有 `raise`：

```python
logger.error("文档复制失败, document_id=%s", document_id, exc_info=True)
```

类型和函数说明使用 docstring，先写职责，再按项目既有 Google、NumPy、Sphinx 等风格说明参数、结果、异常或副作用。不要新引入文档格式依赖；不为描述已有类型注解而机械重复类型。

```python
from dataclasses import dataclass


@dataclass
class DocumentCopyRecord:
    """保存文档副本与来源的关联。

    Attributes:
        source_document_id: 源文档ID。
        copied_document_id: 副本文档ID。
    """

    source_document_id: str
    copied_document_id: str
```

函数型服务按函数职责补说明；外部请求和响应的字段口径分别核实。ORM 或验证模型已有等价字段描述时可复用，不依赖特定第三方包。上述 dataclass 示例适用于 Python 3.7+，不构成安装要求。

## Go

沿用现有 logger。项目已经使用标准库 `log/slog` 时，可以在已有错误处理位置记录：

```go
logger.ErrorContext(ctx, "文档复制失败", "document_id", documentID, "error", err)
```

不要把 `document_id={}` 当作 `slog` 的模板；键值属性成对传入。标准 `log` 没有 `Warn` / `Error` 等级方法，不能为套用本技能而调用不存在的方法或升级日志框架。也不要求原本无 context 的函数新增 context 参数。

保留原有错误返回与包装方式。Go 的 `error` 不保证包含堆栈；堆栈采集沿用已有机制，不为补日志更换错误类型。

导出符号使用其声明前紧邻的 doc comment，通常以符号名开头；不要使用 Java 的 `@param` 或 Python docstring。结构体 tag 只描述映射时，不能代替字段业务说明。

```go
// DocumentCopyRecord 保存文档副本与来源的关联。
type DocumentCopyRecord struct {
    // SourceDocumentID 表示源文档ID。
    SourceDocumentID string `json:"source_document_id"`
    // CopiedDocumentID 表示副本文档ID。
    CopiedDocumentID string `json:"copied_document_id"`
}
```

函数文档说明返回结果及错误条件，不把错误恢复策略写成实现并不存在的承诺。注释与格式遵守现有 `gofmt` 和项目检查约定。`log/slog` 示例要求 Go 1.21+；较旧版本保留现有日志库。

## 其他语言

先识别实际职责与原生日志、文档机制，再映射共同原则。没有项目资料或不熟悉 API 时，列出待核实点，不猜测占位符、错误参数或文档语法，也不引入 Java 式分层。

## 公开技术依据

以下链接用于核实 API 和文档约定；本页说明和案例独立编写，不纳入第三方文档原文或改变其许可。

- [SLF4J FAQ：参数化日志与异常参数](https://www.slf4j.org/faq.html)
- [Java 语言规范：record 类](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10)
- [Python logging：消息参数与异常信息](https://docs.python.org/3/library/logging.html)
- [PEP 257：docstring 约定](https://peps.python.org/pep-0257/)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Go 文档注释](https://go.dev/doc/comment)
- [Go log/slog](https://pkg.go.dev/log/slog)
- [Go 1.21 发布说明：log/slog](https://go.dev/doc/go1.21#log/slog)
