import os
import sqlite3
import requests
import time
import json
import re
from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urljoin, urlparse

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

USE_LOCAL_AI = True 
LOCAL_AI_MODEL = 'deepseek-r1:32b' 
LOCAL_AI_URL = 'http://localhost:11434/api/generate' 

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = 'gemini-2.5-pro'

if not USE_LOCAL_AI:
    try:
        import google.generativeai as genai
    except ImportError:
        print("錯誤：當使用雲端 AI 時，未安裝 'google-generativeai' 函式庫。請執行 'pip install google-generativeai'")
        exit()

START_URLS = ["https://www.gamer.com.tw/", "https://www.dcard.tw/f", "https://www.ettoday.net/", "https://www.wikipedia.org/", "https://google.com.tw/", "https://www.yahoo.com/", "https://www.facebook.com/", "https://www.youtube.com/", "https://www.instagram.com/", "https://www.twitter.com/", "https://www.linkedin.com/", "https://www.reddit.com/", "https://www.quora.com/", "https://www.twitch.tv/", "https://www.netflix.com/", "https://www.amazon.com/", "https://www.ebay.com/", "https://www.alibaba.com/", "https://www.taobao.com/", "https://www.pchome.com.tw/", "https://www.ruten.com.tw/", "https://www.momoshop.com.tw/", "https://www.books.com.tw/", "https://www.cw.com.tw/", "https://www.chinatimes.com/", "https://www.ltn.com.tw/", "https://www.udn.com/", "https://www.bbc.com/", "https://www.cnn.com/", "https://www.nytimes.com/", "https://www.wsj.com/", "https://www.reuters.com/", "https://www.aljazeera.com/", "https://www.npr.org/", "https://www.bloomberg.com/", "https://www.forbes.com/", "https://www.theguardian.com/", "https://www.huffpost.com/", "https://www.vox.com/", "https://www.washingtonpost.com/", "https://www.vice.com/", "https://www.foxnews.com/", "https://www.infowars.com/", "https://github.com/"]
DB_NAME = "domain_classification.db"

MAX_DOMAINS_TO_CRAWL = 20

MAX_CLASSIFICATION_RETRIES = 3
RETRY_DELAY = 3

CLASSIFICATION_SCHEMA_JSON = """
{
  "classification_info": {
    "version": "2.0",
    "description": "一份詳細的網站分類法，適用於內容過濾、策略分析與機器學習模型訓練。總計包含 11 個主要類別和 70 個子類別。",
    "author": "Gemini"
  },
  "website_classifications": [
    {
      "code": "010",
      "category_zh": "🔞 成人與不當內容 (Adult & Inappropriate)",
      "description_zh": "高風險類別，包含不適合未成年人或在特定場合瀏覽的內容，通常預設封鎖。",
      "subcategories": [
        { "sub_code": "010-01", "name_zh": "成人內容/色情", "description_zh": "明確的色情圖片、影片或文字描述。" },
        { "sub_code": "010-02", "name_zh": "裸露/性暗示", "description_zh": "非色情的裸露、清涼服裝或強烈性暗示內容。" },
        { "sub_code": "010-03", "name_zh": "暴力/血腥/恐怖", "description_zh": "包含真實或虛構的暴力、血腥、殘酷或恐怖畫面。" },
        { "sub_code": "010-04", "name_zh": "毒品/酒精/煙品", "description_zh": "提倡、販售或詳細描述非法藥物、酒精、煙草製品的內容。" },
        { "sub_code": "010-05", "name_zh": "武器/軍火/爆裂物", "description_zh": "關於武器、軍火、炸藥的製造、改造與交易資訊。" },
        { "sub_code": "010-06", "name_zh": "賭博/彩票", "description_zh": "提供線上賭博、博弈遊戲、彩票投注或相關資訊的網站。" },
        { "sub_code": "010-07", "name_zh": "仇恨言論/極端主義", "description_zh": "宣揚針對特定族群、宗教、性別的歧視、仇恨或暴力言論。" },
        { "sub_code": "010-08", "name_zh": "自殘/自殺", "description_zh": "鼓勵、描述或提供自殘與自殺方法的內容。" }
      ]
    },
    {
      "code": "020",
      "category_zh": "⚠️ 網路風險與安全 (Web Risk & Security)",
      "description_zh": "可能對使用者設備、個人資訊或財產構成威脅的網站，建議封鎖或審查。",
      "subcategories": [
        { "sub_code": "020-01", "name_zh": "惡意網站/病毒", "description_zh": "散播惡意軟體、病毒、勒索軟體或木馬的網站。" },
        { "sub_code": "020-02", "name_zh": "詐騙/網路釣魚", "description_zh": "企圖騙取使用者個資、帳號密碼或金錢的欺詐網站。" },
        { "sub_code": "020-03", "name_zh": "匿名/規避工具", "description_zh": "提供 VPN、Proxy、Tor 等用於隱藏身份或規避網路審查的工具。" },
        { "sub_code": "020-04", "name_zh": "P2P/非法下載", "description_zh": "提供 BT 種子、檔案共享或盜版軟體、影音內容下載的網站。" },
        { "sub_code": "020-05", "name_zh": "廣告/追蹤器", "description_zh": "主要目的為投放大量廣告或進行跨網站使用者行為追蹤。" },
        { "sub_code": "020-06", "name_zh": "垃圾郵件/可疑網站", "description_zh": "被標記為垃圾郵件來源或行為可疑的網站。" }
      ]
    },
    {
      "code": "030",
      "category_zh": "🌐 社群與通訊 (Social & Communication)",
      "description_zh": "使用者之間進行互動、溝通與內容分享的平台，可視年齡與情境彈性控管。",
      "subcategories": [
        { "sub_code": "030-01", "name_zh": "綜合社群媒體", "description_zh": "如 Facebook、Instagram 等多功能社交平台。" },
        { "sub_code": "030-02", "name_zh": "即時通訊", "description_zh": "如 LINE、Discord、Telegram 等即時訊息溝通工具。" },
        { "sub_code": "030-03", "name_zh": "論壇/使用者生成內容", "description_zh": "如 Reddit、PTT 等以特定主題為核心的討論區。" },
        { "sub_code": "030-04", "name_zh": "部落格平台", "description_zh": "提供個人或團體發表文章、觀點的平台。" },
        { "sub_code": "030-05", "name_zh": "線上交友", "description_zh": "以尋找戀愛或社交關係為目的的約會網站或 App。" }
      ]
    },
    {
      "code": "040",
      "category_zh": "🎬 娛樂與媒體 (Entertainment & Media)",
      "description_zh": "提供消遣、休閒與感官體驗為主的內容。",
      "subcategories": [
        { "sub_code": "040-01", "name_zh": "影音串流", "description_zh": "如 YouTube、Netflix、Twitch 等影音平台。" },
        { "sub_code": "040-02", "name_zh": "音樂/廣播", "description_zh": "如 Spotify、Apple Music 等音樂串流或網路廣播。" },
        { "sub_code": "040-03", "name_zh": "線上遊戲", "description_zh": "提供網頁遊戲、客戶端遊戲下載或遊戲資訊的網站。" },
        { "sub_code": "040-04", "name_zh": "電影/電視", "description_zh": "提供電影、電視劇資訊、評論或時刻表的網站。" },
        { "sub_code": "040-05", "name_zh": "幽默/迷因", "description_zh": "以笑話、趣圖、迷因等輕鬆內容為主的網站。" },
        { "sub_code": "040-06", "name_zh": "動漫", "description_zh": "提供動畫、漫畫線上觀看或相關資訊的網站。" },
        { "sub_code": "040-07", "name_zh": "名人八卦", "description_zh": "專注於報導藝人、名人動態與花邊新聞的網站。" }
      ]
    },
    {
      "code": "050",
      "category_zh": "🛍️ 商業與購物 (Commerce & Shopping)",
      "description_zh": "涉及商品、服務交易或商業活動的網站。",
      "subcategories": [
        { "sub_code": "050-01", "name_zh": "線上購物/電商", "description_zh": "如 Amazon、PChome 等綜合或垂直型電子商務平台。" },
        { "sub_code": "050-02", "name_zh": "拍賣/二手交易", "description_zh": "如 eBay、旋轉拍賣等 C2C 或 B2C 拍賣網站。" },
        { "sub_code": "050-03", "name_zh": "比價網站", "description_zh": "提供商品或服務價格比較資訊的網站。" },
        { "sub_code": "050-04", "name_zh": "團購", "description_zh": "提供集體購買以獲得優惠的平台。" },
        { "sub_code": "050-05", "name_zh": "分類廣告", "description_zh": "提供地區性的商品、服務、求職等分類資訊刊登。" }
      ]
    },
    {
      "code": "060",
      "category_zh": "💰 金融與商業服務 (Finance & Business Services)",
      "description_zh": "提供金融、投資、法律、商業相關服務的網站。",
      "subcategories": [
        { "sub_code": "060-01", "name_zh": "金融/銀行", "description_zh": "提供網路銀行、保險、貸款等服務的金融機構網站。" },
        { "sub_code": "060-02", "name_zh": "投資/股票", "description_zh": "提供股票、基金、外匯等市場資訊與交易平台。" },
        { "sub_code": "060-03", "name_zh": "加密貨幣", "description_zh": "提供加密貨幣交易、資訊或相關服務的平台。" },
        { "sub_code": "060-04", "name_zh": "企業網站", "description_zh": "非購物導向的企業形象與資訊網站。" },
        { "sub_code": "060-05", "name_zh": "求職/人力資源", "description_zh": "提供職缺搜尋、履歷刊登與招募服務的網站。" },
        { "sub_code": "060-06", "name_zh": "房地產", "description_zh": "提供房屋買賣、租賃與相關資訊的網站。" },
        { "sub_code": "060-07", "name_zh": "法律服務", "description_zh": "提供法律諮詢、事務所資訊或法規查詢的網站。" }
      ]
    },
    {
      "code": "070",
      "category_zh": "📖 教育與益智 (Education & Reference)",
      "description_zh": "提供知識獲取、技能學習與參考資訊的網站，通常預設允許。",
      "subcategories": [
        { "sub_code": "070-01", "name_zh": "教育資源/線上學習", "description_zh": "如 Coursera、Khan Academy 等線上課程或教學資源網站。" },
        { "sub_code": "070-02", "name_zh": "學校/教育機構", "description_zh": "各級學校、大學、研究機構的官方網站。" },
        { "sub_code": "070-03", "name_zh": "圖書/字典/百科", "description_zh": "提供線上閱讀、字典查詢、百科全書等服務的網站。" },
        { "sub_code": "070-04", "name_zh": "語言學習", "description_zh": "專門用於學習外語的網站或工具。" },
        { "sub_code": "070-05", "name_zh": "歷史/人文", "description_zh": "提供歷史、地理、藝術等人文科學知識的網站。" },
        { "sub_code": "070-06", "name_zh": "科學/自然", "description_zh": "提供物理、化學、生物等自然科學知識的網站。" }
      ]
    },
    {
      "code": "080",
      "category_zh": "📰 資訊與新聞 (Information & News)",
      "description_zh": "以傳遞時事、資訊、觀點為主要目的的網站。",
      "subcategories": [
        { "sub_code": "080-01", "name_zh": "新聞/媒體", "description_zh": "國內外綜合性、地方性或專業領域的新聞媒體網站。" },
        { "sub_code": "080-02", "name_zh": "天氣", "description_zh": "提供天氣預報與氣象資訊的網站。" },
        { "sub_code": "080-03", "name_zh": "地圖/導航", "description_zh": "提供地圖查詢、路線規劃與定位服務的網站。" },
        { "sub_code": "080-04", "name_zh": "政府機構", "description_zh": "各國中央與地方政府的官方入口網站。" },
        { "sub_code": "080-05", "name_zh": "非營利組織", "description_zh": "非政府、非營利的慈善、環保、人權等組織網站。" }
      ]
    },
    {
      "code": "090",
      "category_zh": "❤️ 生活與健康 (Lifestyle & Health)",
      "description_zh": "與日常生活、個人健康、興趣嗜好相關的網站。",
      "subcategories": [
        { "sub_code": "090-01", "name_zh": "健康/醫療", "description_zh": "提供健康資訊、醫療知識、醫院診所查詢的網站。" },
        { "sub_code": "090-02", "name_zh": "餐飲/食譜", "description_zh": "提供餐廳評論、食譜分享、美食資訊的網站。" },
        { "sub_code": "090-03", "name_zh": "旅遊/訂票", "description_zh": "提供旅遊資訊、行程規劃、機票飯店預訂的網站。" },
        { "sub_code": "090-04", "name_zh": "時尚/美容", "description_zh": "提供流行穿搭、美妝保養資訊的網站。" },
        { "sub_code": "090-05", "name_zh": "汽車", "description_zh": "提供汽車資訊、評測、買賣與社群的網站。" },
        { "sub_code": "090-06", "name_zh": "運動/健身", "description_zh": "提供運動教學、賽事報導、健身資訊的網站。" },
        { "sub_code": "090-07", "name_zh": "寵物", "description_zh": "提供寵物飼養、醫療、社群等資訊的網站。" },
        { "sub_code": "090-08", "name_zh": "宗教", "description_zh": "提供特定宗教教義、活動與資訊的網站。" }
      ]
    },
    {
      "code": "100",
      "category_zh": "🛠️ 技術與工具 (Technology & Tools)",
      "description_zh": "提供軟體、硬體、網路技術資訊或線上實用工具的網站。",
      "subcategories": [
        { "sub_code": "100-01", "name_zh": "搜尋引擎", "description_zh": "如 Google、Bing 等用於搜尋網際網路資訊的網站。" },
        { "sub_code": "100-02", "name_zh": "科技新聞/評論", "description_zh": "專注於報導 3C、軟體、網路與科技產業動態的媒體。" },
        { "sub_code": "100-03", "name_zh": "網頁郵件", "description_zh": "提供網頁版電子郵件收發服務的網站。" },
        { "sub_code": "100-04", "name_zh": "雲端儲存/檔案分享", "description_zh": "提供線上檔案儲存、同步與分享服務的網站。" },
        { "sub_code": "100-05", "name_zh": "軟體下載", "description_zh": "提供軟體、應用程式下載的資源庫或市集。" },
        { "sub_code": "100-06", "name_zh": "線上工具", "description_zh": "提供檔案轉換、圖片編輯、線上翻譯等實用功能的網站。" },
        { "sub_code": "100-07", "name_zh": "開發者資源", "description_zh": "提供程式碼託管、API 文件、技術問答等開發者所需資源。" }
      ]
    },
    {
      "code": "999",
      "category_zh": "⚙️ 系統分類 (System Categories)",
      "description_zh": "用於分類流程管理的特殊類別，非內容導向。",
      "subcategories": [
        { "sub_code": "999-01", "name_zh": "待分類", "description_zh": "已發現但尚未進行人工或自動分類的網站。" },
        { "sub_code": "999-02", "name_zh": "無法訪問/錯誤", "description_zh": "無法正常連線、顯示錯誤訊息或已失效的網站。" },
        { "sub_code": "999-03", "name_zh": "停泊網域", "description_zh": "已註冊但沒有實際內容，僅顯示廣告或「建置中」的網域。" },
        { "sub_code": "999-04", "name_zh": "私人 IP", "description_zh": "指向內部網路或保留 IP 位址的網站。" },
        { "sub_code": "999-99", "name_zh": "未知", "description_zh": "經過分類流程後，仍無法歸類的網站。" }
      ]
    }
  ]
}
"""

CLASSIFICATION_SCHEMA = json.loads(CLASSIFICATION_SCHEMA_JSON)

def build_code_maps(schema):
    main_category_map, subcategory_map = {}, {}
    for category in schema["website_classifications"]:
        main_category_map[category["code"]] = category["category_zh"]
        for sub in category["subcategories"]:
            subcategory_map[sub["sub_code"]] = sub["name_zh"]
    return main_category_map, subcategory_map

MAIN_CATEGORY_MAP, SUBCATEGORY_MAP = build_code_maps(CLASSIFICATION_SCHEMA)


class DatabaseManager:
    """負責處理所有與 SQLite 資料庫相關的操作"""
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        print(f"資料庫 '{db_name}' 連線成功。")

    def setup_tables(self):
        """建立所有需要的資料表"""
        try:
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS classified_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                main_category_code TEXT,
                main_category_name TEXT,
                subcategory_code TEXT,
                subcategory_name TEXT,
                summary TEXT,
                source_url TEXT,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE
            )
            """)
            self.conn.commit()
            print("資料表 'classified_domains' 和 'crawl_queue' 已建立或已存在。")
        except sqlite3.Error as e:
            print(f"建立資料表時發生錯誤: {e}")

    def add_domain_classification(self, domain, main_cat_code, main_cat_name, sub_cat_code, sub_cat_name, summary, source_url):
        try:
            self.cursor.execute(
                """INSERT OR IGNORE INTO classified_domains 
                   (domain, main_category_code, main_category_name, subcategory_code, subcategory_name, summary, source_url) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (domain, main_cat_code, main_cat_name, sub_cat_code, sub_cat_name, summary, source_url)
            )
            self.conn.commit()
            print(f"成功將分類紀錄新增至資料庫: {domain}")
        except sqlite3.Error as e:
            print(f"新增資料至資料庫時發生錯誤: {e}")
    
    def add_to_queue(self, url):
        """將單一 URL 加入待爬取佇列資料表"""
        try:
            self.cursor.execute("INSERT OR IGNORE INTO crawl_queue (url) VALUES (?)", (url,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"將 URL 加入佇列時發生錯誤: {e}")

    def remove_from_queue(self, url):
        """從待爬取佇列資料表中移除單一 URL"""
        try:
            self.cursor.execute("DELETE FROM crawl_queue WHERE url = ?", (url,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"從佇列移除 URL 時發生錯誤: {e}")

    def load_queue(self):
        """從資料庫載入整個待爬取佇列"""
        try:
            self.cursor.execute("SELECT url FROM crawl_queue")
            return [row[0] for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"載入佇列時發生錯誤: {e}")
            return []

    def domain_exists(self, domain):
        self.cursor.execute("SELECT id FROM classified_domains WHERE domain = ?", (domain,))
        return self.cursor.fetchone() is not None

    def close(self):
        self.conn.close()
        print("資料庫連線已關閉。")


def get_summary_prompt(text_content):
    """產生用於第一階段「摘要」的提示"""
    return f"""Analyze the following website text content and provide a single, concise, one-sentence summary in Traditional Chinese that describes the website's primary purpose.

**SPECIAL RULE:** If the content appears to be a security check, firewall, or block page (e.g., from Cloudflare), your summary MUST be "這是一個防火牆或安全檢查頁面。".

**Website Text Content:**
---
{text_content}
---

Your response MUST be only the one-sentence summary and nothing else.
"""

def get_classification_from_summary_prompt(schema_str, url, summary):
    """產生用於第二階段「基於摘要和URL分類」的提示"""
    return f"""You are a JSON-generating robot. Your task is to classify the provided website based on its URL and summary.

**Classification Schema:**
---
{schema_str}
---

**Information to Classify:**
- **URL:** `{url}`
- **Summary:** "{summary}"

**INSTRUCTIONS:**
1.  Analyze both the URL and the Summary to understand the website's true identity and purpose. The URL provides crucial context.
2.  Based on your combined analysis, choose the most accurate `main_category_code` and `subcategory_code` from the schema.
3.  Construct a JSON object with your results.

**SPECIAL RULE:** If the summary is "這是一個防火牆或安全檢查頁面。", you **MUST** classify it with `main_category_code: "999"` and `subcategory_code: "999-02"`.

**OUTPUT RULES:**
- Your response **MUST ONLY** be a single, valid JSON object.
- The JSON **MUST** contain two keys: `main_category_code` and `subcategory_code`.

Now, classify the website and provide ONLY the JSON object.
"""


class AIClassifier:
    """分類器的抽象基底類別"""
    def classify_from_content(self, text_content, url):
        raise NotImplementedError

class LocalOllamaClassifier(AIClassifier):
    """使用本地運行的 Ollama 服務進行兩階段分類"""
    def __init__(self, model, api_url, schema_json):
        self.model = model
        self.api_url = api_url
        self.schema_json_str = schema_json
        print(f"本地 Ollama 分類器已初始化，使用模型: {self.model}")

    def _call_ollama(self, prompt, url_for_log, expect_json=False):
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        if expect_json:
            payload["format"] = "json"
        
        try:
            print(f"正在向本地 Ollama API 請求 ({'JSON' if expect_json else 'Text'}): {url_for_log}")
            response = requests.post(self.api_url, json=payload, timeout=180)
            response.raise_for_status()
            response_data = response.json()
            raw_response_str = response_data.get('response', '')
            print(f"DEBUG: Ollama 原始回覆: {raw_response_str}")
            if not raw_response_str: return None
            
            cleaned_str = re.sub(r'<think>.*?</think>', '', raw_response_str, flags=re.DOTALL).strip()
            
            if expect_json:
                json_str = cleaned_str.lstrip('```json').rstrip('```').strip()
                return json.loads(json_str)
            else:
                return cleaned_str
        except requests.exceptions.ConnectionError:
            print(f"\n錯誤：無法連線至本地 Ollama 服務 ({self.api_url})。")
            exit()
        except Exception as e:
            print(f"呼叫本地 Ollama API 或處理回傳時發生錯誤: {e}")
            return None

    def classify_from_content(self, text_content, url):
        """執行「摘要 -> 分類」的兩階段流程"""
        summary_prompt = get_summary_prompt(text_content[:8000])
        summary = self._call_ollama(summary_prompt, f"{url} [摘要階段]")
        
        if not summary:
            print("錯誤：第一階段未能產生摘要。")
            return None
        
        print(f"INFO: 第一階段摘要完成: {summary}")

        classification_result = None
        for attempt in range(MAX_CLASSIFICATION_RETRIES):
            classification_prompt = get_classification_from_summary_prompt(self.schema_json_str, url, summary)
            result = self._call_ollama(classification_prompt, f"{url} [分類階段]", expect_json=True)
            if result and result.get("main_category_code"):
                classification_result = result
                break
            print(f"警告：分類階段失敗。將在 {RETRY_DELAY} 秒後進行第 {attempt + 2} 次重試...")
            time.sleep(RETRY_DELAY)
        
        if not classification_result:
            print("錯誤：第二階段重試多次後仍未能產生分類。")
            return None
            
        classification_result["summary"] = summary
        return classification_result


class WebScraper:
    """負責抓取網頁內容，具備 Selenium 備援機制"""
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    def fetch(self, url):
        """主抓取函式，優先使用 requests"""
        print(f"正在使用 Requests 嘗試抓取 {url} ...")
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            if response.status_code == 200:
                print("Requests 抓取成功。")
                return response.content, response.url
            else:
                print(f"Requests 失敗，狀態碼: {response.status_code}。將嘗試使用 Selenium。")
                return self._fetch_with_selenium(url)
        except requests.exceptions.RequestException as e:
            print(f"Requests 發生錯誤: {e}。將嘗試使用 Selenium。")
            return self._fetch_with_selenium(url)

    def _fetch_with_selenium(self, url):
        """使用 Selenium 作為備援抓取方式"""
        if not SELENIUM_AVAILABLE:
            print("警告: 未安裝 Selenium，無法使用備援抓取。")
            return None, None
        
        print(f"正在使用 Selenium 嘗試抓取 {url} ...")
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = None
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)
            time.sleep(5)
            page_source = driver.page_source
            final_url = driver.current_url
            print("Selenium 抓取成功。")
            return page_source, final_url
        except Exception as e:
            print(f"Selenium 抓取時發生錯誤: {e}")
            return None, None
        finally:
            if driver:
                driver.quit()

class WebCrawler:
    """主爬蟲程式，採用兩階段分類策略與備援抓取"""
    def __init__(self, start_urls, db_manager, classifier, scraper):
        self.db_manager = db_manager
        self.classifier = classifier
        self.scraper = scraper
        self.crawled_count = 0
        
        queue_from_db = self.db_manager.load_queue()
        if queue_from_db:
            self.urls_to_crawl = deque(queue_from_db)
            print(f"成功從資料庫載入 {len(queue_from_db)} 個待辦項目。")
        else:
            initial_root_urls = sorted(list(set(filter(None, [self.get_root_url(url) for url in start_urls]))))
            self.urls_to_crawl = deque(initial_root_urls)
            print("資料庫中無待辦項目，從 START_URLS 初始化佇列。")
            for url in initial_root_urls:
                self.db_manager.add_to_queue(url)
        
        self.processed_domains = {self.get_domain(url) for url in self.urls_to_crawl}
        print(f"DEBUG: 初始化完成，已處理/待處理域名共 {len(self.processed_domains)} 個。")


    def get_domain(self, url):
        try: return urlparse(url).netloc
        except: return None

    def get_root_url(self, url):
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        except: return None

    def _save_classification(self, domain, url, classification_result):
        """將分類結果儲存至資料庫的輔助函式"""
        main_cat_code = classification_result.get("main_category_code")
        sub_cat_code = classification_result.get("subcategory_code")
        
        if main_cat_code not in MAIN_CATEGORY_MAP or sub_cat_code not in SUBCATEGORY_MAP or not sub_cat_code.startswith(main_cat_code):
             print(f"警告: AI 回傳了無效或不匹配的代碼。Main: {main_cat_code}, Sub: {sub_cat_code}")
             return False
        
        summary = classification_result.get("summary", "無法生成摘要")
        main_cat_name = MAIN_CATEGORY_MAP.get(main_cat_code, "未知")
        sub_cat_name = SUBCATEGORY_MAP.get(sub_cat_code, "未知")
        
        self.db_manager.add_domain_classification(domain, main_cat_code, main_cat_name, sub_cat_code, sub_cat_name, summary, url)
        self.crawled_count += 1
        return True

    def _find_and_queue_new_links(self, soup, base_url):
        """從頁面中尋找新的、未處理過的根 URL 並加入佇列"""
        for link in soup.find_all('a', href=True):
            href = link['href']
            if not href: continue
            
            absolute_url = urljoin(base_url, href)
            new_domain = self.get_domain(absolute_url)
            
            if new_domain and new_domain not in self.processed_domains:
                root_url = self.get_root_url(absolute_url)
                if root_url:
                    self.processed_domains.add(new_domain)
                    self.urls_to_crawl.append(root_url)
                    self.db_manager.add_to_queue(root_url) 
                    print(f"發現新域名 {new_domain}，已將根 URL 加入佇列: {root_url}")

    def run(self, max_domains):
        """執行爬蟲主迴圈"""
        while self.urls_to_crawl and self.crawled_count < max_domains:
            url = self.urls_to_crawl.popleft()
            self.db_manager.remove_from_queue(url)
            
            domain = self.get_domain(url)

            if not domain or self.db_manager.domain_exists(domain):
                continue
            
            print(f"\n--- 開始處理 ({self.crawled_count + 1}/{max_domains}): {url} ---")
            
            html_content, final_url = self.scraper.fetch(url)

            if not html_content:
                print(f"錯誤: 使用所有方法抓取 {url} 皆失敗。將此域名標記為錯誤。")
                self._save_classification(domain, url, {"main_category_code": "999", "subcategory_code": "999-02", "summary": "爬蟲無法訪問此網站。"})
                continue

            soup = BeautifulSoup(html_content, 'html.parser')
            
            print("INFO: 開始進行網頁內容分析...")
            for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
                tag.decompose()
            text_content = soup.get_text(separator=' ', strip=True)

            if text_content and len(text_content) > 150:
                content_result = self.classifier.classify_from_content(text_content, final_url)
                if content_result:
                    self._save_classification(self.get_domain(final_url), final_url, content_result)
                else:
                    print(f"域名 {domain} 的內容分析失敗。")
            else:
                print(f"域名 {domain} 的文字內容太少，無法進行內容分析。")

            self._find_and_queue_new_links(soup, final_url)
            
            time.sleep(1)

        print(f"\n爬取完成！總共處理了 {self.crawled_count} 個域名。")

def main():
    """主執行函數"""
    if not SELENIUM_AVAILABLE:
        print("警告：未安裝 Selenium 相關套件，備援抓取功能將無法使用。")
        print("建議執行：pip install selenium webdriver-manager")

    if not USE_LOCAL_AI:
        print("錯誤：目前的兩階段分類邏輯尚未為 Gemini API 進行優化。請將 USE_LOCAL_AI 設為 True。")
        return
        
    classifier = LocalOllamaClassifier(model=LOCAL_AI_MODEL, api_url=LOCAL_AI_URL, schema_json=CLASSIFICATION_SCHEMA_JSON)

    db_manager = None
    scraper = WebScraper()
    try:
        db_manager = DatabaseManager(DB_NAME)
        db_manager.setup_tables() 
        crawler = WebCrawler(start_urls=START_URLS, db_manager=db_manager, classifier=classifier, scraper=scraper)
        crawler.run(max_domains=MAX_DOMAINS_TO_CRAWL)
    except Exception as e:
        print(f"程式執行時發生嚴重錯誤: {e}")
    finally:
        if db_manager:
            db_manager.close()

if __name__ == "__main__":
    main()
