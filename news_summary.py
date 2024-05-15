import streamlit as st
from gnews import GNews
from newspaper import Article, ArticleException
from rich.console import Console
from datetime import datetime
from zhipuai import ZhipuAI
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import logging
import requests

# 初始化 ZhipuAI 客户端
api_key = os.environ.get("ZHIPU_API_KEY")
client = ZhipuAI(api_key=api_key)
# 创建一个Rich Console对象用于美化输出
console = Console()

# 定义一个正则表达式来匹配 URL
# url_pattern = re.compile(
#     r'(?:(?:http|https):\/\/)?' # 可选的 http:// or https://
#     r'(?:www\.)?' # 可选的 www.
#     r'[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\/[^\s]*)?' # 域名和可选的路径
# )
# 定义一个正则表达式来匹配 URL
url_pattern = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# 判断用户输入是否包含链接并提取链接
def contains_link(user_input: str) -> tuple:
    links = url_pattern.findall(user_input)
    if links:
        return True, links
    return False, []

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

# 从 Jina.ai 提取文章内容
def extract_content_from_jina(url: str) -> str:
    full_url = f"http://r.jina.ai/{url}"
    try:
        response = requests.get(full_url)
        if response.status_code == 200:
            html_content = response.text
            
            # 提取 Title
            start_title = html_content.find('Title:')
            end_title = html_content.find('URL Source:')
            title = html_content[start_title + len('Title:'):end_title].strip()

            # 提取 URL Source
            start_url = html_content.find('URL Source:')
            end_url = html_content.find('Markdown Content:')
            url_source = html_content[start_url + len('URL Source:'):end_url].strip()

            # 提取 Markdown 内容
            markdown_content = html_content[end_url + len('Markdown Content:'):].strip()

            return {
                "title": title,
                "url_source": url_source,
                "content": markdown_content
            }
        else:
            console.print(f"Error fetching Jina content: {url} - Status code: {response.status_code}", style="bold red")
            return ''
    except requests.RequestException as e:
        console.print(f"Error fetching Jina content: {url} - {e}", style="bold red")
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

# 处理新闻项的内容抓取和总结生成
def process_news_item(item: Dict) -> str:
    content = extract_content(item['url'])
    if not content:  # 如果 content 为空
        return 'Try something else or change the trace back period'
    return generate_summary(f"{item['title']} {content}")

# 左侧边栏描述
st.sidebar.markdown("# Welcome to PharmaSignal Info Summary")
st.sidebar.markdown("### Enter keywords (e.g., gpt4o, google I/O) for news summary")
st.sidebar.markdown("### or Weblink(s) for web summary")


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
    contains_link_flag, links = contains_link(user_input)
    if contains_link_flag:
        # 提取并处理链接内容
        summaries = []
        with st.spinner('Fetching and summarizing content from provided links...'):
            progress_bar = st.progress(0)
            for i, link in enumerate(links):
                jina_content = extract_content_from_jina(link)
                if jina_content and 'content' in jina_content:
                    summary = generate_summary(jina_content['content'])
                    summaries.append(summary)
                else:
                    summaries.append('Try something else or change the trace back period')
                progress_bar.progress((i + 1) / len(links))
    else:
        news = get_news(user_input, period_str)
        summaries = []

        with st.spinner('Fetching news articles and generating summaries...'):
            progress_bar = st.progress(0)
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(process_news_item, item): item for item in news}
                for i, future in enumerate(as_completed(futures)):
                    summaries.append(future.result())
                    progress_bar.progress((i + 1) / len(news))

    # 获取总结的合并结果
    bullet_summary = generate_summary('\n'.join(summaries))

    # 定义内容
    top_content = bullet_summary
    middle_content = summaries if summaries else ''
    bottom_content = links if contains_link_flag else [item['url'] for item in news]

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


# 使用自定义CSS来增强页面效果
st.markdown(
    """
    <style>
    .css-1aumxhk {
        background-color: #f8f9fa;
    }
    .stSpinner {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-size: 20px;
        color: #4CAF50;
    }
    </style>
    """,
    unsafe_allow_html=True
)
