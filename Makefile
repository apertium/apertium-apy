langNames.db: language_names/scraped.sql language_names/scraped-sil.sql language_names/manual.sql language_names/variants.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	cat $^ | sqlite3 $@

clean:
	rm -f langNames.db
