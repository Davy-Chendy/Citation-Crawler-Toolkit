# Citation-Crawler-Toolkit

A comprehensive toolkit for crawling, enriching, and managing academic citation data. This project provides a complete pipeline to collect citations of a target paper, merge duplicate records, fetch full abstracts, and retrieve BibTeX entries.

一个全面的学术引文数据爬取、补全和管理工具包。本项目提供了完整的工作流程，用于收集目标论文的引用文献、合并去重、获取完整摘要以及检索BibTeX引用格式。

---

## 项目概述

本工具链专为学术研究人员设计，用于系统性地收集和整理某篇论文的引用文献信息。整个流程分为4个步骤，每个步骤对应一个Python脚本。

### 工作流程

```
目标论文 
   ↓
[1] citation_scraper.py → 爬取被引文献基本信息
   ↓
[2] citation_merger.py → 合并多个文件并去重 [可选，当第一步设置好起始年份一次爬取成功时，可以跳过第二步]
   ↓  
[3] abstract_fetcher.py → 补全完整摘要 (增量式更新)
   ↓
[4] bibtex_fetcher.py → 获取BibTeX引用格式
   ↓
完整引文数据库
```

---

## 环境配置

### 依赖安装

```bash
pip install serpapi requests beautifulsoup4 tqdm --break-system-packages
```

### 代理配置

**⚠️ 重要：所有脚本都需要配置代理才能访问Google Scholar等国际网站**

在脚本中修改 `PROXIES` 配置：

```python
PROXIES = {
    "http": "http://127.0.0.1:7890",   # 修改为你的代理端口
    "https": "http://127.0.0.1:7890"
}
```

常用代理工具：Clash、V2Ray、Shadowsocks等

---

## 脚本详解

### 1. citation_scraper.py - 爬取被引文献

#### 功能
通过SerpAPI从Google Scholar爬取目标论文的所有被引文献。

#### 输入参数
```python
NEW_API_KEY = "your_serpapi_key"  # 在 https://serpapi.com 注册获取
TARGET_TITLE = "论文标题"          # 要查询的目标论文标题
SAVE_PATH = "output.jsonl"        # 输出文件路径
```

#### 输出
生成 `.jsonl` 文件，每行为一条引用记录：
```json
{
  "title": "论文标题",
  "abstract_snippet": "摘要片段",
  "source": "期刊/会议信息",
  "pdf": "PDF链接"
}
```

#### 关键配置

**年份分段策略**
```python
YEAR_RANGES = generate_year_ranges(start_year, end_year)  # 按年份分段爬取，start_year 一般是文章发表的年份
```
- 分段越细越能避开Google Scholar的1000条限制
- 建议按年度拆分

**断点续传**
- 脚本会自动检测已存在的文件并跳过重复标题
- 中断后可直接重新运行，无需从头开始

#### ⚠️ 注意事项

1. **API额度管理**
   - SerpAPI免费计划有调用次数限制
   - 脚本会在检测到额度耗尽时自动退出
   
2. **请求间隔**
   - 默认每次请求间隔0.5秒 (`time.sleep(0.5)`)
   - 避免过快请求导致封禁

3. **错误处理**
   - 连续3次无结果自动跳过该年份段
   - 可根据实际情况调整 `consecutive_errors` 阈值

---

### 2. citation_merger.py - 合并去重 [ 可选，当第一步设置好起始年份一次爬取成功时，可以跳过第二步 ]

#### 功能
合并多个引文数据文件，基于标题进行去重。

#### 输入
```python
files_to_merge = [
    "file1.jsonl",
    "file2.jsonl",
    "file3.jsonl"
]
```

#### 输出
```python
output = "merged_citations.jsonl"  # 合并后的去重文件
```

#### 去重逻辑
- 标题标准化：去除空格 + 小写转换 (`strip().casefold()`)
- 保留第一次出现的记录
- 内存友好：逐行处理，适合大文件

#### ⚠️ 注意事项

1. **文件缺失处理**
   - 自动跳过不存在的文件并打印提示
   
2. **错误行处理**
   - 自动跳过非JSON格式的错误行
   - 建议事后检查输出

---

### 3. abstract_fetcher.py - 获取完整摘要 ⭐

#### 功能
按优先级从OpenAlex → ArXiv → Google Scholar获取完整摘要。

#### 输入/输出
```python
INPUT_FILE = "input.jsonl"    # 待补全的文件
OUTPUT_FILE = "output.jsonl"  # 输出文件
```

#### 核心机制

**增量式更新（断点续传）**
```python
# 已有完整摘要的记录会被自动跳过
if "Abstract" in item and len(item["Abstract"]) > 100:
    return item, False, "Skipped", "Already Done"
```

**使用流程（重要！）**
```bash
# 第1次运行
INPUT_FILE = "merged_citations.jsonl"
OUTPUT_FILE = "output_v1.jsonl"

# 第2次运行（继续补全）
INPUT_FILE = "output_v1.jsonl"  # 使用上次输出作为输入
OUTPUT_FILE = "output_v2.jsonl"

# 重复执行直到 "失败数" 不再减少
```

#### 参数配置

**标题相似度阈值**
```python
SIMILARITY_THRESHOLD = 0.85  # 0-1之间，越高越严格
```
- 用于验证搜索结果是否匹配原标题
- 建议保持0.85，过低会引入错误数据

**并发配置**
```python
MAX_WORKERS = 10  # 并发线程数
```
- 值越大速度越快，但可能导致封禁
- 建议5-10之间

**OpenAlex礼貌通道**
```python
MAIL_TO = "your_email@example.com"  # 提供邮箱可提升请求优先级
```

#### 三数据源说明

| 数据源 | 优势 | 劣势 |
|--------|------|------|
| **OpenAlex** | 稳定、无限制、摘要质量高 | 覆盖率约60% |
| **ArXiv** | 预印本覆盖全、无需认证 | 仅限CS/Physics领域 |
| **Google Scholar** | 覆盖率最高 | 易封禁、需代理 |

#### ⚠️ 关键注意事项

1. **Google Scholar封禁问题**
   - 最不稳定的数据源，很容易触发 "detected unusual traffic"
   - **解决方案**：
     - 更换代理节点/IP
     - 降低并发数 (`MAX_WORKERS = 3`)
     - 增加请求间隔
   
2. **多次执行策略**
   - 每次运行后检查 `not_found_abstracts.txt`
   - Scholar封禁时会有大量 "Scholar BLOCK" 错误
   - 更换节点后重新运行，直到失败数稳定

3. **手动补全**
   - 部分小众论文三个数据源都找不到
   - 最后需手动打开PDF提取摘要
   - 建议使用 `not_found_abstracts.txt` 作为待办清单

4. **代理配置**
   - **必须配置全局代理**，否则无法访问国际数据库

#### 输出说明

**进度条显示**
```
处理进度: 85%|████████▌| 850/1000 [12:34<02:15, OA:400, AX:120, GS:200, Skip:100, 失败:80, 成功率:87.5%]
```

**失败详情文件**
```
not_found_abstracts.txt  # 记录所有失败的论文及原因
```

---

### 4. bibtex_fetcher.py - 获取BibTeX

#### 功能
从DBLP数据库获取标准BibTeX引用格式。

#### 输入/输出
```python
INPUT_FILE = "output_v5.jsonl"     # 带摘要的文件
OUTPUT_FILE = "final_output.jsonl" # 最终输出
```

#### 输出字段变化
```python
# 输入记录
{
  "title": "...",
  "Abstract": "...",
  "source": "Conference 2024"  # 原始来源信息
}

# 成功匹配后
{
  "title": "...",
  "Abstract": "...",
  "bibtex": "@inproceedings{...}"  # source字段被删除，替换为bibtex
}

# 匹配失败时
{
  "title": "...",
  "Abstract": "...",
  "source": "Conference 2024"  # 保留原source字段
}
```

#### 参数配置

**搜索候选数量**
```python
search_url = f"https://dblp.org/search/publ/api?q={encoded_title}&format=json&h={CANDIDATES_NUMS}"
#                                                                              ↑ 增加候选数
```
- `h=30` 表示获取前30个候选结果
- 值越大越可能找到匹配，但速度会变慢

**相似度阈值**
```python
SIMILARITY_THRESHOLD = 0.85
```

#### ⚠️ 注意事项

1. **失败标题日志**
   ```
   failed_titles.txt  # 自动记录所有匹配失败的标题
   ```
   - 用于最后手动补全BibTeX

2. **请求间隔**
   ```python
   SLEEP_INTERVAL = 1.0  # 每次请求间隔1秒
   ```
   - DBLP服务器相对宽松，但仍建议保持间隔

3. **DBLP覆盖范围**
   - 主要覆盖计算机科学领域
   - 其他领域论文可能需要从其他来源获取BibTeX

4. **手动补全建议**
   - 使用 `failed_titles.txt` 作为待办清单
   - 推荐工具：Google Scholar、Semantic Scholar、ResearchGate

---

## 完整使用示例

```bash
# 第1步：爬取被引文献
python citation_scraper.py
# 输出：tent_2025-2026_citations.jsonl

# 第2步：合并多个时间段的数据
python citation_merger.py
# 输出：merged_tent_citations.jsonl

# 第3步：获取完整摘要（多次迭代）
python abstract_fetcher.py  # 第1次：input=merged, output=v1
python abstract_fetcher.py  # 第2次：input=v1, output=v2
python abstract_fetcher.py  # 第3次：input=v2, output=v3
# ... 直到失败数稳定
# 输出：output_v5.jsonl

# 第4步：获取BibTeX
python bibtex_fetcher.py
# 输出：final_output.jsonl

# 第5步：手动补全
# 根据 not_found_abstracts.txt 和 failed_titles.txt 手动添加缺失数据
```

---

## 常见问题 (FAQ)

### Q1: SerpAPI显示 "API错误: 额度耗尽"
**A:** 
- 免费账户每月250次查询
- 可以注册多个账户轮换使用
- 或升级付费计划

### Q2: Google Scholar频繁封禁怎么办？
**A:** 
1. 更换代理节点
2. 降低并发数到3-5
3. 增加请求间隔到3-5秒
4. 间隔1-2小时后重试

### Q3: abstract_fetcher.py运行很久还有很多失败？
**A:** 
- 这是正常现象，部分论文确实三个数据源都没有
- 持续运行直到失败数不再减少
- 最后需要手动补全

### Q4: 如何判断abstract_fetcher.py已经完成？
**A:** 
连续2-3次运行后：
- 成功率不再提升（稳定在80-90%）
- `not_found_abstracts.txt` 内容不再变化
- 进度条中 "Skip" 数量接近总数

### Q5: 代理配置后还是无法访问？
**A:** 
检查：
1. 代理软件是否开启全局模式
2. 端口号是否正确（常见：7890, 1080, 10809）
3. 测试命令：`curl --proxy http://127.0.0.1:7890 https://google.com`

### Q6: DBLP找不到BibTeX怎么办？
**A:** 
替代方案：
1. Google Scholar → 点击 "引用" → 复制BibTeX
2. Semantic Scholar → 论文页面 → "Cite" → BibTeX
3. 直接搜索论文DOI → 从出版商网站获取

---

## 数据格式说明

### 最终输出格式

```json
{
  "title": "Tent: Fully Test-Time Adaptation by Entropy Minimization",
  "Abstract": "We present a novel approach for test-time adaptation...",
  "bibtex": "@inproceedings{wang2021tent,\n  title={Tent: Fully Test-Time Adaptation by Entropy Minimization},\n  author={Wang, Dequan and Shelhamer, Evan and Liu, Shaoteng and Olshausen, Bruno and Darrell, Trevor},\n  booktitle={International Conference on Learning Representations},\n  year={2021}\n}",
  "pdf": "https://arxiv.org/pdf/2006.10726.pdf"
}
```

### 字段说明

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| `title` | string | 论文标题 | SerpAPI |
| `Abstract` | string | 完整摘要 | OpenAlex/ArXiv/Scholar |
| `bibtex` | string | BibTeX引用 | DBLP |
| `pdf` | string (可选) | PDF链接 | SerpAPI |
| `source` | string (fallback) | 原始来源信息 | 仅在bibtex获取失败时保留 |

---

### 准确性优化
1. 提高相似度阈值（0.90）以减少误匹配
2. 人工复核关键论文的数据
3. 对比多个数据源的摘要选择最完整的

---