langNames.db: language_names/scraped.sql language_names/scraped-sil.sql language_names/manual.sql language_names/variants.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	cat $^ | sqlite3 $@

clean:
	rm -rf langNames.db dist/ build/

release: langNames.db
	python3 setup.py sdist bdist_wheel

publish: release
	python3 setup.py upload --repository https://test.pypi.org/legacy/ --sign
