"""Shared Google Analytics snippet for every public page.

The measurement call is unchanged, so a GA4 property IP filter still applies
to hits that are sent. This guard only skips loading gtag.js for automated
browsers. AdSense and the Google consent message are separate and stay as they
are. GitHub Pages cannot filter those browsers on the server.
"""

MEASUREMENT_ID = 'G-ZJK92LK3XT'

GA4_TAG = (
    '<!-- Google tag (gtag.js) -->\n'
    '<script>\n'
    '(function(){\n'
    '  if (navigator.webdriver) return;\n'
    "  var ua = navigator.userAgent || '';\n"
    '  if (/HeadlessChrome|Headless|bot|crawler|spider|Lighthouse|PageSpeed|Playwright|Puppeteer|Selenium/i.test(ua)) return;\n'
    '  if (window.outerWidth === 0 || window.outerHeight === 0) return;\n'
    "  var s = document.createElement('script');\n"
    '  s.async = true;\n'
    "  s.src = 'https://www.googletagmanager.com/gtag/js?id=G-ZJK92LK3XT';\n"
    '  document.head.appendChild(s);\n'
    '  window.dataLayer = window.dataLayer || [];\n'
    '  function gtag(){dataLayer.push(arguments);}\n'
    '  window.gtag = gtag;\n'
    "  gtag('js', new Date());\n"
    "  gtag('config','G-ZJK92LK3XT');\n"
    '})();\n'
    '</script>'
)
