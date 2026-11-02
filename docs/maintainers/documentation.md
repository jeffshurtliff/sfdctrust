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
selects Ubuntu 24.04 and Python 3.12, installs Poetry 2.4.2, checks that the lockfile
matches `pyproject.toml`, and installs the runtime and `docs` groups from `poetry.lock`
into the Read the Docs environment through `READTHEDOCS_VIRTUALENV_PATH`. This follows the
[Poetry build customization](https://docs.readthedocs.com/platform/stable/build-customization.html#install-dependencies-with-poetry)
guidance. The package is installed because autodoc imports it. Builds fail on warnings.

The configuration file only prepares the repository. Creating the Read the Docs project,
connecting the repository and adding a `Documentation` URL to `pyproject.toml` are separate
maintainer steps.

## Branding, logos and favicons

Dark mode is the default on first visit, and the theme switcher remembers each
reader's choice. `docs/_static/custom.css` sets provisional blue and teal accents. Update
them to match the logo once it exists, and check that text contrast meets at least WCAG AA
(4.5:1 for normal text, 3:1 for large text) in both modes.

No logo or favicon files exist yet. `docs/conf.py` enables each asset automatically once a
file with the expected name is added to `docs/_static/`:

| File | Purpose |
| --- | --- |
| `sfdctrust-logo-light.png` | Navbar logo. Used in both modes unless a dark variant exists. |
| `sfdctrust-logo-dark.png` | Optional dark-mode navbar logo. |
| `sfdctrust-favicon-16x16.png` | Browser favicon, 16 × 16 pixels. |
| `sfdctrust-favicon-32x32.png` | Browser favicon, 32 × 32 pixels. |
| `sfdctrust-apple-touch-icon-180x180.png` | Apple touch icon, 180 × 180 pixels. |

Until a logo is present, the navbar shows the project name as text. A horizontal logo works
best; the stylesheet limits its height to 2.5rem (2rem on narrow screens). After adding
assets, rebuild and check the logo in both color modes and at narrow widths.

See the PyData theme's [light and dark mode](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/light-dark.html)
and [branding](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/branding.html)
guides, and the [sphinx-favicon](https://sphinx-favicon.readthedocs.io/) documentation.
