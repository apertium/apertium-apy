langNames.db: language-names/scraped.sql language-names/scraped-sil.sql language-names/manual.sql language-names/variants.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	cat $^ | sqlite3 $@

clean:
	rm -f langNames.db
