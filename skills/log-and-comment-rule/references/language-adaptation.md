# Java、Python、Go、Node.js 语言适配

按目标项目的语言版本、日志库和文档检查规则选用本页对应部分。以下均为独立编写的虚构文档处理示例，不要求引入新框架或采用示例中的分层。

## 共同边界

- 优先使用项目封装或注入的 logger、日志收集器或等价入口。下列库 API 仅在项目实际使用该接口时适用，不绕过封装；测试、生产的启用范围与级别等策略按用户要求和项目现状处理。
- 只补诊断上下文和说明，不新增捕获、重试、返回、异常包装或事务操作；沿用现有错误处理位置。
- 同一失败由承担诊断职责的位置记录，避免入口、业务层、适配层各打一份相同堆栈。不要为去重删除仍有独立诊断价值的记录。
- 只取必要且允许记录的标识和摘要；错误对象、异常消息与堆栈也可能包含敏感数据，沿用已有脱敏机制，不直接输出凭据或完整载荷。
- 不为构造日志执行额外查询、消费迭代器、调用有副作用的格式化方法或展开大集合；耗时计算沿用现有时钟约定。
- 文档语言跟随项目；本页中文示例不要求英文项目改用中文。公开符号或文档检查要求的覆盖优先于简单方法豁免。

## API 和文档格式速查

| 对象 | Java | Python | Go | Node.js（JS/TS） |
| --- | --- | --- | --- | --- |
| 职责载体 | 类、接口、方法 | 模块、类、函数、方法 | package、类型、函数、方法 | 模块、函数、中间件、类、对象契约 |
| 原生文档 | Javadoc | docstring；字段沿用属性文档或模型描述 | 声明前的 doc comment，通常以符号名起句 | JS 用 JSDoc；TS 沿用项目文档格式 |
| 日志参数 | 按既有日志库；SLF4J 示例用 `{}` | 标准 `logging` 消息参数用 `%s` 等占位符 | `slog` 使用消息和键值属性，其他库沿用各自 API | 核对项目封装的参数及 formatter / serializer，不假设占位符或 metadata 通用 |
| 失败证据 | 保留 Throwable 参数和上下文 | 在已有异常处理位置保留异常信息 | 记录原始 `error` 和上下文；不假设有堆栈 | 按已有安全序列化机制保留必要错误信息，验证最终输出 |

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

优先复用项目已有 logger、适配器或日志收集器来记录关键上下文与错误；不要为套用以下示例绕过项目入口。自定义接口不一定支持标准库的占位符或 `exc_info`，先核对封装契约。

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

沿用项目封装或注入的 logger、日志收集器及已有 context，不另起标准库日志实例或用 `fmt.Println` 绕过采集入口。项目已经使用标准库 `log/slog` 接口时，可以在已有错误处理位置记录：

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

## Node.js（JavaScript / TypeScript）

### 日志调用与输出

先阅读项目 logger 封装和实际 formatter / serializer，核实消息、结构化字段及错误参数的位置。Winston、Pino、自定义收集器的调用约定不能互换；不照搬 Java `{}` 或异常尾参数。Winston 的 `%s` 等插值需要相应格式化配置，也不应为套用示例修改共享配置。

- 调用传入了 metadata，不代表格式化结果保留了这些字段；通过已有支持的通道记录安全上下文，并验证最终输出。若必须修改共享 logger 才能满足要求，先报告影响，不顺手扩大范围。
- 不只记录 `err.message`；按已有安全错误序列化机制保留必要的错误类型、错误码和堆栈（存在时）。直接 `JSON.stringify(err)` 或 `{ ...err }` 不能保证保留 `Error` 的消息和堆栈；抛出值也可能不是 `Error`，不强行读取不存在的属性或输出未知对象全文。
- 不完整输出请求上下文、headers、客户端配置或响应载荷；错误文本也需遵守脱敏约定。使用已有白名单或安全序列化能力，不为日志遍历循环对象、展开大对象或消费响应流。

### 异步与请求边界

- 在既有错误处理位置补充记录，保留 `throw`、Promise 的 resolve / reject、回调错误参数及中间件传播语义，不改变 `await next()` 的顺序或调用次数。
- 不为补日志添加全局 `uncaughtException` / `unhandledRejection` 监听、异常恢复、重试或新的吞错分支；缺少错误处理边界时列出缺口，另行处理行为变更。
- 复用已有请求或任务关联标识，不引入新的上下文传播框架。已有访问日志或外部调用摘要时，只补其缺失且有独立价值的信息。
- 按现有客户端契约区分错误响应、无响应、超时、取消及业务失败；无响应时仍能记录诊断，不盲目读取 `response.status`，也不将 HTTP 成功等同于业务成功。
- 轮询、事件消费、WebSocket 优先记录生命周期、关键异常和已有汇总点，避免逐轮或逐消息成功日志；正常空轮询、预期断开不一律视为故障。纯对象转换函数默认不加日志，不为减少日志改变调度、重连或采样策略。

### 函数与模型文档

JS 沿用 JSDoc，说明参数、Promise 的解析结果、失败表达方式和副作用；不把返回失败结果的函数写成必定 reject。TS 沿用项目已有文档格式，说明语义而不机械重复类型签名。模块、函数和中间件均按职责补说明，不要求创建类或切换 CommonJS / ES Modules。

普通对象、JSDoc `@typedef` / `@property`、TS `interface` / `type` 和 ORM 模型都按实际职责适用持久化或外部边界字段规则。已有等价描述时不重复，只有类型或映射名称时仍需核实语义；未知单位、范围和格式列为待查证。

以下为虚构的外部文档查询契约，约定游标是不透明字符串、页大小单位是文档条数：

```javascript
/**
 * 外部文档查询条件。
 * @typedef {Object} DocumentQuery
 * @property {string} cursor - 下游返回的不透明游标，原样传递。
 * @property {number} limit - 每页最多返回的文档条数。
 */
```

这些注释不要求运行时依赖或语言升级。日志示例应以目标项目的实际库版本与封装契约为准，不为适配本技能新增框架。

## 其他语言

先识别实际职责、项目日志采集入口与原生文档机制，再映射共同原则。没有项目资料或不熟悉 API 时，列出待核实点，不猜测占位符、错误参数或文档语法，也不引入 Java 式分层。

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
- [Node.js：错误传播与 Error](https://nodejs.org/api/errors.html)
- [Winston：日志格式与字符串插值](https://github.com/winstonjs/winston#formats)
- [JSDoc：Promise 返回值](https://jsdoc.app/tags-returns)
- [JSDoc：对象属性说明](https://jsdoc.app/tags-property)
- [TypeScript：JSDoc 支持](https://www.typescriptlang.org/docs/handbook/jsdoc-supported-types.html)
