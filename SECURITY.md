# 安全政策

## 支持的版本

| 版本 | 是否支持 |
|------|----------|
| 最新版（main） | ✅ |

## 报告安全漏洞

**请勿通过公开的 GitHub Issue 报告安全漏洞。**

如果你发现安全漏洞，请通过本仓库的
[GitHub Security Advisory](https://github.com/Gikm2157/Rag-chatbot/security/advisories/new)
私下提交报告，请勿在公开 Issue 中披露漏洞细节。

请尽可能提供详细信息：

- 漏洞描述
- 复现步骤
- 潜在影响
- 建议的修复方案（可选）

你将在 **48 小时内**收到回复。请在公开披露漏洞前，给予我们合理的时间来处理该问题。

## 自托管安全注意事项

- **切勿提交 `.env`**，其中包含 API 密钥。该文件已列入 `.gitignore`，必须保持未跟踪状态。
- **Redis** 不应暴露在公网中。请在生产环境中使用 `REDIS_PASSWORD`。
- **CORS**：在生产环境中，将 `CORS_ORIGINS` 设置为你的具体前端域名，而不是 `["*"]`。
- **速率限制**默认启用（每个 IP 每分钟 60 个请求）。请根据流量需求调整 [main.py](main.py) 中的 `RateLimitMiddleware` 设置。
- 应定期轮换 **LLM API 密钥**（OpenAI、Anthropic、Groq），并将其权限限制为所需的最低范围。
