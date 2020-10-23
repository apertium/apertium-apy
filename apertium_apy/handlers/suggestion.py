import logging

from tornado import gen

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from apertium_apy import BYPASS_TOKEN, RECAPTCHA_VERIFICATION_URL
from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils.wiki import wiki_get_token, wiki_get_page, wiki_add_text, wiki_edit_page

if False:
    from typing import Optional  # noqa: F401


def add_suggestion(s, suggest_url, edit_token, data):
    content = wiki_get_page(s, suggest_url)
    content = wiki_add_text(content, data)
    edit_result = wiki_edit_page(s, suggest_url, content, edit_token)

    try:
        if edit_result['edit']['result'] == 'Success':
            logging.info('Update of page %s', suggest_url)
            return True
        else:
            logging.error('Update of page %s failed: %s', suggest_url, edit_result)
            return False
    except KeyError:
        return False


class SuggestionHandler(BaseHandler):
    wiki_session = None  # type: Optional[requests.Session]
    wiki_edit_token = None
    SUGGEST_URL = None
    recaptcha_secret = None
    auth_token = None

    @gen.coroutine
    def get(self):
        self.send_error(405, explanation='GET request not supported')

    @gen.coroutine
    def post(self):
        context = self.get_argument('context', None)
        word = self.get_argument('word', None)
        new_word = self.get_argument('newWord', None)
        langpair = self.get_argument('langpair', None)
        recap = self.get_argument('g-recaptcha-response', None)

        if not new_word:
            self.send_error(400, explanation='A suggestion is required')
            return

        if not recap:
            self.send_error(400, explanation='The ReCAPTCHA is required')
            return

        if not all([context, word, langpair, new_word, recap]):
            self.send_error(400, explanation='All arguments were not provided')
            return

        logging.info('Suggestion (%s): Context is %s \n Word: %s ; New Word: %s ', langpair, context, word, new_word)
        logging.info('Now verifying ReCAPTCHA.')

        if not self.recaptcha_secret:
            logging.error('No ReCAPTCHA secret provided!')
            self.send_error(400, explanation='Server not configured correctly for suggestions')
            return

        if recap == BYPASS_TOKEN:
            logging.info('Adding data to wiki with bypass token')
        else:
            # for nginx or when behind a proxy
            x_real_ip = self.request.headers.get('X-Real-IP')
            user_ip = x_real_ip or self.request.remote_ip
            payload = {
                'secret': self.recaptcha_secret,
                'response': recap,
                'remoteip': user_ip,
            }
            recap_request = self.wiki_session.post(RECAPTCHA_VERIFICATION_URL, data=payload)
            if recap_request.json()['success']:
                logging.info('ReCAPTCHA verified, adding data to wiki')
            else:
                logging.info('ReCAPTCHA verification failed, stopping')
                self.send_error(400, explanation='ReCAPTCHA verification failed')
                return

        data = {
            'context': context, 'langpair': langpair,
            'word': word, 'newWord': new_word,
        }
        result = add_suggestion(self.wiki_session,
                                self.SUGGEST_URL, self.wiki_edit_token,
                                data)

        if result:
            self.send_response({
                'responseData': {
                    'status': 'Success',
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        else:
            logging.info('Page update failed, trying to get new edit token')
            self.wiki_edit_token = wiki_get_token(
                SuggestionHandler.wiki_session, 'edit', 'info|revisions')
            logging.info('Obtained new edit token. Trying page update again.')
            result = add_suggestion(self.wiki_session,
                                    self.SUGGEST_URL, self.wiki_edit_token,
                                    data)
            if result:
                self.send_response({
                    'responseData': {
                        'status': 'Success',
                    },
                    'responseDetails': None,
                    'responseStatus': 200,
                })
            else:
                self.send_error(400, explanation='Page update failed')
