#!/usr/bin/env python3
"""检查 Markdown 前端技术方案中的常见遗漏。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    priority: str
    line: int | None
    message: str


# 解析模板得到 canonical 标题顺序，避免与 `assets/frontend-technical-solution-template.md` 双份硬编码漂移。
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "frontend-technical-solution-template.md"

_TEMPLATE_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
_FENCE_OPEN_RE = re.compile(r"^\s*```")


def _load_canonical_heading_order(template_path: Path) -> list[str]:
    """按出现顺序从模板中提取 ##/###/#### 标题；忽略代码块内容与重复行。"""
    if not template_path.exists():
        raise SystemExit(
            f"错误：模板文件不存在：{template_path}；"
            "脚本需要读取模板以派生标题顺序，请确认 skill 目录完整。"
        )
    text = template_path.read_text(encoding="utf-8")
    headings: list[str] = []
    seen: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        if _FENCE_OPEN_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _TEMPLATE_HEADING_RE.match(line)
        if not match:
            continue
        heading = f"{match.group(1)} {match.group(2)}"
        if heading in seen:
            continue
        seen.add(heading)
        headings.append(heading)
    if not headings:
        raise SystemExit(f"错误：模板内未解析到任何 ##/###/#### 标题：{template_path}")
    return headings


CANONICAL_HEADING_ORDER = _load_canonical_heading_order(TEMPLATE_PATH)

# 编辑决策（不在模板里，故仍以显式集合维护）：
# - OPTIONAL_BUT_EXPECTED_SET：模板中的可选节，缺失只报 P2
# - NON_REQUIRED_STRUCTURAL：模板中仅作容器或通过关键字校验的标题，不单独按"必需章节"检查
# - P0_HEADINGS：模板中必填章节里 P0 的子集
OPTIONAL_BUT_EXPECTED_SET = {
    "### 4.3 监控、埋点与兼容性（如适用）",
    "### B. 评审记录",
    "### C. 参考资料",
}

NON_REQUIRED_STRUCTURAL = {
    "## 附录",
    # 5.2 验收用例下的三个子分组仅作组织分类，由关键字校验（前置条件/操作步骤/预期结果等）把关，不单独强校验其标题存在性。
    "#### 交互联动场景",
    "#### 前后端通信与契约场景",
    "#### 工具函数 / translator 场景（如适用）",
    # 附录 D 下的两个表格标题通过关键字校验（AI_IMPLEMENTATION_RULES）把关。
    "#### D.1 AI 实施原则",
    "#### D.2 实施步骤与验证闭环",
}

P0_HEADINGS = {
    "### 1.1 所属系统",
    "### 1.2 所属功能入口",
    "### 2.1 改动范围",
    "### 2.2 牵涉范围",
    "### 2.3 复用评估与新增实现边界",
    "### 3.3 改动内容",
    "### 3.4 字段清洗、转换与前后端契约对齐（如适用）",
    "### 5.1 验收方式",
    "### 5.2 验收用例",
}

_CANONICAL_SET = set(CANONICAL_HEADING_ORDER)
for _label, _items in (
    ("OPTIONAL_BUT_EXPECTED_SET", OPTIONAL_BUT_EXPECTED_SET),
    ("NON_REQUIRED_STRUCTURAL", NON_REQUIRED_STRUCTURAL),
    ("P0_HEADINGS", P0_HEADINGS),
):
    _missing = sorted(h for h in _items if h not in _CANONICAL_SET)
    if _missing:
        raise SystemExit(
            f"错误：{_label} 中存在模板里不存在的标题：{_missing}。"
            "模板已变更，请同步更新 scripts/audit_frontend_solution.py 的分类集合。"
        )

REQUIRED_HEADINGS = [
    heading
    for heading in CANONICAL_HEADING_ORDER
    if heading not in OPTIONAL_BUT_EXPECTED_SET and heading not in NON_REQUIRED_STRUCTURAL
]

OPTIONAL_BUT_EXPECTED = [
    heading for heading in CANONICAL_HEADING_ORDER if heading in OPTIONAL_BUT_EXPECTED_SET
]

AI_IMPLEMENTATION_RULES = [
    ("显式假设与追问", "缺少 AI 实施原则：显式假设与追问"),
    ("最小可行实现", "缺少 AI 实施原则：最小可行实现"),
    ("变更可追溯", "缺少 AI 实施原则：变更可追溯"),
    ("外科手术式实施", "缺少 AI 实施原则：外科手术式实施"),
    ("每步带验证", "缺少 AI 实施原则：每步带验证"),
    ("先复现后修复", "缺少 AI 实施原则：先复现后修复"),
    ("AI 实施原则", "缺少附录 D 表格：AI 实施原则"),
    ("实施步骤与验证闭环", "缺少附录 D 表格：实施步骤与验证闭环"),
]

PLACEHOLDER_RE = re.compile(
    r"\[(?:填写|YYYY|JIRA|链接地址|链接|姓名|日期|人员列表|路径|说明|输入|输出|回答|需求|风险|步骤|结果|字段名?|如：|TODO|待补充|待确认|taskTopic|xxx)[^\]]*\]",
    re.IGNORECASE,
)
UNRESOLVED_RE = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待补充|待确认|待定|未确认|\?\?|xxx", re.IGNORECASE)
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
ENGLISH_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z-]{2,}\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TECHNICAL_WORDS = {
    "ACK",
    "API",
    "APM",
    "CLI",
    "DTO",
    "HTTP",
    "ID",
    "JIRA",
    "JSON",
    "KEY",
    "MERMAID",
    "MCP",
    "NODE",
    "NPM",
    "NPS",
    "PLAYWRIGHT",
    "PWA",
    "REACT",
    "SDK",
    "SQL",
    "TAB",
    "TRACEID",
    "TS",
    "TYPE",
    "UFORM",
    "UI",
    "URL",
    "UX",
    "VITEST",
}

SCOPE_BUCKET_GROUPS = [
    ["业务布局组件", "布局组件", "页面布局组件", "业务容器组件"],
    ["业务专用组件", "业务定制组件", "页面专用组件"],
    ["业务通用组件", "业务共享组件", "共享业务组件"],
    ["通用 UI 组件", "通用UI组件", "基础 UI 组件", "基础UI组件", "公共 UI 组件", "公共UI组件"],
    ["通用工具函数", "公共工具函数", "工具函数", "通用函数"],
]
FIELD_CONTRACT_KEYWORD_GROUPS = [
    ["字段来源", "来源字段", "字段来源说明"],
    ["转换规则", "字段转换", "清洗规则", "映射规则"],
    ["提供方", "供数方", "发布方", "生产方"],
    ["消费方", "用数方", "订阅方", "消费端"],
    ["类型定义", "类型约束", "类型声明"],
    ["请求字段", "入参字段", "请求参数"],
    ["响应字段", "出参字段", "返回字段", "响应参数"],
]
ACCEPTANCE_METHOD_KEYWORD_GROUPS = [
    ["chrome-devtools", "chrome devtools", "chromedevtools", "浏览器调试", "浏览器联调", "浏览器验收"],
    ["自动化", "自动化脚本", "自动化测试", "自动回归"],
    ["脚本", "测试脚本"],
    ["单元测试", "单测"],
    ["冒烟", "手工冒烟", "冒烟测试"],
    ["playwright"],
]
ACCEPTANCE_CASE_KEYWORD_GROUPS = [
    ["前置条件", "准备条件"],
    ["操作步骤", "执行步骤", "操作流程"],
    ["预期结果", "预期表现", "期望结果"],
    ["校验重点", "检查重点", "检查项"],
    ["UI-", "UI_"],
    ["API-", "API_"],
    ["UT-", "UT_"],
]
DESIGN_TOOL_MODEL_LABEL = "常规设计使用工具和模型"
REVIEW_TOOL_MODEL_KEYWORDS = ["评审工具", "评审模型"]


def strip_fenced_blocks(lines: list[str]) -> list[tuple[int, str]]:
    visible: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            visible.append((index, line.rstrip("\n")))
    return visible


def has_heading(visible: list[tuple[int, str]], heading: str) -> bool:
    return any(line.startswith(heading) for _, line in visible)


def first_heading_line(visible: list[tuple[int, str]], heading: str) -> int | None:
    for line_number, line in visible:
        if line.startswith(heading):
            return line_number
    return None


def heading_order_violations(visible: list[tuple[int, str]]) -> list[Finding]:
    positions: dict[str, int] = {}
    for heading in CANONICAL_HEADING_ORDER:
        line_no = first_heading_line(visible, heading)
        if line_no is not None:
            positions[heading] = line_no

    expected = [h for h in CANONICAL_HEADING_ORDER if h in positions]

    seen_heading: set[str] = set()
    found: list[tuple[int, str]] = []
    for line_no, line in visible:
        candidates = [h for h in CANONICAL_HEADING_ORDER if h not in seen_heading and line.startswith(h)]
        if not candidates:
            continue
        heading = max(candidates, key=len)
        found.append((line_no, heading))
        seen_heading.add(heading)

    found_headings = [h for _, h in found]
    if found_headings == expected:
        return []

    for i, (got, want) in enumerate(zip(found_headings, expected)):
        if got != want:
            return [
                Finding(
                    "P1",
                    found[i][0],
                    f"章节顺序与模板不一致：第 {i + 1} 个结构标题为「{got}」，按模板此处应为「{want}」。请按 `assets/frontend-technical-solution-template.md` 自上而下调整标题顺序。",
                )
            ]

    if len(found_headings) != len(expected):
        return [
            Finding(
                "P1",
                None,
                "章节顺序与模板不一致：结构标题集合与模板不一致或存在重复/歧义标题，请对照 `assets/frontend-technical-solution-template.md` 核对。",
            )
        ]
    return []


def heading_level(line: str) -> int | None:
    match = re.match(r"^(#{1,6})\s+", line)
    return len(match.group(1)) if match else None


def section_body(visible: list[tuple[int, str]], heading: str) -> list[tuple[int, str]]:
    start_index = None
    start_level = None
    for index, (_, line) in enumerate(visible):
        if line.startswith(heading):
            start_index = index
            start_level = heading_level(line)
            break
    if start_index is None or start_level is None:
        return []

    body: list[tuple[int, str]] = []
    for line_number, line in visible[start_index + 1 :]:
        level = heading_level(line)
        if level is not None and level <= start_level:
            break
        body.append((line_number, line))
    return body


def meaningful_text(body: list[tuple[int, str]]) -> str:
    cleaned: list[str] = []
    for _, line in body:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue
        if TABLE_SEPARATOR_RE.match(stripped):
            continue
        if re.match(r"^\|?\s*[-: ]+\|", stripped):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


def looks_like_english_prose(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("<!--"):
        return False

    text = re.sub(r"`[^`]+`", " ", stripped)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"/[A-Za-z0-9_./{}:-]+", " ", text)
    words = [word for word in ENGLISH_WORD_RE.findall(text) if word.upper() not in TECHNICAL_WORDS]
    if len(words) < 5:
        return False

    cjk_count = len(CJK_RE.findall(text))
    alpha_count = sum(len(word) for word in words)
    return cjk_count == 0 or alpha_count > cjk_count * 3


def normalize_for_match(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[\s`'\"/_-]+", "", normalized)
    normalized = normalized.replace("（", "").replace("）", "")
    return normalized


def contains_any(text: str, keywords: list[str]) -> bool:
    normalized_text = normalize_for_match(text)
    return any(normalize_for_match(keyword) in normalized_text for keyword in keywords)


def contains_any_group(text: str, keyword_groups: list[list[str]]) -> bool:
    return any(contains_any(text, group) for group in keyword_groups)


def audit(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    visible = strip_fenced_blocks(lines)
    findings: list[Finding] = []

    findings.extend(heading_order_violations(visible))

    for heading in REQUIRED_HEADINGS:
        if not has_heading(visible, heading):
            priority = "P0" if heading in P0_HEADINGS else "P1"
            findings.append(Finding(priority, None, f"缺少必需章节：{heading}"))

    for heading in REQUIRED_HEADINGS:
        body = section_body(visible, heading)
        if not body:
            continue
        content = meaningful_text(body)
        first_line = body[0][0] if body else None
        if heading in P0_HEADINGS and len(content) < 30 and "不适用" not in content:
            findings.append(Finding("P0", first_line, f"核心章节内容过薄，无法支撑前端方案评审：{heading}"))
        elif len(content) < 40 and "不适用" not in content:
            findings.append(Finding("P1", first_line, f"章节内容过薄，可能缺少可评审细节：{heading}"))

    for heading in OPTIONAL_BUT_EXPECTED:
        if not has_heading(visible, heading):
            findings.append(Finding("P2", None, f"模板章节未出现；若不适用，请补充不适用说明：{heading}"))

    scope_text = meaningful_text(section_body(visible, "### 2.1 改动范围"))
    if scope_text and "不适用" not in scope_text:
        missing_buckets = []
        for bucket_group in SCOPE_BUCKET_GROUPS:
            if not contains_any(scope_text, bucket_group):
                missing_buckets.append(bucket_group[0])
        if missing_buckets:
            findings.append(Finding("P0", None, f"改动范围未覆盖全部必填分类：{', '.join(missing_buckets)}"))

    contract_text = meaningful_text(section_body(visible, "### 3.4 字段清洗、转换与前后端契约对齐（如适用）"))
    if contract_text and "不适用" not in contract_text and not contains_any_group(contract_text, FIELD_CONTRACT_KEYWORD_GROUPS):
        findings.append(Finding("P0", None, "字段清洗、转换与前后端契约章节缺少字段来源、转换规则或提供方/消费方说明"))

    acceptance_method_text = meaningful_text(section_body(visible, "### 5.1 验收方式"))
    if acceptance_method_text and not contains_any_group(acceptance_method_text, ACCEPTANCE_METHOD_KEYWORD_GROUPS):
        findings.append(Finding("P0", None, "验收方式缺少可执行工具或方法，例如 chrome-devtools、自动化脚本、单元测试或冒烟"))

    acceptance_case_text = meaningful_text(section_body(visible, "### 5.2 验收用例"))
    if acceptance_case_text and not contains_any_group(acceptance_case_text, ACCEPTANCE_CASE_KEYWORD_GROUPS):
        findings.append(Finding("P0", None, "验收用例缺少前置条件、操作步骤、预期结果或契约校验重点"))

    if DESIGN_TOOL_MODEL_LABEL not in text:
        findings.append(Finding("P1", None, "缺少常规设计使用工具和模型登记"))

    review_record_body = meaningful_text(section_body(visible, "### B. 评审记录"))
    if review_record_body and not all(keyword in review_record_body for keyword in REVIEW_TOOL_MODEL_KEYWORDS):
        review_line = first_heading_line(visible, "### B. 评审记录")
        findings.append(Finding("P1", review_line, "评审记录缺少评审工具或评审模型登记"))

    for keyword, message in AI_IMPLEMENTATION_RULES:
        if keyword not in text:
            findings.append(Finding("P1", None, message))

    for line_number, line in visible:
        for match in PLACEHOLDER_RE.finditer(line):
            findings.append(Finding("P1", line_number, f"存在模板占位符未替换：{match.group(0)}"))
        if UNRESOLVED_RE.search(line):
            findings.append(Finding("P1", line_number, "存在未确认/TODO/TBD 标记，需要确认或改为明确假设"))
        if looks_like_english_prose(line):
            findings.append(Finding("P1", line_number, "存在疑似英文说明文本；技术方案正文应使用中文"))

    if "不适用" not in text and any(not has_heading(visible, h) for h in OPTIONAL_BUT_EXPECTED):
        findings.append(Finding("P2", None, "存在缺失的可选章节，但全文没有说明任何“不适用”场景"))

    return findings


def print_report(path: Path, findings: list[Finding]) -> None:
    print(f"# 前端技术方案遗漏检查报告\n\n文件：`{path}`\n")
    if not findings:
        print("结果：未发现明显遗漏。仍建议人工复核牵涉范围、字段契约和关键交互验收路径。")
        return

    grouped = {"P0": [], "P1": [], "P2": []}
    for finding in findings:
        grouped.setdefault(finding.priority, []).append(finding)

    for priority in ["P0", "P1", "P2"]:
        items = grouped.get(priority, [])
        if not items:
            continue
        print(f"## {priority}")
        for item in items:
            location = f"第 {item.line} 行" if item.line else "全局"
            print(f"- {location}: {item.message}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Markdown 前端技术方案是否存在常见遗漏。")
    parser.add_argument("solution", type=Path, help="Markdown 前端技术方案文件路径")
    args = parser.parse_args()

    if not args.solution.exists():
        print(f"错误：文件不存在：{args.solution}", file=sys.stderr)
        return 2
    if args.solution.suffix.lower() not in {".md", ".markdown"}:
        print("错误：请输入 Markdown 文件（.md 或 .markdown）", file=sys.stderr)
        return 2

    findings = audit(args.solution)
    print_report(args.solution, findings)
    return 1 if any(item.priority in {"P0", "P1"} for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
