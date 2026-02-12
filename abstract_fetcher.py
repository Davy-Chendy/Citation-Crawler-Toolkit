import json
import time
import requests
import random
from bs4 import BeautifulSoup
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import signal
import sys
import re
import ssl
from xml.etree import ElementTree as ET

# 忽略 SSL 证书检查
ssl._create_default_https_context = ssl._create_unverified_context

# --- 配置 ---
INPUT_FILE = "input.jsonl"    # 待补全的文件
OUTPUT_FILE = "output.jsonl"  # 输出文件
MAX_WORKERS = 10 
SIMILARITY_THRESHOLD = 0.85
MAIL_TO = "your_email@example.com"  # 提供邮箱可提升请求优先级

# 代理配置
PROXIES = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}

# User-Agent 轮换
UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    print("\n\n⚠️  接收到中断信号，正在安全退出...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)

# --- 工具函数 ---

def normalize_title(title):
    if not title: return ""
    title = title.lower()
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def calculate_title_similarity(title1, title2):
    t1 = set(normalize_title(title1).split())
    t2 = set(normalize_title(title2).split())
    if not t1 or not t2: return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0

# --- 爬取函数 ---

def fetch_openalex_abstract(title):
    """从 OpenAlex API 通过标题搜索获取摘要"""
    if shutdown_flag: return None, None
    try:
        base_url = "https://api.openalex.org/works"
        params = {
            'search': title,
            'per-page': 1,
            'mailto': MAIL_TO
        }
        headers = {'User-Agent': 'Mozilla/5.0 (research purposes)'}
        
        response = requests.get(base_url, params=params, headers=headers, timeout=15, proxies=PROXIES)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                work = results[0]
                found_title = work.get('title', '')
                
                # 校验标题相似度
                if calculate_title_similarity(title, found_title) < SIMILARITY_THRESHOLD:
                    return None, f"OpenAlex标题匹配分低"

                abstract = None
                # 方式1: 直接字段
                if work.get('abstract'):
                    abstract = work['abstract']
                # 方式2: 重建倒排索引
                elif work.get('abstract_inverted_index'):
                    inverted_index = work['abstract_inverted_index']
                    word_positions = []
                    for word, positions in inverted_index.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = ' '.join([word for _, word in word_positions])
                
                if abstract and len(abstract) >= 100:
                    return abstract, None
                return None, "摘要过短"
    except Exception as e:
        return None, f"OpenAlex错误: {str(e)}"
    return None, "OpenAlex无结果"

def fetch_arxiv_abstract(title):
    if shutdown_flag: return None, None
    try:
        clean_title = title.replace('"', '')
        query = f'ti:"{clean_title}"'
        url = f"http://export.arxiv.org/api/query?search_query={quote(query)}&max_results=3"
        response = requests.get(url, proxies=PROXIES, timeout=30)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)
            best_score, best_summary = 0, None
            for entry in entries:
                f_title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                score = calculate_title_similarity(title, f_title)
                if score > best_score:
                    best_score, best_summary = score, entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            if best_summary and best_score >= SIMILARITY_THRESHOLD:
                return best_summary, None
            return None, f"ArXiv匹配分低({best_score:.2f})"
    except Exception as e:
        return None, f"ArXiv错误: {str(e)}"
    return None, "ArXiv无结果"

def fetch_google_scholar_abstract(title):
    if shutdown_flag: return None, None
    headers = {'User-Agent': random.choice(UA_LIST), 'Referer': 'https://scholar.google.com/'}
    try:
        search_url = f"https://scholar.google.com/scholar?q=allintitle:{quote(title)}"
        response = requests.get(search_url, headers=headers, proxies=PROXIES, timeout=50)
        if "detected unusual traffic" in response.text:
            return None, "Scholar BLOCK"
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('div', class_='gs_ri')
        if results:
            title_tag = results[0].find('h3', class_='gs_rt')
            for span in title_tag.find_all('span'): span.decompose()
            found_title = title_tag.get_text().strip()
            score = calculate_title_similarity(title, found_title)
            if score >= SIMILARITY_THRESHOLD:
                snippet = results[0].find('div', class_='gs_rs')
                if snippet: return snippet.get_text().strip(), None
                return None, "Scholar无摘要"
            return None, f"Scholar匹配分低({score:.2f})"
    except Exception as e:
        return None, f"Scholar错误: {str(e)}"
    return None, "Scholar未找到"

# --- 核心逻辑 ---

def process_paper(item):
    if shutdown_flag: return None, False, None, None
    
    # 断点续传逻辑
    if "Abstract" in item and item["Abstract"] and len(item["Abstract"]) > 100:
        return item, False, "Skipped", "Already Done"

    title = item.get('title', '')
    original_snippet = item.get('abstract_snippet') or item.get('Abstract') or ''
    if not title: return item, False, None, "无标题"
    
    # 按照优先级尝试：OpenAlex -> ArXiv -> Scholar
    # 1. OpenAlex
    abstract, err = fetch_openalex_abstract(title)
    if abstract:
        item["Abstract"] = abstract
        item.pop("abstract_snippet", None)
        return item, True, "OpenAlex", None
    
    # 2. ArXiv
    abstract, arxiv_err = fetch_arxiv_abstract(title)
    if abstract:
        item["Abstract"] = abstract
        item.pop("abstract_snippet", None)
        return item, True, "ArXiv", None
    
    # 3. Scholar
    abstract, scholar_err = fetch_google_scholar_abstract(title)
    if abstract:
        item["Abstract"] = abstract
        item.pop("abstract_snippet", None)
        return item, True, "Scholar", None
    
    # 失败整合原因
    reason = f"OA:{err} | AX:{arxiv_err} | GS:{scholar_err}"
    item["abstract_snippet"] = original_snippet
    item.pop("Abstract", None)
    return item, False, None, reason

def main():
    global shutdown_flag
    papers = []
    print(f"📖 读取文件: {INPUT_FILE}")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try: papers.append(json.loads(line))
            except: pass
    
    print(f"✓ 共找到 {len(papers)} 篇论文 | 相似度阈值: {SIMILARITY_THRESHOLD}")
    
    results, not_found_papers = [], []
    found_count = 0
    # counts = {"OpenAlex": 0, "ArXiv": 0, "Scholar": 0}
    # 修改这里
    counts = {"OpenAlex": 0, "ArXiv": 0, "Scholar": 0, "Skip": 0}
    
    pbar = tqdm(total=len(papers), desc="处理进度", unit="篇")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_paper, p): p for p in papers}
            for future in as_completed(futures):
                if shutdown_flag: break
                try:
                    result, found, source, reason = future.result(timeout=60)
                    if result is None: continue
                    
                    results.append(result)
                    f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
                    f_out.flush()

                    if source == "Skipped":
                        found_count += 1
                        counts["Skip"] += 1  # 计入新的 Skip 统计项
                        # 更新进度条显示
                        pbar.set_postfix({
                            'OA': counts["OpenAlex"],
                            'AX': counts["ArXiv"],
                            'GS': counts["Scholar"],
                            'Skip': counts["Skip"], # 进度条会显示 Skip 数量
                            '失败': len(not_found_papers),
                            '成功率': f"{found_count/len(results)*100:.1f}%"
                        })
                        pbar.update(1)
                        continue

                    if found:
                        found_count += 1
                        counts[source] = counts.get(source, 0) + 1
                    else:
                        not_found_papers.append({'title': result['title'], 'reason': reason})
                    
                    # 更新进度条
                    pbar.set_postfix({
                        'OA': counts["OpenAlex"],
                        'AX': counts["ArXiv"],
                        'GS': counts["Scholar"],
                        'Skip': counts["Skip"], # 进度条会显示 Skip 数量,
                        '失败': len(not_found_papers),
                        '成功率': f"{found_count/len(results)*100:.1f}%" if results else "0%"
                    })
                    pbar.update(1)
                except Exception as e:
                    if not shutdown_flag: tqdm.write(f"⚠️ 处理出错: {e}")
                    pbar.update(1)

    pbar.close()
    
    print("\n" + "=" * 80)
    print(f"{'⚠️ 程序中断' if shutdown_flag else '✅ 完成！'}")
    print(f"📊 统计信息:")
    print(f"   - 本次运行处理: {len(results)} 篇")
    print(f"   - 成功找到完整摘要: {found_count}")
    for k, v in counts.items():
        print(f"      ├─ {k}: {v}")
    
    if not_found_papers:
        not_found_file = "not_found_abstracts.txt"
        with open(not_found_file, 'w', encoding='utf-8') as f:
            f.write(f"未找到详细报告 (共 {len(not_found_papers)} 篇)\n" + "="*40 + "\n")
            for p in not_found_papers:
                f.write(f"题目: {p['title']}\n原因: {p['reason']}\n\n")
        print(f"📝 失败详情已记录至: {not_found_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()

