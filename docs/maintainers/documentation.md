# Maintain the documentation

The documentation is built with [Sphinx](https://www.sphinx-doc.org/) and the
[PyData Sphinx Theme](https://pydata-sphinx-theme.readthedocs.io/), following the same
structure and practices as the maintainer's other projects.

- Index pages (`index.rst` in each section) use reStructuredText and define navigation.
- All other hand-written pages use Markdown through [MyST-Parser](https://myst-parser.readthedocs.io/).
- API reference pages are reStructuredText and use `sphinx.ext.autodoc`, which imports the
  installed package. Docstrings use Sphinx field lists (`:param name:`, `:returns:`,
  `:raises ExceptionType:`).
- `docs/conf.py` reads the release version from `pyproject.toml`.

The dependencies live in the optional Poetry `docs` group (Sphinx 9.1+, MyST-Parser,
PyData Sphinx Theme and sphinx-favicon). `poetry.lock` pins their exact versions; no
`docs/requirements.txt` is used.

## Build locally

From the repository root:

```sh
poetry install --with docs
poetry run sphinx-build -W --keep-going -E -a -b html docs docs/_build/html
```

The build treats warnings as errors, with nitpicky cross-reference checks enabled.
It downloads the Python intersphinx inventory, so it needs network access to
`docs.python.org`. Open `docs/_build/html/index.html` to review the result, or serve it on
loopback only:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory docs/_build/html
```

Optionally check external links. Report unreachable targets instead of suppressing them:

```sh
poetry run sphinx-build -W --keep-going -b linkcheck docs docs/_build/linkcheck
```

`docs/_build/` is ignored by Git.

## Adding pages

1. Add a Markdown page to the right section: `getting-started/`, `guides/`, `reference/` or
   `maintainers/`.
2. List it in that section's `index.rst` toctree and add a short line describing it.
3. For a new section, such as `guides/` once there are task guides, add an `index.rst` and
   list it in the root `docs/index.rst` toctree.

Document only implemented behavior. Mark planned features as planned, use synthetic data
in examples, and never include real PATs, tenant IDs or incident data.

## Read the Docs

The root `.readthedocs.yaml` uses
[configuration v2](https://docs.readthedocs.com/platform/stable/config-file/v2.html). It
selects Ubuntu 24.04 and Python 3.12, installs Poetry 2.5.1, checks that the lockfile
matches `pyproject.toml`, and installs the runtime and `docs` groups from `poetry.lock`
into the Read the Docs environment through `READTHEDOCS_VIRTUALENV_PATH`. This follows the
[Poetry build customization](https://docs.readthedocs.com/platform/stable/build-customization.html#install-dependencies-with-poetry)
guidance. The package is installed because autodoc imports it. Builds fail on warnings.

The public project and documentation URL already exist. A configuration edit prepares
future builds; verify a hosted build at the exact reviewed source SHA before claiming
that edit is qualified. Project, version-build and integration settings are separate
maintainer actions. See {doc}`ci-and-publishing` for CI and rehearsal evidence requirements.

## Branding, logos and favicons

Dark mode is the default on first visit, and the theme switcher remembers each
reader's choice. The branding images live in `docs/_static/`:

| Folder | Contents | Used for |
| --- | --- | --- |
| `logos/` | Stacked logo with a navy wordmark, 160-1280 px wide, plus the master | Landing page in light mode (640 px file shown at 240 px) |
| `logos-dark/` | Stacked logo with a white wordmark, same sizes | Landing page in dark mode |
| `icons/` | Cloud mark without the wordmark, 32-1024 px wide, plus the master | Navbar logo (128 px file), next to the project name as text |
| `favicons/` | Square favicons, 16-256 px, a multi-size `favicon.ico`, and an opaque 180 px Apple touch icon | Browser tab and home-screen icons through `sphinx-favicon` |
| `social-previews/` | 1280 × 640 PNG and JPEG | GitHub repository social preview (set in the repository settings) |

The stacked logo is too small to read at navbar height, so the navbar pairs the cloud icon
with the project name. The landing page swaps between the light and dark logos with
PyData's `only-light` and `only-dark` image classes.

`*-master.png` files and `social-previews/` are excluded from the build in
`exclude_patterns`, so the source artwork is kept in the repository but not published with
the site. Keep file names stable; `docs/conf.py` and `docs/index.rst` reference them directly.

`docs/_static/custom.css` derives its accents from the logo's bright blue (`#0a84ff`) and
navy (`#002a66`), adjusted so all text meets at least WCAG AA contrast (4.5:1) in both
modes. The logo's navy pulse line has very low contrast on dark backgrounds, so the
stylesheet adds a soft glow to the logo images in dark mode only. A logo variant with a
lighter pulse line would make that glow unnecessary.

The Apple touch icon (`favicons/sfdctrust-apple-touch-icon-180.png`) has a white background
on purpose. iOS fills transparent touch icons with black, so keep any replacement opaque.

The social preview is not used as an Open Graph image for the docs. Doing that would need
an absolute site URL and, ideally, the `sphinxext-opengraph` extension.

After changing images or colors, rebuild and check the landing page and navbar in both
color modes and at a narrow width.

See the PyData theme's [light and dark mode](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/light-dark.html)
and [branding](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/branding.html)
guides, and the [sphinx-favicon](https://sphinx-favicon.readthedocs.io/) documentation.
