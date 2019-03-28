# Language Names

## TSV Files

Each of the following TSVs contains language names. They are combined by
`build_db.py` to create a final SQL database which is used by APy. These
files must be sorted alphabetically for the build to pass. Maintaining a
consistent ordering makes for clearer diffs.

### Generated - DO NOT EDIT

- `scraped.tsv` contains language names from the Unicode CLDR. It is created
  by `scraper-cldr.py`.
- `scraped-sil.tsv` contains language names from SIL International. It is
  created by `scraper-sil.py`.

### Manual - EDIT

- `manual-fixes.tsv` contains fixes to the scraped data.
- `manual-additions.tsv` contains additions to the scraped data.
- `variants.tsv` contains fixes/additions to the scraped data for language
   variants.
- `turkic.tsv` contains Turkic language names.

N.B. Due to historical reasons, there are currently some fixes in
`manual-additions.tsv` and some additions in `manual-fixes.tsv`.

## Scripts

To run `scraper-cldr.py`, first install some dependencies:

    sudo apt-get install libxml2-dev libxslt-dev
    sudo pip3 install lxml

`scraper-sil.py` has no external dependencies.
