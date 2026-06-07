# Hermes Agent 最小化重构方案

## 目标

从 82 万行 / 2108 文件的原始仓库中，提取并重构一个**最小可运行 AI agent**，保留：
- OpenAI + Anthropic 双协议支持
- 8 个核心工具
- 单 chat web 界面（vanilla JS）
- local / docker 运行
- SSE 流式输出 + session 列表 + 工具审批

## 审计结论

### 文件分布（2108 文件 / 825,580 行）

| 分类 | 文件数 | 行数 | 占比 |
|------|--------|------|------|
| **核心必要** | ~160 | ~30,000 | 3.6% |
| **可选但被依赖** | ~70 | ~50,000 | 6.1% |
| **完全可选/独立** | ~1870 | ~745,000 | 90.3% |

---

## 执行计划（按 commit 顺序）

### Phase 0: 建立基线

```
git checkout -b cleanup/minimal-agent-harness
```

### Phase 1: 删除完全独立的可选组件（安全删除，不影响任何代码）

每个 commit 一个目录，带删除理由。

| Commit | 目标 | 行数 | 理由 |
|--------|------|------|------|
| `chore: remove website/` | `website/` | ~2,500 | Docusaurus 文档站点，与运行时无关 |
| `chore: remove ui-tui/ and tui_gateway/` | `ui-tui/` `tui_gateway/` | ~8,000 | Ink React TUI，替代 CLI 的可选前端 |
| `chore: remove acp_adapter/ and acp_registry/` | `acp_adapter/` `acp_registry/` | ~3,000 | VS Code/Zed 编辑器集成 |
| `chore: remove environments/ and rl_cli.py` | `environments/` `rl_cli.py` | ~15,000 | RL 训练环境，仅数据生成/评估用 |
| `chore: remove batch_runner.py and toolset_distributions.py` | `batch_runner.py` `toolset_distributions.py` | ~1,650 | 批量数据生成管道 |
| `chore: remove trajectory_compressor.py` | `trajectory_compressor.py` | ~1,500 | 训练数据后处理 |
| `chore: remove mini_swe_runner.py` | `mini_swe_runner.py` | ~720 | 独立 SWE 任务运行器 |
| `chore: remove mcp_serve.py` | `mcp_serve.py` | ~870 | MCP 服务器，外部集成 |
| `chore: remove optional-skills/` | `optional-skills/` | ~5,000 | 不随默认安装分发的技能 |
| `chore: remove datagen-config-examples/` | `datagen-config-examples/` | ~200 | 数据生成配置示例 |
| `chore: remove scripts/` | `scripts/` | ~3,000 | 构建/安装/开发脚本 |
| `chore: remove docs/` | `docs/` | ~1,000 | 迁移指南、设计文档 |
| `chore: remove docker/` | `docker/` | ~50 | 旧 Docker 部署文件 |
| `chore: remove nix/ flake.nix flake.lock` | `nix/` `flake.nix` `flake.lock` | ~500 | Nix 打包 |
| `chore: remove packaging/` | `packaging/` | ~30 | Homebrew 公式 |
| `chore: remove plans/ .plans/` | `plans/` `.plans/` | ~300 | 设计计划文档 |
| `chore: remove .github/` | `.github/` | ~500 | GitHub CI/CD workflows |
| `chore: remove assets/` | `assets/` | 0 | Banner 图片 |
| `chore: remove top-level docs and configs` | RELEASE_*.md, CONTRIBUTING.md, SECURITY.md, hermes-already-has-routines.md, .envrc, .dockerignore, .gitattributes, .mailmap, constraints-termux.txt, setup-hermes.sh, cli-config.yaml.example | ~8,000 | 文档和开发工具 |

**Phase 1 合计删除: ~50,000 行，不影响任何核心代码运行。**

### Phase 2: 删除可选但被依赖的组件（需要同步修改核心代码）

| Commit | 目标 | 行数 | 需要的代码修改 |
|--------|------|------|----------------|
| `chore: remove gateway/` | `gateway/` (17 文件) | ~35,000 | 移除 `tools/send_message_tool.py`、`tools/tts_tool.py` 中的 gateway 延迟导入；移除 `cli.py` 和 `hermes_cli/main.py` 中 gateway 相关子命令 |
| `chore: remove cron/` | `cron/` (3 文件) | ~1,500 | 移除 `cli.py` 和 `hermes_cli/` 中的 cron 延迟导入；移除 `tools/cronjob_tools.py` |
| `chore: remove plugins/` | `plugins/` (6 文件) | ~3,000 | 移除 `run_agent.py` 中插件记忆加载逻辑；移除 `hermes_cli/` 中插件相关命令 |
| `chore: remove skills/` | `skills/` (26 子目录) | ~15,000 | 移除 `tools/skills_tool.py`、`tools/skills_sync.py`、`tools/skills_hub.py`、`tools/skills_guard.py`；移除 `agent/skill_commands.py` |
| `chore: remove web/ (old React web)` | `web/` (11 文件) | ~3,000 | 移除 `hermes_cli/web_server.py`；旧 web 是 React 构建产物，新 web 将用 vanilla JS 重写 |
| `chore: remove package.json package-lock.json` | `package.json` `package-lock.json` | ~220,000 | 移除 `tools/browser_tool.py`、`tools/browser_camofox.py` 等浏览器工具 |

**Phase 2 合计删除: ~280,000 行，需同步修改 ~20 个核心文件。**

### Phase 3: 精简核心（保留但瘦身）

这些文件必须保留，但可以大幅精简。

#### 3.1 `run_agent.py` (12,067 行 → 目标 ~800 行)

当前包含:
- AIAgent 核心循环 (~500 行) ← **保留**
- Provider 路由/fallback (~1500 行) ← 精简到 openai + anthropic 两个
- 并行 tool 执行 (~400 行) ← 移除，改为串行
- Context 压缩 (~800 行) ← 保留精简版
- Trajectory 保存 (~600 行) ← 移除
- Token 计数 (~300 行) ← 保留
- 消息管理 (~500 行) ← 保留
- 记忆系统集成 (~400 行) ← 移除（plugins 已删）
- 大量 provider 特定适配代码 (~5000 行) ← 移除

**策略**: 新建 `hermes_core/agent.py`，从 `run_agent.py` 提取核心循环，重写为 ~800 行。

#### 3.2 `cli.py` (10,536 行 → 目标 ~500 行)

当前包含:
- HermesCLI 交互式 REPL (~3000 行) ← 保留精简版
- 皮肤/主题系统 (~1500 行) ← 移除
- Slash 命令处理 (~2000 行) ← 保留核心命令
- Banner/显示 (~1000 行) ← 保留
- 配置加载 (~1000 行) ← 保留
- 文件拖放/图片 (~500 行) ← 移除
- 审批 UI (~500 行) ← 保留

**策略**: 新建 `hermes_core/cli.py`，精简到 ~500 行基本 REPL。

#### 3.3 `model_tools.py` (562 行 → 目标 ~200 行)

保留: `get_tool_definitions()`, `handle_function_call()`
移除: MCP 发现、插件发现、异步桥接

#### 3.4 `toolsets.py` (717 行 → 目标 ~100 行)

保留: 单一 core toolset 定义
移除: 40 个 toolset 定义、组合逻辑、自定义 toolset

#### 3.5 `hermes_state.py` (1,293 行 → 目标 ~200 行)

替换为: JSON 文件 session store（`hermes_core/session.py`）
移除: SQLite、FTS5、schema 迁移、token 追踪

#### 3.6 `agent/` (33 文件 → 目标 ~5 文件)

保留:
- `prompt_builder.py` — 系统提示组装（精简）
- `context_compressor.py` — 上下文压缩（精简）
- `model_metadata.py` — 模型上下文长度

移除:
- `anthropic_adapter.py` — 协议适配逻辑内联到 agent.py
- `auxiliary_client.py` — 辅助 LLM 客户端
- `prompt_caching.py` — Anthropic prompt 缓存（v2）
- `display.py` — 终端显示（CLI 内联）
- `skill_commands.py` — 技能命令（skills 已删）
- `trajectory.py` — 轨迹保存
- `memory_manager.py` — 记忆管理（plugins 已删）
- `error_classifier.py` — 错误分类（内联）
- `retry_utils.py` — 重试逻辑（内联）
- 其余 20+ 文件

#### 3.7 `tools/` (61 文件 → 目标 ~10 文件)

保留 8 个核心工具:
- `registry.py` — 工具注册表
- `terminal_tool.py` — 终端执行
- `file_tools.py` — 文件读写
- `file_operations.py` — 文件编辑（patch）
- `web_tools.py` — web_fetch（精简，去掉 web_search）
- `code_execution_tool.py` — Python 执行
- `approval.py` — 危险命令审批
- `process_registry.py` — 后台进程管理

保留基础设施:
- `ansi_strip.py` — ANSI 清理
- `path_security.py` — 路径安全
- `url_safety.py` — URL 安全
- `binary_extensions.py` — 二进制检测
- `patch_parser.py` — Patch 解析
- `fuzzy_match.py` — 模糊匹配
- `budget_config.py` — 预算配置
- `debug_helpers.py` — 调试工具
- `env_passthrough.py` — 环境变量白名单
- `interrupt.py` — 中断信号
- `tool_result_storage.py` — 结果存储
- `credential_files.py` — 凭证透传
- `tool_backend_helpers.py` — 后端选择

移除 ~40 个文件:
- `browser_tool.py` `browser_camofox.py` `browser_camofox_state.py` — 浏览器
- `delegate_tool.py` — 子代理委托
- `mcp_tool.py` `mcp_oauth.py` `mcp_oauth_manager.py` `osv_check.py` — MCP
- `vision_tools.py` — 视觉
- `tts_tool.py` `neutts_synth.py` — TTS
- `send_message_tool.py` — 消息发送
- `skills_tool.py` `skills_hub.py` `skills_sync.py` `skills_guard.py` `skill_manager_tool.py` — 技能
- `cronjob_tools.py` — 定时任务
- `rl_training_tool.py` — RL 训练
- `mixture_of_agents_tool.py` — 多代理混合
- `transcription_tools.py` — 转录
- `todo_tool.py` `memory_tool.py` `checkpoint_manager.py` — agent 自管
- `xai_http.py` `openrouter_client.py` `managed_tool_gateway.py` — 第三方
- `tirith_security.py` `website_policy.py` — 安全策略
- `environments/` 下除 `local.py` 和 `base.py` 外的所有后端

#### 3.8 `hermes_cli/` (49 文件 → 目标 ~5 文件)

保留:
- `main.py` — 入口点
- `config.py` — 配置管理（精简）
- `commands.py` — 斜杠命令（精简）
- `auth.py` — 凭证解析
- `callbacks.py` — 终端回调

移除:
- `skin_engine.py` — 皮肤
- `setup.py` — 设置向导
- `skills_hub.py` `skills_config.py` — 技能
- `tools_config.py` — 工具配置
- `models.py` `model_switch.py` — 模型管理
- `web_server.py` — 旧 web 服务器
- 其余 35+ 文件

### Phase 4: 新建最小核心

在精简后的代码基础上，新建 `hermes_core/` 包:

```
hermes_core/
├── __init__.py          # 导出 AIAgent, HermesConfig
├── agent.py             # ~800 行，核心 agent 循环
├── config.py            # ~100 行，双协议配置
├── session.py           # ~150 行，JSON session store
├── tools_registry.py    # ~100 行，工具注册表
└── tools_builtin/       # 8 个工具实现
    ├── __init__.py
    ├── terminal.py
    ├── files.py
    ├── code_exec.py
    └── web.py
```

新建:
```
server.py               # ~300 行，FastAPI + SSE
main.py                 # ~100 行，CLI 入口
web/                    # vanilla JS 前端
├── index.html
├── styles.css
└── app.js
```

### Phase 5: 测试

```
tests/
├── conftest.py
├── test_agent.py
├── test_config.py
├── test_session.py
├── test_tools_registry.py
├── test_tools_builtin.py
└── test_server_api.py
```

### Phase 6: 文档和部署

- 重写 `README.md`
- 重写 `AGENTS.md`
- 更新 `pyproject.toml`（精简依赖）
- 更新 `requirements.txt`
- 更新 `Dockerfile`
- 更新 `.env.example`

---

## 最终产物

| 组件 | 文件数 | 行数 |
|------|--------|------|
| `hermes_core/` | 10 | ~1,500 |
| `server.py` | 1 | ~300 |
| `main.py` | 1 | ~100 |
| `web/` | 3 | ~500 |
| `tests/` | 7 | ~800 |
| 配置/文档 | 6 | ~300 |
| **合计** | **~28** | **~3,500** |

从 82 万行 → 3,500 行，保留率 0.4%。

---

## 风险点

1. **`run_agent.py` 的 provider fallback 逻辑**: 当前支持 6+ provider 的自动 fallback。精简到 2 个后，需确保错误处理路径完整。
2. **`hermes_state.py` → JSON**: SQLite 有并发安全保证（WAL 模式）。JSON 文件在并发场景下可能丢数据。单用户本地使用可接受。
3. **`agent/context_compressor.py`**: 上下文压缩是生产级长对话的关键能力。v1 保留精简版，v2 补全。
4. **`tools/approval.py`**: 当前审批逻辑与 gateway 深度耦合（通过 gateway 向用户发消息）。需要解耦为简单的 env 开关。

---

## 执行顺序

```
Phase 0: git checkout -b cleanup/minimal-agent-harness
Phase 1: 15 个独立 commit，删除完全可选组件
Phase 2: 6 个 commit，删除可选但被依赖的组件 + 同步修改核心代码
Phase 3: 6 个 commit，精简核心文件
Phase 4: 3 个 commit，新建 hermes_core/ + server.py + web/
Phase 5: 1 个 commit，测试套件
Phase 6: 1 个 commit，文档和部署
```

**总计约 32 个 commit，每个 commit 独立可 review、可 revert。**
