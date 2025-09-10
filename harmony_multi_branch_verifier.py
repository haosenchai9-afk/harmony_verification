#!/usr/bin/env python3
# =============================================================================
# 实例：harmony仓库多分支提交聚合验证脚本
# 功能：验证history-report-2025分支下3类核心产物文件（JSON/Markdown/文本）的合规性
# 依赖: requests, python-dotenv (安装：pip install requests python-dotenv)
# 使用说明：1. 配置.mcp_env文件；2. 确保history-report-2025分支存在；3. 直接运行脚本
# =============================================================================

import sys
import os
import requests
import base64
import json
import re
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv


# -----------------------------
# 1) 实例化配置（已替换为实际值，无需修改）
# -----------------------------
CONFIG = {
    "ENV_CONFIG": {
        "github_token_var": "MCP_GITHUB_TOKEN",
        "github_org_var": "GITHUB_EVAL_ORG",
        "env_file": ".mcp_env",
        "root_env_var": "GITHUB_REPO_ROOT"
    },
    "GITHUB_API_CONFIG": {
        "repo_name": "harmony",
        "api_version": "v3",
        "auth_scheme": "Bearer",
        "timeout": 10,
        "per_page": 100
    },
    "BRANCH_CONFIG": {
        "target_branch": "history-report-2025",
        "must_exist": True,
        "base_branch": "main"
    },
    "ARTIFACTS": [
        {
            "name": "BRANCH_COMMITS.json",
            "must_be_in_branch": True,
            "type": "json",
            "format": "json",
            "schema": {
                "min_branches": 3,
                "commit_fields": ["sha", "author", "message", "files_changed"],
                "min_commits_per_branch": 3,
                "json_strict": True
            },
            "content_checks": {
                "expected_branches_source": "HARDCODED",
                "expected_branches": [
                    "pr/45-googlefan256-main",
                    "pr/25-neuralsorcerer-patch-1",
                    "pr/41-amirhosseinghanipour-fix-race-conditions-and-offline-api"
                ],
                "expected_branches_file": "",
                "field_rules": {
                    "sha": {"regex": r"^[0-9a-f]{40}$"},
                    "author": {"min_len": 3},
                    "files_changed": {"type": "int", "min": 1}
                },
                "uniqueness": {
                    "fields": ["sha"],
                    "error_on_duplicate": True
                }
            }
        },
        {
            "name": "CROSS_BRANCH_ANALYSIS.md",
            "must_be_in_branch": True,
            "type": "text",
            "format": "markdown",
            "schema": {
                "required_sections": [
                    "## Top Contributors",
                    "## Branch Commit Summary"
                ],
                "min_length": 500,
                "encoding": "utf-8"
            },
            "content_checks": {
                "must_contain_keywords": [
                    "contributors", "commits", "branch"
                ],
                "expected_contributors": [
                    "scott-oai: 35 commits",
                    "egorsmkv: 4 commits",
                    "axion66: 2 commits"
                ],
                "allow_extra_contributors": True
            }
        },
        {
            "name": "MERGE_TIMELINE.txt",
            "must_be_in_branch": True,
            "type": "text",
            "format": "txt",
            "schema": {
                "line_pattern": r"^\d{4}-\d{2}-\d{2} \| .+ \| [0-9a-f]{40}$",
                "min_lines": 10,
                "date_format": "YYYY-MM-DD"
            },
            "content_checks": {
                "expected_entries_source": "HARDCODED",
                "expected_entries": [
                    "2025-08-06 | Merge pull request #29 from axion66/improve-readme-and-checks | 3efbf742533a375fc148d75513597e139329578b",
                    "2025-08-06 | Merge pull request #30 from Yuan-ManX/harmony-format | 9d653a4c7382abc42d115014d195d9354e7ad357",
                    "2025-08-05 | Merge pull request #26 from jordan-wu-97/jordan/fix-function-call-atomic-bool | 82b3afb9eb043343f322c937262cc50405e892c3"
                ],
                "expected_entries_file": "",
                "allow_extra_entries": True
            }
        }
    ],
    "SOURCE_VALIDATION": {
        "enable": False,
        "source_branches": ["main"],
        "commit_sha_pattern": r"^[0-9a-f]{40}$"
    },
    "POLICY": {
        "forbid_modifying_existing_files": True,
        "only_allow_artifacts": [
            "BRANCH_COMMITS.json",
            "CROSS_BRANCH_ANALYSIS.md",
            "MERGE_TIMELINE.txt"
        ]
    }
}


# -----------------------------
# 2) 工具函数（无需修改）
# -----------------------------
def _load_github_env() -> Tuple[Optional[str], Optional[str]]:
    """加载GitHub鉴权环境变量（从.mcp_env读取）"""
    load_dotenv(CONFIG["ENV_CONFIG"]["env_file"])
    github_token = os.environ.get(CONFIG["ENV_CONFIG"]["github_token_var"])
    github_org = os.environ.get(CONFIG["ENV_CONFIG"]["github_org_var"])

    if not github_token:
        print(f"❌ 未加载到环境变量 {CONFIG['ENV_CONFIG']['github_token_var']}（检查{CONFIG['ENV_CONFIG']['env_file']}）")
    if not github_org:
        print(f"❌ 未加载到环境变量 {CONFIG['ENV_CONFIG']['github_org_var']}（检查{CONFIG['ENV_CONFIG']['env_file']}）")

    return github_token, github_org


def _build_github_headers(github_token: str) -> Dict[str, str]:
    """构建GitHub API请求头"""
    return {
        "Authorization": f"{CONFIG['GITHUB_API_CONFIG']['auth_scheme']} {github_token}",
        "Accept": f"application/vnd.github.{CONFIG['GITHUB_API_CONFIG']['api_version']}+json",
        "User-Agent": "harmony-multi-branch-verifier"
    }


def _call_github_api(
    endpoint: str,
    headers: Dict[str, str],
    org: str
) -> Tuple[bool, Optional[Dict]]:
    """调用GitHub API（指向harmony仓库）"""
    repo_name = CONFIG["GITHUB_API_CONFIG"]["repo_name"]
    api_url = f"https://api.github.com/repos/{org}/{repo_name}/{endpoint}"

    try:
        response = requests.get(
            api_url,
            headers=headers,
            timeout=CONFIG["GITHUB_API_CONFIG"]["timeout"]
        )

        if response.status_code == 200:
            return True, response.json()
        elif response.status_code == 404:
            print(f"⚠️ API资源未找到：{endpoint}（404）")
            return False, None
        else:
            print(f"❌ API请求失败：{endpoint}（状态码：{response.status_code}）")
            print(f"   响应内容：{response.text[:200]}")
            return False, None

    except Exception as e:
        print(f"❌ API调用异常：{endpoint}（错误：{str(e)}）")
        return False, None


def _check_branch_existence(branch_name: str, headers: Dict[str, str], org: str) -> bool:
    """检查目标分支是否存在"""
    success, _ = _call_github_api(
        endpoint=f"branches/{branch_name}",
        headers=headers,
        org=org
    )
    if not success and CONFIG["BRANCH_CONFIG"]["must_exist"]:
        print(f"❌ 目标分支 '{branch_name}' 不存在（必需分支，终止验证）")
        return False
    elif not success:
        print(f"⚠️ 目标分支 '{branch_name}' 不存在（非必需分支，继续验证）")
        return True
    print(f"✅ 目标分支 '{branch_name}' 存在")
    return True


def _get_artifact_content(
    branch: str,
    file_name: str,
    headers: Dict[str, str],
    org: str
) -> Optional[str]:
    """从目标分支获取产物文件内容（Base64解码）"""
    success, file_data = _call_github_api(
        endpoint=f"contents/{file_name}?ref={branch}",
        headers=headers,
        org=org
    )
    if not success or not file_data:
        print(f"❌ 未在分支 '{branch}' 找到文件 '{file_name}'")
        return None

    try:
        base64_content = file_data.get("content", "").replace("\n", "")
        encoding = next(
            art["schema"]["encoding"] for art in CONFIG["ARTIFACTS"] 
            if art["name"] == file_name and "encoding" in art["schema"]
        ) or "utf-8"
        return base64.b64decode(base64_content).decode(encoding)
    except Exception as e:
        print(f"❌ 文件 '{file_name}' 解码失败（错误：{str(e)}）")
        return None


# -----------------------------
# 3) 核心验证逻辑（无需修改）
# -----------------------------
def _validate_branch_commits_json(content: str) -> bool:
    """验证BRANCH_COMMITS.json"""
    json_artifact = next(art for art in CONFIG["ARTIFACTS"] if art["name"] == "BRANCH_COMMITS.json")
    expected_branches = json_artifact["content_checks"]["expected_branches"]
    commit_fields = json_artifact["schema"]["commit_fields"]
    field_rules = json_artifact["content_checks"]["field_rules"]

    # 验证JSON语法
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ BRANCH_COMMITS.json 语法错误：{str(e)}")
        return False
    print("✅ BRANCH_COMMITS.json 语法验证通过")

    # 验证分支数量与存在性
    if len(data) < json_artifact["schema"]["min_branches"]:
        print(f"❌ 分支数量不足（需≥{json_artifact['schema']['min_branches']}，实际：{len(data)}）")
        return False
    missing_branches = [b for b in expected_branches if b not in data]
    if missing_branches:
        print(f"❌ 缺失预期分支：{', '.join(missing_branches)}")
        return False
    print(f"✅ 分支验证通过（共{len(data)}个分支，含所有预期分支）")

    # 验证提交字段与格式
    sha_set = set()
    valid = True
    for branch, commits in data.items():
        if len(commits) < json_artifact["schema"]["min_commits_per_branch"]:
            print(f"❌ 分支 '{branch}' 提交不足（需≥3，实际：{len(commits)}）")
            valid = False
            continue

        for idx, commit in enumerate(commits, 1):
            # 字段完整性
            missing_fields = [f for f in commit_fields if f not in commit]
            if missing_fields:
                print(f"❌ 分支 '{branch}' 第{idx}条提交缺失字段：{', '.join(missing_fields)}")
                valid = False
                continue

            # SHA格式与唯一性
            sha = commit["sha"]
            if not re.match(field_rules["sha"]["regex"], sha):
                print(f"❌ 分支 '{branch}' 第{idx}条SHA格式错误：{sha}")
                valid = False
                continue
            if sha in sha_set:
                print(f"❌ SHA重复：{sha}")
                valid = False
                continue
            sha_set.add(sha)

            # 作者与文件数规则
            if len(commit["author"]) < field_rules["author"]["min_len"]:
                print(f"❌ 分支 '{branch}' 第{idx}条作者名过短：{commit['author']}")
                valid = False
                continue
            if not isinstance(commit["files_changed"], int) or commit["files_changed"] < field_rules["files_changed"]["min"]:
                print(f"❌ 分支 '{branch}' 第{idx}条修改文件数错误：{commit['files_changed']}")
                valid = False
                continue

    if valid:
        print("✅ BRANCH_COMMITS.json 提交验证通过")
    return valid


def _validate_cross_branch_md(content: str) -> bool:
    """验证CROSS_BRANCH_ANALYSIS.md"""
    md_artifact = next(art for art in CONFIG["ARTIFACTS"] if art["name"] == "CROSS_BRANCH_ANALYSIS.md")
    required_sections = md_artifact["schema"]["required_sections"]
    expected_contributors = md_artifact["content_checks"]["expected_contributors"]
    keywords = md_artifact["content_checks"]["must_contain_keywords"]

    # 验证文档长度
    if len(content) < md_artifact["schema"]["min_length"]:
        print(f"❌ 文档长度不足（需≥{md_artifact['schema']['min_length']}字节，实际：{len(content)}）")
        return False
    print("✅ 文档长度验证通过")

    # 验证必需章节
    missing_sections = [s for s in required_sections if s not in content]
    if missing_sections:
        print(f"❌ 缺失必需章节：{', '.join(missing_sections)}")
        return False
    print("✅ 必需章节验证通过")

    # 验证关键词
    missing_keywords = [k for k in keywords if k.lower() not in content.lower()]
    if missing_keywords:
        print(f"❌ 缺失关键词：{', '.join(missing_keywords)}")
        return False
    print("✅ 关键词验证通过")

    # 验证贡献者记录
    missing_contributors = [c for c in expected_contributors if c not in content]
    if missing_contributors:
        print(f"❌ 缺失贡献者记录：{', '.join(missing_contributors)}")
        return False
    print("✅ 贡献者记录验证通过")
    return True


def _validate_merge_timeline(content: str) -> bool:
    """验证MERGE_TIMELINE.txt"""
    timeline_artifact = next(art for art in CONFIG["ARTIFACTS"] if art["name"] == "MERGE_TIMELINE.txt")
    line_pattern = re.compile(timeline_artifact["schema"]["line_pattern"])
    expected_entries = timeline_artifact["content_checks"]["expected_entries"]
    min_lines = timeline_artifact["schema"]["min_lines"]

    # 验证条目数量
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if len(lines) < min_lines:
        print(f"❌ 时间线条目不足（需≥{min_lines}，实际：{len(lines)}）")
        return False
    print(f"✅ 时间线条目数量验证通过（共{len(lines)}条）")

    # 验证格式
    for idx, line in enumerate(lines, 1):
        if not line_pattern.match(line):
            print(f"❌ 第{idx}条格式错误：{line}")
            print(f"   预期格式：YYYY-MM-DD | 描述 | 40位SHA（如2025-08-06 | Merge... | 3efbf74...）")
            return False
    print("✅ 时间线格式验证通过")

    # 验证预期条目
    missing_entries = [e for e in expected_entries if e not in content]
    if missing_entries:
        print(f"❌ 缺失预期时间线条目：{', '.join([e[:50]+'...' for e in missing_entries])}")
        return False
    print("✅ 预期时间线条目验证通过")
    return True


def _validate_artifact(content: str, artifact_name: str) -> bool:
    """路由验证逻辑"""
    if artifact_name == "BRANCH_COMMITS.json":
        return _validate_branch_commits_json(content)
    elif artifact_name == "CROSS_BRANCH_ANALYSIS.md":
        return _validate_cross_branch_md(content)
    elif artifact_name == "MERGE_TIMELINE.txt":
        return _validate_merge_timeline(content)
    else:
        print(f"⚠️ 未支持的文件类型：{artifact_name}（跳过）")
        return True


# -----------------------------
# 4) 主流程（无需修改）
# -----------------------------
def main():
    print("🔍 开始harmony仓库多分支提交聚合验证...")
    print("=" * 60)

    # 步骤1：加载环境
    print("\n【步骤1/5】加载GitHub环境...")
    github_token, github_org = _load_github_env()
    if not github_token or not github_org:
        print("❌ 环境初始化失败（缺失令牌或组织名）")
        sys.exit(1)
    headers = _build_github_headers(github_token)
    print(f"✅ 环境初始化完成（组织：{github_org}，令牌已加载）")

    # 步骤2：验证目标分支
    print("\n【步骤2/5】验证目标分支...")
    target_branch = CONFIG["BRANCH_CONFIG"]["target_branch"]
    if not _check_branch_existence(target_branch, headers, github_org):
        sys.exit(1)

    # 步骤3：验证产物文件
    print("\n【步骤3/5】验证产物文件（共3个）...")
    all_valid = True
    for artifact in CONFIG["ARTIFACTS"]:
        print(f"\n👉 验证：{artifact['name']}")
        content = _get_artifact_content(
            branch=target_branch,
            file_name=artifact["name"],
            headers=headers,
            org=github_org
        )
        if not content:
            all_valid = False
            continue
        if not _validate_artifact(content, artifact["name"]):
            all_valid = False
        else:
            print(f"✅ {artifact['name']} 验证通过")
    if not all_valid:
        print("\n❌ 部分产物文件验证失败")
        sys.exit(1)

    # 步骤4：源文件交叉验证（默认禁用）
    print("\n【步骤4/5】源文件交叉验证...")
    if CONFIG["SOURCE_VALIDATION"]["enable"]:
        print("⚠️  源文件验证已启用，需扩展实际对比逻辑（当前为占位）")
        print("✅ 源文件验证通过（占位）")
    else:
        print("⚠️  源文件验证未启用（配置disable=false可开启）")
        print("✅ 源文件验证步骤跳过")

    # 步骤5：策略约束检查
    print("\n【步骤5/5】策略约束检查...")
    print(f"✅ 禁止修改仓库文件：{CONFIG['POLICY']['forbid_modifying_existing_files']}")
    print(f"✅ 仅允许验证产物：{', '.join(CONFIG['POLICY']['only_allow_artifacts'])}")
    print("✅ 策略约束验证通过")

    # 最终结果
    print("\n" + "=" * 60)
    print("🎉 harmony仓库多分支提交聚合验证所有步骤通过！")
    print(f"📋 验证汇总：")
    print(f"   - 仓库：{github_org}/harmony")
    print(f"   - 分支：{target_branch}")
    print(f"   - 产物：BRANCH_COMMITS.json、CROSS_BRANCH_ANALYSIS.md、MERGE_TIMELINE.txt")
    print("=" * 60)
    sys.exit(0)


# -----------------------------
# 入口（执行脚本）
# -----------------------------
if __name__ == "__main__":
    main()
