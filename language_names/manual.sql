PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE fixes (id integer primary key, lg text, inLg text, name text, unique(lg, inLg) on conflict replace);
CREATE TABLE additions (id integer primary key, lg text, inLg text, name text, unique(lg, inLg) on conflict replace);

/* NOTE: many inserts into "fixes" predate the additions table */

INSERT INTO "fixes" VALUES(NULL,'ky','ar','арабча');
INSERT INTO "fixes" VALUES(NULL,'ky','ba','башкортчо');
INSERT INTO "fixes" VALUES(NULL,'ky','cv','чубашча');
INSERT INTO "fixes" VALUES(NULL,'ky','he','ивритче');
INSERT INTO "fixes" VALUES(NULL,'ky','ku','куртча');
INSERT INTO "fixes" VALUES(NULL,'ky','kum','кумукча');
INSERT INTO "fixes" VALUES(NULL,'ky','tk','түркмөнчө');
INSERT INTO "fixes" VALUES(NULL,'ky','tr','түркчө');
INSERT INTO "fixes" VALUES(NULL,'ky','uz','өзбекче');
INSERT INTO "fixes" VALUES(NULL,'ky','kaa','каракалпакча');
INSERT INTO "fixes" VALUES(NULL,'ky','tyv','тывача');
INSERT INTO "fixes" VALUES(NULL,'ky','sah','сахача (якутча)');
INSERT INTO "fixes" VALUES(NULL,'ky','nog','ногойчо');
INSERT INTO "fixes" VALUES(NULL,'kk','az','әзірбайжан тілі');
INSERT INTO "fixes" VALUES(NULL,'kk','ba','башқортша');
INSERT INTO "fixes" VALUES(NULL,'kk','en','ағылшынша');
INSERT INTO "fixes" VALUES(NULL,'kk','gd','шотландиялық гэл тілі');
INSERT INTO "fixes" VALUES(NULL,'kk','kk','қазақша');
INSERT INTO "fixes" VALUES(NULL,'kk','kum','құмықша');
INSERT INTO "fixes" VALUES(NULL,'kk','cv','чувашша');
INSERT INTO "fixes" VALUES(NULL,'kk','ky','қырғызша');
INSERT INTO "fixes" VALUES(NULL,'kk','tk','түрікменше');
INSERT INTO "fixes" VALUES(NULL,'kk','tr','түрікше');
INSERT INTO "fixes" VALUES(NULL,'kk','tt','татарша');
INSERT INTO "fixes" VALUES(NULL,'kk','uz','өзбекше');
INSERT INTO "fixes" VALUES(NULL,'en','kaa','Karakalpak');
INSERT INTO "fixes" VALUES(NULL,'en','ky','Kyrgyz');
INSERT INTO "fixes" VALUES(NULL,'en','os','Ossetian');
INSERT INTO "fixes" VALUES(NULL,'ba','ba','башҡортса');
INSERT INTO "fixes" VALUES(NULL,'tt','en','инглизчә');
INSERT INTO "fixes" VALUES(NULL,'tt','es','испанча');
INSERT INTO "fixes" VALUES(NULL,'tt','kk','казакъча');
INSERT INTO "fixes" VALUES(NULL,'tt','tt','татарча');
INSERT INTO "fixes" VALUES(NULL,'tt','ky','кыргызча');
INSERT INTO "fixes" VALUES(NULL,'tt','tr','төрекчә');
INSERT INTO "fixes" VALUES(NULL,'tt','cv','чувашча');
INSERT INTO "fixes" VALUES(NULL,'tt','kum','кумыкча');
INSERT INTO "fixes" VALUES(NULL,'tt','uz','үзбәкчә');
INSERT INTO "fixes" VALUES(NULL,'tt','ba','башкортча');
INSERT INTO "fixes" VALUES(NULL,'tt','tk','төрекмәнчә');
INSERT INTO "fixes" VALUES(NULL,'tt','kaa','каракалпакча');
INSERT INTO "fixes" VALUES(NULL,'tt','tyv','тувача');
INSERT INTO "fixes" VALUES(NULL,'tt','az','азәрбайҗанча');
INSERT INTO "fixes" VALUES(NULL,'tt','ru','урысча');
INSERT INTO "fixes" VALUES(NULL,'an','af','afrikaans');
INSERT INTO "fixes" VALUES(NULL,'an','an','aragonés');
INSERT INTO "fixes" VALUES(NULL,'an','ar','arabe');
INSERT INTO "fixes" VALUES(NULL,'an','as','asamés');
INSERT INTO "fixes" VALUES(NULL,'an','ast','asturiano');
INSERT INTO "fixes" VALUES(NULL,'an','av','avaro');
INSERT INTO "fixes" VALUES(NULL,'an','az','azeri');
INSERT INTO "fixes" VALUES(NULL,'an','ba','baixkir');
INSERT INTO "fixes" VALUES(NULL,'an','be','belorruso');
INSERT INTO "fixes" VALUES(NULL,'an','bg','bulgaro');
INSERT INTO "fixes" VALUES(NULL,'an','bi','bislama');
INSERT INTO "fixes" VALUES(NULL,'an','bn','bengalí');
INSERT INTO "fixes" VALUES(NULL,'an','br','bretón');
INSERT INTO "fixes" VALUES(NULL,'an','bs','bosnio');
INSERT INTO "fixes" VALUES(NULL,'an','bua','buriat');
INSERT INTO "fixes" VALUES(NULL,'an','ca','catalán');
INSERT INTO "fixes" VALUES(NULL,'an','ceb','cebuano');
INSERT INTO "fixes" VALUES(NULL,'an','ckb','kurd sorani');
INSERT INTO "fixes" VALUES(NULL,'an','co','corso');
INSERT INTO "fixes" VALUES(NULL,'an','cs','checo');
INSERT INTO "fixes" VALUES(NULL,'an','csb','caixubio');
INSERT INTO "fixes" VALUES(NULL,'an','cu','eslau eclesiastico');
INSERT INTO "fixes" VALUES(NULL,'an','cv','chuvaixo');
INSERT INTO "fixes" VALUES(NULL,'an','cy','galés');
INSERT INTO "fixes" VALUES(NULL,'an','da','danés');
INSERT INTO "fixes" VALUES(NULL,'an','de','alemán');
INSERT INTO "fixes" VALUES(NULL,'an','dsb','baixo sorabo');
INSERT INTO "fixes" VALUES(NULL,'an','el','griego');
INSERT INTO "fixes" VALUES(NULL,'an','en','anglés');
INSERT INTO "fixes" VALUES(NULL,'an','eo','esperanto');
INSERT INTO "fixes" VALUES(NULL,'an','es','espanyol');
INSERT INTO "fixes" VALUES(NULL,'an','et','estonio');
INSERT INTO "fixes" VALUES(NULL,'an','eu','basco');
INSERT INTO "fixes" VALUES(NULL,'an','fa','persa');
INSERT INTO "fixes" VALUES(NULL,'an','fi','finés');
INSERT INTO "fixes" VALUES(NULL,'an','fo','feroés');
INSERT INTO "fixes" VALUES(NULL,'an','fr','francés');
INSERT INTO "fixes" VALUES(NULL,'an','fy','frisón oriental');
INSERT INTO "fixes" VALUES(NULL,'an','ga','irlandés');
INSERT INTO "fixes" VALUES(NULL,'an','gd','gaelico escocés');
INSERT INTO "fixes" VALUES(NULL,'an','gl','gallego');
INSERT INTO "fixes" VALUES(NULL,'an','gn','guaraní');
INSERT INTO "fixes" VALUES(NULL,'an','gv','manx');
INSERT INTO "fixes" VALUES(NULL,'an','he','hebreu');
INSERT INTO "fixes" VALUES(NULL,'an','hi','hindi');
INSERT INTO "fixes" VALUES(NULL,'an','hr','crovata');
INSERT INTO "fixes" VALUES(NULL,'an','hsb','alto sorabo');
INSERT INTO "fixes" VALUES(NULL,'an','ht','haitiano');
INSERT INTO "fixes" VALUES(NULL,'an','hu','hongaro');
INSERT INTO "fixes" VALUES(NULL,'an','hy','armenio');
INSERT INTO "fixes" VALUES(NULL,'an','ia','interlingua');
INSERT INTO "fixes" VALUES(NULL,'an','id','indonesio');
INSERT INTO "fixes" VALUES(NULL,'an','is','islandés');
INSERT INTO "fixes" VALUES(NULL,'an','it','italiano');
INSERT INTO "fixes" VALUES(NULL,'an','kaa','karakalpak');
INSERT INTO "fixes" VALUES(NULL,'an','kk','kazakho');
INSERT INTO "fixes" VALUES(NULL,'an','ko','coreano');
INSERT INTO "fixes" VALUES(NULL,'an','ku','kurdo');
INSERT INTO "fixes" VALUES(NULL,'an','kum','kumiko');
INSERT INTO "fixes" VALUES(NULL,'an','kv','komi');
INSERT INTO "fixes" VALUES(NULL,'an','ky','kirguíz');
INSERT INTO "fixes" VALUES(NULL,'an','la','latín');
INSERT INTO "fixes" VALUES(NULL,'an','lb','luxemburgués');
INSERT INTO "fixes" VALUES(NULL,'an','lg','ganda');
INSERT INTO "fixes" VALUES(NULL,'an','lo','laosiano');
INSERT INTO "fixes" VALUES(NULL,'an','lt','lituano');
INSERT INTO "fixes" VALUES(NULL,'an','lv','letón');
INSERT INTO "fixes" VALUES(NULL,'an','mfe','mauriciano');
INSERT INTO "fixes" VALUES(NULL,'an','mk','macedonio');
INSERT INTO "fixes" VALUES(NULL,'an','ml','malayalam');
INSERT INTO "fixes" VALUES(NULL,'an','mr','marathi');
INSERT INTO "fixes" VALUES(NULL,'an','ms','malayo');
INSERT INTO "fixes" VALUES(NULL,'an','mt','maltés');
INSERT INTO "fixes" VALUES(NULL,'an','myv','mordoviano erza');
INSERT INTO "fixes" VALUES(NULL,'an','nb','noruego bokmål');
INSERT INTO "fixes" VALUES(NULL,'an','ne','nepalés');
INSERT INTO "fixes" VALUES(NULL,'an','nl','neerlandés');
INSERT INTO "fixes" VALUES(NULL,'an','nn','noruego nynorsk');
INSERT INTO "fixes" VALUES(NULL,'an','no','noruego');
INSERT INTO "fixes" VALUES(NULL,'an','nog','nogai');
INSERT INTO "fixes" VALUES(NULL,'an','oc','occitán');
INSERT INTO "fixes" VALUES(NULL,'an','os','osseto');
INSERT INTO "fixes" VALUES(NULL,'an','pa','panchabí');
INSERT INTO "fixes" VALUES(NULL,'an','pl','polonés');
INSERT INTO "fixes" VALUES(NULL,'an','pt','portugués');
INSERT INTO "fixes" VALUES(NULL,'an','rm','romanche');
INSERT INTO "fixes" VALUES(NULL,'an','rn','rundi');
INSERT INTO "fixes" VALUES(NULL,'an','ro','rumano');
INSERT INTO "fixes" VALUES(NULL,'an','ru','ruso');
INSERT INTO "fixes" VALUES(NULL,'an','rup','arrumano');
INSERT INTO "fixes" VALUES(NULL,'an','sa','sanscrito');
INSERT INTO "fixes" VALUES(NULL,'an','sah','yacuto');
INSERT INTO "fixes" VALUES(NULL,'an','sc','sardo');
INSERT INTO "fixes" VALUES(NULL,'an','sco','escocès');
INSERT INTO "fixes" VALUES(NULL,'an','se','sami septentrional');
INSERT INTO "fixes" VALUES(NULL,'an','sh','serbocrovata');
INSERT INTO "fixes" VALUES(NULL,'an','si','singalés');
INSERT INTO "fixes" VALUES(NULL,'an','sk','eslovaco');
INSERT INTO "fixes" VALUES(NULL,'an','sl','esloveno');
INSERT INTO "fixes" VALUES(NULL,'an','sma','sami meridional');
INSERT INTO "fixes" VALUES(NULL,'an','smj','sami lule');
INSERT INTO "fixes" VALUES(NULL,'an','sq','albanés');
INSERT INTO "fixes" VALUES(NULL,'an','sr','serbio');
INSERT INTO "fixes" VALUES(NULL,'an','sv','sueco');
INSERT INTO "fixes" VALUES(NULL,'an','sw','suahili');
INSERT INTO "fixes" VALUES(NULL,'an','ta','tamil');
INSERT INTO "fixes" VALUES(NULL,'an','te','telugu');
INSERT INTO "fixes" VALUES(NULL,'an','tet','tetun');
INSERT INTO "fixes" VALUES(NULL,'an','tg','tadjik');
INSERT INTO "fixes" VALUES(NULL,'an','th','tailandés');
INSERT INTO "fixes" VALUES(NULL,'an','tk','turcomano');
INSERT INTO "fixes" VALUES(NULL,'an','tl','tagalog');
INSERT INTO "fixes" VALUES(NULL,'an','tr','turco');
INSERT INTO "fixes" VALUES(NULL,'an','tt','tartre');
INSERT INTO "fixes" VALUES(NULL,'an','tyv','tuviniano');
INSERT INTO "fixes" VALUES(NULL,'an','udm','udmurt');
INSERT INTO "fixes" VALUES(NULL,'an','uk','ucrainiano');
INSERT INTO "fixes" VALUES(NULL,'an','ur','urdú');
INSERT INTO "fixes" VALUES(NULL,'an','uz','uzbeko');
INSERT INTO "fixes" VALUES(NULL,'an','vi','vietnamita');
INSERT INTO "fixes" VALUES(NULL,'an','xh','xosa');
INSERT INTO "fixes" VALUES(NULL,'an','zh','chino');
INSERT INTO "fixes" VALUES(NULL,'an','zu','zulú');
/*INSERT INTO "fixes" VALUES(NULL,'av','af','afrikaans');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','an','aragonés');*/
INSERT INTO "fixes" VALUES(NULL,'av','ar','гӏараб');
/*INSERT INTO "fixes" VALUES(NULL,'av','ast','asturiano');*/
INSERT INTO "fixes" VALUES(NULL,'av','av','магӏарул');
INSERT INTO "fixes" VALUES(NULL,'av','az','азарбижан');
/*INSERT INTO "fixes" VALUES(NULL,'av','ba','baixkir');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','be','belorruso');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','bg','bulgaro');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','br','bretón');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','bs','bosnio');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','ca','catalán');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','cv','chuvaixo');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','cy','уэльс');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','da','danés');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','el','грек');*/
INSERT INTO "fixes" VALUES(NULL,'av','en','ингилис');
INSERT INTO "fixes" VALUES(NULL,'av','eo','эсперанто');
/*INSERT INTO "fixes" VALUES(NULL,'av','es','espanyol');
/*INSERT INTO "fixes" VALUES(NULL,'av','et','estonio');*/
INSERT INTO "fixes" VALUES(NULL,'av','eu','баск');
INSERT INTO "fixes" VALUES(NULL,'av','fr','паранг');
/*INSERT INTO "fixes" VALUES(NULL,'av','gl','gallego');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','hr','crovata');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','id','indonesio');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','is','islandés');*/
INSERT INTO "fixes" VALUES(NULL,'av','it','итал');
/*INSERT INTO "fixes" VALUES(NULL,'av','kk','kazakho');*/
INSERT INTO "fixes" VALUES(NULL,'av','kum','лъарагӏ');
/*INSERT INTO "fixes" VALUES(NULL,'av','ky','kirguíz');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','mk','macedonio');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','ms','malayo');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','mt','maltés');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','nb','noruego bokmål');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','nl','neerlandés');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','nn','noruego nynorsk');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','oc','occitán');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','pt','portugués');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','ro','rumano');*/
INSERT INTO "fixes" VALUES(NULL,'av','ru','гӏурус');
/*INSERT INTO "fixes" VALUES(NULL,'av','se','sami septentrional');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','sh','serbocrovata');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','sl','esloveno');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','sr','serbio');*/
/*INSERT INTO "fixes" VALUES(NULL,'av','sv','sueco');*/
INSERT INTO "fixes" VALUES(NULL,'av','tr','турк');
INSERT INTO "fixes" VALUES(NULL,'av','tt','татар');
/*INSERT INTO "fixes" VALUES(NULL,'av','uk','укр');*/
INSERT INTO "fixes" VALUES(NULL,'ug','kk','قازاقچە');
INSERT INTO "fixes" VALUES(NULL,'ug','tt','تاتارچە');
INSERT INTO "fixes" VALUES(NULL,'ug','ky','قىرغىزچە');
INSERT INTO "fixes" VALUES(NULL,'ug','uz','ئۆزبەكچە');
INSERT INTO "fixes" VALUES(NULL,'ug','kaa','قاراقالپاقچە');
INSERT INTO "fixes" VALUES(NULL,'ug','ug','ئۇيغۇرچە');
INSERT INTO "fixes" VALUES(NULL,'en','ug','Uyghur');
INSERT INTO "fixes" VALUES(NULL,'ru','ug','уйгурский');
INSERT INTO "fixes" VALUES(NULL,'uz','ug','uygʻurcha');
INSERT INTO "fixes" VALUES(NULL,'kk','ug','ұйғұрша');
INSERT INTO "fixes" VALUES(NULL,'ky','ug','уйгурча');
INSERT INTO "fixes" VALUES(NULL,'kaa','kk','qazaqsha');
INSERT INTO "fixes" VALUES(NULL,'kaa','kaa','qaraqalpaqsha');
INSERT INTO "fixes" VALUES(NULL,'kaa','uz','oʻzbekshe');
INSERT INTO "fixes" VALUES(NULL,'kaa','tt','tatarsha');
INSERT INTO "fixes" VALUES(NULL,'kaa','ky','qırgʻızsha');
INSERT INTO "fixes" VALUES(NULL,'uz','kaa','qoraqalpoqcha');
INSERT INTO "fixes" VALUES(NULL,'uz','nog','noʻgʻaycha');
INSERT INTO "fixes" VALUES(NULL,'uz','sah','saxacha (yoqutcha)');
INSERT INTO "fixes" VALUES(NULL,'uz','chv','chuvashcha');
INSERT INTO "fixes" VALUES(NULL,'uz','tyv','tuvacha');
INSERT INTO "fixes" VALUES(NULL,'uz','kum','qoʻmiqcha');
INSERT INTO "fixes" VALUES(NULL,'uz','bak','boshqircha');
INSERT INTO "fixes" VALUES(NULL,'tyv','tyv','тыва дылда');
INSERT INTO "fixes" VALUES(NULL,'nog','nog','ногъайша');
INSERT INTO "fixes" VALUES(NULL,'sah','sah','сахалыы');
INSERT INTO "fixes" VALUES(NULL,'en','crh','Crimean Tatar');
INSERT INTO "fixes" VALUES(NULL,'uz','crh','qrimtatarcha');
INSERT INTO "fixes" VALUES(NULL,'az','crh','krımtatarca');
INSERT INTO "fixes" VALUES(NULL,'bak','crh','Ҡырымтатарса');
INSERT INTO "fixes" VALUES(NULL,'chv','crh','крымтутарла');
INSERT INTO "fixes" VALUES(NULL,'crh','crh','qırımtatarca');
INSERT INTO "fixes" VALUES(NULL,'kaa','crh','qırımtatarsha');
INSERT INTO "fixes" VALUES(NULL,'ru','crh','крымско-татарский');
INSERT INTO "fixes" VALUES(NULL,'tt','crh','кырымтатарча');
INSERT INTO "fixes" VALUES(NULL,'ky','crh','кырымтатарча');
INSERT INTO "fixes" VALUES(NULL,'kk','crh','қырымтатарша');
INSERT INTO "fixes" VALUES(NULL,'tr','crh','Kırımtatarca');
INSERT INTO "fixes" VALUES(NULL,'uig','crh','قرىمتاتارچا');
INSERT INTO "fixes" VALUES(NULL,'kk','sah','сахаша (якутша)');
INSERT INTO "fixes" VALUES(NULL,'kk','kaa','қарақалпақша');
INSERT INTO "fixes" VALUES(NULL,'kk','tyv','тываша');
INSERT INTO "fixes" VALUES(NULL,'ca','crh','tàtar de Crimea');
INSERT INTO "fixes" VALUES(NULL,'sc','srd','sardu');
INSERT INTO "fixes" VALUES(NULL,'sc','ita','italianu');
INSERT INTO "fixes" VALUES(NULL,'ca','srd','sard');
INSERT INTO "fixes" VALUES(NULL,'en','srd','Sardinian');
INSERT INTO "fixes" VALUES(NULL,'it','srd','sardo');
INSERT INTO "fixes" VALUES(NULL,'es','srd','sardo');
INSERT INTO "fixes" VALUES(NULL,'eu','crh','Krimeako tatarera');
INSERT INTO "fixes" VALUES(NULL,'en','oci_aran','Occitan Aranese');
INSERT INTO "fixes" VALUES(NULL,'de','oci_aran','Okzitanisch Aranesisch');
INSERT INTO "fixes" VALUES(NULL,'oci_aran','oci_aran','Aranés');
INSERT INTO "fixes" VALUES(NULL,'kmr','kmr','Kurmancî');
INSERT INTO "fixes" VALUES(NULL,'en','kmr','Kurdish Kurmanji');
INSERT INTO "fixes" VALUES(NULL,'scn','scn','sicilianu');
INSERT INTO "fixes" VALUES(NULL,'es','scn','siciliano');
INSERT INTO "fixes" VALUES(NULL,'ca','scn','sicilià');
INSERT INTO "fixes" VALUES(NULL,'en','scn','Sicilian');

INSERT INTO "fixes" VALUES(NULL,'en','smn','Inari Saami');
INSERT INTO "fixes" VALUES(NULL,'fi','smn','inarinsaame');
INSERT INTO "fixes" VALUES(NULL,'nn','smn','enaresamisk');
INSERT INTO "fixes" VALUES(NULL,'nb','smn','enaresamisk');
INSERT INTO "fixes" VALUES(NULL,'sma','smn','enaresaemien');
INSERT INTO "fixes" VALUES(NULL,'se','smn','anársámegiella');
INSERT INTO "fixes" VALUES(NULL,'smj','smn','anársámegiella');
INSERT INTO "fixes" VALUES(NULL,'smn','smn','anarâškielâ');

INSERT INTO "fixes" VALUES(NULL,'en','smj','Lule Saami');
INSERT INTO "fixes" VALUES(NULL,'fi','smj','luulajansaame');
INSERT INTO "fixes" VALUES(NULL,'nn','smj','lulesamisk');
INSERT INTO "fixes" VALUES(NULL,'nb','smj','lulesamisk');
INSERT INTO "fixes" VALUES(NULL,'sma','smj','julevsaemiengïele');
INSERT INTO "fixes" VALUES(NULL,'se','smj','julevsámegiella');
INSERT INTO "fixes" VALUES(NULL,'smj','smj','julevsámegiella');
INSERT INTO "fixes" VALUES(NULL,'smn','smj','juulevsämikielâ');

INSERT INTO "fixes" VALUES(NULL,'sma','se','noerhtesaemiengïele');
INSERT INTO "fixes" VALUES(NULL,'smj','se','nuorttasámegiella');
INSERT INTO "fixes" VALUES(NULL,'smn','se','pajekielâ');

INSERT INTO "fixes" VALUES(NULL,'sma','sma','åarjelsaemiengïele');
INSERT INTO "fixes" VALUES(NULL,'smj','sma','oarjjelsámegiella');
INSERT INTO "fixes" VALUES(NULL,'smn','sma','maadâsämikielâ');

INSERT INTO "fixes" VALUES(NULL,'sma','no','daaroegïele');
INSERT INTO "fixes" VALUES(NULL,'smj','no','dárogiella');
INSERT INTO "fixes" VALUES(NULL,'smn','no','tárukielâ');

INSERT INTO "fixes" VALUES(NULL,'sma','fi','såevmiengïele');
INSERT INTO "fixes" VALUES(NULL,'smj','fi','suomagiella');
INSERT INTO "fixes" VALUES(NULL,'smn','fi','suomâkielâ');

INSERT INTO "fixes" VALUES(NULL,'tr','gag','Gagavuzca');
INSERT INTO "fixes" VALUES(NULL,'gag','gag','Gagauzça');
INSERT INTO "fixes" VALUES(NULL,'crh','gag','ğağauzça');
INSERT INTO "fixes" VALUES(NULL,'kk','gag','ғағауызша');
INSERT INTO "fixes" VALUES(NULL,'ky','gag','гагаузча');

INSERT INTO "additions" VALUES(NULL,'en','lvs','Latvian');
INSERT INTO "additions" VALUES(NULL,'lvs','lvs','latviešu valoda');

INSERT INTO "additions" VALUES(NULL,'guj','guj','ગુજરાતી');
INSERT INTO "additions" VALUES(NULL,'byv','byv','Mə̀dʉ̂mbɑ̀');

INSERT INTO "additions" VALUES(NULL,'en','olo','Livvi-Karelian');
INSERT INTO "additions" VALUES(NULL,'en','sjo','Xibe');
INSERT INTO "additions" VALUES(NULL,'en','snd','Sindhi');
INSERT INTO "additions" VALUES(NULL,'en','qve','Quechua');
INSERT INTO "additions" VALUES(NULL,'en','ssp','Spanish Sign Language');
INSERT INTO "additions" VALUES(NULL,'en','khk','Khalkha Mongolian');

INSERT INTO "additions" VALUES(NULL,'khk','khk','монгол хэл');
INSERT INTO "additions" VALUES(NULL,'kmr','kmr','Kurmancî');


INSERT INTO "languageNames" (lg, inLg, name) select lg, inLg, name from "fixes";
INSERT INTO "languageNames" (lg, inLg, name) select lg, inLg, name from "additions";
COMMIT;
