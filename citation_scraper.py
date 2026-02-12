import os
import json
import time
from serpapi import GoogleSearch


# --- 配置区 ---
NEW_API_KEY = "your_serpapi_key"  # 在 https://serpapi.com 注册获取
TARGET_TITLE = "论文标题"          # 要查询的目标论文标题
SAVE_PATH = "output.jsonl"        # 输出文件路径

# 定义年份区间（一般start_year就是文章发表的年份）
# 拆得越细，越能避开 Google 的 1000 条限制
def generate_year_ranges(start_year, end_year):
    return [{"ylo": year, "yhi": year} for year in range(start_year, end_year + 1)]

start_year = 2020
end_year = 2026
YEAR_RANGES = generate_year_ranges(start_year, end_year)



def load_existing_titles():
    """读取已有标题用于去重，防止重复写入"""
    titles = set()
    if not os.path.exists(SAVE_PATH):
        return titles

    with open(SAVE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                titles.add(json.loads(line)["title"])
            except:
                pass
    return titles

def safe_fetch():
    # A. 获取 cites_id
    print(f"正在定位文章: {TARGET_TITLE}")
    search = GoogleSearch({
        "engine": "google_scholar",
        "q": TARGET_TITLE,
        "api_key": NEW_API_KEY
    })
    init_res = search.get_dict()
    
    try:
        cite_info = init_res["organic_results"][0]["inline_links"]["cited_by"]
        cites_id = cite_info["cites_id"]
        total_goal = cite_info["total"]
        print(f"成功获取 ID: {cites_id} | 总引用量约: {total_goal}")
    except:
        print("定位失败，请检查标题或 API Key。")
        return

    # B. 按年份循环抓取
    total_scraped = 0
    
    existing_titles = load_existing_titles()
    print(f"检测到已有 {len(existing_titles)} 条记录")
    
    for yr in YEAR_RANGES:
        ylo, yhi = yr["ylo"], yr["yhi"]
        print(f"\n>>> 正在抓取 {ylo}-{yhi} 年段的文献...")
        
        start = 0
        print(f"从 start={start} 继续抓取…")
        while True:
            params = {
                "engine": "google_scholar",
                "cites": cites_id,
                "api_key": NEW_API_KEY,
                "start": start,
                "as_ylo": ylo,
                "as_yhi": yhi
            }
            
            try:
                search = GoogleSearch(params)
                results = search.get_dict()
                print()
                
                # if "error" in results:
                #     print(f"API 错误: {results['error']}")
                #     return # 额度耗尽或 Key 失效直接退出
                if "error" in results:
                    error_msg = results["error"]
                    if "hasn't returned any results" in error_msg:
                        consecutive_errors += 1
                        print(f"  start={start:4d} | ⚠️  该页无结果 (跳过) | 连续错误: {consecutive_errors}")
                        
                        # 如果连续 3 次错误，或者已抓取数接近总数，判定为完成
                        current_total = len(existing_titles)
                        if consecutive_errors >= 3 or current_total >= total_goal:
                            print(f"   已抓取: {current_total} 条")
                            print(f"   总引用: {total_goal} 条")
                            break
                        
                        # 否则跳过这一页，继续下一页
                        start += 10
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"⚠️  API 错误: {error_msg}")
                        return

                papers = results.get("organic_results", [])
                if not papers:
                    print(f"--- {ylo}-{yhi} 段抓取完毕 ---")
                    break

                # 写入文件
                with open(SAVE_PATH, "a", encoding="utf-8") as f:
                    for p in papers:
                        item = {
                            "title": p.get("title"),
                            "abstract_snippet": p.get("snippet"),
                            "source": p.get("publication_info", {}).get("summary"),
                            "pdf": p.get("resources", [{}])[0].get("link") if p.get("resources") else None,
                        }
                        if item["title"] not in existing_titles:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                            existing_titles.add(item["title"])
                            total_scraped += 1

                print(f"  已抓取该段第 {start+10} 条 (累计: {total_scraped})")
                
                # 翻页判断
                if "next" in results.get("serpapi_pagination", {}):
                    start += 10
                else:
                    break
                    
                # 稍微缓冲，防止请求过快
                time.sleep(0.5)

            except Exception as e:
                print(f"发生意外: {e}，正在重试...")
                time.sleep(5)
                continue

    print(f"\n任务圆满完成！最终去重后的文献保存在: {SAVE_PATH}")

if __name__ == "__main__":
    safe_fetch()