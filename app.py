import streamlit as st
import re
import html
import urllib.request
import ssl
import time

# Cấu hình giao diện trang web Streamlit
st.set_page_config(
    page_title="Web Article Reader & Scraper",
    page_icon="📰",
    layout="wide"
)

# ==========================================
# LOGIC CÀO BÀI VIẾT V8 (CLEAN HTML MAIN CONTENT)
# ==========================================
def clean_html_content(html_content):
    # 1. Xóa các thẻ rác/không chứa nội dung chính
    non_content_tags = r'<(script|style|svg|noscript|iframe|header|footer|nav|aside|form)[^>]*>.*?</\1>'
    cleaned = re.sub(non_content_tags, '', html_content, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)

    # 2. Xóa các khối class/id rác
    junk_patterns = r'<(div|section|ul|ol|aside)[^>]*(id|class)=["\'][^"\']*(menu|nav|sidebar|footer|header|widget|related|comment|cookie|banner|advertisement|share|social)[^"\']*["\'][^>]*>.*?</\1>'
    cleaned = re.sub(junk_patterns, '', cleaned, flags=re.DOTALL | re.IGNORECASE)

    # 3. Quy đổi Block elements thành '\n'
    block_tags = r'</?(p|div|h[1-6]|li|td|th|tr|blockquote|section|article|br|hr)[^>]*>'
    cleaned = re.sub(block_tags, '\n', cleaned, flags=re.IGNORECASE)

    # 4. Thay Inline tags bằng khoảng trắng
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    text = html.unescape(cleaned)

    # 5. Lọc các đoạn văn chất lượng
    paragraphs = []
    for line in text.splitlines():
        line_str = re.sub(r'\s+', ' ', line).strip()
        if len(line_str) > 40 or re.search(r'[\.\?!]$', line_str):
            paragraphs.append(line_str)

    return paragraphs

# ==========================================
# GIAO DIỆN STREAMLIT WEB APP
# ==========================================
st.title("📰 Web Article Reader & Scraper")
st.caption("Dán URL bài viết báo để tự động lọc sạch rác, xem nội dung trọn vẹn và tải file HTML Reader Mode.")

# Sử dụng Session State để quản lý dữ liệu khi bấm Clear
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = None

col1, col2 = st.columns([1, 1], gap="large")

# --- CỘT TRÁI: NHẬP URL & THAO TÁC ---
with col1:
    st.subheader("⚙️ Thao tác")
    
    url_input = st.text_input(
        "🔗 Nhập URL bài viết cần cào:", 
        placeholder="https://example.com/bai-viet...",
        key="url_input_key"
    )
    
    btn_col1, btn_col2 = st.columns([2, 1])
    with btn_col1:
        submit_btn = st.button("🚀 Cào & Bóc Tách Bài Viết", type="primary", use_container_width=True)
    with btn_col2:
        if st.button("🧹 Clear", use_container_width=True):
            st.session_state.scraped_data = None
            st.rerun()

    if submit_btn:
        if not url_input.strip():
            st.warning("⚠️ Vui lòng nhập URL bài viết!")
        else:
            url = url_input.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            context = ssl._create_unverified_context()

            with st.spinner("⏳ Đang cào dữ liệu & dọn dẹp rác..."):
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, context=context) as response:
                        html_content = response.read().decode('utf-8', errors='ignore')
                        paragraphs = clean_html_content(html_content)

                        if not paragraphs:
                            st.error("⚠️ Không lấy được nội dung văn bản nào từ URL này.")
                        else:
                            timestamp = int(time.time())
                            filename = f"article_{timestamp}.html"
                            
                            body_html = "\n".join([f"<p>{p}</p>" for p in paragraphs])
                            full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Article Reader - {timestamp}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.8; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #222; background-color: #fcfcfc; }}
        p {{ margin-bottom: 1.5em; font-size: 1.05rem; }}
        .meta {{ font-size: 0.85rem; color: #666; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 25px; }}
    </style>
</head>
<body>
    <div class="meta">Nguồn: <a href="{url}" target="_blank">{url}</a></div>
    {body_html}
</body>
</html>"""

                            st.session_state.scraped_data = {
                                "filename": filename,
                                "html_content": full_html,
                                "full_text": "\n\n".join(paragraphs),
                                "count": len(paragraphs)
                            }
                except Exception as e:
                    st.error(f"❌ Lỗi khi bóc tách dữ liệu: {e}")

    # Hiển thị thông tin file & Nút Download
    if st.session_state.scraped_data:
        data = st.session_state.scraped_data
        st.markdown("---")
        st.success(f"🎉 **THÀNH CÔNG!**\n- **Tên file:** `{data['filename']}`\n- **Tổng số:** {data['count']} đoạn văn")
        
        st.download_button(
            label="📥 Tải File HTML Reader về máy",
            data=data["html_content"],
            file_name=data["filename"],
            mime="text/html",
            use_container_width=True
        )

# --- CỘT PHẢI: FULL READER CONTENT ---
with col2:
    st.subheader("📖 Nội dung trọn vẹn (Full Reader Content)")
    if st.session_state.scraped_data:
        st.text_area(
            label="Nội dung bài viết",
            value=st.session_state.scraped_data["full_text"],
            height=520,
            label_visibility="collapsed"
        )
    else:
        st.info("Nội dung sạch sẽ hiển thị trọn vẹn tại đây sau khi bạn dán URL và bấm Cào.")
