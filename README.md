Apertium APy
============

[![Build Status](https://github.com/apertium/apertium-apy/actions/workflows/main.yml/badge.svg?branch=master)](https://github.com/apertium/apertium-apy/actions/workflows/main.yml?query=branch%3Amaster++)
[![Coverage Status](https://coveralls.io/repos/github/apertium/apertium-apy/badge.svg?branch=master)](https://coveralls.io/github/apertium/apertium-apy?branch=master)
[![PyPI](https://img.shields.io/pypi/v/apertium-apy.svg)](https://pypi.org/project/apertium-apy/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/apertium-apy.svg)](https://pypi.org/project/apertium-apy/)

Apertium APy, **Apertium A**PI in **Py**thon, is a web server exposing Apertium
functions including text, document, and webpage translation, as well as morphological
analysis and generation. More information is available on the [Apertium Wiki][1].

Requirements
------------

- Python 3.8+
- Tornado 4.5.3 - 6.0.4 (`python3-tornado` on Debian/Ubuntu)

Additional functionality is provided by installation
of the following packages:

- `apertium-streamparser` enables spell checking
- `requests` enables suggestion handling
- `chromium_compact_language_detector` enables improved language detection (cld2)
- `chardet` enables website character encoding detection
- `commentjson` allows to keep API keys in commented json
- `lxml` enables pair preferences

Precise versions are available in `requirements.txt` and `setup.py`.

Installation
------------

Before you install, you can try out a live version of APy at [apertium.org][2].

APy is available through [PyPi](https://pypi.org/project/apertium-apy/):

    $ pip install apertium-apy

On Ubuntu/Debian, it is also available through `apt`:

    $ wget -qO- https://apertium.projectjj.com/apt/install-nightly.sh | bash
    $ apt-get install apertium-apy

Finally, [GitHub Container Registry][3] hosts an image of the provided
`Dockerfile` with entry point `apertium-apy` exposing port 2737:

    $ docker pull ghcr.io/apertium/apy

Usage
-----

Installation through `apt` or `pip` adds an `apertium-apy` executable:

    $ apertium-apy --help
    usage: apertium-apy [-h] [-s NONPAIRS_PATH] [-l LANG_NAMES] [-F FASTTEXT_MODEL]
                      [-f MISSING_FREQS] [-p PORT] [-c SSL_CERT] [-k SSL_KEY]
                      [-t TIMEOUT] [-j [NUM_PROCESSES]] [-d] [-P LOG_PATH]
                      [-i MAX_PIPES_PER_PAIR] [-n MIN_PIPES_PER_PAIR]
                      [-u MAX_USERS_PER_PIPE] [-m MAX_IDLE_SECS]
                      [-r RESTART_PIPE_AFTER] [-v VERBOSITY] [-V] [-S]
                      [-M UNKNOWN_MEMORY_LIMIT] [-T STAT_PERIOD_MAX_AGE]
                      [-wp WIKI_PASSWORD] [-wu WIKI_USERNAME] [-b]
                      [-rs RECAPTCHA_SECRET] [-md MAX_DOC_PIPES] [-C CONFIG]
                      [-ak API_KEYS]
                      pairs_path

    Apertium APY -- API server for machine translation and language analysis

    positional arguments:
      pairs_path            path to Apertium installed pairs (all modes files in
                            this path are included)

    options:
      -h, --help            show this help message and exit
      -s NONPAIRS_PATH, --nonpairs-path NONPAIRS_PATH
                            path to Apertium tree (only non-translator debug modes
                            are included from this path)
      -l LANG_NAMES, --lang-names LANG_NAMES
                            path to localised language names sqlite database
                            (default = langNames.db)
      -F FASTTEXT_MODEL, --fasttext-model FASTTEXT_MODEL
                            path to fastText language identification model (e.g.
                            lid.release.ftz)
      -f MISSING_FREQS, --missing-freqs MISSING_FREQS
                            path to missing word frequency sqlite database
                            (default = None)
      -p PORT, --port PORT  port to run server on (default = 2737)
      -c SSL_CERT, --ssl-cert SSL_CERT
                            path to SSL Certificate
      -k SSL_KEY, --ssl-key SSL_KEY
                            path to SSL Key File
      -t TIMEOUT, --timeout TIMEOUT
                            timeout for requests (default = 10)
      -j [NUM_PROCESSES], --num-processes [NUM_PROCESSES]
                            number of processes to run (default = 1; use 0 to run
                            one http server per core, where each http server runs
                            all available language pairs)
      -d, --daemon          daemon mode: redirects stdout and stderr to files
                            apertium-apy.log and apertium-apy.err; use with --log-
                            path
      -P LOG_PATH, --log-path LOG_PATH
                            path to log output files to in daemon mode; defaults
                            to local directory
      -i MAX_PIPES_PER_PAIR, --max-pipes-per-pair MAX_PIPES_PER_PAIR
                            how many pipelines we can spin up per language pair
                            (default = 1)
      -n MIN_PIPES_PER_PAIR, --min-pipes-per-pair MIN_PIPES_PER_PAIR
                            when shutting down pipelines, keep at least this many
                            open per language pair (default = 0)
      -u MAX_USERS_PER_PIPE, --max-users-per-pipe MAX_USERS_PER_PIPE
                            how many concurrent requests per pipeline before we
                            consider spinning up a new one (default = 5)
      -m MAX_IDLE_SECS, --max-idle-secs MAX_IDLE_SECS
                            if specified, shut down pipelines that have not been
                            used in this many seconds
      -r RESTART_PIPE_AFTER, --restart-pipe-after RESTART_PIPE_AFTER
                            restart a pipeline if it has had this many requests
                            (default = 1000)
      -v VERBOSITY, --verbosity VERBOSITY
                            logging verbosity
      -V, --version         show APY version
      -S, --scalemt-logs    generates ScaleMT-like logs; use with --log-path;
                            disables
      -M UNKNOWN_MEMORY_LIMIT, --unknown-memory-limit UNKNOWN_MEMORY_LIMIT
                            keeps unknown words in memory until a limit is
                            reached; use with --missing-freqs (default = 1000)
      -T STAT_PERIOD_MAX_AGE, --stat-period-max-age STAT_PERIOD_MAX_AGE
                            How many seconds back to keep track request timing
                            stats (default = 3600)
      -wp WIKI_PASSWORD, --wiki-password WIKI_PASSWORD
                            Apertium Wiki account password for SuggestionHandler
      -wu WIKI_USERNAME, --wiki-username WIKI_USERNAME
                            Apertium Wiki account username for SuggestionHandler
      -b, --bypass-token    ReCAPTCHA bypass token
      -rs RECAPTCHA_SECRET, --recaptcha-secret RECAPTCHA_SECRET
                            ReCAPTCHA secret for suggestion validation
      -md MAX_DOC_PIPES, --max-doc-pipes MAX_DOC_PIPES
                            how many concurrent document translation pipelines we
                            allow (default = 3)
      -C CONFIG, --config CONFIG
                            Configuration file to load options from
      -ak API_KEYS, --api-keys API_KEYS
                            Configuration file to load API keys

Contributing
------------

APy uses [GitHub Actions][4] for continuous integration. Locally, use `make test`
to run the same checks it does. After installing [Pipenv][5], run `pipenv install --dev`
to install the requirements required for development, e.g. linters.

[1]: https://wiki.apertium.org/wiki/Apertium-apy
[2]: https://apertium.org/apy/listPairs
[3]: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
[4]: https://github.com/apertium/apertium-apy/actions
[5]: https://pipenv.pypa.io/en/latest/
