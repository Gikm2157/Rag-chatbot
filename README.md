<div align="center">

# 企业知识库智能客服

### 面向中小知识库场景的 RAG 问答后端

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![LangChain](https://img.shields.io/badge/LangChain-LLM%20Orchestration-orange)
![ChromaDB](https://img.shields.io/badge/VectorDB-Chroma-purple)
![LLM](https://img.shields.io/badge/LLM-DeepSeek-black)

</div>

---

## 📋 目录

- [项目概览](#-项目概览)
- [开源说明](#-开源说明)
- [项目背景](#-项目背景)
- [系统架构](#-系统架构)
- [工作原理](#-工作原理)
- [项目结构](#-项目结构)
- [安装与配置](#-安装与配置)
- [文档导入](#-6-文档导入s3--chromadb)
- [API 文档（Swagger）](#-7-api-文档swagger)
- [聊天 API](#-8-聊天-api)
- [健康检查](#-9-健康检查)
- [核心系统设计](#-核心系统设计)
- [主要功能](#-主要功能)
- [测试](#-测试)
- [待办事项](#-待办事项路线图)
- [技术栈](#-技术栈)
- [文档](#-文档)
- [参与贡献](#-参与贡献)
- [总结](#-总结)

---

## 📌 项目概览

这是一个面向中小企业知识库场景的 **RAG 智能客服后端**，使用以下技术构建：

* 🧠 使用 LangGraph 编排对话流程
* 🔍 使用 ChromaDB 构建 RAG 流水线
* 💬 默认接入 DeepSeek，并保留 OpenAI、Anthropic、Groq 扩展能力
* ⚡ 使用 FastAPI 提供后端 API
* 🧠 使用 Redis 存储记忆

支持的能力包括：

* 对话记忆
* 基于文档的问答（RAG）
* 严格限制在知识库范围内回答，机器人会拒绝回答已导入文档之外的问题
* 中文优先的多语言回答（简体中文、阿拉伯语、英语）
* 可扩展的后端设计

## 开源说明

本项目基于 [hasandeveloper/chat-bot](https://github.com/hasandeveloper/chat-bot)
进行中文场景二次开发，原项目采用 MIT License。

上游基准版本：`4522d7bb1184654953325dc86909371afa17eb1b`

当前版本主要完成了：

* DeepSeek OpenAI 兼容接口接入
* `BAAI/bge-small-zh-v1.5` 本地中文嵌入模型部署
* Docker 国内镜像与 CPU 版 PyTorch 构建适配
* 中文回答、中文对话摘要、中文 Swagger 和错误提示
* 中文说明文档、测试与部署验证

原项目版权声明保留在 [LICENSE](LICENSE) 中，后续功能将在此基础上持续开发。

## 🎯 项目背景

大多数聊天机器人 API 都是无状态的，无法保留长期上下文。

本项目通过组合以下能力解决这一问题：

- 有状态记忆（Redis）
- 长期对话摘要
- 基于 RAG 的知识检索
- LangGraph 流程编排

因此，它适合真实场景中的 SaaS 集成。

## 🧠 系统架构

<div align="center">

```
┌─────────────────────────────────────────────────────┐
│                    用户问题                         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
              FastAPI  POST /api/v1/chat
                         │
                         ▼
          ┌──────────────────────────────┐
          │       LangGraph 编排器       │
          │                              │
          │  1. load_memory   (Redis)    │
          │  2. retrieve_context (Chroma)│
          │  3. generate_answer  (LLM)   │
          │  4. summarize                │
          │  5. store_memory  (Redis)    │
          └──────────────────────────────┘
                         │
                         ▼
                    返回用户
```

</div>

## 🧠 工作原理

1. 用户发送问题
2. 系统从 Redis 加载对话历史
3. 从 ChromaDB 检索相关文档（RAG）
4. LangGraph 编排处理流程：
   - 记忆 → 检索 → 推理 → 回答
5. LLM 生成结合上下文的最终回答
6. 系统更新对话，并生成摘要供后续使用

## 🗂️ 项目结构

```
Rag-chatbot/
├── controllers/          # 路由处理逻辑（聊天、导入端点）
├── middlewares/          # 速率限制中间件
├── db/                   # Redis 和 ChromaDB 客户端
├── graph/
│   ├── builder.py        # LangGraph 流水线定义
│   └── nodes/            # 各个图节点（加载记忆、检索上下文、生成回答、摘要、存储记忆）
├── ingest/               # 增量文档导入流水线
├── prompts/
│   ├── answer.py         # 回答生成提示词
│   └── summarize.py      # 对话摘要提示词
├── schemas/
│   ├── chat.py           # ChatRequest 数据结构
│   └── ingest.py         # IngestRequest 数据结构
├── tests/
│   ├── conftest.py                      # 共享夹具（fakeredis、FakeEmbeddings、app_client）
│   ├── controllers/
│   │   ├── chat_controller_test.py      # 16 项测试：聊天 API
│   │   └── ingest_controller_test.py    # 7 项测试：导入端点
│   └── ingest/
│       └── policies_test.py             # 16 项测试：导入流水线逻辑
├── .github/
│   └── workflows/
│       └── ci.yml                       # CI 流水线（每次 PR/推送时运行单元测试）
├── main.py               # 应用入口
├── config.py             # 配置（pydantic-settings）
├── pytest.ini            # 测试配置
├── requirements.txt
├── requirements-dev.txt  # 测试依赖（pytest、fakeredis、responses、fpdf2）
└── docker-compose.yml
```

## ⚙️ 安装与配置

### 🧩 1. 安装运行环境

请先安装 [Miniconda](https://www.anaconda.com/download) 和
[Docker Desktop](https://www.docker.com/products/docker-desktop/)。

### 🐍 2. 创建环境

```bash
conda create -n chat-bot python=3.10
conda activate chat-bot
```

### 📦 3. 克隆项目并安装依赖

```bash
git clone https://github.com/Gikm2157/Rag-chatbot.git
cd Rag-chatbot
pip install -r requirements.txt
```

下载中文嵌入模型到项目目录：

```bash
git clone https://www.modelscope.cn/BAAI/bge-small-zh-v1.5.git models/bge-small-zh-v1.5
```

### ⚠️ 4. 配置环境变量

复制示例文件并填写你的配置值：

```bash
cp .env.example .env
```

主要变量：

```env
LLM_PROVIDER=openai
LLM_MODEL=deepseek-flash
OPENAI_API_KEY=your_deepseek_api_key_here
OPENAI_API_BASE=https://api.deepseek.com

EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=./models/bge-small-zh-v1.5

REDIS_HOST=localhost
REDIS_PORT=6379

RETRIEVAL_SCORE_THRESHOLD=0.3           # 如需更严格地依据知识库回答，可提高到 0.7
```

完整配置项请参见 [.env.example](.env.example)。

### 🚀 5. 启动服务器

```bash
uvicorn main:app --reload
```

服务器运行地址为 `http://127.0.0.1:8000`。

本地二次开发时，先用 Docker 启动 Redis，再启动 API：

```bash
docker compose up -d redis
uvicorn main:app --reload
```

也可以使用 Docker 运行完整服务：

```bash
docker compose up -d --build
```

## 📥 6. 文档导入（S3 → ChromaDB）

### 导入文档

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "file_name": "terms_conditions",
    "s3_url": "https://your-s3-url.pdf"
  }'
```

### 本地开发（无需 S3）

使用 Python 内置 HTTP 服务器提供 `samples/` 目录中的文件，导入流水线会像访问普通 URL 一样获取这些文件：

```bash
# 终端 1：提供本地 PDF
python -m http.server 8080

# 终端 2：导入示例文件
curl -X POST "http://127.0.0.1:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_name": "ecommerce_knowledge_base", "s3_url": "http://localhost:8080/samples/ecommerce_knowledge_base.pdf"}'
```

> **Docker 用户：**请将 `localhost` 替换为 `host.docker.internal`，使容器能够访问宿主机：
> `"s3_url": "http://host.docker.internal:8080/samples/ecommerce_knowledge_base.pdf"`

可直接使用的中文电商知识库样例请参见 [`samples/`](samples/)；有关如何准备自己的文档，请参见 [`docs/PDF_INGESTION_GUIDE.md`](docs/PDF_INGESTION_GUIDE.md)。

### 查看导入状态

```bash
curl http://127.0.0.1:8000/api/v1/ingest/terms_conditions
```

### 列出所有已导入文档

```bash
curl http://127.0.0.1:8000/api/v1/ingest/docs
```

### 删除文档

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/ingest/terms_conditions
```

## 📖 7. API 文档（Swagger）

服务器启动后，可以直接在浏览器中查看和测试所有端点：

```
http://127.0.0.1:8000/docs     # Swagger UI：交互式文档，可直接发送测试请求
http://127.0.0.1:8000/redoc    # ReDoc：简洁的只读参考文档
```

所有路由均使用 `/api/v1` 版本前缀。

## 💬 8. 聊天 API

### 端点

```
POST /api/v1/chat
```

### 请求

```json
{
  "q": "退货政策是什么？"
}
```

### 示例

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: user_123" \
  -d '{"q":"退货政策是什么？"}'
```

> `X-User-ID` 用于标识用户会话，系统会按用户分别存储和加载记忆。如省略该请求头，默认值为 `anonymous`。

## 🏥 9. 健康检查

```bash
curl http://127.0.0.1:8000/health
```

## 🧠 核心系统设计

### 🔹 记忆系统

Redis 存储以下内容：

- 完整对话历史
- 持续更新的对话摘要（用于长期上下文）
- 基于 TTL 的过期机制（可通过 `REDIS_TTL_SECONDS` 配置）

### 🔹 RAG 系统：增量导入 + MMR 检索

#### 导入流程

<div align="center">

```
POST /api/v1/ingest  { file_name, s3_url }
         │
         ▼
┌─────────────────────────────────────────────────┐
│  第 1 步：下载                                   │
│  requests.get(s3_url, stream=True)              │
│  • 强制执行 MAX_FILE_SIZE_MB 限制               │
│  • 写入磁盘上的临时 .pdf 文件                   │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  第 2 步：文件级去重检查                         │
│  SHA-256(file) → new_file_hash                  │
│                                                 │
│  Redis: GET ingest_status:{doc_id}.file_hash    │
│  ┌─ 哈希相同？───────────────────────────────┐  │
│  │  返回 { status: "skipped",               │  │
│  │         reason: "file unchanged" }        │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  Redis: HGET ingest:content_hashes new_hash     │
│  ┌─ 哈希已属于其他文档？─────────────────────┐  │
│  │  返回 { status: "skipped",               │  │
│  │         reason: "duplicate content       │  │
│  │         already ingested as '{doc}'" }   │  │
│  └───────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────┘
                     │  （文件是新增或已有变更）
                     ▼
┌─────────────────────────────────────────────────┐
│  第 3 步：解析并切分                             │
│  PyPDFLoader  →  原始页面                       │
│  RecursiveCharacterTextSplitter                 │
│    chunk_size=800, overlap=100                  │
│    separators: [\n\n, \n, ., " ", ""]         │
│  _clean_text()：合并多余空白字符                │
│  MD5(chunk_text) → 每个文本块的 chunk_hash      │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  第 4 步：文本块级差异比较                       │
│                                                 │
│  old_hashes = Redis SMEMBERS doc_chunks:{id}    │
│  new_hashes = 第 3 步生成的 MD5 集合            │
│                                                 │
│  stale = old_hashes − new_hashes                │
│    └─► 从 ChromaDB 删除这些文本块 ID            │
│                                                 │
│  fresh = new_hashes − old_hashes                │
│    └─► 只对这些文本块生成嵌入并加入 ChromaDB    │
│                                                 │
│  unchanged = 交集 → 跳过（不调用 API）          │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  第 5 步：更新 Redis 注册信息                    │
│  DEL  doc_chunks:{doc_id}                       │
│  SADD doc_chunks:{doc_id}  ← new_hashes         │
│  SADD ingest:doc_ids       ← doc_id             │
│  HDEL ingest:content_hashes old_file_hash       │
│  HSET ingest:content_hashes new_hash → doc_id   │
│  HSET ingest_status:{doc_id} 状态/哈希/数量     │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
        { status: "done", added, removed, total }
```

</div>

**导入流水线使用的 Redis 键：**

| 键 | 类型 | 用途 |
|----|------|------|
| `ingest_status:{doc_id}` | Hash | 每个文档的状态、文件哈希、版本和文本块数量 |
| `doc_chunks:{doc_id}` | Set | 当前版本中每个文本块的 MD5 哈希 |
| `ingest:doc_ids` | Set | 所有已导入文档 ID 的全局列表 |
| `ingest:content_hashes` | Hash | 将 `file_hash → doc_id`，用于识别使用不同文件名提交的相同 PDF |

#### 检索：得分门槛 + MMR（防止幻觉）

检索分两步进行，以防止 LLM 根据弱相关或不相关的匹配结果产生幻觉：

<div align="center">

```
用户问题
      │
      ▼
第 1 步：相关性门槛
similarity_search k=1  →  score < 0.3？
      │                         │
      │                         └──► docs = ""  →  “我们的知识库中没有相关
      │                                             信息，请联系客户支持。”
      │ score ≥ 0.3
      │ （问题与主题相关）
      ▼
第 2 步：MMR 检索
max_marginal_relevance_search k=3, fetch_k=10
      │
      ▼
3 个多样且相关的文本块 → LLM → 基于知识库的回答
```

</div>

**第 1 步：得分门槛。**获取最接近的一个文本块，并检查其余弦相似度得分。如果最佳匹配的得分仍低于 `0.3`，则认为问题偏离主题，系统不会向 LLM 提供推测性上下文。

**第 2 步：MMR。**仅在通过第 1 步后执行。系统获取 10 个候选文本块，并选出其中既相关又具有差异性的 3 个，避免将 3 个几乎相同的段落发送给 LLM。

**ChromaDB 配置为使用余弦距离**（`hnsw:space: cosine`），这是适合文本嵌入的度量方式。如果不进行此配置，得分将基于 L2 距离，可能出现负值，使阈值失去意义。

> 阈值可通过 `.env` 中的 `RETRIEVAL_SCORE_THRESHOLD` 配置（默认值为 `0.3`）。如需更严格地依据知识库回答，可提高到 `0.7`；如果过多有效问题被拒绝，可降低到 `0.2`。

### 🔹 LLM 层

可通过环境变量进行配置：

- 使用对话摘要（长期记忆）
- 使用近期消息（短期记忆）
- 使用检索到的上下文（RAG）
- 使用用户所用的语言生成最终回答（简体中文、阿拉伯语、英语）

## 🧠 主要功能

* ✅ 对话记忆（通过 Redis 实现短期和长期记忆）
* ✅ RAG 检索，结合余弦得分门槛（阈值 0.3）与 MMR 多样性排序
* ✅ 防止幻觉：在调用 LLM 前拦截偏离主题的问题
* ✅ 来源引用：每个回答都会包含所使用的源文档
* ✅ 对话式追问：未匹配到文档时，也能结合上下文回答后续问题
* ✅ 增量导入：只为有变化的文本块重新生成嵌入，而非处理整篇文档
* ✅ 导入保护：防止重复提交、限制文件大小、将失败状态保存到 Redis，并提供状态轮询端点
* ✅ 全局重复检测：通过内容哈希识别使用不同文件名提交的相同 PDF
* ✅ 速率限制：每个 IP 每分钟 60 个请求（由 Redis 支持，超限时返回 429）
* ✅ 默认接入 DeepSeek，并保留多个 LLM 提供商适配层
* ✅ 多语言回答（自动检测简体中文、阿拉伯语、英语）
* ✅ LangGraph 工作流编排
* ✅ 严格限制在知识库范围内回答，拒绝回答已导入文档之外的问题
* ✅ 面向生产环境的 FastAPI API 层
* ✅ 使用 Docker Compose 容器化（Redis 通过命名卷实现 AOF 持久化）
* ✅ 将结构化日志输出到控制台和滚动日志文件（`logs/app.log`，上限 10 MB）
* ✅ CI 流水线：每次发起 PR 或推送到 main 时自动运行单元测试

## 🧪 测试

单元测试分布在三个文件中，无需服务器、API 密钥或外部服务：

```bash
pytest tests/controllers/ tests/ingest/ -v
```

| 文件 | 覆盖内容 |
|------|----------|
| `tests/controllers/chat_controller_test.py` | 聊天 API、记忆隔离、速率限制、参数验证 |
| `tests/controllers/ingest_controller_test.py` | 状态查询、文档列表和删除端点 |
| `tests/ingest/policies_test.py` | 导入流水线：文本切分、去重、差异比较和错误处理 |

测试使用 `fakeredis`（内存 Redis）、`FakeEmbeddings`（不调用 OpenAI）和临时 ChromaDB，环境完全隔离且运行快速（约 1 秒）。

## 🧩 待办事项（路线图）

* [ ] 对导入流水线中的文本块进行分批流式处理，以支持数百万个文本块

## ⚡ 技术栈

* **后端：**FastAPI
* **LLM：**DeepSeek（OpenAI 兼容接口）
* **嵌入模型：**BAAI/bge-small-zh-v1.5
* **编排：**LangGraph
* **框架：**LangChain
* **向量数据库：**ChromaDB
* **缓存/记忆：**Redis
* **运行时：**Python 3.10
* **容器：**Docker + Docker Compose

---

## 📁 文档

| 指南 | 说明 |
|------|------|
| [docs/PDF_INGESTION_GUIDE.md](docs/PDF_INGESTION_GUIDE.md) | 如何让 PDF 顺利导入：文档结构规则、常见失败原因、验证脚本和上传前检查清单 |

遵循导入指南的示例 PDF 位于 [`samples/`](samples/) 目录。

---

## 🤝 参与贡献

欢迎提交问题和改进建议。有关开发环境配置、测试要求和拉取请求规范，请参见 [贡献指南](CONTRIBUTING.md)。

问题反馈请使用本仓库的 GitHub Issues；安全问题请使用 GitHub Security Advisory 私下报告。

---

## 📌 总结

本项目展示了一套面向中文企业知识库场景的 **RAG 智能客服架构**，结合了：

> RAG + 记忆 + LLM + 后端工程
