import feedparser
from fastapi import FastAPI, HTTPException, APIRouter
import uvicorn

router = APIRouter(prefix="/news", tags=["news"])

@router.get("/newsko")
async def get_newsko_news(limit: int = 10):
    try:
        rss_url = "https://www.newsko.ru/rss.xml"
        feed = feedparser.parse(rss_url)

        if feed.bozo:
            print(f"Предупреждение парсинга: {feed.bozo_exception}")

        news_list = []
        for entry in feed.entries[:limit]:
            news_list.append({
                "title": entry.get("title", "").replace("<![CDATA[", "").replace("]]>", ""),
                "description": entry.get("description", "").replace("<![CDATA[", "").replace("]]>", ""),
                "link": entry.get("link"),
                "published": entry.get("published"),
                "source": "Новый компаньон"
            })

        return {
            "source": "Новый компаньон",
            "total": len(news_list),
            "news": news_list
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка парсинга RSS: {str(e)}")
