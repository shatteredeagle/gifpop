"""Async HTTP on Qt's event loop, with a disk cache for thumbnails and media."""
from PyQt6.QtCore import QObject, QUrl
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

    def get(self, url, on_ok, on_err=None, prefer_cache=True):
        """Fetch url; on_ok(bytes) or on_err(str). Returns the reply so callers can abort()."""
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        if prefer_cache:
            req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self.nam.get(req)

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
