import random
import string

RECAPTCHA_VERIFICATION_URL = 'https://www.google.com/recaptcha/api/siteverify'
BYPASS_TOKEN = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(24))
