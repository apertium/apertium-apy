langNames.db: language_names/scraped.sql language_names/scraped-sil.sql language_names/manual.sql language_names/variants.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	cat $^ | sqlite3 $@

release: langNames.db
	python3 setup.py sdist bdist_wheel

publish: release
	python3 setup.py upload --repository https://test.pypi.org/legacy/ --sign

test:
	flake8 **/*.py
	mypy --config-file mypy.ini **/*.py
	coverage run --source apertium_apy -m unittest tests/test*.py
	coverage report --fail-under 20

clean:
	rm -rf langNames.db dist/ build/
