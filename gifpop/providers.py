"""GIF search back ends. Tenor's API shut down on 2026-06-30, so it's KLIPY or GIPHY."""
import json
from dataclasses import asdict, dataclass
from urllib.parse import quote, urlencode


@dataclass
class Gif:
    id: str
    title: str
    preview: str   # small animated gif for the grid
    full: str      # gif that gets copied
    url: str       # shareable page/media link for "copy link"

    def to_dict(self):
        return asdict(self)


def _pick(file, sizes, fmt="gif"):
    for s in sizes:
        u = (file.get(s) or {}).get(fmt, {}).get("url")
        if u:
            return u
    return ""


class Klipy:
    name = "KLIPY"
    signup = "https://partner.klipy.com"
    base = "https://api.klipy.com/api/v1"

    def __init__(self, cfg):
        self.cfg = cfg

    def url(self, query, page, per_page=30):
        params = {"page": page, "per_page": per_page,
                  "customer_id": self.cfg["customer_id"],
                  "content_filter": self.cfg["content_filter"]}
        key = quote(self.cfg["klipy_key"], safe="")
        if query:
            params["q"] = query
            return f"{self.base}/{key}/gifs/search?{urlencode(params)}"
        return f"{self.base}/{key}/gifs/trending?{urlencode(params)}"

    def parse(self, raw):
        j = json.loads(raw)
        data = j.get("data") or {}
        out = []
        q = self.cfg["copy_quality"]
        order = {"hd": ["hd", "md", "sm"], "md": ["md", "hd", "sm"], "sm": ["sm", "md", "hd"]}[q]
        for it in data.get("data", []):
            f = it.get("file")
            if it.get("type", "gif") != "gif" or not f:
                continue  # skips ad slots
            full = _pick(f, order)
            out.append(Gif(id=str(it.get("id") or it.get("slug")),
                           title=it.get("title") or "",
                           preview=_pick(f, ["sm", "xs", "md"]) or full,
                           full=full, url=full))
        return out, bool(data.get("has_next"))


class Giphy:
    name = "GIPHY"
    signup = "https://developers.giphy.com/dashboard/"
    base = "https://api.giphy.com/v1/gifs"
    ratings = {"off": "r", "low": "pg-13", "medium": "pg", "high": "g"}

    def __init__(self, cfg):
        self.cfg = cfg
        self.per_page = 30

    def url(self, query, page, per_page=30):
        self.per_page = per_page
        params = {"api_key": self.cfg["giphy_key"], "limit": per_page,
                  "offset": (page - 1) * per_page,
                  "rating": self.ratings.get(self.cfg["content_filter"], "pg")}
        if query:
            params["q"] = query
            return f"{self.base}/search?{urlencode(params)}"
        return f"{self.base}/trending?{urlencode(params)}"

    def parse(self, raw):
        j = json.loads(raw)
        out = []
        q = self.cfg["copy_quality"]
        full_key = {"hd": "original", "md": "downsized_medium", "sm": "fixed_width"}[q]
        for it in j.get("data", []):
            im = it.get("images", {})
            full = (im.get(full_key) or im.get("original") or {}).get("url", "")
            prev = (im.get("fixed_width") or {}).get("url", full)
            out.append(Gif(id=it["id"], title=it.get("title", ""), preview=prev,
                           full=full, url=it.get("url") or full))
        p = j.get("pagination", {})
        has_next = p.get("offset", 0) + p.get("count", 0) < p.get("total_count", 0)
        return out, has_next


def make_provider(cfg):
    return Giphy(cfg) if cfg["provider"] == "giphy" else Klipy(cfg)
