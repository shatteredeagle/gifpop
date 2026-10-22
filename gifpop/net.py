"""Async HTTP on Qt's event loop, with a disk cache for thumbnails and API pages.
Full-size GIFs are never written to the cache (KLIPY's terms allow storing thumbnails only)."""
import json

from PyQt6.QtCore import QByteArray, QObject, QUrl, QUrlQuery
from PyQt6.QtNetwork import (QNetworkAccessManager, QNetworkDiskCache,
                             QNetworkReply, QNetworkRequest)

from .config import HTTP_CACHE

USER_AGENT = "gifpop/0.1 (+linux)"


class Net(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(str(HTTP_CACHE))
        cache.setMaximumCacheSize(400 * 1024 * 1024)
        self.nam.setCache(cache)

    def get(self, url, on_ok, on_err=None, prefer_cache=True, store=True):
        """Fetch url; on_ok(bytes) or on_err(str). Returns the reply so callers can abort()."""
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        if prefer_cache:
            req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.PreferCache)
        if not store:
            req.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
        return self._watch(self.nam.get(req), on_ok, on_err)

    def post_form(self, url, fields, on_ok, on_err=None, headers=None):
        """POST url-encoded fields (never cached); same callbacks as get()."""
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                      "application/x-www-form-urlencoded")
        for k, v in (headers or {}).items():
            req.setRawHeader(k.encode(), v.encode())
        q = QUrlQuery()
        for k, v in fields.items():
            q.addQueryItem(k, str(v))
        body = q.query(QUrl.ComponentFormattingOption.FullyEncoded).encode()
        return self._watch(self.nam.post(req, QByteArray(body)), on_ok, on_err)

    def _watch(self, reply, on_ok, on_err):
        def done():
            try:
                if reply.error() == QNetworkReply.NetworkError.NoError:
                    on_ok(bytes(reply.readAll()))
                elif reply.error() != QNetworkReply.NetworkError.OperationCanceledError and on_err:
                    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                    on_err(f"HTTP {status}: {reply.errorString()}" if status else reply.errorString())
            except RuntimeError:
                pass  # the widget that asked has been deleted
            finally:
                reply.deleteLater()

        reply.finished.connect(done)
        return reply

    def post_json(self, url, body):
        """Fire and forget (KLIPY's share ping)."""
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self.nam.post(req, QByteArray(json.dumps(body).encode()))
        reply.finished.connect(reply.deleteLater)
