"""
!pip install PyQt5 PyQtWebEngine
"""
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile
from PyQt5.QtCore import QUrl, QTimer, QDateTime
from PyQt5.QtNetwork import QNetworkCookie
import sys


def create_consent_cookie():
    # Construct a simple CONSENT cookie. The exact value used by Google can vary,
    # but many people use "YES+..." or at least "YES" to mark consent client-side.
    cookie = QNetworkCookie()
    cookie.setName(b"SOCS")
    cookie.setValue(b"CAESEwgDEgk4MTM3OTEyOTAaAmZyIAEaBgiAx4HHBg")
    cookie.setDomain(".youtube.com")
    cookie.setPath("/")
    # Set expiry far in the future
    cookie.setExpirationDate(QDateTime.currentDateTimeUtc().addYears(3))
    cookie.setSecure(True)
    cookie.setHttpOnly(False)
    return cookie


def dismiss_cookie_banner():
    js = """
    const buttons = document.querySelectorAll('button');
    buttons.forEach(btn => {
        if (btn.innerText.includes('Tout refuser')) {
            btn.click();
        }
    });
    """
    view.page().runJavaScript(js)


def on_load_finished(ok):
    if ok:
        QTimer.singleShot(1000, dismiss_cookie_banner)

app = QApplication(sys.argv)
profile = QWebEngineProfile.defaultProfile()
cookie_store = profile.cookieStore()
consent_cookie = create_consent_cookie()
cookie_store.setCookie(consent_cookie, QUrl("https://www.youtube.com"))
view = QWebEngineView()
view.page().profile()
view.loadFinished.connect(on_load_finished)
view.load(QUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
view.showFullScreen()
sys.exit(app.exec_())


# # Pause
# view.page().runJavaScript("document.querySelector('video').pause();")

# # Play
# view.page().runJavaScript("document.querySelector('video').play();")

# # Seek to 30 seconds
# view.page().runJavaScript("document.querySelector('video').currentTime = 30;")

# # Set volume to 50%
# view.page().runJavaScript("document.querySelector('video').volume = 0.5;")
