import json
import requests
import time
import re
from urllib.parse import quote

# --- 配置 ---
INPUT_FILE = "output_v5.jsonl"     # 带摘要的文件
OUTPUT_FILE = "final_output.jsonl" # 最终输出
SIMILARITY_THRESHOLD = 0.85 
PROXIES = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}
SLEEP_INTERVAL = 1.0
FAILED_LOG_FILE = "failed_titles.txt"  # <--- 新增：保存失败标题的文件
CANDIDATES_NUMS = 30

def normalize_title(title):
    if not title: return ""
    title = title.lower()
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def calculate_title_similarity(title1, title2):
    t1 = set(normalize_title(title1).split())
    t2 = set(normalize_title(title2).split())
    print(f't1: {t1}')
    print(f't2: {t2}')
    if not t1 or not t2: return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0

def process_citations():
    stats = {"total": 0, "success": 0, "failed": 0}
    
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
    except FileNotFoundError:
        print(f"❌ 错误：找不到文件 {INPUT_FILE}")
        return

    print(f"开始处理，共 {len(lines)} 条数据。\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f_out:
        for i, line in enumerate(lines):
            data = json.loads(line)
            original_title = data.get("title", "")
            stats["total"] += 1
            
            print(f"[{i+1}/{len(lines)}] 检索中: {original_title[:50]}...")
            
            found_bib = False
            try:
                # --- 修改点 1: h=10 获取更多候选 ---
                encoded_title = quote(original_title)
                search_url = f"https://dblp.org/search/publ/api?q={encoded_title}&format=json&h={CANDIDATES_NUMS}"
                response = requests.get(search_url, proxies=PROXIES, timeout=15)
                
                if response.status_code == 200:
                    res_json = response.json()
                    hits = res_json.get("result", {}).get("hits", {}).get("hit", [])
                    
                    # --- 修改点 2: 遍历候选结果 ---
                    for hit in hits:
                        hit_info = hit["info"]
                        hit_title = hit_info.get("title", "")
                        score = calculate_title_similarity(original_title, hit_title)
                        
                        if score >= SIMILARITY_THRESHOLD:
                            # 命中目标
                            dblp_url = hit_info.get("url")
                            bib_resp = requests.get(f"{dblp_url}.bib", proxies=PROXIES, timeout=15)
                            
                            if bib_resp.status_code == 200:
                                if "source" in data:
                                    del data["source"]
                                data["bibtex"] = bib_resp.text.strip()
                                stats["success"] += 1
                                found_bib = True
                                print(f"  ✅ 匹配成功! (Score: {score:.2f}, Title: {hit_title[:30]}...)")
                                break # 找到满意的了，跳出候选循环
                            else:
                                print('没有找到对应的bib文件')
                        else:
                            # 如果第一条没中，会继续循环看第二条
                            continue
                            
                    if not found_bib and hits:
                        print(f"  ⚠️ 尝试了 {len(hits)} 个候选，相似度均低于阈值或没找到对应的bib文件")
                    elif not hits:
                        print(f"  ❌ DBLP 库中无匹配项")
                        
                else:
                    print(f"  ❌ API 返回错误码: {response.status_code}")
                    
            except Exception as e:
                print(f"  🔥 网络异常: {e}")

            if not found_bib:
                stats["failed"] += 1
                # --- 新增：将失败的标题追加到日志文件 ---
                with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f_fail:
                    f_fail.write(f"{original_title}\n")

            f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
            time.sleep(SLEEP_INTERVAL)

    print(f"\n任务完成！成功: {stats['success']} | 失败: {stats['failed']}")
    if stats['failed'] > 0:
        print(f"📄 已将 {stats['failed']} 个失败标题保存至: {FAILED_LOG_FILE}")

if __name__ == "__main__":
    process_citations()