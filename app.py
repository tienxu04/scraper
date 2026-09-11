from __future__ import annotations

import html
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
import trafilatura
from bs4 import BeautifulSoup

APP_USER_AGENT = (
    "ArticleReaderStreamlit/1.0 (+personal reader; "
    "respect publisher access controls)"
)


class FetchError(RuntimeError):
    pass


def validate_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FetchError("URL không hợp lệ. Hãy dùng dạng https://example.com/article.")
    return url


def fetch_html(url: str, timeout: float = 20, retries: int = 2):
    url = validate_url(url)
    headers = {
        "User-Agent": APP_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "vi,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    last_error = None
    with requests.Session() as session:
        session.headers.update(headers)
        for attempt in range(retries + 1):
            try:
                response = session.get(url, timeout=timeout, allow_redirects=True)
                if response.status_code == 403:
                    raise FetchError(
                        "Máy chủ trả về 403 Forbidden. Trang đang yêu cầu quyền "
                        "truy cập hoặc chặn client tự động. Ứng dụng không vượt qua "
                        "paywall, CAPTCHA hay cơ chế anti-bot."
                    )
                if response.status_code in {401, 402}:
                    raise FetchError(
                        f"Trang yêu cầu quyền truy cập (HTTP {response.status_code}). "
                        "Chế độ public không thể đọc trang này."
                    )
                if response.status_code >= 400:
                    raise FetchError(f"Máy chủ trả về HTTP {response.status_code}.")
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    raise FetchError(
                        f"URL không trả về HTML (Content-Type: {content_type})."
                    )
                response.encoding = (
                    response.encoding or response.apparent_encoding or "utf-8"
                )
                return response.text, response
            except FetchError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
    raise FetchError(f"Không tải được URL sau {retries + 1} lần thử: {last_error}")


def extract_article(url: str, raw_html: str, response) -> dict:
    extracted_html = trafilatura.extract(
        raw_html,
        include_comments=False,
        include_tables=True,
        include_links=False,
        favor_precision=True,
        output_format="html",
    ) or ""

    # Keep the block structure returned by Trafilatura. Converting directly to
    # plain text can collapse several publisher paragraphs into one long block.
    extracted_soup = BeautifulSoup(extracted_html, "html.parser")
    blocks = []
    for node in extracted_soup.find_all(["h1", "h2", "h3", "h4", "p", "blockquote", "li"]):
        value = node.get_text(" ", strip=True)
        if value:
            blocks.append(value)

    if not blocks:
        plain_text = trafilatura.extract(
            raw_html,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_precision=True,
            output_format="txt",
        ) or ""
        blocks = [part.strip() for part in re.split(r"\n{2,}", plain_text) if part.strip()]

    # Some pages expose one unusually large text block. Split only such blocks,
    # and only at sentence boundaries, so ordinary short paragraphs stay intact.
    normalized_blocks = []
    for block in blocks:
        if len(block) <= 1100:
            normalized_blocks.append(block)
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỵ“‘\"\d])", block)
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) + 1 > 700:
                normalized_blocks.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            normalized_blocks.append(current.strip())

    text = "\n\n".join(normalized_blocks)

    soup = BeautifulSoup(raw_html, "html.parser")
    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    title = title or "Untitled article"

    if len(text.strip()) < 120:
        raise FetchError(
            "Tải HTML thành công nhưng không tìm thấy đủ nội dung bài viết. "
            "Trang có thể yêu cầu JavaScript, đăng nhập hoặc chỉ hiển thị một phần."
        )

    return {
        "url": url,
        "title": title,
        "text": text.strip(),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
    }


def make_reader_html(article: dict) -> str:
    title = html.escape(article["title"])
    url = html.escape(article["url"])
    paragraphs = "\n".join(
        f"<p>{html.escape(p.strip())}</p>"
        for p in article["text"].split("\n\n")
        if p.strip()
    )
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;line-height:1.75;max-width:760px;margin:3rem auto;padding:0 1.2rem;color:#222;background:#fff}}
.meta{{color:#666;border-bottom:1px solid #ddd;padding-bottom:1rem;margin-bottom:2rem}}
p{{font-size:1.05rem;margin:0 0 1.35em}}
</style>
</head>
<body><div class="meta"><strong>{title}</strong><br>Source: <a href="{url}">{url}</a></div>{paragraphs}</body>
</html>"""


st.set_page_config(page_title="Article Reader v1.5", page_icon="📰", layout="wide")
st.title("Article Reader")
st.caption(
    "Đọc và làm sạch nội dung HTML công khai. Ứng dụng không vượt paywall, "
    "CAPTCHA, đăng nhập hoặc anti-bot."
)

with st.sidebar:
    st.subheader("Cài đặt")
    timeout = st.slider("Timeout (giây)", min_value=5, max_value=60, value=20)
    st.markdown(
        "**Lưu ý:** Một số nhà xuất bản có thể từ chối request tự động dù bài viết "
        "có thể mở bằng trình duyệt. Khi đó ứng dụng sẽ hiển thị lỗi 403 rõ ràng."
    )

url = st.text_input("URL bài viết", placeholder="https://example.com/article")
run = st.button("Đọc bài viết", type="primary", use_container_width=True)

if run:
    if not url.strip():
        st.warning("Vui lòng nhập URL bài viết.")
    else:
        try:
            with st.spinner("Đang tải và bóc tách nội dung..."):
                normalized_url = validate_url(url)
                raw_html, response = fetch_html(normalized_url, timeout=timeout)
                article = extract_article(normalized_url, raw_html, response)
            st.session_state["article"] = article
            st.success(
                f"Đã đọc: {article['title']} — "
                f"{len(article['text']):,} ký tự"
            )
        except FetchError as exc:
            st.session_state.pop("article", None)
            st.error(str(exc))
        except Exception as exc:
            st.session_state.pop("article", None)
            st.error(f"Lỗi không dự kiến: {type(exc).__name__}: {exc}")

article = st.session_state.get("article")
if article:
    st.subheader(article["title"])
    st.caption(f"Nguồn: {article['url']}")
    left, right = st.columns([3, 1])
    with left:
        st.text_area("Nội dung", article["text"], height=620, label_visibility="collapsed")
    with right:
        st.metric("Số ký tự", f"{len(article['text']):,}")
        st.metric("Số từ", f"{len(article['text'].split()):,}")
        filename = re.sub(r"[^a-zA-Z0-9_-]+", "_", article["title"]).strip("_")[:60] or "article"
        st.download_button(
            "Tải TXT",
            data=article["text"],
            file_name=f"{filename}.txt",
            mime="text/plain",
            use_container_width=True,
        )
        st.download_button(
            "Tải Reader HTML",
            data=make_reader_html(article),
            file_name=f"{filename}.html",
            mime="text/html",
            use_container_width=True,
        )
else:
    st.info("Nhập URL rồi bấm “Đọc bài viết”.")
