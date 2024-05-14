import streamlit as st
from gnews import GNews
from newspaper import Article, ArticleException
from rich.console import Console
from datetime import datetime
from zhipuai import ZhipuAI
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
import os

# 初始化 ZhipuAI 客户端
api_key = os.environ.get("ZHIPU_API_KEY")
# api_key = '65597dabfc8a8220298b47f25bbd0c65.FUXaG8j5PeArCsRc'
client = ZhipuAI(api_key=api_key)
# 创建一个Rich Console对象用于美化输出
console = Console()

# 获取新闻数据
def get_news(query: str, period: str) -> List[Dict]:
    google_news = GNews()
    google_news.period = period  # 设置新闻时间段
    google_news.max_results = 5  # number of responses across a keyword
    return google_news.get_news(query)

# 提取文章内容
def extract_content(url: str) -> str:
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except ArticleException as e:
        console.print(f"Error processing article: {url} - {e}", style="bold red")
        return ''

# 生成一段总结
def generate_summary(text: str) -> str:
    try:
        completion = client.chat.completions.create(
            model="glm-4",
            messages=[
                {"role": "system", "content": "你是文字解读机器人，会根据提供的文字内容，用一段汉语进行精简总结"},
                {"role": "user", "content": text}
            ],
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating summary: {e}")
        return "Error generating summary"



# 从给定的字典列表中提取"url"字段，并将所有的url组合到一起
def extract_urls(data: List[Dict[str, str]]) -> List[str]:
    return [item['url'] for item in data]

# 处理新闻项的内容抓取和总结生成
def process_news_item(item: Dict) -> str:
    content = extract_content(item['url'])
    if not content:  # 如果 content 为空
        return 'Try something else or change the trace back period'
    return generate_summary(f"{item['title']} {content}")

# 获取用户输入
user_input = st.sidebar.text_input('Key Words For News', 'Type here...')

# 创建一个滑条，用于调节新闻时间段
period = st.sidebar.select_slider(
    'Trace Back in days (Default 7d):',
    options=[1, 7, 14, 30, 90, 180, 365],
    value=7
)

# 将选择的时间段转为对应的字符串格式
period_mapping = {
    1: '1d',
    7: '7d',
    14: '14d',
    30: '1m',
    90: '3m',
    180: '6m',
    365: '1y'
}
period_str = period_mapping[period]

# 创建一个提交按钮
if st.sidebar.button('Submit'):
    news = get_news(user_input, period_str)
    summaries = []

    # 并行处理新闻内容的抓取和总结生成
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for item in news:
            future = executor.submit(process_news_item, item)
            futures.append(future)

        for future in futures:
            summaries.append(future.result())

    # 获取总结的合并结果
    bullet_summary = generate_summary('\n'.join(summaries))

    # 定义内容
    top_content = bullet_summary
    middle_content = summaries if summaries else ''
    bottom_content = extract_urls(news)

    # 显示内容
    st.write("# In Seconds")
    st.write(top_content)

    st.write("# Less than a Minute")
    # 将middle_content呈现为可点击链接格式
    st.write(middle_content)

    st.write("### Check out the Source")
    # 将链接呈现为可点击格式
    for url in bottom_content:
        st.markdown(f"[{url}]({url})")
