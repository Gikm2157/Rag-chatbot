# 贡献指南

感谢你考虑为本项目作出贡献！

## 开始之前

1. **Fork** 本仓库并克隆你的 Fork
2. 为你的改动**创建分支**：
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **配置开发环境**，任选一种方式：

   **本地环境（Conda）**
   ```bash
   conda create -n chat-bot python=3.10
   conda activate chat-bot
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

   **Docker**
   ```bash
   docker-compose up --build
   ```

4. 修改代码前先**运行测试**：
   ```bash
   pytest tests/controllers/ tests/ingest/ -v
   ```

## 修改代码

- 保持改动聚焦，每个拉取请求只包含一个功能或修复
- 为所有新增行为在对应子目录中添加测试：
  - API 端点改动使用 `tests/controllers/`
  - 文档导入流水线改动使用 `tests/ingest/`
- 提交拉取请求前运行完整测试套件，全部 39 项测试必须通过
- 不要提交 `.env` 或任何包含 API 密钥的文件

## 拉取请求指南

- 为拉取请求提供清晰的标题和说明，解释改动的**内容**和**原因**
- 使用 `Closes #issue-number` 引用相关 Issue
- 保持拉取请求的差异较小且便于审查；如需进行大规模改动，请先创建 Issue

## 适合初次贡献的任务

- 在 [utils/llm_adapter.py](utils/llm_adapter.py) 中添加新的 LLM 提供商支持
- 在 [ingest/](ingest/) 中添加新的文档加载器（DOCX、TXT）
- 提高测试覆盖率
- 添加 Guardrails 或 RAGAS 评估（参见 [README 中的待办事项](README.md#-待办事项路线图)）

## 报告问题

请创建 GitHub Issue，并提供：

- 对问题的清晰描述
- 复现步骤
- 预期行为与实际行为
- Python 版本和操作系统

## 提问

请在本仓库发起 GitHub Discussion 或 Issue。
