#!/usr/bin/env python3
import logging
import json

WIKI_API_URL = 'http://wiki.apertium.org/w/api.php'


# Apertium Wiki utility functions
def wikiLogin(s, loginName, password):
    try:
        payload = {'action': 'login', 'format': 'json', 'lgname': loginName, 'lgpassword': password}
        authResult = s.post(WIKI_API_URL, params=payload)
        authToken = json.loads(authResult.text)['login']['token']
        logging.debug('Auth token: {}'.format(authToken))

        payload = {'action': 'login', 'format': 'json', 'lgname': loginName, 'lgpassword': password, 'lgtoken': authToken}
        authResult = s.post(WIKI_API_URL, params=payload)
        if not json.loads(authResult.text)['login']['result'] == 'Success':
            logging.critical('Failed to login as {}: {}'.format(loginName, json.loads(authResult.text)['login']['result']))
        else:
            logging.info('Login as {} succeeded'.format(loginName))
            return authToken
    except Exception as e:
        logging.critical('Failed to login: {}'.format(e))


def wikiGetPage(s, pageTitle):
    payload = {
        'action': 'query',
        'format': 'json',
        'titles': pageTitle,
        'prop': 'revisions',
        'rvprop': 'content'
    }
    viewResult = s.get(WIKI_API_URL, params=payload)
    jsonResult = json.loads(viewResult.text)

    if 'missing' not in list(jsonResult['query']['pages'].values())[0]:
        return list(jsonResult['query']['pages'].values())[0]['revisions'][0]['*']


def wikiEditPage(s, pageTitle, pageContents, editToken):
    payload = {
        'action': 'edit',
        'format': 'json',
        'title': pageTitle,
        'text': pageContents,
        'bot': 'True',
        'contentmodel': 'wikitext',
        'token': editToken
    }
    editResult = s.post(WIKI_API_URL, data=payload)
    jsonResult = json.loads(editResult.text)
    return jsonResult


def wikiGetToken(s, tokenType, props):
    try:
        payload = {
            'action': 'query',
            'format': 'json',
            'prop': props,
            'intoken': tokenType,
            'titles': 'Main Page'
        }
        tokenResult = s.get(WIKI_API_URL, params=payload)
        token = json.loads(tokenResult.text)['query']['pages']['1']['%stoken' % tokenType]
        logging.debug('%s token: %s' % (tokenType, token))
        return token
    except Exception as e:
        logging.error('Failed to obtain %s token: %s' % (tokenType, e))


def wikiAddText(content, data):
    if not content:
        content = ''

    src, dst = data['langpair'].split('|')
    content += '\n* {{suggest|%s|%s|%s|%s|%s}}' % (src, dst,
                                                   data['word'],
                                                   data['newWord'],
                                                   data['context'],)

    return content
