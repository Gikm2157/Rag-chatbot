# PDF 导入指南

本指南说明什么样的 PDF 能够顺利导入此聊天机器人的知识库。添加文档前请先阅读本指南，因为结构不佳的 PDF 会导致检索效果差、产生幻觉或返回空答案。

---

## 流水线的工作原理

了解流水线有助于理解某些 PDF 导入失败的原因：

```
PDF 文件
   │
   ▼
PyPDFLoader          — 提取文本层（无法处理扫描件或纯图片 PDF）
   │
   ▼
RecursiveCharacterTextSplitter
  chunk_size=800, overlap=100
  separators: [\n\n, \n, ., " ", ""]   — 优先按段落 → 行 → 句子边界切分
   │
   ▼
text-embedding-3-small   — 将每个文本块转换为向量
   │
   ▼
ChromaDB（余弦相似度）
```

查询时会**独立检索**每个文本块。机器人每次回答问题只能看到 3 个文本块，因此每个文本块都必须内容完整，并且能够独立表达明确含义。

---

## 推荐做法

### 文档结构

| 做法 | 作用 |
|------|------|
| 使用清晰的章节标题，后接 `\n\n` | 切分器会优先使用段落分隔符，标题有助于形成清晰的文本块边界 |
| 每段只讨论一个主题 | 每个文本块只包含一个观点，可提高检索精度 |
| 每段 100～300 个单词 | 能够轻松容纳在 800 字符的文本块窗口中 |
| 使用编号列表或单层项目符号列表 | 可提取为易读的文本行；嵌套项目符号通常会被错误合并 |
| 每句话都明确写出主语 | 机器人拿到的 3 个文本块没有周边上下文，因此应避免大量使用“它”“这”“他们”等代词 |

### 文件质量

| 做法 | 作用 |
|------|------|
| 导出为基于文本的 PDF（Word/Google Docs → 另存为 PDF） | `PyPDFLoader` 可以直接读取文本层，无需 OCR |
| 使用单栏布局 | 多栏 PDF 会跨栏从左向右提取文字，导致无关内容合并 |
| 不使用包含页码的页眉或页脚 | 页码会被嵌入文本块中，例如在句子中插入 `"Page 4 of 12"` |
| 使用兼容 UTF-8 的内容 | 确保非 ASCII 字符能够被正确提取 |

---

## 导致导入异常的情况

| 问题 | 后果 |
|------|------|
| **扫描版 PDF（仅含图片）** | `PyPDFLoader` 提取到空字符串，最终保存 0 个文本块；状态为 `done`，但 `total=0` |
| **多栏布局** | 不同栏的内容在句子中间被合并，产生语义混乱的文本块和较低的检索得分 |
| **使用表格存放关键信息** | 表格会被提取为以制表符或空格分隔的片段，而不是可读的句子 |
| **超过 1000 字符的密集段落** | 切分器会退而按 `.` 或空格切分，可能从句子中间截断 |
| **大量使用代词** | 检索到的文本块可能只有“它适用于他们”，却没有所指对象，导致 LLM 无法正确回答 |
| **受密码保护的 PDF** | `PyPDFLoader` 抛出异常，导入失败，并在 Redis 中将状态保存为 `failed` |
| **混合布局中的阿拉伯语或从右到左文本** | 某些 PDF 生成器会导致文本提取后的字符顺序颠倒 |
| **每页重复的样板内容** | 页眉、页脚和水印会与正文一起被切分，降低嵌入内容的相关性 |

---

## 推荐的 PDF 结构

创建待导入文档时，请采用以下结构：

```
文档标题

第 1 节标题

第 1 节的第一段。只围绕一个明确的主题展开。句子应当完整，
即使没有上一段的上下文也能独立表达清楚。

如有需要，可添加第二段。每段应保持在 100～300 个单词。

第 2 节标题

第 2 节的第一段。每段都应明确指出讨论对象，
不要使用“它”或“本政策”这类依赖上下文的代词。
```

**关键规则：**

- 使用空行（`\n\n`）分隔章节，这是切分器首选的断点
- 每个段落只关注一个观点
- 避免嵌套结构，使用单层列表代替多级项目符号层次
- 将重要事实写成完整段落，不要只放在表格中

---

## 导入前快速验证

上传前，可对任意 PDF 运行以下脚本，检查流水线实际能够提取出的内容：

```python
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

pages = PyPDFLoader("your_document.pdf").load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ".", " ", ""]
)
chunks = splitter.split_documents(pages)

print(f"页数：{len(pages)} | 文本块数：{len(chunks)}\n")
for i, chunk in enumerate(chunks[:5]):
    print(f"--- 文本块 {i+1} ---")
    print(chunk.page_content[:300])
    print()
```

**良好的输出：**文本块中的段落可正常阅读，且每块内容都能独立表达完整含义。

**异常的输出：**字符乱码、不同栏内容合并、空字符串或零散的页码片段。

---

## 示例 PDF

[`samples/`](../samples/) 目录中包含 5 个可直接使用的示例 PDF。它们遵循上述全部指南，无需额外处理即可顺利导入：

| 文件 | 内容 |
|------|------|
| `return_refund_policy.pdf` | 退货资格、RMA 流程、退款时间和换货政策 |
| `shipping_policy.pdf` | 国内与国际配送、物流跟踪和包裹丢失处理 |
| `privacy_policy.pdf` | 数据收集与使用、GDPR 权利和 Cookie |
| `terms_and_conditions.pdf` | 平台使用、定价、知识产权和责任 |
| `customer_support_policy.pdf` | 客服渠道、响应时间和升级流程 |

使用这些文件在本地测试导入流水线：

```bash
# 启动服务器
uvicorn main:app --reload

# 导入示例（请替换为实际托管 URL 或本地文件服务器地址）
curl -X POST "http://127.0.0.1:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_name": "return_refund_policy", "s3_url": "https://your-bucket.s3.amazonaws.com/return_refund_policy.pdf"}'

# 查看导入状态
curl http://127.0.0.1:8000/api/v1/ingest/return_refund_policy
```

---

## PDF 上传前检查清单

- [ ] PDF 由文字处理软件导出，并非扫描件
- [ ] 使用单栏布局
- [ ] 未设置密码保护
- [ ] 每个段落不超过 300 个单词
- [ ] 每句话都明确写出主语，不使用指代不明的代词
- [ ] 关键信息并非只存放在表格中
- [ ] 已使用上述快速验证脚本进行检查，文本块清晰可读
