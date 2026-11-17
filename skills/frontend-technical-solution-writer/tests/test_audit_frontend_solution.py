"""回归检查器对字段契约与验收要素的漏检，不调用模型服务。"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("solution_audit", ROOT / "scripts/audit_frontend_solution.py")
audit_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit_module
spec.loader.exec_module(audit_module)

CONTRACT_HEADING = "### 3.4 字段清洗、转换与前后端契约对齐（如适用）"
CASE_HEADING = "### 5.2 验收用例"
CONTRACT = [
    "字段来源：仓库选择控件。",
    "转换规则：直接使用选项编码，不转换单位。",
    "提供方：页面筛选表单。",
    "消费方：库存查询接口。",
    "类型定义：仓库编码为字符串。",
    "请求字段：warehouseCode，空值不传。",
    "响应字段：items，为库存记录数组。",
]
CASES = "前置条件：用户已登录且有仓库权限。\n操作步骤：选择仓库并查询。\n预期结果：只展示该仓库记录，清空选择后恢复默认范围。"


class AuditFrontendSolutionTests(unittest.TestCase):
    def audit_sections(self, contract="\n".join(CONTRACT), cases=CASES):
        # 只提供本组用例关注的章节；其他缺失章节由独立的既有检查报告。
        text = f"{CONTRACT_HEADING}\n{contract}\n### 3.5 状态管理、表单联动与异常态\n{CASE_HEADING}\n{cases}\n### 5.3 单元测试与自动化补充\n"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "solution.md"
            path.write_text(text, encoding="utf-8")
            return audit_module.audit(path)

    def contract_findings(self, findings):
        return [f for f in findings if "契约" in f.message and "缺少必需章节" not in f.message]

    def case_findings(self, findings):
        return [f for f in findings if "验收用例" in f.message and "缺少必需章节" not in f.message]

    def test_complete_contract_and_cases_have_no_element_findings(self):
        findings = self.audit_sections()
        self.assertEqual(self.contract_findings(findings), [])
        self.assertEqual(self.case_findings(findings), [])

    def test_each_missing_contract_element_is_reported(self):
        for index, line in enumerate(CONTRACT):
            with self.subTest(element=line.split("：")[0]):
                findings = self.contract_findings(self.audit_sections(contract="\n".join(CONTRACT[:index] + CONTRACT[index + 1:])))
                self.assertTrue(any(f.priority == "P0" and line.split("：")[0] in f.message for f in findings))

    def test_case_id_or_precondition_does_not_replace_steps_and_result(self):
        for cases in ["UI-001：验证仓库筛选的正常路径和清空路径，使用当前项目已有页面执行并记录观察情况。", "前置条件：用户登录并准备好仓库数据，打开当前页面并保证相关服务处于正常可用状态。"]:
            with self.subTest(cases=cases):
                findings = self.case_findings(self.audit_sections(cases=cases))
                self.assertTrue(any(f.priority == "P0" and "操作步骤" in f.message and "预期结果" in f.message for f in findings))

    def test_supported_synonyms_cover_case_elements(self):
        findings = self.audit_sections(cases="准备条件：用户已登录且具备仓库权限。\n执行步骤：选择仓库后点击查询。\n期望结果：列表仅展示目标仓库数据，其他筛选条件保持不变。")
        self.assertEqual(self.case_findings(findings), [])

    def test_each_default_case_table_covers_required_elements(self):
        template = (ROOT / "assets/frontend-technical-solution-template.md").read_text(encoding="utf-8")
        visible = audit_module.strip_fenced_blocks(template.splitlines())
        for heading in ["#### 交互联动场景", "#### 前后端通信与契约场景", "#### 工具函数 / translator 场景（如适用）"]:
            with self.subTest(heading=heading):
                # 只保留这一类适用用例，避免依赖其他用例表头通过检查。
                cases = audit_module.meaningful_text(audit_module.section_body(visible, heading))
                self.assertTrue(cases)
                self.assertEqual(self.case_findings(self.audit_sections(cases=cases)), [])

    def test_section_exemption_requires_reason(self):
        self.assertEqual(self.contract_findings(self.audit_sections(contract="本节不适用：本次仅调整按钮间距，不改变字段或接口。")), [])
        for contract in ["不适用", "本节不适用："]:
            with self.subTest(contract=contract):
                self.assertTrue(self.contract_findings(self.audit_sections(contract=contract)))

    def test_one_inapplicable_element_does_not_exempt_other_elements(self):
        findings = self.contract_findings(self.audit_sections(contract="请求字段：不适用，因为本次仅处理本地数据；页面筛选仍然需要说明输入和输出的数据约定。"))
        self.assertTrue(any(f.priority == "P0" and "字段来源" in f.message and "类型定义" in f.message for f in findings))

    def test_reasoned_element_exemption_preserves_other_checks(self):
        contract = "\n".join(CONTRACT[:-1] + ["响应字段：不适用，因为本次操作不读取服务端响应。"])
        self.assertEqual(self.contract_findings(self.audit_sections(contract=contract)), [])

    def test_empty_core_section_is_reported_even_without_blank_line(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.md"
            path.write_text(CONTRACT_HEADING + "\n### 3.5 状态管理、表单联动与异常态\n", encoding="utf-8")
            findings = self.contract_findings(audit_module.audit(path))
        self.assertTrue(any(f.priority == "P0" for f in findings))


if __name__ == "__main__":
    unittest.main()
