langNames.db: language_names/scraped-cldr.tsv language_names/scraped-sil.tsv language_names/manual-fixes.tsv language_names/manual-additions.tsv language_names/variants.tsv
	language_names/build_db.py $@ $^
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi

dist: langNames.db
	python3 setup.py sdist

release: langNames.db
	python3 setup.py sdist bdist_wheel
	twine upload --sign dist/*

test-release: langNames.db
	python3 setup.py sdist bdist_wheel
	twine upload --sign --repository-url https://test.pypi.org/legacy/ dist/*

unit-test:
	python3 -m unittest tests/test*.py

lint:
	flake8 *.py apertium_apy/ language_names/ tests/
	LC_ALL=C find language_names/*.tsv -exec sh -c 'tail -n +2 {} | sort -c' \;
	mypy --config-file mypy.ini **/*.py

test: unit-test lint

coverage:
	coverage run -m unittest tests/test*.py
	coverage combine
	coverage report --fail-under 40
	ls .coverage

clean:
	rm -f langNames.db

distclean: clean
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .coverage
