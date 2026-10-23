"""将已准备的评审提示词通过 stdin 发送给已核验的只读 CLI。

调用前由宿主核实模型接收方授权、当前 CLI 参数和有效工具权限。
本程序只保障输入传递方式，不提供沙箱、授权或二进制身份验证。
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


COMMANDS = {
    "claude": ["claude", "--bare", "--print", "--tools", "",
               "--disallowedTools", "mcp__*", "--strict-mcp-config",
               "--mcp-config", '{"mcpServers":{}}'],
    "codex": ["codex", "--ask-for-approval", "never", "exec", "--sandbox",
              "read-only", "--ignore-user-config", "--ignore-rules", "--ephemeral", "-"],
    "cursor": ["agent", "--mode", "ask", "--print", "--output-format", "text"],
}


def run_review(runtime, prompt_file, timeout=300, *, runner=None):
    if runtime not in COMMANDS:
        raise ValueError("unsupported runtime")
    if not 0 < timeout <= 1800:
        raise ValueError("timeout must be between 1 and 1800 seconds")
    prompt = Path(prompt_file).read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("prompt is empty")
    execute = subprocess.run if runner is None else runner
    return execute(
        list(COMMANDS[runtime]), input=prompt, text=True, encoding="utf-8",
        capture_output=True, timeout=timeout, check=False, shell=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=tuple(COMMANDS), required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_review(args.runtime, args.prompt_file, args.timeout)
    except subprocess.TimeoutExpired:
        print("评审超时；未输出原始输入或错误内容。", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("评审未启动或调用失败；请检查输入文件、CLI 和参数兼容性。", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print("评审进程失败（退出码 %s）；原始输出已隐藏。" % result.returncode, file=sys.stderr)
        return 1
    if not result.stdout.strip():
        print("评审返回空输出。", file=sys.stderr)
        return 1
    # 成功结果仍为待核验的评审材料，必须由宿主解析裁定，不构成操作授权。
    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
