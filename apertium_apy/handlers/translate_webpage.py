import html
import logging
import os
import re
import time
from hashlib import sha1
from urllib.parse import urlparse, urlunsplit

from tornado import gen
from tornado import httpclient
from typing import Optional  # noqa: F401


try:
    import chardet
except ImportError:             # type should be Optional[Module] but there's no module in mypy? TODO
    chardet = None              # type: ignore


from apertium_apy.utils import translation
from apertium_apy.handlers.translate import TranslateHandler


class TranslateWebpageHandler(TranslateHandler):
    def url_repl(self, base, attr, quote, aurl):
        a = urlparse(aurl)
        if a.netloc == '':
            newurl = urlunsplit((base.scheme,
                                 base.netloc,
                                 a.path,
                                 a.query,
                                 a.fragment))
        else:
            newurl = aurl
        return ' {a}={q}{u}{q}'.format(a=attr, u=newurl, q=quote)

    def unescape(self, page):
        # First workaround old bug that exists in a lot of
        # Windows-based web pages, see
        # http://stackoverflow.com/a/1398921/69663 :
        page = page.replace('&#150;', '&#8211;')
        # Unescape all other entities the regular way:
        return html.unescape(page)

    def clean_html(self, page, urlbase):
        page = self.unescape(page)
        if urlbase.netloc in ['www.avvir.no', 'avvir.no']:
            page = re.sub(r'([a-zæøåášžđŋ])=([a-zæøåášžđŋ])',
                          '\\1\\2',
                          page)
        page = page.replace('\u00ad', '')  # soft hyphen
        return page

    def html_to_text(self, page, url):
        encoding = 'utf-8'
        if chardet:
            encoding = chardet.detect(page).get('encoding', 'utf-8') or encoding
        base = urlparse(url)
        text = self.clean_html(page.decode(encoding), base)  # type: str
        return re.sub(r' (href|src)=([\'"])(..*?)\2',
                      lambda m: self.url_repl(base, m.group(1), m.group(2), m.group(3)),
                      text)

    def set_cached(self, pair, url, translated, origtext):
        """Cache translated text for a pair and url to memory, and disk.
        Also caches origtext to disk; see cache_path."""
        if pair not in self.url_cache:
            self.url_cache[pair] = {}
        elif len(self.url_cache[pair]) > self.max_inmemory_url_cache:
            self.url_cache[pair] = {}
        ts = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(time.time()))
        self.url_cache[pair][url] = (ts, translated)
        if self.url_cache_path is None:
            logging.info('No --url-cache-path, not storing cached url to disk')
            return
        dirname, basename = self.cache_path(self.url_cache_path, pair, url)
        os.makedirs(dirname, exist_ok=True)
        statvfs = os.statvfs(dirname)
        if (statvfs.f_frsize * statvfs.f_bavail) < self.min_free_space_disk_url_cache:
            logging.warn('Disk of --url-cache-path has < {} free, not storing cached url to disk'.format(
                self.min_free_space_disk_url_cache))
            return
        # Note: If we make this a @gen.coroutine, we will need to lock
        # the file to avoid concurrent same-url requests clobbering:
        path = os.path.join(dirname, basename)
        with open(path, 'w') as f:
            f.write(ts)
            f.write('\n')
            f.write(translated)
        origpath = os.path.join(dirname, pair[0])
        with open(origpath, 'w') as f:
            f.write(origtext)

    def cache_path(self, url_cache_path, pair, url):
        """Give the directory for where to cache the translation of this url,
        and the file name to use for this pair."""
        hsh = sha1(url.encode('utf-8')).hexdigest()
        dirname = os.path.join(url_cache_path,
                               # split it to avoid too many files in one dir:
                               hsh[:1], hsh[1:2], hsh[2:])
        return (dirname, '{}-{}'.format(*pair))

    def get_cached(self, pair, url):
        if not self.url_cache_path:
            return None
        if pair not in self.url_cache:
            self.url_cache[pair] = {}
        if url in self.url_cache[pair]:
            logging.info('Got cache from memory')
            return self.url_cache[pair][url]
        dirname, basename = self.cache_path(self.url_cache_path, pair, url)
        path = os.path.join(dirname, basename)
        if os.path.exists(path):
            logging.info('Got cache on disk, we want to retranslate in background …')
            with open(path, 'r') as f:
                return (f.readline().strip(), f.read())

    def retranslate_cache(self, pair, url, cached):
        """If we've got something from the cache, and it isn't in memory, then
        it was from disk. We want to retranslate anything we found on
        disk, since it's probably using older versions of the language
        pair.
        """
        mem_cached = self.url_cache.get(pair, {}).get(url)
        if mem_cached is None and cached is not None and self.url_cache_path is not None:
            dirname, _ = self.cache_path(self.url_cache_path, pair, url)
            origpath = os.path.join(dirname, pair[0])
            if os.path.exists(origpath):
                return open(origpath, 'r').read()

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      # Don't yet know the size of the text, and don't want to fetch it unnecessarily:
                                      -1)
        if pair is None:
            return
        self.note_pair_usage(pair)
        mode_path = self.pairs['%s-%s' % pair]
        url = self.get_argument('url')
        if not url.startswith('http'):
            url = 'http://' + url
        got304 = False
        cached = self.get_cached(pair, url)
        request = httpclient.HTTPRequest(url=url,
                                         # TODO: tweak timeouts:
                                         connect_timeout=20.0,
                                         request_timeout=20.0)

        try:
            response = yield httpclient.AsyncHTTPClient().fetch(request)
        except Exception as e:
            logging.info('%s exception has occurred', e)
            self.send_error(404, explanation='{} on fetching url: {}'.format('Error 404', e))
            return
        try:
            response = yield httpclient.AsyncHTTPClient().fetch(request, raise_error=True)
        except httpclient.HTTPError as e:
            if e.code == 304:
                got304 = True
                logging.info('304, can use cache')
            else:
                logging.error(e)
                self.send_error(503, explanation='{} on fetching url: {}'.format(response.code, response.error))
                return
        if got304 and cached is not None:
            translation_catpipeline = translation.CatPipeline  # type: ignore
            translated = yield translation_catpipeline().translate(cached[1])
        else:
            if response.body is None:
                self.send_error(503, explanation='got an empty file on fetching url: {}'.format(url))
                return
            page = response.body  # type: bytes
            try:
                to_translate = self.html_to_text(page, url)
            except UnicodeDecodeError as e:
                logging.info("/translatePage '{}' gave UnicodeDecodeError {}".format(url, e))
                self.send_error(503, explanation="Couldn't decode (or detect charset/encoding of) {}".format(url))
                return
            before = self.log_before_translation()
            translated = yield translation.translate_html_mark_headings(to_translate, mode_path)
            self.log_after_translation(before, len(to_translate))
            self.set_cached(pair, url, translated, to_translate)
        self.send_response({
            'responseData': {
                'translatedText': self.maybe_strip_marks(self.mark_unknown, pair, translated),
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
        retranslate = self.retranslate_cache(pair, url, cached)
        if got304 and retranslate is not None:
            logging.info('Retranslating {}'.format(url))
            translated = yield translation.translate_html_mark_headings(retranslate, mode_path)
            logging.info('Done retranslating {}'.format(url))
            self.set_cached(pair, url, translated, retranslate)
