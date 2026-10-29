import os
import time
import json
import datetime
import requests
import feedparser

# 自定义请求头，降低 Reddit 等社区对云端容器 IP 的拦截概率
HEADERS = {
    "User-Agent": "linux:daily_news_agent:v1.0 (by /u/github_action_runner)"
}

def fetch_ai_hot_topics():
    """抓取过去 24 小时 AI 领域高热度讨论与论文"""
    items = []
    
    # 1. Hacker News Algolia API (按过去24小时点赞热度排序)
    try:
        yesterday_ts = int(time.time()) - 86400
        hn_url = (
            f"https://hn.algolia.com/api/v1/search?query=AI+OR+LLM+OR+Agent+OR+GPT+OR+Claude+OR+DeepSeek"
            f"&tags=story&numericFilters=created_at_i>{yesterday_ts}&hitsPerPage=12"
        )
        resp = requests.get(hn_url, timeout=15).json()
        for hit in resp.get("hits", []):
            title = hit.get("title")
            points = hit.get("points", 0)
            comments = hit.get("num_comments", 0)
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            if title:
                items.append(f"[HackerNews | 👍{points} 💬{comments}] {title} ({url})")
    except Exception as e:
        print(f"HN fetch warning: {e}")

    # 2. HuggingFace Daily Papers (当日最热 AI 论文)
    try:
        hf_url = "https://huggingface.co/api/daily_papers?limit=8"
        resp = requests.get(hf_url, timeout=15).json()
        for paper in resp:
            title = paper.get("title")
            upvotes = paper.get("paper", {}).get("upvotes", 0)
            paper_id = paper.get("paper", {}).get("id", "")
            url = f"https://huggingface.co/papers/{paper_id}"
            summary = paper.get("summary", "")[:180].replace("\n", " ")
            if title:
                items.append(f"[HuggingFace Paper | 👍{upvotes}] {title} - 摘要: {summary}... ({url})")
    except Exception as e:
        print(f"HF fetch warning: {e}")

    # 3. Reddit r/LocalLLaMA 24h Top
    items.extend(fetch_reddit_top("LocalLLaMA", limit=8))
    return "\n".join(items[:25])


def fetch_headphone_hot_topics():
    """抓取过去 24 小时耳机、IEM 与 Hi-Fi 音频高热话题"""
    items = []
    # 1. Reddit 垂直发烧友社区 24h 热榜
    for sub in ["headphones", "inearfidelity", "audiophile"]:
        items.extend(fetch_reddit_top(sub, limit=8))

    # 2. Head-Fi 官方最新热帖与中外音频 24 小时资讯 RSS (防拦截兜底)
    rss_urls = [
        ("Head-Fi", "https://www.head-fi.org/forums/-/index.rss"),
        ("GoogleNews-Audio", "https://news.google.com/rss/search?q=headphones+OR+IEM+OR+audiophile+OR+DAC+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("中文音频热点", "https://news.google.com/rss/search?q=%E8%80%B3%E6%9C%BA+OR+HiFi+OR+%E8%80%B3%E5%A1%9E+OR+%E5%A4%B4%E6%88%B4%E5%BC%8F%E8%80%B3%E6%9C%BA+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    ]
    for source_name, url in rss_urls:
        items.extend(fetch_rss_items(source_name, url, limit=6))

    return "\n".join(items[:25])


def fetch_music_hot_topics():
    """抓取过去 24 小时华语与全球音乐高热话题"""
    items = []
    # 1. Reddit 音乐社区 24h 热榜
    for sub in ["Music", "popheads", "indieheads"]:
        items.extend(fetch_reddit_top(sub, limit=6))

    # 2. 权威音乐媒体与华语乐坛 24 小时动态 RSS
    rss_urls = [
        ("Pitchfork", "https://pitchfork.com/feed/feed-news/rss"),
        ("Billboard", "https://www.billboard.com/feed/"),
        ("华语与全球乐坛24h", "https://news.google.com/rss/search?q=%E9%9F%B3%E4%B9%90+OR+%E6%96%B0%E6%AD%8C+OR+%E4%B8%93%E8%BE%91+OR+%E6%AD%8C%E6%89%8B+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    ]
    for source_name, url in rss_urls:
        items.extend(fetch_rss_items(source_name, url, limit=6))

    return "\n".join(items[:25])


def fetch_reddit_top(subreddit, limit=8):
    """通用 Reddit 24h 热帖抓取（JSON 优先，失败自动回退至 RSS）"""
    results = []
    json_url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limit}"
    try:
        resp = requests.get(json_url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            children = resp.json().get("data", {}).get("children", [])
            for post in children:
                data = post.get("data", {})
                title = data.get("title", "")
                score = data.get("score", 0)
                comments = data.get("num_comments", 0)
                permalink = f"https://www.reddit.com{data.get('permalink', '')}"
                selftext = data.get("selftext", "")[:150].replace("\n", " ")
                results.append(f"[r/{subreddit} | 👍{score} 💬{comments}] {title} - {selftext} ({permalink})")
            if results:
                return results
    except Exception as e:
        print(f"Reddit JSON fallback for r/{subreddit}: {e}")

    # 若 JSON 被限流，使用 RSS 回退
    rss_url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"
    return fetch_rss_items(f"r/{subreddit}", rss_url, limit=limit)


def fetch_rss_items(source_name, rss_url, limit=6):
    """通用 RSS 解析器"""
    results = []
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=12)
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:limit]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            if title:
                results.append(f"[{source_name}] {title} ({link})")
    except Exception as e:
        print(f"RSS fetch warning ({source_name}): {e}")
    return results


def summarize_with_llm(ai_raw, headphone_raw, music_raw):
    """调用大模型 API 提炼三大领域 Top 5 日报"""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").strip().rstrip("/")
    model_name = os.environ.get("LLM_MODEL", "glm-4-flash").strip()

    if not api_key:
        raise ValueError("未检测到 LLM_API_KEY 环境变量！请在 GitHub Secrets 中配置。")

    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")

    system_prompt = (
        "你是一位资深的科技、Hi-Fi 音频与音乐领域主笔。请根据用户提供的过去24小时多源热帖与资讯数据，"
        "分别筛选出【AI 与大模型】、【耳机与音频】、【音乐动态】三个领域当日讨论热度最高、最有价值的 Top 5 话题。"
    )

    user_prompt = f"""今天是 {today_str}。请根据下方采集到的原始动态，生成一份结构清晰、信息密度高的 Markdown 每日热度日报。

### 输出要求：
1. 分为三大板块：`## 🤖 AI 与大模型 Top 5`、`## 🎧 耳机与音频 Top 5`、`## 🎵 音乐动态 Top 5`。
2. 每个板块严格筛选出 **5 个最值得关注的热门话题**（优先选择点赞/评论热度高或行业实质性动态的话题，剔除水贴与重复内容）。
3. 每个话题包含：
   - **话题中文标题**（保留关键型号、模型名或音乐人原名）
   - **🔥 热度来源与指标**（注明来自哪个社区/媒体，以及点赞、评论数或上榜原因）
   - **📝 核心简介**（80~120字中文精炼概括：大家具体在讨论什么痛点、技术突破、听感评价或争议点）
   - **🔗 原文链接**（使用 Markdown 超链接 `[查看原帖](URL)` 格式保留原始链接）

---
【原始数据 1：AI 领域】
{ai_raw}

【原始数据 2：耳机与音频领域】
{headphone_raw}

【原始数据 3：音乐领域】
{music_raw}
"""

    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return f"# 📅 每日跨界热度日报 ({today_str})\n\n{content}"


def push_notifications(report_md):
    """输出到 GitHub 摘要页，并按需推送到微信或飞书"""
    # 1. 写入 GitHub Actions 原生运行摘要页（零配置即可在网页端查看排版效果）
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(report_md + "\n")
        print("已写入 GitHub Actions Job Summary 预览页。")

    # 2. 自动创建 reports 文件夹并保存归档日报
    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)  # 目录不存在会自动创建
    
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    archive_path = os.path.join(output_dir, f"{today_str}.md")
    
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"已生成归档日报文件: {archive_path}")
    # 同时保留一份 latest_report.md 供快速查看
    with open("latest_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    # 3. 可选推送：PushPlus (微信推送)
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if pushplus_token:
        try:
            requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": pushplus_token,
                    "title": "📅 今日 AI / 耳机 / 音乐 热度日报",
                    "content": report_md,
                    "template": "markdown"
                },
                timeout=15
            )
            print("PushPlus 微信推送成功。")
        except Exception as e:
            print(f"PushPlus 推送失败: {e}")

    # 4. 可选推送：飞书群机器人 Webhook
    feishu_webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if feishu_webhook:
        try:
            requests.post(
                feishu_webhook,
                json={
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {"tag": "plain_text", "content": "📅 每日 AI / 耳机 / 音乐 热度日报"},
                            "template": "blue"
                        },
                        "elements": [{"tag": "markdown", "content": report_md}]
                    }
                },
                timeout=15
            )
            print("飞书机器人推送成功。")
        except Exception as e:
            print(f"飞书推送失败: {e}")


if __name__ == "__main__":
    print("开始抓取三大领域过去 24 小时高热话题...")
    ai_data = fetch_ai_hot_topics()
    headphone_data = fetch_headphone_hot_topics()
    music_data = fetch_music_hot_topics()

    print("抓取完成，正在调用大模型生成日报...")
    report = summarize_with_llm(ai_data, headphone_data, music_data)

    print("日报生成完毕，正在执行发布与推送...")
    push_notifications(report)
    print("全部任务执行成功！")
