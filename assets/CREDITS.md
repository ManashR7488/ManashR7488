# Credits, licences and sources

Everything below is embedded inside the five SVGs in this folder. The SVGs make no
network requests: fonts and photos are inlined as `data:` URIs.

## Photos

| File | Source | How it is used |
| --- | --- | --- |
| `id.png` (1086×1448, RGBA) | Supplied by Manash Ranjan Mahanand | `hero.svg`: whole image downscaled to 600×800. `id-dashboard.svg`: head-and-shoulders crop (source pixels 170–916 × 70–943), downscaled to 352 px wide. |
| `right_pointing.png` (1024×1536, RGBA) | Supplied by Manash Ranjan Mahanand | `connect.svg`: whole image downscaled to 480×720. |

The pixels are not redrawn, retouched, masked or recoloured. Downscaling is done in
premultiplied-alpha space and saved as lossless PNG, so the original cut-out alpha is
kept. The only clipping is the rounded photo window on the ID card and the card's own
rounded corners. The full-size originals are in `tools/src/`.

## Fonts (SIL Open Font License 1.1)

| Font | Copyright | Package | Weights embedded |
| --- | --- | --- | --- |
| Bricolage Grotesque | © 2022 The Bricolage Grotesque Project Authors (https://github.com/ateliertriay/bricolage) | `@fontsource/bricolage-grotesque@5.3.0` (latin) | 400, 500, 600, 800 |
| JetBrains Mono | © 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) | `@fontsource/jetbrains-mono@5.3.0` (latin) | 500, 700 |

Each SVG embeds a WOFF2 subset of only the glyphs it uses. The fonts' copyright and
licence name records are kept, and the full licence text is also in each SVG's
`<metadata>`. The licence files are [`licenses/OFL-BricolageGrotesque.txt`](licenses/OFL-BricolageGrotesque.txt)
and [`licenses/OFL-JetBrainsMono.txt`](licenses/OFL-JetBrainsMono.txt). Neither font declares a
Reserved Font Name. Inside the SVGs the families are called `MR Bricolage` and `MR JetBrains`.

## Brand icons

All brand marks come from [Simple Icons](https://simpleicons.org) (icon data CC0-1.0). The
trademarks belong to their owners and are used only to identify the technology or platform.

| Icon | Slug | Package | Official source recorded by Simple Icons | Used in |
| --- | --- | --- | --- | --- |
| Arduino | `arduino` | simple-icons@16.36.0 | <https://www.arduino.cc> | about-life.svg, stack.svg |
| Blender | `blender` | simple-icons@16.36.0 | <https://www.blender.org/about/logo> | about-life.svg |
| Docker | `docker` | simple-icons@16.36.0 | <https://www.docker.com/company/newsroom/media-resources> | stack.svg |
| Espressif | `espressif` | simple-icons@16.36.0 | <https://www.espressif.com> | about-life.svg, stack.svg |
| Express | `express` | simple-icons@16.36.0 | <https://github.com/openjs-foundation/artwork/blob/3816245ebbf4707bdafde748350ac8476b6b5b62/projects/express/express-icon-black.svg> | stack.svg |
| GitHub | `github` | simple-icons@16.36.0 | <https://github.com/logos> | connect.svg, id-dashboard.svg |
| Gmail | `gmail` | simple-icons@16.36.0 | <https://fonts.gstatic.com/s/i/productlogos/gmail_2020q4/v8/192px.svg> | connect.svg |
| Google Gemini | `googlegemini` | simple-icons@16.36.0 | <https://gemini.google.com> | stack.svg |
| Instagram | `instagram` | simple-icons@16.36.0 | <https://about.meta.com/brand/resources/instagram> | connect.svg |
| JavaScript | `javascript` | simple-icons@16.36.0 | <https://github.com/voodootikigod/logo.js/blob/1544bdeed6d618a6cfe4f0650d04ab8d9cfa76d9/js.svg> | stack.svg |
| LangChain | `langchain` | simple-icons@16.36.0 | <https://www.langchain.com/langchain> | stack.svg |
| LinkedIn | `linkedin` | simple-icons@13.21.0 (last release that ships LinkedIn; removed in 14.0.0) | <https://brand.linkedin.com> | connect.svg |
| MongoDB | `mongodb` | simple-icons@16.36.0 | <https://www.mongodb.com/pressroom> | stack.svg |
| Node.js | `nodedotjs` | simple-icons@16.36.0 | <https://nodejs.org/en/about/branding> | stack.svg |
| Python | `python` | simple-icons@16.36.0 | <https://www.python.org/community/logos/> | stack.svg |
| Raspberry Pi | `raspberrypi` | simple-icons@16.36.0 | <https://www.raspberrypi.org/trademark-rules> | about-life.svg |
| React | `react` | simple-icons@16.36.0 | <https://github.com/facebook/create-react-app/blob/282c03f9525fdf8061ffa1ec50dce89296d916bd/test/fixtures/relative-paths/src/logo.svg> | stack.svg |
| Socket.io | `socketdotio` | simple-icons@16.36.0 | <https://socket.io> | stack.svg |
| Tailwind CSS | `tailwindcss` | simple-icons@16.36.0 | <https://tailwindcss.com/brand> | stack.svg |
| TensorFlow | `tensorflow` | simple-icons@16.36.0 | <https://www.tensorflow.org> | stack.svg |
| TypeScript | `typescript` | simple-icons@16.36.0 | <https://www.typescriptlang.org/branding> | stack.svg |
| YouTube | `youtube` | simple-icons@16.36.0 | <https://www.youtube.com/howyoutubeworks/resources/brand-resources/#logos-icons-and-colors> | connect.svg |

**LinkedIn:** current Simple Icons (v14 and later) no longer ships the LinkedIn mark, so it was
taken from `simple-icons@13.21.0`, the last release that has it. That release cites LinkedIn's
brand centre (<https://brand.linkedin.com>, guidelines <https://brand.linkedin.com/policies>) as
the source. The LinkedIn site itself could not be reached from the build sandbox, so the mark
was not downloaded from there directly. It is used unmodified, in LinkedIn blue (#0A66C2), to
link to Manash's own profile.

Brand colours are Simple Icons' official hex values. Marks that are too dark to read on navy
(for example Express, Socket.io and Raspberry Pi) are drawn in off-white, which Simple Icons
allows for monochrome use. Generic UI glyphs (pin, briefcase, arrows, trophy, the capability
icons) and the illustrations are original line drawings made for this README.

## Data shown in `id-dashboard.svg`

- Source: GitHub REST API, retrieved **2026-11-05**: `GET /user` and `GET /search/repositories?q=user:ManashR7488`, public repositories only.
- Public repositories 50, stars across public repos 20, followers 15, account created 2024-03-05.
- Primary-language split across public repos: JavaScript 26, not set 8, HTML 6, Python 5, CSS 2, C++ 1, EJS 1, TypeScript 1. Language colours are GitHub Linguist's.
- Featured-repo stars, languages and last-push dates come from the same snapshot (`tools/data/github-snapshot.json`).

These numbers are a dated snapshot and do not update by themselves. Re-run `tools/build.py`
after refreshing the snapshot to update them.

## Barcode

The ID-card barcode is a real Code 128-B encoding of `ManashR7488`. The symbol table was checked against the `python-barcode` reference tables.
