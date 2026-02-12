import json
import os

def merge_jsonl_files(input_files, output_file):
    seen_titles = set()
    total_count = 0
    
    # 使用上下文管理器确保输出文件安全打开
    with open(output_file, "w", encoding="utf-8") as outfile:
        for file_path in input_files:
            if not os.path.exists(file_path):
                print(f"跳过不存在的文件: {file_path}")
                continue
            
            print(f"正在处理: {file_path}...")
            
            with open(file_path, "r", encoding="utf-8") as infile:
                for line in infile:
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                        # 获取标题并进行标准化处理（去空格+小写）
                        title = data.get("title", "").strip().casefold()

                        # 核心去重逻辑
                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            # 直接写入文件，避免在大数据量时占用过多内存
                            outfile.write(json.dumps(data, ensure_ascii=False) + "\n")
                            total_count += 1
                    except json.JSONDecodeError:
                        print(f"跳过错误行（非有效JSON）: {line[:50]}...")

    print(f"\n--- 合并完成 ---")
    print(f"原始文件数量: {len(input_files)}")
    print(f"去重后总条数: {total_count}")
    print(f"保存路径: {output_file}")

# --- 用户配置区 ---
# 你可以在这里放入 1 到 N 个文件名
files_to_merge = [
    "1.jsonl",
    "2.jsonl"
]

output = "merged_citations.jsonl"

# 执行合并
merge_jsonl_files(files_to_merge, output)