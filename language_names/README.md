# Language Names

## SQL Files

### Generated - DO NOT EDIT

- `scraped.sql` contains language names from the Unicode CLDR. It is created
  by `scraper.py`.
- `scraped-sil.sql` contains language names from SIL International. It is
  created by `scraper-sil.py`.

### Manual - EDIT

- `manual.sql` contains 'fixes' and 'additions' to the scraped data.
- `variants.sql` contains additions to the scraped data for language variants.
- `turkic.sql` contains Turkic language names.

## Scripts

To run `scraper.py`, first install some dependencies:

    sudo apt-get install libxml2-dev libxslt-dev
    sudo pip3 install lxml

`scraper-sil.py` has no external dependencies.
