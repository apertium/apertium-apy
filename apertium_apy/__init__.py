import random
import string

if False:
    from typing import Optional  # noqa: F401

    from apertium_apy import missingdb  # noqa: F401

missing_freqs_db = None  # type: Optional[missingdb.MissingDb]  # has to be global for sig_handler :-/

RECAPTCHA_VERIFICATION_URL = 'https://www.google.com/recaptcha/api/siteverify'
BYPASS_TOKEN = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(24))
