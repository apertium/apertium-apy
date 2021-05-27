import logging
import json

WIKI_API_URL = 'https://wiki.apertium.org/w/api.php'


# Apertium Wiki utility functions
def wiki_login(s, login_name, password):
    try:
        payload = {'action': 'login', 'format': 'json', 'lgname': login_name, 'lgpassword': password}
        auth_result = s.post(WIKI_API_URL, params=payload)
        auth_token = json.loads(auth_result.text)['login']['token']
        logging.debug('Auth token: {}'.format(auth_token))

        payload = {'action': 'login', 'format': 'json', 'lgname': login_name, 'lgpassword': password, 'lgtoken': auth_token}
        auth_result = s.post(WIKI_API_URL, params=payload)
        if not json.loads(auth_result.text)['login']['result'] == 'Success':
            logging.critical('Failed to login as {}: {}'.format(login_name, json.loads(auth_result.text)['login']['result']))
        else:
            logging.info('Login as {} succeeded'.format(login_name))
            return auth_token
    except Exception as e:
        logging.critical('Failed to login: {}'.format(e))


def wiki_get_page(s, page_title):
    payload = {
        'action': 'query',
        'format': 'json',
        'titles': page_title,
        'prop': 'revisions',
        'rvprop': 'content',
    }
    view_result = s.get(WIKI_API_URL, params=payload)
    json_result = json.loads(view_result.text)

    if 'missing' not in list(json_result['query']['pages'].values())[0]:
        return list(json_result['query']['pages'].values())[0]['revisions'][0]['*']


def wiki_edit_page(s, page_title, page_contents, edit_token):
    payload = {
        'action': 'edit',
        'format': 'json',
        'title': page_title,
        'text': page_contents,
        'bot': 'True',
        'contentmodel': 'wikitext',
        'token': edit_token,
    }
    edit_result = s.post(WIKI_API_URL, data=payload)
    json_result = json.loads(edit_result.text)
    return json_result


def wiki_get_token(s, token_type, props):
    try:
        payload = {
            'action': 'query',
            'format': 'json',
            'prop': props,
            'intoken': token_type,
            'titles': 'Main Page',
        }
        token_result = s.get(WIKI_API_URL, params=payload)
        token = json.loads(token_result.text)['query']['pages']['1']['%stoken' % token_type]
        logging.debug('%s token: %s', token_type, token)
        return token
    except Exception as e:
        logging.error('Failed to obtain %s token: %s', token_type, e)


def wiki_add_text(content, data):
    if not content:
        content = ''

    src, dst = data['langpair'].split('|')
    content += '\n* {{suggest|%s|%s|%s|%s|%s}}' % (src, dst,
                                                   data['word'],
                                                   data['newWord'],
                                                   data['context'])

    return content
