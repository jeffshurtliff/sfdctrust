# -*- coding: utf-8 -*-
"""
:Module:            docs.conf
:Synopsis:          Configures the Sphinx documentation build for sfdctrust
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via Claude Opus 5.5)
:Modified Date:     02 Nov 2026
"""

import tomllib
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
STATIC_DIR = DOCS_DIR / '_static'

# Read the version from pyproject.toml so the build never depends on stale installed metadata
with (DOCS_DIR.parent / 'pyproject.toml').open('rb') as metadata:
    package = tomllib.load(metadata)['project']

# -- Project information -----------------------------------------------------

project = 'sfdctrust'
author = 'Jeff Shurtliff'
copyright = '2026, Jeff Shurtliff'
release = package['version']
version = '.'.join(release.split('.')[:2])

# -- General configuration ---------------------------------------------------

needs_sphinx = '9.1'
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinx_favicon',
]
source_suffix = {'.rst': 'restructuredtext', '.md': 'markdown'}
root_doc = 'index'
language = 'en'
templates_path = ['_templates']
exclude_patterns = ['_build', '.DS_Store', 'Thumbs.db', 'desktop.ini']
nitpicky = True

# -- MyST configuration ------------------------------------------------------

myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'fieldlist',
    'replacements',
    'strikethrough',
]
myst_heading_anchors = 3
myst_links_external_new_tab = True

# -- Autodoc and intersphinx -------------------------------------------------

# The package is imported from the installed project (``poetry install --with docs``)
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- HTML output -------------------------------------------------------------

html_theme = 'pydata_sphinx_theme'
html_title = f'{project} {release} Documentation'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_context = {'default_mode': 'dark'}
html_show_sourcelink = True
html_copy_source = True
pygments_style = 'a11y-high-contrast-light'
pygments_dark_style = 'a11y-high-contrast-dark'
htmlhelp_basename = 'sfdctrust'

html_theme_options = {
    'logo': {'text': project, 'alt_text': f'{project} Documentation - Home'},
    'navbar_end': ['theme-switcher', 'navbar-icon-links'],
    'icon_links': [
        {
            'name': 'GitHub',
            'url': 'https://github.com/jeffshurtliff/sfdctrust',
            'icon': 'fa-brands fa-github',
        },
    ],
    'show_prev_next': True,
    'navigation_depth': 2,
    'show_toc_level': 2,
    'footer_start': ['custom_copyright'],
    'footer_end': ['sphinx-version', 'theme-version'],
}

# -- Branding assets ---------------------------------------------------------

# Logos and favicons are not created yet. Each one is enabled automatically once a file with
# the expected name is added to docs/_static/, so builds stay warning-free until then.
LOGO_LIGHT = 'sfdctrust-logo-light.png'
LOGO_DARK = 'sfdctrust-logo-dark.png'
FAVICONS = [
    {'rel': 'icon', 'sizes': '16x16', 'href': 'sfdctrust-favicon-16x16.png'},
    {'rel': 'icon', 'sizes': '32x32', 'href': 'sfdctrust-favicon-32x32.png'},
    {'rel': 'apple-touch-icon', 'sizes': '180x180', 'href': 'sfdctrust-apple-touch-icon-180x180.png'},
]

if (STATIC_DIR / LOGO_LIGHT).is_file():
    # Fall back to the light logo in dark mode until a dedicated dark variant exists
    dark_logo = LOGO_DARK if (STATIC_DIR / LOGO_DARK).is_file() else LOGO_LIGHT
    html_theme_options['logo'].update({'image_light': LOGO_LIGHT, 'image_dark': dark_logo})
    html_theme_options['logo'].pop('text')

favicons = [icon for icon in FAVICONS if (STATIC_DIR / icon['href']).is_file()]

# -- Link checking -----------------------------------------------------------

linkcheck_retries = 2
linkcheck_timeout = 15
