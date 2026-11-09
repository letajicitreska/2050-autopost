# Pravidla pro návrhy reels (čte je pondělní plánovač)

1. Přístup k podkladům: repozitář `faktaoklimatu/web-2050podcast` je veřejný, `add_repo` nepotřebuješ.
   `git clone --depth 1 https://github.com/faktaoklimatu/web-2050podcast /tmp/w` → `/tmp/w/_episodes/NNN-*.md`.
2. Pestrost: každý reel v týdnu z JINÉ epizody; ne ze stejné epizody jako reel publikovaný/naplánovaný v posledních ~14 dnech.
3. Popisky jen z epizody (summary, úvod, přepis) a z citátu na coveru, ne z lokálních skriptů.
4. Cover si prohlédni (device_stage_files + Read). Bez coveru epizodu nevybírej.
5. Návrh ukaž v chatu, nahrávej až po „schvaluju“.
6. Použité reely se neopakují: jakmile je reel zařazen do fronty, přesuň ho (mv, ne mazání) na Macu z 'reels na instagram' do podsložky 'reels na instagram/_pouzito/' i s coverem. Při výběru vynech vše, co je v schedule.json (jakýkoli status) nebo v _pouzito.
7. DVA TÝDNY NÁSKOKU (od 2026-11-04, na pokyn Petra): fronta má mít vždy naplánováno 2 týdny dopředu. V pondělí X se plánuje týden začínající pondělím X+14 (týden X+7 už má být hotový z minulého týdne). Značka plan/proposed_week.txt obsahuje pondělí PLÁNOVANÉHO týdne (X+14). Úkol končí, pokud značka == X+14 NEBO pokud fronta (schedule.json, status approved/posted) už pokrývá termíny celého týdne X+14. Termíny drž v rytmu jednou za tři dny od posledního naplánovaného reelu.
8. COLLAB (od 2026-11-09, na pokyn Petra): každý reel jde na Instagram jako collab s @faktaoklimatu automaticky (výchozí v scripts/post.py, není třeba nic psát). Při každém pondělním návrhu se Petra u každého reelu zeptej (přes klikací otázky), jestli má být navíc collab s dalším účtem (typicky host). Pokud ano, zapiš do položky `"collaborators": ["ucet_bez_zavinace"]` (max 2 další, celkem s faktaoklimatu nejvýš 3). Handle nevymýšlej ani nehádej, jen ten, který Petr potvrdí. Collab musí druhá strana přijmout v Instagramu, do té doby se reel u ní neukáže. Když collab API odmítne (neexistující/soukromý účet), reel se publikuje bez collabu a v položce je `collab_error`.
