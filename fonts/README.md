# Skrifttyper (single-line / enkeltstregs)

Filerne her er **uændrede** kopier fra deres oprindelige projekter. nGrave læser
dem (`workers/svg_font.py`) og graverer stregerne direkte — der sker ingen
omdannelse af selve fontfilerne.

| Mappe | Font(e) | Kilde | Licens |
|---|---|---|---|
| `relief/` | Relief SingleLine | <https://github.com/isdat-type/Relief-SingleLine> (`fonts/open_svg/ReliefSingleLineSVG-Regular.svg`) | SIL Open Font License 1.1 — se `relief/OFL.txt` |
| `ems/` | EMS Readability (+ kursiv), EMS Nixish (+ kursiv), EMS Osmotron, EMS Tech, EMS Allure, EMS Felix, EMS Elfin | Inkscape-udvidelsen *Hershey Text* (<https://gitlab.com/inkscape/extensions>, `svg_fonts/`) — skabt af Sheldon B. Michaels, SVG ved Windell H. Oskay (Evil Mad Scientist) | SIL Open Font License 1.1 — se `ems/OFL.txt` og metadata i hver fil |

EMS-fontene er enkeltstregs-versioner af Google-fonte (bl.a. Source Sans Pro,
Nixie One, Orbitron, Architects Daughter, Allura, Felipa, Mountains of
Christmas); den oprindelige designer står i hver fils `<metadata>`.

OFL tillader at fontene bruges, kopieres og distribueres sammen med software
(også kommercielt), så længe licensteksten følger med og fontene ikke sælges
for sig selv. Ændres en font, må den ikke udgives under samme navn.

## Hershey-fontene

Sans, Times, Script, Kursiv og Gotisk kommer fra Python-pakken
[`Hershey-Fonts`](https://pypi.org/project/Hershey-Fonts/) (MIT), der indeholder
de klassiske Hershey-fonte (A. V. Hershey, U.S. National Bureau of Standards,
1967 — frit tilgængelige). De har ikke Æ, Ø og Å; nGrave bygger dem af fontens
egne bogstaver (`workers/dansk.py`).

## Block

nGraves egen nøgle-font i `workers/block_font.py`.

## Tilføj en ny font

1. Læg en enkeltstregs SVG-font (`<font>`/`<glyph d="…">`, samme format som
   Inkscape *Hershey Text*) i en ny mappe sammen med dens licens.
2. Tilføj en linje i `_REGISTER` i `workers/font_manager.py`.
3. Kør `python3 -m unittest discover -s tests` — testene tjekker bl.a. at alle
   fonte kan gravere Æ Ø Å æ ø å.
